"""Dựng HTML cho 3 màn hình chung: Bảng điều khiển, Tin nhắn, Khách hàng.

Chỉ lo phần hiển thị — dữ liệu do `app/ui/routes.py` lấy sẵn rồi truyền vào.
Dùng lại các hàm dựng thẻ/bong bóng của Pancake để 2 màn chat giống hệt nhau.
"""

from html import escape
from urllib.parse import urlencode

from app.pancake.client import ALL_PAGES
from app.pancake.client import tag_label as _tag_label
from app.pancake.switches import is_page_enabled
from app.pancake.webview import (
    _avatar,
    _fmt_dt,
    _relative_time,
    _tag_color,
    conv_href,
    render_composer,
    render_recent_list,
    render_thread,
)
from app.ui.shell import render_shell, stat


def render_tag_filter(
    facet: list[tuple[int, int]],
    active_tag: str,
    page_id: str,
    tags_meta: dict | None = None,
) -> str:
    """Thanh chip lọc theo thẻ. `facet` = [(tag_id, số hội thoại)] đã sắp xếp.

    `tags_meta` = {id: {'text','color'}} tên/màu thật từ public API (nếu có).
    Bấm 1 chip -> lọc; bấm 'Tất cả' -> bỏ lọc. Chip đang chọn được tô đậm.
    """
    if not facet:
        return ""
    all_cls = "tchip all on" if not active_tag else "tchip all"
    chips = (
        f'<a class="{all_cls}" href="/tin-nhan?page_id={escape(page_id)}">'
        f"Tất cả</a>"
    )
    for tid, count in facet:
        href = "/tin-nhan?" + urlencode({"page_id": page_id, "tag": tid})
        on = " on" if active_tag == str(tid) else ""
        color = _tag_color(tid, tags_meta)
        chips += (
            f'<a class="tchip{on}" href="{href}" '
            f'style="--tc:{color}" title="{count} hội thoại">'
            f'<span class="tdot"></span>{escape(_tag_label(tid, tags_meta))}'
            f'<span class="tnum">{count}</span></a>'
        )
    return f'<div class="tagbar">{chips}</div>'


def _page_select(
    pages: list[dict], current: str, base: str, all_label: str = ""
) -> str:
    """Ô chọn page ở góc phải topbar; đổi lựa chọn là nhảy trang luôn.

    `data-nav-tpl` để `_NAV_JS` (app/ui/shell.py) bắt sự kiện đổi lựa chọn và
    điều hướng bằng AJAX, thay vì gán thẳng location.href (tải lại cả trang).

    `all_label` — có thì thêm mục "gộp mọi page" (value=ALL) lên đầu. Chỉ màn
    Tin nhắn dùng; các màn khác vẫn chỉ xem được từng page một.
    """
    if not pages:
        return ""
    opts = ""
    if all_label:
        sel = " selected" if str(current) == ALL_PAGES else ""
        opts += f'<option value="{ALL_PAGES}"{sel}>{escape(all_label)}</option>'
    for p in pages:
        sel = " selected" if p["id"] == str(current) else ""
        # Page TẮT vẫn liệt kê (để bấm vào còn biết đường bật lại) nhưng đánh dấu
        # rõ — chọn phải nó mà không có nhãn thì màn hình trống, tưởng lỗi.
        # Dùng ký hiệu chữ chứ không dùng CSS: <option> không tô màu được đồng
        # nhất giữa các trình duyệt/hệ điều hành.
        label = (
            escape(p["name"]) if is_page_enabled(p["id"])
            else f'○ {escape(p["name"])} — TẮT'
        )
        opts += f'<option value="{escape(p["id"])}"{sel}>{label}</option>'
    return (
        f'<select class="inp" data-nav-tpl="{escape(base)}?page_id=">'
        f"{opts}</select>"
    )


# ---------------------------------------------------------- bảng điều khiển
def _dashboard_page_list(pages: list[dict]) -> str:
    """Panel danh sách page hiện NGAY trên bảng điều khiển (ẩn, bấm ô stat mới mở).

    Dùng CSS `:target` (không JS): ô "Page truy cập được" trỏ tới #ds-page ->
    bấm là panel hiện ra tại chỗ, không rời trang. Bấm "Đóng" (href="#") thì ẩn lại.
    """
    if not pages:
        return ""
    rows = ""
    for p in pages:
        pid = escape(str(p.get("id", "")))
        on = is_page_enabled(p.get("id", ""))
        sw_cls = "pgsw on" if on else "pgsw off"
        sw_label = "● BẬT" if on else "○ TẮT"
        sw_title = (
            "Đang BẬT — bấm để TẮT (chặn lấy/gửi tin của page này)" if on
            else "Đang TẮT — bấm để BẬT lại"
        )
        switch = (
            '<form method="post" action="/bang-dieu-khien/page-switch" '
            'style="flex:0 0 auto;margin:0">'
            f'<input type="hidden" name="page_id" value="{pid}">'
            f'<button type="submit" class="{sw_cls}" title="{sw_title}">{sw_label}</button>'
            "</form>"
        )
        rows += f"""
          <li class="row pgrow {"on" if on else "off"}" style="align-items:center">
            {_avatar(p).replace('class="avatar"', 'class="avatar sm"')}
            <div class="rbody">
              <div class="name">{escape(p.get("name") or "(không tên)")}
                <span class="pgstate">{"ĐANG BẬT" if on else "ĐANG TẮT"}</span></div>
              <div class="rmeta">ID {pid} · {escape(p.get("platform") or "")}</div>
            </div>
            {switch}
            <a class="btn" style="flex:0 0 auto" href="/tin-nhan?page_id={pid}">Mở tin nhắn</a>
          </li>"""
    on_total = sum(1 for p in pages if is_page_enabled(p.get("id", "")))
    off_total = len(pages) - on_total
    return (
        '<section id="ds-page" class="ds-page"><div class="card">'
        '<div class="ds-page-head">'
        f'<b>Danh sách page ({len(pages)})</b>'
        f'<span class="rmeta" style="margin:0">'
        f'<span style="color:var(--ok);font-weight:700">● {on_total} BẬT</span> · '
        f'{off_total} TẮT</span>'
        '<form method="post" action="/bang-dieu-khien/page-switch-all" '
        'style="margin:0 0 0 auto">'
        '<input type="hidden" name="action" value="on">'
        '<button type="submit" class="btn">Bật tất cả</button></form>'
        '<form method="post" action="/bang-dieu-khien/page-switch-all" style="margin:0">'
        '<input type="hidden" name="action" value="off">'
        '<button type="submit" class="btn">Tắt tất cả</button></form>'
        '<a class="btn" href="#">Đóng</a></div>'
        f'<ul class="list">{rows}</ul>'
        "</div></section>"
    )


def render_dashboard(
    pancake: dict, data: dict, config: dict, errors: dict,
    pages: list[dict] | None = None,
) -> str:
    """Trang tổng quan: số liệu Pancake + kho dữ liệu bot + cấu hình hệ thống."""

    def err_card(key: str) -> str:
        msg = errors.get(key)
        return f'<div class="flash err">✕ {escape(str(msg)[:200])}</div>' if msg else ""

    # --- Ô số liệu ---
    if errors.get("pancake"):
        pancake_stats = err_card("pancake")
    else:
        pancake_stats = (
            '<div class="stats">'
            + stat("Page truy cập được", str(pancake["total_pages"]),
                   f'{pancake["active_pages"]} page đang hoạt động · bấm để xem',
                   href="#ds-page")
            + stat("Hội thoại đang mở", str(pancake["conv_count"]),
                   escape(pancake["page_name"]))
            + stat("Tin chưa đọc", str(pancake["unread"]),
                   "trên page đang chọn",
                   tone="err" if pancake["unread"] else "ok")
            + stat("Khách nhắn gần nhất", escape(pancake["last_rel"] or "—"),
                   escape(pancake["last_name"] or ""))
            + "</div>"
        )

    if errors.get("data"):
        data_stats = err_card("data")
    else:
        qa_tone = "err" if data["qa_total"] == 0 else ""
        kb_tone = "err" if data["kb_total"] == 0 else ""
        data_stats = (
            '<div class="stats">'
            + stat("Hội thoại mẫu", str(data["qa_total"]),
                   f'{data["qa_emb"]} dòng đã có embedding', tone=qa_tone,
                   href="/data/hoi-thoai")
            + stat("Bước kịch bản", str(data["kb_total"]),
                   f'{data["kb_emb"]} dòng đã có embedding', tone=kb_tone)
            + "</div>"
        )
        if data["qa_total"] < 5:
            data_stats += (
                '<p class="note">⚠️ Kho dữ liệu còn rất ít — bot sẽ trả lời chung '
                'chung. Thêm hội thoại mẫu ở <a href="/data/hoi-thoai">Dữ liệu bot'
                "</a> để câu trả lời bám sát nghiệp vụ của bạn.</p>"
            )

    # --- Bảng cấu hình ---
    def kv(k: str, v: str) -> str:
        return f'<div class="kv"><span class="k">{escape(k)}</span><span class="v">{v}</span></div>'

    def pill(ok: bool, yes: str = "đã cấu hình", no: str = "chưa có") -> str:
        cls = "pill ok" if ok else "pill err"
        return f'<span class="{cls}">{yes if ok else no}</span>'

    cfg = (
        '<div class="card">'
        + kv("Pancake token", pill(config["pancake_token"]))
        + kv("OpenAI API key", pill(config["openai_key"]))
        + kv(
            "Nơi lưu dữ liệu",
            pill(config["db_ready"], yes=config["db_backend"], no="chưa cấu hình")
            + (
                f' <code>{escape(config["db_target"])}</code>'
                if config["db_target"] else ""
            ),
        )
        + kv("Model trả lời", f'<code>{escape(config["llm_model"])}</code>')
        + kv("Model embedding",
             f'<code>{escape(config["embedding_model"])}</code> '
             f'({config["embedding_dim"]} chiều)')
        + kv("Số kết quả tìm (top-k)", str(config["top_k"]))
        + kv("Ngưỡng tương đồng",
             f'{config["threshold"]}'
             + ("" if config["threshold"] else " <span class=\"pill\">không lọc</span>"))
        + "</div>"
    )

    links = (
        '<div class="card"><div class="links">'
        '<a class="btn primary" href="/tin-nhan">Mở hộp thư</a>'
        '<a class="btn" href="/khach-hang">Danh sách khách</a>'
        '<a class="btn" href="/data/hoi-thoai">Thêm hội thoại mẫu</a>'
        '<a class="btn" href="/data/thu-tin-nhan">Thử câu hỏi</a>'
        '<a class="btn" href="#ds-page">Danh sách page</a>'
        '<a class="btn" href="/docs" target="_blank">API docs ↗</a>'
        "</div></div>"
    )

    body = (
        '<h2 class="grp">Pancake</h2>' + pancake_stats
        + _dashboard_page_list(pages or [])
        + '<h2 class="grp">Kho dữ liệu bot</h2>' + data_stats
        + '<h2 class="grp">Lối tắt</h2>' + links
        + '<h2 class="grp">Cấu hình hệ thống</h2>' + cfg
    )
    return render_shell(
        title="Bảng điều khiển",
        active="dashboard",
        heading="Bảng điều khiển",
        sub="Tổng quan hệ thống bán hàng qua Pancake + bot RAG",
        body=body,
        script=_DASHBOARD_JS,
    )


# ------------------------------------------------------------------ tin nhắn
def render_inbox(
    pages: list[dict],
    page_id: str,
    page_name: str,
    convs: list[dict],
    conv_id: str,
    customer_id: str,
    convo: dict | None,
    limit: int,
    sent: bool = False,
    error: str = "",
    tags_facet: list[tuple[int, int]] | None = None,
    active_tag: str = "",
    tags_meta: dict | None = None,
    merged: bool = False,
    enabled_count: int = 0,
    thread_page_id: str = "",
    thread_page_name: str = "",
) -> str:
    """Màn Tin nhắn 2 cột: trái = danh sách hội thoại, phải = khung chat.

    `merged` — hộp thư GỘP mọi page đang BẬT (`page_id` = ALL). Khi đó mỗi thẻ
    hội thoại tự mang `page_id` thật của nó, còn `thread_page_id` là page của
    hội thoại đang mở bên phải (dùng để gửi trả lời / gợi ý cho đúng page).
    """
    # Thẻ là dữ liệu RIÊNG của từng page (cùng số id ở 2 page = 2 thẻ khác nhau)
    # nên hộp thư gộp không lọc thẻ — gộp lại sẽ dán nhãn sai.
    if merged:
        tags_facet, active_tag, tags_meta = [], "", {}
    lhead_label = (
        f"{len(convs)} hội thoại có thẻ « {escape(_tag_label(int(active_tag), tags_meta))} »"
        if active_tag and active_tag.lstrip("-").isdigit()
        else f"{len(convs)} hội thoại mới nhất"
    )
    if merged:
        lhead_label += f" · {enabled_count} page đang BẬT"
    # Đang lọc thẻ -> danh sách là "ảnh chụp" mẻ lớn, không tự cập nhật (cho nhẹ).
    live_html = (
        '<span class="live" style="margin-left:auto">'
        '<span class="dot"></span>tự cập nhật</span>'
        if not active_tag
        else '<span class="lhint" style="margin-left:auto">ảnh chụp</span>'
    )
    list_html = (
        '<p class="empty">Mọi page đang TẮT nên không lấy tin nào. '
        'Bật lại ở <a href="/bang-dieu-khien#ds-page">Bảng điều khiển</a>.</p>'
        if merged and not enabled_count
        else render_recent_list(
            convs, page_id, "INBOX", mode="inbox", active=conv_id, tag=active_tag
        )
    )
    left = (
        '<div class="inbox-list">'
        f'<div class="lhead">{lhead_label}{live_html}</div>'
        f'{render_tag_filter(tags_facet or [], active_tag, page_id, tags_meta)}'
        f'<div class="lbody" id="feed">{list_html}</div></div>'
    )
    # Page thật của hội thoại đang mở: chế độ gộp thì lấy từ URL, còn lại chính
    # là page đang xem. Mọi hành động ghi (gửi tin, gợi ý) đều bám giá trị này.
    thread_pid = thread_page_id or page_id

    if convo is None:
        right = (
            '<div class="pane"><div class="placeholder">'
            "<div><b>Chọn một hội thoại ở cột bên trái</b>"
            '<p class="note">Tin nhắn và ô trả lời sẽ hiện ở đây.</p></div>'
            "</div></div>"
        )
    else:
        cust_name = escape(convo.get("customer_name") or "Khách")
        who = {"name": convo.get("customer_name") or "K", "id": customer_id or "0"}
        flash_html = ""
        if sent:
            flash_html = ('<div class="flash ok" style="margin:12px 22px 0">'
                          "✓ Đã gửi tin nhắn</div>")
        elif error:
            flash_html = (f'<div class="flash err" style="margin:12px 22px 0">'
                          f"✕ {escape(error)}</div>")
        right = (
            '<div class="pane">'
            f'<div class="chead">{_avatar(who)}'
            f'<div class="info"><div class="name">{cust_name}</div>'
            f'<div class="sub">{escape(thread_page_name or page_name)}</div></div>'
            f'<a class="btn" href="{conv_href({"conv_id": conv_id, "customer_id": customer_id}, thread_pid)}">'
            "Mở toàn màn hình</a>"
            '<button type="button" id="btn-copy" class="btn" '
            'title="Sao chép toàn bộ hội thoại">📋 Copy</button></div>'
            + flash_html
            + f'<div class="thread" id="thread">'
              f'{render_thread(convo.get("messages") or [])}</div>'
            + '<div class="suggest-bar">'
              '<button type="button" id="btn-suggest" class="btn">'
              '💡 Gợi ý trả lời</button>'
              '<button type="button" id="btn-extract" class="btn" '
              'title="Đọc hội thoại này, đề xuất cặp hỏi-đáp cho kho tri thức">'
              '🧠 Trích tri thức</button>'
              '<span class="shint" id="suggest-hint"></span>'
              "</div>"
            + '<div id="extract-panel" style="padding:0 16px"></div>'
            + render_composer(
                "/tin-nhan/tra-loi", customer_id,
                # page_id = page THẬT của hội thoại (gửi tin/gợi ý phải đúng page).
                # list_page_id = page đang xem ở cột trái (có thể là ALL) — chỉ
                # dùng để quay lại đúng danh sách sau khi gửi.
                extra=f'<input type="hidden" name="page_id" '
                      f'value="{escape(str(thread_pid))}">'
                      f'<input type="hidden" name="list_page_id" '
                      f'value="{escape(str(page_id))}">'
                      f'<input type="hidden" name="conv_id" '
                      f'value="{escape(str(conv_id))}">',
            )
            + "</div>"
        )

    # Luôn hiện mục gộp, kể cả khi 0 page BẬT — nếu ẩn đi thì người đang ở chế
    # độ gộp mà lỡ tắt hết page sẽ không còn lối nào quay lại mục này.
    all_label = f"📥 Tất cả page ({enabled_count} đang BẬT)"
    sub = (
        f"Gộp {enabled_count} page đang BẬT"
        if merged else f"{escape(page_name)} · ID {escape(str(page_id))}"
    )
    return render_shell(
        title=f"Tin nhắn — {page_name}",
        active="messages",
        heading="Tin nhắn",
        sub=sub,
        actions=_page_select(pages, page_id, "/tin-nhan", all_label=all_label),
        body=f'<div class="inbox">{left}{right}</div>',
        full=True,
        script=_INBOX_JS.replace("__LIMIT__", str(limit))
                        .replace("__LIST_MS__", "15000" if merged else "10000"),
    )


# ----------------------------------------------------------------- khách hàng
def render_customers(
    pages: list[dict], page_id: str, page_name: str, convs: list[dict]
) -> str:
    """Bảng danh sách khách đã nhắn tin vào page (có ô tìm nhanh)."""
    rows = ""
    for c in convs:
        who = {"name": c["name"], "id": c.get("fb_id") or c.get("conv_id", "0")}
        unread = c.get("unread_count", 0)
        unread_html = f'<span class="unread">{unread}</span>' if unread else "—"
        rows += f"""
          <tr>
            <td><div style="display:flex;align-items:center;gap:10px">
              {_avatar({"name": who["name"], "id": who["id"]}).replace('class="avatar"', 'class="avatar sm"')}
              <span class="name">{escape(c["name"])}</span></div></td>
            <td><code>{escape(str(c.get("fb_id") or "—"))}</code></td>
            <td>{c.get("message_count", 0)}</td>
            <td>{unread_html}</td>
            <td title="{escape(_fmt_dt(c["updated_at"]))}">
              {escape(_relative_time(c["updated_at"]))}</td>
            <td><a class="btn" href="{conv_href(c, page_id, mode="inbox")}">Nhắn tin</a></td>
          </tr>"""

    table = (
        '<div class="twrap"><table class="tbl" id="tbl"><thead><tr>'
        "<th>Khách hàng</th><th>Facebook ID</th><th>Số tin</th><th>Chưa đọc</th>"
        "<th>Tương tác cuối</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        if convs
        else '<p class="empty">Chưa có khách nào nhắn tin vào page này.</p>'
    )

    search = (
        '<input class="inp" id="q" placeholder="Tìm theo tên hoặc ID…" '
        'style="min-width:220px" autocomplete="off">'
    )
    return render_shell(
        title=f"Khách hàng — {page_name}",
        active="customers",
        heading="Khách hàng",
        sub=f'{len(convs)} khách đã nhắn tin · {escape(page_name)}',
        actions=search + _page_select(pages, page_id, "/khach-hang"),
        body=table,
        script=_SEARCH_JS,
    )


def render_error(message: str, active: str = "dashboard") -> str:
    """Trang lỗi dùng chung cho các màn hình ở module này."""
    return render_shell(
        title="Lỗi",
        active=active,
        heading="Không tải được dữ liệu",
        body=f'<div class="flash err">✕ {escape(message)}</div>'
             '<p class="note">Kiểm tra lại cấu hình trong <code>.env</code> '
             "(token Pancake / khoá Supabase / OpenAI) rồi tải lại trang.</p>",
    )


# --- JS -----------------------------------------------------------------
# Tự làm mới cả 2 cột: danh sách hội thoại (10s) và khung chat (8s).
_INBOX_JS = """
(function(){
  var q = location.search || '?';
  function poll(id, url, ms, stick){
    var el = document.getElementById(id);
    if (!el) return;
    var last = null;
    // Đăng ký vào __pjaxTimers để _NAV_JS (shell.py) huỷ khi rời trang bằng
    // AJAX — không thì mỗi lần quay lại Tin nhắn lại chồng thêm 1 vòng poll.
    (window.__pjaxTimers = window.__pjaxTimers || []).push(setInterval(function(){
      if (document.hidden) return;
      fetch(url, {cache:'no-store'})
        .then(function(r){ return r.ok ? r.text() : null; })
        .then(function(html){
          if (html == null) return;
          if (last === null) { last = html; return; }   // mồi lần đầu
          if (html !== last) {
            var atEnd = stick &&
              (el.scrollHeight - el.scrollTop - el.clientHeight < 60);
            el.innerHTML = html; last = html;
            if (atEnd) el.scrollTop = el.scrollHeight;
          }
        })
        .catch(function(){});
    }, ms));
  }
  // Đang lọc thẻ (?tag=): danh sách là ảnh chụp mẻ lớn -> không tự nạp lại.
  // Nhịp: 10s cho 1 page, 15s cho hộp thư gộp (khớp cache gộp ở client.py, để
  // mỗi nhịp không bung ra N lời gọi Pancake).
  if (!/[?&]tag=/.test(q)) poll('feed', '/tin-nhan/fragment/list' + q, __LIST_MS__, false);
  poll('thread', '/tin-nhan/fragment/thread' + q, 8000, true);

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

  // Nút "Gợi ý trả lời": gọi RAG+LLM cho tin cuối của khách, đổ vào ô soạn để
  // người sửa rồi tự bấm Gửi. KHÔNG tự gửi. Đọc page_id/conv_id/customer_id từ
  // chính các input ẩn của composer (một nguồn dữ liệu duy nhất).
  var sug = document.getElementById('btn-suggest');
  var hint = document.getElementById('suggest-hint');
  if (sug) {
    sug.addEventListener('click', function(){
      var f = form;
      var body = new URLSearchParams({
        page_id: (f && f.page_id) ? f.page_id.value : '',
        conv_id: (f && f.conv_id) ? f.conv_id.value : '',
        customer_id: (f && f.customer_id) ? f.customer_id.value : ''
      });
      var old = sug.textContent;
      sug.disabled = true; sug.textContent = 'Đang soạn…';
      if (hint) { hint.textContent = ''; hint.classList.remove('warn'); }
      fetch('/tin-nhan/goi-y', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: body.toString()
      })
      .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
      .then(function(d){
        sug.disabled = false; sug.textContent = old;
        if (!d || d.error) {
          if (hint) { hint.textContent = '⚠ ' + ((d && d.error) || 'Không gợi ý được'); hint.classList.add('warn'); }
          return;
        }
        if (d.no_match || !d.reply) {   // câu hỏi chưa có trong tri thức -> KHÔNG gợi ý
          if (hint) {
            hint.textContent = d.nguon_text || 'Câu hỏi này chưa có trong tri thức — không gợi ý.';
            hint.classList.add('warn');
          }
          return;   // giữ nguyên ô soạn, không ghi đè
        }
        ta.value = d.reply;
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 130) + 'px';
        ta.focus();
        if (hint) hint.textContent = d.nguon_text || '';
      })
      .catch(function(){
        sug.disabled = false; sug.textContent = old;
        if (hint) { hint.textContent = '⚠ Lỗi mạng, thử lại.'; hint.classList.add('warn'); }
      });
    });
  }

  // Nút "Trích tri thức": đọc TOÀN BỘ hội thoại đang mở, gọi GPT đề xuất các
  // cặp hỏi-đáp (KHÔNG ghi DB) rồi hiện màn xem/sửa/bỏ từng dòng — chỉ dòng
  // người dùng bấm Lưu mới thật sự vào hoi_thoai_mau (human-in-the-loop, tri
  // thức y tế không được tự động vào kho mà chưa ai duyệt).
  var extBtn = document.getElementById('btn-extract');
  var extPanel = document.getElementById('extract-panel');

  function extractRow(item){
    var wrap = document.createElement('div');
    wrap.className = 'card ext-row';
    wrap.style.marginBottom = '10px';

    var head = document.createElement('label');
    head.className = 'check';
    var chk = document.createElement('input');
    chk.type = 'checkbox'; chk.checked = true; chk.className = 'ext-on';
    head.appendChild(chk);
    head.appendChild(document.createTextNode('Lưu cặp này'));
    wrap.appendChild(head);

    var qLabel = document.createElement('label');
    qLabel.appendChild(document.createTextNode('Câu hỏi'));
    var qTa = document.createElement('textarea');
    qTa.rows = 2; qTa.className = 'ext-q';
    qTa.value = (item && item.cau_hoi) || '';       // .value -> an toàn, không parse HTML
    qLabel.appendChild(qTa);
    wrap.appendChild(qLabel);

    var aLabel = document.createElement('label');
    aLabel.appendChild(document.createTextNode('Câu trả lời'));
    var aTa = document.createElement('textarea');
    aTa.rows = 3; aTa.className = 'ext-a';
    aTa.value = (item && item.cau_tra_loi) || '';
    aLabel.appendChild(aTa);
    wrap.appendChild(aLabel);

    var nLabel = document.createElement('label');
    nLabel.appendChild(document.createTextNode('Nguồn'));
    var nIn = document.createElement('input');
    nIn.className = 'ext-n'; nIn.value = 'chat_that';
    nLabel.appendChild(nIn);
    wrap.appendChild(nLabel);

    return wrap;
  }

  function closeExtract(){ extPanel.innerHTML = ''; }

  // Thanh đầu bảng: tiêu đề + nút ✕ Đóng. Có ở MỌI trạng thái (lỗi / không có
  // đề xuất / đã lưu / chưa lưu) vì bảng nằm chen giữa khung chat và ô soạn tin
  // — không đóng được thì vướng chỗ trả lời khách.
  function extractHead(){
    var head = document.createElement('div');
    head.className = 'ext-head';
    var title = document.createElement('b');
    title.textContent = '🧠 Trích tri thức';
    var x = document.createElement('button');
    x.type = 'button'; x.className = 'btn ext-close';
    x.textContent = '✕ Đóng';
    x.title = 'Đóng bảng trích tri thức';
    x.addEventListener('click', closeExtract);
    head.appendChild(title);
    head.appendChild(x);
    return head;
  }

  function renderExtractPanel(d){
    extPanel.innerHTML = '';
    if (!d) return;
    var box = document.createElement('div');
    box.className = 'card form';
    box.style.marginTop = '10px';
    box.appendChild(extractHead());
    if (d.error) {
      var err = document.createElement('div');
      err.className = 'flash err';
      err.textContent = '✕ ' + d.error;
      box.appendChild(err);
      extPanel.appendChild(box);
      return;
    }
    var items = d.items || [];
    if (!items.length) {
      var p = document.createElement('p');
      p.className = 'intro';
      p.textContent = d.note || 'Không có đề xuất nào.';
      box.appendChild(p);
      extPanel.appendChild(box);
      return;
    }
    var intro = document.createElement('p');
    intro.className = 'intro';
    intro.textContent = 'GPT đề xuất ' + items.length + ' cặp hỏi-đáp từ hội '
      + 'thoại này — xem/sửa rồi bấm Lưu (bỏ tick dòng nào không muốn lưu).';
    box.appendChild(intro);
    for (var i = 0; i < items.length; i++) box.appendChild(extractRow(items[i]));

    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:10px;align-items:center;margin-top:6px';
    var saveBtn = document.createElement('button');
    saveBtn.type = 'button'; saveBtn.className = 'btn primary';
    saveBtn.textContent = '💾 Lưu các mục đã chọn';
    // Nút đóng thứ 2 ở CUỐI bảng: danh sách đề xuất có thể dài, lưu xong mà
    // phải cuộn ngược lên đầu mới đóng được thì rất vướng.
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button'; closeBtn.className = 'btn';
    closeBtn.textContent = '✕ Đóng';
    closeBtn.addEventListener('click', closeExtract);
    var resultSpan = document.createElement('span');
    resultSpan.className = 'shint';
    actions.appendChild(saveBtn);
    actions.appendChild(closeBtn);
    actions.appendChild(resultSpan);
    box.appendChild(actions);

    saveBtn.addEventListener('click', function(){
      var rows = box.querySelectorAll('.ext-row');
      var payload = [];
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        if (!row.querySelector('.ext-on').checked) continue;
        var q = row.querySelector('.ext-q').value.trim();
        var a = row.querySelector('.ext-a').value.trim();
        var n = row.querySelector('.ext-n').value.trim();
        if (q && a) payload.push({cau_hoi: q, cau_tra_loi: a, nguon: n});
      }
      if (!payload.length) {
        resultSpan.classList.add('warn');
        resultSpan.textContent = 'Chưa chọn dòng nào để lưu.';
        return;
      }
      var oldTxt = saveBtn.textContent;
      saveBtn.disabled = true; saveBtn.textContent = 'Đang lưu…';
      fetch('/tin-nhan/trich-tri-thuc/luu', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({items: JSON.stringify(payload)}).toString()
      })
      .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
      .then(function(res){
        saveBtn.disabled = false; saveBtn.textContent = oldTxt;
        if (!res || res.error) {
          resultSpan.classList.add('warn');
          resultSpan.textContent = '⚠ ' + ((res && res.error) || 'Lỗi khi lưu');
          return;
        }
        resultSpan.classList.remove('warn');
        resultSpan.textContent = '✓ Đã lưu ' + res.saved + ' cặp hỏi-đáp'
          + ((res.errors && res.errors.length) ? ' (lỗi ' + res.errors.length + ' dòng)' : '') + '.';
      })
      .catch(function(){
        saveBtn.disabled = false; saveBtn.textContent = oldTxt;
        resultSpan.classList.add('warn');
        resultSpan.textContent = '⚠ Lỗi mạng, thử lại.';
      });
    });

    extPanel.appendChild(box);
  }

  if (extBtn && extPanel) {
    extBtn.addEventListener('click', function(){
      var f = form;
      var body = new URLSearchParams({
        page_id: (f && f.page_id) ? f.page_id.value : '',
        conv_id: (f && f.conv_id) ? f.conv_id.value : '',
        customer_id: (f && f.customer_id) ? f.customer_id.value : ''
      });
      var old = extBtn.textContent;
      extBtn.disabled = true; extBtn.textContent = 'Đang phân tích…';
      extPanel.innerHTML = '';
      fetch('/tin-nhan/trich-tri-thuc', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: body.toString()
      })
      .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
      .then(function(d){
        extBtn.disabled = false; extBtn.textContent = old;
        renderExtractPanel(d);
      })
      .catch(function(){
        extBtn.disabled = false; extBtn.textContent = old;
        renderExtractPanel({error: 'Lỗi mạng, thử lại.'});
      });
    });
  }

  // Nút "Copy": gom toàn bộ hội thoại đang hiển thị (#thread) thành text rồi chép
  // vào clipboard. Đọc DOM lúc bấm nên luôn khớp nội dung mới nhất (kể cả sau
  // auto-refresh). Có fallback execCommand cho trình duyệt không hỗ trợ clipboard.
  var cp = document.getElementById('btn-copy');
  if (cp) {
    cp.addEventListener('click', function(){
      var th = document.getElementById('thread');
      if (!th) return;
      var nameEl = document.querySelector('.chead .name');
      var lines = nameEl ? ['Hội thoại với ' + nameEl.textContent.trim(), ''] : [];
      var msgs = th.querySelectorAll('.msg');
      for (var i = 0; i < msgs.length; i++) {
        var who = msgs[i].classList.contains('out') ? 'Bác sĩ' : 'Khách';
        var b = msgs[i].querySelector('.bubble');
        var txt = b ? b.textContent.trim() : '';
        var tmEl = msgs[i].querySelector('.mtime');
        var tm = tmEl ? tmEl.textContent.trim() : '';
        if (txt) lines.push(who + (tm ? ' (' + tm + ')' : '') + ': ' + txt);
      }
      var text = lines.join('\\n');
      var old = cp.textContent;
      function done(ok){
        cp.textContent = ok ? '✓ Đã copy' : '✕ Lỗi copy';
        setTimeout(function(){ cp.textContent = old; }, 1500);
      }
      function fallback(){
        try {
          var t = document.createElement('textarea');
          t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
          document.body.appendChild(t); t.focus(); t.select();
          var ok = document.execCommand('copy');
          document.body.removeChild(t); done(ok);
        } catch (e) { done(false); }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function(){ done(true); }, fallback);
      } else { fallback(); }
    });
  }
})();
"""

# Lọc nhanh bảng khách hàng ngay tại trình duyệt (không gọi lại server).
_SEARCH_JS = """
(function(){
  var box = document.getElementById('q');
  var tbl = document.getElementById('tbl');
  if (!box || !tbl) return;
  box.addEventListener('input', function(){
    var kw = box.value.trim().toLowerCase();
    var rows = tbl.tBodies[0].rows;
    for (var i = 0; i < rows.length; i++) {
      var txt = rows[i].cells[0].textContent + ' ' + rows[i].cells[1].textContent;
      rows[i].style.display = txt.toLowerCase().indexOf(kw) === -1 ? 'none' : '';
    }
  });
})();
"""

# Bật/tắt page NGAY tại chỗ (AJAX) — không reload, không gọi lại số liệu dashboard.
# Thao tác chỉ ghi file JSON phía server; JS chỉ đổi nhãn/màu nút sau khi nhận JSON.
_DASHBOARD_JS = """
(function(){
  function setBtn(btn, on){
    btn.className = 'pgsw ' + (on ? 'on' : 'off');
    btn.textContent = on ? '● BẬT' : '○ TẮT';
    btn.title = on ? 'Đang BẬT — bấm để TẮT (chặn lấy/gửi tin của page này)'
                   : 'Đang TẮT — bấm để BẬT lại';
  }
  function post(url, data){
    return fetch(url, {
      method: 'POST',
      headers: {'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'fetch'},
      body: new URLSearchParams(data).toString()
    }).then(function(r){ return r.ok ? r.json() : null; });
  }
  // Bật/tắt 1 page
  var one = document.querySelectorAll('form[action="/bang-dieu-khien/page-switch"]');
  for (var i = 0; i < one.length; i++) {
    one[i].addEventListener('submit', function(e){
      e.preventDefault();
      var f = e.currentTarget;
      var btn = f.querySelector('button');
      var el = f.querySelector('input[name=page_id]');
      var pid = el ? el.value : '';
      if (!pid) return;
      btn.disabled = true;
      post('/bang-dieu-khien/page-switch', {page_id: pid})
        .then(function(d){ btn.disabled = false; if (d) setBtn(btn, d.enabled); })
        .catch(function(){ btn.disabled = false; });
    });
  }
  // Bật/tắt TẤT CẢ
  var all = document.querySelectorAll('form[action="/bang-dieu-khien/page-switch-all"]');
  for (var j = 0; j < all.length; j++) {
    all[j].addEventListener('submit', function(e){
      e.preventDefault();
      var f = e.currentTarget;
      var el = f.querySelector('input[name=action]');
      var action = el ? el.value : '';
      if (action === 'off' &&
          !confirm('Tắt tất cả page? Sẽ ngừng lấy/gửi tin của MỌI page.')) return;
      post('/bang-dieu-khien/page-switch-all', {action: action}).then(function(d){
        if (!d) return;
        var btns = document.querySelectorAll('.ds-page .pgsw');
        for (var k = 0; k < btns.length; k++) setBtn(btns[k], action === 'on');
      });
    });
  }
})();
"""
