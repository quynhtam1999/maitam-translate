# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma** (Google AI Studio) và
**Qwen** (ModelScope, OpenAI-compatible).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật
giữ bố cục dùng **overlay PyMuPDF** (xóa chữ gốc tại chỗ + chèn bản dịch đè lên, tự co
cỡ chữ cho vừa).

## Trạng thái hiện tại (cập nhật 2026-07-02)

✅ **Đã kiểm thử end-to-end** (Python 3.14.5 + Node.js 24.18.0):
- Backend khởi động, `/api/health` trả `{"status":"ok"}`.
- **Không có đăng ký công khai.** Chỉ **admin** tạo được tài khoản mới (qua bảng "Quản trị"
  trong giao diện, hoặc `POST /api/auth/users`). Tài khoản admin đầu tiên được tạo tự động
  lúc khởi động từ `ADMIN_USERNAME`/`ADMIN_PASSWORD` trong `.env` (xem mục Cài đặt bên dưới).
- User tự đổi mật khẩu qua nút **Đổi mật khẩu** trong bảng Cài đặt (giống Google/YouTube).
  Đăng nhập sai nhiều lần liên tiếp sẽ bị khóa tạm thời chống dò mật khẩu.
- Các API làm việc chính yêu cầu session cookie `HttpOnly`. Đăng nhập **một lần**, phần mềm tự
  nhớ tài khoản trên thiết bị đó (mặc định 365 ngày, `AUTH_SESSION_DAYS`), và **tự gia hạn mỗi
  khi còn dùng app** — giống Google/YouTube: chỉ phải đăng nhập lại trên thiết bị mới hoặc khi
  xóa cookie/cache trình duyệt. Nút **Đăng xuất** (góc trên phải) vẫn xóa phiên ngay lập tức để
  đăng nhập tài khoản khác.
- `/api/providers` trả đúng danh sách **Qwen3 235B / Gemini / Gemma** cùng trạng thái key
  theo tài khoản đang đăng nhập và ghi chú hạn mức miễn phí.
- Tạo job dịch PDF qua `/api/pdf/jobs` thành công, job chuyển trạng thái đúng luồng
  (`queued` → `running` → `done` / `paused_quota` / `failed`).
- **Giao diện dark premium** (nền đen + gradient tím theo tông logo), có **bảng ⚙ Cài đặt**
  đầy đủ: nhập/xóa API key theo tài khoản, Qwen Base URL theo tài khoản, đổi mật khẩu,
  xem thống kê cache/job riêng của user và nút **xóa cache bản dịch / xóa lịch sử job & file**.
  Giới hạn quota (RPM/TPM/RPD) hiển thị cho mọi user nhưng **chỉ admin chỉnh được** (cấu hình
  chung, ghi vào `.env`). Admin có thêm bảng **Quản trị**: tạo/xóa tài khoản, đặt lại mật khẩu hộ user.

🔑 **API key được lưu riêng theo từng tài khoản** trong SQLite (`backend/storage/cache/auth.db`),
mã hóa at-rest bằng **AES-GCM** với secret server-side (`AUTH_SECRET_KEY` hoặc `auth_secret.key`).
Backend chỉ trả về trạng thái/masked key, không trả lại key gốc cho frontend.

✅ **Đã có logic dịch thật**:
- `backend/app/providers/gemini.py` & `qwen.py` gọi HTTP thật tới Gemini / ModelScope và lấy
  token usage từ phản hồi để đếm quota cục bộ.
- `backend/app/services/pdf_overlay.py` bóc chữ bằng PyMuPDF, giữ bố cục PDF gốc bằng overlay,
  hỗ trợ tài liệu 2 cột, giữ nguyên ảnh/biểu đồ dạng image block, và tách bảng dạng vector
  theo cell/dòng để không làm vỡ cấu trúc bảng.
- Ảnh/biểu đồ không được OCR và không dịch nội dung nằm trong ảnh; caption và chữ thật ngoài
  vùng ảnh vẫn được xử lý như văn bản PDF.

### Model Qwen đang dùng
`Qwen/Qwen3-235B-A22B-Instruct-2507` qua ModelScope (endpoint OpenAI-compatible).
Hạn mức miễn phí: **2.000 lượt gọi/ngày** (chung mọi model), tối đa **500 lượt/model/ngày**;
reset lúc 00:00 giờ Bắc Kinh (UTC+8), vượt hạn mức trả HTTP 429. Vì chỉ dùng 1 model để dịch
nên ngưỡng thực tế là 500/ngày (đã đặt `QWEN_RPD_LIMIT=500`).

### Cách xử lý quota

- **RPM** (requests per minute) và **TPM** (tokens per minute): khi bộ đếm cục bộ đạt giới hạn
  trong cửa sổ 60 giây, backend tự chờ tới khi sang cửa sổ phút kế tiếp rồi tiếp tục dịch.
- **RPD** (requests per day): khi đạt giới hạn ngày của model/key hiện tại, job ngưng ở trạng
  thái `paused_quota` và báo rõ đã hết giới hạn ngày; người dùng có thể chờ reset ngày hoặc
  đổi model/API key để dịch tiếp nhờ cache đoạn đã dịch.
- Khi dịch PDF, backend gom nhiều đoạn chưa có cache vào một request batch lớn theo TPM của
  model (mặc định Gemini/Gemma 250.000 TPM), nhằm giảm số request và tiết kiệm RPD.

## Kiến trúc

- `frontend/` — **React + Vite**: đăng nhập (không đăng ký), giao diện upload PDF, theo dõi tiến trình, tải kết quả, tab dịch văn bản, **bảng Cài đặt** (API key theo account / đổi mật khẩu / dọn cache), **bảng Quản trị** (chỉ admin).
- `backend/` — **Python + FastAPI + PyMuPDF**: auth/session cookie + vai trò admin, nhận PDF, dịch giữ bố cục, đa provider, đọc/ghi cấu hình runtime vào `.env`.

Dịch PDF chạy theo **mẫu job bất đồng bộ**: tạo job → poll trạng thái → tải file kết quả.
Bản dịch được **cache theo nội dung đoạn và user** (SQLite) nên hết quota/tắt máy vẫn **dịch tiếp**
được (resume), kể cả khi đổi sang model khác, nhưng không dùng chung cache giữa các tài khoản.

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
copy .env.example .env          # rồi điền GEMINI_API_KEY / QWEN_API_KEY khi có
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
    ├── main.py                 # FastAPI app, CORS, health check, bootstrap admin
    ├── core/                   # config.py, job_store.py, auth.py (dependencies), auth_store.py (accounts/sessions/crypto)
    ├── models/                 # Pydantic: auth, job, translate, provider, glossary, settings
    ├── routers/                # auth, pdf, text, providers, glossary, settings (lớp HTTP)
    ├── services/               # pdf_overlay, translator, pipeline, cache, glossary, job_runner, app_settings, user_data
    └── providers/              # base, gemini, qwen, registry, quota_tracker

backend/storage/                # uploads/, outputs/, cache/ (auth.db + segments.db + jobs.db), glossary/

frontend/
└── src/
    ├── api/translate.js        # gọi backend (auth, admin, job, text, providers, settings)
    └── components/             # AuthPage, AdminModal, SettingsModal, FileUpload, JobProgress, QuotaBadge, ResultView, TextTranslate
```

Router `auth` xử lý đăng nhập/đăng xuất/session/đổi mật khẩu, và (chỉ admin) tạo/xóa/liệt kê
tài khoản + đặt lại mật khẩu hộ user; logic tài khoản/mật khẩu/mã hóa key nằm trong
`core/auth_store.py`. Router `settings` (backend) + `SettingsModal` (frontend) đọc/ghi API key
mã hóa theo tài khoản, Qwen Base URL theo tài khoản, và dọn cache/job của user hiện tại;
**giới hạn quota chỉ admin sửa được** (ghi vào `.env`). `services/user_data.py` gom logic xóa
toàn bộ dữ liệu của một user (dùng khi admin xóa tài khoản, hoặc user tự dọn cache/job). Ở gốc
còn `start.bat` để khởi động nhanh cả hai server.

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
| GET/PUT | `/api/settings` | Xem / cập nhật API key và Qwen Base URL theo user; quota chỉ admin sửa |
| POST | `/api/settings/cache/clear` | Xóa cache bản dịch của user hiện tại |
| POST | `/api/settings/jobs/clear` | Xóa lịch sử job + file PDF của user hiện tại |

## Việc cần làm tiếp (TODO)

1. Kiểm thử thêm trên nhiều PDF y khoa 2 cột phức tạp, đặc biệt tài liệu scan/OCR kém hoặc bảng nhiều tầng.
2. Hoàn thiện xử lý glossary (mode `translate`/`keep`) trong `services/glossary.py`.
3. (Tùy chọn) nâng job runner từ `BackgroundTasks` lên hàng đợi thật nếu cần chạy song song.
