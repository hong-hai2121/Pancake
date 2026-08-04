"""Dựng HTML khu Quản trị (A5): nhân viên (màn 65-66) · phân quyền (màn 67) ·
nhật ký hoạt động (màn 77). Chỉ hiển thị — dữ liệu do routes/admin.py đưa vào."""

from html import escape

from app.web.shell import flash, render_shell, tabs_bar

_TABS = [
    ("/quan-tri/nhan-vien", "Nhân viên", "nhan-vien"),
    ("/quan-tri/phan-quyen", "Vai trò & quyền", "phan-quyen"),
    ("/quan-tri/the-pancake", "Thẻ Pancake", "the-pancake"),
    ("/quan-tri/cai-dat", "Cài đặt", "cai-dat"),
    ("/quan-tri/nhat-ky", "Nhật ký", "nhat-ky"),
]


def _shell(
    title: str, tab: str, body: str, ok: str = "", error: str = "",
    tabs_items: list | None = None, sub: str = "", script: str = "",
) -> str:
    return render_shell(
        title, "admin", flash(ok, error) + body,
        heading="Quản trị",
        sub=sub or "Tài khoản, vai trò, quyền và nhật ký hệ thống (A5)",
        tabs=tabs_bar(_TABS if tabs_items is None else tabs_items, tab),
        script=script,
    )


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _fmt_dt(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


_TRANG_THAI = {
    "active": '<span class="pill ok">hoạt động</span>',
    "inactive": '<span class="pill">nghỉ việc</span>',
    "suspended": '<span class="pill err">tạm khoá</span>',
}

# Lọc danh sách nhân viên NGAY trên trình duyệt (không tải lại trang):
# ô tìm khớp tên/email/@username/SĐT (gõ `@` -> chỉ dò username; SĐT so bản
# chỉ-chữ-số nên gõ liền vẫn trúng bản lưu có khoảng cách), chip khớp nhóm.
# Dải tiêu đề nhóm tự ẩn khi cả nhóm bị lọc hết. Chạy lại sau PJAX nhờ
# data-page-script của shell.
_UM_JS = """
window.umFilter = function(){
  var inp = document.getElementById('umSearch');
  if (!inp) return;
  var q = inp.value.trim().toLowerCase();
  var so = q.replace(/[^0-9]/g, '');
  var chip = document.querySelector('.um-chip.on');
  var nhom = chip ? (chip.getAttribute('data-nhom') || '') : '';
  var rows = document.querySelectorAll('tr[data-tim]');
  var thay = 0;
  for (var i = 0; i < rows.length; i++){
    var r = rows[i], hit;
    if (q.charAt(0) === '@'){
      hit = (r.getAttribute('data-un') || '').indexOf(q.slice(1)) !== -1;
    } else {
      hit = !q || (r.getAttribute('data-tim') || '').indexOf(q) !== -1
             || (so !== '' && (r.getAttribute('data-sdt') || '').indexOf(so) !== -1);
    }
    var show = hit && (nhom === '' || r.getAttribute('data-nhom') === nhom);
    r.style.display = show ? '' : 'none';
    if (show) thay++;
  }
  var grps = document.querySelectorAll('tr.tgrp');
  for (var g = 0; g < grps.length; g++){
    var any = false, el = grps[g].nextElementSibling;
    while (el && !el.classList.contains('tgrp')){
      if (el.hasAttribute('data-tim') && el.style.display !== 'none'){ any = true; break; }
      el = el.nextElementSibling;
    }
    grps[g].style.display = any ? '' : 'none';
  }
  var trong = document.getElementById('umEmpty');
  if (trong) trong.style.display = thay ? 'none' : '';
};
window.umDept = function(el){
  var chips = document.querySelectorAll('.um-chip');
  for (var i = 0; i < chips.length; i++) chips[i].classList.remove('on');
  el.classList.add('on');
  window.umFilter();
};

// Hộp thoại sửa nhanh: MỘT hộp dùng chung cho mọi dòng, JS chép dữ liệu từ
// data-* của nút bút chì vào. Mỗi dòng một hộp riêng thì 100 nhân viên ×
// ~113 lựa chọn Pancake = vài trăm KB HTML cho thứ mở ra một lần.
window.umEdit = function(btn){
  var d = document.getElementById('umDlg');
  if (!d) return;
  var g = function(k){ return btn.getAttribute('data-' + k) || ''; };
  d.querySelector('#umDlgTen').textContent = g('ten');
  d.querySelector('form').action = '/quan-tri/nhan-vien/' + g('uid') + '/sua';
  d.querySelector('[name=name]').value = g('ten');
  var set = function(sel, val){ var e = d.querySelector(sel); if (e) e.value = val; };
  set('[name=role_id]', g('role'));
  set('[name=team_id]', g('team'));
  set('[name=pancake_staff]', g('pc'));
  var rs = d.querySelector('#umDlgReset');
  if (rs) rs.action = '/quan-tri/nhan-vien/' + g('uid') + '/reset-mat-khau';
  // showModal() cho nền mờ + Esc đóng sẵn; trình duyệt cũ thì lùi về show().
  if (d.showModal) d.showModal(); else d.setAttribute('open', '');
};
window.umEditClose = function(){
  var d = document.getElementById('umDlg');
  if (!d) return;
  if (d.close) d.close(); else d.removeAttribute('open');
};
window.umFilter();
"""


# ------------------------------------------------------------ màn 65: danh sách
_NHAN_NGUON = {"pancake_pos": "POS", "pancake_pages": "Chat"}


def _ma_staff(s: dict | None) -> str:
    """Khoá một dòng staff_mappings thành 1 chuỗi cho ô <select>: 'provider|uuid'.

    Phải kèm provider vì khoá thật của bảng là (provider, external_staff_id)."""
    if not s or not s.get("external_staff_id"):
        return ""
    return f'{s["provider"]}|{s["external_staff_id"]}'


def _nguon_pill(nguon) -> str:
    """Người này do nguồn nào biết: POS · Chat · cả hai.

    Cùng một người thường có mặt ở cả hai (uuid dùng chung), nhưng POS biết cả
    kho/nhân sự còn chat biết vài người POS không có — nói rõ ra để Admin hiểu
    vì sao có người thiếu email/SĐT (bên chat không trả mấy trường đó)."""
    ds = list(nguon or [])
    if not ds:
        return "—"
    if len(ds) > 1:
        return '<span class="pill ok">cả hai</span>'
    ma = ds[0]
    lop = "pill" if ma == "pancake_pos" else "pill warn"
    return f'<span class="{lop}">chỉ {_NHAN_NGUON.get(ma, ma)}</span>'


def _o_pancake(pc: dict | None) -> str:
    """Ô cột 'Ghép Pancake' của một nhân viên CRM.

    Chưa ghép thì phải ĐẬP VÀO MẮT: người chưa ghép mà đem chia khách là hỏng —
    hội thoại vẫn thuộc người khác bên Pancake, việc chăm không về đúng tay."""
    if not pc:
        return ('<span class="pill err" title="Chưa ứng với nhân viên nào bên '
                'Pancake">CHƯA GHÉP</span>')
    phu = pc.get("department") or ""
    return (f'<span class="pill ok">{_e(pc.get("external_name"))}</span>'
            + (f'<div class="note">{_e(phu)}</div>' if phu else ""))


def render_users(
    users: list[dict], roles: list[dict], teams: list[dict],
    *, q: str = "", nhom: str = "", co_xuat: bool = False,
    ok: str = "", error: str = "", gioi_han: dict | None = None,
    pancake: dict | None = None, pancake_thua: list[dict] | None = None,
) -> str:
    """`gioi_han` = phạm vi trưởng nhóm (user_service.pham_vi_doi): bản thu gọn —
    chỉ đội mình, tạo đúng 1 vai trò, hết nút khoá/mở + link hồ sơ (đó là việc
    của Admin); reset MK chỉ hiện ở dòng thành viên. Chặn thật vẫn ở service.

    `pancake` = {users.id: dòng staff_mappings đã ghép} (integration_repo
    .staff_theo_user); `pancake_thua` = nhân viên Pancake (gộp POS + chat, đã
    distinct theo uuid) chưa ứng với tài khoản nào.
    """
    pancake = pancake or {}
    opt_role = "".join(
        f'<option value="{r["id"]}">{escape(r["name"])}</option>' for r in roles
    )
    opt_team = "".join(
        f'<option value="{t["id"]}">{escape(t["name"])}</option>' for t in teams
    )

    # Khối cảnh báo: người bên Pancake chưa ứng với tài khoản CRM nào. Chỉ đếm
    # người CÒN trong danh sách (synced_at) — id chỉ thấy trong đơn/hội thoại cũ
    # là nhân viên đã nghỉ, bày ra chỉ tổ rối. Trưởng nhóm không thấy khối này:
    # ghép Pancake là việc của Admin (quyền integration.manage).
    thua = pancake_thua or []
    con_lam = [s for s in thua if s.get("synced_at")]
    da_nghi = len(thua) - len(con_lam)
    khoi_thua = ""
    if con_lam and not gioi_han:
        # Xếp theo phòng ban rồi tên: 69 người mà để lộn xộn thì không dò được ai.
        con_lam = sorted(con_lam, key=lambda s: ((s.get("department") or "zzz").lower(),
                                                 (s.get("external_name") or "").lower()))
        ds = "".join(
            "<tr>"
            f'<td><b>{_e(s["external_name"])}</b></td>'
            f'<td>{_e(s.get("department"))}</td>'
            f'<td>{_e(s.get("email"))}</td>'
            f'<td class="nowrap">{_e(s.get("phone"))}</td>'
            f"<td>{_nguon_pill(s.get('nguon'))}</td>"
            "</tr>"
            for s in con_lam
        )
        ghi_chu_nghi = (
            f' Ngoài ra có <b>{da_nghi}</b> ID chỉ còn thấy trong đơn/hội thoại cũ '
            "— người đã nghỉ, không bày ở đây." if da_nghi else ""
        )
        khoi_thua = f"""
<div class="card" style="margin-top:14px">
  <h3>Nhân viên Pancake chưa ghép <span class="pill warn">{len(con_lam)}</span></h3>
  <p class="note">Những người này có trong danh sách nhân viên của Pancake nhưng chưa
  ứng với tài khoản CRM nào. Chưa ghép thì đơn/hội thoại họ xử lý bên Pancake không
  quy được về ai trong CRM. Ghép ở
  <a href="/quan-tri/tich-hop/anh-xa">Tích hợp → Ánh xạ</a> — gán một lần là ăn cả
  hai nguồn.{ghi_chu_nghi}</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Tên bên Pancake</th><th>Phòng ban</th><th>Email</th><th>SĐT</th>
  <th>Nguồn</th></tr></thead>
  <tbody>{ds}</tbody></table></div>
</div>"""

    # Ô "Ghép Pancake" trong hộp thoại: mọi nhân viên Pancake CÒN LÀM (có hồ sơ),
    # kèm người đang ghép sẵn ở dòng nào đó. Người đã nghỉ không đưa vào — ghép
    # tài khoản CRM vào người đã nghỉ là vô nghĩa.
    ds_pc = sorted(
        [s for s in (pancake_thua or []) if s.get("synced_at")]
        + [s for s in pancake.values() if s.get("synced_at")],
        key=lambda s: ((s.get("department") or "zzz").lower(),
                       (s.get("external_name") or "").lower()),
    )
    opt_pc = '<option value="">— chưa ghép —</option>' + "".join(
        f'<option value="{escape(_ma_staff(s))}">{escape(s["external_name"] or "?")}'
        + (f' · {escape(s["department"])}' if s.get("department") else "")
        + f' · {_NHAN_NGUON.get(s["provider"], s["provider"])}</option>'
        for s in ds_pc
    )
    hop_thoai = "" if gioi_han else f"""
<dialog id="umDlg" class="umdlg">
  <form method="post" action="" class="form">
    <input type="hidden" name="ve" value="ds">
    <h3 style="margin:0 0 14px">Sửa nhân viên · <span id="umDlgTen"></span></h3>
    <label>Tên<input type="text" name="name"></label>
    <div class="grid2" style="margin-top:11px">
      <label>Vị trí<select name="role_id"><option value="">—</option>{opt_role}</select></label>
      <label>Nhóm<select name="team_id"><option value="">—</option>{opt_team}</select></label>
    </div>
    <label style="margin-top:11px">Ghép Pancake
      <select name="pancake_staff">{opt_pc}</select></label>
    <p class="note" style="margin:6px 0 0">Gán một lần là ăn cả hai nguồn (POS +
    chat) nếu cùng ID Pancake. Chọn <b>— chưa ghép —</b> để gỡ.</p>
    <button type="button" class="btn sm" form="umDlgReset" style="margin-top:12px"
      onclick="return confirm('Cấp mật khẩu mới? Mọi phiên của người này sẽ bị đăng xuất.')
               &amp;&amp; (document.getElementById('umDlgReset').submit(), false)">
      🔑 Đặt lại mật khẩu</button>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px">
      <button type="button" class="btn" onclick="umEditClose()">Huỷ</button>
      <button class="btn primary">Lưu</button>
    </div>
  </form>
</dialog>
<form id="umDlgReset" method="post" action="" style="display:none"></form>"""

    def _dong_nv(u: dict) -> str:
        khoa_mo = (
            ("suspended", "Khoá") if u["status"] == "active" else ("active", "Mở")
        )
        if gioi_han:
            ten = f"<b>{_e(u['username'])}</b>"
            nut_khoa = ""
            cho_reset = u["role_id"] == gioi_han["role_id"]
        else:
            ten = f'<a href="/quan-tri/nhan-vien/{u["id"]}"><b>{_e(u["username"])}</b></a>'
            nut_khoa = (
                f'<form method="post" action="/quan-tri/nhan-vien/{u["id"]}/trang-thai" '
                'style="display:inline">'
                f'<input type="hidden" name="status" value="{khoa_mo[0]}">'
                f'<button class="btn sm">{khoa_mo[1]}</button></form> '
            )
            cho_reset = True
        nut_reset = (
            f'<form method="post" action="/quan-tri/nhan-vien/{u["id"]}/reset-mat-khau" '
            'style="display:inline" onsubmit="return confirm(\'Cấp mật khẩu mới? '
            'Mọi phiên của người này sẽ bị đăng xuất.\')">'
            '<button class="btn sm">Reset MK</button></form>'
        ) if cho_reset else ""
        # Nút bút chì: mở hộp thoại sửa nhanh (tên · vị trí · nhóm · ghép Pancake).
        # Trưởng nhóm không có — sửa hồ sơ người khác là việc của Admin.
        pc_cua = pancake.get(u["id"]) or {}
        nut_sua = "" if gioi_han else (
            '<button class="btn sm" title="Sửa nhanh" onclick="umEdit(this)"'
            f' data-uid="{u["id"]}" data-ten="{escape(u["name"] or "")}"'
            f' data-role="{u["role_id"] or ""}" data-team="{u["team_id"] or ""}"'
            f' data-pc="{escape(_ma_staff(pc_cua))}">✎</button> '
        )
        tim = " ".join(
            str(x) for x in (u["username"], u["name"], u["email"], u["phone"]) if x
        ).lower()
        sdt = "".join(c for c in (u["phone"] or "") if c.isdigit())
        return (
            f'<tr data-nhom="{u["team_id"] or 0}" '
            f'data-un="{escape((u["username"] or "").lower())}" '
            f'data-tim="{escape(tim)}" data-sdt="{sdt}">'
            f"<td>{ten}</td>"
            f"<td>{_e(u['name'])}</td><td>{_e(u['email'])}</td>"
            f"<td class='nowrap'>{_e(u['phone'])}</td>"
            f"<td>{_e(u['role_name'])}</td>"
            f"<td>{_o_pancake(pancake.get(u['id']))}</td>"
            f"<td>{_TRANG_THAI.get(u['status'], _e(u['status']))}</td>"
            f"<td>{_fmt_dt(u['last_login_at'])}</td>"
            f"<td class='act'>{nut_sua}{nut_khoa}{nut_reset}</td></tr>"
        )

    # Gom theo nhóm cho dễ nhìn: mỗi đội một dải tiêu đề (trưởng nhóm đứng đầu),
    # người chưa vào nhóm dồn xuống cuối — cột "Nhóm" nhờ vậy bỏ được.
    theo_nhom: dict[str, list[dict]] = {}
    for u in users:
        theo_nhom.setdefault(u["team_name"] or "", []).append(u)
    truong = {t["name"]: t["manager_id"] for t in teams}

    dong = ""
    for ten_nhom in sorted(k for k in theo_nhom if k) + [""]:
        thanh_vien = theo_nhom.get(ten_nhom)
        if not thanh_vien:
            continue
        nhan = escape(ten_nhom) if ten_nhom else "Chưa vào nhóm"
        dong += (f'<tr class="tgrp"><td colspan="9">{nhan}'
                 f' · {len(thanh_vien)} người</td></tr>')
        thanh_vien.sort(key=lambda u: (u["id"] != truong.get(ten_nhom), u["name"] or ""))
        dong += "".join(_dong_nv(u) for u in thanh_vien)

    if gioi_han:
        # Trưởng nhóm: vai trò + đội bị ép ở server — chỉ báo cho biết, không cho chọn
        chon_vai = (
            f'<label>Vai trò<input type="text" disabled '
            f'value="{escape(gioi_han["role_name"])} — {escape(gioi_han["team_name"])}"></label>'
        )
    else:
        chon_vai = (
            f'<label>Vai trò<select name="role_id"><option value="">—</option>{opt_role}</select></label>\n'
            f'    <label>Nhóm<select name="team_id"><option value="">—</option>{opt_team}</select></label>'
        )

    # Toolbar MỘT HÀNG kiểu Pancake: 🔍 ô tìm · chip nhóm · Xuất Excel — lọc
    # ngay trên trình duyệt (_UM_JS), không tải lại trang. Chip lấy động từ
    # crm.teams nên tạo nhóm mới (vd Kho vận) là tự hiện. Trưởng nhóm bị ép về
    # đội mình: không chip, không nút xuất (nút còn cần thêm quyền data.export).
    chips = ""
    if not gioi_han:
        def _chip(gia_tri: str, ten: str) -> str:
            return (f'<span class="um-chip{" on" if nhom == gia_tri else ""}" '
                    f'data-nhom="{gia_tri}" onclick="umDept(this)">{ten}</span>')

        chips = (
            _chip("", "Tất cả")
            + "".join(_chip(str(t["id"]), escape(t["name"])) for t in teams)
            + _chip("0", "Chưa vào nhóm")
        )
    # `download` để PJAX bỏ qua link này — trình duyệt tải file CSV thẳng
    nut_xuat = (
        '<a class="btn" href="/quan-tri/nhan-vien/xuat-excel" download>⬇ Xuất Excel</a>'
        if co_xuat and not gioi_han else ""
    )

    body = f"""
<style>
.um-toolbar{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:14px}}
.um-search{{display:flex;align-items:center;gap:6px;background:var(--card);
  border:1px solid var(--border);border-radius:8px;padding:6px 12px}}
.um-search input{{border:0;outline:0;background:transparent;color:inherit;
  width:220px;font:inherit}}
.um-chip{{font-size:12.5px;padding:5px 12px;border-radius:20px;cursor:pointer;
  border:1px solid var(--border);background:var(--card);user-select:none}}
.um-chip:hover{{border-color:var(--accent);color:var(--accent)}}
.um-chip.on{{background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;border-color:transparent}}
/* hộp thoại sửa nhanh — <dialog> thuần, không thư viện */
.umdlg{{width:440px;max-width:calc(100% - 40px);border:1px solid var(--border);
  border-radius:16px;background:var(--card);color:var(--text);
  box-shadow:var(--shadow-lg);padding:20px}}
.umdlg::backdrop{{background:rgba(43,34,48,.45)}}
.umdlg label{{display:flex;flex-direction:column;gap:4px;font-size:12px;
  color:var(--sub)}}
</style>

<div class="um-toolbar">
  <div class="um-search">🔍 <input id="umSearch" value="{escape(q)}"
       placeholder="Tìm tên, @tài khoản, SĐT…" oninput="umFilter()"></div>
  {chips}
  <span style="flex:1"></span>
  {nut_xuat}
</div>

<div class="tblwrap card"><table class="tbl">
<thead><tr><th>Username</th><th>Họ tên</th><th>Email</th><th>SĐT</th><th>Vai trò</th>
<th>Ghép Pancake</th><th>Trạng thái</th><th>Đăng nhập cuối</th><th></th></tr></thead>
<tbody>{dong or '<tr><td colspan="9">Chưa có nhân viên nào</td></tr>'}
<tr id="umEmpty" style="display:none"><td colspan="9">Không ai khớp bộ lọc</td></tr>
</tbody>
</table></div>

<details class="card" style="margin-top:14px"><summary><b>+ Tạo tài khoản mới</b>
 (mật khẩu để trống = hệ thống tự sinh và hiện MỘT lần)</summary>
<form class="form" method="post" action="/quan-tri/nhan-vien" style="margin-top:10px">
  <div class="grid2">
    <label>Họ tên *<input type="text" name="name" required></label>
    <label>Email *<input type="text" name="email" required placeholder="a@b.com"></label>
    <label>Username *<input type="text" name="username" required
           pattern="[a-zA-Z0-9_.\\-]{{3,60}}" placeholder="vd sale01"></label>
    <label>Điện thoại<input type="text" name="phone" placeholder="vd 0912 345 678"></label>
    <label>Mật khẩu (≥8 ký tự, bỏ trống = tự sinh)
      <input type="text" name="password" autocomplete="new-password"></label>
    {chon_vai}
  </div>
  <button class="btn primary">Tạo tài khoản</button>
</form></details>
{khoi_thua}
{hop_thoai}
"""
    if gioi_han:
        return _shell(
            "Nhân viên", "nhan-vien", body, ok, error,
            tabs_items=[_TABS[0]],
            sub=(f"Đội {escape(gioi_han['team_name'])} — trưởng nhóm tạo tài khoản "
                 f"{escape(gioi_han['role_name'])} và cấp lại mật khẩu cho đội mình"),
            script=_UM_JS,
        )
    return _shell("Nhân viên", "nhan-vien", body, ok, error, script=_UM_JS)


# ------------------------------------------------------------ màn 66: hồ sơ
def render_user_detail(
    u: dict, roles: list[dict], teams: list[dict], others: list[dict],
    sessions: list[dict], *, ok: str = "", error: str = "",
) -> str:
    def _opt(items, chon):
        return '<option value="">—</option>' + "".join(
            f'<option value="{i["id"]}"{" selected" if i["id"] == chon else ""}>'
            f'{escape(i["name"])}</option>' for i in items
        )

    opt_nhan = "".join(
        f'<option value="{o["id"]}">{escape(o["name"])} ({escape(o["username"] or "")})</option>'
        for o in others
    )

    phien = "".join(
        "<tr>"
        f"<td>{_fmt_dt(s['created_at'])}</td><td>{_e(s['ip'])}</td>"
        f"<td class='mono' style='max-width:340px;overflow:hidden;text-overflow:ellipsis;"
        f"white-space:nowrap'>{_e(s['user_agent'])}</td>"
        f"<td>{'đã thu hồi' if s['revoked_at'] else ('hết hạn ' + _fmt_dt(s['expires_at']))}</td>"
        "</tr>"
        for s in sessions
    )

    body = f"""
<p><a href="/quan-tri/nhan-vien">← Danh sách nhân viên</a></p>

<form class="card form" method="post" action="/quan-tri/nhan-vien/{u['id']}/sua">
  <h3>{_e(u['name'])} {_TRANG_THAI.get(u['status'], '')}</h3>
  <div class="grid2">
    <label>Họ tên<input type="text" name="name" value="{escape(u['name'] or '')}"></label>
    <label>Email<input type="text" name="email" value="{escape(u['email'] or '')}"></label>
    <label>Username<input type="text" name="username" value="{escape(u['username'] or '')}"></label>
    <label>Điện thoại<input type="text" name="phone" value="{escape(u['phone'] or '')}"></label>
    <label>Vai trò<select name="role_id">{_opt(roles, u['role_id'])}</select></label>
    <label>Nhóm<select name="team_id">{_opt(teams, u['team_id'])}</select></label>
  </div>
  <button class="btn primary">Lưu thay đổi</button>
</form>

<div class="card form" style="margin-top:14px">
  <h3>Chuyển toàn bộ khách / việc (FR-002)</h3>
  <p class="note">Bắt buộc làm trước khi khoá tài khoản nghỉ việc. Khách tiềm năng,
  kế hoạch chăm, cơ hội mua lại và việc đang mở sẽ sang người nhận; lịch sử người
  cũ vẫn giữ.</p>
  <form method="post" action="/quan-tri/nhan-vien/{u['id']}/chuyen-khach">
    <div class="grid2">
      <label>Chuyển cho<select name="new_owner_id" required>
        <option value="">— chọn người nhận —</option>{opt_nhan}</select></label>
      <label>&nbsp;<button class="btn"
        onclick="return confirm('Chuyển TOÀN BỘ sang người này?')">Chuyển</button></label>
    </div>
  </form>
</div>

<div class="card" style="margin-top:14px">
  <h3>Lịch sử đăng nhập (10 phiên gần nhất)</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Lúc</th><th>IP</th><th>Thiết bị</th><th>Trạng thái</th></tr></thead>
  <tbody>{phien or '<tr><td colspan="4">Chưa đăng nhập lần nào</td></tr>'}</tbody>
  </table></div>
</div>
"""
    return _shell(f"Nhân viên — {u['name']}", "nhan-vien", body, ok, error)


# ------------------------------------------------------------ màn 67: ma trận
def render_roles(
    roles: list[dict], permissions: list[dict], teams: list[dict],
    users: list[dict], *, ok: str = "", error: str = "",
) -> str:
    cot = "".join(
        f'<th title="{escape(p["code"])}">{escape(p["name"])}</th>' for p in permissions
    )
    dong = ""
    for r in roles:
        o = "".join(
            f'<td style="text-align:center"><input type="checkbox" name="perm" '
            f'value="{escape(p["code"])}"'
            f'{" checked" if p["code"] in (r["perms"] or []) else ""}></td>'
            for p in permissions
        )
        dong += (
            f'<tr><td><form method="post" action="/quan-tri/phan-quyen/{r["id"]}" '
            f'id="role-{r["id"]}"><b>{escape(r["name"])}</b>'
            f'<div class="note">{r["so_nguoi"]} người</div></form></td>'
            + o.replace("<input ", f'<input form="role-{r["id"]}" ')
            + f'<td><button class="btn sm primary" form="role-{r["id"]}">Lưu</button></td></tr>'
        )

    opt_manager = '<option value="">—</option>' + "".join(
        f'<option value="{u["id"]}">{escape(u["name"])}</option>' for u in users
    )
    nhom = "".join(
        f"<tr><td><b>{escape(t['name'])}</b></td><td>{_e(t['department'])}</td>"
        f"<td>{_e(t['manager_name'])}</td><td>{t['so_nguoi']}</td></tr>"
        for t in teams
    )

    body = f"""
<div class="card">
  <h3>Ma trận vai trò × quyền</h3>
  <p class="note">Tick rồi bấm <b>Lưu</b> từng dòng. Người thuộc vai trò nhận quyền
  mới ở lần làm mới phiên kế tiếp (tối đa 30 phút). Mọi thay đổi đều vào nhật ký.</p>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Vai trò</th>{cot}<th></th></tr></thead>
  <tbody>{dong}</tbody></table></div>
</div>

<details class="card" style="margin-top:14px"><summary><b>+ Tạo vai trò mới</b></summary>
<form class="form" method="post" action="/quan-tri/phan-quyen/vai-tro" style="margin-top:10px">
  <div class="grid2">
    <label>Tên vai trò *<input type="text" name="name" required></label>
    <label>Mô tả<input type="text" name="description"></label>
  </div>
  <button class="btn primary">Tạo (quyền tick sau ở ma trận)</button>
</form></details>

<div class="card" style="margin-top:14px">
  <h3>Nhóm làm việc</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Nhóm</th><th>Bộ phận</th><th>Trưởng nhóm</th><th>Số người</th></tr></thead>
  <tbody>{nhom or '<tr><td colspan="4">Chưa có nhóm</td></tr>'}</tbody></table></div>
  <details style="margin-top:8px"><summary><b>+ Tạo nhóm</b></summary>
  <form class="form" method="post" action="/quan-tri/phan-quyen/nhom" style="margin-top:10px">
    <div class="grid2">
      <label>Tên nhóm *<input type="text" name="name" required></label>
      <label>Bộ phận<select name="department"><option value="">—</option>
        <option value="sale">Sale</option><option value="cskh">CSKH</option>
        <option value="marketing">Marketing</option>
        <option value="chuyen_mon">Chuyên môn</option>
        <option value="kho_van">Kho vận</option>
        <option value="admin">Vận hành</option></select></label>
      <label>Trưởng nhóm<select name="manager_id">{opt_manager}</select></label>
    </div>
    <button class="btn primary">Tạo nhóm</button>
  </form></details>
  <p class="note" style="margin-top:6px">Gán người vào nhóm: mở hồ sơ từng nhân viên
  (tab Nhân viên) và chọn nhóm.</p>
</div>
"""
    return _shell("Vai trò & phân quyền", "phan-quyen", body, ok, error)


# ------------------------------------------------------------ màn 77: nhật ký
def render_audit(
    rows: list[dict], total: int, *, action: str = "", page: int = 1,
    ok: str = "", error: str = "",
) -> str:
    dong = "".join(
        "<tr>"
        f"<td>{_fmt_dt(r['created_at'])}</td>"
        f"<td>{_e(r['user_name'])}</td>"
        f"<td><span class='pill'>{_e(r['action'])}</span></td>"
        f"<td>{_e(r['object_type'])}#{_e(r['object_id'])}</td>"
        f"<td>{_e(r['reason'])}</td><td>{_e(r['ip'])}</td>"
        "</tr>"
        for r in rows
    )
    truoc = f'<a class="btn sm" href="?action={escape(action)}&page={page-1}">← Mới hơn</a>' if page > 1 else ""
    sau = f'<a class="btn sm" href="?action={escape(action)}&page={page+1}">Cũ hơn →</a>' if page * 30 < total else ""

    body = f"""
<form class="card form" method="get" action="/quan-tri/nhat-ky" style="margin-bottom:14px">
  <div class="grid2">
    <label>Lọc theo hành động
      <input type="text" name="action" value="{escape(action)}"
             placeholder="vd login, user_update, role_set_permissions"></label>
    <label>&nbsp;<button class="btn primary">Lọc</button></label>
  </div>
</form>
<div class="tblwrap card"><table class="tbl">
<thead><tr><th>Lúc</th><th>Ai</th><th>Hành động</th><th>Đối tượng</th>
<th>Lý do</th><th>IP</th></tr></thead>
<tbody>{dong or '<tr><td colspan="6">Trống</td></tr>'}</tbody></table></div>
<p style="margin-top:10px">{truoc} {sau} <span class="note">tổng {total} dòng</span></p>
"""
    return _shell("Nhật ký hoạt động", "nhat-ky", body, ok, error)


# ------------------------------------------------------------ trang 403
def render_403(message: str = "", heading: str = "Quản trị") -> str:
    """Trang 'không có quyền' dùng chung (khu Quản trị lẫn chặn khu Bot Pancake
    ở middleware). Có `message` riêng thì hiện nó; không thì giải thích bộ quyền
    khu Quản trị như cũ."""
    if message:
        ruot = (f"<p><b>{escape(message)}</b></p>"
                "<p>Liên hệ Admin nếu bạn cần được cấp.</p>")
    else:
        ruot = (
            "<p>Khu Quản trị cần quyền <code>user.manage</code>; tab Nhân viên mở "
            "thêm cho trưởng nhóm có <code>user.manage_team</code> (nhật ký cần "
            "<code>audit.view</code>). Liên hệ Admin nếu bạn cần được cấp.</p>"
        )
    return render_shell(
        "Không có quyền", "admin",
        f'<div class="card"><h3>⛔ Không có quyền truy cập</h3>{ruot}</div>',
        heading=heading,
    )


# ------------------------------------------------------------ màn 78: cài đặt
def render_cai_dat(nhom: list[dict], *, ok: str = "", error: str = "") -> str:
    """Công tắc bật/tắt + nhịp chạy của worker — đổi ngay, không restart server.

    Mỗi nhóm là một form riêng: bấm Lưu ở nhóm nào chỉ gửi các ô của nhóm đó,
    nên sửa một chỗ không kéo theo rủi ro ghi đè chỗ khác đang mở ở tab kia.
    """
    khoi = ""
    for g in nhom:
        hang = ""
        for m in g["muc"]:
            gt = m["gia_tri"]
            if m["kieu"] == "bool":
                dieu_khien = (
                    f'<label class="sw"><input type="checkbox" name="{escape(m["code"])}"'
                    f'{" checked" if gt else ""}><span></span>'
                    f'<b>{"Bật" if gt else "Tắt"}</b></label>'
                )
            elif m["chon"]:
                chon = "".join(
                    f'<option value="{escape(c)}"'
                    f'{" selected" if str(gt) == c else ""}>{escape(c)}</option>'
                    for c in m["chon"]
                )
                dieu_khien = f'<select name="{escape(m["code"])}">{chon}</select>'
            else:
                buoc = "1" if m["kieu"] == "int" else "any"
                gioi_han = ""
                if m["nho_nhat"] is not None:
                    gioi_han += f' min="{m["nho_nhat"]:g}"'
                if m["lon_nhat"] is not None:
                    gioi_han += f' max="{m["lon_nhat"]:g}"'
                dieu_khien = (
                    f'<input type="number" step="{buoc}"{gioi_han} '
                    f'name="{escape(m["code"])}" value="{escape(str(gt))}" '
                    'style="max-width:150px">'
                    + (f' <span class="note">{escape(m["don_vi"])}</span>'
                       if m["don_vi"] else "")
                )

            dau = ""
            if m["rieng"]:
                dau = ' <span class="pill">công tắc riêng</span>'
            elif m["da_doi"]:
                dau = (f' <span class="pill warn" title="Mặc định trong .env: '
                       f'{escape(str(m["mac_dinh"]))}">đã đổi</span>')
            hang += (
                f'<tr><td><b>{escape(m["ten"])}</b>{dau}'
                f'<div class="note">{escape(m["mo_ta"])}'
                f'{" · " if m["mo_ta"] else ""}<code>{escape(m["code"].upper())}</code></div></td>'
                f'<td>{dieu_khien}</td>'
                f'<td class="note">{escape(str(m["mac_dinh"])) if m["mac_dinh"] is not None else "—"}</td>'
                "</tr>"
            )
        khoi += f"""
<form class="card" method="post" action="/quan-tri/cai-dat" style="margin-bottom:14px">
  <input type="hidden" name="nhom" value="{escape(g['ma'])}">
  <h3>{escape(g['ten'])}</h3>
  <div class="tblwrap"><table class="tbl">
  <thead><tr><th>Cài đặt</th><th>Giá trị</th><th>Mặc định (.env)</th></tr></thead>
  <tbody>{hang}</tbody></table></div>
  <div style="margin-top:10px;display:flex;gap:8px">
    <button class="btn primary">Lưu nhóm này</button>
    <button class="btn" name="mac_dinh" value="1"
            title="Bỏ mọi thay đổi của nhóm, quay về giá trị trong .env">Trả về mặc định</button>
  </div>
</form>"""

    body = f"""
<div class="card" style="margin-bottom:14px">
  <p class="note" style="margin:0">Đổi ở đây có tác dụng <b>ngay ở lượt chạy kế tiếp</b>
  của worker (chậm nhất khoảng 10 giây) — không phải khởi động lại server. Cột
  <b>Mặc định</b> là giá trị đang khai trong <code>.env</code>; ô nào không đổi thì
  hệ thống dùng đúng giá trị đó. Mọi thay đổi đều vào <a href="/quan-tri/nhat-ky">Nhật ký</a>.</p>
  <p class="note">Token, mật khẩu và chuỗi kết nối <b>cố ý không</b> nằm ở đây — chúng
  chỉ có trong <code>.env</code> trên máy chủ.</p>
</div>
{khoi}
"""
    return _shell("Cài đặt hệ thống", "cai-dat", body, ok, error,
                  sub="Công tắc đồng bộ và nhịp chạy của worker (màn 78)")


# ------------------------------------------------ thẻ Pancake (kho tên/màu thẻ)
_QUYEN_NHAN = {
    "ADMINISTER": ("Quản trị", "ok"),
    "EDIT_PROFILE": ("Biên tập", ""),
    "MODERATE": ("Kiểm duyệt", ""),
}


def _the_pill(tid: int, meta: dict) -> str:
    """Một pill thẻ, dùng lại đúng lớp `.ctag` của màn Tin nhắn cho đồng bộ."""
    mau = (meta.get("color") or "").strip() or "var(--sub)"
    ten = (meta.get("text") or "").strip() or f"Thẻ #{tid}"
    return (f'<span class="ctag" style="--tc:{escape(mau)}" '
            f'title="#{tid} · {escape(ten)}">{escape(ten)}</span>')


def render_the_pancake(pages: list[dict], the: dict[str, dict],
                       moc: dict[str, dict], *, moi_giay: int,
                       ok: str = "", error: str = "") -> str:
    """Màn Quản trị → Thẻ Pancake: kho tên/màu thẻ + nút cập nhật tay.

    pages    — danh sách page từ Pancake (có `role` để biết quyền).
    the      — {page_id: {tag_id: {text,color}}} đang lưu trong kho.
    moc      — {page_id: {luc, so_the, nguon, loi}} lần hỏi API gần nhất.
    moi_giay — mỗi page bao lâu mới hỏi lại (để ghi rõ ra màn hình).
    """
    tong_the = sum(len(v) for v in the.values())
    co_the = sum(1 for v in the.values() if v)
    lan_cuoi = max((m.get("luc") for m in moc.values() if m.get("luc")),
                   default=None)

    hang = ""
    for p in sorted(pages, key=lambda x: str(x.get("name") or "")):
        pid = str(p.get("id") or "")
        cua_page = the.get(pid) or {}
        m = moc.get(pid) or {}
        nhan, tone = _QUYEN_NHAN.get(str(p.get("role") or ""),
                                     (str(p.get("role") or "—"), ""))
        # Xem trước tối đa 12 pill cho khỏi vỡ hàng; còn lại gộp thành "+N".
        ds = list(cua_page.items())[:12]
        pills = "".join(_the_pill(t, mt) for t, mt in ds)
        if len(cua_page) > 12:
            pills += f'<span class="ctag" style="--tc:var(--sub)">+{len(cua_page) - 12}</span>'
        if not cua_page:
            pills = ('<span class="note">chưa có thẻ trong kho</span>'
                     if not m else
                     f'<span class="note">{_e(m.get("loi") or "không lấy được")}</span>')
        hang += (
            f"<tr><td><b>{_e(p.get('name'))}</b>"
            f"<div class=\"note\">{_e(pid)}</div></td>"
            f'<td><span class="pill {tone}">{escape(nhan)}</span></td>'
            f"<td class=\"num\">{len(cua_page) or '—'}</td>"
            f"<td>{_fmt_dt(m.get('luc'))}</td>"
            f'<td><div class="ctags">{pills}</div></td></tr>'
        )

    gio = round(moi_giay / 3600)
    body = f"""
<div class="stats" style="margin-bottom:14px">
  <div class="stat"><div class="s-label">Thẻ đang lưu</div>
    <div class="s-value">{tong_the}</div></div>
  <div class="stat"><div class="s-label">Page có thẻ</div>
    <div class="s-value">{co_the} / {len(pages)}</div></div>
  <div class="stat"><div class="s-label">Cập nhật gần nhất</div>
    <div class="s-value" style="font-size:17px">{_fmt_dt(lan_cuoi)}</div></div>
</div>

<div class="card" style="margin-bottom:14px">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <form method="post" action="/quan-tri/the-pancake/cap-nhat" data-native>
      <button class="btn primary">🔄 Cập nhật thẻ ngay</button>
    </form>
    <p class="note" style="margin:0;flex:1 1 260px">Bình thường mỗi page chỉ hỏi
    Pancake <b>{gio} giờ một lần</b>, mốc lưu trong DB nên khởi động lại server
    cũng không gọi thêm. Bấm nút này là hỏi lại <b>toàn bộ page ngay lập tức</b>
    — mỗi page tốn 1 lời gọi.</p>
  </div>
</div>

<div class="tblwrap card"><table class="tbl">
<thead><tr><th>Page</th><th>Quyền</th><th>Số thẻ</th><th>Hỏi API lần cuối</th>
<th>Thẻ trong kho</th></tr></thead>
<tbody>{hang or '<tr><td colspan="5" class="note">Chưa lấy được danh sách page.</td></tr>'}</tbody>
</table></div>

<p class="note">Kho nằm ở bảng <code>watcher.the_pancake</code> (mốc đồng bộ:
<code>watcher.the_pancake_dong_bo</code>) trong Postgres. Đây là <b>bản sao</b> —
xoá đi thì lượt cập nhật kế tiếp dựng lại đủ. Thẻ đã bị xoá trên Pancake vẫn
được giữ, vì hội thoại cũ còn gắn ID đó.</p>
"""
    return _shell("Thẻ Pancake", "the-pancake", body, ok, error,
                  sub="Kho tên + màu thẻ dùng cho màn Tin nhắn và Hội thoại")
