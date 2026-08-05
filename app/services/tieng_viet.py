"""So khớp chữ tiếng Việt kiểu người gõ thật (C4 — nền cho "soi tin" và tìm
kiếm thư viện kịch bản).

Nhân viên gõ cho khách theo ba kiểu, và cùng một người đổi kiểu giữa chừng:

    có dấu    "em vừa gọi chị rồi ạ"
    bỏ dấu    "em vua goi chi roi a"
    viết tắt  "e vua goi c r a"

Tìm kiếm khớp chuỗi thẳng chỉ bắt được kiểu đầu. Hệ quả thật ở mẫu: nhân viên
nhắn tin thật nhưng máy soi không thấy → công bị bác oan → nhân viên mất niềm
tin vào cả hệ thống. Nên module này bắt cả ba.

CỐ Ý KHÔNG dùng AI/embedding: kết quả soi phải **giải thích được** — bác công
của người ta thì phải chỉ ra được đã dò cái gì và không thấy cái gì.
"""

import re
import unicodedata

# Viết tắt hay gặp trong chat bán hàng VN. Mở rộng bằng cách thêm dòng —
# KHÔNG được xoá dòng cũ (sẽ làm soi lại các bản ghi cũ ra kết quả khác).
VIET_TAT: dict[str, str] = {
    "e": "em", "a": "anh", "c": "chi", "ac": "anh chi",
    "k": "khong", "ko": "khong", "kh": "khong", "hok": "khong",
    "r": "roi", "rui": "roi",
    "dc": "duoc", "đc": "duoc", "vs": "voi", "vk": "vo",
    "sp": "san pham", "lt": "lieu trinh", "sdt": "so dien thoai",
    "tk": "tai khoan", "ck": "chuyen khoan", "cod": "thu ho",
    "nt": "nhan tin", "gd": "goi dien", "dt": "dien thoai",
    "bs": "bac si", "bn": "benh nhan",
    # "kh" CỐ Ý để nghĩa "không" (đã khai ở trên) chứ không phải "khách hàng":
    # đây là bảng bung chữ trong TIN CHAT, mà trong chat "kh" gần như luôn là
    # "không". Khai lại ở đây sẽ đè mất dòng trên (dict lấy dòng cuối).
    "ib": "nhan tin rieng", "cmt": "binh luan",
    "trc": "truoc", "s": "sao", "j": "gi", "z": "vay", "v": "vay",
    "ny": "nay", "nx": "nhan xet", "ah": "a", "ak": "a",
}

# Dấu câu/emoji → khoảng trắng. Giữ chữ và số.
_RAC = re.compile(r"[^0-9a-z\s]")
_KHOANG = re.compile(r"\s+")


def bo_dau(s: str) -> str:
    """'Đau dạ dày' -> 'dau da day'. Chữ Đ/đ phải xử riêng: nó không phải D có
    dấu mà là một chữ cái khác, NFD không tách ra được."""
    if not s:
        return ""
    s = s.replace("Đ", "D").replace("đ", "d")
    tach = unicodedata.normalize("NFD", s)
    return "".join(c for c in tach if unicodedata.category(c) != "Mn")


def chuan_hoa(s: str) -> str:
    """Về dạng so sánh được: bỏ dấu · thường hoá · bỏ ký tự rác · gộp khoảng."""
    s = bo_dau(s or "").lower()
    s = _RAC.sub(" ", s)
    return _KHOANG.sub(" ", s).strip()


def bung_viet_tat(s: str) -> str:
    """'e vua goi c r' -> 'em vua goi chi roi'.

    Chỉ bung TỪ ĐỨNG RIÊNG. Không bung trong lòng từ khác, nếu không 'ca' sẽ
    thành 'chia' và mọi thứ loạn hết."""
    ra = []
    for tu in chuan_hoa(s).split():
        ra.append(VIET_TAT.get(tu, tu))
    return " ".join(ra)


def cac_dang(s: str) -> set[str]:
    """Ba dạng so sánh của một chuỗi — dùng cho cả hai phía (mẫu và tin thật)."""
    goc = (s or "").lower().strip()
    khong_dau = chuan_hoa(s)
    return {goc, khong_dau, bung_viet_tat(s)} - {""}


def khop(mau: str, van_ban: str) -> bool:
    """`mau` có xuất hiện trong `van_ban` không, xét cả ba dạng.

    Bung viết tắt CẢ HAI PHÍA: mẫu có thể viết đầy đủ ("vừa gọi") trong khi tin
    thật viết tắt ("vua goi"), và ngược lại người quản lý cũng hay gõ mẫu tắt.
    """
    if not (mau and van_ban):
        return False
    dang_vb = cac_dang(van_ban)
    for m in cac_dang(mau):
        if any(m in vb for vb in dang_vb):
            return True
    return False


def khop_bat_ky(mau: list[str], van_ban: str) -> str | None:
    """Mẫu ĐẦU TIÊN khớp, hoặc None. Trả về mẫu để giải thích được kết quả."""
    for m in mau:
        if khop(m, van_ban):
            return m
    return None


# Mẫu câu nhận diện "đã gọi điện" — nhân viên gõ vào chat sau khi gọi.
# Đây là bằng chứng cho hành động 'goi' (cuộc gọi không đi qua hệ thống nên
# không có log nào khác).
MAU_DA_GOI: list[str] = [
    "vua goi", "da goi", "goi cho", "goi dien", "em goi", "minh goi",
    "goi ma khong nghe", "goi khong bat may", "khong lien lac duoc",
    "goi lai sau", "alo",
]

# Mẫu CHẶN — chạy TRƯỚC MAU_DA_GOI. Câu chứa mẫu này thì KHÔNG tính là đã gọi,
# dù có chứa từ "gọi": "chị gọi lại cho em nhé" là nhân viên NHỜ khách gọi.
MAU_CHAN_GOI: list[str] = [
    "goi lai cho em", "goi lai cho minh", "chi goi", "anh goi",
    "khi nao ranh goi", "co gi goi",
    # Đ2 — HẸN gọi, chưa gọi. Thiếu mấy dòng này thì "lát em gọi lại cho chị"
    # bị chấm là đã gọi (mẫu "goi cho" khớp qua chữ "lai" xen giữa).
    "lat em goi", "lat nua em goi", "ti nua em goi", "chut nua em goi",
    "em se goi", "minh se goi", "em goi sau", "de em goi",
]


def la_tin_da_goi(noi_dung: str) -> bool:
    """Tin của nhân viên có phải bằng chứng "đã gọi khách" không?

    ⚠️ Đây là bản NỀN, chỉ biết hai hằng ở trên và dò chuỗi thẳng. Đường chính
    từ Đợt 2 là `services/nhan_dien.la_tin_da_goi` — nó cộng thêm mẫu admin khai
    ở màn Cài đặt và cho chèn từ lạ giữa các từ của mẫu. Giữ hàm này để module
    text vẫn tự chạy được (test đơn, script rời) mà không cần chạm DB.
    """
    if khop_bat_ky(MAU_CHAN_GOI, noi_dung):
        return False
    return khop_bat_ky(MAU_DA_GOI, noi_dung) is not None
