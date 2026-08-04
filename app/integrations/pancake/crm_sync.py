"""B2 + BRD mục 4 — đổ hội thoại Pancake vào CRM (FR-011, FR-012).

Một hội thoại từ poller đi qua đây thành: khách (`crm.customers`, chống trùng
4 bậc) + định danh + dòng `crm.conversations` + lead tự động + **thẻ** (dịch ID
thẻ Pancake ra tên rồi gắn vào khách) + **nhân viên xử lý** (assignee Pancake
ánh xạ về `users` nếu Admin đã gán ở màn Tích hợp).

Nguyên tắc sống còn: hàm ở đây KHÔNG BAO GIỜ được ném lỗi lên poller — bot
trả lời khách là luồng chính, CRM là luồng bồi. Lỗi row nào vừa ghi stderr vừa
đẩy vào hàng đợi retry (`crm.sync_errors`) kèm nguyên văn hội thoại, để chạy lại
được mà không phải gọi lại Pancake.

Ánh xạ trường (xem app/db/repositories/inbox_store.py):
    customer_id (UUID Pancake)  -> bậc 1: external_customer_id
    fb_id                       -> bậc 2: PSID
    phones[0]                   -> bậc 3: SĐT (chuẩn hoá trong service)
    page_id + conv_id           -> bậc 4: page + external_conversation_id
    tags[]                      -> crm.tags/customer_tags (type='pancake')
    assignee_ids[0]             -> conversations.assignee_external_id (+ user_id)
    updated_at                  -> conversations.external_updated_at
"""

import json
import sys
import time

from app.db.repositories import (
    customer_repo,
    integration_repo,
    page_repo,
    tag_store,
)
from app.services import customer_service, integration_service

_PROVIDER = "pancake_pages"

_page_cache: dict[str, int] = {}   # external_page_id -> crm.pages.id

# Cờ "page nào đang TẮT đồng bộ" (màn Tích hợp) — đọc lại mỗi 60s thay vì mỗi
# hội thoại: poller gọi rất dày, mà Admin bật/tắt thì chờ 1 phút là chấp nhận được.
_tat_cache: dict = {"luc": 0.0, "ids": set()}
_TAT_TTL = 60.0

# Thẻ Pancake: {page_id: {tag_id: {'text','color'}}} — đọc từ kho watcher.the
# (poller đã làm tươi sẵn), cache ngắn cho khỏi query mỗi dòng.
_the_cache: dict = {"luc": 0.0, "data": {}}
_THE_TTL = 300.0


def _crm_page_id(external_page_id: str, page_name: str) -> int:
    """Tìm-hoặc-tạo crm.pages cho page Pancake; cache vì poller gọi dày.

    Chặn page rỗng: `find_or_create` sẽ tạo một dòng pages có external_page_id ''
    rồi mọi hội thoại thiếu page dồn hết vào đó — hỏng cả ánh xạ page lẫn link mở
    Pancake. Thà để lỗi rơi vào hàng đợi cho người xử lý.
    """
    if not str(external_page_id or "").strip():
        raise ValueError("Thiếu external_page_id — không đồng bộ hội thoại 'mồ côi'")
    pid = _page_cache.get(external_page_id)
    if pid is None:
        pid = page_repo.find_or_create(
            platform="facebook",
            external_page_id=external_page_id,
            name=page_name or external_page_id,
        )["id"]
        _page_cache[external_page_id] = pid
    return pid


def _dang_tat(external_page_id: str) -> bool:
    """Page bị TẮT đồng bộ ở màn Tích hợp -> bỏ qua, poller vẫn chạy cho bot."""
    if time.monotonic() - _tat_cache["luc"] > _TAT_TTL:
        try:
            _tat_cache["ids"] = integration_repo.pages_tat_dong_bo()
        except Exception:  # noqa: BLE001 — DB hỏng thì cứ đồng bộ như cũ
            _tat_cache["ids"] = set()
        _tat_cache["luc"] = time.monotonic()
    return str(external_page_id) in _tat_cache["ids"]


def _the_cua_page(external_page_id: str) -> dict:
    if time.monotonic() - _the_cache["luc"] > _THE_TTL:
        try:
            _the_cache["data"] = tag_store.load_all_tags()
        except Exception:  # noqa: BLE001 — không có tên thẻ thì bỏ qua phần thẻ
            _the_cache["data"] = {}
        _the_cache["luc"] = time.monotonic()
    return _the_cache["data"].get(str(external_page_id), {})


def _phones(raw) -> str | None:
    """`phones` là list (từ API) hoặc chuỗi JSON (đọc lại từ DB) — lấy số đầu."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            return None
    return (raw or [None])[0]


def _ids(raw) -> list:
    """`tags`/`assignee_ids` cũng có 2 dạng (list từ API, chuỗi JSON từ DB)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            return []
    return list(raw or [])


def _dong_bo_the(customer_id: int, external_page_id: str, tag_ids: list) -> None:
    """Gắn thẻ Pancake vào khách CRM, dịch ID -> TÊN thẻ.

    Dịch theo tên (không theo ID) vì ID thẻ chỉ duy nhất TRONG một page: cùng
    nhãn "Đã chốt" ở 2 page mang 2 ID khác nhau nhưng phải về CÙNG một thẻ CRM.
    Thẻ chưa biết tên (kho thẻ chưa kịp làm tươi) thì bỏ qua, lượt sau bồi.
    """
    bang = _the_cua_page(external_page_id)
    for tid in tag_ids:
        try:
            ten = (bang.get(int(tid)) or {}).get("text")
        except (TypeError, ValueError):
            continue
        if not ten:
            continue
        the = customer_repo.find_or_create_tag(ten.strip(), "pancake")
        customer_repo.add_tag(customer_id, the["id"])


def _nhan_vien(assignee_ids: list) -> tuple[str | None, int | None]:
    """assignee đầu tiên -> (id bên Pancake, users.id trong CRM nếu đã ánh xạ).

    Ghi nhận mọi id gặp được vào `staff_mappings` để Admin có sẵn danh sách mà
    gán ở màn Ánh xạ — chưa gán thì user_id rỗng, KHÔNG chặn đồng bộ.
    """
    ids = [str(x) for x in assignee_ids if str(x or "").strip()]
    if not ids:
        return None, None
    ngoai = ids[0]
    try:
        integration_repo.upsert_staff(
            provider=_PROVIDER, external_staff_id=ngoai, role_hint="inbox")
        return ngoai, integration_repo.map_staff(_PROVIDER, ngoai)
    except Exception:  # noqa: BLE001 — ánh xạ hỏng không được chặn đồng bộ khách
        return ngoai, None


def sync_nhan_vien(danh_sach: list[dict], external_page_id: str) -> dict:
    """Đổ DANH SÁCH nhân viên của MỘT page vào staff_mappings. Trả dict đếm.

    Song song với pos_sync.sync_nhan_vien nhưng nghèo hơn: pages.fm chỉ trả
    tên + fb_id + quyền trên page, KHÔNG có email/SĐT/phòng ban. Vì hai bên
    dùng chung không gian uuid, người nào cũng có bên POS thì hồ sơ đầy đủ đã
    nằm ở dòng `pancake_pos` — dòng này chỉ cần đủ TÊN để Admin gán được.

    `role_in_page` (ADMINISTER/EDIT_PROFILE) là quyền trên page, KHÔNG phải vai
    nghiệp vụ, nên để trong `raw` chứ không đụng `role_hint` (seller/care/…).
    """
    dem = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    for u in danh_sach:
        ngoai = str(u.get("id") or "").strip()
        if not ngoai:
            dem["bo_qua"] += 1
            continue
        try:
            row = integration_repo.upsert_staff(
                provider=_PROVIDER, external_staff_id=ngoai,
                external_name=str(u.get("name") or "").strip(),
                ho_so={"fb_id": str(u.get("fb_id") or "").strip(),
                       "shop_id": "", "email": "", "phone": "", "department": "",
                       "avatar_url": "", "raw": {**u, "external_page_id": external_page_id}},
            )
            dem["tao_moi" if (row or {}).get("vua_tao") else "cap_nhat"] += 1
        except Exception as exc:  # noqa: BLE001 — 1 người hỏng không chặn cả mẻ
            dem["loi"] += 1
            print(f"[crm_sync] nhân viên {ngoai}: {exc}", file=sys.stderr)
    return dem


def sync_row(external_page_id: str, page_name: str, conv: dict) -> bool:
    """Đồng bộ MỘT hội thoại. Trả True nếu vừa tạo khách mới. Idempotent."""
    page_id = _crm_page_id(str(external_page_id), page_name)
    conv_id = str(conv.get("conv_id") or "")
    kh, vua_tao = customer_service.upsert_from_source(
        platform="facebook",
        name=conv.get("name"),
        phone=_phones(conv.get("phones")),
        external_customer_id=conv.get("customer_id") or None,
        psid=conv.get("fb_id") or None,
        page_id=page_id,
        external_conversation_id=conv_id or None,
        source="pancake",
    )
    tag_ids = _ids(conv.get("tags"))
    nv_ngoai, nv_crm = _nhan_vien(_ids(conv.get("assignee_ids")))
    if conv_id:
        customer_repo.upsert_conversation(
            customer_id=kh["id"], page_id=page_id,
            external_conversation_id=conv_id,
            last_message_at=conv.get("updated_at") or None,
            source="pancake",
            external_updated_at=conv.get("updated_at") or None,
            assignee_external_id=nv_ngoai,
            assignee_user_id=nv_crm,
            external_tags=tag_ids,
            snippet=(conv.get("snippet") or None),
            message_count=conv.get("message_count"),
            unread_count=conv.get("unread_count"),
        )
    if tag_ids:
        _dong_bo_the(kh["id"], str(external_page_id), tag_ids)
    customer_repo.danh_dau_dong_bo(kh["id"])
    return vua_tao


def sync_batch(external_page_id: str, page_name: str, convs: list[dict]) -> dict:
    """Poller gọi sau mỗi mẻ upsert. Nuốt lỗi từng row — không vỡ luồng bot.

    Mỗi mẻ ghi 1 dòng `crm.sync_logs` (màn Nhật ký đồng bộ); row hỏng vào
    `crm.sync_errors` kèm nguyên văn để worker retry chạy lại.
    """
    ket_qua = {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0, "loi": 0}
    if _dang_tat(external_page_id):
        ket_qua["bo_qua"] = len(convs)
        return ket_qua

    log_id = None
    try:
        log_id = integration_service.mo_log(
            _PROVIDER, "conversation", scope=str(external_page_id))
    except Exception as err:  # noqa: BLE001 — không có nhật ký vẫn phải đồng bộ
        print(f"[crm_sync] không mở được nhật ký: {err}", file=sys.stderr)

    for conv in convs:
        try:
            if sync_row(external_page_id, page_name, conv):
                ket_qua["tao_moi"] += 1
            else:
                ket_qua["cap_nhat"] += 1
        except Exception as err:  # noqa: BLE001 — xem docstring
            ket_qua["loi"] += 1
            print(
                f"[crm_sync] loi conv {conv.get('conv_id')}: {type(err).__name__}: {err}",
                file=sys.stderr,
            )
            integration_service.ghi_loi(
                _PROVIDER, "conversation", str(conv.get("conv_id") or ""),
                err,
                # Kèm page vào payload: lượt retry sau chỉ có mỗi dòng lỗi trong
                # tay, thiếu page là không biết đổ hội thoại vào đâu.
                payload={**conv, "_page_id": str(external_page_id),
                         "_page_name": page_name},
                scope=str(external_page_id), sync_log_id=log_id,
            )

    if log_id:
        try:
            integration_service.dong_log(log_id, ket_qua)
            pid = _page_cache.get(str(external_page_id))
            if pid:
                integration_repo.mark_page_synced(
                    pid, f"{ket_qua['loi']} dòng lỗi" if ket_qua["loi"] else "")
        except Exception as err:  # noqa: BLE001
            print(f"[crm_sync] không đóng được nhật ký: {err}", file=sys.stderr)
    return ket_qua
