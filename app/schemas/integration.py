"""Schema Pydantic cho API Tích hợp (BRD mục 4 — INTEGRATION-001…010)."""

from pydantic import BaseModel, Field

_PROVIDER = "^(pancake_pages|pancake_pos)$"


class PageSyncIn(BaseModel):
    """Bật/tắt đồng bộ CRM cho 1 page (poller vẫn chạy phục vụ bot)."""

    sync_enabled: bool


class PageAccountIn(BaseModel):
    """Gán page về một kết nối (ánh xạ Page — màn Ánh xạ)."""

    account_id: int | None = None


class StaffMapIn(BaseModel):
    """Ánh xạ nhân viên Pancake -> tài khoản CRM; user_id rỗng = gỡ ánh xạ."""

    provider: str = Field(pattern=_PROVIDER)
    external_staff_id: str = Field(min_length=1, max_length=100)
    user_id: int | None = None


class RetryIn(BaseModel):
    """Chạy hàng đợi lỗi ngay (không chờ worker)."""

    limit: int = Field(default=50, ge=1, le=500)
