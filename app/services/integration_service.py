"""Luật khu Tích hợp Pancake & nguồn quảng cáo — BRD mục 4.

Bốn luật trọng yếu của mục 4 nằm ở đây (hoặc được ép ở nơi đã ghi rõ):

  1. "Không tạo khách mới khi đã tồn tại cùng định danh chuẩn"
     -> chống trùng 4 bậc của B1 (`customer_service.upsert_from_source`); đồng bộ
        chỉ được đi qua cửa đó, KHÔNG insert khách trực tiếp.
  2. "Không gọi API Pancake trực tiếp mỗi lần mở màn hình"
     -> mọi màn CRM đọc từ `crm.*`; API tích hợp cũng chỉ đọc DB. Duy nhất hai
        chỗ được gọi ra ngoài: worker nền và nút "Kiểm tra kết nối" (người bấm).
  3. "Token lỗi/hết hạn phải cảnh báo"
     -> `kiem_tra_ket_noi()` cập nhật token_status; màn Tích hợp báo đỏ,
        `tinh_trang()` trả cờ `canh_bao` cho nơi khác dùng lại.
  4. "Dữ liệu nguồn không được sửa ngược nếu chưa có cơ chế hai chiều rõ ràng"
     -> service này KHÔNG có hàm nào ghi ngược sang Pancake. Cố tình.

Ngoài ra: mở/đóng nhật ký đồng bộ (sync_logs), hàng đợi lỗi + thử lại
(sync_errors), ánh xạ page/nhân viên. KHÔNG import FastAPI (quy ước services/).
"""

import sys
from datetime import datetime, timezone

from app.core import runtime_config
from app.core.config import settings
from app.core.errors import ApiError
from app.db.repositories import attribution_repo, audit_repo, integration_repo, order_repo

PROVIDER_TEN = {
    "pancake_pages": "Pancake (pages.fm) — hội thoại",
    "pancake_pos": "Pancake POS — đơn hàng",
}


def _bay_gio() -> datetime:
    return datetime.now(timezone.utc)


def _actor_id(actor: dict | None) -> int | None:
    return int(actor["sub"]) if actor else None


def _audit(actor: dict | None, **kw) -> None:
    audit_repo.ghi(user_id=_actor_id(actor), object_type="integration_accounts", **kw)


def _mask(token: str) -> str:
    """Che token: chỉ giữ 4 ký tự cuối. Không bao giờ lưu/hiện bản đầy đủ."""
    token = (token or "").strip()
    if not token:
        return ""
    return f"…{token[-4:]}" if len(token) > 4 else "…"


# ------------------------------------------------------------------ kết nối
def dam_bao_ket_noi() -> list[dict]:
    """Tạo sẵn 2 dòng kết nối theo .env (chạy lại được).

    Cấu hình thật vẫn nằm ở .env — bảng chỉ là chỗ theo dõi tình trạng, nên hàm
    này gọi bao nhiêu lần cũng không sinh trùng.
    """
    ra = []
    if settings.pancake_access_token:
        ra.append(integration_repo.upsert_account(
            provider="pancake_pages", name=PROVIDER_TEN["pancake_pages"],
            config={"base_url": settings.pancake_base_url},
        ))
    if settings.pancake_pos_api_key:
        ra.append(integration_repo.upsert_account(
            provider="pancake_pos", name=PROVIDER_TEN["pancake_pos"],
            external_id=str(settings.pancake_pos_shop_id or ""),
            config={"base_url": settings.pancake_pos_base_url},
        ))
    return ra


def danh_sach_ket_noi() -> list[dict]:
    """Tab Kết nối: mọi kết nối + cờ thiếu token (đọc .env, không lộ token)."""
    dam_bao_ket_noi()
    rows = integration_repo.list_accounts()
    for r in rows:
        r["co_token"] = bool(
            settings.pancake_access_token if r["provider"] == "pancake_pages"
            else settings.pancake_pos_api_key
        )
        r["canh_bao"] = (not r["co_token"]) or r["token_status"] in ("invalid", "missing")
    return rows


async def kiem_tra_ket_noi(account_id: int, actor: dict | None = None) -> dict:
    """Gọi THẬT sang Pancake một lần để biết token còn sống không (nút bấm tay).

    Đây là ngoại lệ có chủ ý của luật "không gọi API mỗi lần mở màn hình": người
    dùng chủ động bấm, mỗi lần đúng 1 lời gọi nhẹ.
    """
    acc = integration_repo.get_account(account_id)
    if not acc:
        raise ApiError("NOT_FOUND", "Không tìm thấy kết nối này")

    provider = acc["provider"]
    token = (settings.pancake_access_token if provider == "pancake_pages"
             else settings.pancake_pos_api_key)
    if not token:
        thieu = "Chưa cấu hình token trong .env"
        acc = integration_repo.update_account(account_id, {
            "token_status": "missing", "status": "error",
            "token_checked_at": _bay_gio(), "last_error": thieu,
            "last_error_at": _bay_gio(),
        })
        return {**(acc or {}), "ok": False, "message": thieu}

    try:
        if provider == "pancake_pages":
            from app.integrations.pancake import client

            pages = await client.list_pages(force=True)
            thong_diep = f"Token còn hiệu lực — thấy {len(pages)} page"
            so_luong = len(pages)
        else:
            from app.integrations.pancake_pos import client as pos_client

            shops = await pos_client.list_shops()
            thong_diep = f"api_key còn hiệu lực — thấy {len(shops)} shop"
            so_luong = len(shops)
    except Exception as err:  # noqa: BLE001 — mọi lỗi ngoài đều là "token/kết nối hỏng"
        loi = f"{type(err).__name__}: {err}"[:500]
        integration_repo.update_account(account_id, {
            "token_status": "invalid", "status": "error",
            "token_checked_at": _bay_gio(),
            "last_error": loi, "last_error_at": _bay_gio(),
        })
        _audit(actor, action="integration_check_failed", object_id=account_id,
               new_value={"error": loi})
        return {"ok": False, "message": loi}

    acc = integration_repo.update_account(account_id, {
        "token_status": "ok", "status": "active",
        "token_hint": _mask(token),
        "token_checked_at": _bay_gio(),
        "last_ok_at": _bay_gio(),
        "last_error": None, "last_error_at": None,
    })
    _audit(actor, action="integration_check_ok", object_id=account_id,
           new_value={"so_luong": so_luong})
    return {**(acc or {}), "ok": True, "message": thong_diep}


# ------------------------------------------------------------------ page
def danh_sach_page(account_id: int | None = None) -> list[dict]:
    return integration_repo.list_pages(account_id)


def bat_tat_page(page_id: int, bat: bool, actor: dict | None = None) -> dict:
    """Bật/tắt đồng bộ CRM cho 1 page (poller vẫn chạy phục vụ bot như cũ)."""
    cu = integration_repo.get_page(page_id)
    if not cu:
        raise ApiError("NOT_FOUND", "Không tìm thấy page")
    moi = integration_repo.set_page_sync(page_id, bat)
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="pages", object_id=page_id,
        action="page_sync_on" if bat else "page_sync_off",
        old_value={"sync_enabled": cu["sync_enabled"]},
        new_value={"sync_enabled": bat},
    )
    return moi


def gan_page_vao_ket_noi(page_id: int, account_id: int | None,
                         actor: dict | None = None) -> dict:
    """Ánh xạ page -> tài khoản Pancake nào (màn Ánh xạ)."""
    if not integration_repo.get_page(page_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy page")
    if account_id is not None and not integration_repo.get_account(account_id):
        raise ApiError("NOT_FOUND", "Không tìm thấy kết nối")
    moi = integration_repo.set_page_account(page_id, account_id)
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="pages", object_id=page_id,
        action="page_account_mapped", new_value={"account_id": account_id},
    )
    return moi


# ------------------------------------------------------------------ nhân viên
def danh_sach_nhan_vien(provider: str = "") -> list[dict]:
    return integration_repo.list_staff(provider)


def gan_nhan_vien(provider: str, external_staff_id: str, user_id: int | None,
                  actor: dict | None = None) -> dict:
    """Ánh xạ nhân viên Pancake -> tài khoản CRM (màn Ánh xạ)."""
    if provider not in integration_repo.PROVIDERS:
        raise ApiError("VALIDATION_ERROR", f"Nguồn lạ: {provider}")
    if not str(external_staff_id or "").strip():
        raise ApiError("VALIDATION_ERROR", "Thiếu ID nhân viên bên Pancake")
    row = integration_repo.gan_staff(provider, external_staff_id, user_id)
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="staff_mappings",
        object_id=row["id"], action="staff_mapped",
        new_value={"external_staff_id": external_staff_id, "user_id": user_id},
    )
    return row


# ------------------------------------------------------------------ nhật ký
def mo_log(provider: str, entity: str, scope: str = "", run_type: str = "poll") -> int:
    return integration_repo.bat_dau_log(
        provider=provider, entity=entity, scope=scope, run_type=run_type)


def dong_log(log_id: int, ket_qua: dict, message: str = "") -> None:
    """Đóng nhật ký từ dict đếm của sync_batch ({tao_moi, cap_nhat, bo_qua, loi})."""
    integration_repo.ket_thuc_log(
        log_id,
        tao_moi=int(ket_qua.get("tao_moi") or 0),
        cap_nhat=int(ket_qua.get("cap_nhat") or 0),
        bo_qua=int(ket_qua.get("bo_qua") or 0),
        loi=int(ket_qua.get("loi") or 0),
        message=message,
    )


def danh_sach_log(**kw) -> tuple[list[dict], int]:
    return integration_repo.list_logs(**kw)


# ------------------------------------------------------------------ hàng đợi lỗi
def ghi_loi(provider: str, entity: str, external_id: str, err: Exception,
            *, payload: dict | None = None, scope: str = "",
            sync_log_id: int | None = None) -> None:
    """Đưa 1 bản ghi hỏng vào hàng đợi retry. TỰ NUỐT lỗi của chính nó.

    Gọi từ trong except của luồng đồng bộ: nếu ghi hàng đợi cũng hỏng (DB sập)
    thì chỉ in stderr — không được ném tiếp làm vỡ luồng bot/worker.
    """
    try:
        integration_repo.ghi_loi(
            provider=provider, entity=entity, external_id=str(external_id),
            payload=payload, error_type=type(err).__name__,
            error_message=str(err), scope=scope, sync_log_id=sync_log_id,
        )
    except Exception as err2:  # noqa: BLE001 — xem docstring
        print(f"[integration] không ghi được hàng đợi lỗi: {err2}", file=sys.stderr)


def danh_sach_loi(**kw) -> tuple[list[dict], int]:
    return integration_repo.list_loi(**kw)


def thu_lai_ngay(error_id: int, actor: dict | None = None) -> dict:
    """Người bấm "Thử lại" -> đặt hạn về NGAY, worker retry nhặt ở lượt kế."""
    row = integration_repo.get_loi(error_id)
    if not row:
        raise ApiError("NOT_FOUND", "Không tìm thấy dòng lỗi")
    moi = integration_repo.hen_lai(error_id, 0)
    audit_repo.ghi(
        user_id=_actor_id(actor), object_type="sync_errors", object_id=error_id,
        action="sync_error_retry", new_value={"entity": row["entity"],
                                              "external_id": row["external_id"]},
    )
    return moi


def chay_hang_doi(limit: int = 50) -> dict:
    """Chạy lại các bản ghi lỗi đã tới hạn. Trả {da_thu, xong, con_loi}.

    Chạy lại từ `payload` đã lưu — KHÔNG gọi lại Pancake (dữ liệu cũ gọi lại
    cũng không còn). Payload rỗng thì bỏ cuộc luôn, đánh dấu given_up.
    """
    from app.integrations.pancake import crm_sync
    from app.integrations.pancake_pos import pos_sync

    rows = integration_repo.lay_loi_toi_han(limit)
    ket = {"da_thu": 0, "xong": 0, "con_loi": 0}
    if not rows:
        return ket

    anh_xa = order_repo.load_mapping_dict()
    for row in rows:
        ket["da_thu"] += 1
        payload = row.get("payload") or {}
        if not payload:
            integration_repo.ghi_loi(
                provider=row["provider"], entity=row["entity"],
                external_id=row["external_id"],
                error_type="EmptyPayload",
                error_message="Không còn dữ liệu gốc để chạy lại — xử lý tay",
            )
            ket["con_loi"] += 1
            continue
        try:
            if row["entity"] == "order":
                pos_sync.sync_row(payload, anh_xa)
            elif row["entity"] == "conversation":
                # page lấy từ scope, thiếu thì lấy bản kèm trong payload —
                # KHÔNG được để rỗng (crm_sync sẽ chặn: xem _crm_page_id).
                crm_sync.sync_row(
                    row.get("scope") or payload.get("_page_id") or "",
                    payload.get("_page_name") or "", payload)
            elif row["entity"] == "message":
                # FR-012: payload giữ nguyên mẻ tin đã lấy được từ Pancake —
                # phát lại đúng phần GHI DB, không gọi lại API.
                from app.integrations.pancake import message_sync

                message_sync.ghi_mot_me(
                    int(payload["_conv_crm_id"]), payload.get("_rows") or [])
            else:
                raise ValueError(f"Chưa hỗ trợ chạy lại loại: {row['entity']}")
            integration_repo.danh_dau_xong(row["id"])
            ket["xong"] += 1
        except Exception as err:  # noqa: BLE001 — lỗi lần nữa thì giãn lịch, không vỡ vòng
            ket["con_loi"] += 1
            integration_repo.ghi_loi(
                provider=row["provider"], entity=row["entity"],
                external_id=row["external_id"], payload=payload,
                error_type=type(err).__name__, error_message=str(err),
                scope=row.get("scope") or "",
            )
    return ket


# ------------------------------------------------------------------ tổng hợp
def tinh_trang(so_gio: int = 24) -> dict:
    """Khối "Tình trạng đồng bộ" (dữ liệu đầu ra của mục 4).

    Toàn bộ đọc từ DB — mở màn hình bao nhiêu lần cũng không gọi Pancake.
    """
    ket_noi = danh_sach_ket_noi()
    return {
        "ket_noi": ket_noi,
        "canh_bao_token": [k["name"] for k in ket_noi if k["canh_bao"]],
        # Đọc công tắc ĐANG CÓ HIỆU LỰC (màn Cài đặt đổi được lúc chạy), không
        # phải giá trị .env đọc-một-lần lúc khởi động.
        "cong_tac": {
            "crm_sync_enabled": runtime_config.bat("crm_sync_enabled"),
            "pos_sync_enabled": runtime_config.bat("pos_sync_enabled"),
        },
        "theo_nguon": integration_repo.thong_ke_log(so_gio),
        "loi_dang_cho": integration_repo.dem_loi_dang_cho(),
        "quy_nguon": attribution_repo.dem_cham(),
    }
