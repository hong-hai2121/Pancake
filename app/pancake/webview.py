"""Dựng HTML cho webview hiển thị danh sách page (server-side render)."""

from datetime import datetime, timezone
from html import escape
from urllib.parse import urlencode

# Bảng màu cho avatar chữ cái đầu (ổn định theo id).
_AVATAR_COLORS = [
    "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
    "#ca8a04", "#16a34a", "#0891b2", "#4f46e5", "#0d9488",
]


def _avatar(page: dict) -> str:
    """Ô avatar tròn hiển thị chữ cái đầu của tên; màu chọn ổn định theo id."""
    name = page.get("name") or "?"
    initial = escape(name.strip()[:1].upper() or "?")
    # Băm id -> chỉ số màu: cùng 1 page luôn ra cùng 1 màu.
    idx = sum(ord(c) for c in page.get("id", "0")) % len(_AVATAR_COLORS)
    color = _AVATAR_COLORS[idx]
    return (
        f'<span class="avatar" style="background:{color}">{initial}</span>'
    )


def _page_card(page: dict) -> str:
    """Dựng 1 thẻ <li> cho một page trong danh sách (avatar + tên + badge)."""
    name = escape(page["name"])
    pid = escape(page["id"])
    username = page.get("username")
    role = page.get("role")
    platform = escape(page.get("platform", "unknown"))

    fb_url = f"https://facebook.com/{escape(str(username or page['id']))}"
    sub_bits = [f'ID: {pid}']
    if username:
        sub_bits.append(f'@{escape(str(username))}')
    subtitle = " · ".join(sub_bits)

    badges = [f'<span class="badge platform">{platform}</span>']
    if role:
        badges.append(f'<span class="badge role">{escape(str(role))}</span>')
    badges_html = "".join(badges)

    return f"""
      <li class="card">
        {_avatar(page)}
        <div class="info">
          <a class="name" href="{fb_url}" target="_blank" rel="noopener">{name}</a>
          <div class="sub">{subtitle}</div>
          <div class="badges">{badges_html}</div>
        </div>
      </li>"""


def _fmt_exp(exp) -> str:
    """Đổi timestamp (giây, epoch) hết hạn token -> chuỗi ngày dd/mm/yyyy.

    Trả "" nếu không có hoặc không parse được (để chỗ hiển thị bỏ qua).
    """
    if not exp:
        return ""
    try:
        dt = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return ""
    return dt.strftime("%d/%m/%Y")


def render_pages(pages: list[dict], owner: dict | None = None) -> str:
    """Trang HTML hoàn chỉnh liệt kê các page, gom theo nhóm."""
    owner = owner or {}
    total = len(pages)

    # Gom theo nhóm, giữ thứ tự xuất hiện.
    groups: dict[str, list[dict]] = {}
    for p in pages:
        groups.setdefault(p["group_label"], []).append(p)

    sections = []
    for label, items in groups.items():
        cards = "".join(_page_card(p) for p in items)
        sections.append(
            f'<h2 class="group">{escape(label)} '
            f'<span class="count">{len(items)}</span></h2>'
            f'<ul class="list">{cards}</ul>'
        )
    body = "".join(sections) or '<p class="empty">Không có page nào.</p>'

    owner_line = ""
    if owner.get("name"):
        exp = _fmt_exp(owner.get("exp"))
        exp_html = f' · token hết hạn {exp}' if exp else ""
        owner_line = (
            f'<div class="owner">Tài khoản: <b>{escape(str(owner["name"]))}</b>'
            f'{exp_html}</div>'
        )

    return _PAGE_TEMPLATE.format(total=total, owner=owner_line, body=body)


def _parse_dt(iso: str):
    """Parse chuỗi ISO của Pancake -> datetime (gắn UTC nếu thiếu tzinfo).

    Trả None nếu rỗng/sai định dạng.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _relative_time(iso: str) -> str:
    """Đổi thời điểm -> chuỗi tương đối tiếng Việt ("5 phút trước", "2 ngày trước")."""
    dt = _parse_dt(iso)
    if not dt:
        return ""
    # Số giây tính từ lúc đó tới bây giờ; rồi quy về đơn vị lớn dần.
    secs = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if secs < 60:
        return "vừa xong"
    mins = secs // 60
    if mins < 60:
        return f"{mins} phút trước"
    hours = mins // 60
    if hours < 24:
        return f"{hours} giờ trước"
    days = hours // 24
    if days < 30:
        return f"{days} ngày trước"
    months = days // 30
    if months < 12:
        return f"{months} tháng trước"
    return f"{days // 365} năm trước"


def _fmt_dt(iso: str) -> str:
    """Đổi thời điểm -> chuỗi tuyệt đối "HH:MM · dd/mm/yyyy" (dùng cho tooltip)."""
    dt = _parse_dt(iso)
    return dt.strftime("%H:%M · %d/%m/%Y") if dt else ""


def _conv_card(conv: dict, page_id: str) -> str:
    """Dựng 1 thẻ hội thoại (link bấm vào để mở trang chat), có avatar, tên,
    tin nhắn cuối, thời gian tương đối và badge số tin / chưa đọc."""
    name = escape(conv["name"])
    who = {"name": conv["name"], "id": conv.get("fb_id") or conv.get("conv_id", "0")}
    snippet = escape(conv["snippet"]) or '<i>(không có nội dung)</i>'
    rel = escape(_relative_time(conv["updated_at"]))
    abs_dt = escape(_fmt_dt(conv["updated_at"]))
    unread = conv.get("unread_count", 0)
    unread_html = (
        f'<span class="unread" title="{unread} tin chưa đọc">{unread}</span>'
        if unread else ""
    )
    query = urlencode({"customer_id": conv.get("customer_id", "")})
    href = (
        f'/pancake/pages/{escape(str(page_id))}/conversations/'
        f'{escape(conv["conv_id"])}?{query}'
    )
    return f"""
      <li>
        <a class="card" href="{href}">
          {_avatar(who)}
          <div class="info">
            <div class="row">
              <span class="name">{name}</span>
              <span class="time" title="{abs_dt}">{rel}</span>
            </div>
            <div class="snippet">{snippet}</div>
            <div class="badges">
              <span class="badge">{conv.get('message_count', 0)} tin nhắn</span>
              {unread_html}
            </div>
          </div>
        </a>
      </li>"""


def render_recent_list(convs: list[dict], page_id: str, msg_type: str) -> str:
    """Chỉ phần danh sách thẻ (dùng cho cả trang đầy đủ lẫn polling fragment)."""
    kind = "nhắn tin" if msg_type == "INBOX" else "bình luận"
    cards = "".join(_conv_card(c, page_id) for c in convs)
    return (
        f'<ul class="list">{cards}</ul>'
        if convs
        else f'<p class="empty">Chưa có ai {kind}.</p>'
    )


def render_recent(
    page_id: str, page: dict | None, convs: list[dict], msg_type: str, limit: int
) -> str:
    """Trang HTML: N người nhắn tin mới nhất của 1 page."""
    page_name = escape((page or {}).get("name") or f"Page {page_id}")
    kind = "nhắn tin" if msg_type == "INBOX" else "bình luận"
    return _RECENT_TEMPLATE.format(
        page_name=page_name,
        page_id=escape(str(page_id)),
        heading=f"{len(convs)} người {kind} mới nhất",
        limit=limit,
        body=render_recent_list(convs, page_id, msg_type),
    )


def _msg_bubble(msg: dict) -> str:
    """Dựng 1 bong bóng chat: 'out' (page/bot, phải) hay 'in' (khách, trái),
    kèm ảnh/tệp đính kèm và giờ gửi."""
    side = "out" if msg.get("is_page") else "in"
    text = escape(msg.get("text") or "")
    atts = ""
    for att in msg.get("attachments") or []:
        # Ảnh/sticker -> hiện thumbnail; tệp khác -> link; không url -> nhãn.
        url = att.get("url")
        if url and str(att.get("type", "")).lower() in ("photo", "image", "sticker"):
            atts += f'<a href="{escape(url)}" target="_blank" rel="noopener">' \
                    f'<img class="att" src="{escape(url)}" alt="ảnh"></a>'
        elif url:
            atts += f'<a class="att-link" href="{escape(url)}" target="_blank" ' \
                    f'rel="noopener">📎 tệp đính kèm</a>'
        else:
            atts += '<span class="att-link">📎 (đính kèm)</span>'
    if not text and not atts:
        text = '<i>(không có nội dung)</i>'
    time = escape(_fmt_dt(msg.get("inserted_at", "")))
    return (
        f'<div class="msg {side}">'
        f'<div class="bubble">{text}{atts}</div>'
        f'<div class="mtime">{time}</div>'
        f'</div>'
    )


def render_thread(messages: list[dict]) -> str:
    """Chỉ phần bong bóng chat (dùng cho cả trang đầy đủ lẫn polling fragment)."""
    return "".join(_msg_bubble(m) for m in messages) or \
        '<p class="empty">Chưa có tin nhắn.</p>'


def render_conversation(
    page_id: str,
    page: dict | None,
    conv_id: str,
    customer_id: str,
    convo: dict,
    sent: bool = False,
    error: str = "",
) -> str:
    """Trang HTML: xem toàn bộ hội thoại + form trả lời (mô phỏng Pancake)."""
    page_name = escape((page or {}).get("name") or f"Page {page_id}")
    cust_name = escape(convo.get("customer_name") or "Khách")
    thread = render_thread(convo.get("messages") or [])

    flash = ""
    if sent:
        flash = '<div class="flash ok">✓ Đã gửi tin nhắn</div>'
    elif error:
        flash = f'<div class="flash err">✕ {escape(error)}</div>'

    return _CONVO_TEMPLATE.format(
        page_name=page_name,
        cust_name=cust_name,
        back_url=f"/pancake/pages/{escape(str(page_id))}/recent",
        action_url=f"/pancake/pages/{escape(str(page_id))}/conversations/"
                   f"{escape(str(conv_id))}/reply",
        customer_id=escape(str(customer_id or "")),
        thread=thread,
        flash=flash,
    )


def render_error(message: str) -> str:
    """Trang lỗi dùng chung khi không tải được dữ liệu (vd Pancake API lỗi)."""
    return _PAGE_TEMPLATE.format(
        total=0,
        owner="",
        body=f'<div class="error"><b>Không tải được danh sách page</b>'
             f'<p>{escape(message)}</p></div>',
    )


_PAGE_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pancake — Danh sách Page</title>
<style>
  :root {{
    --bg: #f5f6f8; --card: #ffffff; --text: #1f2328; --sub: #6b7280;
    --border: #e5e7eb; --accent: #2563eb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --sub: #9198a1;
      --border: #30363d; --accent: #4493f8;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
    padding: 20px; line-height: 1.45;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}
  header {{ margin-bottom: 18px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .owner, .total {{ color: var(--sub); font-size: 13px; }}
  .group {{
    font-size: 14px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--sub); margin: 22px 0 8px;
  }}
  .count {{
    background: var(--border); color: var(--text); border-radius: 10px;
    padding: 1px 8px; font-size: 12px; margin-left: 4px;
  }}
  .list {{ list-style: none; margin: 0; padding: 0;
           display: flex; flex-direction: column; gap: 8px; }}
  .card {{
    display: flex; gap: 12px; align-items: center; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
  }}
  .avatar {{
    flex: 0 0 auto; width: 42px; height: 42px; border-radius: 50%;
    display: grid; place-items: center; color: #fff; font-weight: 700;
    font-size: 18px;
  }}
  .info {{ min-width: 0; }}
  .name {{
    font-weight: 600; color: var(--text); text-decoration: none;
    display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .name:hover {{ color: var(--accent); text-decoration: underline; }}
  .sub {{ color: var(--sub); font-size: 12px; margin-top: 1px; }}
  .badges {{ margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }}
  .badge {{
    font-size: 11px; padding: 2px 8px; border-radius: 20px;
    border: 1px solid var(--border);
  }}
  .badge.platform {{ text-transform: capitalize; color: var(--accent); }}
  .badge.role {{ color: var(--sub); }}
  .empty, .error {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px; color: var(--sub);
  }}
  .error b {{ color: #dc2626; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Danh sách Page có quyền truy cập</h1>
      <div class="total">Tổng cộng <b>{total}</b> page</div>
      {owner}
    </header>
    {body}
  </div>
</body>
</html>"""


_RECENT_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading} — {page_name}</title>
<style>
  :root {{
    --bg: #f5f6f8; --card: #ffffff; --text: #1f2328; --sub: #6b7280;
    --border: #e5e7eb; --accent: #2563eb; --unread: #dc2626;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --sub: #9198a1;
      --border: #30363d; --accent: #4493f8; --unread: #f85149;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
    padding: 20px; line-height: 1.45;
  }}
  .wrap {{ max-width: 640px; margin: 0 auto; }}
  header {{ margin-bottom: 18px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: var(--sub); font-size: 13px; }}
  .list {{ list-style: none; margin: 0; padding: 0;
           display: flex; flex-direction: column; gap: 8px; }}
  .card {{
    display: flex; gap: 12px; align-items: flex-start; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
    text-decoration: none; color: inherit; transition: border-color .15s;
  }}
  .card:hover {{ border-color: var(--accent); }}
  .avatar {{
    flex: 0 0 auto; width: 42px; height: 42px; border-radius: 50%;
    display: grid; place-items: center; color: #fff; font-weight: 700;
    font-size: 18px;
  }}
  .info {{ min-width: 0; flex: 1; }}
  .row {{ display: flex; align-items: baseline; gap: 8px; }}
  .name {{
    font-weight: 600; color: var(--text);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .time {{ color: var(--sub); font-size: 12px; margin-left: auto;
           flex: 0 0 auto; white-space: nowrap; }}
  .snippet {{
    color: var(--sub); font-size: 13px; margin-top: 2px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .badges {{ margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap;
             align-items: center; }}
  .badge {{
    font-size: 11px; padding: 2px 8px; border-radius: 20px;
    border: 1px solid var(--border); color: var(--sub);
  }}
  .unread {{
    background: var(--unread); color: #fff; border-radius: 20px;
    font-size: 11px; font-weight: 700; padding: 2px 8px; min-width: 20px;
    text-align: center;
  }}
  .empty {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px; color: var(--sub);
  }}
  .live {{ display: inline-flex; align-items: center; gap: 5px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #16a34a;
          box-shadow: 0 0 0 0 rgba(22,163,74,.6); animation: pulse 1.8s infinite; }}
  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(22,163,74,.5); }}
    70% {{ box-shadow: 0 0 0 6px rgba(22,163,74,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(22,163,74,0); }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{page_name}</h1>
      <div class="sub">{heading} · ID {page_id}
        · <span class="live"><span class="dot"></span>tự cập nhật</span></div>
    </header>
    <div id="feed">{body}</div>
  </div>
  <script>
    (function () {{
      var feed = document.getElementById('feed');
      if (!feed) return;
      var url = location.pathname + '/fragment' + location.search;
      var last = null;               // "mồi" lần đầu, không thay để tránh nháy
      function tick() {{
        if (document.hidden) return;
        fetch(url, {{ cache: 'no-store' }})
          .then(function (r) {{ return r.ok ? r.text() : null; }})
          .then(function (html) {{
            if (html == null) return;
            if (last === null) {{ last = html; return; }}
            if (html !== last) {{ feed.innerHTML = html; last = html; }}
          }})
          .catch(function () {{}});
      }}
      setInterval(tick, 10000);      // 10 giây/lần
    }})();
  </script>
</body>
</html>"""


_CONVO_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{cust_name} — {page_name}</title>
<style>
  :root {{
    --bg: #f5f6f8; --card: #ffffff; --text: #1f2328; --sub: #6b7280;
    --border: #e5e7eb; --accent: #2563eb; --in: #eceef1; --out: #2563eb;
    --ok: #16a34a; --err: #dc2626;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --sub: #9198a1;
      --border: #30363d; --accent: #4493f8; --in: #21262d; --out: #2f6fed;
      --ok: #3fb950; --err: #f85149;
    }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
    line-height: 1.45;
  }}
  .wrap {{ max-width: 640px; margin: 0 auto; min-height: 100vh;
           display: flex; flex-direction: column; }}
  header {{
    position: sticky; top: 0; z-index: 5; background: var(--card);
    border-bottom: 1px solid var(--border); padding: 12px 16px;
    display: flex; align-items: center; gap: 12px;
  }}
  .back {{ color: var(--accent); text-decoration: none; font-size: 20px;
           line-height: 1; }}
  .htext {{ min-width: 0; }}
  .htext h1 {{ font-size: 16px; margin: 0; overflow: hidden;
               text-overflow: ellipsis; white-space: nowrap; }}
  .htext .sub {{ color: var(--sub); font-size: 12px; }}
  .thread {{ flex: 1; padding: 16px; display: flex; flex-direction: column;
             gap: 4px; overflow-y: auto; }}
  .msg {{ display: flex; flex-direction: column; max-width: 78%;
          margin-top: 8px; }}
  .msg.in {{ align-self: flex-start; align-items: flex-start; }}
  .msg.out {{ align-self: flex-end; align-items: flex-end; }}
  .bubble {{
    padding: 8px 12px; border-radius: 16px; font-size: 14px;
    white-space: pre-wrap; word-wrap: break-word; overflow-wrap: anywhere;
  }}
  .msg.in .bubble {{ background: var(--in); color: var(--text);
                     border-bottom-left-radius: 4px; }}
  .msg.out .bubble {{ background: var(--out); color: #fff;
                      border-bottom-right-radius: 4px; }}
  .att {{ display: block; max-width: 220px; max-height: 220px;
          border-radius: 10px; margin-top: 6px; }}
  .att-link {{ display: inline-block; margin-top: 6px; font-size: 13px; }}
  .mtime {{ color: var(--sub); font-size: 11px; margin: 2px 4px 0; }}
  .empty {{ color: var(--sub); text-align: center; margin: 40px 0; }}
  .flash {{ margin: 10px 16px 0; padding: 8px 12px; border-radius: 8px;
            font-size: 13px; }}
  .flash.ok {{ background: color-mix(in srgb, var(--ok) 15%, transparent);
               color: var(--ok); }}
  .flash.err {{ background: color-mix(in srgb, var(--err) 15%, transparent);
                color: var(--err); }}
  .composer {{
    position: sticky; bottom: 0; background: var(--card);
    border-top: 1px solid var(--border); padding: 10px 12px;
    display: flex; gap: 8px; align-items: flex-end;
  }}
  .composer textarea {{
    flex: 1; resize: none; border: 1px solid var(--border);
    border-radius: 20px; padding: 9px 14px; font: inherit; font-size: 14px;
    background: var(--bg); color: var(--text); max-height: 120px;
  }}
  .composer button {{
    flex: 0 0 auto; border: 0; background: var(--accent); color: #fff;
    border-radius: 20px; padding: 9px 18px; font: inherit; font-weight: 600;
    cursor: pointer;
  }}
  .composer button:disabled {{ opacity: .5; cursor: default; }}
  .live {{ display: inline-flex; align-items: center; gap: 5px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--ok);
          box-shadow: 0 0 0 0 rgba(22,163,74,.6); animation: pulse 1.8s infinite; }}
  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(22,163,74,.5); }}
    70% {{ box-shadow: 0 0 0 6px rgba(22,163,74,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(22,163,74,0); }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <a class="back" href="{back_url}" title="Quay lại">&#8592;</a>
      <div class="htext">
        <h1>{cust_name}</h1>
        <div class="sub">{page_name} · <span class="live">
          <span class="dot"></span>tự cập nhật</span></div>
      </div>
    </header>
    {flash}
    <div class="thread" id="thread">
      {thread}
    </div>
    <form class="composer" method="post" action="{action_url}">
      <input type="hidden" name="customer_id" value="{customer_id}">
      <textarea name="message" rows="1" placeholder="Nhập tin nhắn trả lời…"
                autocomplete="off" required></textarea>
      <button type="submit">Gửi</button>
    </form>
  </div>
  <script>
    // Cuộn xuống tin mới nhất khi mở
    var t = document.getElementById('thread');
    if (t) t.scrollTop = t.scrollHeight;
    // Textarea tự giãn + Enter để gửi (Shift+Enter xuống dòng)
    var ta = document.querySelector('.composer textarea');
    var form = document.querySelector('.composer');
    if (ta) {{
      ta.addEventListener('input', function () {{
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
      }});
      ta.addEventListener('keydown', function (e) {{
        if (e.key === 'Enter' && !e.shiftKey) {{
          e.preventDefault();
          if (ta.value.trim()) form.submit();
        }}
      }});
    }}
    // Poll tin nhắn mới, chỉ thay khi có thay đổi để khỏi nháy/mất ảnh
    (function () {{
      if (!t) return;
      var url = location.pathname + '/fragment' + location.search;
      var last = null;
      function atBottom() {{
        return t.scrollHeight - t.scrollTop - t.clientHeight < 60;
      }}
      function tick() {{
        if (document.hidden) return;
        fetch(url, {{ cache: 'no-store' }})
          .then(function (r) {{ return r.ok ? r.text() : null; }})
          .then(function (html) {{
            if (html == null) return;
            if (last === null) {{ last = html; return; }}
            if (html !== last) {{
              var stick = atBottom();
              t.innerHTML = html; last = html;
              if (stick) t.scrollTop = t.scrollHeight;
            }}
          }})
          .catch(function () {{}});
      }}
      setInterval(tick, 8000);       // 8 giây/lần
    }})();
  </script>
</body>
</html>"""
