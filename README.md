# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma** (Google AI Studio) và
**Qwen** (ModelScope, OpenAI-compatible).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật
giữ bố cục dùng **overlay PyMuPDF** (xóa chữ gốc tại chỗ + chèn bản dịch đè lên, tự co
cỡ chữ cho vừa).

## Trạng thái hiện tại (cập nhật 2026-07-02)

✅ **Đã chạy & kiểm thử end-to-end** phần khung + giao diện (Python 3.14.5 + Node.js 24.18.0):
- Backend khởi động, `/api/health` trả `{"status":"ok"}`.
- `/api/providers` trả đúng danh sách **Qwen3 235B / Gemini / Gemma** cùng trạng thái key
  và ghi chú hạn mức miễn phí.
- Tạo job dịch PDF qua `/api/pdf/jobs` thành công, job chuyển trạng thái đúng luồng
  (`queued` → `running` → `done` / `paused_quota` / `failed`).
- **Giao diện dark premium** (nền đen + gradient tím theo tông logo), có **bảng ⚙ Cài đặt**
  đầy đủ: nhập/xóa API key, Qwen Base URL, chỉnh giới hạn quota riêng cho Qwen / Gemini / Gemma, xem thống kê
  cache và nút **xóa cache bản dịch / xóa lịch sử job & file**. Đã xác minh trên trình duyệt:
  mở modal → lưu cài đặt → ghi vào `.env` → danh sách mô hình tự cập nhật trạng thái key.

🔑 **API key đã được cấu hình** (Gemini + Qwen/ModelScope) trong `backend/.env`.

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

- `frontend/` — **React + Vite**: giao diện upload PDF, theo dõi tiến trình, tải kết quả, tab dịch văn bản, **bảng Cài đặt** (API key / quota / dọn cache).
- `backend/` — **Python + FastAPI + PyMuPDF**: nhận PDF, dịch giữ bố cục, đa provider, đọc/ghi cấu hình runtime vào `.env`.

Dịch PDF chạy theo **mẫu job bất đồng bộ**: tạo job → poll trạng thái → tải file kết quả.
Bản dịch được **cache theo nội dung đoạn** (SQLite) nên hết quota/tắt máy vẫn **dịch tiếp**
được (resume), kể cả khi đổi sang model khác.

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
    ├── main.py                 # FastAPI app, CORS, health check
    ├── core/                   # config.py, job_store.py (SQLite)
    ├── models/                 # Pydantic: job, translate, provider, glossary
    ├── routers/                # pdf, text, providers, glossary (lớp HTTP)
    ├── services/               # pdf_overlay, translator, pipeline, cache, glossary, job_runner
    └── providers/              # base, gemini, qwen, registry, quota_tracker

backend/storage/                # uploads/, outputs/, cache/ (segments.db + jobs.db), glossary/

frontend/
└── src/
    ├── api/translate.js        # gọi backend (job, text, providers, settings)
    └── components/             # FileUpload, JobProgress, QuotaBadge, ResultView, TextTranslate, SettingsModal
```

Router `settings` (backend) + `SettingsModal` (frontend) là phần mới: đọc/ghi API key, Qwen
Base URL, giới hạn quota vào `.env`, và dọn cache/job. Ở gốc còn `start.bat`
để khởi động nhanh cả hai server.

## API chính

| Method | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/pdf/jobs` | Tạo job dịch PDF (upload file + chọn provider) |
| GET | `/api/pdf/jobs/{id}` | Trạng thái + tiến trình job |
| POST | `/api/pdf/jobs/{id}/resume` | Dịch tiếp (đổi provider) khi hết quota |
| GET | `/api/pdf/jobs/{id}/download` | Tải PDF đã dịch |
| POST | `/api/text/translate` | Dịch văn bản dán tay |
| GET | `/api/providers` | Danh sách mô hình + trạng thái key |
| GET/POST | `/api/glossary` | Xem / tải lên từ điển thuật ngữ (CSV) |
| GET/PUT | `/api/settings` | Xem / cập nhật cấu hình (API key, base URL, quota) — ghi vào `.env` |
| POST | `/api/settings/cache/clear` | Xóa toàn bộ cache bản dịch (segments.db) |
| POST | `/api/settings/jobs/clear` | Xóa lịch sử job + file PDF gốc/đã dịch |

## Việc cần làm tiếp (TODO)

1. Kiểm thử thêm trên nhiều PDF y khoa 2 cột phức tạp, đặc biệt tài liệu scan/OCR kém hoặc bảng nhiều tầng.
2. Hoàn thiện xử lý glossary (mode `translate`/`keep`) trong `services/glossary.py`.
3. (Tùy chọn) nâng job runner từ `BackgroundTasks` lên hàng đợi thật nếu cần chạy song song.
