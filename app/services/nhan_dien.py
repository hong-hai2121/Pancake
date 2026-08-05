"""Bộ NHẬN DIỆN tin nhân viên gõ (Đợt 2 — mẫu Kallet `cai-dat.php?sec=script`).

Trả lời ba câu hỏi trên MỘT câu chat:

    1. Câu này có phải bằng chứng ĐÃ GỌI khách không?
    2. Có phải tin BÁO MÃ giảm giá cho khách không?
    3. Nếu không, vì sao không — phải nói ra được.

Câu 3 là lý do module này CỐ Ý không dùng AI: kết quả dò được đem đi bác công
của nhân viên, mà bác công thì phải chỉ ra được đã dò cái gì và không thấy gì.

HAI NGUỒN MẪU, cộng vào nhau chứ không thay nhau:

    nền   hằng trong `services/tieng_viet.py` — luôn có hiệu lực, admin không
          xoá được. Bảng mẫu rỗng thì bộ dò vẫn chạy y như trước Đợt 2.
    thêm  `crm.phrase_patterns` — admin tự khai trên màn Cài đặt.

Gộp kiểu này vì bộ nền là phần đã chạy đúng nhiều tháng; để admin xoá được nó
là một buổi chiều nghịch tay có thể làm cả hệ thống soi tin ngừng nhận diện mà
không ai biết.

CHÈN TỪ LẠ: "em vừa gọi" phải bắt được cả "em vừa mới gọi", "em vừa alo gọi".
Dò chuỗi thẳng thì trượt. Nên mẫu được dịch thành regex cho phép tối đa N từ lạ
xen giữa các từ của mẫu (`nhandien_goi_gap`, mặc định 2). Đặt N quá lớn là mẫu
bắt bừa: "gọi" cách "vừa" mười từ thì hai chữ đó chẳng liên quan gì nhau nữa.
"""

import re
import time

from app.core import runtime_config
from app.services import tieng_viet as tv

_TTL = 10.0
_cache: dict = {"luc": 0.0, "data": None}


# --------------------------------------------------------------- nạp mẫu
def _nap() -> dict[str, list[dict]]:
    """{loại: [mẫu…]} từ DB, cache `_TTL` giây. Bảng lỗi/chưa tạo -> rỗng: bộ
    nền vẫn đủ để chạy, không được để màn soi tin chết theo."""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["luc"] < _TTL:
        return _cache["data"]
    ra: dict[str, list[dict]] = {k: [] for k in ("goi", "chan", "voucher",
                                                 "viet_tat")}
    try:
        from app.db.repositories import nhan_dien_repo

        for r in nhan_dien_repo.tat_ca(chi_active=True):
            ra.setdefault(r["kind"], []).append(dict(r))
    except Exception:                       # noqa: BLE001 — xem docstring
        pass
    _cache.update(luc=now, data=ra)
    return ra


def xoa_cache() -> None:
    _cache.update(luc=0.0, data=None)


def mau(loai: str) -> list[str]:
    """Danh sách mẫu ĐANG DÙNG của một loại = nền + phần admin khai thêm."""
    nen = {"goi": tv.MAU_DA_GOI, "chan": tv.MAU_CHAN_GOI,
           "voucher": TU_VOUCHER_NEN}.get(loai, [])
    them = [p["pattern"] for p in _nap().get(loai, [])]
    # dict.fromkeys: bỏ trùng mà GIỮ thứ tự — nền trước, admin sau, để câu giải
    # thích "khớp mẫu X" luôn chỉ ra mẫu ổn định nhất trước.
    return list(dict.fromkeys([*nen, *them]))


def viet_tat() -> dict[str, str]:
    """Bảng bung viết tắt = nền + phần admin khai. Admin đè được một dòng nền
    (khai lại cùng viết tắt với nghĩa khác) nhưng không xoá được nó."""
    ra = dict(tv.VIET_TAT)
    for p in _nap().get("viet_tat", []):
        tat = tv.chuan_hoa(p["pattern"])
        day = tv.chuan_hoa(p.get("replacement") or "")
        if tat and day:
            ra[tat] = day
    return ra


# Từ báo voucher — bộ nền. Kênh A (dò đúng MÃ đã phát) không cần khai gì; kênh B
# dành cho voucher cũ không có mã, cần ĐÚNG con số mệnh giá VÀ một từ voucher
# trong cùng một tin.
TU_VOUCHER_NEN: list[str] = [
    "voucher", "ma giam", "ma giam gia", "uu dai", "khuyen mai", "coupon",
    "ma qua tang", "phieu giam",
]


# ------------------------------------------------------------ dò có chèn
def _bung(s: str) -> str:
    """Chuẩn hoá + bung viết tắt theo bảng ĐÃ GỘP (khác `tv.bung_viet_tat` chỉ
    biết bảng nền)."""
    bang = viet_tat()
    return " ".join(bang.get(t, t) for t in tv.chuan_hoa(s).split())


def khop_chen(mau_cau: str, van_ban: str, chen: int = 2) -> bool:
    """`mau_cau` xuất hiện trong `van_ban`, cho phép tối đa `chen` từ lạ xen
    giữa mỗi cặp từ liền nhau của mẫu.

    Ràng buộc biên từ (`\\b`) là bắt buộc: không có nó thì "goi" khớp luôn vào
    trong "goi y", "ngoi", và mọi thống kê đã gọi thành rác.
    """
    tu = _bung(mau_cau).split()
    if not tu:
        return False
    vb = _bung(van_ban)
    if chen <= 0:
        return re.search(r"\b" + r"\s+".join(map(re.escape, tu)) + r"\b",
                         vb) is not None
    noi = r"(?:\s+\S+){0," + str(int(chen)) + r"}\s+"
    return re.search(r"\b" + noi.join(map(re.escape, tu)) + r"\b",
                     vb) is not None


def kiem_mau(loai: str, mau_cau: str) -> None:
    """Chặn mẫu quá ngắn TRƯỚC khi nó vào bảng.

    Một mẫu MỘT TỪ ngắn là cái bẫy kinh điển sau khi bỏ dấu: khai "goi" thì
    "gợi ý" cũng thành "goi y" và khớp — mọi thống kê đã gọi thành rác, mà lỗi
    chỉ lộ ra hàng tuần sau khi có người soi lại công. Cụm nhiều từ thì không
    dính vì phải trúng cả cụm.

    `viet_tat` được miễn: viết tắt ngắn là bản chất của nó ("e", "k"), và bảng
    bung chỉ đổi TỪ ĐỨNG RIÊNG chứ không dò trong câu.
    """
    from app.core.errors import ApiError

    goc = tv.chuan_hoa(mau_cau)
    if not goc:
        raise ApiError("VALIDATION_ERROR", "Mẫu câu rỗng.")
    if loai == "viet_tat":
        return
    if len(goc.split()) == 1 and len(goc) <= 4:
        raise ApiError(
            "VALIDATION_ERROR",
            f'Mẫu «{mau_cau}» quá ngắn, dễ khớp nhầm sau khi bỏ dấu — '
            f'"{goc}" sẽ đụng vào mọi từ viết giống nó. Dùng CỤM nhiều từ '
            '(vd "vừa gọi cho" thay vì "gọi").')


def so_tu_chen() -> int:
    """Trần số từ lạ cho chèn giữa các từ của mẫu."""
    return max(0, min(5, int(runtime_config.so("nhandien_goi_gap", 2))))


def _khop_bat_ky(ds: list[str], van_ban: str) -> str | None:
    chen = so_tu_chen()
    for m in ds:
        if khop_chen(m, van_ban, chen):
            return m
    return None


# ------------------------------------------------------------------ kết luận
def la_tin_da_goi(noi_dung: str) -> bool:
    """Tin của nhân viên có phải bằng chứng "đã gọi khách" không?

    Danh sách CHẶN chạy TRƯỚC: "chị gọi lại cho em nhé" chứa chữ gọi nhưng là
    nhân viên NHỜ khách gọi, tính là đã gọi thì công được chấm oan.
    """
    if not noi_dung:
        return False
    if _khop_bat_ky(mau("chan"), noi_dung):
        return False
    return _khop_bat_ky(mau("goi"), noi_dung) is not None


def la_tin_bao_voucher(noi_dung: str, *, ma: str = "",
                       menh_gia: float | None = None) -> bool:
    """Kênh A (khớp MÃ đã phát) hoặc kênh B (con số mệnh giá + từ voucher)."""
    return bool(soi(noi_dung, ma=ma, menh_gia=menh_gia)["voucher"])


def _co_so(van_ban: str, menh_gia: float) -> bool:
    """Con số mệnh giá có trong tin không — KHÔNG cắt giữa số.

    "50000" không được khớp vào "150000": tin báo giảm 150k mà tính thành mã
    50k thì đối soát tiền sai. Chấp cả "50000", "50.000", "50k".
    """
    n = int(menh_gia)
    goc = tv.chuan_hoa(van_ban).replace(".", "").replace(",", "")
    cac = {str(n)}
    if n >= 1000 and n % 1000 == 0:
        cac.add(f"{n // 1000}k")
    return any(re.search(rf"(?<!\d){re.escape(c)}(?!\d)", goc) for c in cac)


def soi(noi_dung: str, *, ma: str = "", menh_gia: float | None = None) -> dict:
    """Bản GIẢI THÍCH ĐƯỢC: máy hiểu câu này thế nào và vì sao.

    Thứ tự chốt đúng theo mẫu: chặn → đã gọi → voucher. Đảo thứ tự là câu
    "lát em gọi báo mã cho chị" bị tính thành đã gọi.
    """
    noi_dung = noi_dung or ""
    ra = {"nhan": "không khớp gì", "vi_sao": "Không thấy mẫu nào trong câu này.",
          "mau": "", "goi": False, "voucher": False, "chan": False}
    if not noi_dung.strip():
        ra["vi_sao"] = "Câu rỗng — không có gì để dò."
        return ra

    if (m := _khop_bat_ky(mau("chan"), noi_dung)):
        ra.update(nhan="bị CHẶN", chan=True, mau=m,
                  vi_sao=f'Khớp mẫu chặn «{m}» — đây là hẹn gọi/nhờ khách gọi, '
                         "KHÔNG tính là đã gọi.")
        return ra
    if (m := _khop_bat_ky(mau("goi"), noi_dung)):
        ra.update(nhan="ĐÃ GỌI", goi=True, mau=m,
                  vi_sao=f'Khớp mẫu «{m}» trong danh sách tính là đã gọi.')
        return ra

    # Voucher — kênh A trước (chắc chắn hơn), rồi kênh B.
    if ma and len(str(ma).strip()) >= 5:
        goc = tv.chuan_hoa(noi_dung).replace(" ", "").replace("-", "")
        if tv.chuan_hoa(str(ma)).replace(" ", "").replace("-", "") in goc:
            ra.update(nhan="BÁO VOUCHER", voucher=True, mau=str(ma),
                      vi_sao=f"Kênh A — thấy đúng mã «{ma}» đã phát cho khách.")
            return ra
    if menh_gia and menh_gia > 0 and _co_so(noi_dung, menh_gia):
        if (m := _khop_bat_ky(mau("voucher"), noi_dung)):
            ra.update(nhan="BÁO VOUCHER", voucher=True, mau=m,
                      vi_sao=f'Kênh B — có đúng con số {int(menh_gia):,}'
                             .replace(",", ".")
                             + f' VÀ từ voucher «{m}» trong cùng một tin.')
            return ra
        ra["vi_sao"] = ("Có đúng con số mệnh giá nhưng KHÔNG có từ voucher nào "
                        "— chưa đủ để tính là báo mã.")
        return ra
    return ra
