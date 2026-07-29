"""Khung (shell) dùng chung cho toàn bộ giao diện web.

Mọi trang đều gọi `render_shell(...)` để có cùng một bố cục:

    ┌──────────┬────────────────────────────────┐
    │ sidebar  │ topbar (tiêu đề + tab + nút)   │
    │ (menu    ├────────────────────────────────┤
    │  trái)   │ content (nội dung từng trang)  │
    └──────────┴────────────────────────────────┘

Toàn bộ CSS của dự án nằm ở `_CSS` trong file này (một stylesheet duy nhất),
gồm cả các class dùng riêng cho từng màn hình: form/danh sách dữ liệu bot,
thẻ hội thoại, bong bóng chat... Nhờ vậy các module webview khác chỉ cần dựng
phần thân HTML rồi bọc lại bằng `render_shell`.

Bố cục tự co theo bề rộng: dưới 900px sidebar chuyển thành thanh ngang trên đầu.
"""

from html import escape

# --- Icon dạng SVG inline (dùng currentColor nên tự đổi màu theo trạng thái) ---
_ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/>'
                 '<rect x="14" y="3" width="7" height="5" rx="1"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1"/>'
                 '<rect x="3" y="16" width="7" height="5" rx="1"/>',
    "messages": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.9-.9L3 21'
                'l1.9-5A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>',
    "customers": '<path d="M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
                 '<circle cx="9.5" cy="7" r="4"/>'
                 '<path d="M22 21v-2a4 4 0 0 0-3-3.9"/>'
                 '<path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    "data": '<path d="M12 2a3 3 0 0 0-3 3v.4A3.2 3.2 0 0 0 7 11a3 3 0 0 0 2 5.6V18'
            'a3 3 0 0 0 6 0v-1.4A3 3 0 0 0 17 11a3.2 3.2 0 0 0-2-5.6V5a3 3 0 0 0-3-3z"/>'
            '<path d="M12 2v20"/>',
}

# Menu bên trái: (đường dẫn, nhãn, khoá `active`, tên icon)
MENU: list[tuple[str, str, str, str]] = [
    ("/bang-dieu-khien", "Bảng điều khiển", "dashboard", "dashboard"),
    ("/tin-nhan", "Tin nhắn", "messages", "messages"),
    ("/khach-hang", "Khách hàng", "customers", "customers"),
    ("/data/kich-ban", "Dữ liệu bot", "data", "data"),
]


def _icon(name: str) -> str:
    """Bọc path SVG thành thẻ <svg> 20px, nét theo màu chữ hiện tại."""
    return (
        '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f'{_ICONS.get(name, "")}</svg>'
    )


def _sidebar(active: str) -> str:
    """Menu trái: logo + các mục; mục đang xem được tô đậm."""
    items = ""
    for href, label, key, icon in MENU:
        cls = "nav-item on" if key == active else "nav-item"
        items += f'<a class="{cls}" href="{href}">{_icon(icon)}<span>{label}</span></a>'
    return (
        '<aside class="side">'
        '<a class="brand" href="/bang-dieu-khien">'
        '<span class="logo">FB</span><span class="bname">Sales Bot</span></a>'
        f'<nav class="nav">{items}</nav>'
        '<div class="side-foot">Pancake + RAG · nội bộ</div>'
        "</aside>"
    )


def tabs_bar(items: list[tuple[str, str, str]], active: str) -> str:
    """Dải tab con trong 1 mục menu. `items` = [(href, nhãn, khoá)]."""
    html = ""
    for href, label, key in items:
        cls = "tab on" if key == active else "tab"
        html += f'<a class="{cls}" href="{href}">{escape(label)}</a>'
    return f'<nav class="tabs">{html}</nav>'


def flash(ok: str = "", error: str = "") -> str:
    """Dải thông báo kết quả (xanh = thành công, đỏ = lỗi)."""
    if ok:
        return f'<div class="flash ok">✓ {escape(ok)}</div>'
    if error:
        return f'<div class="flash err">✕ {escape(error)}</div>'
    return ""


def stat(
    label: str, value: str, hint: str = "", tone: str = "", href: str = ""
) -> str:
    """Ô số liệu cho Bảng điều khiển. `tone` = '' | 'ok' | 'err' | 'warn'.

    href — nếu có, cả ô trở thành liên kết bấm được (hiện chevron ở góc phải).
    """
    hint_html = f'<div class="s-hint">{hint}</div>' if hint else ""
    tone_cls = f" {tone}" if tone else ""
    inner = (
        f'<div class="s-label">{escape(label)}</div>'
        f'<div class="s-value">{value}</div>{hint_html}'
    )
    if href:
        return f'<a class="stat link{tone_cls}" href="{escape(href)}">{inner}</a>'
    return f'<div class="stat{tone_cls}">{inner}</div>'


def render_shell(
    title: str,
    active: str,
    body: str,
    heading: str = "",
    sub: str = "",
    tabs: str = "",
    actions: str = "",
    script: str = "",
    full: bool = False,
) -> str:
    """Ghép 1 trang HTML hoàn chỉnh.

    title   — tên trên tab trình duyệt
    active  — khoá mục menu đang chọn (xem MENU)
    body    — HTML phần nội dung
    heading — tiêu đề lớn trên topbar (mặc định = title)
    sub     — dòng mô tả nhỏ dưới tiêu đề (đã là HTML)
    tabs    — dải tab con (dùng `tabs_bar`)
    actions — HTML nút/điều khiển đặt bên phải topbar
    script  — JS riêng của trang, thêm vào cuối (vd polling ở màn Tin nhắn).
              Được đánh dấu `data-page-script` để `_NAV_JS` tìm và chạy lại
              sau mỗi lần điều hướng bằng AJAX (xem _NAV_JS).
    full    — True: nội dung chiếm hết chiều cao, tự cuộn (dùng cho màn chat)
    """
    heading = heading or title
    sub_html = f'<div class="page-sub">{sub}</div>' if sub else ""
    actions_html = f'<div class="page-actions">{actions}</div>' if actions else ""
    page_script_html = f"<script data-page-script>{script}</script>" if script else ""
    script_html = f"<script>{_NAV_JS}</script>{page_script_html}"
    content_cls = "content full" if full else "content"

    return (
        "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} — FB Sales Bot</title>"
        f"<style>{_CSS}</style></head><body>"
        + _sidebar(active)
        + '<main class="main"><header class="topbar">'
        '<div class="page-head">'
        f'<h1>{escape(heading)}</h1>{sub_html}</div>{actions_html}'
        f"</header>{tabs}"
        f'<div class="{content_cls}">{body}</div>'
        "</main>"
        + script_html
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Stylesheet dùng chung. Để nguyên dạng chuỗi thường (không f-string) nên không
# phải nhân đôi dấu ngoặc nhọn của CSS.
# ---------------------------------------------------------------------------
_CSS = """
/* Chuyển trang mượt: trình duyệt crossfade giữa 2 lần tải thay vì chớp trắng.
   Đặt tên ổn định cho các khối lặp lại y hệt ở mọi trang (sidebar/topbar/tab)
   để chúng được giữ nguyên vị trí, chỉ phần nội dung bên dưới mới crossfade. */
@view-transition{navigation:auto}
.side{view-transition-name:side}
.topbar{view-transition-name:topbar}
.tabs{view-transition-name:tabs}
:root{
  --bg:#f4f5f7; --card:#fff; --text:#111827; --sub:#6b7280; --border:#e4e7eb;
  --accent:#2563eb; --soft:#eef4ff; --ok:#16a34a; --err:#dc2626; --warn:#d97706;
  --side:#111827; --side-tx:#9aa4b2; --side-on:#1f2937; --in:#eceef1; --out:#2563eb;
  --shadow:0 1px 2px rgba(16,24,40,.06);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0d1117; --card:#161b22; --text:#e6edf3; --sub:#9198a1; --border:#30363d;
    --accent:#4493f8; --soft:#132039; --ok:#3fb950; --err:#f85149; --warn:#d29922;
    --side:#010409; --side-tx:#8b949e; --side-on:#161b22; --in:#21262d; --out:#2f6fed;
    --shadow:none;
  }
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; display:flex; background:var(--bg); color:var(--text); line-height:1.45;
  font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif; font-size:14px;
}
a{color:var(--accent)}

/* ---------- sidebar ---------- */
.side{
  flex:0 0 236px; width:236px; background:var(--side); color:var(--side-tx);
  position:sticky; top:0; height:100vh; display:flex; flex-direction:column;
  padding:16px 12px;
}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:#fff;
  padding:6px 8px 16px}
.logo{width:32px;height:32px;border-radius:9px;background:var(--accent);
  display:grid;place-items:center;font-weight:800;font-size:13px;color:#fff}
.bname{font-weight:700;font-size:15px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav-item{
  display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:9px;
  color:var(--side-tx);text-decoration:none;font-size:14px;font-weight:500;
}
.nav-item:hover{background:var(--side-on);color:#fff}
.nav-item.on{background:var(--side-on);color:#fff;font-weight:600;
  box-shadow:inset 3px 0 0 var(--accent)}
.ico{width:19px;height:19px;flex:0 0 auto}
.side-foot{margin-top:auto;font-size:11px;color:var(--side-tx);opacity:.6;padding:8px}

/* ---------- khung phải ---------- */
.main{flex:1;min-width:0;display:flex;flex-direction:column;min-height:100vh}
.topbar{
  position:sticky;top:0;z-index:6;background:var(--card);
  border-bottom:1px solid var(--border);padding:14px 26px;
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;
}
.page-head{min-width:0}
.topbar h1{font-size:18px;margin:0;font-weight:650}
.page-sub{color:var(--sub);font-size:12.5px;margin-top:2px}
.page-actions{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.content{padding:22px 26px 40px;width:100%;max-width:1280px}
.content.full{padding:0;max-width:none;flex:1;min-height:0;display:flex}

/* ---------- tab con ---------- */
.tabs{display:flex;gap:6px;padding:10px 26px 0;background:var(--card);
  border-bottom:1px solid var(--border);flex-wrap:wrap}
.tab{padding:8px 14px;border-radius:8px 8px 0 0;text-decoration:none;
  color:var(--sub);font-size:13.5px;font-weight:500;border-bottom:2px solid transparent;
  margin-bottom:-1px}
.tab:hover{color:var(--text)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:650}

/* ---------- thành phần chung ---------- */
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:16px;box-shadow:var(--shadow)}
.intro{color:var(--sub);font-size:13px;margin:0 0 14px}
.grp{font-size:12px;margin:22px 0 8px;color:var(--sub);text-transform:uppercase;
  letter-spacing:.04em;font-weight:650}
.count{background:var(--border);color:var(--text);border-radius:10px;padding:1px 8px;
  font-size:11.5px;margin-left:4px;text-transform:none;letter-spacing:0}
.empty{background:var(--card);border:1px dashed var(--border);border-radius:12px;
  padding:24px;color:var(--sub);text-align:center}
.flash{padding:9px 12px;border-radius:9px;font-size:13px;margin-bottom:14px}
.flash.ok{background:color-mix(in srgb,var(--ok) 14%,transparent);color:var(--ok)}
.flash.err{background:color-mix(in srgb,var(--err) 14%,transparent);color:var(--err)}
.note{color:var(--sub);font-size:12px;margin:10px 0 0}
code{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--bg);
  padding:1px 5px;border-radius:5px}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);
  background:var(--card);color:var(--text);border-radius:8px;padding:7px 13px;
  text-decoration:none;font-size:13px;font-weight:550;cursor:pointer}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{opacity:.9;color:#fff}
select,.inp{border:1px solid var(--border);background:var(--card);color:var(--text);
  border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}
.live{display:inline-flex;align-items:center;gap:5px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);
  box-shadow:0 0 0 0 rgba(22,163,74,.6);animation:pulse 1.8s infinite}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(22,163,74,.5)}
  70%{box-shadow:0 0 0 6px rgba(22,163,74,0)}
  100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}
}

/* ---------- form ---------- */
.form label{display:block;font-size:12.5px;color:var(--sub);margin-bottom:10px}
.form input,.form textarea,.form select{display:block;width:100%;margin-top:4px;
  padding:8px 10px;border:1px solid var(--border);border-radius:8px;font:inherit;
  font-size:14px;background:var(--bg);color:var(--text);resize:vertical}
.form input:focus,.form textarea:focus{outline:2px solid var(--soft);
  border-color:var(--accent)}
.grid2{display:flex;gap:12px;flex-wrap:wrap}
.grid2>label{flex:1 1 200px}
.form button{border:0;background:var(--accent);color:#fff;border-radius:8px;
  padding:9px 18px;font:inherit;font-weight:600;cursor:pointer}
.check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--sub);
  margin-bottom:12px}
.check input{width:auto;margin:0}

/* ---------- danh sách dòng dữ liệu ---------- */
.list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.row{display:flex;gap:12px;align-items:flex-start;background:var(--card);
  border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.step{flex:0 0 auto;min-width:28px;height:28px;border-radius:8px;background:var(--accent);
  color:#fff;font-weight:700;font-size:13px;display:grid;place-items:center}
.rbody{flex:1;min-width:0}
.rtext{font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.qa .q{font-weight:600;font-size:14px;overflow-wrap:anywhere}
.qa .a{font-size:14px;margin-top:2px;overflow-wrap:anywhere}
.rmeta{color:var(--sub);font-size:12px;margin-top:4px}
.del button{border:1px solid var(--border);background:transparent;color:var(--err);
  border-radius:8px;width:30px;height:30px;cursor:pointer;font-size:14px;line-height:1}
.del button:hover{border-color:var(--err)}

/* ---------- màn "Thử tin nhắn" ---------- */
.mono{font-size:13px}
.mono .lbl{color:var(--sub);font-size:12px;margin-top:8px}
.qline{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--bg);
  border:1px solid var(--border);border-radius:8px;padding:6px 9px;margin-bottom:6px;
  overflow-x:auto;white-space:nowrap}
.score{flex:0 0 auto;width:92px;text-align:right}
.snum{font-size:12px;color:var(--sub);font-family:ui-monospace,Consolas,monospace}
.sbar{display:block;height:5px;border-radius:3px;background:var(--border);
  margin-top:4px;overflow:hidden}
.sbar i{display:block;height:100%;border-radius:3px}
.answer{background:color-mix(in srgb,var(--accent) 10%,transparent);
  border-left:3px solid var(--accent);border-radius:8px;padding:12px 14px;
  font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
details{margin-top:10px;font-size:13px;color:var(--sub)}
summary{cursor:pointer}
.prompt{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:10px;margin-top:8px;font-size:12px;white-space:pre-wrap;overflow-x:auto;
  font-family:ui-monospace,Consolas,monospace;color:var(--text)}

/* ---------- bảng điều khiển ---------- */
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;box-shadow:var(--shadow)}
.s-label{color:var(--sub);font-size:12px;font-weight:550}
.s-value{font-size:24px;font-weight:700;margin-top:4px;letter-spacing:-.02em}
.s-hint{color:var(--sub);font-size:11.5px;margin-top:3px}
.stat.ok .s-value{color:var(--ok)}
.stat.err .s-value{color:var(--err)}
.stat.warn .s-value{color:var(--warn)}
a.stat.link{position:relative;display:block;text-decoration:none;color:inherit;
  transition:border-color .15s}
a.stat.link:hover{border-color:var(--accent)}
a.stat.link::after{content:"›";position:absolute;top:12px;right:14px;
  color:var(--sub);font-size:18px;line-height:1}
a.stat.link:hover::after{color:var(--accent)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--border);font-size:13px}
.kv:last-child{border-bottom:0}
.kv .k{color:var(--sub)}
.kv .v{text-align:right;overflow-wrap:anywhere}
.pill{font-size:11px;padding:2px 9px;border-radius:20px;border:1px solid var(--border);
  color:var(--sub)}
.pill.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}
.pill.err{color:var(--err);border-color:color-mix(in srgb,var(--err) 40%,transparent)}
.links{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
/* Danh sách page hiện ngay trên bảng điều khiển: ẩn, bấm ô stat (#ds-page) mới mở */
.ds-page{display:none;margin-top:12px}
.ds-page:target{display:block}
.ds-page-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
/* Dòng page trong danh sách: nhìn phát biết page nào đang chạy.
   BẬT = vạch xanh bên trái, chữ rõ. TẮT = xám mờ, avatar mất màu. */
.pgrow{border-left:3px solid transparent;transition:opacity .15s linear}
.pgrow.on{border-left-color:var(--ok)}
.pgrow.off{background:var(--bg);border-left-color:var(--border)}
.pgrow.off .avatar{filter:grayscale(1);opacity:.5}
.pgrow.off .name{color:var(--sub);font-weight:500}
.pgrow.off .rmeta{opacity:.7}
.pgrow.off .btn{opacity:.6}
.pgstate{font-size:11px;font-weight:700;margin-left:6px;letter-spacing:.02em}
.pgrow.on .pgstate{color:var(--ok)}
.pgrow.off .pgstate{color:var(--sub)}
/* Công tắc BẬT/TẮT page: BẬT = xanh đặc, TẮT = xám nhạt */
.pgsw{border:1px solid var(--border);background:var(--card);color:var(--sub);
  border-radius:20px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer;
  white-space:nowrap}
.pgsw.on{background:var(--ok);border-color:var(--ok);color:#fff}
.pgsw.off{background:var(--bg);border-color:var(--border);color:var(--sub)}
.pgsw:hover{opacity:.9}

/* ---------- thẻ page / hội thoại / khách ---------- */
.avatar{flex:0 0 auto;width:40px;height:40px;border-radius:50%;display:grid;
  place-items:center;color:#fff;font-weight:700;font-size:17px}
.avatar.sm{width:30px;height:30px;font-size:13px}
.info{min-width:0;flex:1}
.name{font-weight:600;color:var(--text);text-decoration:none;display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
a.name:hover{color:var(--accent)}
.sub{color:var(--sub);font-size:12px;margin-top:1px}
.badges{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--border);
  color:var(--sub)}
.badge.platform{text-transform:capitalize;color:var(--accent)}
.unread{background:var(--err);color:#fff;border-radius:20px;font-size:11px;
  font-weight:700;padding:2px 8px;min-width:20px;text-align:center}
.snippet{color:var(--sub);font-size:13px;margin-top:2px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
/* Tên page trên thẻ hội thoại — CHỈ hiện ở hộp thư gộp (page_id=ALL) */
.cpage{color:var(--accent);font-size:11px;font-weight:600;margin-top:1px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.9}
.time{color:var(--sub);font-size:12px;margin-left:auto;flex:0 0 auto;white-space:nowrap}
.card.link,.card.link-wrap{display:flex;gap:12px;align-items:center;
  transition:border-color .15s}
.card.link{text-decoration:none;color:inherit;align-items:flex-start}
.card.link:hover,.card.link-wrap:hover{border-color:var(--accent)}
.crow{display:flex;align-items:baseline;gap:8px}
/* thẻ (tag) của hội thoại, hiện ngay dưới tên để dễ so sánh */
.ctags{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}
.ctag{font-size:10px;font-weight:700;line-height:1.7;padding:0 6px;border-radius:9px;
  color:var(--tc);border:1px solid var(--tc);
  background:color-mix(in srgb,var(--tc) 13%,transparent)}

/* ---------- lưới danh sách page (tối đa 4 cột, giảm dần theo màn hình) ---------- */
.pages-grid{list-style:none;margin:0;padding:0;display:grid;gap:12px;
  grid-template-columns:repeat(4,minmax(0,1fr))}
.page-card{display:flex;flex-direction:column;gap:10px;padding:14px;
  transition:border-color .15s}
.page-card:hover{border-color:var(--accent)}
.pc-head{display:flex;gap:11px;align-items:center;min-width:0}
.page-card .info{min-width:0;flex:1}
.page-card .sub{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.page-card .badges{margin-top:0}
.page-card .btn{margin-top:auto;justify-content:center}
@media (max-width:1080px){.pages-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:800px){.pages-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.pages-grid{grid-template-columns:1fr}}

/* ---------- bảng ---------- */
.tbl{width:100%;border-collapse:collapse;background:var(--card);
  border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tbl th,.tbl td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);
  font-size:13.5px;vertical-align:middle}
.tbl th{color:var(--sub);font-size:11.5px;text-transform:uppercase;letter-spacing:.03em;
  background:var(--bg);font-weight:650}
.tbl tr:last-child td{border-bottom:0}
.tbl tr:hover td{background:var(--soft)}
.twrap{overflow-x:auto;border-radius:12px}

/* ---------- màn tin nhắn 2 cột ---------- */
.inbox{display:flex;flex:1;min-height:0;width:100%}
.inbox-list{flex:0 0 330px;border-right:1px solid var(--border);background:var(--card);
  display:flex;flex-direction:column;min-height:0}
.inbox-list .lhead{padding:12px 16px;border-bottom:1px solid var(--border);
  color:var(--sub);font-size:12px;display:flex;align-items:center;gap:8px}
.lhint{color:var(--sub);font-size:11px;border:1px solid var(--border);
  border-radius:20px;padding:1px 8px}
.inbox-list .lbody{overflow-y:auto;padding:8px;flex:1;min-height:0}
.inbox-list .list{gap:4px}
.inbox-list .card{border-color:transparent;box-shadow:none;padding:9px 10px;
  border-radius:10px}
.inbox-list .card:hover{background:var(--bg)}
.inbox-list .card.on{background:var(--soft);border-color:var(--accent)}
/* ---------- thanh lọc theo thẻ (giống Pancake) ---------- */
.tagbar{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px;
  border-bottom:1px solid var(--border);background:var(--card);
  max-height:108px;overflow-y:auto}
.tchip{display:inline-flex;align-items:center;gap:6px;text-decoration:none;
  font-size:12px;font-weight:550;color:var(--text);border:1px solid var(--border);
  background:var(--card);border-radius:20px;padding:3px 10px;line-height:1.7}
.tchip:hover{border-color:var(--tc,var(--accent))}
.tchip .tdot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;
  background:var(--tc,var(--sub))}
.tchip .tnum{color:var(--sub);font-size:11px;font-weight:600}
.tchip.on{border-color:var(--tc,var(--accent));
  background:color-mix(in srgb,var(--tc,var(--accent)) 15%,transparent)}
.tchip.on .tnum{color:var(--text)}
.tchip.all{color:var(--sub)}
.tchip.all.on{color:var(--accent);border-color:var(--accent);background:var(--soft)}
.pane{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}
.thread{flex:1;padding:18px 22px;display:flex;flex-direction:column;gap:4px;
  overflow-y:auto;min-height:0}
.msg{display:flex;flex-direction:column;max-width:min(72%,560px);margin-top:8px}
.msg.in{align-self:flex-start;align-items:flex-start}
.msg.out{align-self:flex-end;align-items:flex-end}
.bubble{padding:8px 12px;border-radius:16px;font-size:14px;white-space:pre-wrap;
  word-wrap:break-word;overflow-wrap:anywhere}
.msg.in .bubble{background:var(--in);color:var(--text);border-bottom-left-radius:4px}
.msg.out .bubble{background:var(--out);color:#fff;border-bottom-right-radius:4px}
.att{display:block;max-width:220px;max-height:220px;border-radius:10px;margin-top:6px}
.att-link{display:inline-block;margin-top:6px;font-size:13px}
.mtime{color:var(--sub);font-size:11px;margin:2px 4px 0}
.chead{padding:12px 22px;border-bottom:1px solid var(--border);background:var(--card);
  display:flex;align-items:center;gap:10px}
.suggest-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:10px 16px 0;background:var(--card)}
.suggest-bar .btn:disabled{opacity:.6;cursor:default}
.shint{color:var(--sub);font-size:12.5px;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.shint.warn{color:var(--warn)}
/* Bảng "Trích tri thức": thanh đầu có nút ✕ đóng (panel chen giữa khung chat và
   ô soạn tin nên phải luôn đóng được, dù đã lưu hay chưa) */
.ext-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.ext-head .ext-close{margin-left:auto;flex:0 0 auto;padding:4px 10px;font-size:12px}
.composer{border-top:1px solid var(--border);background:var(--card);padding:12px 16px;
  display:flex;gap:10px;align-items:flex-end}
.composer textarea{flex:1;resize:none;border:1px solid var(--border);border-radius:20px;
  padding:10px 15px;font:inherit;font-size:14px;background:var(--bg);color:var(--text);
  max-height:130px}
.composer button{flex:0 0 auto;border:0;background:var(--accent);color:#fff;
  border-radius:20px;padding:10px 20px;font:inherit;font-weight:600;cursor:pointer}
.placeholder{flex:1;display:grid;place-items:center;color:var(--sub);padding:40px;
  text-align:center}

/* ---------- co theo màn hình nhỏ ---------- */
@media (max-width:900px){
  body{flex-direction:column}
  .side{width:100%;flex:none;height:auto;position:static;padding:10px 12px;
    flex-direction:row;align-items:center;gap:12px}
  .brand{padding:0}
  .side-foot{display:none}
  .nav{flex-direction:row;overflow-x:auto;gap:4px;margin-left:auto}
  .nav-item span{display:none}
  .nav-item{padding:9px 12px}
  .nav-item.on{box-shadow:inset 0 -3px 0 var(--accent)}
  .topbar,.tabs{padding-left:16px;padding-right:16px}
  .content{padding:16px}
  .inbox{flex-direction:column}
  .inbox-list{flex:0 0 auto;max-height:38vh;border-right:0;
    border-bottom:1px solid var(--border)}
}

/* ---------- tab "Thử API" (bố cục kiểu Postman) ---------- */
.pm{gap:12px}
.pm-bar{display:flex;gap:0;align-items:stretch;flex-wrap:wrap}
.pm-method{flex:0 0 auto;width:96px;font-weight:700;border-radius:10px 0 0 10px;
  border-right:none}
.pm-base{display:flex;align-items:center;padding:0 10px;font-size:12.5px;
  font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--sub);
  background:var(--bg);border:1px solid var(--border);border-left:none;
  border-right:none;white-space:nowrap}
.pm-path{flex:1 1 260px;min-width:0;border-radius:0;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.pm-send{flex:0 0 auto;border-radius:0 10px 10px 0;padding:0 22px}
.pm-opts{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.pm-inline{display:flex;align-items:center;gap:6px;font-size:13px;margin:0}
.pm-inline .inp{width:auto;min-width:130px}
.pm-kv-head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.pm-kv-head .btn{margin-left:auto;padding:3px 10px;font-size:12px}
.pm-row{display:flex;gap:6px;margin-bottom:6px}
.pm-row .inp{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
.pm-row .inp:first-child{flex:0 0 34%}
.pm-row .inp:nth-child(2){flex:1;min-width:0}
.pm-del{flex:0 0 auto;width:34px;border:1px solid var(--border);background:transparent;
  color:var(--err);border-radius:8px;cursor:pointer;font-size:13px;line-height:1}
.pm-del:hover{background:var(--bg)}
.pm-status{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pm-url{font-size:12.5px;overflow-wrap:anywhere;margin-bottom:10px}
.pm-url code{font-size:12.5px}
.pm-params{display:flex;flex-direction:column;gap:4px}
.pm-prow{display:flex;gap:10px;align-items:baseline;font-size:12.5px;
  padding:4px 0;border-bottom:1px dashed var(--border)}
.pm-prow:last-child{border-bottom:none}
.pm-prow code{flex:0 0 34%;color:var(--accent)}
.pm-prow span{flex:1;min-width:0;overflow-wrap:anywhere;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.pm-prow code.pm-secret{color:var(--warn)}
/* Bảng tra cứu của trang test: token đầy đủ + page ID bấm được */
.pm-ref>summary{cursor:pointer;font-weight:600;font-size:14px;list-style:none;
  display:flex;align-items:center;gap:8px}
.pm-ref>summary::-webkit-details-marker{display:none}
.pm-ref>summary::before{content:"▸";color:var(--sub);font-size:12px}
.pm-ref[open]>summary::before{content:"▾"}
.pm-ref .lbl{margin-top:0}
.pm-ref .tblwrap{max-height:280px;overflow:auto}
.pm-copy{display:flex;gap:8px;align-items:flex-start}
.pm-copy code{flex:1;min-width:0;overflow-wrap:anywhere;font-size:12px;
  background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 10px}
.pm-copy .btn{flex:0 0 auto;padding:4px 12px;font-size:12px}
code.pm-pid{cursor:pointer;color:var(--accent);border-bottom:1px dashed var(--accent)}
code.pm-pid:hover{background:var(--soft)}
.pm-json{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;margin:0;max-height:60vh;overflow:auto;font-size:12.5px;
  line-height:1.55;font-family:ui-monospace,Menlo,Consolas,monospace;
  white-space:pre;tab-size:2}
@media (max-width:700px){
  .pm-base{display:none}
  .pm-method,.pm-path,.pm-send{border-radius:10px}
  .pm-method{border-right:1px solid var(--border);width:100%}
  .pm-path{border:1px solid var(--border);margin:6px 0}
  .pm-send{width:100%}
}

/* ---------- điều hướng kiểu AJAX (_NAV_JS) ---------- */
html.pjax-loading{cursor:progress}
html.pjax-loading .main{opacity:.55;transition:opacity .15s linear}
"""


# ---------------------------------------------------------------------------
# Điều hướng kiểu SPA (PJAX): chặn click link nội bộ + submit form, gọi fetch
# tới CHÍNH route đó (server vẫn trả nguyên trang HTML như cũ, không cần thêm
# route/endpoint riêng cho từng màn), rồi chỉ thay <title>, .side (menu trái)
# và .main (topbar + tab + nội dung) của trang HIỆN TẠI thay vì để trình duyệt
# điều hướng thật — nhờ vậy sidebar/topbar không bị trình duyệt huỷ và vẽ lại
# (đó chính là nguồn gốc hiện tượng nhấp nháy khi chuyển trang/tab).
#
# Một số trang có thêm JS riêng (script[data-page-script], vd polling ở màn
# Tin nhắn) — đoạn này KHÔNG tự chạy lại khi ta gán innerHTML nên phải tự tạo
# lại thẻ <script> để trình duyệt thực thi sau mỗi lần thay nội dung; các
# setInterval của lần trước cũng phải tự huỷ (qua window.__pjaxTimers) kẻo
# rò rỉ khi người dùng ra vào lại cùng 1 trang nhiều lần.
_NAV_JS = """
(function(){
  // Đường dẫn hiện tại KHÔNG tính #fragment — dùng để phân biệt "đổi trang
  // thật" với "chỉ nhảy tới neo trong trang" ở handler popstate bên dưới.
  var here = location.pathname + location.search;

  function sameOrigin(url){
    try { return new URL(url, location.href).origin === location.origin; }
    catch (e) { return false; }
  }

  function runPageScript(doc){
    (window.__pjaxTimers || []).forEach(clearInterval);
    window.__pjaxTimers = [];
    var old = document.querySelector('script[data-page-script]');
    if (old) old.remove();
    var fresh = doc.querySelector('script[data-page-script]');
    if (fresh && fresh.textContent.trim()) {
      var s = document.createElement('script');
      s.setAttribute('data-page-script', '');
      s.textContent = fresh.textContent;
      document.body.appendChild(s);
    }
  }

  function applyDoc(doc, url){
    document.title = doc.title;
    var newSide = doc.querySelector('.side');
    var newMain = doc.querySelector('.main');
    var curSide = document.querySelector('.side');
    var curMain = document.querySelector('.main');
    if (newSide && curSide) curSide.innerHTML = newSide.innerHTML;
    if (newMain && curMain) curMain.innerHTML = newMain.innerHTML;
    runPageScript(doc);
    window.scrollTo({top: 0});
    var hash = (url.split('#')[1]) || '';
    var target = hash && document.getElementById(hash);
    if (target) target.scrollIntoView();
  }

  function swap(doc, url){
    if (document.startViewTransition) {
      document.startViewTransition(function(){ applyDoc(doc, url); });
    } else {
      applyDoc(doc, url);
    }
  }

  function go(url, opts, push){
    document.documentElement.classList.add('pjax-loading');
    fetch(url, opts || {})
      .then(function(r){
        return r.text().then(function(html){ return {html: html, url: r.url}; });
      })
      .then(function(res){
        var doc = new DOMParser().parseFromString(res.html, 'text/html');
        swap(doc, res.url);
        if (push) history.pushState({pjax: true}, '', res.url);
        here = location.pathname + location.search;
      })
      .catch(function(){ location.href = url; })
      .then(function(){ document.documentElement.classList.remove('pjax-loading'); });
  }

  // Click link nội bộ -> AJAX thay vì điều hướng thật. Bỏ qua: mở tab mới
  // (Ctrl/Cmd/Shift/giữa chuột), target khác _self, link tải file, neo cùng
  // trang (#...), mailto/tel, hoặc khác origin.
  document.addEventListener('click', function(e){
    if (e.defaultPrevented || e.button !== 0 ||
        e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]');
    if (!a || a.target || a.hasAttribute('download')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(mailto|tel):/i.test(href)) return;
    if (!sameOrigin(href)) return;
    e.preventDefault();
    go(href, {cache: 'no-store'}, true);
  });

  // Submit form (GET hoặc POST) -> AJAX. e.defaultPrevented tôn trọng các
  // handler khác chạy trước (vd confirm() huỷ ở nút Xoá, hoặc trang đã tự xử
  // lý AJAX riêng như công tắc BẬT/TẮT page ở Bảng điều khiển).
  document.addEventListener('submit', function(e){
    if (e.defaultPrevented) return;
    var f = e.target;
    // ĐỌC QUA getAttribute, KHÔNG dùng f.method / f.action trực tiếp: form có
    // [LegacyOverrideBuiltIns] nên một ô <input name="method"> (hay "action",
    // "target"...) sẽ CHE property gốc — f.method trả về thẻ <select> chứ không
    // phải chuỗi, gọi .toLowerCase() là ném lỗi ngay sau preventDefault() và
    // form không bao giờ được gửi đi.
    var action = f.getAttribute('action') || location.pathname;
    var verb = (f.getAttribute('method') || 'get').toLowerCase();
    if (f.getAttribute('target') || !sameOrigin(action)) return;
    e.preventDefault();
    var qs = new URLSearchParams(new FormData(f)).toString();
    if (verb === 'post') {
      go(action, {
        method: 'POST', body: qs,
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      }, true);
    } else {
      var base = action.split('?')[0];
      go(base + (qs ? '?' + qs : ''), {cache: 'no-store'}, true);
    }
  });

  // <select data-nav-tpl="/tin-nhan?page_id="> đổi lựa chọn -> AJAX (thay vì
  // gán thẳng location.href khiến trình duyệt điều hướng thật).
  document.addEventListener('change', function(e){
    var tpl = e.target.getAttribute && e.target.getAttribute('data-nav-tpl');
    if (tpl == null) return;
    go(tpl + encodeURIComponent(e.target.value), {cache: 'no-store'}, true);
  });

  // Back/Forward: trang đã đổi qua AJAX nên không có bfcache riêng -> tải lại
  // nội dung cho khớp URL, vẫn không đụng sidebar/topbar (không push state mới).
  //
  // ⚠ Bấm link neo trong trang (href="#...") CŨNG phát 'popstate' trên
  // Chrome/Safari (fragment navigation là một mục lịch sử mới của cùng tài
  // liệu). Nếu không lọc, mỗi lần bấm neo là tải lại + gán innerHTML cho .main
  // -> phần tử đích bị dựng mới nên `:target` hết khớp: panel "Danh sách page"
  // ở Bảng điều khiển vừa hiện ra đã tự đóng lại ngay.
  // => Chỉ đổi mỗi #fragment thì để trình duyệt tự xử lý, không tải lại gì cả.
  window.addEventListener('popstate', function(){
    var now = location.pathname + location.search;
    if (now === here) return;
    here = now;
    go(location.href, {cache: 'no-store'}, false);
  });
})();
"""
