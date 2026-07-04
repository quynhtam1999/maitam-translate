# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma 4 31B** (Google AI Studio) và
**Qwen3 235B** qua **ModelScope API-Inference** (endpoint OpenAI-compatible, server quốc tế `.ai`).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật
giữ bố cục dùng **overlay PyMuPDF** (xóa chữ gốc tại chỗ + chèn bản dịch đè lên, tự co
cỡ chữ cho vừa).

## Trạng thái hiện tại (cập nhật 2026-07-04)

✅ **Tính năng chính đã có**
- Dịch PDF y khoa bằng job bất đồng bộ (`queued` → `running` → `done` / `paused_quota` / `failed`),
  có cache theo user để tiếp tục dịch khi hết quota, đổi model hoặc tắt/mở lại app.
- Thanh tiến trình real-time: job báo từng giai đoạn (bóc tách cấu trúc PDF → đang dịch → dựng file PDF)
  và cập nhật "đang dịch X/N đoạn (Z%)" theo thời gian thực nhờ **stream** phản hồi provider — **không tốn thêm request**.
- Dịch văn bản dán tay bằng 1 request cho mỗi lần gửi, giúp RPD không thể thấp hơn nữa ở luồng văn bản.
- Provider thật: Gemini, Gemma 4 31B qua Google AI Studio và Qwen3 235B qua **ModelScope API-Inference**
  (OpenAI-compatible). Backend đọc token usage thật từ phản hồi để ghi quota cục bộ.
- PDF overlay bằng PyMuPDF: bóc chữ, xóa chữ gốc tại chỗ, chèn bản dịch, hỗ trợ tài liệu 2 cột,
  giữ ảnh/biểu đồ và tách bảng vector theo cell/dòng để hạn chế vỡ bố cục.
- Ảnh/biểu đồ chưa OCR nên không dịch chữ nằm trong ảnh; caption và chữ thật ngoài vùng ảnh vẫn được dịch.

✅ **Giao diện thân thiện với mobile**
- Header thu gọn thành nút `tên tài khoản ☰` mở panel thả xuống (Quản trị / Cài đặt / Đổi mật khẩu /
  Đăng xuất) trên màn hình ≤720px, thay vì dàn hàng ngang dễ vỡ layout; desktop giữ nguyên các nút inline.
- Tabs, nút, ô chọn/nhập đều đạt vùng chạm ≥44px; input/textarea/select dùng `font-size: 16px` để
  tránh Safari/iOS tự phóng to khi focus.
- Modal (Cài đặt, Quản trị, Đổi mật khẩu) hiển thị gần full-screen trên điện thoại, header và thanh nút
  dưới cùng dính (sticky) khi cuộn.
- Bảng giới hạn quota trong ⚙ Cài đặt chuyển từ lưới 5 cột (phải cuộn ngang) sang các ô xếp dọc có nhãn
  RPM/TPM/RPD/Max token riêng từng ô trên mobile; desktop vẫn giữ dạng lưới cũ.
- Bảng danh sách tài khoản trong **Quản trị** reflow thành thẻ xếp dọc trên mobile thay vì bảng bị tràn.
- Khung nội dung chính (`.app`) rộng hơn trên desktop (`max-width: 1200px`, trước là 860px) để đỡ chật
  trên màn hình lớn; layout mobile (≤720px) không đổi.

✅ **Auth, tài khoản và cấu hình**
- Không có đăng ký công khai. Chỉ admin tạo/xóa tài khoản hoặc đặt lại mật khẩu hộ user qua bảng
  **Quản trị** hoặc API admin.
- Admin đầu tiên được bootstrap từ `ADMIN_USERNAME`/`ADMIN_PASSWORD` trong `.env` khi database
  chưa có admin.
- Session dùng cookie `HttpOnly`, mặc định nhớ đăng nhập 365 ngày (`AUTH_SESSION_DAYS`) và tự gia hạn
  khi còn dùng app; nút **Đăng xuất** xóa phiên ngay lập tức.
- API key Gemini/Qwen lưu riêng theo từng tài khoản trong bảng `user_api_keys`, mã hóa at-rest
  bằng AES-GCM với secret server-side (`AUTH_SECRET_KEY` hoặc `auth_secret.key`). Backend chỉ trả
  trạng thái/masked key, không trả key gốc.
- **Không có key dùng chung**: `.env` không cấu hình API key Gemini/Gemma/Qwen, và tầng provider
  không fallback về key toàn cục nào — tài khoản chưa tự lưu key sẽ bị chặn (400) ngay khi gọi dịch.
- Bảng **Cài đặt** cho phép nhập/xóa API key theo tài khoản, cấu hình Qwen theo tài khoản
  (API key ModelScope + Base URL + tên model), xem thống kê cache/job và xóa cache/job riêng của user.

✅ **State ra ngoài — deploy free-tier bền vững**
- Tầng DB dùng **SQLAlchemy Core**: cùng một code chạy **SQLite cục bộ** (`storage/cache/app.db`,
  zero-setup, `start.bat` giữ nguyên) khi `DATABASE_URL` trống, và **Postgres (Neon)** khi đặt
  `DATABASE_URL` — gộp 3 DB cũ (`auth.db`/`jobs.db`/`segments.db`) thành 5 bảng
  (`users`, `user_api_keys`, `sessions`, `jobs`, `segment_cache`) trong một engine dùng chung
  (`core/db.py`).
- Tầng file (PDF gốc/đã dịch + glossary) qua **object storage abstraction**
  (`services/storage.py`): `LocalStorage` ghi xuống `storage/` như cũ khi `S3_BUCKET` trống,
  `S3Storage` (boto3, S3-compatible: Cloudflare R2 / Supabase Storage / Backblaze B2) khi đặt
  `S3_BUCKET`. Cột `jobs.input_path`/`output_path` nay chứa *storage key*
  (`uploads/{user}/{job}.pdf`…) thay vì đường dẫn đĩa.
- Nhờ vậy app **stateless** trên host free có filesystem ephemeral (Render Free, Fly, Koyeb, HF
  Spaces…): restart/ngủ dậy không mất tài khoản, API key, cache bản dịch hay file PDF. Không cần
  Persistent Disk trả phí. Xem biến môi trường ở mục **Deploy** bên dưới.

✅ **Tối ưu RPD mới**
- Admin chỉnh được RPM/TPM/RPD và **Max token/request** cho Gemini, Gemma 4 31B, Qwen; các field này ghi
  vào `.env` và user thường chỉ xem được.
- Dịch PDF gom batch lớn nhất có thể theo ngân sách input `TPM × 0.8` và ngân sách output
  `Max token/request × 0.9`; không còn trần cứng 200 đoạn/request hoặc 200.000 token/request.
- Provider set giới hạn đầu ra khi gọi API (`generationConfig.maxOutputTokens` cho Gemini/Gemma 4 31B,
  `max_tokens` cho Qwen), giúp batch lớn ít bị cắt cụt JSON hơn.
- Dịch PDF **stream** phản hồi provider (SSE) để cập nhật tiến trình theo từng đoạn dịch xong ngay trong
  lúc nhận — **vẫn đúng 1 request cho mỗi batch**, không đánh đổi RPD để lấy thanh tiến trình real-time.
- Dịch văn bản dán tay vẫn giữ 1 request/lần gửi nhưng cũng hưởng lợi từ giới hạn output mới.

✅ **Kiểm tra gần nhất**
- `python -m compileall backend/app`: pass. Import `app.main` thành công (11 route).
- Sanity test FastAPI bằng `TestClient` (SQLite + đĩa cục bộ, storage tạm cô lập): bootstrap admin
  → login → lưu API key (mã hóa AES-GCM, masked đúng) → upload/đọc glossary CSV → tạo job PDF tối giản
  → tải PDF kết quả → xóa job/file qua `/api/settings/jobs/clear`.
- Sanity test trực tiếp tầng DB/storage: init SQLite qua SQLAlchemy, đọc/ghi API key, cache segment,
  storage local và `job_store` đều pass.
- `npm run build` trong `frontend/`: pass (API không đổi nên không cần sửa frontend).

⚠️ **Chưa kiểm thử lại trong lượt cập nhật này**
- Chưa chạy full E2E qua giao diện thật (browser) với API key thật của một provider — lượt này
  test qua `TestClient`/API local để xác nhận tầng DB/storage, chưa xác nhận lại bố cục PDF sau dịch.
- Chưa test thật với Postgres (Neon)/S3 (R2 hay tương đương) — chỉ verify SQLite + đĩa cục bộ.

### Model Qwen đang dùng
Mặc định `Qwen/Qwen3-235B-A22B-Instruct-2507` qua **ModelScope API-Inference** (server quốc tế
`https://api-inference.modelscope.ai/v1`). Cấu hình gồm **3 trường**, nhập trong ⚙ Cài đặt theo
từng tài khoản: **API key ModelScope** (lấy ở [modelscope.ai](https://modelscope.ai), dạng `ms-...`),
**Base URL** và **tên model** — cả ba đều sửa được để đổi sang model ModelScope khác.

**Mọi provider (Gemini, Gemma 4 31B, Qwen) đều bắt buộc mỗi tài khoản tự nhập API key riêng của
mình** trong ⚙ Cài đặt thì mới dịch được — không có key dùng chung của admin hay tài khoản khác;
`.env` không cấu hình API key.

### Cách xử lý quota

- **RPM** (requests per minute) và **TPM** (tokens per minute): khi bộ đếm cục bộ đạt giới hạn
  trong cửa sổ 60 giây, backend tự chờ tới khi sang cửa sổ phút kế tiếp rồi tiếp tục dịch.
- **RPD** (requests per day): khi đạt giới hạn ngày của model/key hiện tại, job ngưng ở trạng
  thái `paused_quota` và báo rõ đã hết giới hạn ngày; người dùng có thể chờ reset ngày hoặc
  đổi model/API key để dịch tiếp nhờ cache đoạn đã dịch.
- Khi dịch PDF, backend gom nhiều đoạn chưa có cache vào batch lớn nhất có thể theo **TPM do admin đặt**
  và **Max token/request** của từng model. TPM giữ batch trong ngân sách phút, còn Max token/request được
  truyền xuống API (`maxOutputTokens`/`max_tokens`) để hạn chế phản hồi bị cắt cụt, nhờ đó giảm số request
  và tiết kiệm RPD.
- Trong lúc dịch batch, backend **stream** phản hồi (SSE) và đếm số đoạn đã dịch xong để đẩy tiến trình
  real-time ra frontend **mà không tách nhỏ request** — RPD giữ nguyên như khi gộp batch tối đa.

## Kiến trúc

- `frontend/` — **React + Vite**: đăng nhập (không đăng ký), giao diện upload PDF, theo dõi tiến trình, tải kết quả, tab dịch văn bản, **bảng Cài đặt** (API key theo account / đổi mật khẩu / dọn cache), **bảng Quản trị** (chỉ admin).
- `backend/` — **Python + FastAPI + PyMuPDF**: auth/session cookie + vai trò admin, nhận PDF, dịch giữ bố cục, đa provider, đọc/ghi cấu hình runtime vào `.env`.

Dịch PDF chạy theo **mẫu job bất đồng bộ**: tạo job → poll trạng thái → tải file kết quả.
Bản dịch được **cache theo nội dung đoạn và user** (SQLAlchemy Core — SQLite cục bộ hoặc Postgres
khi deploy) nên hết quota/tắt máy vẫn **dịch tiếp** được (resume), kể cả khi đổi sang model khác,
nhưng không dùng chung cache giữa các tài khoản.

## Yêu cầu

- **Python** >= 3.11 — hiện dùng `Python 3.14.5`
- **Node.js** >= 18 — đã cài: `v24.18.0` tại `C:\Program Files\nodejs`

> Nếu lệnh `python`/`node`/`npm` báo "not recognized" trong terminal mới, PATH của
> Windows chưa nạp lại sau khi cài — mở terminal mới hoặc thêm thủ công
> `C:\Program Files\nodejs` và thư mục Python vào PATH.

> ⚠️ **Lưu ý về `.venv`:** venv của backend được tạo lại bằng Python 3.14.5 hiện có trên máy
> (bản Python cũ mà venv trỏ tới trước đây đã bị gỡ). Nếu đổi máy hoặc venv hỏng, xóa
> `backend/.venv` rồi tạo lại theo hướng dẫn bên dưới.

## Chạy nhanh (Windows)

Cách nhanh nhất: double-click **`start.bat`** ở thư mục gốc — script mở 2 cửa sổ, khởi động
backend (uvicorn :8000) và frontend (Vite :5173). Lần đầu vẫn cần cài đặt theo mục dưới.

## Cài đặt & chạy (development)

### Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # rồi điền ADMIN_USERNAME/ADMIN_PASSWORD (API key provider nhập sau, theo từng tài khoản, trong ⚙ Cài đặt)
uvicorn app.main:app --reload --port 8000
```

> ⚠️ **Bắt buộc trước lần chạy đầu tiên:** điền `ADMIN_USERNAME` và `ADMIN_PASSWORD` trong
> `.env`. Vì không có nút đăng ký công khai, đây là cách duy nhất để có tài khoản đầu tiên —
> app tự tạo (hoặc nâng quyền) tài khoản admin này khi khởi động lần đầu. Sau đó admin đăng
> nhập và tạo các tài khoản khác qua bảng **Quản trị** trong giao diện.
>
> Nếu database đã có sẵn tài khoản trùng `ADMIN_USERNAME` (ví dụ tài khoản `admin` tạo lúc
> còn cho đăng ký công khai) thì app chỉ **nâng quyền** tài khoản đó thành admin, **giữ nguyên
> mật khẩu cũ** — `ADMIN_PASSWORD` lúc này bị bỏ qua. Bootstrap chỉ chạy khi database chưa có
> admin nào; chạy lại sau đó sẽ không có tác dụng.
>
> Khi deploy qua HTTPS thật, nhớ đặt `AUTH_COOKIE_SECURE=true` và một `AUTH_SECRET_KEY` dài,
> riêng cho server (nếu để trống app tự sinh secret cục bộ, không di chuyển được sang máy khác).
>
> **Deploy frontend (Vercel) + backend (Render) khác domain** → dùng **Vercel rewrites** để
> proxy `/api/*` sang backend, biến request thành **same-site** thay vì cross-site (cookie
> phiên không còn bị trình duyệt di động/Safari chặn nữa, không cần `AUTH_COOKIE_SAMESITE=none`).
> Xem `frontend/vercel.json` (đích trỏ tới URL Render thật). Kèm theo:
> - Đặt biến môi trường `VITE_API_URL=/api` (đường dẫn tương đối, **không** trỏ thẳng URL Render)
>   trong Vercel Project Settings → Environment Variables, rồi redeploy.
> - `BACKEND_CORS_ORIGINS`/`AUTH_COOKIE_SAMESITE` giữ mặc định (`lax`) là đủ vì trình duyệt giờ
>   chỉ thấy request cùng domain Vercel; `AUTH_COOKIE_SECURE=true` vẫn nên bật vì Vercel luôn HTTPS.
> - Render free tier tự ngủ sau ~15 phút không dùng — request đầu tiên qua proxy có thể chờ
>   vài chục giây để backend khởi động lại, không liên quan tới cấu hình proxy.

Mở `http://localhost:8000/docs` để xem & thử các API (Swagger UI).

### Frontend (http://localhost:5173)

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Cấu trúc thư mục

```
backend/
├── requirements.txt
├── .env.example
└── app/
    ├── main.py                 # FastAPI app, CORS, health check, bootstrap admin, init db + storage
    ├── core/                   # config.py, db.py (engine + schema dùng chung), job_store.py, auth.py (dependencies), auth_store.py (accounts/sessions/crypto)
    ├── models/                 # Pydantic: auth, job, translate, provider, glossary, settings
    ├── routers/                # auth, pdf, text, providers, glossary, settings (lớp HTTP)
    ├── services/               # pdf_overlay, translator, pipeline, cache, glossary, job_runner, app_settings, user_data, storage (object storage abstraction)
    └── providers/              # base, gemini, qwen, registry, quota_tracker

backend/storage/                # dev cục bộ (khi DATABASE_URL/S3_BUCKET trống): uploads/, outputs/,
                                 # cache/app.db (users, user_api_keys, sessions, jobs, segment_cache), glossary/

frontend/
└── src/
    ├── api/translate.js        # gọi backend (auth, admin, job, text, providers, settings)
    └── components/             # AuthPage, AdminModal, SettingsModal, ChangePasswordModal, FileUpload, JobProgress, QuotaBadge, ResultView, TextTranslate
```

Router `auth` xử lý đăng nhập/đăng xuất/session/đổi mật khẩu, và (chỉ admin) tạo/xóa/liệt kê
tài khoản + đặt lại mật khẩu hộ user; logic tài khoản/mật khẩu/mã hóa key nằm trong
`core/auth_store.py`. Frontend gọi `POST /api/auth/change-password` qua modal riêng
`ChangePasswordModal` (nút cạnh Đăng xuất), tách khỏi bảng Cài đặt. Router `settings`
(backend) + `SettingsModal` (frontend) đọc/ghi API key mã hóa theo tài khoản, cấu hình Qwen
theo tài khoản (Base URL + tên model), và dọn cache/job của user hiện tại; **giới hạn quota và Max token/request chỉ admin sửa được**
(ghi vào `.env`). `services/user_data.py` gom logic xóa toàn bộ dữ liệu của một user qua
`services/storage.py` (dùng khi admin xóa tài khoản, hoặc user tự dọn cache/job). Ở gốc còn
`start.bat` để khởi động nhanh cả hai server.

## Deploy (state ra ngoài — free-tier bền vững)

Mặc định (không đặt `DATABASE_URL`/`S3_BUCKET`) app lưu state trên đĩa cục bộ — phù hợp dev,
nhưng **mất dữ liệu khi host free ngủ/restart** (filesystem ephemeral). Đặt các biến sau khi
deploy để state sống ngoài host, bất kỳ host free nào cũng chạy bền:

```
# Bootstrap admin (lần đầu)
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
# Khóa mã hóa API key — BẮT BUỘC đặt cố định (python -c "import secrets;print(secrets.token_hex(32))")
AUTH_SECRET_KEY=<64 hex>
# DB: Neon Postgres pooled connection string (bật -pooler + sslmode=require)
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

Không có nút chuyển đổi runtime — engine/backend storage được chọn một lần khi tiến trình khởi
động (`db.init`/`storage.init` trong `main.py` lifespan), dựa vào `DATABASE_URL`/`S3_BUCKET` lúc
đó có rỗng hay không.

## API chính

| Method | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/auth/login` | Đăng nhập và set session cookie |
| POST | `/api/auth/logout` | Đăng xuất, xóa session |
| GET | `/api/auth/me` | Xem user hiện tại (kèm `is_admin`) |
| POST | `/api/auth/change-password` | Tự đổi mật khẩu (yêu cầu mật khẩu hiện tại) |
| GET | `/api/auth/users` | *(admin)* Liệt kê tài khoản |
| POST | `/api/auth/users` | *(admin)* Tạo tài khoản mới |
| DELETE | `/api/auth/users/{id}` | *(admin)* Xóa tài khoản + toàn bộ dữ liệu của user đó |
| POST | `/api/auth/users/{id}/reset-password` | *(admin)* Đặt lại mật khẩu hộ user, thu hồi phiên cũ |
| POST | `/api/pdf/jobs` | Tạo job dịch PDF (upload file + chọn provider) |
| GET | `/api/pdf/jobs/{id}` | Trạng thái + tiến trình job |
| POST | `/api/pdf/jobs/{id}/resume` | Dịch tiếp (đổi provider) khi hết quota |
| GET | `/api/pdf/jobs/{id}/download` | Tải PDF đã dịch |
| POST | `/api/text/translate` | Dịch văn bản dán tay |
| GET | `/api/providers` | Danh sách mô hình + trạng thái key của user hiện tại |
| GET/POST | `/api/glossary` | Xem / tải lên từ điển thuật ngữ (CSV) theo user |
| GET/PUT | `/api/settings` | Xem / cập nhật API key, Qwen Base URL + tên model theo user; quota và Max token/request chỉ admin sửa |
| POST | `/api/settings/cache/clear` | Xóa cache bản dịch của user hiện tại |
| POST | `/api/settings/jobs/clear` | Xóa lịch sử job + file PDF của user hiện tại |

## Việc cần làm tiếp (TODO)

1. Kiểm thử thêm trên nhiều PDF y khoa 2 cột phức tạp, đặc biệt tài liệu scan/OCR kém hoặc bảng nhiều tầng.
2. Hoàn thiện xử lý glossary (mode `translate`/`keep`) trong `services/glossary.py`.
3. (Tùy chọn) nâng job runner từ `BackgroundTasks` lên hàng đợi thật nếu cần chạy song song — cần
   thiết hơn khi deploy thật vì host free ngủ giữa chừng làm job dừng (bấm **Resume** dịch tiếp
   được nhờ cache Postgres, nhưng job không tự chạy lại).
4. Quota admin chỉnh trong bảng **Quản trị** vẫn ghi vào `.env` (ephemeral trên host free) — khi
   deploy nên đặt quota qua env var lúc khởi tạo (`GEMINI_RPM_LIMIT`…) thay vì sửa runtime. Chuyển
   quota vào DB là follow-up tùy chọn.
5. `quota_tracker` và giới hạn đăng nhập sai (`_login_attempts`) vẫn in-memory (reset khi restart)
   — chấp nhận được, không nằm trong phạm vi việc tách state lần này.
