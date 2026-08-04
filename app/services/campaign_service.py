"""Luật chiến dịch 2 tầng + mẫu tin (C3 — port mẫu Kallet chien-dich.php,
mau-tin.php).

CHIẾN DỊCH HAI TẦNG — vì sao không gộp thành một:

    TẦNG 1  máy gửi cho CẢ TỆP (miễn phí, không tốn người)
              │
              └─ khách TRẢ LỜI ─────► TẦNG 2  sinh MỘT việc cho nhân viên

  Gộp một tầng nghĩa là ném cả tệp mấy chục nghìn khách vào bảng việc của vài
  người. Kết quả thực tế ở mẫu: quá tải, nhân viên bỏ luôn cả những khách thật
  sự quan tâm. Hai tầng lọc trước bằng máy, người chỉ chạm vào khách đã giơ tay.

BỐN LUẬT KHÁC, ĐỀU CÓ LÝ DO ĐAU THƯƠNG:

  * **Công tắc gửi tin** (`outbound_messaging_enabled`) mặc định TẮT. Tắt =
    chạy nháp: mọi thứ diễn ra như thật nhưng KHÔNG tin nào rời hệ thống và
    khách KHÔNG bị đánh dấu "đã gửi" — bật thật vẫn gửi đủ, không mất ai.
  * **Chia đợt** (mẫu chốt: thử 500 ngẫu nhiên → 5.000/tuần). Bắn cả tệp một
    lượt là cách nhanh nhất để Meta khoá page.
  * **J5 — 1 khách không nằm 2 chiến dịch cùng lúc**, nhưng chiến dịch ĐÓNG
    rồi thì phải NHẢ khách ra. Quên nhả là khách kẹt vĩnh viễn.
  * **Đếm xem trước và nạp thật dùng CHUNG một bộ lọc** — "thấy bao nhiêu thì
    nạp đúng bấy nhiêu", không có chuyện xem 3.000 mà nạp 12.000.
"""

import re
from datetime import timedelta

from app.core import runtime_config
from app.core.errors import ApiError
from app.core.ngay import bay_gio, hom_nay
from app.db.repositories import campaign_repo as repo

# Nhóm khách theo số ngày im ắng — khớp mẫu (151-180 · 181-210 · >210).
NHOM_TEP: dict[str, tuple[str, int, int | None]] = {
    "151_180": ("Sắp rời bỏ · 151–180 ngày", 151, 180),
    "181_210": ("Đang rời bỏ · 181–210 ngày", 181, 210),
    "ngu210":  ("Khách ngủ · quá 210 ngày", 211, None),
}

TRANG_THAI = {"draft": "Nháp", "running": "Đang chạy",
              "paused": "Tạm dừng", "finished": "Đã đóng"}


def gui_that() -> bool:
    """Công tắc an toàn. False = chế độ NHÁP."""
    return bool(runtime_config.bat("outbound_messaging_enabled"))


def tran_moi_dot() -> int:
    return int(runtime_config.so("campaign_batch_max", 500))


# ------------------------------------------------------------------ tệp khách
def chuan_hoa_loc(nguon: dict) -> dict:
    """Chuẩn hoá tham số bộ lọc từ form — MỘT nơi duy nhất, để màn xem trước và
    lúc nạp thật không bao giờ hiểu khác nhau."""
    nhom = str(nguon.get("nhom") or "ngu210")
    if nhom not in NHOM_TEP:
        nhom = "ngu210"
    _, tu, den = NHOM_TEP[nhom]
    hang = re.sub(r"[^a-z_]", "", str(nguon.get("hang") or ""))
    so_mua = str(nguon.get("so_mua") or "")
    return {
        "nhom": nhom, "ngu_tu": tu, "ngu_den": den,
        "hang": hang if hang else "",
        "so_mua": so_mua if so_mua in ("1", "2p") else "",
    }


def xem_truoc(loc: dict) -> int:
    """Bao nhiêu khách khớp bộ lọc NGAY BÂY GIỜ (đã trừ khách đang ở chiến
    dịch khác — luật J5)."""
    return repo.dem_xem_truoc(chuan_hoa_loc(loc))


# ------------------------------------------------------------------ vòng đời
def tao(*, ten: str, loc: dict, mo_ta: str = "", flow_id: str = "",
        template_id: int | None = None, kenh: str = "bot",
        moi_dot: int = 500, cach_ngay: int = 7, han: str = "",
        gan_cho: int | None = None, nguoi: int | None = None) -> dict:
    """Tạo chiến dịch + nạp tệp khách theo đúng bộ lọc vừa xem trước."""
    ten = (ten or "").strip()
    if not ten:
        raise ApiError("VALIDATION_ERROR", "Chiến dịch phải có tên.")
    loc = chuan_hoa_loc(loc)
    cd = repo.tao(
        name=ten, description=(mo_ta or "").strip(), rule=loc,
        channel=kenh, flow_id=(flow_id or "").strip() or None,
        template_id=template_id,
        batch_size=max(1, min(int(moi_dot or 500), 5000)),
        batch_interval_days=max(1, min(int(cach_ngay or 7), 60)),
        deadline=han or None, created_by=nguoi)
    so = repo.nap_khach(int(cd["id"]), loc, gan_cho=gan_cho)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="tao_chien_dich", object_type="campaign",
                   object_id=int(cd["id"]), user_id=nguoi,
                   new_value={"ten": ten, "so_khach": so, "loc": str(loc)})
    return {**dict(cd), "so_khach": so}


def doi_trang_thai(campaign_id: int, trang_thai: str, *,
                   nguoi: int | None = None) -> dict:
    if trang_thai not in TRANG_THAI:
        raise ApiError("VALIDATION_ERROR", f"Trạng thái lạ: {trang_thai}")
    cd = repo.get(campaign_id)
    if not cd:
        raise ApiError("NOT_FOUND", "Không tìm thấy chiến dịch.")
    kq = repo.doi_trang_thai(campaign_id, trang_thai)
    nha = 0
    if trang_thai == "finished":
        # Đóng thì phải NHẢ khách chưa chốt, nếu không họ kẹt vĩnh viễn (J5).
        nha = repo.nha_khach(campaign_id)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="doi_trang_thai_chien_dich", object_type="campaign",
                   object_id=campaign_id, user_id=nguoi,
                   old_value={"status": cd["status"]},
                   new_value={"status": trang_thai, "nha_khach": nha})
    return {**dict(kq or {}), "nha_khach": nha}


# ------------------------------------------------------------------ TẦNG 1
async def chay_dot(campaign_id: int, so_luong: int = 0, *,
                   nguoi: int | None = None) -> dict:
    """Gửi MỘT đợt tin tầng 1.

    Chế độ NHÁP (công tắc tắt): duyệt hết danh sách, dựng đủ nội dung, nhưng
    KHÔNG gọi Pancake và KHÔNG đóng dấu `sent_at`. Nhờ vậy chạy thử bao nhiêu
    lần cũng được mà không "tiêu" mất khách nào.
    """
    cd = repo.get(campaign_id)
    if not cd:
        raise ApiError("NOT_FOUND", "Không tìm thấy chiến dịch.")
    if cd["status"] != "running":
        raise ApiError("CONFLICT",
                       "Chiến dịch chưa ở trạng thái Đang chạy — bấm Chạy trước.")
    cap = max(1, min(int(so_luong or cd["batch_size"] or 500), tran_moi_dot()))
    ds = repo.khach_chua_gui(campaign_id, cap)
    that = gui_that()
    da_gui, loi = 0, 0

    for kh in ds:
        if not that:
            continue                      # nháp: đếm mà không gửi, không đánh dấu
        try:
            await _gui_tang_1(cd, kh)
        except Exception:                 # noqa: BLE001 — 1 khách hỏng không dừng đợt
            loi += 1
            continue
        repo.danh_dau_da_gui(int(kh["member_id"]), "da_gui")
        da_gui += 1

    if that:
        repo.ghi_nhip_dot(campaign_id)
        if cd.get("template_id"):
            repo.cong_da_gui(int(cd["template_id"]), da_gui)

    from app.db.repositories import audit_repo

    audit_repo.ghi(action="chay_dot_chien_dich", object_type="campaign",
                   object_id=campaign_id, user_id=nguoi,
                   new_value={"chon": len(ds), "da_gui": da_gui, "loi": loi,
                              "che_do": "that" if that else "nhap"})
    return {"chon": len(ds), "da_gui": da_gui, "loi": loi, "gui_that": that}


async def _gui_tang_1(cd: dict, kh: dict) -> None:
    """Gửi một tin tầng 1. Tách riêng để chế độ nháp không bao giờ chạm vào."""
    from app.integrations.pancake import client

    page = kh.get("external_page_id")
    conv = kh.get("external_conversation_id")
    if not (page and conv):
        raise ApiError("CONFLICT", "Khách chưa có hội thoại Pancake")
    noi_dung = _noi_dung_tin(cd, kh)
    if not noi_dung:
        raise ApiError("CONFLICT", "Chiến dịch chưa gắn mẫu tin/kịch bản")
    await client.send_message(str(page), str(conv), noi_dung)


def _noi_dung_tin(cd: dict, kh: dict) -> str:
    if not cd.get("template_id"):
        return ""
    mau = repo.get_mau(int(cd["template_id"]))
    if not mau:
        return ""
    return dien_bien(mau["body"], {"ten_khach": kh.get("full_name") or "bạn"})


def dien_bien(body: str, gia_tri: dict) -> str:
    """Thay {{bien}} bằng giá trị thật. Biến không có giá trị để NGUYÊN dấu
    ngoặc — thà khách thấy `{{ten_khach}}` còn hơn gửi đi câu cụt lủn mà không
    ai biết là đã hỏng."""
    def _thay(m):
        khoa = m.group(1).strip()
        return str(gia_tri.get(khoa, m.group(0)))

    return re.sub(r"\{\{\s*([a-z0-9_]+)\s*\}\}", _thay, body or "")


# ------------------------------------------------------------------ TẦNG 2
def hook_khach_tra_loi(customer_id: int) -> dict | None:
    """Khách trong chiến dịch NHẮN LẠI → sinh việc TẦNG 2 cho nhân viên.

    Gọi từ luồng đồng bộ tin nhắn. Idempotent: khách nhắn 10 câu vẫn chỉ một
    việc (điều kiện `responded_at is null` ở repo).
    """
    tv = repo.thanh_vien_dang_cham(customer_id)
    if not tv or tv["campaign_status"] != "running" or tv["responded_at"]:
        return None
    task_id = None
    nguoi = tv.get("assigned_to") or _nguoi_phu_trach(customer_id)
    if nguoi:
        from app.services import task_service

        try:
            task = task_service.create_task({
                "task_type": "mua_lai",
                "title": f'Khách trả lời chiến dịch "{tv["campaign_name"]}"',
                "assigned_to": nguoi,
                "customer_id": customer_id,
                "due_at": bay_gio() + timedelta(days=1),
                "priority": "high",
            })
            task_id = int(task["id"])
        except Exception:  # noqa: BLE001 — không có người phụ trách vẫn phải
            task_id = None      # ghi nhận là khách ĐÃ trả lời
    return repo.danh_dau_tra_loi(int(tv["id"]), task_id)


def _nguoi_phu_trach(customer_id: int) -> int | None:
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        r = conn.execute(
            "select user_id from crm.customer_assignments "
            "where customer_id = %s and end_at is null "
            "order by id desc limit 1", (customer_id,),
        ).fetchone()
    return int(r["user_id"]) if r else None


# ------------------------------------------------------------------ báo cáo
def so_sanh() -> list[dict]:
    """R6 — so sánh kết quả giữa các chiến dịch.

    Ba tỷ lệ, mỗi cái trả lời một câu hỏi khác nhau:
      * tra_loi_pct  — nội dung tầng 1 có đủ hấp dẫn để khách giơ tay không?
      * chot_pct     — nhân viên có chốt được khách đã giơ tay không?
      * ra_don_pct   — hiệu quả CHUNG của cả chiến dịch.
    Trộn ba số này làm một là mất khả năng biết lỗi nằm ở tầng nào.
    """
    ra = []
    for c in repo.danh_sach():
        d = dict(c)
        so_khach = int(d["so_khach"] or 0)
        da_gui = int(d["da_gui"] or 0)
        tra_loi = int(d["da_tra_loi"] or 0)
        ra_don = int(d["ra_don"] or 0)
        d["tra_loi_pct"] = round(tra_loi / da_gui * 100, 1) if da_gui else None
        d["chot_pct"] = round(ra_don / tra_loi * 100, 1) if tra_loi else None
        d["ra_don_pct"] = round(ra_don / so_khach * 100, 1) if so_khach else None
        ra.append(d)
    return ra


# ------------------------------------------------------------------ mẫu tin
_BIEN_HOP_LE = re.compile(r"^[a-z0-9_]+$")


def luu_mau_tin(*, code: str, name: str, body: str, kind: str = "tu_do",
                meta_status: str = "rong", variables: str = "",
                nguoi: int | None = None) -> dict:
    """Lưu mẫu tin. Chặn hai kiểu sai hay gặp:

      * biến trong nội dung mà không khai ở danh sách biến → lúc gửi thật sẽ
        lòi ra `{{...}}` trước mặt khách;
      * mẫu `tu_do` nhưng đánh dấu gửi được NGOÀI cửa 24h → Meta phạt page.
    """
    code = (code or "").strip().upper()
    if not code:
        raise ApiError("VALIDATION_ERROR", "Mẫu tin phải có mã.")
    if kind not in ("tu_do", "meta_duyet"):
        raise ApiError("VALIDATION_ERROR", f"Loại mẫu lạ: {kind}")
    if meta_status not in ("gui_ngoai_cua", "chi_trong_cua", "rong"):
        raise ApiError("VALIDATION_ERROR", f"Trạng thái Meta lạ: {meta_status}")
    if kind == "tu_do" and meta_status == "gui_ngoai_cua":
        raise ApiError(
            "VALIDATION_ERROR",
            "Mẫu TỰ DO không gửi được ngoài cửa 24h — muốn gửi ngoài cửa phải "
            "là mẫu Meta đã duyệt.")
    khai = {v.strip() for v in (variables or "").split(",") if v.strip()}
    xau = [v for v in khai if not _BIEN_HOP_LE.match(v)]
    if xau:
        raise ApiError("VALIDATION_ERROR",
                       f"Tên biến chỉ gồm chữ thường/số/gạch dưới: {xau}")
    dung = set(re.findall(r"\{\{\s*([a-z0-9_]+)\s*\}\}", body or ""))
    thieu = sorted(dung - khai)
    if thieu:
        raise ApiError(
            "VALIDATION_ERROR",
            f"Nội dung dùng biến chưa khai: {', '.join(thieu)} — khai vào ô "
            "Biến, nếu không lúc gửi khách sẽ thấy nguyên dấu ngoặc.")
    return repo.luu_mau(code=code, name=(name or "").strip(), kind=kind,
                        meta_status=meta_status,
                        variables=",".join(sorted(khai)), body=body or "",
                        created_by=nguoi)


def xem_thu(template_id: int, gia_tri: dict | None = None) -> str:
    mau = repo.get_mau(template_id)
    if not mau:
        raise ApiError("NOT_FOUND", "Không tìm thấy mẫu tin.")
    mac_dinh = {"ten_khach": "Chị Lan", "ma_voucher": "SALE50K",
                "so_tien": "50.000đ"}
    return dien_bien(mau["body"], {**mac_dinh, **(gia_tri or {})})
