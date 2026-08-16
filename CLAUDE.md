# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma 4 31B** (Google AI Studio) và
**Qwen3 235B** qua **ModelScope API-Inference** (endpoint OpenAI-compatible, server quốc tế `.ai`).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật giữ bố
cục nằm ở **engine bố cục riêng** (`services/layout/`, PyMuPDF): nhận diện cấu trúc trang
(bảng / hình / chữ) trước, dịch theo **khối trọn vẹn**, rồi rót bản dịch trở lại đúng cấu trúc.

## Trạng thái hiện tại (cập nhật 2026-08-16)

✅ **Tính năng chính đã có**
- Dịch PDF y khoa bằng job bất đồng bộ (`queued` → `running` → `done` / `paused_quota` / `failed`),
  có cache theo user để tiếp tục dịch khi hết quota, đổi model hoặc tắt/mở lại app.
- Thanh tiến trình real-time: job báo từng giai đoạn (bóc tách cấu trúc PDF → đang dịch → dựng file PDF)
  và cập nhật "đang dịch X/N đoạn (Z%)" theo thời gian thực nhờ **stream** phản hồi provider — **không tốn thêm request**.
- Dịch văn bản dán tay bằng 1 request cho mỗi lần gửi, giúp RPD không thể thấp hơn nữa ở luồng văn bản.
- Provider thật: Gemini, Gemma 4 31B qua Google AI Studio và Qwen3 235B qua **ModelScope API-Inference**
  (OpenAI-compatible). Backend đọc token usage thật từ phản hồi để ghi quota cục bộ.
- Engine bố cục PDF (`services/layout/`): nhận diện bảng (theo nền tô + nét kẻ + `find_tables`),
  hình/nhãn trong hình, hộp lưu đồ, caption, footnote, header–footer chạy trang, rồi chia cột và
  gom dòng thành **khối dịch trọn vẹn**. Bản dịch được dựng lại đúng khối, đúng cột, đúng ô bảng.
- Ảnh/biểu đồ chưa OCR nên không dịch chữ **nằm bên trong ảnh raster**; nhãn, caption và mọi chữ
  thật (kể cả chữ nằm ĐÈ trên ảnh hoặc trên nền màu) đều được dịch tại chỗ.

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
  (`core/db.py`). SQLite file-backed dùng `QueuePool` để web thread và worker dịch có connection
  riêng; `StaticPool` chỉ giữ cho SQLite in-memory trong test.
- Tầng file (PDF gốc/đã dịch + glossary) qua **object storage abstraction**
  (`services/storage.py`): `LocalStorage` ghi xuống `storage/` như cũ khi `S3_BUCKET` trống,
  `S3Storage` (boto3, S3-compatible: Cloudflare R2 / Supabase Storage / Backblaze B2) khi đặt
  `S3_BUCKET`. Cột `jobs.input_path`/`output_path` nay chứa *storage key*
  (`uploads/{user}/{job}.pdf`…) thay vì đường dẫn đĩa.
- Nhờ vậy app **stateless** trên host free có filesystem ephemeral (Render Free, Fly, Koyeb, HF
  Spaces…): restart/ngủ dậy không mất tài khoản, API key, cache bản dịch hay file PDF. Không cần
  Persistent Disk trả phí. Xem biến môi trường ở mục **Deploy** bên dưới.

✅ **Chống lỗi 502 khi deploy Vercel → Render (2026-07-15)**
- Ca thật sau khi gộp câu: job Gemini 20 trang đã hoàn tất **679/679 đơn vị**, `status="done"`,
  `error=null`, nhưng frontend từng báo `Lỗi 502`. Đây **không phải lỗi provider**: `done` chỉ được
  ghi sau khi dựng PDF và upload file kết quả thành công; 502 phát sinh ở lớp proxy/poll status.
- Điểm nghẽn phù hợp nhất với ca lỗi là `BackgroundTasks` await pipeline async trên event loop web,
  trong khi PyMuPDF, boto3 và SQLAlchemy là đồng bộ; chưa có Vercel/Render timing log để khẳng định
  đây là nguyên nhân production duy nhất của 502. Các pha tải glossary/PDF từ storage, bóc cấu trúc,
  dịch + đọc/ghi cache, dựng PDF và upload/download nay chạy qua worker thread; endpoint poll vẫn
  phản hồi trong lúc job nặng đang chạy. SQLite in-memory cố ý giữ cùng thread vì dùng một connection.
- Frontend không còn dừng vĩnh viễn ở lỗi mạng/502 đầu tiên: `ApiError` giữ cả HTTP status và body;
  poll chấp nhận body `JobStatus` hợp lệ của đúng job ngay cả khi proxy gắn 502, đồng thời retry
  lỗi mạng/408/425/429/5xx tối đa 8 lần với exponential backoff (trần 15 giây).
- Mỗi vòng poll có `AbortController` và identity guard: đổi job, đăng xuất hoặc unmount sẽ hủy
  request/timer cũ, tránh poll cũ ghi đè trạng thái của phiên hay job mới.

✅ **Tối ưu RPD mới**
- Admin chỉnh được RPM/TPM/RPD và **Max token/request** cho Gemini, Gemma 4 31B, Qwen; các field này ghi
  vào `.env` và user thường chỉ xem được.
- Dịch PDF gom batch lớn theo ngân sách input `TPM × 0.8` và ngân sách output
  `Max token/request × 0.9`, **trần 200 đoạn/request** (`_MAX_BATCH_ITEMS`).
  > Trần 200 từng bị bỏ, nay đặt lại sau khi **đo thật** (2026-07-15) — lý do là **độ ổn định của
  > stream**, không phải trần token: tài liệu 738 đoạn gom vào 1 request thì stream đứt ở 702/738,
  > phải chia đôi 2 lần → **5 request / 294s**; để trần 200 → **4 request / 124s**, không lần nào
  > phải chia. Trần 200 vừa tiết kiệm RPD hơn vừa nhanh gấp đôi.
- Provider set giới hạn đầu ra khi gọi API (`generationConfig.maxOutputTokens` cho Gemini/Gemma 4 31B,
  `max_tokens` cho Qwen), giúp batch lớn ít bị cắt cụt JSON hơn.
- Gemini/Gemma gửi kèm **`generationConfig.responseSchema`** để ràng buộc cấu trúc JSON batch dịch
  (xem `_BATCH_RESPONSE_SCHEMA` trong `providers/gemini.py`). **Bắt buộc, không phải tối ưu**: chỉ đặt
  `responseMimeType="application/json"` và dặn trong prompt là KHÔNG đủ — xem mục *Bài học* bên dưới.
- Dịch PDF **stream** phản hồi provider (SSE) để cập nhật tiến trình theo từng đoạn dịch xong ngay trong
  lúc nhận — **vẫn đúng 1 request cho mỗi batch**, không đánh đổi RPD để lấy thanh tiến trình real-time.
- Dịch văn bản dán tay vẫn giữ 1 request/lần gửi nhưng cũng hưởng lợi từ giới hạn output mới.
- **Batch hỏng thì tự chia đôi và dịch lại** (`_translate_batch_with_split` trong
  `services/translator.py`): bắt `ProviderBatchError` (JSON cụt / thiếu mảng / sai số đoạn), chia
  đôi đệ quy tới khi còn 1 đoạn. Chỉ tốn thêm request **khi thật sự hỏng**; job tự cứu thay vì mất
  trắng cả tài liệu. Request hỏng vẫn được `quota_tracker.record()` vì nó **đã tiêu quota thật** —
  không ghi thì RPM/RPD bị đếm thiếu.

✅ **Viết lại engine bố cục PDF (2026-08-16)** — `services/layout/`
Engine cũ (`pdf_overlay.py` + `segment_merge.py`) đã **bị xoá**. Nó coi mọi block PyMuPDF là văn
xuôi như nhau, rồi cứu vãn bằng cách gộp mảnh câu và **cắt bản dịch theo tỉ lệ ký tự** rải về từng
bbox. Chạy `01. tntc.pdf` (sách sản phụ khoa 18 trang, 2 cột) đo được nó hỏng nặng:

| Lỗi đo được ở bản cũ | Nguyên nhân |
|---|---|
| Bảng 32-1 **trắng trơn**, chữ của bảng bị hút sang khối khác | `_looks_like_table_block` đòi ≥4 dòng *trong một block*; sách này mỗi hàng bảng là 1 block riêng ⇒ **0/18 trang nhận ra bảng nào**. Hàng bảng bị gộp vào văn xuôi rồi cắt theo tỉ lệ |
| Footnote và caption **đè lên hình** | cùng cơ chế cắt theo tỉ lệ, không phân biệt vùng |
| Chữ gốc còn nguyên, bản dịch **đè chồng lên** | redaction làm **trôi chữ** (xem dưới) |
| Trang mở chương + hộp KEY POINTS mất sạch chữ | 37 block bị loại vì `_overlaps_image` |

Nguyên lý bản mới: **nhận diện cấu trúc trước, dịch sau, và đơn vị dịch luôn là một khối trọn vẹn.**

- `analyze.py` — bóc **dòng** (kèm cỡ/đậm/nghiêng/serif/màu) → khoanh vùng (bảng, hình, hộp lưu đồ,
  caption, footnote, header–footer chạy trang) → chia cột & thứ tự đọc → gom dòng thành **khối**
  (đoạn văn, tiêu đề, gạch đầu dòng, ô bảng, nhãn hình) → nối khối chảy tràn sang cột/trang kế.
- `tables.py` — nhận bảng bằng 3 tín hiệu độc lập: **nền tô** nằm gọn trong trang có ≥2 dòng chữ,
  **≥3 nét kẻ ngang** cùng khoảng x, và `find_tables(strategy="lines_strict")`. Chia ô theo cụm cột
  rồi cắt hàng tại nét kẻ. Kết quả trên `01. tntc.pdf`: **87 ô bảng** (bản cũ: 0), ô nhiều dòng vẫn
  là **một** đơn vị dịch. Chiến lược `"text"` bị loại vì đo được nó coi nguyên trang là bảng 59×10.
- `render.py` — **rót tuần tự**, không cắt theo tỉ lệ: khối tràn 2 cột thì đổ đầy vùng 1 rồi mới
  sang vùng 2, nên chữ không bao giờ rơi vào ô bảng hay caption của khối khác.
- `fonts.py` — 8 face Việt hoá: **Tinos** (khớp metric Times) cho serif, **Noto Sans** cho sans,
  DejaVuSans dự phòng, tự đổi font khi thiếu glyph (`≥ ≤ → ←` Noto Sans không có, Tinos có).

**Đơn vị dịch không còn cắt giữa câu** (yêu cầu gốc). Đo trên `01. tntc.pdf`:

| | đơn vị cụt đuôi | đơn vị cụt đầu |
|---|---|---|
| Lấy block PDF làm đơn vị (cách cũ) | **72%** | 15% |
| Khối của engine mới (văn xuôi) | **13%** | 10% |

Ba luật làm nên khác biệt đó, mỗi luật đều từ một ca hỏng đo được:
- **Đổi đậm/nghiêng KHÔNG cắt đoạn**, chỉ đổi cỡ hoặc màu mới cắt. Sách y khoa hay mở đầu đoạn bằng
  cụm in đậm; coi đó là hết đoạn thì đoạn đứt ngay **giữa từ** (`'…may be insti-'` / `'tuted. There
  are many…'`). Kiểu chữ của khối lấy theo phần chữ chiếm nhiều nhất.
- **Nối tràn cột/trang xuyên qua khối ngoài mạch đọc**: tiêu đề, caption, tiêu đề bảng, header chạy
  trang, nhãn hình không cắt mạch — chỉ khối văn xuôi mới cắt (đo được: đoạn cuối trang 830 nối sang
  cột phải trang 831, mà đầu trang 831 lại là tiêu đề bảng 32-1). Luật nối vẫn **chặt**: cụt đuôi +
  mở đầu chữ thường + cùng cỡ/màu + mảnh trước phải **chạm đáy cột** (≥75% chiều cao trang). Soi tay
  toàn bộ 14 mối nối: **không mối nào ghép sai**, tất cả đều kết thúc trọn câu.
- **Không bỏ chữ nào.** Luật `_overlaps_image` bị xoá hẳn: chữ nằm đè lên ảnh/nền màu vẫn là chữ,
  vẫn dịch tại chỗ, chỉ ảnh là không bị đụng tới.

**Chữ vừa hộp mà không phải co nhỏ** (theo lựa chọn "co vừa phải + mượn chỗ trống"). Thứ tự thử:
giữ nguyên cỡ → co dần tối đa 15% → nới xuống khoảng trắng trống ngay bên dưới (đã tính sẵn, không
đụng dòng/ảnh/hàng bảng nào) → cuối cùng mới co mạnh. Số khối phải co dưới 0.85 lần giảm
**159 → 34 / 560** nhờ ba sửa lỗi đo được:
- Đổi Noto Serif → **Tinos**: một dòng bảng 9pt rộng 226pt ở bản gốc thành **364pt** khi đặt bằng
  Noto Serif — tức 35% co chữ là do **font rộng hơn**, không phải do tiếng Việt dài hơn. Tinos rộng
  **×0.98** so với Times gốc (đo trên 1117 dòng).
- Hộp chữ phải cao `n×pitch`, không phải cao bằng **hộp mực** (bbox của n dòng hụt gần một khoảng
  dẫn dòng ⇒ dòng cuối không bao giờ đủ chỗ). Nới đều lên/xuống nửa khoảng leading, chặn ở chỗ trống thật.
- **Nhãn hình nở ngang** sang phải thay vì co chữ (nhãn ngắn trong hộp vừa khít không xuống dòng được).

**Chữ trong hộp lưu đồ là một nhãn**: khung kín nhỏ (<45% bề ngang, <15% chiều cao trang) chứa ≤3
dòng thì cả hộp thành **một** khối, dịch trọn cụm và canh lề đúng như bản gốc (đo trên lưu đồ trang
839: hộp ~74×33pt). Canh giữa chỉ khi bản gốc canh giữa — mặc định canh giữa hết thì cả cột mục lục
trang mở chương trôi khỏi chỗ.

⚠️ **Cache bản dịch cũ thành vô dụng một lần**: khoá cache là *nội dung khối*, mà khối nay khác hẳn
mảnh cũ. Job cũ sẽ dịch lại từ đầu (tốn RPD một lần), không phải lỗi.

⚠️ **Số đơn vị dịch tăng** (bảng và nhãn lưu đồ nay tách riêng): `01. tntc.pdf` ra ~390–470 khối.
Vẫn gói trong 2–3 request nhờ trần 200 đoạn/batch.

✅ **Xoá chữ gốc: chọn cách theo từng trang (2026-08-16)**
- PyMuPDF `apply_redactions` là cách sạch nhất (gỡ hẳn chữ khỏi tầng text) nhưng **làm hỏng**
  `01. tntc.pdf`: file này đặt chữ bằng toán tử dời chỗ **tương đối**, nên xoá một dòng làm các dòng
  sau **trôi đi** — đo được footnote trang 831 nhảy từ `y=660` lên `y=497` (đè lên hình), ghi chú
  bảng trang 832 nhảy `330 → 251`. Đây mới là thủ phạm thật của ca "chữ gốc còn nguyên, bản dịch đè
  chồng lên", **không phải** luật bỏ khối đè ảnh như chẩn đoán ban đầu.
- `clean_contents(sanitize=True)` **không cứu được**: so ảnh render trước/sau, chính nó làm trôi chữ
  ở **62/1867 dòng** của tài liệu này. Đừng thử lại đường này.
- Nên: thử bôi đen trên một **bản sao** trước; trang nào mà mọi dòng còn lại vẫn **nguyên vị trí**
  thì bôi đen thật, trang nào có dòng trôi thì chuyển sang **vá nền** (vẽ chữ nhật màu nền đè lên
  đúng hộp dòng chữ, màu lấy bằng **mốt** các điểm ảnh bên trong hộp — nét chữ luôn là thiểu số nên
  đúng cả với chữ trắng trên nền sẫm). Trên `01. tntc.pdf`: 3/18 trang bôi đen được, 15/18 phải vá.
- Đánh đổi của vá nền: chữ gốc vẫn nằm trong tầng text (vô hình vì bị che), nên tìm kiếm/copy trên
  file kết quả sẽ thấy cả bản gốc lẫn bản dịch.

✅ **Nâng model Gemini lên 3.5 Flash Lite (2026-08-15)**
- Đổi `gemini-3.1-flash-lite` → **`gemini-3.5-flash-lite`**, và hạ `GEMINI_RPD_LIMIT` **1500 → 500**
  cho khớp hạn mức free tier thật của model mới. RPM 15 / TPM 250.000 / Max token 65.536 giữ nguyên
  vì đã đúng sẵn (docs xác nhận 3.5 Flash Lite có output limit 65.536, context 1.048.576).
- **Vì sao không chọn 3.6/3.7 Flash dù chúng mới hơn**: free tier của cả 3.5 Flash, 3.6 Flash và
  3.7 Flash đều chỉ **20 RPD**, còn Flash Lite được **500 RPD**. Theo số đo thật (tài liệu 20 trang
  = **4 request**), 20 RPD chỉ đủ ~5 tài liệu/ngày và hết quota giữa chừng ngay khi có batch hỏng
  phải chia đôi. Cả kiến trúc này (gom batch theo TPM, trần 200 đoạn/request, cache theo user,
  `paused_quota`) được xây quanh việc tiết kiệm RPD — 20 RPD là con số phá vỡ nó.
- Mức tăng của 3.6/3.7 Flash nằm ở **coding và agentic** (DeepSWE 49→65%, AutomationBench 17→30%,
  WebDev Arena Elo 1538→1588) — dự án này không dùng tới. Chúng còn có **thinking mode**, tốn output
  token cho phần suy nghĩ và chậm hơn, phản tác dụng với 738 đoạn/tài liệu.
- 3.5 Flash Lite vẫn là **nâng cấp thẳng một thế hệ** so với 3.1 Flash Lite ở đúng thứ dự án cần:
  **long-context GDM-MRCR v2 60,1% → 72,2%** (đúng năng lực mà batch 200 đoạn/request đòi hỏi: giữ
  mạch và không lẫn `id` giữa hàng trăm đoạn) và **GDPval-AA v2 642 → 1140**. Google mô tả nhánh
  Flash-Lite là "best-in-class translation and multilingual understanding".

✅ **Kiểm tra engine bố cục mới (2026-08-16) — `01. tntc.pdf`, bản dịch GIẢ**
Bản dịch giả dài hơn bản gốc ~15% và có dấu tiếng Việt, dùng để soi bố cục mà không tốn quota:
- Phân tích 18 trang: **2,5s**; dựng lại PDF: **~15s**; ra 467 khối (140 đoạn văn, 87 ô bảng,
  136 nhãn hình, 61 tiêu đề, 22 header/footer, 17 gạch đầu dòng, caption + tiêu đề bảng).
- **Soi mắt người từng trang** ở các trang khó nhất (830 mở chương 3 cột + hộp KEY POINTS, 831
  bảng + hình giải phẫu + footnote, 832 bảng 2 cột, 834 hai cột đặc, 839 lưu đồ, 843/845 nhiều
  bảng): bảng đủ hàng đủ ô, hình và nét vẽ nguyên vẹn, nhãn nằm đúng trong hộp lưu đồ, footnote
  đúng chỗ, **không còn chữ gốc sót lại và không còn chữ đè chồng**.
- Đối chiếu chữ trong file kết quả với bản gốc theo toạ độ: không còn dòng nào bị trôi chỗ.

✅ **E2E pipeline với provider giả (2026-08-16)**
- Chạy thẳng `pipeline.translate_pdf` trên `01. tntc.pdf` với SQLite + đĩa cục bộ tạm và một
  provider stub: `status=done`, `error=None`, tiến trình `391/391`, PDF kết quả 2,4 MB,
  **18/18 trang có bản dịch**. Bao trọn job_store → storage → cache → translator → layout → render.
- `python -m compileall backend/app`: pass. Import `app.main`: 11 route.

✅ **Kiểm tra trước đó (2026-07-15) — E2E THẬT với API key thật**
> ⚠️ Toàn bộ số đo dưới đây chạy trên **Gemini 3.1 Flash Lite** và trên **engine PDF cũ** (đã bị
> thay 2026-08-16). Giữ lại vì phần quota/batch/provider không đổi.
- **Dịch trọn `pedsinreview.2021005273.pdf`** (20 trang, 804 đoạn / 738 đoạn duy nhất), cache rỗng
  để ép gọi API thật: **738/738 đoạn, 4 request, 124s**, xuất PDF 6,7 MB thành công. Lỗi
  `Provider không trả JSON hợp lệ` **không còn tái hiện**.
- So chất lượng Gemini vs Qwen trên 14 đoạn mẫu: cả hai đều trả **14/14 đoạn**, JSON hợp lệ, và
  đều có sai sót y khoa thật — xem mục *Chất lượng dịch* bên dưới.
- Sanity test FastAPI bằng `TestClient`: bootstrap admin → login → lưu API key (mã hóa AES-GCM,
  masked đúng) → upload/đọc glossary CSV → tạo job PDF tối giản → tải PDF kết quả → xóa job/file.
- Sanity test tầng DB/storage, regression test chống 502, test polling frontend (3 ca) và
  `npm run build` trong `frontend/`: pass.

⚠️ **Chưa kiểm thử**
- **Engine bố cục mới chưa chạy với API key thật** — mới chỉ chạy với bản dịch giả và provider
  stub. Cần một lần dịch thật để xem chất lượng chữ tiếng Việt thật (dài hơn bao nhiêu, có phải co
  chữ nhiều hơn bản giả không) và để chấm lại chất lượng dịch khi đơn vị dịch nay là **đoạn trọn vẹn**.
- **`gemini-3.5-flash-lite` chưa chạy E2E với API key thật** — đợt đổi model 2026-08-15 mới kiểm
  bằng `compileall`, load registry (đúng model id + quota `15 / 250000 / 500 / 65536`) và
  `npm run build`. Hai điểm **bắt buộc phải đo**, vì đúng là hai chỗ đã từng làm hỏng job:
  (a) model mới có tôn trọng `responseSchema` không (docs ghi structured output "Supported", nhưng
  bài học cũ là phải đo chứ đừng tin prompt/mime type), (b) stream SSE ở batch 200 đoạn có đứt ngang
  không. Thấy batch bị cắt cụt bất thường thì nghi `thinkingConfig` trước — 3.5 Flash Lite có
  thinking mode, khác 3.1.
- Engine mới mới chỉ đo trên **một** tài liệu (`01. tntc.pdf`) cộng với các tài liệu cũ chưa chạy
  lại. Cần thêm PDF y khoa khác kiểu: tạp chí 2 cột, tài liệu scan/OCR, bảng nhiều tầng.
- Chưa kiểm thử có hệ thống toàn bộ luồng bằng browser sau bản sửa retry/cancel polling.
- Chưa chạy regression test có chủ đích với Postgres (Neon)/S3 sau đợt tách worker; bộ test tự động
  hiện dùng SQLite file + đĩa cục bộ.
- Gemma 4 31B chưa được đo trong đợt này (chỉ Gemini và Qwen).

### Thứ tự model & model mặc định

Thứ tự khai báo trong `_PROVIDERS` (`providers/registry.py`) quyết định thứ tự hiển thị, và
frontend (`FileUpload.jsx`, `TextTranslate.jsx`) tự chọn **model dùng được đầu tiên** làm mặc
định. Thứ tự hiện tại:

1. **Gemini 3.5 Flash Lite** (`gemini-3.5-flash-lite`) — mặc định
2. **Qwen3 235B** (ModelScope)
3. **Gemma 4 31B** (`gemma-4-31b-it`)

> ⚠️ Tên model Gemini phải đúng chính xác — nhánh Lite luôn có hậu tố `-lite`, và **không có**
> model tên `gemini-3.1-flash` (gọi tên đó API trả **404**). Trước khi đổi sang bất kỳ model nào,
> xác minh tên thật của key bằng
> `GET https://generativelanguage.googleapis.com/v1beta/models?key=...`.

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
- Khi dịch PDF, backend gom nhiều đoạn chưa có cache vào batch lớn nhất có thể theo **TPM do admin đặt**,
  **Max token/request** của từng model, và **trần 200 đoạn/request**. TPM giữ batch trong ngân sách phút,
  còn Max token/request được truyền xuống API (`maxOutputTokens`/`max_tokens`); trần 200 đoạn giữ stream
  đủ ngắn để không bị đứt ngang (xem mục **Tối ưu RPD** ở trên). Nhờ vậy giảm số request và tiết kiệm RPD.
- Batch nào vẫn hỏng thì **tự chia đôi dịch lại**, và request hỏng vẫn bị tính vào RPM/RPD vì nó đã
  tiêu quota thật của provider.
- Trong lúc dịch batch, backend **stream** phản hồi (SSE) và đếm số đoạn đã dịch xong để đẩy tiến trình
  real-time ra frontend **mà không tách nhỏ request** — RPD giữ nguyên như khi gộp batch tối đa.

## Chất lượng dịch: Gemini vs Qwen (đo 2026-07-15)

So trên 14 đoạn mẫu của `pedsinreview.2021005273.pdf`, lấy bản dịch tham chiếu làm chuẩn. **Cả hai
đều chạy được 14/14 đoạn; cả hai đều có lỗi y khoa thật — không bên nào thắng tuyệt đối.**

> ⚠️ Bảng này đo trên **Gemini 3.1 Flash Lite**, model cũ trước đợt nâng cấp 2026-08-15. Chưa có
> benchmark dịch Anh→Việt chuyên ngành y cho 3.5 Flash Lite, nên **không khẳng định được** các lỗi
> dưới đây đã hết. Muốn biết chắc phải đo lại trên đúng 14 đoạn mẫu này.

| | Sai sót đo được |
|---|---|
| **Gemini 3.1 Flash Lite** (model cũ) | "công thức máu **toàn bộ**" (đúng: *toàn phần*) · `≥18` → **`>18`** (sai ranh giới khoảng tham chiếu) · "Resolves with medication discontinuation" → "**Giải quyết bằng cách ngừng thuốc**" (đọc thành mệnh lệnh; ý gốc là *tự hết* khi ngưng thuốc) · bỏ mất "inherited" khi dịch mảnh cụt |
| **Qwen3 235B** | để nguyên "**reticulocyte**" không dịch (đúng: *hồng cầu lưới*) · pancytopenia → "**giảm toàn bộ huyết sắc tố**" — **sai nặng nhất**: *huyết sắc tố* là hemoglobin, còn pancytopenia là giảm cả **ba dòng tế bào máu**. Gemini dịch đúng ("giảm ba dòng tế bào máu") |

Khác biệt cần lưu ý: **Qwen đổi dấu thập phân sang kiểu Việt** (`14,0`), **Gemini giữ kiểu Anh**
(`14.0`). Cả hai đều biện hộ được, nhưng không thống nhất trong cùng bảng xét nghiệm thì dễ đọc nhầm.

Nhiều lỗi trong bảng trên **bắt nguồn từ đoạn bị cắt giữa câu**, không phải model kém — bảng này đo
trên **engine PDF cũ**, khi đơn vị dịch còn là mảnh bbox (ví dụ "bỏ mất *inherited*" của Gemini
chính là một mảnh cụt). Engine mới đưa tỉ lệ đơn vị cụt đuôi từ 72% xuống 13%, nên **cần đo lại**
mới biết còn bao nhiêu là lỗi thật của model.

## Bài học: vì sao batch dịch hỏng (đo thật 2026-07-15)

Ghi lại vì lỗi này **rất dễ chẩn đoán nhầm**, và nhầm thì sẽ sửa sai chỗ.

**Triệu chứng**: job PDF `failed` với `Provider không trả JSON hợp lệ cho batch dịch`.

**Nguyên nhân thật**: Gemini sinh **JSON sai cấu trúc** — bỏ hẳn khoá `"text"` ở đoạn bắt đầu
bằng ký tự `<`. Ví dụ thật với đoạn `"<2 SD for age)a"`:

```
{"id": 114, "text": "Rối loạn hồng cầu: Thiếu máu (Hgb"},
{"id": 115, "<2 SD theo tuổi)a"},        <-- thiếu khoá "text":
```

Phản hồi có `finishReason=STOP`, đóng ngoặc đầy đủ, chỉ dùng 8.287/65.536 token — **không hề bị
cắt**. `responseMimeType="application/json"` + dặn trong prompt KHÔNG chặn được; chỉ `responseSchema`
mới chặn (ràng buộc bộ giải mã). Đo: batch 200 đoạn hỏng lặp lại được khi thiếu schema, 17/17 lần
sạch khi có.

**Những giả thuyết SAI đã bị số liệu bác bỏ** — đừng đi lại đường này:
- ❌ *"Batch vượt trần 65.536 token đầu ra"*: batch hỏng chỉ dùng 8.287 token. Cả tài liệu 738 đoạn
  ước lượng thừa nhất cũng chỉ ~54.000 token → **chưa bao giờ chạm trần**.
- ❌ *"Hệ số ước lượng token tiếng Việt 1.3 quá thấp"*: đo thật `candidatesTokenCount / token nguồn`
  = **1.07–1.25**. `_OUTPUT_EXPANSION_FACTOR = 1.3` là đúng, đừng nâng.
- ❌ *"Lỗi parse JSON ⇒ phản hồi bị cắt"*: sai. Còn khả năng thứ ba — JSON **đủ ngoặc nhưng sai
  khoá**. `_looks_truncated()` trong `providers/base.py` phân biệt hai ca này.

**Quy tắc**: gặp lỗi parse batch, **dump phản hồi thô + `finishReason` + `usageMetadata` trước**,
đừng suy luận từ triệu chứng.

**Vấn đề riêng, chưa sửa**: stream SSE của Google đôi khi **đứt ngang** (~10-15%, đo trên ~14 lượt),
trả về một phần dữ liệu mà **không báo lỗi** và `finishReason` vẫn `STOP`. Batch càng dài càng dễ
dính (batch 738 đoạn đứt ở 702/738). Đây là lý do giữ cơ chế chia đôi batch, không phải vì token.

## Kiến trúc

- `frontend/` — **React + Vite**: đăng nhập (không đăng ký), giao diện upload PDF, theo dõi tiến trình, tải kết quả, tab dịch văn bản, **bảng Cài đặt** (API key theo account / đổi mật khẩu / dọn cache), **bảng Quản trị** (chỉ admin).
- `backend/` — **Python + FastAPI + PyMuPDF**: auth/session cookie + vai trò admin, nhận PDF, dịch giữ bố cục, đa provider, đọc/ghi cấu hình runtime vào `.env`.

Engine bố cục PDF nằm trong `backend/app/services/layout/`, dùng qua đúng hai hàm:

```python
blocks = analyze_document(doc)             # bảng / hình / chữ; mỗi khối là 1 đơn vị dịch trọn vẹn
render_document(doc, blocks, translations) # xóa chữ gốc + rót bản dịch về đúng cấu trúc
```

`translations` là ánh xạ `block.id -> bản dịch`; `translator.translate_units()` nhận thẳng danh sách
khối, khử trùng lặp theo nội dung và trả về đúng ánh xạ đó — **không còn bước cắt/gộp nào ở giữa**.

Dịch PDF chạy theo **mẫu job bất đồng bộ**: tạo job → poll trạng thái → tải file kết quả.
Bản dịch được **cache theo nội dung khối và user** (SQLAlchemy Core — SQLite cục bộ hoặc Postgres
khi deploy) nên hết quota/tắt máy vẫn **dịch tiếp** được (resume), kể cả khi đổi sang model khác,
nhưng không dùng chung cache giữa các tài khoản. Job vẫn dùng FastAPI `BackgroundTasks`, nhưng các
pha PDF/storage/provider/cache đồng bộ hoặc dài được đưa sang worker thread để không chặn event loop
phục vụ auth, poll tiến trình và các request khác.

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
> - External rewrite của Vercel có timeout tối đa 120 giây. Backend không để các pha đồng bộ dài chặn
>   event loop, còn frontend tự retry lỗi gateway tạm thời và vẫn nhận body job hợp lệ nếu proxy gắn 502.
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
    ├── core/                   # config.py, db.py (engine + schema; QueuePool cho SQLite file/Postgres, StaticPool cho SQLite memory), job_store.py, auth.py, auth_store.py
    ├── models/                 # Pydantic: auth, job, translate, provider, glossary, settings
    ├── routers/                # auth, pdf, text, providers, glossary, settings (lớp HTTP)
    ├── services/               # translator, pipeline, cache, glossary, job_runner, app_settings, user_data, storage (object storage abstraction)
    │   └── layout/             # ENGINE BỐ CỤC PDF
    │       ├── model.py        # Block (đơn vị dịch) / Area (vùng rót bản dịch) / TextLine / Style
    │       ├── analyze.py      # dòng -> vùng -> cột & thứ tự đọc -> khối trọn vẹn -> nối tràn cột/trang
    │       ├── tables.py       # nhận vùng bảng (nền tô + nét kẻ + find_tables) và chia thành ô
    │       ├── render.py       # xóa chữ gốc (bôi đen hoặc vá nền) + rót bản dịch, co chữ/mượn chỗ trống
    │       └── fonts.py        # Tinos (serif) / Noto Sans (sans) / DejaVu (dự phòng), tự tránh thiếu glyph
    ├── assets/fonts/           # 9 file .ttf: Tinos ×4, Noto Sans ×4, DejaVuSans
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

0. **Chạy engine bố cục mới với API key thật** trên `01. tntc.pdf` rồi **mở PDF kết quả soi bằng
   mắt**: bản dịch tiếng Việt thật dài hơn bao nhiêu so với bản giả 1,15× đã đo, có khối nào phải co
   chữ quá tay không, và chất lượng dịch cải thiện ra sao khi đơn vị dịch nay là **đoạn trọn vẹn**.
1. Kiểm thử engine trên nhiều kiểu PDF y khoa khác: tạp chí 2 cột, tài liệu scan/OCR kém, bảng nhiều
   tầng (bảng lồng bảng / ô gộp). Các chỗ engine mới còn yếu, biết trước:
   - Bảng **không có nền tô cũng không có nét kẻ** (chỉ căn cột bằng khoảng trắng) chưa nhận ra được.
   - Ô bảng gộp nhiều cột (`colspan`) bị chia theo cụm x nên có thể tách nhầm.
   - Một khối chỉ mang **một** kiểu chữ: đoạn có cụm in đậm mở đầu sẽ ra toàn chữ thường (đúng cấu
     trúc, đúng câu, nhưng mất nhấn mạnh). Muốn giữ thì phải dựng lại kiểu chữ theo từng span, tức
     phải tự ngắt dòng thay vì dùng `fill_textbox`.
2. **Chạy E2E `gemini-3.5-flash-lite` với API key thật** (cache rỗng, `pedsinreview.2021005273.pdf`)
   để xác nhận `responseSchema` và độ ổn định stream SSE ở batch 200 đoạn — xem mục *Chưa kiểm thử*.
   Tiện thể chấm lại 14 đoạn mẫu để cập nhật bảng *Chất lượng dịch* cho model mới.
3. Hoàn thiện xử lý glossary (mode `translate`/`keep`) trong `services/glossary.py`.
4. (Tùy chọn) nâng job runner từ `BackgroundTasks` lên hàng đợi thật để **kiểm soát concurrency** và
   bền qua restart; các BackgroundTask của request riêng hiện đã có thể chồng lấp. Các pha nặng đã
   chạy ngoài event loop nên không còn chặn poll, nhưng host free ngủ/restart giữa chừng vẫn làm job
   dừng (bấm **Resume** dịch tiếp được nhờ cache Postgres, nhưng job không tự chạy lại).
5. Quota admin chỉnh trong bảng **Quản trị** vẫn ghi vào `.env` (ephemeral trên host free) — khi
   deploy nên đặt quota qua env var lúc khởi tạo (`GEMINI_RPM_LIMIT`…) thay vì sửa runtime. Chuyển
   quota vào DB là follow-up tùy chọn.
6. `quota_tracker` và giới hạn đăng nhập sai (`_login_attempts`) vẫn in-memory (reset khi restart)
   — chấp nhận được, không nằm trong phạm vi việc tách state lần này.
