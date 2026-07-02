# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma 4 31B** (Google AI Studio) và
**Qwen3 235B** qua endpoint OpenAI-compatible tự triển khai (vLLM/SGLang).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật
giữ bố cục dùng **overlay PyMuPDF** (xóa chữ gốc tại chỗ + chèn bản dịch đè lên, tự co
cỡ chữ cho vừa).

## Trạng thái hiện tại (cập nhật 2026-07-02)

✅ **Tính năng chính đã có**
- Dịch PDF y khoa bằng job bất đồng bộ (`queued` → `running` → `done` / `paused_quota` / `failed`),
  có cache theo user để tiếp tục dịch khi hết quota, đổi model hoặc tắt/mở lại app.
- Dịch văn bản dán tay bằng 1 request cho mỗi lần gửi, giúp RPD không thể thấp hơn nữa ở luồng văn bản.
- Provider thật: Gemini, Gemma 4 31B qua Google AI Studio và Qwen3 235B qua endpoint
  OpenAI-compatible tự triển khai. Backend đọc token usage thật từ phản hồi để ghi quota cục bộ.
- PDF overlay bằng PyMuPDF: bóc chữ, xóa chữ gốc tại chỗ, chèn bản dịch, hỗ trợ tài liệu 2 cột,
  giữ ảnh/biểu đồ và tách bảng vector theo cell/dòng để hạn chế vỡ bố cục.
- Ảnh/biểu đồ chưa OCR nên không dịch chữ nằm trong ảnh; caption và chữ thật ngoài vùng ảnh vẫn được dịch.

✅ **Auth, tài khoản và cấu hình**
- Không có đăng ký công khai. Chỉ admin tạo/xóa tài khoản hoặc đặt lại mật khẩu hộ user qua bảng
  **Quản trị** hoặc API admin.
- Admin đầu tiên được bootstrap từ `ADMIN_USERNAME`/`ADMIN_PASSWORD` trong `.env` khi database
  chưa có admin.
- Session dùng cookie `HttpOnly`, mặc định nhớ đăng nhập 365 ngày (`AUTH_SESSION_DAYS`) và tự gia hạn
  khi còn dùng app; nút **Đăng xuất** xóa phiên ngay lập tức.
- API key Gemini/Qwen lưu riêng theo từng tài khoản trong SQLite
  (`backend/storage/cache/auth.db`), mã hóa at-rest bằng AES-GCM với secret server-side
  (`AUTH_SECRET_KEY` hoặc `auth_secret.key`). Backend chỉ trả trạng thái/masked key, không trả key gốc.
- Bảng **Cài đặt** cho phép nhập/xóa API key theo tài khoản, Qwen Base URL theo tài khoản,
  xem thống kê cache/job và xóa cache/job riêng của user.

✅ **Tối ưu RPD mới**
- Admin chỉnh được RPM/TPM/RPD và **Max token/request** cho Gemini, Gemma 4 31B, Qwen; các field này ghi
  vào `.env` và user thường chỉ xem được.
- Dịch PDF gom batch lớn nhất có thể theo ngân sách input `TPM × 0.8` và ngân sách output
  `Max token/request × 0.9`; không còn trần cứng 200 đoạn/request hoặc 200.000 token/request.
- Provider set giới hạn đầu ra khi gọi API (`generationConfig.maxOutputTokens` cho Gemini/Gemma 4 31B,
  `max_tokens` cho Qwen), giúp batch lớn ít bị cắt cụt JSON hơn.
- Dịch văn bản dán tay vẫn giữ 1 request/lần gửi nhưng cũng hưởng lợi từ giới hạn output mới.

✅ **Kiểm tra gần nhất**
- `backend/.venv/Scripts/python.exe -m compileall backend/app`: pass.
- Script kiểm tra batching giả lập: tăng TPM/Max token làm số batch giảm rõ rệt, batch nhiều item
  không vượt ngân sách output.
- `npm run build` trong `frontend/`: pass.
- `git diff --check`: pass.

⚠️ **Chưa kiểm thử lại trong lượt cập nhật này**
- Chưa chạy E2E PDF/text với API key thật và file PDF thật sau tối ưu RPD. Khi có key và file test,
  cần xác nhận job về `done`, PDF tải được, bố cục giữ ổn và `rpd_used` giảm so với cấu hình cũ.

### Model Qwen đang dùng
`Qwen/Qwen3-235B-A22B-Instruct-2507` từ ModelScope. Model card hiện báo không bật hosted
API inference (`SupportApiInference=false`), nên app không gọi mặc định vào
`https://api-inference.modelscope.ai/v1` nữa. Hãy chạy model bằng vLLM/SGLang để tạo endpoint
OpenAI-compatible rồi nhập `QWEN_BASE_URL` / Qwen Base URL, ví dụ `http://localhost:8001/v1`.
Nếu endpoint không yêu cầu khóa, có thể để trống API key; backend sẽ gửi `EMPTY` theo mẫu Qwen-Agent.

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
>
> **Deploy frontend (Vercel) tách domain với backend** là truy cập **cross-site** — trình duyệt
> chỉ gửi kèm cookie phiên nếu đặt `AUTH_COOKIE_SAMESITE=none` (tự bật kèm `Secure`, nên backend
> bắt buộc chạy HTTPS). Nếu để mặc định `lax`, giao diện vẫn đăng nhập được nhưng mọi thao tác
> cần xác thực sau đó (ví dụ lưu API key) sẽ báo lỗi *"Vui lòng đăng nhập..."* do cookie bị chặn.
> Đồng thời `BACKEND_CORS_ORIGINS` phải liệt kê đúng URL Vercel (không dùng `*` vì có
> `allow_credentials`), và frontend cần `VITE_API_URL` trỏ tới URL backend HTTPS.

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
    └── components/             # AuthPage, AdminModal, SettingsModal, ChangePasswordModal, FileUpload, JobProgress, QuotaBadge, ResultView, TextTranslate
```

Router `auth` xử lý đăng nhập/đăng xuất/session/đổi mật khẩu, và (chỉ admin) tạo/xóa/liệt kê
tài khoản + đặt lại mật khẩu hộ user; logic tài khoản/mật khẩu/mã hóa key nằm trong
`core/auth_store.py`. Frontend gọi `POST /api/auth/change-password` qua modal riêng
`ChangePasswordModal` (nút cạnh Đăng xuất), tách khỏi bảng Cài đặt. Router `settings`
(backend) + `SettingsModal` (frontend) đọc/ghi API key mã hóa theo tài khoản, Qwen Base URL
theo tài khoản, và dọn cache/job của user hiện tại; **giới hạn quota và Max token/request chỉ admin sửa được**
(ghi vào `.env`). `services/user_data.py` gom logic xóa toàn bộ dữ liệu của một user (dùng khi
admin xóa tài khoản, hoặc user tự dọn cache/job). Ở gốc còn `start.bat` để khởi động nhanh cả
hai server.

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
| GET/PUT | `/api/settings` | Xem / cập nhật API key và Qwen Base URL theo user; quota và Max token/request chỉ admin sửa |
| POST | `/api/settings/cache/clear` | Xóa cache bản dịch của user hiện tại |
| POST | `/api/settings/jobs/clear` | Xóa lịch sử job + file PDF của user hiện tại |

## Việc cần làm tiếp (TODO)

1. Kiểm thử thêm trên nhiều PDF y khoa 2 cột phức tạp, đặc biệt tài liệu scan/OCR kém hoặc bảng nhiều tầng.
2. Hoàn thiện xử lý glossary (mode `translate`/`keep`) trong `services/glossary.py`.
3. (Tùy chọn) nâng job runner từ `BackgroundTasks` lên hàng đợi thật nếu cần chạy song song.
