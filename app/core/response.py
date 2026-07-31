"""Khuôn phản hồi + phân trang dùng chung cho mọi API (A3).

Khuôn theo đúng "Danh sách API CRM" mục I:
    thành công: {"success": true,  "data": {...}, "message": "Thành công"}
    lỗi       : {"success": false, "error_code": "...", "message": "...", "errors": {}}
    phân trang: ?page=1&per_page=20 · sắp xếp: ?sort_by=...&sort_order=desc
"""

from dataclasses import dataclass

from fastapi import Query
from fastapi.responses import JSONResponse

from app.core.errors import ERROR_STATUS


def ok(data=None, message: str = "Thành công") -> dict:
    """Bao thành công. `data` dict/list đều được (list bọc vào items khi phân trang)."""
    return {"success": True, "data": data if data is not None else {}, "message": message}


def err_response(code: str, message: str, errors: dict | None = None) -> JSONResponse:
    """Bao lỗi kèm mã HTTP đúng bảng ERROR_STATUS."""
    return JSONResponse(
        status_code=ERROR_STATUS.get(code, 400),
        content={
            "success": False, "error_code": code,
            "message": message, "errors": errors or {},
        },
    )


# ------------------------------------------------------------------ phân trang
@dataclass
class PhanTrang:
    """Tham số phân trang đã chuẩn hoá; dùng làm dependency:
    `pt: PhanTrang = Depends(phan_trang)` -> pt.limit / pt.offset."""

    page: int
    per_page: int

    @property
    def limit(self) -> int:
        return self.per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


def phan_trang(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> PhanTrang:
    """Dependency đọc ?page=&per_page= (trần 100 — chống kéo cả bảng)."""
    return PhanTrang(page=page, per_page=per_page)


def bao_trang(items: list, total: int, pt: PhanTrang) -> dict:
    """Gói danh sách + thông tin trang vào `data` chuẩn."""
    return {
        "items": items,
        "pagination": {
            "page": pt.page,
            "per_page": pt.per_page,
            "total": total,
            "total_pages": max((total + pt.per_page - 1) // pt.per_page, 1),
        },
    }
