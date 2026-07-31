"""Dựng HTML cho màn hình Cảm xúc (quét tin nhắn tiêu cực)."""

import re
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlencode

from app.ai import sentiment as sentiment_engine
from app.web.shell import flash, render_shell, stat

# Pancake trả giờ UTC; hiển thị theo giờ VN cho khớp các màn khác.
_TZ = timezone(timedelta(hours=7))


def _gio(value) -> str:
    """datetime/chuỗi ISO -> "HH:MM · dd/mm" theo giờ VN ("" nếu không parse được)."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_TZ).strftime("%H:%M · %d/%m")


def _link_hoi_thoai(row: dict) -> str:
    """Đường dẫn mở đúng hội thoại đó ở màn Tin nhắn (hộp thư gộp)."""
    params = {
        "page_id": "ALL",
        "conv_id": row.get("conv_id") or "",
        "conv_page_id": row.get("page_id") or "",
    }
    if row.get("customer_id"):
        params["customer_id"] = row["customer_id"]
    return "/tin-nhan?" + urlencode(params)


def _the_tieu_cuc(row: dict) -> str:
    """1 dòng trong danh sách hội thoại tiêu cực."""
    return f"""
      <li class="card link-row">
        <div class="info">
          <div class="crow">
            <span class="name">{escape(row.get("name") or "(không tên)")}</span>
            <span class="time">{escape(_gio(row.get("sentiment_checked_at")))}</span>
          </div>
          <div class="cpage">{escape(row.get("page_name") or "")}</div>
          <div class="snippet">{escape(row.get("snippet") or "")}</div>
          <div class="badges">
            <span class="neg">⚠ tiêu cực</span>
            <span class="badge">{escape(row.get("sentiment_method") or "")}</span>
          </div>
        </div>
        <a class="btn" href="{_link_hoi_thoai(row)}">Mở hội thoại →</a>
      </li>"""


def _the_nhat_ky(row: dict) -> str:
    """1 dòng trong nhật ký quét gần đây."""
    kq = row.get("sentiment") or "?"
    pill = (
        '<span class="neg">tiêu cực</span>' if kq == "negative"
        else f'<span class="badge">{escape(kq)}</span>'
    )
    return f"""
      <tr>
        <td class="nowrap">{escape(_gio(row.get("sentiment_checked_at")))}</td>
        <td>{escape(row.get("page_name") or "")}</td>
        <td>{escape(row.get("name") or "")}</td>
        <td class="snip">{escape((row.get("snippet") or "")[:90])}</td>
        <td class="nowrap">{pill}</td>
      </tr>"""


def _to_sang(snippet: str, tu_khoa: list[str], gioi_han: int = 110) -> str:
    """Escape `snippet` rồi bọc `<mark>` quanh các cụm từ khoá đã khớp.

    Cắt bớt cho vừa ô nhưng CỬA SỔ CẮT bám theo cụm khớp đầu tiên: cắt cứng 110
    ký tự đầu thì từ khoá nằm ở cuối câu dài sẽ không bao giờ lộ ra, đúng lúc
    người dùng cần nhìn nhất. Cắt ở giữa thì thêm "…" hai đầu cho biết còn nữa.

    Luật khớp lặp lại `mau_khop` của sentiment_engine (ranh giới từ) thay vì tìm
    chuỗi con: từ khoá đã lưu chắc chắn có trong câu, nhưng tìm thô có thể tô
    nhầm chỗ khác (vd "ngu" trong "Nguyễn") — nơi quyết định tiêu cực vẫn là
    sentiment_engine, đây chỉ là phần nhìn.
    """
    if not snippet:
        return ""
    if not tu_khoa:
        return escape(snippet[:gioi_han])

    vung: list[tuple[int, int]] = []
    for kw in tu_khoa:
        for m in re.finditer(sentiment_engine.mau_khop(kw), snippet, re.IGNORECASE):
            vung.append((m.start(), m.end()))
    if not vung:
        return escape(snippet[:gioi_han])
    vung.sort()

    # Cửa sổ hiển thị: mở từ trước cụm khớp đầu tiên một quãng cho có ngữ cảnh.
    dau = 0
    if vung[0][0] > gioi_han - 40:
        dau = max(0, vung[0][0] - 30)
    cuoi = dau + gioi_han

    ra = "… " if dau else ""
    vi_tri = dau
    for bat_dau, ket_thuc in vung:
        if ket_thuc <= dau or bat_dau >= cuoi:      # nằm ngoài cửa sổ
            continue
        ra += escape(snippet[vi_tri:bat_dau])
        ra += f'<mark class="kw">{escape(snippet[bat_dau:ket_thuc])}</mark>'
        vi_tri = ket_thuc
    ra += escape(snippet[vi_tri:cuoi])
    if len(snippet) > cuoi:
        ra += " …"
    return ra


def _the_canh_bao(row: dict) -> str:
    """1 dòng trong SỔ cảnh báo tiêu cực (bảng riêng, không bao giờ xoá).

    Khác `_the_nhat_ky`: nội dung ở đây là bản CHỤP lúc phát hiện, nên vẫn đọc
    được đúng câu đã làm bung cảnh báo dù về sau khách nhắn tiếp hàng chục tin.
    """
    tu_khoa = row.get("tu_khoa_khop") or []
    if tu_khoa:
        khop_html = "".join(
            f'<span class="kwhit">{escape(kw)}</span>' for kw in tu_khoa
        )
    elif (row.get("cach_quet") or "") == "llm":
        khop_html = '<span class="rmeta" title="LLM tự đọc ngữ cảnh, không dựa trên từ khoá">LLM quyết định</span>'
    else:
        # Dòng ghi TRƯỚC khi có tính năng này — cố ý không dò lại (xem sentiment_log).
        khop_html = '<span class="rmeta" title="Dòng ghi trước khi có tính năng lưu từ khoá">—</span>'
    return f"""
      <tr>
        <td class="nowrap">{escape(_gio(row.get("phat_hien_luc")))}</td>
        <td>{escape(row.get("page_name") or "")}</td>
        <td>{escape(row.get("name") or "")}</td>
        <td class="snip-kw">{_to_sang(row.get("snippet") or "", tu_khoa)}</td>
        <td class="nowrap">{khop_html}</td>
        <td class="nowrap"><span class="badge">{escape(row.get("cach_quet") or "")}</span></td>
        <td class="nowrap"><a class="btn" href="{_link_hoi_thoai(row)}">Mở →</a></td>
      </tr>"""


def _khung_tu_khoa(tu_khoa: list[str]) -> str:
    """Khung thêm/xoá/sửa hàng loạt danh sách từ khoá tiêu cực.

    Mỗi từ khoá là 1 chip kèm nút xoá; dưới cùng có ô sửa hàng loạt (mỗi dòng 1
    từ) cho ai muốn dán cả danh sách vào. File `keywords.json` được `analyze()`
    đọc lại MỖI lần quét nên sửa xong là có tác dụng ngay, không cần restart.
    """
    chips = "".join(
        f"""
        <form class="kwchip" method="post" action="/cam-xuc/tu-khoa/xoa">
          <input type="hidden" name="tu_khoa" value="{escape(kw, quote=True)}">
          <span>{escape(kw)}</span>
          <button type="submit" title="Xoá từ khoá này">×</button>
        </form>"""
        for kw in tu_khoa
    ) or '<p class="empty">Chưa có từ khoá nào.</p>'

    # Dòng xem trước gọn 1 hàng khi đang thu lại — thấy ngay vài từ đầu mà không
    # phải mở ra; phần dư bị CSS cắt bằng dấu "…".
    xem_truoc = escape(" · ".join(tu_khoa)) or "(chưa có từ nào)"

    return f"""
      <div class="card">
        <form class="kwadd" method="post" action="/cam-xuc/tu-khoa/them">
          <input class="inp" type="text" name="tu_khoa" required
                 placeholder="Thêm từ khoá / cụm từ, ví dụ: chậm giao hàng"
                 maxlength="80">
          <button class="btn primary" type="submit">Thêm</button>
        </form>
        <details class="kwbox">
          <summary>
            <span class="kwsum-n">{len(tu_khoa)} từ khoá</span>
            <span class="kwsum-preview">{xem_truoc}</span>
            <span class="kwsum-more">xem / sửa</span>
          </summary>
          <div class="kwlist">{chips}</div>
          <div class="kwbulk">
            <form method="post" action="/cam-xuc/tu-khoa/luu">
              <div class="kwbulk-lbl">Sửa hàng loạt — mỗi dòng 1 từ khoá</div>
              <textarea class="inp" name="danh_sach" rows="10"
                spellcheck="false">{escape(chr(10).join(tu_khoa))}</textarea>
              <p class="note">Lưu là thay thế TOÀN BỘ danh sách. Khớp theo ranh
                giới từ nên "kiện" không dính vào "điều kiện".</p>
              <button class="btn primary" type="submit">Lưu danh sách</button>
            </form>
          </div>
        </details>
      </div>"""


def render_cam_xuc(
    bat: bool,
    cach_quet: str,
    so_lieu: dict,
    tieu_cuc: list[dict],
    nhat_ky: list[dict],
    tu_khoa: list[str],
    telegram_chat: str = "",
    loi_kho: str = "",
    ok: str = "",
    error: str = "",
    canh_bao: list[dict] | None = None,
    so_canh_bao: dict | None = None,
) -> str:
    """Trang /cam-xuc: công tắc + số liệu + danh sách tiêu cực + nhật ký quét.

    `telegram_chat` = chat id đang cấu hình ("" nghĩa là chưa cấu hình -> tính
    năng báo Telegram đang TẮT, worker sẽ bỏ qua bước gửi mà không báo lỗi).

    `canh_bao` / `so_canh_bao` = SỔ cảnh báo vĩnh viễn (`watcher.canh_bao_tieu_cuc`).
    Cố tình tách khỏi `tieu_cuc`: cái kia là trạng thái HIỆN TẠI (khách nhắn thêm
    câu bình thường là hội thoại rơi khỏi danh sách), còn sổ thì giữ mãi.
    """
    canh_bao = canh_bao or []
    so_canh_bao = so_canh_bao or {}
    nut_thu = (
        '<form method="post" action="/cam-xuc/thu-telegram" style="display:inline">'
        '<button class="btn" type="submit">Gửi tin thử</button></form>'
    )
    telegram_html = (
        f'<span class="pill ok">✓ đã cấu hình</span> <code>chat {escape(telegram_chat)}</code> {nut_thu}'
        if telegram_chat else
        '<span class="pill err">chưa cấu hình</span> — điền '
        '<code>TELEGRAM_BOT_TOKEN</code> + <code>TELEGRAM_CHAT_ID</code> vào '
        '<code>.env</code> gốc rồi khởi động lại app'
    )
    # --- công tắc BẬT/TẮT ---
    trang_thai = (
        '<span class="pill ok">🟢 ĐANG QUÉT</span>' if bat
        else '<span class="pill err">⏸ ĐANG TẮT</span>'
    )
    nut_bat_tat = (
        '<form method="post" action="/cam-xuc/bat-tat" style="display:inline">'
        f'<button class="btn {"" if bat else "primary"}" type="submit">'
        f'{"Tắt quét cảm xúc" if bat else "Bật quét cảm xúc"}</button></form>'
    )

    # --- chọn cách quét ---
    def _nut_cach(gia_tri: str, nhan: str, mo_ta: str) -> str:
        dang_chon = cach_quet == gia_tri
        return (
            '<form method="post" action="/cam-xuc/cach-quet" style="display:inline">'
            f'<input type="hidden" name="cach_quet" value="{gia_tri}">'
            f'<button class="btn{" primary" if dang_chon else ""}" type="submit" '
            f'title="{escape(mo_ta)}">{"● " if dang_chon else ""}{escape(nhan)}</button>'
            "</form>"
        )

    cong_tac = f"""
      <div class="card">
        <div class="kv"><span class="k">Trạng thái worker</span>
          <span class="v">{trang_thai} {nut_bat_tat}</span></div>
        <div class="kv"><span class="k">Cách quét</span><span class="v">
          {_nut_cach("keyword", "Từ khoá", "Khớp danh sách từ khoá tiếng Việt — "
                     "chạy tại máy, miễn phí, không cần internet")}
          {_nut_cach("llm", "LLM (OpenAI)", "Nhờ model đọc hiểu ngữ cảnh — chính xác "
                     "hơn nhưng mỗi hội thoại mới tốn 1 lượt gọi có phí")}
        </span></div>
        <div class="kv"><span class="k">Danh sách từ khoá</span><span class="v">
          <code>{len(tu_khoa)}</code> từ — sửa ở khung bên dưới (dùng chung với app
          "Pancake Watcher", cùng đọc <code>keywords.json</code>)</span></div>
        <div class="kv"><span class="k">Báo Telegram</span><span class="v">{telegram_html}</span></div>
        <div class="kv"><span class="k">Quét lại</span><span class="v">
          <form method="post" action="/cam-xuc/quet-lai" style="display:inline">
            <button class="btn" type="submit"
              title="Xoá dấu đã quét của các hội thoại CHƯA từng tiêu cực để worker
                     quét lại theo từ khoá mới. Hội thoại đã tiêu cực được giữ nguyên.">
              Quét lại theo từ khoá mới</button>
          </form></span></div>
      </div>"""

    # --- số liệu ---
    if loi_kho:
        so_lieu_html = f'<div class="flash err">✕ Không đọc được kho: {escape(loi_kho)}</div>'
    else:
        so_lieu_html = (
            '<div class="stats">'
            + stat("Hội thoại trong kho", str(so_lieu.get("tong", 0)),
                   "poller nền tự đổ về")
            + stat("Đã quét cảm xúc", str(so_lieu.get("da_quet", 0)))
            + stat("Đang chờ quét", str(so_lieu.get("cho_quet", 0)),
                   "hết = worker đã theo kịp",
                   tone="warn" if so_lieu.get("cho_quet") else "")
            + stat("Đang tiêu cực", str(so_lieu.get("tieu_cuc", 0)),
                   "theo tin nhắn MỚI NHẤT",
                   tone="err" if so_lieu.get("tieu_cuc") else "ok")
            + stat("Đã vào sổ cảnh báo", str(so_canh_bao.get("tong", 0)),
                   f'{so_canh_bao.get("so_hoi_thoai", 0)} hội thoại · giữ vĩnh viễn')
            + "</div>"
        )

    # --- danh sách tiêu cực ---
    ds_tieu_cuc = (
        f'<ul class="list">{"".join(_the_tieu_cuc(r) for r in tieu_cuc)}</ul>'
        if tieu_cuc
        else '<p class="empty">Chưa phát hiện hội thoại tiêu cực nào.</p>'
    )

    # --- nhật ký quét ---
    if nhat_ky:
        nhat_ky_html = (
            '<div class="tblwrap"><table class="tbl"><thead><tr>'
            "<th>Lúc</th><th>Page</th><th>Khách</th><th>Nội dung</th><th>Kết quả</th>"
            "</tr></thead><tbody>"
            + "".join(_the_nhat_ky(r) for r in nhat_ky)
            + "</tbody></table></div>"
        )
    else:
        nhat_ky_html = '<p class="empty">Chưa quét hội thoại nào.</p>'

    # --- sổ cảnh báo vĩnh viễn ---
    if canh_bao:
        canh_bao_html = (
            '<div class="tblwrap"><table class="tbl"><thead><tr>'
            "<th>Phát hiện lúc</th><th>Page</th><th>Khách</th>"
            "<th>Nội dung lúc đó</th><th>Khớp từ</th><th>Cách quét</th><th></th>"
            "</tr></thead><tbody>"
            + "".join(_the_canh_bao(r) for r in canh_bao)
            + "</tbody></table></div>"
        )
    else:
        canh_bao_html = (
            '<p class="empty">Sổ chưa có dòng nào — chưa phát hiện tiêu cực lần nào '
            "kể từ khi bật tính năng này.</p>"
        )

    body = (
        flash(ok, error)
        + '<h2 class="grp">Công tắc</h2>' + cong_tac
        + f'<h2 class="grp">Từ khoá tiêu cực <span class="count">{len(tu_khoa)}</span></h2>'
        + _khung_tu_khoa(tu_khoa)
        + '<h2 class="grp">Số liệu</h2>' + so_lieu_html
        + f'<h2 class="grp">Sổ cảnh báo tiêu cực '
          f'<span class="count">{so_canh_bao.get("tong", 0)}</span></h2>'
        + '<p class="intro">Mỗi lần phát hiện là một dòng, <b>không bao giờ bị xoá '
          'hay ghi đè</b> — một tháng sau vẫn tra được. Nội dung là bản chụp đúng '
          'lúc bung cảnh báo, <b>từ khoá đã khớp được tô vàng</b> ngay trong câu '
          'để soi được ca báo nhầm.</p>'
        + canh_bao_html
        + f'<h2 class="grp">Đang tiêu cực <span class="count">{len(tieu_cuc)}</span></h2>'
        + '<p class="intro">Xét theo tin nhắn <b>mới nhất</b> của hội thoại. Khách '
          'nhắn tiếp câu bình thường thì hội thoại rời khỏi mục này — nhưng vẫn còn '
          'nguyên trong sổ ở trên.</p>'
        + ds_tieu_cuc
        + '<h2 class="grp">Nhật ký quét gần đây</h2>' + nhat_ky_html
    )

    return render_shell(
        title="Cảm xúc",
        active="sentiment",
        heading="Quét tin nhắn tiêu cực",
        sub="Worker nền tự quét mọi hội thoại mới · "
            '<span class="live"><span class="dot"></span>tự cập nhật</span>',
        body=body,
        script=_JS,
    )


# Tự tải lại trang mỗi 15s để số liệu/nhật ký luôn mới mà không phải F5.
# Dừng khi tab ẩn để không tốn tài nguyên vô ích.
_JS = """
(function(){
  (window.__pjaxTimers = window.__pjaxTimers || []).push(setInterval(function(){
    if (document.hidden) return;
    if (document.querySelector('.flash')) return;   // đang hiện thông báo -> để yên
    fetch(location.pathname, {cache:'no-store'})
      .then(function(r){ return r.ok ? r.text() : null; })
      .then(function(html){
        if (!html) return;
        var moi = new DOMParser().parseFromString(html, 'text/html')
                    .querySelector('.content');
        var cu = document.querySelector('.content');
        if (moi && cu && moi.innerHTML !== cu.innerHTML) cu.innerHTML = moi.innerHTML;
      })
      .catch(function(){});
  }, 15000));
})();
"""
