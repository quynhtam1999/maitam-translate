# Font nhúng trong bản dịch PDF

Base14 của PDF (Helvetica/Times) không có dấu tiếng Việt, nên bản dịch phải nhúng font riêng.

| Font | Dùng cho | Nguồn | Giấy phép |
|---|---|---|---|
| Tinos (Regular/Bold/Italic/BoldItalic) | chữ có chân (serif) — khớp metric với Times New Roman | [google/fonts `ofl/tinos`](https://github.com/google/fonts/tree/main/ofl/tinos) | SIL Open Font License 1.1 |
| Noto Sans (Regular/Bold/Italic/BoldItalic) | chữ không chân (sans) | [notofonts.github.io `NotoSans/hinted`](https://github.com/notofonts/notofonts.github.io/tree/main/fonts/NotoSans/hinted/ttf) | SIL Open Font License 1.1 |
| DejaVu Sans | dự phòng khi thiếu glyph | [dejavu-fonts.github.io](https://dejavu-fonts.github.io/) | Bitstream Vera / xem `LICENSE_DEJAVU.txt` |

Vì sao Tinos chứ không phải Noto Serif: tài liệu y khoa hầu hết đặt bằng Times, mà Noto Serif rộng
hơn Times đáng kể (đo được một dòng 9pt rộng 226pt thành 364pt) nên bản dịch phải co chữ oan ~35%.
Tinos khớp metric Times (đo trên 1117 dòng: ×0.98) nên gần như không phải co.

Toàn văn giấy phép SIL OFL 1.1: https://openfontlicense.org
