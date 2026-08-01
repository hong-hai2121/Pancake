"""Schema Pydantic cho API thông báo (NOTIFY-004)."""

from pydantic import BaseModel, Field


class NotificationSettingsIn(BaseModel):
    """{"settings": {"viec_qua_han": false, "lead_moi": true}} — gửi loại nào
    thì đổi loại đó, loại không gửi giữ nguyên."""

    settings: dict[str, bool] = Field(min_length=1)
