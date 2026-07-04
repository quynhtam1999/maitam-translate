---
name: update-readme
description: Cập nhật README.md của dự án Mai Tam Translate để phản ánh đúng tình trạng code hiện tại (xoá/sửa mọi nội dung đã cũ, không còn đúng), rồi tự động commit và push thẳng lên origin/main — không cần hỏi lại xác nhận. Dùng skill này bất cứ khi nào anh nói "cập nhật README", "đồng bộ README với code", "đẩy code lên git", "push lên main", "ghi lại tiến độ mới nhất", hoặc sau khi vừa hoàn thành một đợt thay đổi code đáng kể và muốn lưu lại + công bố lên GitHub.
---

# Cập nhật README + đẩy code lên Git

Skill này gói gọn một việc anh làm thường xuyên: sau khi code thay đổi, README.md
bị lạc hậu so với thực tế — mô tả sai luồng, liệt kê thiếu file mới, giữ lại TODO
đã xong. Việc của skill là đọc lại code + lịch sử git, viết lại README cho khớp
sự thật, rồi tự commit/push mà không cần hỏi lại (anh đã uỷ quyền việc này).

## Quy trình

### 1. Khảo sát trạng thái thật của repo

Đừng đoán — luôn đọc trực tiếp:

- `git status --short` — file nào đã đổi/thêm/xoá, còn gì chưa commit.
- `git diff` và `git diff --stat` (cả staged lẫn unstaged) — đổi cái gì, không chỉ đổi ở đâu.
- `git log -15 --oneline` — vài commit gần nhất, để hiểu bối cảnh và bắt đúng văn
  phong commit message của repo (ngắn gọn, imperative, tập trung vào "vì sao" hơn "cái gì").
- Đọc `README.md` hiện tại từ đầu đến cuối.
- Nếu thay đổi code không tự giải thích rõ (tên file không đủ nói lên bản chất),
  đọc nhanh nội dung file đã đổi để hiểu đúng — README sai sự thật còn tệ hơn
  README thiếu cập nhật.

### 2. Xác định phần cần sửa trong README

So khớp từng phần của README với code thật, sửa mọi chỗ lệch:

- **"Trạng thái hiện tại"** — cập nhật ngày, thêm tính năng/thay đổi mới, **xoá**
  câu mô tả hành vi không còn đúng (ví dụ: còn nhắc "có nút đăng ký" trong khi đã
  bỏ tính năng đó thì phải xoá/sửa ngay, không được giữ lại cho "đủ lịch sử").
- **"Kiến trúc" / "Cấu trúc thư mục"** — thêm file/router/service/component mới,
  bỏ những gì đã xoá khỏi code.
- **"API chính"** — thêm endpoint mới, xoá endpoint không còn tồn tại.
- **"Việc cần làm tiếp (TODO)"** — xoá mục đã hoàn thành, thêm mục mới phát sinh
  từ đợt thay đổi này (nếu có).
- Bất kỳ đoạn văn nào mô tả một luồng/quyết định đã bị thay thế bởi đợt thay đổi
  mới nhất — sửa thẳng, đừng thêm ghi chú kiểu "(cập nhật: giờ không còn vậy nữa)"
  chồng lên đoạn cũ; viết lại cho gọn như thể đang mô tả trạng thái hiện tại từ đầu.

**Nguyên tắc:** README phải phản ánh đúng những gì code *thực sự* đang làm, không
phải những gì dự định làm hay từng làm. Không thêm mục tính năng chưa có trong code.

### 3. Viết lại README.md

- Toàn bộ nội dung bằng **tiếng Việt**, giữ đúng văn phong đã có trong file (cách
  dùng **in đậm**, ký hiệu ✅ 🔑 ⚠️, block `>` ghi chú, bảng markdown cho API...).
- Sửa tối thiểu cần thiết để README đúng và gọn — không viết lại toàn bộ file nếu
  chỉ vài đoạn bị lạc hậu.
- Không bịa thêm nội dung không có căn cứ từ code/git history.

### 4. Xem lại phạm vi thay đổi trước khi add

- Chạy lại `git status --short` sau khi sửa README.
- Chỉ add rõ từng file liên quan đến đợt việc này (README.md + các file code đã
  thay đổi mà chưa được commit trước đó). **Không** dùng `git add -A` / `git add .`
  một cách mù quáng — tránh cuốn theo file rác, file tạm, hoặc file không liên quan.
- **Không bao giờ** add/commit `backend/.env` hay bất kỳ file chứa secret nào (đã
  có `.gitignore` chặn, nhưng vẫn kiểm tra lại `git status` không thấy nó xuất hiện
  trước khi push — nếu có nghĩa là có gì đó bất thường, dừng lại và báo anh).

### 5. Commit

Viết commit message theo đúng phong cách đã thấy ở `git log` của repo này: dòng đầu
ngắn gọn, thì mệnh lệnh (ví dụ "Add...", "Update...", "Fix..."), tập trung vào lý do
thay đổi chứ không liệt kê từng dòng diff. Thêm dòng cuối:

```
Co-Authored-By: Codex Sonnet 5 <noreply@anthropic.com>
```

### 6. Push — đã được uỷ quyền, không hỏi lại

Chủ repo (anh) đã xác nhận rõ ràng khi tạo skill này: **skill được phép chạy
`git push origin main` trực tiếp, không cần hỏi xác nhận lại mỗi lần chạy.** Đây là
uỷ quyền lâu dài cho riêng luồng "cập nhật README + push" của skill này trong dự
án Mai Tam Translate. Không hỏi kiểu "anh có muốn push không?" — cứ push sau khi
commit xong, rồi báo lại kết quả (commit hash, tóm tắt README đã sửa gì).

**Ngoại lệ duy nhất — dừng lại và hỏi anh trước khi push nếu:**
- `git status` cho thấy có file lạ/nhiều thay đổi không liên quan gì đến bối cảnh
  gần đây (có thể là việc dở dang của anh chưa muốn công bố).
- Có dấu hiệu file chứa secret/dữ liệu nhạy cảm lọt vào vùng staged.
- Repo đang ở trạng thái bất thường (conflict chưa giải quyết, đang giữa rebase...).

Uỷ quyền này chỉ áp dụng cho luồng bình thường; gặp rủi ro rõ ràng thì vẫn dừng hỏi.

## Khi không có gì để làm

Nếu README đã khớp hoàn toàn với code hiện tại và không có thay đổi nào chưa
commit, báo lại cho anh là không có gì cần cập nhật — không tạo commit rỗng, không
push vô ích.
