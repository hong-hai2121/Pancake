"""API Cài đặt hệ thống — SYSTEM-001/002 (màn 78).

Công tắc bật/tắt + nhịp chạy của worker, đổi được lúc đang chạy (worker đọc lại
mỗi vòng). Quyền `user.manage`: đây là thao tác quản trị hệ thống, ảnh hưởng cả
công ty — không mở cho trưởng nhóm.

KHÔNG có endpoint nào đọc/ghi token, mật khẩu hay chuỗi kết nối: những thứ đó
nằm ở `.env`, cố ý không phơi qua API.
"""

from fastapi import APIRouter, Depends

from app.core.deps import require_permission
from app.core.response import ok
from app.schemas.cai_dat import CaiDatIn, CaiDatNhieuIn
from app.services import cai_dat_service

router = APIRouter(prefix="/api/v1", tags=["settings"])

_quan_tri = Depends(require_permission("user.manage"))


@router.get("/settings")
async def list_settings(nhom: bool = True, _user: dict = _quan_tri):
    """SYSTEM-001 — danh sách cài đặt + giá trị đang có hiệu lực.

    `nhom=false` trả danh sách phẳng (tiện cho script), mặc định trả theo nhóm
    đúng thứ tự hiển thị trên màn.
    """
    if nhom:
        return ok({"nhom": cai_dat_service.theo_nhom()})
    return ok({"items": cai_dat_service.danh_sach()})


@router.put("/settings/{code}")
async def set_setting(code: str, body: CaiDatIn, user: dict = _quan_tri):
    """SYSTEM-002 — đổi một cài đặt (có hiệu lực ở lượt chạy kế của worker)."""
    return ok(cai_dat_service.dat(code, body.gia_tri, actor=user), "Đã lưu cài đặt")


@router.post("/settings/{code}/mac-dinh")
async def reset_setting(code: str, user: dict = _quan_tri):
    """Bỏ ghi đè, quay về giá trị trong .env."""
    return ok(cai_dat_service.dat_lai_mac_dinh(code, actor=user),
              "Đã trả về mặc định")


@router.put("/settings")
async def set_many(body: CaiDatNhieuIn, user: dict = _quan_tri):
    """Lưu nhiều cài đặt một lượt — sai một ô thì KHÔNG ô nào được ghi."""
    return ok({"items": cai_dat_service.dat_nhieu(body.gia_tri, actor=user)},
              "Đã lưu cài đặt")
