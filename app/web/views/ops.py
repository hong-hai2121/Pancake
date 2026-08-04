"""Màn 16-17 (bám đuổi) · 57-58 (báo cáo lý do/băn khoăn) · 68 (nhóm & ca) ·
69-71 (automation) · 72 (danh mục dùng chung) · 79 (sao lưu).

Nguyên tắc trung thực áp dụng cho khu này: màn nào hệ thống mới làm được MỘT
PHẦN thì nói thẳng phần nào chưa có và ai làm được gì, thay vì bày ô trống.
Cụ thể: automation hiện chạy CỨNG trong code (worker), chưa có builder Khi-Nếu-Thì
(FR-161 thuộc phần C) — màn 69 vì vậy là bảng THEO DÕI chứ không phải bảng cấu hình.
"""

import time
from html import escape

from app.web.shell import render_shell, stat

from app.web.views.crm import _bang, _dt, _e, _tien

# Automation ĐANG chạy thật trong hệ thống (worker + hook trong service).
# Sửa danh sách này khi thêm/bớt automation — màn 69 đọc từ đây.
AUTOMATION = [
    ("Chia khách tiềm năng cho Sale", "Khách tiềm năng mới về (Pancake/tay)",
     "Chia vòng tròn theo tải + đặt SLA 5'/15'", "B3 · lead_service", "luôn bật"),
    ("Cảnh báo khách tiềm năng quá SLA", "Quá hạn nhận / hạn hành động",
     "Đánh dấu quá hạn, hiện ở Pipeline + Thông báo", "B3 · worker", "luôn bật"),
    ("Báo việc quá hạn", "Việc tới hạn mà chưa đóng",
     "Đánh dấu escalated + audit báo quản lý", "B4 · worker tasks-qua-han", "luôn bật"),
    ("Sinh phiếu bàn giao", "Đơn chuyển 'giao thành công'",
     "Tạo phiếu + hồ sơ chăm + việc onboarding, gán CSKH vòng tròn",
     "B8 · hook order_service", "luôn bật"),
    ("Sinh mốc chăm CS01-CS11", "Bàn giao xong / ghi ngày bắt đầu dùng thật",
     "Sinh mốc đúng ngày 4/10/15/20/25/28", "B9 · care_service", "luôn bật"),
    ("Nhắc mốc chăm tới hạn", "Mốc chăm tới ngày",
     "Chuyển mốc sang 'due' + tạo việc cho CSKH", "B9 · worker care-steps", "luôn bật"),
    ("Mở ca chuyên môn", "Cờ đỏ sàng lọc · phản ứng thuốc · RS04+",
     "Tạo ca + việc khẩn cho Người chuyên môn, CHẶN đề xuất",
     "B5/B9 · consult_service", "luôn bật"),
    ("Tạo cơ hội mua lại", "Phiếu chăm ngày 20",
     "Sinh cơ hội mua lại kèm ngày dự kiến chốt", "B9 · AU08", "luôn bật"),
    ("Quét sinh thông báo", "5 phút/lần",
     "11 loại thông báo cho đúng người phụ trách", "Màn 3 · worker notify-scan",
     "NOTIFY_SCAN_ENABLED"),
    ("Đồng bộ Pancake → CRM", "Poller kéo hội thoại",
     "Tạo/cập nhật khách · hội thoại · thẻ · nhân viên", "B2 · crm_sync",
     "CRM_SYNC_ENABLED"),
    ("Đồng bộ đơn POS", "Poll bù theo nhịp",
     "Kéo đơn + trạng thái + quy nguồn quảng cáo", "B7 · worker pos-orders",
     "POS_SYNC_ENABLED"),
    ("Kéo nội dung tin nhắn", "Hội thoại có tin mới",
     "Đổ tin nhắn đầy đủ về crm.messages", "FR-012 · worker msg-sync",
     "MSG_SYNC_ENABLED"),
    ("Chi phí quảng cáo theo ngày", "6 giờ/lượt",
     "Kéo cây campaign/adset/ad + chi phí", "B-QC · worker ads-cost",
     "ADS_SYNC_ENABLED"),
    ("Chạy lại đồng bộ lỗi", "Hàng đợi lỗi tới hạn",
     "Phát lại từ payload đã lưu, backoff ×3, 5 lần thì bỏ cuộc",
     "Mục 4 · worker sync-retry", "SYNC_RETRY_ENABLED"),
]

# Chuỗi follow-up mẫu ĐANG chạy (màn 71) — mô tả đúng thứ tự hệ thống thực thi
CHUOI_MAU = [
    ("Chuỗi chăm liệu trình 1", "CS01 → CS02 → CS03 → CS04 (ngày 4) → CS05 (10) "
     "→ CS06 (15) → CS07 (20) → CS08 (25) → CS09 (28)",
     "Mốc tính từ ngày BẮT ĐẦU DÙNG thật (FR-102)", "B9 — đang chạy"),
    ("Chuỗi liệu trình 2 và 3", "CS10 → CS11",
     "Sinh khi khách mua tiếp liệu trình sau", "B9 — đang chạy"),
    ("Chuỗi không phản hồi", "Nhắn lần 1 → Gọi lần 1 → Nhắn lần 2 → Gọi lần 2 "
     "→ tạm mất liên lạc (C08)", "Sai thứ tự kênh là hệ thống chặn (FR-110)",
     "B9 — đang chạy"),
    ("Chuỗi khách chưa mua (ngày 0/1/3/7/14/30)", "—",
     "FR-070: chuỗi bám đuổi tự động sau báo giá", "CHƯA có engine — thuộc phần C"),
    ("Chuỗi khách ngủ / tái kích hoạt", "—",
     "FR-123: chiến dịch tái kích hoạt khách 30/60/90/180 ngày",
     "B10 có màn khách ngủ; chuỗi tự động thuộc phần C"),
]


def _dem_qua_hen(rows: list[dict]) -> int:
    bay_gio = time.time()
    return sum(1 for r in rows
               if r.get("next_action_at")
               and r["next_action_at"].timestamp() < bay_gio)


# ------------------------------------------------------------- màn 16
def render_bam_duoi(rows: list[dict], ly_do: list[dict], loc: int) -> str:
    chip = (f'<a class="btn sm{"" if loc else " primary"}" '
            'href="/crm/bam-duoi">Tất cả</a> ')
    for r in ly_do:
        on = " primary" if loc == r["id"] else ""
        chip += (f'<a class="btn sm{on}" href="/crm/bam-duoi?ly_do={r["id"]}">'
                 f'{escape(r["name"])}</a> ')
    dong = ""
    for r in rows:
        dong += (
            f'<tr><td><a href="/crm/khach-hang/{r["customer_id"]}">'
            f'<b>{_e(r["full_name"])}</b></a>'
            f'<div class="note">{_e(r["primary_phone"])}</div></td>'
            f"<td>{_e(r['sale_name'])}</td><td>{_e(r['stage_name'])}</td>"
            f"<td>{_e(r['ly_do'])}</td>"
            f"<td>{_e(r['temperature'])}</td><td>{r['so_cham']}</td>"
            f"<td>{_dt(r['cham_cuoi'])}</td><td>{_dt(r['next_action_at'])}</td>"
            f'<td><a class="btn sm" href="/crm/bam-duoi/{r["customer_id"]}">Chuỗi</a> '
            f'<a class="btn sm" href="/crm/tu-van/{r["customer_id"]}">Tư vấn</a></td>'
            "</tr>"
        )
    body = (
        '<div class="stats">'
        + stat("Khách đang cần bám", str(len(rows)),
               tone="warn" if rows else "")
        + stat("Đã quá hẹn hành động", str(_dem_qua_hen(rows)), tone="err")
        + "</div>"
        + f'<div style="margin:14px 0 10px">{chip}</div>'
        + _bang(["Khách", "Sale", "Giai đoạn", "Lý do chưa mua", "Nhiệt",
                 "Số lần chạm", "Chạm cuối", "Hẹn kế tiếp", ""], dong,
                "Không có khách tiềm năng nào đang mở")
        + '<p class="note" style="margin-top:8px">Lý do chưa mua ghi ở màn tư vấn / '
          "khi đóng hồ sơ khách tiềm năng. Chuỗi bám đuổi TỰ ĐỘNG theo mốc ngày "
          "0/1/3/7/14/30 (FR-070) "
          "chưa có engine — hiện bám bằng công việc thủ công (B4).</p>"
    )
    return render_shell("Bám đuổi", "crm-pipeline", body,
                        heading="Khách chưa mua cần bám đuổi",
                        sub="Màn 16 — lọc theo lý do chưa mua")


# ------------------------------------------------------------- màn 17
def render_chuoi_bam_duoi(kh: dict, d: dict) -> str:
    cham = "".join(
        f"<tr><td>{_dt(r['completed_at'] or r['due_at'])}</td>"
        f"<td>{_e(r['task_type'])}</td><td>{_e(r['title'])}</td>"
        f"<td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{_e(r['result'])}</td><td>{_e(r['nguoi'])}</td></tr>"
        for r in d["cham"]
    )
    chuoi = "".join(
        f"<tr><td>#{r['id']}</td><td><span class='pill'>{_e(r['status'])}</span></td>"
        f"<td>{r['so_lan']}/4</td><td>{_dt(r['started_at'])}</td>"
        f"<td>{_dt(r.get('closed_at'))}</td></tr>"
        for r in d["chuoi"]
    )
    body = (
        '<p style="margin-bottom:10px">'
        '<a class="btn sm" href="/crm/bam-duoi">← Danh sách</a> '
        f'<a class="btn sm" href="/crm/khach-hang/{kh["id"]}">Hồ sơ 360°</a> '
        f'<a class="btn sm primary" href="/crm/tu-van/{kh["id"]}">Tư vấn</a></p>'
        '<div class="card" style="margin-bottom:14px">'
        f"<h3 style='margin:0'>{_e(kh['full_name'])}</h3>"
        f"<p class='note' style='margin:4px 0 0'>SĐT {_e(kh['primary_phone'])} · "
        f"chi tiêu {_tien(kh.get('tong_chi_tieu'))}</p></div>"
        + '<div class="card"><h3>Các lần chạm đã thực hiện</h3>'
        + _bang(["Lúc", "Kênh/loại", "Nội dung", "Trạng thái", "Kết quả", "Người"],
                cham, "Chưa có lần chạm nào được ghi")
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Chuỗi không phản hồi (nhắn → gọi → nhắn → gọi)</h3>"
        + _bang(["Chuỗi", "Trạng thái", "Số lần chạm", "Bắt đầu", "Đóng"], chuoi,
                "Khách chưa vào chuỗi không phản hồi nào")
        + "</div>"
    )
    return render_shell(f"Chuỗi bám đuổi {kh['full_name']}", "crm-pipeline", body,
                        heading="Chi tiết chuỗi bám đuổi",
                        sub="Màn 17 — từng lần chạm: thời gian · kênh · kết quả")


# ------------------------------------------------------------- màn 57-58
def render_bao_cao_ly_do(d: dict, tu: str, den: str) -> str:
    tong = d["tong"] or 1
    ly_do = "".join(
        f"<tr><td>{_e(r['name'])}</td><td>{r['n']}</td>"
        f"<td>{r['n'] * 100 // tong}%</td>"
        f'<td><div style="background:var(--accent);height:10px;border-radius:5px;'
        f'width:{max(2, r["n"] * 100 // tong)}%"></div></td></tr>'
        for r in d["theo_ly_do"]
    )
    sale = "".join(
        f"<tr><td>{_e(r['sale'])}</td><td>{_e(r['ly_do'])}</td><td>{r['n']}</td></tr>"
        for r in d["theo_sale"]
    )
    ad = "".join(
        f"<tr><td>{_e(r['quang_cao'])}</td><td>{_e(r['ly_do'])}</td>"
        f"<td>{r['n']}</td></tr>"
        for r in d["theo_ad"]
    )
    body = (
        '<form class="card form" method="get" style="margin-bottom:14px">'
        '<div class="grid2">'
        f'<label>Từ ngày<input type="date" name="tu" value="{escape(tu)}"></label>'
        f'<label>Đến ngày<input type="date" name="den" value="{escape(den)}"></label>'
        "</div><button class='btn primary' style='margin-top:8px'>Lọc</button></form>"
        + '<div class="stats">'
        + stat("Tổng lượt ghi lý do", str(d["tong"]))
        + stat("Số nhóm lý do", str(len(d["theo_ly_do"])))
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Tỷ trọng lý do chưa chốt (màn 58)</h3>"
        + _bang(["Lý do", "Số lượt", "Tỷ trọng", ""], ly_do,
                "Chưa có khách tiềm năng nào được ghi lý do chưa mua — Sale ghi "
                "ở màn tư vấn hoặc khi đóng hồ sơ")
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Băn khoăn theo Sale (màn 57)</h3>"
        + _bang(["Sale", "Lý do / băn khoăn", "Số lượt"], sale, "Chưa có dữ liệu")
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Băn khoăn theo quảng cáo (chạm cuối)</h3>"
        + _bang(["Quảng cáo", "Lý do / băn khoăn", "Số lượt"], ad,
                "Chưa quy được nguồn cho khách tiềm năng có lý do")
        + '<p class="note" style="margin-top:8px">Bấm sang '
          '<a href="/crm/quang-cao">Nguồn quảng cáo</a> để xem chi phí/ROAS của '
          "từng quảng cáo trong bảng này.</p></div>"
    )
    return render_shell("Báo cáo lý do chưa chốt", "crm-ads", body,
                        heading="Băn khoăn & lý do chưa chốt",
                        sub="Màn 57 + 58 — theo lý do · theo Sale · theo quảng cáo")


# ------------------------------------------------------------- màn 69 + 71
def render_automation() -> str:
    dong = "".join(
        f"<tr><td><b>{escape(ten)}</b></td><td>{escape(khi)}</td>"
        f"<td>{escape(thi)}</td><td class='note'>{escape(o_dau)}</td>"
        f"<td><span class='pill {'ok' if ct == 'luôn bật' else ''}'>"
        f"{escape(ct)}</span></td></tr>"
        for ten, khi, thi, o_dau, ct in AUTOMATION
    )
    chuoi = "".join(
        f"<tr><td><b>{escape(ten)}</b></td><td>{escape(buoc)}</td>"
        f"<td>{escape(ghi)}</td>"
        f"<td><span class='pill {'ok' if 'đang chạy' in tt else 'warn'}'>"
        f"{escape(tt)}</span></td></tr>"
        for ten, buoc, ghi, tt in CHUOI_MAU
    )
    body = (
        '<div class="flash warn" style="margin-bottom:14px">ℹ️ Hệ thống hiện chạy '
        "automation <b>cứng trong code</b> (worker + hook trong service) — chắc chắn "
        "và có kiểm thử. <b>Trình tạo Khi–Nếu–Thì</b> cho người dùng tự dựng luật "
        "(FR-161, màn 70) thuộc giai đoạn sau. Màn này là bảng THEO DÕI: automation "
        "nào đang chạy, kích hoạt bởi gì, làm gì, bật/tắt ở đâu.</div>"
        + '<div class="card"><h3>Automation đang chạy (màn 69)</h3>'
        + _bang(["Tên luật", "KHI (kích hoạt)", "THÌ (hành động)", "Nằm ở", "Công tắc"],
                dong, "")
        + '<p class="note" style="margin-top:8px">Công tắc bật/tắt được ở '
          '<a href="/quan-tri/cai-dat">Cài đặt hệ thống</a>; lỗi chạy xem ở '
          '<a href="/quan-tri/tich-hop/loi">Hàng đợi lỗi</a>.</p></div>'
        + '<div class="card" style="margin-top:14px">'
          "<h3>Mẫu chuỗi follow-up (màn 71)</h3>"
        + _bang(["Chuỗi", "Các bước", "Ghi chú", "Tình trạng"], chuoi, "")
        + "</div>"
    )
    return render_shell("Automation", "crm-tasks", body,
                        heading="Automation & chuỗi follow-up",
                        sub="Màn 69 + 71 — theo dõi luật tự động đang chạy")


# ------------------------------------------------------------- màn 72
def render_danh_muc(nhom: list[dict], dang_xem: str, muc: list[dict],
                    ok_msg: str = "", error: str = "") -> str:
    chip = ""
    for n in nhom:
        on = " primary" if n["group_code"] == dang_xem else ""
        chip += (f'<a class="btn sm{on}" href="/crm/danh-muc?nhom={n["group_code"]}">'
                 f'{escape(n["group_code"])} · {n["n"]}</a> ')
    dong = ""
    for r in muc:
        tat = r["status"] != "active"
        nut = ("dùng lại" if tat else "ngừng dùng")
        # Python 3.11: KHÔNG đặt backslash/nháy lồng trong biểu thức f-string
        mo = ' style="opacity:.5"' if tat else ""
        dong += (
            f"<tr{mo}>"
            f"<td><code>{_e(r['code'])}</code></td><td>{_e(r['name'])}</td>"
            f"<td>{_e(r['description'])}</td><td>{r['sort_order']}</td>"
            f"<td><span class='pill {'' if tat else 'ok'}'>{_e(r['status'])}</span></td>"
            f'<td><form method="post" action="/crm/danh-muc/{r["id"]}/trang-thai">'
            f'<input type="hidden" name="status" value="{"active" if tat else "inactive"}">'
            f'<button class="btn sm">{nut}</button></form></td></tr>'
        )
    flash = ""
    if ok_msg:
        flash = f'<div class="flash ok" style="margin-bottom:14px">{escape(ok_msg)}</div>'
    if error:
        flash = f'<div class="flash err" style="margin-bottom:14px">{escape(error)}</div>'

    body = (
        flash
        + '<p class="note">Danh mục dùng chung: trạng thái khách · lý do chưa mua · '
          "băn khoăn · triệu chứng · kết quả chăm · mức cải thiện · loại việc… "
          "Cột nghiệp vụ tra giá trị hợp lệ ở đây thay vì khoá cứng trong DB, nên "
          "<b>thêm giá trị mới không phải sửa code</b>.</p>"
        + f'<div style="margin:14px 0 10px">{chip}</div>'
        + _bang(["Mã", "Tên", "Mô tả", "Thứ tự", "Trạng thái", ""], dong,
                "Chọn một nhóm ở trên để xem các mã")
        + ('<form class="card form" method="post" action="/crm/danh-muc" '
           'style="margin-top:14px"><h3>Thêm mã mới</h3><div class="grid2">'
           f'<label>Nhóm<input type="text" name="group_code" value="{escape(dang_xem)}" '
           "required></label>"
           '<label>Mã<input type="text" name="code" required '
           'placeholder="vd GIA_CAO"></label>'
           '<label>Tên hiển thị<input type="text" name="name" required></label>'
           '<label>Thứ tự<input type="number" name="sort_order" value="0"></label>'
           "</div><button class='btn primary' style='margin-top:10px'>➕ Thêm</button>"
           "</form>")
        + '<p class="note" style="margin-top:10px">Mã đã dùng thì <b>ngừng dùng</b> '
          "chứ không xoá — dữ liệu cũ còn tham chiếu tới nó.</p>"
    )
    return render_shell("Danh mục dùng chung", "admin", body,
                        heading="Danh mục dùng chung",
                        sub="Màn 72 — bộ mã dùng chung toàn hệ thống")


# ------------------------------------------------------------- màn 68
def render_nhom_ca(nhom: list[dict], chua_nhom: list[dict]) -> str:
    khoi = ""
    for n in nhom:
        tv = "".join(
            f"<tr><td>{_e(u['name'])}</td><td>{_e(u['vai_tro'])}</td>"
            f"<td>{_e(u['status'])}</td></tr>" for u in n["thanh_vien"])
        khoi += (
            '<div class="card" style="margin-top:14px">'
            f"<h3>{_e(n['name'])} <span class='pill'>{_e(n['department'])}</span></h3>"
            f"<p class='note'>Trưởng nhóm: <b>{_e(n['manager_name'])}</b> · "
            f"{n['so_nguoi']} thành viên</p>"
            + _bang(["Thành viên", "Vai trò", "Trạng thái"], tv, "Nhóm chưa có ai")
            + "</div>"
        )
    le = "".join(
        f"<tr><td>{_e(u['name'])}</td><td>{_e(u['vai_tro'])}</td></tr>"
        for u in chua_nhom)
    body = (
        '<div class="stats">'
        + stat("Số nhóm", str(len(nhom)))
        + stat("Chưa vào nhóm", str(len(chua_nhom)),
               tone="warn" if chua_nhom else "")
        + "</div>"
        + khoi
        + '<div class="card" style="margin-top:14px"><h3>Chưa vào nhóm nào</h3>'
        + _bang(["Nhân viên", "Vai trò"], le, "Mọi người đều đã có nhóm")
        + "</div>"
        + '<div class="card" style="margin-top:14px">'
          "<h3>Quy tắc chia khách tiềm năng</h3>"
          "<p>Khách tiềm năng mới chia <b>vòng tròn theo tải</b>: ai đang giữ ít "
          "hồ sơ đang mở nhất thì nhận trước (không phải chia đều theo lượt). "
          "Không ai đủ điều kiện thì hồ sơ nằm ở <b>hàng đợi</b> chờ trưởng nhóm "
          "gán tay.</p>"
          '<p class="note">Ca trực theo khung giờ (FR-031) chưa cấu hình được trên '
          "web — hiện chia không phân biệt ca. Tạo/sửa nhóm ở "
          '<a href="/quan-tri/phan-quyen">Vai trò &amp; phân quyền</a>.</p></div>'
    )
    return render_shell("Nhóm & ca làm việc", "admin", body,
                        heading="Phân nhóm và ca làm việc",
                        sub="Màn 68 — nhóm · trưởng nhóm · quy tắc chia khách tiềm năng")
