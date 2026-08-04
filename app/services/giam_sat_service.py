"""Luật C4 — thư viện kịch bản · kho data · vòng xác minh công ("soi tin").

Port từ mẫu Kallet: kich-ban.php · kho-data.php · lich-su.php ·
includes/xac_minh.php.

VÒNG XÁC MINH CÔNG — bốn luật, mỗi luật vá một cách gian lận hoặc một kiểu oan:

  1. **1 CÔNG / khách / nhân viên / hành động / NGÀY.** Nhắn 10 tin vẫn 1 công.
     Không có luật này thì spam tin là ra tiền.
  2. **TIN NHẮN THẬT là bằng chứng.** Máy soi `crm.messages`; thấy nhân viên
     nhắn thì tự cộng công và đánh dấu đã xác minh — không cần ai bấm gì.
  3. **Tự khai quá hạn không soi thấy tin → tự BÁC.** Trưởng nhóm vớt tay được
     (có ghi ai vớt, vì sao).
  4. **CỬA SỔ SOI ±1 NGÀY.** Nhân viên hay nhắn buổi sáng, tối mới ngồi tick;
     soi đúng trong ngày là bác oan hàng loạt.

Và một luật về gọi điện: cuộc gọi KHÔNG đi qua hệ thống nên không có log nào.
Bằng chứng duy nhất là câu nhân viên gõ vào chat sau khi gọi ("e vừa gọi c
rồi ạ") — nên phải khớp được cả ba kiểu gõ, xem services/tieng_viet.py.
"""

from datetime import timedelta

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import bay_gio, hom_nay
from app.db.repositories import giam_sat_repo as repo
from app.services import tieng_viet as tv

HANH_DONG = {"nhan": "Nhắn tin", "goi": "Gọi điện",
             "tang_voucher": "Tặng voucher", "xong": "Hoàn thành việc"}

NHAN_TRANG_THAI = {
    "da_xac_minh": "Đã xác minh",
    "tu_khai_chua_soi": "Tự khai — chờ soi",
    "bac_bo": "Bị bác",
    "dang_xac_minh": "Đang soi",
}

NHAN_NGUON = {
    "may_tu_nhan": "🤖 Máy tự làm",
    "may_tu_soi": "🔍 Máy soi thấy tin",
    "tu_khai": "✍️ Người tự khai",
    "chat_ngay": "💬 Chat trong CRM",
}


def cua_soi_ngay() -> int:
    """Cửa sổ soi tính bằng NGÀY về mỗi phía. Mặc định 1 (±1 ngày)."""
    return int(runtime_config.so("verify_window_days", 1))


def han_bac_gio() -> int:
    """Tự khai quá ngần này giờ mà không soi thấy tin thì tự bác."""
    return int(runtime_config.so("verify_reject_hours", 72))


# ------------------------------------------------------------------ ghi công
# Kênh mặc định suy từ hành động — `care_interactions.channel` có CHECK
# ('call','chat','zalo','sms','direct'), không nhận 'pancake' như mẫu PHP.
_KENH_THEO_HANH_DONG = {"goi": "call", "nhan": "chat",
                        "tang_voucher": "chat", "xong": "direct"}


def ghi_cong(customer_id: int, user_id: int, action_kind: str, *,
             channel: str = "", may_tu_lam: bool = False,
             ly_do: str = "", luc=None) -> str:
    """CỔNG GHI CÔNG DUY NHẤT. Mọi nơi muốn cộng công phải đi qua đây.

    Trả: 'moi' (ghi mới) · 'nang_cap' (bằng chứng đến sau, nâng bản khai cùng
    ngày) · 'trung' (hôm nay đã có công này rồi, KHÔNG cộng thêm).

    `may_tu_lam=True` = máy chủ TỰ thực hiện hành động (CRM gửi tin hộ, tạo
    voucher) → bằng chứng theo cấu trúc, xác minh ngay không cần soi.
    """
    if action_kind not in HANH_DONG:
        raise ApiError("VALIDATION_ERROR", f"Hành động lạ: {action_kind}")
    channel = channel or _KENH_THEO_HANH_DONG.get(action_kind, "chat")
    luc = luc or bay_gio()
    ngay = luc.date() if hasattr(luc, "date") else hom_nay()

    cu = repo.cong_hom_nay(customer_id, user_id, action_kind, ngay)
    if cu:
        if may_tu_lam and cu["verify_status"] != "da_xac_minh":
            repo.nang_cong(int(cu["id"]),
                           ly_do or "máy nâng: có bằng chứng qua CRM cùng ngày")
            return "nang_cap"
        return "trung"

    dong = repo.ghi_cong(
        customer_id=customer_id, user_id=user_id, action_kind=action_kind,
        channel=channel,
        verify_source="may_tu_nhan" if may_tu_lam else "tu_khai",
        verify_status="da_xac_minh" if may_tu_lam else "tu_khai_chua_soi",
        action_at=luc,
        verify_reason=(ly_do or "máy ghi: hành động thực hiện qua CRM")
                      if may_tu_lam else "")
    # `on conflict do nothing` trả None khi có người ghi song song cùng lúc —
    # kết quả vẫn đúng luật 1-công/ngày nên báo 'trung', không phải lỗi.
    return "moi" if dong else "trung"


# ------------------------------------------------------------------ soi tin
def soi_mot(cong: dict) -> dict:
    """Soi MỘT bản tự khai. Trả {ket_qua, ly_do, bang_chung}.

    Ba kết quả: `da_xac_minh` (thấy bằng chứng) · `bac_bo` (quá hạn mà không
    thấy) · `cho_them` (chưa quá hạn, để lần sau soi tiếp — KHÔNG bác vội).
    """
    luc = cong.get("action_at") or cong.get("created_at")
    if not luc:
        return {"ket_qua": "cho_them", "ly_do": "thiếu mốc hành động",
                "bang_chung": None}
    cua = timedelta(days=cua_soi_ngay())
    tin = repo.tin_trong_cua(int(cong["customer_id"]), luc - cua, luc + cua)

    hd = cong.get("action_kind")
    for m in tin:
        # Tin phải đúng của NGƯỜI này. Pancake không phải lúc nào cũng trả
        # sender_user_id, nên rớt xuống so tên — thiếu cả hai thì bỏ qua tin đó
        # chứ không nhận vơ cho ai.
        if m.get("sender_user_id") and int(m["sender_user_id"]) != int(cong["user_id"]):
            continue
        if not m.get("sender_user_id"):
            continue
        if hd == "goi":
            # Cuộc gọi không có log — bằng chứng là câu nhân viên gõ sau khi gọi
            if not tv.la_tin_da_goi(m.get("content") or ""):
                continue
            return {"ket_qua": "da_xac_minh",
                    "ly_do": f'máy soi: thấy tin báo đã gọi "'
                             f'{(m["content"] or "")[:60]}"',
                    "bang_chung": m}
        return {"ket_qua": "da_xac_minh",
                "ly_do": f'máy soi: thấy tin nhân viên gửi lúc '
                         f'{m["sent_at"]:%d/%m %H:%M}',
                "bang_chung": m}

    tuoi = (bay_gio() - (luc if luc.tzinfo else luc.replace(tzinfo=None)))
    if tuoi.total_seconds() < han_bac_gio() * 3600:
        return {"ket_qua": "cho_them",
                "ly_do": "chưa tới hạn soi, để lần sau", "bang_chung": None}
    return {
        "ket_qua": "bac_bo",
        "ly_do": f"máy bác: quá {han_bac_gio()} giờ vẫn không soi thấy tin nào "
                 f"của nhân viên trong cửa ±{cua_soi_ngay()} ngày",
        "bang_chung": None,
    }


def soi_hang_loat(limit: int = 500) -> dict:
    """Một vòng soi. Worker gọi định kỳ; bấm tay ở màn Giám sát cũng gọi đây."""
    ket = {"soi": 0, "xac_minh": 0, "bac_bo": 0, "cho_them": 0}
    for cong in repo.cong_cho_soi(limit):
        kq = soi_mot(dict(cong))
        ket["soi"] += 1
        ket[kq["ket_qua"]] = ket.get(kq["ket_qua"], 0) + 1
        if kq["ket_qua"] == "cho_them":
            continue
        repo.dat_ket_qua_soi(
            int(cong["id"]), trang_thai=kq["ket_qua"], ly_do=kq["ly_do"],
            nguon="may_tu_soi" if kq["ket_qua"] == "da_xac_minh" else None)
    return ket


def duyet_tay(cong_id: int, dong_y: bool, ly_do: str, *,
              nguoi: int | None = None) -> dict:
    """Trưởng nhóm vớt/bác tay. BẮT BUỘC ghi lý do — công là tiền của người ta."""
    ly_do = (ly_do or "").strip()
    if not ly_do:
        raise ApiError("VALIDATION_ERROR",
                       "Phải ghi lý do khi duyệt/bác công.")
    kq = repo.dat_ket_qua_soi(
        cong_id, trang_thai="da_xac_minh" if dong_y else "bac_bo",
        ly_do=f'{"duyệt tay" if dong_y else "bác tay"}: {ly_do}', boi=nguoi)
    if not kq:
        raise ApiError("NOT_FOUND", "Không tìm thấy bản ghi công.")

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="duyet_cong" if dong_y else "bac_cong",
                   object_type="care_interaction", object_id=cong_id,
                   user_id=nguoi, reason=ly_do)
    return dict(kq)


# ------------------------------------------------------------ thư viện kịch bản
def luu_kich_ban(*, script_id: int | None = None, kind: str = "sale",
                 situation: str = "", title: str = "", body: str = "",
                 tags: str = "", milestone: str = "",
                 channel: str = "nhan_tin", nguoi: int | None = None) -> dict:
    """Lưu một câu mẫu. Cột BỎ DẤU sinh tự động — chỗ duy nhất sinh nó, để
    tìm kiếm không bao giờ lệch với nội dung."""
    if kind not in ("sale", "sau_ban"):
        raise ApiError("VALIDATION_ERROR", f"Loại kịch bản lạ: {kind}")
    if not (body or "").strip():
        raise ApiError("VALIDATION_ERROR", "Kịch bản phải có nội dung.")
    return repo.luu_kich_ban(
        id=script_id, kind=kind, situation=situation.strip(),
        milestone=milestone.strip() or None, channel=channel,
        title=title.strip(), body=body,
        body_nodiacritic=tv.chuan_hoa(body), tags=tags.strip(),
        created_by=nguoi)


def goi_y(tin_khach: str, so_luong: int = 3) -> list[dict]:
    """💡 Gợi ý kịch bản theo TỪ KHOÁ trong tin của khách.

    Dò từ khoá thuần, CỐ Ý không dùng AI: nhân viên phải hiểu được vì sao máy
    gợi ra câu này, và quản lý phải sửa được luật gợi ý mà không cần train lại
    cái gì. Khớp cả ba kiểu gõ (có dấu/bỏ dấu/viết tắt).
    """
    if not (tin_khach or "").strip():
        return []
    ra = []
    for luat in repo.luat_goi_y():
        tu_khoa = [t.strip() for t in (luat["keywords"] or "").split(",")
                   if t.strip()]
        trung = tv.khop_bat_ky(tu_khoa, tin_khach)
        if trung:
            ra.append({"script_id": luat["script_id"], "title": luat["title"],
                       "body": luat["body"], "kind": luat["kind"],
                       "vi_sao": f'khách nhắc tới "{trung}"'})
        if len(ra) >= so_luong:
            break
    return ra


def chep(script_id: int) -> dict:
    """Nhân viên CHÉP một câu mẫu. Chỉ đếm lượt dùng — KHÔNG gửi gì cho ai.

    Đây là ranh giới quan trọng nhất của màn Thư viện: mở/chép ở đây tuyệt đối
    không sinh tin nhắn. Muốn máy bắn tin thì sang Chiến dịch (C3)."""
    kb = repo.get_kich_ban(script_id)
    if not kb:
        raise ApiError("NOT_FOUND", "Không tìm thấy kịch bản.")
    repo.cong_luot_dung(script_id)
    return {"body": kb["body"], "title": kb["title"], "da_gui": False}


def kich_ban_chet(nguong: int = 0) -> list[dict]:
    """Kịch bản viết ra rồi KHÔNG AI DÙNG — dọn thư viện định kỳ."""
    rows, _ = repo.kich_ban(limit=1000)
    return [dict(r) for r in rows if int(r["use_count"] or 0) <= nguong]


# ------------------------------------------------------------------ kho data
def tong_quan_kho() -> dict:
    """Số liệu màn Kho data."""
    chua_chia = repo.khach_chua_chia(limit=500)
    ket = repo.khach_ket()
    return {
        "chua_chia": chua_chia[:200],
        "so_chua_chia": len(chua_chia),
        "ket": ket,
        "so_ket": len(ket),
        "nhat_ky_chia": repo.nhat_ky_chia(limit=50),
        "nhat_ky_gop": repo.nhat_ky_gop(limit=50),
        "nhat_ky_xuat": repo.nhat_ky_xuat(limit=50),
    }


def thu_hoi(customer_id: int, user_id: int, ly_do: str, *,
            khoa_ngay: int = 30, nguoi: int | None = None) -> dict:
    """Thu hồi khách khỏi một nhân viên. BẮT BUỘC lý do (mẫu chốt).

    Kèm khoá `khoa_ngay` ngày không chia lại cho chính người đó — nếu không sẽ
    thành vòng lặp thu hồi/chia lại vô nghĩa."""
    ly_do = (ly_do or "").strip()
    if not ly_do:
        raise ApiError("VALIDATION_ERROR",
                       "Thu hồi khách BẮT BUỘC ghi lý do — nhân viên phải biết "
                       "vì sao mất khách.")
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "update crm.customer_assignments set end_at = now() "
            "where customer_id = %s and user_id = %s and end_at is null",
            (customer_id, user_id))
    repo.ghi_chia(customer_id, tu=user_id, den=None, hanh_dong="thu_hoi",
                  ly_do=ly_do, boi=nguoi)
    repo.khoa_thu_hoi(customer_id, user_id, hom_nay() + timedelta(days=khoa_ngay),
                      ly_do)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="thu_hoi_khach", object_type="customer",
                   object_id=customer_id, user_id=nguoi,
                   old_value={"phu_trach": user_id}, reason=ly_do)
    return {"customer_id": customer_id, "khoa_den": hom_nay() + timedelta(days=khoa_ngay)}


def chia(customer_id: int, user_id: int, *, ly_do: str = "",
         may: bool = False, nguoi: int | None = None) -> dict:
    """Chia khách cho một nhân viên. Chặn nếu người đó đang bị KHOÁ với khách
    này (vừa bị thu hồi) — không thì thu hồi xong lại chia về chỗ cũ."""
    if repo.dang_bi_khoa(customer_id, user_id):
        raise ApiError(
            "CONFLICT",
            "Khách này vừa bị thu hồi khỏi chính nhân viên đó — đang trong "
            "thời gian khoá, chọn người khác hoặc chờ hết khoá.")
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute(
            "insert into crm.customer_assignments (customer_id, user_id, "
            "assignment_type) values (%s, %s, 'sale')",
            (customer_id, user_id))
    repo.ghi_chia(customer_id, tu=None, den=user_id,
                  hanh_dong="chia_deu" if may else "chia",
                  ly_do=ly_do, may=may, boi=nguoi)
    return {"customer_id": customer_id, "user_id": user_id}
