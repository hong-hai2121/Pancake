"""Seed danh mục nghiệp vụ từ BRD (mục 7, 8, 14) — chạy song song với A2, khác bảng.

Nạp vào schema `crm`:
  1. Pipeline "Bán mới" + 13 giai đoạn        (BRD mục 7 — Kanban màn 11)
  2. lead_reasons — 9 lý do chưa mua           (màn 16 + BRD mục 8)
  3. ref_codes — các bộ mã BRD mục 14:
       cskh_state  C01-C09   trạng thái pipeline CSKH (bảng 17)
       care_step   CS01-CS11 quy trình chăm 11 bước   (bảng 18, khớp CHECK
                             của care_plan_steps.step_code)
       care_result RS01-RS12 kết quả chuẩn sau mỗi lần chăm (bảng 20)
       automation  AU01-AU13 luật KHI–THÌ (bảng 21 — THAM CHIẾU cho Phần C,
                             chưa phải máy luật chạy được)
       7 bộ giá trị phiếu chăm (bảng 19): adherence_level, diet_compliance,
                             adverse_event, bowel_status, repurchase_readiness,
                             contact_result, next_action

Idempotent: `on conflict ... do update` — chạy lại thì CẬP NHẬT tên/mô tả theo
BRD mới nhất (danh mục là dữ liệu chuẩn, nguồn sự thật là BRD chứ không phải DB).

Chạy:  python scripts/seed_danh_muc.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import get_pg_pool  # noqa: E402

# ============================================================
# 1. Pipeline Sale — BRD mục 7, thứ tự đúng như dòng "Pipeline: ..."
#    (code, tên, is_closed)
# ============================================================
PIPELINE_SALE = ("ban_moi", "Bán mới", "new_sale")
SALE_STAGES: list[tuple[str, str, bool]] = [
    ("lead_moi",       "Khách tiềm năng mới", False),
    ("chua_lien_he",   "Chưa liên hệ",    False),
    ("da_ket_noi",     "Đã kết nối",      False),
    ("dang_khai_thac", "Đang khai thác",  False),
    ("da_tu_van",      "Đã tư vấn",       False),
    ("da_bao_gia",     "Đã báo giá",      False),
    ("dang_can_nhac",  "Đang cân nhắc",   False),
    ("hen_goi_lai",    "Hẹn gọi lại",     False),
    ("can_bam_duoi",   "Cần bám đuổi",    False),
    ("da_chot",        "Đã chốt",         True),
    ("khong_phu_hop",  "Không phù hợp",   True),
    ("tu_choi",        "Từ chối",         True),
    ("mat_lien_lac",   "Mất liên lạc",    True),
]

# ============================================================
# 2. Lý do chưa mua — bộ lọc màn 16; category theo CHECK của lead_reasons
#    (code, tên, category)
# ============================================================
LEAD_REASONS: list[tuple[str, str, str]] = [
    ("gia_cao",           "Giá cao",                 "price"),
    ("chua_co_tien",      "Chưa có tiền",            "price"),
    ("chua_tin_tuong",    "Chưa tin tưởng",          "trust"),
    ("hoi_nguoi_nha",     "Hỏi người nhà",           "timing"),
    ("dang_dieu_tri_khac","Đang điều trị nơi khác",  "competitor"),
    ("so_tac_dung_phu",   "Sợ tác dụng phụ",         "health"),
    ("khong_dung_doi_tuong","Không đúng đối tượng",  "health"),
    ("khong_nghe_may",    "Không nghe máy",          "other"),
    ("khong_phan_hoi",    "Không phản hồi",          "other"),
]

# ============================================================
# 3. ref_codes — (group, code, name, description, extra)
# ============================================================
REF: list[tuple[str, str, str, str, dict]] = []

# --- cskh_state C01-C09 (BRD bảng 17) ---
for code, ten, vao, ra in [
    ("C01", "Mới bàn giao",              "Đơn đạt điều kiện bàn giao",                              "Đã gán CSKH và tạo việc xác nhận"),
    ("C02", "Chờ xác nhận đơn/nhận hàng","Có đơn mới hoặc đang giao",                               "Đã xác nhận đầy đủ hoặc chuyển xử lý sự cố"),
    ("C03", "Onboarding",                "Khách đã nhận hàng",                                      "Đã gửi cách dùng, kết nối kênh chăm, xác định ngày bắt đầu"),
    ("C04", "Đang sử dụng",              "Có actual_start_date",                                    "Hoàn thành các mốc 4-10-15-20-25"),
    ("C05", "Cần chuyên môn",            "Có phản ứng/nặng hơn/không cải thiện dù dùng đúng",       "Có kết luận chuyên môn"),
    ("C06", "Sắp mua lại",               "Đến ngày 20 hoặc còn ít sản phẩm",                        "Đã chốt, hẹn, từ chối hoặc mất cơ hội"),
    ("C07", "Đã mua lại",                "Có đơn LT2/LT3",                                          "Tạo care plan chu kỳ mới"),
    ("C08", "Tạm mất liên lạc",          "Đủ 2 tin nhắn + 2 cuộc gọi không phản hồi",               "Khách phản hồi hoặc vào tái kích hoạt"),
    ("C09", "Dừng chăm",                 "Khách yêu cầu hoặc điều kiện dừng",                       "Chỉ mở lại khi có đồng ý mới"),
]:
    REF.append(("cskh_state", code, ten, "",
                {"dieu_kien_vao": vao, "dieu_kien_ra": ra}))

# --- care_step CS01-CS11 (BRD bảng 18) — khớp CHECK care_plan_steps.step_code ---
for code, ten, kich_hoat, muc_tieu, kenh, du_lieu, ngoai_le in [
    ("CS01", "Xác nhận đơn",           "Ngay khi Sale lên đơn",               "Kiểm tra khách, liệu trình, tiền, địa chỉ",
     "Gọi",        "order_confirmed, amount_confirmed, address_confirmed, next_contact_at", "3 lần không được → trả Sale/trưởng nhóm"),
    ("CS02", "Nhận hàng & onboarding", "Sau 3-5 ngày gửi hoặc giao thành công","Xác nhận đủ hàng, giới thiệu CSKH, kết nối Zalo, gửi cách dùng",
     "Gọi + Zalo", "received_status, zalo_connected, guidance_sent, care_owner_id",          "Thiếu/lỗi hàng → ticket sự cố"),
    ("CS03", "Xác nhận bắt đầu dùng",  "Sau 2 ngày từ khi nhận",              "Lấy actual_start_date, xử lý trì hoãn",
     "Zalo",       "actual_start_date, not_started_reason, rescheduled_start_date",          "Không dùng/không phản hồi → chuỗi nhắc"),
    ("CS04", "Đánh giá sớm",           "Ngày 4 dùng",                         "Tuân thủ, dung nạp, phân, triệu chứng, ăn uống",
     "Gọi",        "adherence_level, adverse_event, bowel_status, symptom_snapshot, meal_relation", "Phản ứng/nặng → chuyên môn"),
    ("CS05", "Kiểm tra tuân thủ",      "Ngày 10 dùng",                        "Phân biệt dùng sai, ăn sai, phản ứng hay đáp ứng chậm",
     "Zalo/Gọi",   "adherence_level, diet_compliance, adverse_event, symptom_change",        "Dùng đúng không cải thiện → chuyên môn"),
    ("CS06", "Đánh giá đáp ứng",       "Ngày 15 dùng",                        "So sánh từng triệu chứng trước và hiện tại",
     "Gọi",        "score_before, score_current, response_level, consultation_note",         "Nặng hơn/không cải thiện đúng đủ → chuyên môn"),
    ("CS07", "Chuẩn bị mua lại",       "Ngày 20 dùng",                        "Kiểm tra lượng còn, ngày hết, tạo cơ hội mua lại",
     "Gọi + nội dung", "remaining_quantity, estimated_end_date, repurchase_readiness, objection_primary", "Vấn đề chuyên môn → tạm khóa bán lại"),
    ("CS08", "Chốt liệu trình tiếp",   "Ngày 25 dùng",                        "Tổng kết tháng đầu, đề xuất bước tiếp theo",
     "Gọi",        "response_summary, recommendation_id, repurchase_status, followup_at",    "Chưa mua → lý do chuẩn + CS09"),
    ("CS09", "Cứu cơ hội",             "Ngày 28 nếu chưa mua",                "Xác định nguyên nhân cuối và kết thúc có kiểm soát",
     "Gọi",        "lost_reason, objection_evidence, next_action, do_not_contact",           "Yêu cầu dừng → dừng mọi automation"),
    ("CS10", "Chăm LT2",               "Sau giao LT2",                        "2-3 ngày nhận hàng; 7 ngày kiểm tra; 15 ngày đánh giá; 20-25 ngày mua tiếp",
     "Gọi + Zalo", "cycle_no, adherence_level, response_level, next_repurchase_date",        "Phản ứng/không cải thiện → chuyên môn"),
    ("CS11", "Chăm LT3 & duy trì",     "Sau giao LT3",                        "Chăm theo mẫu duy trì, đánh giá kế hoạch lâu dài",
     "Gọi + Zalo", "maintenance_plan, next_review_at, repurchase_status",                    "Không tiếp tục → ghi lý do; yêu cầu dừng → dừng"),
]:
    REF.append(("care_step", code, ten, muc_tieu,
                {"kich_hoat": kich_hoat, "kenh": kenh,
                 "du_lieu_bat_buoc": [s.strip() for s in du_lieu.split(",")],
                 "ngoai_le": ngoai_le}))

# --- care_result RS01-RS12 (BRD bảng 20) — danh mục cho care_plan_steps.result_code ---
for code, ten, dieu_kien, hanh_dong in [
    ("RS01", "Đáp ứng tốt",           "Triệu chứng giảm rõ, dùng đúng, không phản ứng", "Tiếp tục theo lịch; tạo cơ hội mua lại đúng mốc"),
    ("RS02", "Đáp ứng một phần",      "Một số triệu chứng giảm, một số còn",            "Tiếp tục, điều chỉnh hướng dẫn, đánh giá lại"),
    ("RS03", "Chưa rõ đáp ứng",       "Thiếu dữ liệu hoặc dùng chưa đều",               "Sửa tuân thủ; hẹn đánh giá lại"),
    ("RS04", "Không cải thiện",       "Điểm không đổi",                                  "Kiểm tra tuân thủ; dùng đúng thì chuyên môn"),
    ("RS05", "Nặng hơn",              "Điểm tăng hoặc có triệu chứng mới",              "Dừng bán lại; chuyển chuyên môn"),
    ("RS06", "Có phản ứng",           "Khách báo phản ứng",                              "Ghi chi tiết; chuyển chuyên môn"),
    ("RS07", "Không phản hồi",        "Không nghe/không trả lời",                        "Chạy chuỗi 4 lần"),
    ("RS08", "Đã mua lại",            "Có đơn mới",                                      "Đóng cơ hội; tạo care plan mới"),
    ("RS09", "Hẹn mua",               "Có ngày mua cụ thể",                              "Tạo task đúng ngày"),
    ("RS10", "Chưa mua - còn cơ hội", "Có băn khoăn chưa từ chối rõ",                    "Ghi lý do + bằng chứng + lịch tiếp"),
    ("RS11", "Mất cơ hội",            "Từ chối rõ hoặc quá số lần",                      "Đóng cơ hội có lý do"),
    ("RS12", "Dừng liên hệ",          "Khách yêu cầu không làm phiền",                   "Dừng automation và chiến dịch"),
]:
    REF.append(("care_result", code, ten, "",
                {"dieu_kien": dieu_kien, "hanh_dong": hanh_dong}))

# --- automation AU01-AU13 (BRD bảng 21) — tham chiếu cho Phần C ---
for code, khi, thi, uu_tien in [
    ("AU01", "Sale tạo đơn",                          "Tạo việc CS01",                                        "cao"),
    ("AU02", "CS01 gọi 3 lần không được",             "Báo Sale và trưởng nhóm",                              "cao"),
    ("AU03", "Đơn giao thành công",                   "Tạo hồ sơ chăm + CS02",                                "cao"),
    ("AU04", "CS02 xác nhận nhận hàng",               "Tạo CS03 sau 2 ngày",                                  "trung_binh"),
    ("AU05", "Có actual_start_date",                  "Sinh CS04/05/06/07/08 theo ngày 4/10/15/20/25",        "cao"),
    ("AU06", "Có phản ứng hoặc nặng hơn",             "Tạo ticket chuyên môn và khóa bán lại",                "khan"),
    ("AU07", "Ngày 15 không cải thiện + dùng đúng",   "Chuyển chuyên môn",                                    "khan"),
    ("AU08", "Đến ngày 20",                           "Tạo cơ hội mua lại và ngày hết dự kiến",               "trung_binh"),
    ("AU09", "Ngày 25 chưa mua",                      "Bắt buộc lý do + tạo CS09 ngày 28",                    "cao"),
    ("AU10", "Không phản hồi",                        "Chạy 2 tin + 2 gọi",                                   "trung_binh"),
    ("AU11", "Yêu cầu không liên hệ",                 "Dừng mọi automation",                                  "khan"),
    ("AU12", "Nội dung chứa từ cấm",                  "Chặn gửi và yêu cầu duyệt",                            "khan"),
    ("AU13", "Đơn LT2/LT3 giao thành công",           "Tạo care plan duy trì",                                "cao"),
]:
    REF.append(("automation", code, f"{khi} → {thi}", "",
                {"khi": khi, "thi": thi, "uu_tien": uu_tien}))

# --- 7 bộ giá trị phiếu chăm (BRD bảng 19, cột "Giá trị chuẩn") ---
VALUE_SETS: dict[str, list[str]] = {
    "adherence_level":      ["Đúng đủ", "Thiếu liều", "Ngắt quãng", "Chưa dùng", "Không rõ"],
    "diet_compliance":      ["Tốt", "Một phần", "Không thực hiện", "Không rõ"],
    "adverse_event":        ["Không", "Nhẹ", "Vừa", "Nặng", "Chưa rõ"],
    "bowel_status":         ["Bình thường", "Lỏng", "Táo", "Lỏng xen rắn", "Khác"],
    "repurchase_readiness": ["Sẵn sàng", "Cân nhắc", "Chưa sẵn sàng", "Từ chối"],
    "contact_result":       ["Kết nối", "Không nghe", "Sai số", "Hẹn lại", "Từ chối"],
    "next_action":          ["Gọi", "Nhắn", "Gửi nội dung", "Chuyên môn", "Kết thúc"],
}
for group, values in VALUE_SETS.items():
    for i, ten in enumerate(values, 1):
        REF.append((group, f"{group}_{i:02d}", ten, "", {}))


# ============================================================
# 4. symptoms — danh mục triệu chứng tiêu hoá (B5, FR-050 / SYMPTOM-001)
#    (code, tên, nhóm). Dấu hiệu BÁO ĐỘNG (nôn máu, phân đen...) KHÔNG nằm
#    ở đây — chúng thuộc phiếu sàng lọc an toàn (safety_screenings, FR-053).
# ============================================================
SYMPTOMS: list[tuple[str, str, str]] = [
    ("dau_thuong_vi",   "Đau thượng vị",              "dạ dày"),
    ("o_chua",          "Ợ chua",                     "dạ dày"),
    ("o_hoi",           "Ợ hơi",                      "dạ dày"),
    ("o_nong",          "Ợ nóng / nóng rát",          "dạ dày"),
    ("buon_non",        "Buồn nôn",                   "dạ dày"),
    ("non",             "Nôn",                        "dạ dày"),
    ("day_bung",        "Đầy bụng, khó tiêu",         "dạ dày"),
    ("chan_an",         "Chán ăn",                    "dạ dày"),
    ("trao_nguoc_dem",  "Trào ngược về đêm",          "trào ngược"),
    ("nong_rat_hong",   "Nóng rát họng, vướng họng",  "trào ngược"),
    ("ho_dai_dang",     "Ho dai dẳng sau ăn",         "trào ngược"),
    ("dau_bung_quan",   "Đau bụng quặn",              "đại tràng"),
    ("tieu_chay",       "Tiêu chảy",                  "đại tràng"),
    ("tao_bon",         "Táo bón",                    "đại tràng"),
    ("phan_song",       "Phân sống",                  "đại tràng"),
    ("phan_nat",        "Phân nát, không thành khuôn","đại tràng"),
    ("di_ngoai_nhieu",  "Đi ngoài nhiều lần trong ngày", "đại tràng"),
    ("mat_ngu",         "Mất ngủ do triệu chứng",     "tiêu hóa chung"),
    ("met_moi",         "Mệt mỏi kéo dài",            "tiêu hóa chung"),
]


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        # 1. Pipeline Bán mới + 13 giai đoạn ------------------------------
        code, ten, loai = PIPELINE_SALE
        row = conn.execute(
            "insert into crm.pipelines (name, type) values (%s, %s) "
            "on conflict (name) do update set type = excluded.type returning id",
            (ten, loai),
        ).fetchone()
        pid = row["id"]
        for i, (scode, sten, closed) in enumerate(SALE_STAGES, 1):
            conn.execute(
                """
                insert into crm.pipeline_stages (pipeline_id, code, name, sort_order, is_closed)
                values (%s, %s, %s, %s, %s)
                on conflict (pipeline_id, code) do update
                    set name = excluded.name, sort_order = excluded.sort_order,
                        is_closed = excluded.is_closed
                """,
                (pid, scode, sten, i * 10, closed),
            )

        # 2. Lý do chưa mua ----------------------------------------------
        for rcode, rten, cat in LEAD_REASONS:
            conn.execute(
                "insert into crm.lead_reasons (code, name, category) values (%s, %s, %s) "
                "on conflict (code) do update set name = excluded.name, category = excluded.category",
                (rcode, rten, cat),
            )

        # 3. ref_codes ----------------------------------------------------
        for i, (group, rcode, rten, mo_ta, extra) in enumerate(REF, 1):
            conn.execute(
                """
                insert into crm.ref_codes (group_code, code, name, description, extra, sort_order)
                values (%s, %s, %s, %s, %s::jsonb, %s)
                on conflict (group_code, code) do update
                    set name = excluded.name, description = excluded.description,
                        extra = excluded.extra, sort_order = excluded.sort_order
                """,
                (group, rcode, rten, mo_ta, json.dumps(extra, ensure_ascii=False), i),
            )

        # 4. symptoms -----------------------------------------------------
        for scode, sten, nhom in SYMPTOMS:
            conn.execute(
                "insert into crm.symptoms (code, name, group_name) values (%s, %s, %s) "
                "on conflict (code) do update "
                "    set name = excluded.name, group_name = excluded.group_name",
                (scode, sten, nhom),
            )

        # Báo cáo ---------------------------------------------------------
        for cau, nhan in [
            ("select count(*) as n from crm.pipeline_stages where pipeline_id = %s", "giai đoạn Sale"),
            ("select count(*) as n from crm.lead_reasons", "lý do chưa mua"),
            ("select count(*) as n from crm.ref_codes", "mã ref_codes"),
            ("select count(*) as n from crm.symptoms", "triệu chứng"),
        ]:
            n = conn.execute(cau, (pid,) if "%s" in cau else None).fetchone()["n"]
            print(f"  {nhan}: {n}")
    print("Seed danh mục xong.")


if __name__ == "__main__":
    main()
