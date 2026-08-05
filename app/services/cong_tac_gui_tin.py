"""Công tắc gửi tin ra ngoài — BA trạng thái, HAI lớp khoá (Đợt 2, mẫu Kallet
`cai-dat.php?sec=msg`).

Vì sao không phải một ô bật/tắt:

    tắt   máy không đụng gì tới hàng đợi gửi
    nháp  chạy ĐỦ quy trình — chọn tệp, dựng nội dung, ghi việc — nhưng KHÔNG
          tin nào rời hệ thống và khách KHÔNG bị đánh dấu "đã gửi"
    thật  tin bay tới khách thật

"Nháp" là trạng thái làm việc thật sự, không phải nửa vời: nó cho phép diễn tập
cả chiến dịch trên dữ liệu thật rồi soi lại kết quả trước khi bấm thật. Gộp nó
vào "tắt" là bỏ mất bước duy nhất bắt được lỗi trước khi tin ra ngoài.

HAI LỚP KHOÁ, phải mở cả hai máy mới gửi thật:

    1. Khoá cứng `outbound_hard_lock` — CHỈ có trong `.env`, không bày lên web.
       Còn đóng thì bấm nút trên màn Cài đặt cũng không gửi được, kể cả tài
       khoản admin bị chiếm. Mở lớp này phải vào được máy chủ.
    2. Chế độ ở màn Cài đặt — cần quyền `gui_tin.bat_cong_tac` (quyền RIÊNG,
       không đi kèm `user.manage`: sửa nhịp worker là chuyện thường ngày, còn
       bật gửi tin thật là quyết định không thu hồi được).

Tin đã ra khỏi hệ thống thì không rút lại được, nên mọi cửa ở đây đều đóng theo
mặc định và mở thì phải cố ý.
"""

from app.core import runtime_config
from app.core.config import settings
from app.core.errors import ApiError

MA = "outbound_messaging_mode"

# mã → (nhãn, icon, câu giải thích ngắn cho người bấm nút)
CHE_DO: dict[str, tuple[str, str, str]] = {
    "tat":  ("TẮT", "⏹️", "Máy không đụng tới hàng đợi gửi tin."),
    "nhap": ("Nháp", "📝", "Chạy đủ quy trình, không tin nào rời hệ thống."),
    "that": ("THẬT", "🔴", "Tin bay tới khách thật — không thu hồi được."),
}


def khoa_cung() -> bool:
    """Lớp 1. True = ĐÓNG. Chỉ `.env` đổi được, web thì không."""
    return bool(getattr(settings, "outbound_hard_lock", True))


def che_do() -> str:
    """Lớp 2. Trả về mã chế độ ĐANG ĐẶT (chưa xét khoá cứng).

    Đọc thêm khoá cũ `outbound_messaging_enabled` để bản cài đặt sẵn có không
    lặng lẽ tụt về "tắt" sau khi nâng cấp: ai đã bật công tắc bool ngày trước
    thì nay là "thật".
    """
    gt = str(runtime_config.chuoi(MA, "") or "").strip().lower()
    if gt in CHE_DO:
        return gt
    return "that" if runtime_config.bat("outbound_messaging_enabled") else "tat"


def gui_that() -> bool:
    """Câu hỏi DUY NHẤT mọi nơi gửi tin phải hỏi: có được bắn ra ngoài không?"""
    return che_do() == "that" and not khoa_cung()


def dien_giai() -> dict:
    """Gói trạng thái cho màn Cài đặt — một nguồn, khỏi để view tự suy lại."""
    ma = che_do()
    nhan, icon, mo_ta = CHE_DO[ma]
    khoa = khoa_cung()
    return {
        "ma": ma, "nhan": nhan, "icon": icon, "mo_ta": mo_ta,
        "khoa_cung": khoa, "gui_that": gui_that(),
        # Vì sao KHÔNG gửi thật, nói thẳng ra thay vì để người dùng đoán.
        "vi_sao": ("Khoá cứng hệ thống đang ĐÓNG — sửa `OUTBOUND_HARD_LOCK=false` "
                   "trong .env rồi khởi động lại mới mở được lớp này."
                   if khoa and ma == "that"
                   else "" if ma == "that" else mo_ta),
    }


def dat_che_do(ma: str, *, actor: dict | None = None) -> str:
    """Đổi chế độ. Gọi thẳng `cai_dat_service` để lượt đổi vào Nhật ký cấu hình
    kèm giá trị CŨ → MỚI như mọi cài đặt khác."""
    from app.services import cai_dat_service

    ma = (ma or "").strip().lower()
    if ma not in CHE_DO:
        raise ApiError("VALIDATION_ERROR",
                       f"Chế độ gửi tin không hợp lệ: {ma!r}. "
                       f"Chọn một trong {', '.join(CHE_DO)}.")
    cai_dat_service.dat(MA, ma, actor=actor)
    return ma


# ------------------------------------------------------------------ cửa của Meta
# Meta chia khách thành 3 cửa; cửa nào tắt thì máy không gửi và dòng khách đó
# hiện KHOÁ kèm lời giải thích, chứ không im lặng bỏ qua.
CUA: tuple[tuple[str, str, str], ...] = (
    ("meta_door_24h_on", "Cửa 24 giờ — khách tự nhiên",
     "24 giờ kể từ tin nhắn cuối của khách — gõ tay tự do, gửi gì cũng được."),
    ("meta_door_ads_on", "Cửa 7 ngày — khách từ quảng cáo",
     "7 ngày kể từ lần bấm quảng cáo cuối; khách bấm lại thì làm mới 7 ngày."),
    ("meta_door_out_on", "Ngoài cửa — chỉ mẫu Meta đã duyệt",
     "Hết cả 24 giờ và 7 ngày — chỉ gửi được kịch bản có mẫu Meta đã duyệt."),
)


def cua_mo(ma: str) -> bool:
    return bool(runtime_config.bat(ma))


# ==================================================================== CỬA GỬI
# Mọi đường bắn tin HÀNG LOẠT đi qua `xin_phep_gui()`. Có một cửa duy nhất thì
# thêm một nguồn gửi mới là phải khai ở đây — không lỡ tay dựng được đường thứ
# hai đi vòng qua các lớp khoá.
#
# LUẬT KHÁC NHAU THEO NGUỒN, vì hậu quả khác nhau thật:
#
#   tay         Nhân viên đang ngồi trả lời một khách trong hội thoại đang mở.
#               KHÔNG gác ở đây. Gác thì bật công tắc an toàn của chiến dịch
#               lên là cả phòng Sale không trả lời được khách — một người gõ
#               sai một tin thì xin lỗi một khách, đó là rủi ro thường ngày của
#               nghề, không phải thứ cần khoá cứng.
#   chien_dich  Người dựng tệp rồi bấm Chạy đợt. Cần khoá cứng MỞ + chế độ THẬT.
#   auto_flow   MÁY tự bắn theo luật, không ai bấm nút. Khoá cứng RIÊNG, tách
#               khỏi khoá trên: mở đường gửi tay/chiến dịch không được kéo theo
#               việc máy tự chạy. Một luật sai thì sai với cả chục nghìn khách
#               trong một đêm, và không ai kịp nhận ra trước khi tin bay hết.
NGUON: dict[str, str] = {
    "tay": "nhân viên bấm gửi ở màn Hội thoại",
    "chien_dich": "chiến dịch C3 — người dựng tệp rồi bấm Chạy đợt",
    "auto_flow": "luồng tự động — máy tự bắn theo luật",
}


class KhongDuocGui(RuntimeError):
    """Xin phép gửi bị TỪ CHỐI. Cố ý là một lớp Exception riêng: nơi gọi phải
    xử lý tường minh chứ không lẫn vào `except Exception` chung."""

    def __init__(self, ly_do: str):
        super().__init__(ly_do)
        self.ly_do = ly_do


def auto_flow_khoa_cung() -> bool:
    """Khoá cứng RIÊNG của luồng tự động. Mặc định ĐÓNG, chỉ `.env` mở được."""
    return bool(getattr(settings, "auto_flow_hard_lock", True))


def xin_phep_gui(nguon: str) -> None:
    """Cửa DUY NHẤT. Không được gửi thì NÉM `KhongDuocGui` kèm lý do đọc được.

    Ném chứ không trả False: bỏ quên một `if` là tin bay ra ngoài, còn bỏ quên
    một `except` thì cùng lắm là báo lỗi. Chọn hướng hỏng an toàn.
    """
    if nguon not in NGUON:
        raise KhongDuocGui(
            f"Nguồn gửi lạ {nguon!r} — chưa khai trong `NGUON`. Mọi đường gửi "
            "phải khai ở đây trước, không có cửa sau.")

    # Gửi TAY không gác ở đây — xem lý do ở bảng `NGUON`.
    if nguon == "tay":
        return

    # Luồng tự động: KHOÁ TRƯỚC, xét sau. Đợt 3 CỐ Ý mới dựng khung — engine
    # chỉ chạy khô để soi luật, chưa có mã gọi API nào. Mở khoá này cũng chưa
    # gửi được gì; nó đứng đây để ngày viết đường gửi thật thì đã có sẵn chốt.
    if nguon == "auto_flow" and auto_flow_khoa_cung():
        raise KhongDuocGui(
            "Luồng tự động đang bị KHOÁ CỨNG (AUTO_FLOW_HARD_LOCK trong .env). "
            "Đây là chốt riêng, độc lập với công tắc gửi tin thường: engine chỉ "
            "chạy khô để xem luật trúng ai, không tin nào rời hệ thống.")

    if khoa_cung():
        raise KhongDuocGui(
            "Khoá cứng hệ thống đang ĐÓNG (OUTBOUND_HARD_LOCK trong .env).")
    ma = che_do()
    if ma != "that":
        raise KhongDuocGui(
            f"Chế độ gửi tin đang là «{CHE_DO[ma][0]}» — "
            + ("đang diễn tập, không tin nào rời hệ thống."
               if ma == "nhap" else "máy không đụng tới hàng đợi gửi."))


def duoc_gui(nguon: str) -> bool:
    """Bản hỏi-không-ném, cho giao diện hiện trạng thái. KHÔNG dùng để gác
    đường gửi — gác thì phải `xin_phep_gui()` (xem lý do ở trên)."""
    try:
        xin_phep_gui(nguon)
    except KhongDuocGui:
        return False
    return True


def vi_sao_khong_gui(nguon: str) -> str:
    """Câu giải thích cho màn hình. Rỗng = đang gửi được."""
    try:
        xin_phep_gui(nguon)
    except KhongDuocGui as err:
        return err.ly_do
    return ""
