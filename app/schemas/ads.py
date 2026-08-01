"""Schema Pydantic cho API quảng cáo (ADS-005 · ATTRIBUTION-001)."""

from datetime import datetime

from pydantic import BaseModel, Field


class AttributionIn(BaseModel):
    """Gắn nguồn tay: cần ít nhất external_ad_id hoặc post_id (service kiểm)."""

    external_ad_id: str | None = Field(default=None, max_length=100)
    post_id: str | None = Field(default=None, max_length=100)
    touch_type: str = Field(default="last", pattern="^(first|last)$")
    attributed_at: datetime | None = None
    source: str | None = Field(default=None, max_length=50)
    lead_id: int | None = None
    utm: dict | None = None


class SyncAdsIn(BaseModel):
    """Kéo tay cây quảng cáo + chi phí N ngày gần nhất (trần 90 — API POS tính
    insights theo khoảng, hỏi quá dài vừa chậm vừa dễ 429)."""

    so_ngay: int = Field(default=7, ge=1, le=90)
