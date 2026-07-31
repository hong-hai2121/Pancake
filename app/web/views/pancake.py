"""Dựng HTML cho các màn hình Pancake (server-side render).

Chỉ dựng phần THÂN trang rồi bọc bằng `app.web.shell.render_shell` để mọi màn
hình dùng chung menu trái + topbar + stylesheet.
"""

from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlencode

from app.integrations.pancake.client import tag_color_override, tag_label
from app.web.shell import render_shell

# Pancake trả thời gian theo UTC; cộng offset này để hiển thị GIỜ ĐỊA PHƯƠNG (VN=+7).
_DISPLAY_TZ = timezone(timedelta(hours=7))

# Bảng màu cho avatar chữ cái đầu (ổn định theo id).
_AVATAR_COLORS = [
    "#6f5a9c", "#a8718f", "#e91e8c", "#c4868f", "#8c6a9b",
    "#b06a9a", "#7a4c88", "#9a86ad", "#d4778c", "#5f4b8b",
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


# Bảng màu chip thẻ — ổn định theo ID để cùng 1 thẻ luôn 1 màu (khớp thanh lọc).
_TAG_COLORS = [
    "#6f5a9c", "#a8718f", "#e91e8c", "#c4868f", "#8c6a9b",
    "#b06a9a", "#7a4c88", "#9a86ad", "#d4778c", "#5f4b8b",
]


def _tag_color(tag_id: int, meta: dict | None = None) -> str:
    """Màu 1 thẻ.

    Ưu tiên: màu THẬT của page (`meta` — public API hoặc kho) > màu khai báo tay
    (TAG_OVERRIDES) > xám cho thẻ hệ thống (id<0) > màu ổn định theo ID.
    Cùng thứ tự với `tag_label` để tên và màu không bao giờ đến từ 2 nguồn khác nhau.
    """
    real = (meta.get(tag_id) or {}).get("color") if meta else ""
    if real:
        return real
    manual = tag_color_override(tag_id)
    if manual:
        return manual
    if tag_id < 0:
        return "#6b7280"
    return _TAG_COLORS[tag_id % len(_TAG_COLORS)]


def _conv_tags_html(tags: list[int], meta: dict | None = None) -> str:
    """Dãy pill thẻ nhỏ hiển thị dưới tên hội thoại (chỉ thẻ người dùng gắn, id>0).

    `meta` = {tag_id: {'text','color'}} của ĐÚNG page chứa hội thoại này -> pill
    hiện TÊN thẻ như trên Pancake. Không có tên (chưa lấy được quyền Admin) thì
    `tag_label` tự lùi về "Thẻ #id" — vẫn đọc được, chỉ kém rõ.

    Thẻ hệ thống (id âm như -99, -3…) bỏ qua cho gọn. Dùng để nhìn nhanh & so sánh.
    """
    pills = "".join(
        f'<span class="ctag" style="--tc:{_tag_color(tid, meta)}" '
        f'title="Thẻ #{tid}">{escape(tag_label(tid, meta))}</span>'
        for tid in tags if tid > 0
    )
    return f'<div class="ctags">{pills}</div>' if pills else ""


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

    # Tên page link vào màn Tin nhắn của page đó; nút riêng mở trang Facebook.
    return f"""
      <li class="card page-card">
        <div class="pc-head">
          {_avatar(page)}
          <div class="info">
            <a class="name" href="/tin-nhan?page_id={pid}">{name}</a>
            <div class="sub">{subtitle}</div>
          </div>
        </div>
        <div class="badges">{badges_html}</div>
        <a class="btn" href="{fb_url}" target="_blank" rel="noopener">Facebook ↗</a>
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
    """Trang liệt kê các page token có quyền, gom theo nhóm."""
    owner = owner or {}

    # Gom theo nhóm, giữ thứ tự xuất hiện.
    groups: dict[str, list[dict]] = {}
    for p in pages:
        groups.setdefault(p["group_label"], []).append(p)

    sections = []
    for label, items in groups.items():
        cards = "".join(_page_card(p) for p in items)
        sections.append(
            f'<h2 class="grp">{escape(label)} '
            f'<span class="count">{len(items)}</span></h2>'
            f'<ul class="pages-grid">{cards}</ul>'
        )
    body = "".join(sections) or '<p class="empty">Không có page nào.</p>'

    sub_bits = [f"Tổng cộng <b>{len(pages)}</b> page"]
    if owner.get("name"):
        exp = _fmt_exp(owner.get("exp"))
        sub_bits.append(f'tài khoản <b>{escape(str(owner["name"]))}</b>')
        if exp:
            sub_bits.append(f"token hết hạn {exp}")

    return render_shell(
        title="Danh sách Page",
        active="messages",
        heading="Danh sách Page",
        sub=" · ".join(sub_bits),
        body=body,
    )


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
    """Đổi thời điểm -> chuỗi tuyệt đối "HH:MM · dd/mm/yyyy" theo giờ VN (tooltip)."""
    dt = _parse_dt(iso)
    return dt.astimezone(_DISPLAY_TZ).strftime("%H:%M · %d/%m/%Y") if dt else ""


def _clock_dt(iso: str) -> str:
    """Giờ cụ thể (giờ VN), gọn: "HH:MM" nếu hôm nay, else kèm ngày.

    Dùng cho danh sách ảnh chụp (lọc thẻ) — nơi giờ tương đối sẽ bị lệ dần.
    """
    dt = _parse_dt(iso)
    if not dt:
        return ""
    local = dt.astimezone(_DISPLAY_TZ)
    now = datetime.now(_DISPLAY_TZ)
    if local.date() == now.date():
        return local.strftime("%H:%M")
    if local.year == now.year:
        return local.strftime("%H:%M · %d/%m")
    return local.strftime("%H:%M · %d/%m/%Y")


def conv_href(conv: dict, page_id: str, mode: str = "pancake", tag: str = "") -> str:
    """Đường dẫn mở 1 hội thoại.

    mode = "pancake" -> trang chat riêng cũ (/pancake/.../conversations/...)
    mode = "inbox"   -> màn Tin nhắn 2 cột (/tin-nhan?page_id=&conv_id=...)
    tag  -> giữ bộ lọc thẻ đang chọn khi mở hội thoại (chỉ dùng cho mode "inbox").

    Ở hộp thư GỘP (`page_id` = ALL), hội thoại mang sẵn `page_id` thật của nó:
    link giữ nguyên `page_id=ALL` cho danh sách bên trái, và nói riêng page thật
    qua `conv_page_id` để khung chat bên phải mở/gửi đúng chỗ.
    """
    cust = conv.get("customer_id", "")
    real_pid = str(conv.get("page_id") or page_id)
    if mode == "inbox":
        params = {"page_id": page_id, "conv_id": conv["conv_id"], "customer_id": cust}
        if real_pid != str(page_id):
            params["conv_page_id"] = real_pid
        if tag:
            params["tag"] = tag
        return f"/tin-nhan?{urlencode(params)}"
    query = urlencode({"customer_id": cust})
    return (
        f'/pancake/pages/{escape(real_pid)}/conversations/'
        f'{escape(conv["conv_id"])}?{query}'
    )


def _conv_card(
    conv: dict, page_id: str, mode: str = "pancake", active: str = "", tag: str = "",
    tags_by_page: dict | None = None,
) -> str:
    """Dựng 1 thẻ hội thoại (link bấm vào để mở trang chat), có avatar, tên,
    tin nhắn cuối, thời gian và badge số tin / chưa đọc.

    Cột thời gian hiện GIỜ cụ thể theo giờ VN (vd "16:17", khác ngày kèm ngày);
    tooltip là giờ + ngày đầy đủ.

    `tags_by_page` = {page_id: {tag_id: {'text','color'}}}. Tra theo page THẬT
    của hội thoại (hộp thư gộp mới có `page_id` trong từng dòng; xem 1 page thì
    lùi về `page_id` đang xem) — thẻ là dữ liệu riêng của từng page nên tra
    bằng mỗi `tag_id` sẽ dán nhầm tên của page khác.
    """
    name = escape(conv["name"])
    who = {"name": conv["name"], "id": conv.get("fb_id") or conv.get("conv_id", "0")}
    snippet = escape(conv["snippet"]) or '<i>(không có nội dung)</i>'
    shown_time = escape(_clock_dt(conv["updated_at"]))
    abs_dt = escape(_fmt_dt(conv["updated_at"]))
    unread = conv.get("unread_count", 0)
    unread_html = (
        f'<span class="unread" title="{unread} tin chưa đọc">{unread}</span>'
        if unread else ""
    )
    cls = "card link on" if conv["conv_id"] == active else "card link"
    tags_meta = (tags_by_page or {}).get(str(conv.get("page_id") or page_id)) or {}
    # Chỉ hộp thư GỘP mới kèm `page_name` -> hiện thêm dòng cho biết hội thoại
    # này của page nào; chế độ xem 1 page không có field này nên không đổi gì.
    page_html = (
        f'<div class="cpage">{escape(conv["page_name"])}</div>'
        if conv.get("page_name") else ""
    )
    # Chỉ hội thoại đọc từ kho mới có `sentiment` (worker nền quét — xem
    # app/workers/sentiment.py); đường gọi Pancake trực tiếp không có -> không badge.
    neg_html = (
        '<span class="neg" title="Worker nền phát hiện dấu hiệu tiêu cực'
        f' (cách quét: {escape(conv.get("sentiment_method") or "?")})">⚠ tiêu cực</span>'
        if conv.get("sentiment") == "negative" else ""
    )
    # data-upd/data-cid = mốc phân trang cho "kéo xuống nạp thêm" (xem _INBOX_JS):
    # JS đọc thẻ CUỐI danh sách rồi xin các hội thoại cũ hơn mốc đó từ kho.
    return f"""
      <li data-upd="{escape(str(conv.get("updated_at") or ""))}"
          data-cid="{escape(str(conv.get("conv_id") or ""))}">
        <a class="{cls}" href="{conv_href(conv, page_id, mode, tag)}">
          {_avatar(who)}
          <div class="info">
            <div class="crow">
              <span class="name">{name}</span>
              <span class="time" title="{abs_dt}">{shown_time}</span>
            </div>
            {page_html}
            {_conv_tags_html(conv.get("tags") or [], tags_meta)}
            <div class="snippet">{snippet}</div>
            <div class="badges">
              <span class="badge">{conv.get('message_count', 0)} tin nhắn</span>
              {unread_html}
              {neg_html}
            </div>
          </div>
        </a>
      </li>"""


def render_recent_list(
    convs: list[dict],
    page_id: str,
    msg_type: str,
    mode: str = "pancake",
    active: str = "",
    tag: str = "",
    items_only: bool = False,
    tags_by_page: dict | None = None,
) -> str:
    """Chỉ phần danh sách thẻ (dùng cho cả trang đầy đủ lẫn polling fragment).

    `items_only` — trả về CÁC THẺ `<li>` trần, không bọc `<ul>` và không có
    thông báo rỗng. Dùng cho "kéo xuống nạp thêm": JS nối thẳng chuỗi này vào
    cuối `<ul>` đang có, và hiểu chuỗi rỗng là "hết hội thoại cũ hơn".

    `tags_by_page` — tên/màu thẻ theo từng page (xem `_conv_card`). Thiếu thì
    pill thẻ hiện "Thẻ #id"; PHẢI truyền cả ở fragment, không thì mỗi nhịp tự
    cập nhật lại thay tên thẻ bằng số.
    """
    kind = "nhắn tin" if msg_type == "INBOX" else "bình luận"
    cards = "".join(
        _conv_card(c, page_id, mode, active, tag, tags_by_page) for c in convs
    )
    if items_only:
        return cards
    return (
        f'<ul class="list">{cards}</ul>'
        if convs
        else f'<p class="empty">Chưa có ai {kind}.</p>'
    )


def render_recent(
    page_id: str, page: dict | None, convs: list[dict], msg_type: str, limit: int,
    tags_by_page: dict | None = None,
) -> str:
    """Trang: N người nhắn tin mới nhất của 1 page (danh sách 1 cột)."""
    page_name = escape((page or {}).get("name") or f"Page {page_id}")
    kind = "nhắn tin" if msg_type == "INBOX" else "bình luận"
    return render_shell(
        title=page_name,
        active="messages",
        heading=page_name,
        sub=f'{len(convs)} người {kind} mới nhất · ID {escape(str(page_id))} · '
            f'<span class="live"><span class="dot"></span>tự cập nhật</span>',
        actions=f'<a class="btn" href="/tin-nhan?page_id={escape(str(page_id))}">'
                f'Mở dạng 2 cột</a>',
        body=f'<div id="feed">'
             f'{render_recent_list(convs, page_id, msg_type, tags_by_page=tags_by_page)}'
             f'</div>',
        script=_POLL_JS.replace("__TARGET__", "feed").replace("__MS__", "10000"),
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


def render_composer(action_url: str, customer_id: str, extra: str = "") -> str:
    """Ô soạn tin ở đáy khung chat (Enter gửi, Shift+Enter xuống dòng).

    `extra` = HTML các input ẩn thêm (vd page_id/conv_id khi form nằm ở màn
    Tin nhắn 2 cột, nơi đường dẫn POST không chứa sẵn 2 giá trị đó).
    """
    return f"""
      <form class="composer" method="post" action="{action_url}">
        <input type="hidden" name="customer_id" value="{escape(str(customer_id or ''))}">
        {extra}
        <textarea name="message" rows="1" placeholder="Nhập tin nhắn trả lời…"
                  autocomplete="off" required></textarea>
        <button type="submit">Gửi</button>
      </form>"""


def render_conversation(
    page_id: str,
    page: dict | None,
    conv_id: str,
    customer_id: str,
    convo: dict,
    sent: bool = False,
    error: str = "",
) -> str:
    """Trang xem toàn bộ hội thoại + form trả lời (mô phỏng Pancake)."""
    page_name = escape((page or {}).get("name") or f"Page {page_id}")
    cust_name = escape(convo.get("customer_name") or "Khách")
    action_url = (
        f"/pancake/pages/{escape(str(page_id))}/conversations/"
        f"{escape(str(conv_id))}/reply"
    )

    flash_html = ""
    if sent:
        flash_html = '<div class="flash ok" style="margin:12px 22px 0">✓ Đã gửi tin nhắn</div>'
    elif error:
        flash_html = (
            f'<div class="flash err" style="margin:12px 22px 0">✕ {escape(error)}</div>'
        )

    body = (
        '<div class="pane">'
        + flash_html
        + f'<div class="thread" id="thread">'
          f'{render_thread(convo.get("messages") or [])}</div>'
        + render_composer(action_url, customer_id)
        + "</div>"
    )
    return render_shell(
        title=f"{cust_name} — {page_name}",
        active="messages",
        heading=cust_name,
        sub=f'{page_name} · <span class="live"><span class="dot"></span>'
            f"tự cập nhật</span>",
        actions=f'<a class="btn" href="/pancake/pages/{escape(str(page_id))}/recent">'
                f"← Danh sách</a>",
        body=body,
        full=True,
        script=_CHAT_JS + _POLL_JS.replace("__TARGET__", "thread").replace(
            "__MS__", "8000"
        ),
    )


def render_error(message: str) -> str:
    """Trang lỗi dùng chung khi không tải được dữ liệu (vd Pancake API lỗi)."""
    return render_shell(
        title="Lỗi",
        active="messages",
        heading="Không tải được dữ liệu từ Pancake",
        body=f'<div class="flash err">✕ {escape(message)}</div>'
             '<p class="note">Kiểm tra <code>PANCAKE_ACCESS_TOKEN</code> trong '
             "<code>.env</code> (token có thể đã hết hạn) rồi tải lại trang.</p>",
    )


# --- JS dùng chung -----------------------------------------------------------
# Tự tải lại nội dung: gọi endpoint /fragment cùng đường dẫn, chỉ thay DOM khi
# HTML thực sự đổi (tránh nháy màn hình và mất ảnh đang tải).
_POLL_JS = """
(function(){
  var el = document.getElementById('__TARGET__');
  if(!el) return;
  var url = location.pathname + '/fragment' + location.search;
  var last = null;
  function atBottom(){ return el.scrollHeight - el.scrollTop - el.clientHeight < 60; }
  function tick(){
    if (document.hidden) return;
    fetch(url, {cache:'no-store'})
      .then(function(r){ return r.ok ? r.text() : null; })
      .then(function(html){
        if (html == null) return;
        if (last === null) { last = html; return; }   // mồi lần đầu
        if (html !== last) {
          var stick = atBottom();
          el.innerHTML = html; last = html;
          if (stick) el.scrollTop = el.scrollHeight;
        }
      })
      .catch(function(){});
  }
  // Đăng ký vào __pjaxTimers để _NAV_JS (app/web/shell.py) huỷ khi rời trang
  // bằng AJAX — không thì mỗi lần quay lại lại chồng thêm 1 vòng poll.
  (window.__pjaxTimers = window.__pjaxTimers || []).push(setInterval(tick, __MS__));
})();
"""

# Khung chat: cuộn xuống cuối khi mở, textarea tự giãn, Enter = gửi.
_CHAT_JS = """
(function(){
  var t = document.getElementById('thread');
  if (t) t.scrollTop = t.scrollHeight;
  var ta = document.querySelector('.composer textarea');
  var form = document.querySelector('.composer');
  if (!ta) return;
  ta.addEventListener('input', function(){
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 130) + 'px';
  });
  ta.addEventListener('keydown', function(e){
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // form.submit() không phát sự kiện 'submit' (_NAV_JS sẽ không bắt được
      // -> tải lại cả trang) nên phải dùng requestSubmit().
      if (ta.value.trim()) {
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      }
    }
  });
})();
"""
