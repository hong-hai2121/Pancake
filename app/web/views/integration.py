"""Dựng HTML khu Tích hợp (BRD mục 4) — 4 màn theo đúng danh sách của đặc tả:

    Kết nối          — tài khoản Pancake/POS, tình trạng token, công tắc đồng bộ
    Nhật ký đồng bộ  — mỗi lượt chạy 1 dòng (sync_logs)
    Danh sách lỗi    — hàng đợi retry (sync_errors) + nút thử lại
    Ánh xạ           — Page ↔ kết nối · nhân viên Pancake ↔ nhân viên CRM ·
                       mã trạng thái đơn POS ↔ 11 trạng thái CRM (màn 23)

Chỉ hiển thị — dữ liệu do routes/integration.py đưa vào. MỌI số liệu đọc từ DB
(luật mục 4: không gọi API Pancake mỗi lần mở màn hình); riêng nút "Kiểm tra kết
nối" là người chủ động bấm.
"""

from html import escape

from app.web.shell import flash, render_shell, stat, tabs_bar

_TABS = [
    ("/quan-tri/tich-hop", "Kết nối", "ket-noi"),
    ("/quan-tri/tich-hop/nhat-ky", "Nhật ký đồng bộ", "nhat-ky"),
    ("/quan-tri/tich-hop/loi", "Danh sách lỗi", "loi"),
    ("/quan-tri/tich-hop/anh-xa", "Ánh xạ", "anh-xa"),
]

_TRANG_THAI_LOG = {
    "running": '<span class="pill">đang chạy</span>',
    "success": '<span class="pill ok">xong</span>',
    "partial": '<span class="pill warn">xong, có lỗi</span>',
    "failed": '<span class="pill err">hỏng</span>',
}
_TRANG_THAI_LOI = {
    "pending": '<span class="pill warn">đang chờ</span>',
    "resolved": '<span class="pill ok">đã xong</span>',
    "given_up": '<span class="pill err">bỏ cuộc</span>',
}
_TOKEN = {
    "ok": '<span class="pill ok">token tốt</span>',
    "invalid": '<span class="pill err">token lỗi/hết hạn</span>',
    "missing": '<span class="pill err">thiếu token</span>',
    "unknown": '<span class="pill">chưa kiểm</span>',
}
_ENTITY = {"conversation": "Hội thoại", "order": "Đơn hàng",
           "customer": "Khách", "tag": "Thẻ", "page": "Page"}
_NGUON = {"pancake_pages": "Pancake chat", "pancake_pos": "Pancake POS"}


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _fmt_dt(v) -> str:
    return v.strftime("%d/%m %H:%M:%S") if v else "—"


def _o_loi(n) -> str:
    return f'<b class="err-txt">{n}</b>' if n else "0"


def _shell(title: str, tab: str, body: str, ok: str = "", error: str = "") -> str:
    return render_shell(
        title, "tich-hop", flash(ok, error) + body,
        heading="Tích hợp Pancake",
        sub="Đồng bộ khách · hội thoại · đơn hàng · nguồn quảng cáo (BRD mục 4)",
        tabs=tabs_bar(_TABS, tab),
    )


# ------------------------------------------------------------ tab 1: kết nối
def render_ket_noi(tt: dict, pages: list[dict], *, ok: str = "", error: str = "") -> str:
    cong_tac = tt["cong_tac"]
    canh_bao = tt["canh_bao_token"]

    o_so = (
        # Bấm vào ô công tắc là sang thẳng màn Cài đặt để bật/tắt (không còn phải
        # sửa .env rồi khởi động lại server).
        stat("Đồng bộ hội thoại", "BẬT" if cong_tac["crm_sync_enabled"] else "TẮT",
             "bấm để đổi ở màn Cài đặt",
             tone="ok" if cong_tac["crm_sync_enabled"] else "warn",
             href="/quan-tri/cai-dat")
        + stat("Đồng bộ đơn POS", "BẬT" if cong_tac["pos_sync_enabled"] else "TẮT",
               "bấm để đổi ở màn Cài đặt",
               tone="ok" if cong_tac["pos_sync_enabled"] else "warn",
               href="/quan-tri/cai-dat")
        + stat("Lỗi đang chờ xử lý", str(tt["loi_dang_cho"]),
               "hàng đợi tự thử lại", tone="err" if tt["loi_dang_cho"] else "ok",
               href="/quan-tri/tich-hop/loi")
        + stat("Khách đã quy nguồn", str((tt["quy_nguon"] or {}).get("cham_cuoi") or 0),
               f"{(tt['quy_nguon'] or {}).get('so_ad') or 0} quảng cáo khác nhau")
    )

    dai_canh_bao = ""
    if canh_bao:
        dai_canh_bao = (
            '<div class="flash err">✕ Token có vấn đề: '
            + escape(", ".join(canh_bao))
            + " — sửa trong <b>.env</b> rồi bấm <b>Kiểm tra</b>.</div>"
        )

    dong_kn = ""
    for k in tt["ket_noi"]:
        # Python 3.11 chưa cho backslash trong biểu thức f-string → tách ra biến
        thieu_token = "" if k["co_token"] else '<div class="note">chưa có trong .env</div>'
        dong_kn += (
            "<tr>"
            f"<td><b>{_e(k['name'])}</b>"
            f"<div class=\"note\">{_e(_NGUON.get(k['provider'], k['provider']))}"
            f"{' · shop ' + _e(k['external_id']) if k['external_id'] else ''}</div></td>"
            f"<td>{_TOKEN.get(k['token_status'], '')}"
            f"{thieu_token}</td>"
            f"<td>{_e(k['token_hint'])}</td>"
            f"<td>{_fmt_dt(k['token_checked_at'])}</td>"
            f"<td>{k['so_page_bat']}/{k['so_page']}</td>"
            f"<td class=\"note\">{_e((k['last_error'] or '')[:120])}</td>"
            '<td><form method="post" '
            f"action=\"/quan-tri/tich-hop/{k['id']}/kiem-tra\">"
            '<button class="btn sm">Kiểm tra</button></form></td>'
            "</tr>"
        )

    dong_page = ""
    for p in pages:
        nut = (
            f'<form method="post" action="/quan-tri/tich-hop/page/{p["id"]}/dong-bo">'
            f'<input type="hidden" name="bat" value="{0 if p["sync_enabled"] else 1}">'
            f'<button class="btn sm{"" if p["sync_enabled"] else " primary"}">'
            f'{"Tắt" if p["sync_enabled"] else "Bật"}</button></form>'
        )
        pill_bat = ('<span class="pill ok">bật</span>' if p["sync_enabled"]
                    else '<span class="pill">tắt</span>')
        dong_page += (
            "<tr>"
            f"<td><b>{_e(p['name'])}</b><div class=\"note\">{_e(p['external_page_id'])}</div></td>"
            f"<td>{pill_bat}</td>"
            f"<td>{p['so_hoi_thoai']}</td>"
            f"<td>{_fmt_dt(p['last_synced_at'])}</td>"
            f"<td class=\"note\">{_e((p['last_error'] or '')[:80])}</td>"
            f"<td>{nut}</td>"
            "</tr>"
        )

    dong_nguon = "".join(
        "<tr>"
        f"<td>{_e(_NGUON.get(r['provider'], r['provider']))}</td>"
        f"<td>{_e(_ENTITY.get(r['entity'], r['entity']))}</td>"
        f"<td>{r['so_luot']}</td><td>{r['tao_moi']}</td><td>{r['cap_nhat']}</td>"
        f"<td>{r['loi']}</td><td>{_fmt_dt(r['lan_cuoi'])}</td>"
        "</tr>"
        for r in tt["theo_nguon"]
    )

    body = f"""
{dai_canh_bao}
<div class="stats">{o_so}</div>

<div class="card" style="margin-top:14px">
  <h3>Kết nối Pancake</h3>
  <p class="note">Token thật nằm trong <b>.env</b>, KHÔNG lưu ở CSDL — bảng này chỉ
  theo dõi tình trạng. Bấm <b>Kiểm tra</b> để gọi Pancake đúng một lần và biết token
  còn sống không (luật mục 4: token lỗi/hết hạn phải cảnh báo).</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Kết nối</th><th>Token</th><th>Mã che</th><th>Kiểm lúc</th>
  <th>Page bật</th><th>Lỗi gần nhất</th><th></th></tr></thead>
  <tbody>{dong_kn or '<tr><td colspan="7">Chưa cấu hình kết nối nào trong .env</td></tr>'}</tbody>
  </table></div>
</div>

<div class="card" style="margin-top:14px">
  <h3>Page đang nối vào CRM</h3>
  <p class="note">Tắt một page = hội thoại page đó KHÔNG đổ vào CRM nữa (bot vẫn
  chạy như cũ). Đổi có hiệu lực trong vòng 1 phút.</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Page</th><th>Đồng bộ</th><th>Hội thoại</th><th>Lần cuối</th>
  <th>Lỗi</th><th></th></tr></thead>
  <tbody>{dong_page or '<tr><td colspan="6">Chưa có page nào — bật CRM_SYNC_ENABLED rồi chờ poller</td></tr>'}</tbody>
  </table></div>
</div>

<div class="card" style="margin-top:14px">
  <h3>Tình trạng đồng bộ 24 giờ qua</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Nguồn</th><th>Loại</th><th>Số lượt</th><th>Tạo mới</th>
  <th>Cập nhật</th><th>Lỗi</th><th>Lần cuối</th></tr></thead>
  <tbody>{dong_nguon or '<tr><td colspan="7">Chưa có lượt đồng bộ nào trong 24h</td></tr>'}</tbody>
  </table></div>
</div>
"""
    return _shell("Tích hợp Pancake", "ket-noi", body, ok, error)


# ------------------------------------------------------------ tab 2: nhật ký
def render_nhat_ky(
    rows: list[dict], total: int, *, provider: str = "", page: int = 1,
    per_page: int = 30, ok: str = "", error: str = "",
) -> str:
    dong = "".join(
        "<tr>"
        f"<td>{_fmt_dt(r['started_at'])}</td>"
        f"<td>{_e(_NGUON.get(r['provider'], r['provider']))}</td>"
        f"<td>{_e(_ENTITY.get(r['entity'], r['entity']))}</td>"
        f"<td class=\"note\">{_e(r['scope'])}</td>"
        f"<td><span class='pill'>{_e(r['run_type'])}</span></td>"
        f"<td>{r['created_count']}</td><td>{r['updated_count']}</td>"
        f"<td>{r['skipped_count']}</td>"
        f"<td>{_o_loi(r['error_count'])}</td>"
        f"<td>{r['duration_ms'] or 0} ms</td>"
        f"<td>{_TRANG_THAI_LOG.get(r['status'], _e(r['status']))}</td>"
        "</tr>"
        for r in rows
    )
    q = f"?provider={escape(provider)}"
    truoc = f'<a class="btn sm" href="{q}&page={page-1}">← Mới hơn</a>' if page > 1 else ""
    sau = f'<a class="btn sm" href="{q}&page={page+1}">Cũ hơn →</a>' if page * per_page < total else ""

    body = f"""
<form class="card form" method="get" action="/quan-tri/tich-hop/nhat-ky" style="margin-bottom:14px">
  <div class="grid2">
    <label>Nguồn
      <select name="provider">
        <option value=""{' selected' if not provider else ''}>Tất cả</option>
        <option value="pancake_pages"{' selected' if provider == 'pancake_pages' else ''}>Pancake chat</option>
        <option value="pancake_pos"{' selected' if provider == 'pancake_pos' else ''}>Pancake POS</option>
      </select></label>
    <label>&nbsp;<button class="btn primary">Lọc</button></label>
  </div>
</form>
<div class="tblwrap card"><table class="tbl">
<thead><tr><th>Bắt đầu</th><th>Nguồn</th><th>Loại</th><th>Phạm vi</th><th>Kiểu</th>
<th>Tạo</th><th>Sửa</th><th>Bỏ qua</th><th>Lỗi</th><th>Thời lượng</th><th>Kết quả</th></tr></thead>
<tbody>{dong or '<tr><td colspan="11">Chưa có lượt đồng bộ nào</td></tr>'}</tbody></table></div>
<p style="margin-top:10px">{truoc} {sau} <span class="note">tổng {total} lượt</span></p>
"""
    return _shell("Nhật ký đồng bộ", "nhat-ky", body, ok, error)


# ------------------------------------------------------------ tab 3: lỗi
def render_loi(
    rows: list[dict], total: int, *, status: str = "pending", page: int = 1,
    per_page: int = 30, ok: str = "", error: str = "",
) -> str:
    dong = ""
    for r in rows:
        nut = (
            f'<form method="post" action="/quan-tri/tich-hop/loi/{r["id"]}/thu-lai">'
            '<button class="btn sm">Thử lại</button></form>'
            if r["status"] != "resolved" else ""
        )
        dong += (
            "<tr>"
            f"<td>{_fmt_dt(r['updated_at'])}</td>"
            f"<td>{_e(_NGUON.get(r['provider'], r['provider']))}</td>"
            f"<td>{_e(_ENTITY.get(r['entity'], r['entity']))}</td>"
            f"<td class=\"note\">{_e(r['external_id'])}</td>"
            f"<td><span class='pill'>{_e(r['error_type'])}</span>"
            f"<div class=\"note\">{_e((r['error_message'] or '')[:160])}</div></td>"
            f"<td>{r['retry_count']}</td>"
            f"<td>{_fmt_dt(r['next_retry_at'])}</td>"
            f"<td>{_TRANG_THAI_LOI.get(r['status'], _e(r['status']))}</td>"
            f"<td>{nut}</td>"
            "</tr>"
        )
    q = f"?status={escape(status)}"
    truoc = f'<a class="btn sm" href="{q}&page={page-1}">← Mới hơn</a>' if page > 1 else ""
    sau = f'<a class="btn sm" href="{q}&page={page+1}">Cũ hơn →</a>' if page * per_page < total else ""

    body = f"""
<div class="card" style="margin-bottom:14px">
  <p class="note" style="margin:0">Bản ghi đồng bộ hỏng nằm ở đây kèm <b>nguyên văn dữ
  liệu gốc</b> nên chạy lại được mà không phải gọi lại Pancake. Worker tự thử lại theo
  lịch giãn dần (5' → 15' → 45' → …); quá 5 lần thì chuyển <b>bỏ cuộc</b> chờ xử lý tay.</p>
  <form method="post" action="/quan-tri/tich-hop/loi/chay-ngay" style="margin-top:10px">
    <button class="btn primary">Chạy hàng đợi ngay</button>
  </form>
</div>
<form class="card form" method="get" action="/quan-tri/tich-hop/loi" style="margin-bottom:14px">
  <div class="grid2">
    <label>Tình trạng
      <select name="status">
        <option value="pending"{' selected' if status == 'pending' else ''}>Đang chờ</option>
        <option value="given_up"{' selected' if status == 'given_up' else ''}>Bỏ cuộc</option>
        <option value="resolved"{' selected' if status == 'resolved' else ''}>Đã xong</option>
        <option value=""{' selected' if not status else ''}>Tất cả</option>
      </select></label>
    <label>&nbsp;<button class="btn primary">Lọc</button></label>
  </div>
</form>
<div class="tblwrap card"><table class="tbl">
<thead><tr><th>Lúc</th><th>Nguồn</th><th>Loại</th><th>ID ngoài</th><th>Lỗi</th>
<th>Đã thử</th><th>Thử lại lúc</th><th>Tình trạng</th><th></th></tr></thead>
<tbody>{dong or '<tr><td colspan="9">Không có lỗi nào — đồng bộ đang sạch</td></tr>'}</tbody></table></div>
<p style="margin-top:10px">{truoc} {sau} <span class="note">tổng {total} dòng</span></p>
"""
    return _shell("Lỗi đồng bộ", "loi", body, ok, error)


# ------------------------------------------------------------ tab 4: ánh xạ
def render_anh_xa(
    pages: list[dict], accounts: list[dict], nhan_vien: list[dict],
    users: list[dict], mappings: list[dict], crm_statuses: list[str],
    *, ok: str = "", error: str = "",
) -> str:
    opt_acc = lambda chon: '<option value="">—</option>' + "".join(  # noqa: E731
        f'<option value="{a["id"]}"{" selected" if a["id"] == chon else ""}>'
        f'{escape(a["name"])}</option>' for a in accounts
    )
    dong_page = "".join(
        "<tr>"
        f"<td><b>{_e(p['name'])}</b><div class=\"note\">{_e(p['external_page_id'])}</div></td>"
        f"<td>{_e(p['platform'])}</td>"
        '<td><form method="post" class="inline" '
        f"action=\"/quan-tri/tich-hop/page/{p['id']}/ket-noi\">"
        f'<select name="account_id">{opt_acc(p["account_id"])}</select> '
        '<button class="btn sm primary">Lưu</button></form></td>'
        "</tr>"
        for p in pages
    )

    opt_user = lambda chon: '<option value="">— chưa gán —</option>' + "".join(  # noqa: E731
        f'<option value="{u["id"]}"{" selected" if u["id"] == chon else ""}>'
        f'{escape(u.get("name") or u.get("username") or "")}</option>' for u in users
    )
    def _ho_so(s: dict) -> str:
        """Cột Tên: có hồ sơ POS thì bày tên + phòng ban + email/SĐT; chưa có thì
        nói thẳng là chỉ nhặt được id trong đơn cũ (thường là người đã nghỉ) để
        Admin khỏi ngồi gán cho người không còn làm."""
        if not s.get("synced_at"):
            return ('<i class="note">— chỉ thấy trong đơn cũ, không còn trong '
                    "danh sách POS —</i>")
        phu = " · ".join(x for x in (s.get("department"), s.get("email"),
                                     s.get("phone")) if x)
        return (f"<b>{_e(s['external_name'])}</b>"
                + (f'<div class="note">{_e(phu)}</div>' if phu else ""))

    dong_nv = "".join(
        "<tr>"
        f"<td class=\"note\">{_e(s['external_staff_id'])}</td>"
        f"<td>{_ho_so(s)}</td>"
        f"<td>{_e(_NGUON.get(s['provider'], s['provider']))}</td>"
        f"<td><span class='pill'>{_e(s['role_hint'])}</span></td>"
        f"<td>{_fmt_dt(s['last_seen_at'])}</td>"
        '<td><form method="post" class="inline" action="/quan-tri/tich-hop/nhan-vien">'
        f'<input type="hidden" name="provider" value="{escape(s["provider"])}">'
        f'<input type="hidden" name="external_staff_id" value="{escape(s["external_staff_id"])}">'
        f'<select name="user_id">{opt_user(s["user_id"])}</select> '
        '<button class="btn sm primary">Lưu</button></form></td>'
        "</tr>"
        for s in nhan_vien
    )

    dong_tt = ""
    for m in mappings:
        chon = "".join(
            f'<option value="{s}"{" selected" if s == m["crm_status"] else ""}>{s}</option>'
            for s in crm_statuses
        )
        dong_tt += (
            "<tr>"
            f"<td><b>{m['pancake_status']}</b></td>"
            f"<td>{_e(m['pancake_status_name'])}</td>"
            '<td><form method="post" class="inline" '
            f"action=\"/quan-tri/tich-hop/trang-thai-don/{m['pancake_status']}\">"
            f'<select name="crm_status">{chon}</select> '
            '<button class="btn sm primary">Lưu</button></form></td>'
            f"<td>{_e(m.get('updated_by_name'))}</td>"
            f"<td>{_fmt_dt(m.get('updated_at'))}</td>"
            "</tr>"
        )

    body = f"""
<div class="card">
  <h3>Ánh xạ Page → kết nối</h3>
  <p class="note">Page tự xuất hiện khi poller gặp lần đầu. Gán về đúng tài khoản để
  biết page nào thuộc kết nối nào (nhiều tài khoản Pancake dùng chung một CRM).</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Page</th><th>Nền tảng</th><th>Kết nối</th></tr></thead>
  <tbody>{dong_page or '<tr><td colspan="3">Chưa có page</td></tr>'}</tbody></table></div>
</div>

<div class="card" style="margin-top:14px">
  <div style="display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap">
    <h3 style="flex:1 1 auto;margin:0">Ánh xạ nhân viên Pancake → nhân viên CRM</h3>
    <form method="post" action="/quan-tri/tich-hop/nhan-vien/dong-bo?nguon=pos"
          class="inline"><button class="btn sm primary">↻ Lấy NV từ POS</button></form>
    <form method="post" action="/quan-tri/tich-hop/nhan-vien/dong-bo?nguon=pages"
          class="inline"><button class="btn sm">↻ Lấy NV từ Pancake (chat)</button></form>
  </div>
  <p class="note">ID nhân viên bên Pancake (người xử lý hội thoại, người bán, người
  chăm trên đơn POS) tự được ghi nhận khi đồng bộ — nhưng đơn/hội thoại chỉ mang
  <b>id trần</b>, không có tên. Bấm hai nút trên để kéo hồ sơ về rồi mới gán được
  ai ra ai: <b>POS</b> cho tên · phòng ban · email · SĐT; <b>Pancake (chat)</b>
  chỉ có tên nhưng biết cả người POS không có. Nên bấm cả hai. Gán vào tài khoản
  CRM để hội thoại hiện đúng người phụ trách. <b>Việc gán này KHÔNG tự phân công
  khách</b> — quyền sở hữu khách theo luật riêng của Sale/CSKH (FR-030…032).</p>
  <p class="note">Một người thường có <b>hai dòng</b> ở đây (một của POS, một của
  chat) vì hai bên dùng chung ID Pancake. Gán ở dòng nào cũng được —
  <b>máy tự áp cho dòng kia</b>, khỏi phải làm hai lần.</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>ID bên Pancake</th><th>Tên</th><th>Nguồn</th><th>Vai</th>
  <th>Gặp lần cuối</th><th>Nhân viên CRM</th></tr></thead>
  <tbody>{dong_nv or '<tr><td colspan="6">Chưa gặp nhân viên nào (chờ đồng bộ)</td></tr>'}</tbody>
  </table></div>
</div>

<div class="card" style="margin-top:14px">
  <h3>Ánh xạ trạng thái đơn POS → CRM <span class="note">(màn 23)</span></h3>
  <p class="note">Sửa xong là lượt đồng bộ kế tiếp dùng ngay bản mới. Mã POS chưa có
  trong bảng này sẽ nhận tạm <b>draft</b> và ghi rõ lý do trong lịch sử đơn.</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Mã POS</th><th>Tên bên POS</th><th>Trạng thái CRM</th>
  <th>Người sửa</th><th>Sửa lúc</th></tr></thead>
  <tbody>{dong_tt or '<tr><td colspan="5">Chưa có ánh xạ</td></tr>'}</tbody></table></div>
</div>
"""
    return _shell("Ánh xạ tích hợp", "anh-xa", body, ok, error)
