"""Dựng HTML cho 3 màn hình chung: Bảng điều khiển, Tin nhắn, Khách hàng.

Chỉ lo phần hiển thị — dữ liệu do `app/ui/routes.py` lấy sẵn rồi truyền vào.
Dùng lại các hàm dựng thẻ/bong bóng của Pancake để 2 màn chat giống hệt nhau.
"""

from html import escape
from urllib.parse import urlencode

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


def _page_select(pages: list[dict], current: str, base: str) -> str:
    """Ô chọn page ở góc phải topbar; đổi lựa chọn là nhảy trang luôn."""
    if not pages:
        return ""
    opts = ""
    for p in pages:
        sel = " selected" if p["id"] == str(current) else ""
        opts += f'<option value="{escape(p["id"])}"{sel}>{escape(p["name"])}</option>'
    return (
        f'<select class="inp" onchange="location.href=\'{base}?page_id=\'+this.value">'
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
          <li class="row" style="align-items:center">
            {_avatar(p).replace('class="avatar"', 'class="avatar sm"')}
            <div class="rbody">
              <div class="name">{escape(p.get("name") or "(không tên)")}</div>
              <div class="rmeta">ID {pid} · {escape(p.get("platform") or "")}</div>
            </div>
            {switch}
            <a class="btn" style="flex:0 0 auto" href="/tin-nhan?page_id={pid}">Mở tin nhắn</a>
          </li>"""
    return (
        '<section id="ds-page" class="ds-page"><div class="card">'
        '<div class="ds-page-head">'
        f'<b>Danh sách page ({len(pages)})</b>'
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
                   f'{data["qa_emb"]} dòng đã có embedding', tone=qa_tone)
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
        + kv("Supabase", pill(config["supabase"]))
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
) -> str:
    """Màn Tin nhắn 2 cột: trái = danh sách hội thoại, phải = khung chat."""
    lhead_label = (
        f"{len(convs)} hội thoại có thẻ « {escape(_tag_label(int(active_tag), tags_meta))} »"
        if active_tag and active_tag.lstrip("-").isdigit()
        else f"{len(convs)} hội thoại mới nhất"
    )
    # Đang lọc thẻ -> danh sách là "ảnh chụp" mẻ lớn, không tự cập nhật (cho nhẹ).
    live_html = (
        '<span class="live" style="margin-left:auto">'
        '<span class="dot"></span>tự cập nhật</span>'
        if not active_tag
        else '<span class="lhint" style="margin-left:auto">ảnh chụp</span>'
    )
    left = (
        '<div class="inbox-list">'
        f'<div class="lhead">{lhead_label}{live_html}</div>'
        f'{render_tag_filter(tags_facet or [], active_tag, page_id, tags_meta)}'
        f'<div class="lbody" id="feed">'
        f'{render_recent_list(convs, page_id, "INBOX", mode="inbox", active=conv_id, tag=active_tag)}'
        "</div></div>"
    )

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
            f'<div class="sub">{escape(page_name)}</div></div>'
            f'<a class="btn" href="{conv_href({"conv_id": conv_id, "customer_id": customer_id}, page_id)}">'
            "Mở toàn màn hình</a>"
            '<button type="button" id="btn-copy" class="btn" '
            'title="Sao chép toàn bộ hội thoại">📋 Copy</button></div>'
            + flash_html
            + f'<div class="thread" id="thread">'
              f'{render_thread(convo.get("messages") or [])}</div>'
            + '<div class="suggest-bar">'
              '<button type="button" id="btn-suggest" class="btn">'
              '💡 Gợi ý trả lời</button>'
              '<span class="shint" id="suggest-hint"></span>'
              "</div>"
            + render_composer(
                "/tin-nhan/tra-loi", customer_id,
                extra=f'<input type="hidden" name="page_id" '
                      f'value="{escape(str(page_id))}">'
                      f'<input type="hidden" name="conv_id" '
                      f'value="{escape(str(conv_id))}">',
            )
            + "</div>"
        )

    return render_shell(
        title=f"Tin nhắn — {page_name}",
        active="messages",
        heading="Tin nhắn",
        sub=f"{escape(page_name)} · ID {escape(str(page_id))}",
        actions=_page_select(pages, page_id, "/tin-nhan"),
        body=f'<div class="inbox">{left}{right}</div>',
        full=True,
        script=_INBOX_JS.replace("__LIMIT__", str(limit)),
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
    setInterval(function(){
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
    }, ms);
  }
  // Đang lọc thẻ (?tag=): danh sách là ảnh chụp mẻ lớn -> không tự nạp lại.
  if (!/[?&]tag=/.test(q)) poll('feed', '/tin-nhan/fragment/list' + q, 10000, false);
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
      if (ta.value.trim()) form.submit();
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
