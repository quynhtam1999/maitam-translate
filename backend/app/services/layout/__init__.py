"""Engine bố cục PDF: phân tích cấu trúc trang -> khối dịch trọn vẹn -> dựng lại bản dịch.

    blocks = analyze_document(doc)            # bảng / hình / chữ, mỗi khối là 1 đơn vị dịch
    render_document(doc, blocks, {id: text})  # xóa chữ gốc + rót bản dịch đúng cấu trúc
"""
from .analyze import analyze_document
from .model import Area, Block, BlockKind, Style, TextLine
from .render import render_document

__all__ = [
    "Area",
    "Block",
    "BlockKind",
    "Style",
    "TextLine",
    "analyze_document",
    "render_document",
]
