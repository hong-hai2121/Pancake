"""Seed THANG BAM DUOI SALE — 8 buoc (C5, port mau Kallet sale_buoc.php).

Thang mau Kallet viet cho nganh do lot; bo duoi day viet lai cho nganh THUC
PHAM CHUC NANG TIEU HOA (dung nganh cua du an nay). Sua tren web o man
/crm/thang-sale cho khop giong dieu that.

⚠️ CAI BAY NGON NGU — mau da do tren 53.000 tin that roi moi chot:
   May BO DAU truoc khi so, nen tu DON hay dung nhau. Vi du co that:
     "dat"  <- ca "đắt" LAN "đặt hàng"   (619 tin sai)
     "mac"  <- ca "mắc"  LAN "mặc"
   ⇒ TU KHOA PHAI LA CUM NHIEU CHU. Khai "đắt quá", "sao đắt" —
     TUYET DOI dung khai moi chu "đắt".

Ba tu MAY TU HIEU (do tren nguyen van, khong bo dau):
   #anh — tin co anh · #gia — tin co so tien · #ma — tin co ma giam

Cot 4 = tu khoa NHAN VIEN noi  ⇒ coi nhu da lam buoc do.
Cot 5 = tu khoa KHACH noi      ⇒ NHAY COC thang toi buoc do.
   Buoc 1 va buoc cuoi CO Y de trong cot 5 (khong nhay coc duoc).

Idempotent: `on conflict (step_no) do update` — chay lai thi cap nhat theo file.

Chay:  python scripts/seed_thang_sale.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool  # noqa: E402

# (so buoc, ten, viec can lam, tu khoa NV noi, tu khoa KHACH noi)
THANG: list[tuple[int, str, str, str, str]] = [
    (1, "Chào + hỏi triệu chứng",
     "Chào khách, hỏi đang gặp vấn đề tiêu hoá gì",
     "chào chị, chào anh, em hỗ trợ, mình đang bị sao, triệu chứng thế nào, "
     "bị bao lâu rồi, đau ở đâu, em tư vấn giúp",
     ""),
    (2, "Báo giá + liệu trình",
     "Gửi bảng giá và liệu trình phù hợp",
     "#gia, bảng giá, giá bên em, chi phí liệu trình, liệu trình 1 tháng, "
     "liệu trình 2 tháng, hộp dùng được, giá gốc",
     "bao nhiêu tiền, giá thế nào, giá bao nhiêu, hết bao nhiêu, chi phí sao"),
    (3, "Feedback + gỡ rủi ro",
     "Gửi phản hồi khách cũ, giấy kiểm nghiệm, chính sách đổi trả",
     "#anh, phản hồi của khách, khách bên em, feedback, kiểm nghiệm, "
     "giấy phép, bộ y tế, cam kết, hoàn tiền, đổi trả, hàng chính hãng",
     "có uy tín không, hàng thật không, có giấy tờ không, ai dùng chưa, "
     "review thế nào, sợ hàng giả"),
    (4, "Trấn an an toàn",
     "Giải thích thành phần, tác dụng phụ, tương tác thuốc",
     "thành phần gồm, thảo dược, không tác dụng phụ, lành tính, "
     "đang uống thuốc gì, có bệnh nền không, hỏi lại chuyên môn",
     "có hại không, tác dụng phụ, nóng trong không, đang uống thuốc, "
     "có bầu dùng được, cho con bú"),
    (5, "Hỏi lý do phân vân",
     "Hỏi khách còn băn khoăn gì — xử lý từ chối",
     "băn khoăn, phân vân, lăn tăn, chị thấy sao ạ, chưa ưng chỗ nào, "
     "còn điều gì, vì sao ạ",
     "để em nghĩ, để em xem, suy nghĩ đã, tính sau, từ từ đã, chưa quyết"),
    (6, "Gửi mã giảm giá",
     "Gửi mã giảm riêng cho khách",
     "#ma, mã giảm, giảm giá, voucher, ưu đãi riêng, tặng chị mã, "
     "combo tiết kiệm",
     "đắt quá, đắt thế, sao đắt, giá cao, bớt được không, giảm được không, "
     "có mã không, có khuyến mãi không"),
    (7, "Nhắc ưu đãi có hạn",
     "Nhắc mã sắp hết hạn — tạo lý do chốt",
     "hết hạn, sắp hết, còn hôm nay, hạn cuối, áp dụng đến, chỉ còn suất",
     "để mai, cuối tháng, khi nào có lương, tháng sau, đợi đã"),
    (8, "Nhắc trước khi buông",
     "Nhắn câu cuối trước khi dừng bám đuổi",
     "không làm phiền, lần cuối, khi nào cần, chị cần thì nhắn, em vẫn ở đây",
     ""),
]


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        for so, ten, viec, kw_nv, kw_kh in THANG:
            conn.execute(
                """
                insert into crm.sale_steps
                       (step_no, name, work, keywords_agent, keywords_customer)
                values (%s, %s, %s, %s, %s)
                on conflict (step_no) do update set
                    name = excluded.name, work = excluded.work,
                    keywords_agent = excluded.keywords_agent,
                    keywords_customer = excluded.keywords_customer,
                    status = 'active'
                """,
                (so, ten, viec, kw_nv, kw_kh),
            )
        n = conn.execute("select count(*) as n from crm.sale_steps "
                         "where status = 'active'").fetchone()["n"]
        print(f"  buoc dang dung: {n}")
    # In KHONG dau va khong emoji: console Windows dung cp1252.
    print("Seed thang bam duoi xong.")
    print("!! NHO DAT 'Ngay bat thang' o Cai dat -> Thang bam duoi Sale.")
    print("   Bo do CHI doc tin TU ngay do. De trong = hom nay (an toan).")
    print("   Lui qua xa = khach nhan qua lai vai thang nhay thang buoc cuoi,")
    print("   'het thang', roi khoi bang viec -> ca bang Sale trong.")


if __name__ == "__main__":
    main()
