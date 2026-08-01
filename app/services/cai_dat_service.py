"""Luật cho màn CÀI ĐẶT hệ thống (màn 78 · SYSTEM-001/002).

Đọc/ghi đi qua `app/core/runtime_config.py` (nơi giữ danh mục + cache); ở đây lo
phần nghiệp vụ: kiểm giá trị hợp lệ trước khi ghi và ghi **audit** — đổi nhịp
worker hay tắt đồng bộ là thao tác ảnh hưởng cả hệ thống, phải biết ai đổi lúc nào.

KHÔNG bày token/mật khẩu/chuỗi kết nối lên đây: những thứ đó ở `.env`, người có
quyền xem màn này không đương nhiên được phép đọc bí mật hệ thống.
"""

from app.core import runtime_config as cfg
from app.core.errors import ApiError
from app.db.repositories import audit_repo


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


def danh_sach() -> list[dict]:
    """Tất cả cài đặt kèm giá trị hiện tại (phẳng) — dùng cho API."""
    return cfg.danh_sach()


def theo_nhom() -> list[dict]:
    """Cài đặt gom nhóm — dùng dựng màn."""
    return cfg.theo_nhom()


def _kiem(muc: cfg.Muc, value):
    """Ép kiểu + kiểm khoảng hợp lệ. Sai thì VALIDATION_ERROR kèm lý do rõ ràng."""
    if muc.kieu == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "on", "bat", "yes")

    if muc.kieu == "str":
        v = str(value).strip()
        if muc.chon and v not in muc.chon:
            raise ApiError("VALIDATION_ERROR",
                           f"{muc.ten}: chỉ nhận {', '.join(muc.chon)}",
                           errors={muc.code: v})
        return v

    try:
        so = float(value)
    except (TypeError, ValueError) as err:
        raise ApiError("VALIDATION_ERROR", f"{muc.ten}: phải là số",
                       errors={muc.code: str(value)}) from err
    if muc.nho_nhat is not None and so < muc.nho_nhat:
        raise ApiError("VALIDATION_ERROR",
                       f"{muc.ten}: nhỏ nhất là {muc.nho_nhat:g} {muc.don_vi}".strip(),
                       errors={muc.code: str(value)})
    if muc.lon_nhat is not None and so > muc.lon_nhat:
        raise ApiError("VALIDATION_ERROR",
                       f"{muc.ten}: lớn nhất là {muc.lon_nhat:g} {muc.don_vi}".strip(),
                       errors={muc.code: str(value)})
    return int(so) if muc.kieu == "int" else so


def dat(code: str, value, actor: dict | None = None) -> dict:
    """Đổi một cài đặt. Trả về dòng đã cập nhật (kèm giá trị mới có hiệu lực)."""
    muc = cfg.THEO_MA.get(code)
    if muc is None:
        raise ApiError("NOT_FOUND", f"Không có cài đặt tên «{code}»")
    cu = cfg.lay(code)
    moi = cfg.dat(code, _kiem(muc, value), user_id=_actor_id(actor))
    if cu != moi:
        audit_repo.ghi(
            user_id=_actor_id(actor), object_type="app_settings", action="setting_update",
            old_value={code: cu}, new_value={code: moi},
        )
    return {"code": code, "ten": muc.ten, "gia_tri": moi, "truoc_do": cu}


def dat_lai_mac_dinh(code: str, actor: dict | None = None) -> dict:
    """Bỏ phần ghi đè -> quay về giá trị trong .env."""
    muc = cfg.THEO_MA.get(code)
    if muc is None:
        raise ApiError("NOT_FOUND", f"Không có cài đặt tên «{code}»")
    cu = cfg.lay(code)
    moi = cfg.dat_lai_mac_dinh(code)
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="app_settings", action="setting_reset",
        old_value={code: cu}, new_value={code: moi},
    )
    return {"code": code, "ten": muc.ten, "gia_tri": moi, "truoc_do": cu}


def dat_nhieu(du_lieu: dict, actor: dict | None = None) -> list[dict]:
    """Lưu cả một form. Kiểm HẾT trước rồi mới ghi — sai một ô thì không ô nào
    được ghi, tránh cảnh nửa bật nửa tắt."""
    can_ghi = []
    for code, value in du_lieu.items():
        muc = cfg.THEO_MA.get(code)
        if muc is None:
            continue
        can_ghi.append((code, _kiem(muc, value)))
    return [dat(code, value, actor) for code, value in can_ghi]
