# Mai Tam Translate (Web)

Web app dịch **tài liệu PDF y khoa** (sản phụ khoa, nhi khoa) sang **tiếng Việt**,
**giữ nguyên bố cục trang gốc** (ảnh, bảng, chia cột — chỉ thay chữ tại chỗ), và dịch
**văn bản dán tay**. Engine dịch đa nhà cung cấp: **Gemini/Gemma 4 31B** (Google AI Studio) và
**Qwen3 235B** qua **ModelScope API-Inference** (endpoint OpenAI-compatible, server quốc tế `.ai`).

Đây là bản web của phần mềm desktop cùng tên (Python/Tkinter, đóng gói .exe). Kỹ thuật
giữ bố cục dùng **overlay PyMuPDF** (xóa chữ gốc tại chỗ + chèn bản dịch đè lên, tự co
cỡ chữ cho vừa).

## Trạng thái hiện tại (cập nhật 2026-08-15)

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

✅ **Gộp mảnh câu bị PDF cắt ngang (2026-07-15)**
- `collect_segments` bóc chữ **theo vị trí trên trang** để chèn bản dịch lại đúng bbox, nên một câu
  bị cắt ở biên khối/cột/trang thành nhiều mảnh và mỗi mảnh từng là một đơn vị dịch riêng — model
  nhận được thứ như `'ited bone marrow failure. In a child with a history of bone'` (đuôi của
  *inherited*). Không model nào dịch chuẩn được mảnh như vậy: đây là **trần chất lượng chung**,
  không phải lỗi provider.
- `services/segment_merge.py` gộp các mảnh liền mạch trong thứ tự đọc thành **đơn vị dịch**, dịch
  trọn câu, rồi **cắt bản dịch trả về từng bbox theo tỉ lệ độ dài nguồn**, luôn cắt ở ranh giới từ.
  > **Vì sao cắt theo tỉ lệ là đúng dù trật tự từ Việt/Anh khác nhau**: người đọc đọc các bbox
  > *theo thứ tự đọc*, nên chỗ cắt không cần khớp ngữ nghĩa với mảnh gốc — chỉ cần ghép các phần
  > lại đúng thứ tự thì ra nguyên văn bản dịch, và mỗi phần vừa bbox của nó.
- **Đo trên 2 tài liệu y khoa 2 cột thật** (1176 khối, tạp chí + sách): mảnh văn xuôi **cụt đầu giảm
  ~40%** (106→64 và 60→45), gộp được cả qua **biên cột** (đáy cột trái → đỉnh cột phải) và qua
  **biên trang**. Soi tay toàn bộ các chỗ nối qua biên cột/trang: **không ca nào gộp nhầm**
  (`'…may result in a'` + `'higher prevalence of disease…'`). Ngưỡng chỉnh trên tài liệu thứ nhất
  chạy thẳng trên tài liệu thứ hai không phải sửa gì. Phần cụt đầu còn lại phần lớn là **dòng bảng**
  (việc #1, không phải luật gộp câu) → xét riêng văn xuôi thì giảm quá nửa.
- **Bonus RPD**: gộp làm số đơn vị dịch duy nhất giảm ~8% (ít việc gọi API hơn), số request không đổi.
- **Không làm rơi thêm chữ, không làm đoạn lởm chởm hơn** — so cũ/mới cùng một bản dịch giả giãn
  1.15×: số bbox tràn **giảm nhẹ** ở cả hai tài liệu (157→154 và 31→29). Chênh cỡ chữ trong cùng
  đoạn gộp: trung vị **0.0pt**, tối đa 2.8pt — **bản cũ cũng y hệt** (0.0 / 2.9pt), tức độ lởm chởm
  là vốn có chứ không do cắt theo tỉ lệ. Lý do: cắt theo tỉ lệ giữ nguyên hệ số giãn ở mọi mảnh nên
  Fitter co chữ đều như trước.
- ⚠️ **Cache bản dịch cũ thành vô dụng một lần**: khoá cache là *nội dung đơn vị dịch*, nay là câu
  đã gộp thay vì từng mảnh. Job cũ sẽ dịch lại từ đầu (tốn RPD một lần), không phải lỗi.
- Luật gộp cố ý **chặt** (sai một lần gộp là trộn nội dung hai khối không liên quan, hại hơn cái nó
  sửa): phải **cụt đuôi ở mảnh trước + mở đầu bằng chữ thường ở mảnh sau**, cùng kiểu chữ, và hình
  học phải hợp lý — cùng cột thì khe dọc nhỏ, tràn cột/trang thì mảnh trước phải **chạm đáy cột**.
  Không chắc thì không gộp: mảnh giữ nguyên như trước, không tệ đi.

✅ **Thứ tự đọc & header chạy trang (2026-07-15, viết lại cùng đợt)**
- Thứ tự đọc cũ (`_reading_order_key`) xếp **mọi khối ở 22% đầu trang** vào "băng header" — tức
  nuốt luôn đỉnh cả hai cột thân bài rồi trộn chúng vào nhau. Trước đây vô hại (mỗi bbox dịch độc
  lập, chèn lại theo `block_id`) nhưng việc gộp câu thì **phụ thuộc hoàn toàn** vào thứ tự đọc đúng.
  Nay thay bằng thuật toán **băng/cột**: khối chạy ngang cả trang (rộng ≥72%) cắt băng, trong mỗi
  băng đọc hết cột trái rồi cột phải; phân cột theo **tâm khối**, không theo "có cắt qua tâm trang"
  (đo được: cột trái chạy tới x=302 còn cột phải bắt đầu x=294 — **hai cột đều lấn qua tâm 297**).
- Header/footer chạy trang nhận diện bằng **chữ lặp lại** (sau khi bỏ số trang), **không** bằng vị
  trí lặp lại: đo được băng `y0≈58` trúng 10/15 trang nhưng **toàn là thân bài** — đỉnh khung chữ
  đương nhiên lặp y0 ở mọi trang. Kết quả: đúng **15/372 khối** là furniture, mỗi trang 1, không
  bắt nhầm khối nào. Chúng bị **bỏ qua trong mạch đọc** (nhờ vậy cuối trang trước nối được đầu
  trang sau) nhưng **vẫn được dịch** bình thường.
- Footer trang mở chương (`111 DOI: 10.1201/…`) nằm **trong cột trái, dưới cùng**, nên từng chen
  vào giữa đáy cột trái và đỉnh cột phải và cắt đứt mạch nối; nay bắt bằng luật riêng "không thân
  bài nào chạy xuống 5% cuối trang" (đo được: đáy thân bài y1=743, footer y1=773, trang cao 792).

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

✅ **Kiểm tra gần nhất (2026-07-15) — E2E THẬT với API key thật**
> ⚠️ Toàn bộ số đo dưới đây chạy trên **Gemini 3.1 Flash Lite**, tức model **trước** đợt nâng cấp
> 2026-08-15. Chưa đo lại trên 3.5 Flash Lite.
- **Dịch trọn `pedsinreview.2021005273.pdf`** (20 trang, 804 đoạn / 738 đoạn duy nhất) bằng
  **Gemini 3.1 Flash Lite**, cache rỗng để ép gọi API thật: **738/738 đoạn, 4 request, 124s**,
  xuất PDF 6,7 MB thành công. Lỗi `Provider không trả JSON hợp lệ` **không còn tái hiện**.
- **Chạy lại sau khi có cơ chế gộp câu** bằng Gemini thật: job 20 trang hoàn tất **679/679 đơn vị**,
  `status="done"`, `error=null`; đây là lần E2E API thật đầu tiên xác nhận luồng gộp → dịch → chia
  bản dịch về bbox → dựng/upload PDF chạy hết pipeline. Lỗi 502 nhìn thấy ở frontend thuộc lớp
  poll/proxy, không làm hỏng job hay file kết quả; code đã được gia cố nhưng vẫn cần retest production.
- So chất lượng Gemini vs Qwen trên 14 đoạn mẫu (văn xuôi dài, bảng số, tiêu đề, mẩu cụt):
  cả hai đều trả **14/14 đoạn**, JSON hợp lệ. Cả hai đều có sai sót y khoa thật, không bên nào
  thắng tuyệt đối — xem mục *Chất lượng dịch* bên dưới.
- `python -m compileall backend/app`: pass. Import `app.main` thành công (11 route).
- Sanity test FastAPI bằng `TestClient` (SQLite + đĩa cục bộ, storage tạm cô lập): bootstrap admin
  → login → lưu API key (mã hóa AES-GCM, masked đúng) → upload/đọc glossary CSV → tạo job PDF tối giản
  → tải PDF kết quả → xóa job/file qua `/api/settings/jobs/clear`.
- Sanity test trực tiếp tầng DB/storage: init SQLite qua SQLAlchemy, đọc/ghi API key, cache segment,
  storage local và `job_store` đều pass.
- Regression test chống 502: pipeline mở lại và dựng PDF hợp lệ; SQLite file dùng `QueuePool`;
  event loop vẫn phản hồi trong lúc local-copy, dịch/cache và render giả lập đang block ở worker.
- Test polling frontend: pass cả 3 ca **502 + body done**, 502 trống rồi retry thành công, và hủy
  poll không còn callback muộn. `npm run build` trong `frontend/`: pass.

⚠️ **Chưa kiểm thử**
- **`gemini-3.5-flash-lite` chưa chạy E2E với API key thật** — đợt đổi model 2026-08-15 mới chỉ
  kiểm bằng `compileall`, load registry (ra đúng model id + quota `15 / 250000 / 500 / 65536`) và
  `npm run build`. Hai điểm **bắt buộc phải đo** trước khi tin tưởng, vì đây đúng là hai chỗ đã
  từng làm hỏng job: (a) model mới có tôn trọng `responseSchema` không (docs ghi structured output
  "Supported", nhưng bài học cũ là phải đo chứ đừng tin prompt/mime type), (b) stream SSE ở batch
  200 đoạn có đứt ngang không. Nếu thấy batch bị cắt cụt nhiều bất thường, nghi `thinkingConfig`
  trước — 3.5 Flash Lite có thinking mode, khác 3.1.
- Cơ chế gộp câu đã chạy hết pipeline với API thật, nhưng **chưa chấm lại chất lượng bản dịch** để đo
  mức cải thiện so với bảng Gemini/Qwen cũ, và **chưa mở PDF kết quả để mắt người soi lại bố cục**.
- Chưa kiểm thử có hệ thống toàn bộ luồng bằng browser sau bản sửa retry/cancel polling; mới có ca thật
  tái hiện 502 trước khi sửa và regression test trực tiếp logic frontend.
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
**trước** khi có cơ chế gộp mảnh câu (xem mục *Gộp mảnh câu*), nên **cần đo lại** thì mới biết còn
lại bao nhiêu là lỗi thật của model. Ví dụ "bỏ mất *inherited*" của Gemini chính là ca mảnh cụt.

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

Dịch PDF chạy theo **mẫu job bất đồng bộ**: tạo job → poll trạng thái → tải file kết quả.
Bản dịch được **cache theo nội dung đoạn và user** (SQLAlchemy Core — SQLite cục bộ hoặc Postgres
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
    ├── services/               # pdf_overlay, segment_merge (gộp mảnh câu + cắt bản dịch về từng bbox), translator, pipeline, cache, glossary, job_runner, app_settings, user_data, storage (object storage abstraction)
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

0. **Đoạn bị cắt giữa câu — đã sửa cho VĂN XUÔI (2026-07-15).** Xem mục *Gộp mảnh câu* ở trên.
   Phần cụt đầu còn lại **phần lớn là dòng bảng**, không phải văn xuôi: `_looks_like_table_block`
   cắt bảng **theo dòng**, nên một ô bảng nhiều dòng vỡ thành nhiều mảnh
   (`'• Includes a pre-IVM culture and the IVM culture'` / `'prior to IVM culture [88]'`). Gộp đúng
   chúng cần biết ranh giới **ô**, không phải dòng → thuộc việc #1, không phải luật gộp câu. Số ít
   ca văn xuôi còn lại chủ yếu do mạch đọc đứt vì khối chen giữa **bị bỏ do đè lên ảnh**
   (`_overlaps_image`), nên khối liền trước kết thúc trọn câu và không có gì để nối.
1. Kiểm thử thêm trên nhiều PDF y khoa 2 cột phức tạp, đặc biệt tài liệu scan/OCR kém hoặc bảng
   nhiều tầng. Ưu tiên **xử lý bảng**, nay là nguồn lỗi cụt đoạn lớn nhất còn lại:
   `_looks_like_table_block` (a) bỏ sót bảng có khối < 4 dòng — hàng bảng lọt ra thành khối văn xuôi
   thường và bị gộp như văn xuôi, (b) cắt bảng theo **dòng** thay vì theo **ô**. Cân nhắc dùng
   `page.find_tables()` của PyMuPDF thay cho heuristic hiện tại.
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
