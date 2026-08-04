"""Seed THU VIEN KICH BAN + luat goi y (C4 — port mau Kallet kich-ban.php).

Nap bo cau mau toi thieu de man /crm/kich-ban co du lieu that chay ngay, va de
tinh nang "goi y 3 cau theo tu khoa trong tin khach" co gi de goi.

⚠️ Day la THU VIEN CHEP TAY — nap vao day KHONG gui gi cho ai. Noi dung gui
that nam o crm.message_templates (C3, man /crm/mau-tin).

Bo cau duoi la MAU CHUNG cho nganh thuc pham chuc nang tieu hoa; sua/them tren
web cho khop giong dieu that cua cong ty.

Idempotent: xoa het cau co dau `[seed]` roi nap lai — cau nhan vien tu them
tren web KHONG bi dung toi.

Chay:  python scripts/seed_kich_ban.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool          # noqa: E402
from app.services.tieng_viet import chuan_hoa  # noqa: E402

DAU = "[seed] "

# (loai, tinh huong, tieu de, noi dung, the)
KICH_BAN: list[tuple[str, str, str, str, str]] = [
    ("sale", "Khách chê đắt", "Trả lời khách chê đắt",
     "Dạ em hiểu ạ. Sản phẩm bên em giá nhỉnh hơn vì dùng nguyên liệu nhập "
     "khẩu và có kiểm nghiệm đầy đủ. Chị dùng đủ liệu trình sẽ thấy khác biệt "
     "rõ, nhiều khách nhà em cũng băn khoăn giá lúc đầu như chị ạ.",
     "gia,dat,phan-doi"),
    ("sale", "Khách chê đắt", "Chia nhỏ chi phí theo ngày",
     "Dạ liệu trình 1 tháng của bên em tính ra khoảng 20 nghìn/ngày thôi ạ, "
     "bằng một cốc cà phê mà đổi lại chị ăn ngủ ngon hơn ạ.",
     "gia,dat"),
    ("sale", "Khách hỏi công dụng", "Giới thiệu công dụng ngắn gọn",
     "Dạ sản phẩm hỗ trợ giảm đau, giảm trào ngược và bảo vệ niêm mạc dạ dày "
     "ạ. Chị đang gặp triệu chứng gì nhiều nhất để em tư vấn đúng ạ?",
     "cong-dung,tu-van"),
    ("sale", "Khách im lặng", "Nhắc nhẹ khách im lặng",
     "Dạ chị ơi, em vẫn giữ phần tư vấn cho mình nhé. Chị cần em gửi thêm "
     "thông tin gì không ạ?",
     "im-lang,bam-duoi"),
    ("sale", "Khách hẹn mua sau", "Chốt lịch hẹn cụ thể",
     "Dạ vâng ạ. Vậy khoảng ngày mai em nhắn lại cho chị nhé, để em giữ ưu "
     "đãi này cho mình ạ.",
     "hen,chot"),
    ("sale", "Khách sợ tác dụng phụ", "Trấn an về an toàn",
     "Dạ sản phẩm có giấy kiểm nghiệm và công bố đầy đủ ạ. Tuy nhiên nếu chị "
     "đang dùng thuốc điều trị hoặc có bệnh nền thì chị cho em biết để em hỏi "
     "lại bộ phận chuyên môn trước khi tư vấn ạ.",
     "an-toan,tac-dung-phu"),
    ("sau_ban", "Xác nhận đơn", "Gọi xác nhận đơn hàng",
     "Dạ em chào chị, em gọi để xác nhận đơn hàng của mình ạ. Chị cho em xin "
     "địa chỉ nhận hàng chính xác để bên em gửi đi ạ.",
     "xac-nhan,cs01"),
    ("sau_ban", "Hướng dẫn dùng", "Hướng dẫn ngày đầu sử dụng",
     "Dạ chị nhận được hàng rồi ạ. Chị uống trước ăn 30 phút, ngày 2 lần sáng "
     "và tối nhé. Trong quá trình dùng có gì chị cứ nhắn em ạ.",
     "onboarding,huong-dan"),
    ("sau_ban", "Chăm ngày 4", "Hỏi thăm sau 4 ngày dùng",
     "Dạ chị dùng được mấy ngày rồi ạ, chị thấy trong người thế nào? Có bị "
     "đầy bụng hay khó chịu gì không để em ghi nhận ạ?",
     "cham,ngay-4"),
    ("sau_ban", "Khách phản ánh chưa đỡ", "Xử lý khách chưa thấy hiệu quả",
     "Dạ em ghi nhận ạ. Chị cho em hỏi mình dùng có đều không và có kiêng đồ "
     "cay nóng, rượu bia không ạ? Em sẽ nhờ bộ phận chuyên môn xem lại cho "
     "chị ạ.",
     "chua-do,su-co"),
    ("sau_ban", "Mua lại", "Nhắc khách sắp hết liệu trình",
     "Dạ liệu trình của chị sắp hết rồi ạ. Để giữ kết quả thì mình nên dùng "
     "tiếp đợt nữa, bên em đang có ưu đãi cho khách cũ ạ.",
     "mua-lai,nhac"),
    ("sau_ban", "Khách từ chối mua lại", "Ghi nhận khách chưa mua lại",
     "Dạ vâng, em ghi nhận ạ. Khi nào chị cần dùng lại thì nhắn em nhé, em "
     "vẫn giữ ưu đãi khách cũ cho mình ạ.",
     "tu-choi,mua-lai"),
]

# (tu khoa cach nhau dau phay, tieu de kich ban se goi y)
LUAT_GOI_Y: list[tuple[str, str]] = [
    ("dat,mac,gia cao,sao dat the,tien qua", "Trả lời khách chê đắt"),
    ("cong dung,co tac dung gi,chua duoc benh gi", "Giới thiệu công dụng ngắn gọn"),
    ("tac dung phu,co hai khong,an toan khong", "Trấn an về an toàn"),
    ("de suy nghi,de xem da,hen hom sau,mai", "Chốt lịch hẹn cụ thể"),
    ("uong the nao,dung sao,huong dan", "Hướng dẫn ngày đầu sử dụng"),
    ("chua do,khong thay gi,van dau", "Xử lý khách chưa thấy hiệu quả"),
    ("het thuoc,sap het,mua them", "Nhắc khách sắp hết liệu trình"),
]


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        conn.execute("delete from crm.script_suggest_rules where script_id in "
                     "(select id from crm.sale_scripts where title like %s)",
                     (f"{DAU}%",))
        conn.execute("delete from crm.sale_scripts where title like %s",
                     (f"{DAU}%",))
        ma_theo_ten = {}
        for i, (loai, th, tieu_de, noi_dung, the) in enumerate(KICH_BAN):
            r = conn.execute(
                """
                insert into crm.sale_scripts
                       (kind, situation, title, body, body_nodiacritic, tags,
                        sort_order)
                values (%s, %s, %s, %s, %s, %s, %s) returning id
                """,
                (loai, th, DAU + tieu_de, noi_dung, chuan_hoa(noi_dung), the, i),
            ).fetchone()
            ma_theo_ten[tieu_de] = r["id"]
        for tu_khoa, tieu_de in LUAT_GOI_Y:
            sid = ma_theo_ten.get(tieu_de)
            if sid:
                conn.execute(
                    "insert into crm.script_suggest_rules (keywords, script_id)"
                    " values (%s, %s)", (tu_khoa, sid))

        for cau, nhan in [
            ("select count(*) as n from crm.sale_scripts", "cau mau"),
            ("select count(*) as n from crm.script_suggest_rules", "luat goi y"),
        ]:
            print(f"  {nhan}: {conn.execute(cau).fetchone()['n']}")
    print("Seed thu vien kich ban xong. Mo /crm/kich-ban de xem.")


if __name__ == "__main__":
    main()
