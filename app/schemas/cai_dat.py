"""Schema Pydantic cho API cài đặt hệ thống (SYSTEM-001/002)."""

from pydantic import BaseModel, Field


class CaiDatIn(BaseModel):
    """Giá trị để nguyên kiểu tự do (bool/số/chuỗi) — kiểu đúng của từng cài đặt
    do danh mục trong `app/core/runtime_config.py` quyết, service ép + kiểm."""

    gia_tri: bool | float | str


class CaiDatNhieuIn(BaseModel):
    gia_tri: dict[str, bool | float | str] = Field(min_length=1)
