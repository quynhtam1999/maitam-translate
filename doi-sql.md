# Kế hoạch: Chuyển state ra ngoài (Neon Postgres + Object Storage) để deploy free-tier bền vững

## Context (vì sao làm việc này)

App **Mai Tam Translate** hiện lưu toàn bộ state trên đĩa cục bộ của backend:
- 3 SQLite DB: `auth.db` (tài khoản + API key mã hóa + session), `jobs.db` (job dịch PDF),
  `segments.db` (cache bản dịch theo user).
- File trên đĩa: `uploads/`, `outputs/` (PDF gốc + PDF đã dịch), `glossary/<user>/glossary.csv`.

Mọi host free (Render Free, Fly, Koyeb, HF Spaces…) đều có **filesystem ephemeral** + **ngủ khi
idle**, nên cứ restart/ngủ dậy là **mất sạch tài khoản, API key, cache, file**. Gắn Persistent Disk
của Render cần gói trả phí ($7/tháng).

**Mục tiêu:** tách state ra dịch vụ ngoài để app trở thành *stateless* → chạy bền trên bất kỳ host
free nào (kể cả ở lại Render Free), không mất dữ liệu khi host ngủ/restart.

**Quyết định đã chốt với user:**
1. **DB**: dùng **SQLAlchemy Core** — cùng một code chạy **SQLite khi local** (zero-setup, `start.bat`
   giữ nguyên) và **Postgres (Neon) khi deploy**. Chọn theo biến `DATABASE_URL`.
2. **File**: thêm **object storage** (S3-compatible: Cloudflare R2 / Supabase Storage / Backblaze B2)
   cho PDF + glossary. Local dev vẫn ghi ra đĩa như cũ. Chọn theo biến `S3_BUCKET`.
3. Host: **host-agnostic** — kế hoạch chỉ liệt kê env var cần đặt; chọn host sau, không đổi code.

---

## Phần A — Tầng DB: gộp 3 SQLite → SQLAlchemy Core (SQLite local / Postgres prod)

### A1. Dependency mới (`backend/requirements.txt`)
- `SQLAlchemy>=2.0`
- `psycopg[binary]>=3.1` (driver Postgres cho Neon)

### A2. Config mới (`backend/app/core/config.py`)
- Thêm `database_url: str = ""`.
- Thêm property `db_url`: nếu `database_url` rỗng → `sqlite:///<cache_dir>/app.db`; nếu có → dùng
  `database_url` (Neon). Chuẩn hóa prefix `postgres://` → `postgresql+psycopg://` cho SQLAlchemy 2 + psycopg3.

### A3. Module engine mới (`backend/app/core/db.py`)
- Tạo `engine = create_engine(url, pool_pre_ping=True, future=True)`.
  - Postgres/Neon: `pool_pre_ping=True` để tự phục hồi khi Neon autosuspend đóng kết nối.
  - SQLite: `connect_args={"check_same_thread": False}`, `poolclass=StaticPool` (một kết nối dùng chung,
    giống hành vi hiện tại với các thread của BackgroundTasks).
- Định nghĩa `MetaData` + 5 `Table`: `users`, `user_api_keys`, `sessions`, `jobs`, `segment_cache`
  (đúng cột như schema SQLite hiện tại; `REAL`→`Float`, `INTEGER`→`Integer`, `TEXT`→`String/Text`).
- `def init(url)`: tạo engine, `metadata.create_all(engine)` — thay toàn bộ `CREATE TABLE IF NOT EXISTS`
  + vá `PRAGMA table_info`/`ALTER TABLE` thủ công (schema mới tạo full ngay, không cần vá cột cũ).
- Helper `upsert(table)` chọn dialect-insert phù hợp:
  `sqlalchemy.dialects.postgresql.insert` hoặc `...sqlite.insert` (cả hai đều có
  `.on_conflict_do_update(...)` / `.on_conflict_do_nothing(...)`), chọn theo `engine.dialect.name`.

### A4. Viết lại 3 module DB, GIỮ NGUYÊN chữ ký hàm (routers/services không đổi)
- **`core/auth_store.py`**: thay `sqlite3` bằng SQLAlchemy Core (`engine.begin()`/`connect()`).
  - `INSERT ... VALUES(?)` → `conn.execute(users.insert(), {...})`, placeholder theo SQLAlchemy.
  - `sqlite3.IntegrityError` → `sqlalchemy.exc.IntegrityError`.
  - `ON CONFLICT(user_id) DO NOTHING` trong `update_api_keys` → `upsert(user_api_keys).on_conflict_do_nothing`.
  - `row["col"]` → dùng `Row._mapping` / `.mappings()` để truy cập theo tên cột.
  - **Giữ nguyên** toàn bộ logic mã hóa AES-GCM (`_seal/_open`, `_load_or_create_secret`,
    `AUTH_SECRET_KEY`) — không đụng crypto. Secret vẫn init riêng như hiện tại.
- **`core/job_store.py`**: tương tự; `update_job` dựng câu UPDATE động → `jobs.update().where(...).values(**sets)`.
  Cột `progress` vẫn là chuỗi JSON (`json.dumps/loads`) như cũ.
- **`services/cache.py`** (`SegmentCache`): đổi khởi tạo từ `SegmentCache(db_path, user_id)` →
  `SegmentCache(user_id)` dùng engine chung (bỏ tham số `db_path`). `set()` dùng
  `upsert(segment_cache).on_conflict_do_update(index_elements=["hash"], set_={...})`.
  - Cập nhật các nơi gọi: `services/pipeline.py:37`, `routers/text.py:44`, `routers/settings.py:22`,
    `routers/settings.py:105`, `services/user_data.py:49` → bỏ đối số `cache_dir/segments.db`.

### A5. `backend/app/main.py`
- Thay `job_store.init(cache_dir/"jobs.db")` + `auth_store.init(cache_dir/"auth.db", ...)` bằng:
  `db.init(settings.db_url)` (tạo engine + create_all) rồi `auth_store.init_secret(secret_path, secret)`
  (chỉ còn init khóa mã hóa), `auth_store.ensure_admin(...)` giữ nguyên.

---

## Phần B — Tầng file: Object Storage cho PDF + glossary

### B1. Dependency mới
- `boto3` (client S3-compatible; hoạt động với R2 / Supabase Storage / B2).

### B2. Config mới (`config.py`)
- `s3_endpoint_url: str = ""`, `s3_bucket: str = ""`, `s3_access_key_id: str = ""`,
  `s3_secret_access_key: str = ""`, `s3_region: str = "auto"`.

### B3. Module storage mới (`backend/app/services/storage.py`)
Interface chung, chọn backend theo `s3_bucket`:
- `put_bytes(key, data)`, `get_bytes(key) -> bytes | None`, `exists(key) -> bool`,
  `delete_prefix(prefix)`, và context manager `local_copy(key)` (tải object về file tạm để PyMuPDF mở),
  `upload_file(key, local_path)`.
- **LocalStorage** (khi chưa đặt `S3_BUCKET`): đọc/ghi dưới `settings.storage_path` — giữ nguyên hành
  vi dev hiện tại. `key` chính là đường dẫn tương đối trong `storage/`.
- **S3Storage** (khi có `S3_BUCKET`): `boto3.client("s3", endpoint_url=..., ...)`.
- `def init(settings)` chọn backend, gọi trong lifespan của `main.py`.

### B4. Sửa các điểm đọc/ghi file (dùng "storage key" thay vì đường dẫn đĩa)
Quy ước key: `uploads/{user}/{job}.pdf`, `outputs/{user}/{job}_vi.pdf`, `glossary/{user}/glossary.csv`.
Cột `jobs.input_path`/`output_path` **giữ tên cột**, nhưng nay chứa *storage key* thay vì path đĩa.
- **`routers/pdf.py`**: upload → `storage.put_bytes(input_key, await file.read())`; lưu key vào job.
  Download → `storage.get_bytes(output_key)` trả `Response(content, media_type="application/pdf",
  headers=Content-Disposition)` (thay `FileResponse`); kiểm tra `storage.exists`.
- **`services/pipeline.py`**: `with storage.local_copy(input_key) as tmp_in: doc = fitz.open(tmp_in)`;
  lưu ra file tạm rồi `storage.upload_file(output_key, tmp_out)`. Glossary đọc qua storage (xem B5).
- **`routers/glossary.py`**: upload → `storage.put_bytes(glossary_key, ...)`; get → đọc bytes qua storage.
- **`routers/text.py:45`**: glossary đọc qua storage.
- **`services/user_data.py`**: thay xóa thư mục đĩa bằng `storage.delete_prefix("uploads/{user}/")`,
  `"outputs/{user}/"`, `"glossary/{user}/"`. Bỏ `purge_jobs_and_files` phần resolve path đĩa.

### B5. `services/glossary.py`
- `load_glossary(path)` hiện đọc từ `Path`. Thêm `load_glossary_bytes(data: bytes)` (tách phần parse CSV),
  cho các nơi lấy bytes từ storage gọi. Giữ `load_glossary(path)` cho tương thích/nếu còn dùng local.

---

## Env var cần đặt khi deploy (host-agnostic)

```
# Bootstrap admin (lần đầu)
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
# Khóa mã hóa API key — BẮT BUỘC đặt cố định (python -c "import secrets;print(secrets.token_hex(32))")
AUTH_SECRET_KEY=<64 hex>
# DB: Neon pooled connection string (bật -pooler + sslmode=require)
DATABASE_URL=postgresql://user:pass@ep-xxx-pooler.<region>.aws.neon.tech/neondb?sslmode=require
# Object storage (S3-compatible: R2 / Supabase Storage / B2)
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
S3_BUCKET=maitam-files
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=auto
# Cookie/CORS khi frontend khác domain
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=none
BACKEND_CORS_ORIGINS=https://<frontend-url>
```
Local dev: **không** đặt `DATABASE_URL` và `S3_BUCKET` → tự dùng SQLite + đĩa như hiện tại.

---

## Files sẽ sửa (tóm tắt)
- Mới: `backend/app/core/db.py`, `backend/app/services/storage.py`.
- Sửa: `config.py`, `main.py`, `core/auth_store.py`, `core/job_store.py`, `services/cache.py`,
  `services/pipeline.py`, `services/user_data.py`, `services/glossary.py`,
  `routers/pdf.py`, `routers/glossary.py`, `routers/text.py`, `routers/settings.py`,
  `requirements.txt`, `.env.example`, `README.md`.
- **Không** đổi frontend (API không đổi).

## Ngoài phạm vi (ghi chú)
- **Quota admin ghi `.env`** (`services/app_settings.py`) vẫn ephemeral trên host free → khuyến nghị đặt
  quota qua env var (`GEMINI_RPM_LIMIT`…). Chuyển quota vào DB là follow-up tùy chọn, không làm lần này.
- **Job chạy bằng BackgroundTasks in-process**: host free ngủ giữa chừng → job dừng; bấm **Resume** dịch
  tiếp nhờ cache Postgres. Không đổi trong lần này.
- `quota_tracker` và `_login_attempts` là in-memory (reset khi restart) — chấp nhận được.

---

## Verification (kiểm thử end-to-end)

**1. Local (SQLite + đĩa, không đặt env cloud):**
- `python -m compileall backend/app` → pass.
- Chạy `uvicorn app.main:app --reload`; xác nhận tạo `storage/cache/app.db`.
- Luồng: tạo admin (bootstrap) → login → lưu API key (⚙ Cài đặt) → upload 1 PDF nhỏ →
  job `done` → download PDF → upload glossary → xóa cache/job. Xác nhận file nằm dưới `storage/`.
- `cd frontend && npm run build` → pass.

**2. Prod-like (Neon + S3 test):**
- Đặt `DATABASE_URL` (Neon test DB) + `S3_*` (bucket test); chạy lại luồng trên.
- Kiểm chứng dữ liệu bền: xem rows trong Neon Console (`users`, `user_api_keys`, `segment_cache`,
  `jobs`) và object trong bucket (`uploads/…`, `outputs/…`, `glossary/…`).
- **Restart process** → login lại, tài khoản/API key/cache/PDF vẫn còn (chứng minh không mất state).
- Tài khoản mới chưa lưu key: gọi dịch → vẫn trả **400** đúng như hành vi hiện tại.

**3. Regression:** đảm bảo hành vi provider (Gemini/Qwen/stream tiến trình), resume khi hết quota,
và masked key không đổi.
