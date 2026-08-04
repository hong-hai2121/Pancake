"""Dò TOÀN BỘ endpoint /api/v1 của chính app này để dựng màn "Thử API dự án".

Nguồn sự thật là bản thân FastAPI app (`request.app.routes`) chứ không phải một
danh sách chép tay — thêm/xoá route là màn hình tự cập nhật, không bao giờ lệch.

Mỗi endpoint moi ra: method · đường dẫn · mô tả (dòng đầu docstring) · quyền cần
có · tham số đường dẫn · tham số truy vấn (kể cả page/per_page lấy từ dependency
`phan_trang`) · mẫu JSON body dựng từ schema Pydantic.
"""

from __future__ import annotations

import datetime as _dt
import json
import types
import typing
from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

# Tên tiếng Việt cho từng tag của router (khớp app/api/v1/*.py).
NHOM: dict[str, str] = {
    "auth": "Đăng nhập & phiên",
    "users": "Nhân viên",
    "roles-teams": "Vai trò · quyền · nhóm",
    "audit": "Nhật ký hoạt động",
    "settings": "Cài đặt hệ thống",
    "leads": "Khách tiềm năng & pipeline",
    "customers": "Khách hàng",
    "tasks": "Công việc",
    "consult": "Tư vấn · sàng lọc · ca chuyên môn",
    "products": "Sản phẩm & bảng giá",
    "treatments": "Liệu trình",
    "orders": "Đơn hàng",
    "handovers": "Bàn giao Sale → CSKH",
    "care": "Chăm sóc sau bán",
    "repurchase": "Cơ hội mua lại",
    "conversations": "Hội thoại & tin nhắn",
    "notifications": "Thông báo",
    "integrations": "Tích hợp (Pancake/POS)",
    "ads": "Nguồn quảng cáo",
    "reports": "Báo cáo & dashboard",
}

# Thứ tự hiện trên màn: theo luồng nghiệp vụ, không theo bảng chữ cái.
THU_TU = list(NHOM)

_MO_TA_MAC_DINH = {
    "page": "trang thứ mấy", "per_page": "số dòng mỗi trang",
    "sort_by": "sắp theo cột", "sort_order": "asc | desc",
}


def _dong_dau(text: str | None) -> str:
    """Dòng đầu docstring — đủ để biết endpoint làm gì, không tràn màn hình."""
    for dong in (text or "").strip().splitlines():
        if dong.strip():
            return dong.strip()
    return ""


def _kieu(anno: Any) -> str:
    """Tên kiểu ngắn gọn để hiện cạnh ô nhập (int · str · bool…)."""
    anno = _bo_optional(anno)
    ten = getattr(anno, "__name__", None) or str(anno)
    return {"int": "số", "float": "số", "bool": "true/false",
            "str": "chữ", "date": "yyyy-mm-dd",
            "datetime": "yyyy-mm-ddThh:mm"}.get(ten, ten)


def _bo_optional(anno: Any) -> Any:
    """`X | None` / `Optional[X]` -> X (chỉ để đoán kiểu, không cần chính xác)."""
    if typing.get_origin(anno) in (typing.Union, types.UnionType):
        con = [a for a in typing.get_args(anno) if a is not type(None)]
        if con:
            return con[0]
    return anno


def _quyen(dependant) -> list[str]:
    """Mã quyền nằm trong closure của `require_permission`/`require_any_permission`."""
    ma: list[str] = []
    for dep in dependant.dependencies:
        call = getattr(dep, "call", None)
        if getattr(call, "__name__", "") != "_check":
            ma.extend(_quyen(dep))
            continue
        for cell in call.__closure__ or ():
            noi_dung = cell.cell_contents
            if isinstance(noi_dung, str):
                ma.append(noi_dung)
            elif isinstance(noi_dung, tuple):
                ma.extend(x for x in noi_dung if isinstance(x, str))
    return ma


def _query(dependant, da_co: set[str] | None = None) -> list[dict]:
    """Tham số truy vấn của route + của mọi dependency con (vd `phan_trang`)."""
    da_co = da_co if da_co is not None else set()
    ra: list[dict] = []
    for q in dependant.query_params:
        if q.name in da_co:
            continue
        da_co.add(q.name)
        mac_dinh = q.field_info.default
        if mac_dinh is PydanticUndefined or mac_dinh is None:
            mac_dinh = ""
        ra.append({
            "ten": q.name,
            "kieu": _kieu(q.field_info.annotation),
            "bat_buoc": bool(q.required),
            "mac_dinh": str(mac_dinh),
            "goi_y": _MO_TA_MAC_DINH.get(q.name, ""),
        })
    for dep in dependant.dependencies:
        ra.extend(_query(dep, da_co))
    return ra


def _vi_du(anno: Any, mac_dinh: Any = PydanticUndefined, sau: int = 0) -> Any:
    """Giá trị mẫu cho 1 trường body: ưu tiên default, không có thì đoán theo kiểu."""
    if mac_dinh is not PydanticUndefined and mac_dinh is not None:
        if isinstance(mac_dinh, (str, int, float, bool, list, dict)):
            return mac_dinh
    anno = _bo_optional(anno)
    goc = typing.get_origin(anno)
    if goc in (list, set, tuple):
        con = typing.get_args(anno)
        if con and sau < 2:
            return [_vi_du(con[0], sau=sau + 1)]
        return []
    if goc is dict:
        return {}
    if isinstance(anno, type) and issubclass(anno, BaseModel) and sau < 2:
        return _mau_dict(anno, sau + 1)
    if isinstance(anno, type):
        if issubclass(anno, bool):
            return False
        if issubclass(anno, int):
            return 0
        if issubclass(anno, float):
            return 0
        if issubclass(anno, _dt.datetime):
            return "2026-08-03T09:00:00"
        if issubclass(anno, _dt.date):
            return "2026-08-03"
    return ""


def _mau_dict(model: type[BaseModel], sau: int = 0) -> dict:
    """Khung JSON của một schema Pydantic (mọi trường, kể cả trường tuỳ chọn)."""
    return {
        ten: _vi_du(f.annotation, f.default, sau)
        for ten, f in model.model_fields.items()
    }


def _mau_body(route: APIRoute) -> str:
    """JSON mẫu để điền sẵn vào ô body; rỗng nếu endpoint không nhận body."""
    field = route.body_field
    if field is None:
        return ""
    anno = _bo_optional(field.field_info.annotation)
    try:
        if isinstance(anno, type) and issubclass(anno, BaseModel):
            mau: Any = _mau_dict(anno)
        else:
            mau = _vi_du(anno)
    except Exception:  # noqa: BLE001 — schema lạ thì thà để ô trống còn hơn vỡ trang
        return "{}"
    return json.dumps(mau, ensure_ascii=False, indent=2)


def liet_ke(app) -> list[dict]:
    """Danh sách endpoint /api/ đã chuẩn hoá, sắp theo nhóm nghiệp vụ rồi đường dẫn."""
    ra: list[dict] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        tag = str(route.tags[0]) if route.tags else "khac"
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            ra.append({
                "method": method,
                "path": route.path,
                "ten": route.name,
                "tag": tag,
                "nhom": NHOM.get(tag, tag),
                "mo_ta": _dong_dau(route.description),
                "quyen": _quyen(route.dependant),
                "path_params": [
                    {"ten": p.name, "kieu": _kieu(p.field_info.annotation)}
                    for p in route.dependant.path_params
                ],
                "query": _query(route.dependant),
                "body": _mau_body(route) if method != "GET" else "",
                "chi_doc": method == "GET",
            })
    ra.sort(key=lambda e: (
        THU_TU.index(e["tag"]) if e["tag"] in THU_TU else len(THU_TU),
        e["path"], e["method"],
    ))
    return ra


def gom_nhom(items: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """Gom theo tag, giữ nguyên thứ tự đã sắp: [(tag, tên tiếng Việt, endpoints)]."""
    nhom: list[tuple[str, str, list[dict]]] = []
    for e in items:
        if not nhom or nhom[-1][0] != e["tag"]:
            nhom.append((e["tag"], e["nhom"], []))
        nhom[-1][2].append(e)
    return nhom
