"""Dựng HTML cho mục "Dữ liệu bot" — 3 tab (server-side render).

  - Kịch bản (bảng `kich_ban`): các bước bán hàng theo tên kịch bản.
  - Hội thoại mẫu (bảng `hoi_thoai_mau`): cặp hỏi–đáp dùng cho RAG.
  - Thử tin nhắn: mô phỏng tin khách để xem bot truy xuất được gì.
Hai tab đầu đều có: form thêm mới (tự tạo embedding khi lưu) + danh sách + nút xoá.

Phần khung (menu trái, topbar, CSS) lấy từ `app.web.shell`.
"""

import json
from datetime import datetime, timezone
from html import escape

from app.ai.prompt import NO_MATCH_SENTINEL
from app.core.config import settings
from app.integrations.pancake.client import mask_token
from app.integrations.pancake.switches import is_page_enabled
from app.web.shell import flash as flash_bar
from app.web.shell import render_shell, tabs_bar


def _fmt_dt(iso: str) -> str:
    """Đổi chuỗi ISO từ Supabase -> 'HH:MM dd/mm/yyyy'; rỗng nếu không parse được."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%H:%M %d/%m/%Y")


# 4 tab của mục "Dữ liệu bot": (đường dẫn, nhãn, khoá active)
_TABS = [
    ("/data/kich-ban", "Kịch bản", "kich-ban"),
    ("/data/hoi-thoai", "Hội thoại mẫu", "hoi-thoai"),
    ("/data/thu-tin-nhan", "Thử tin nhắn", "thu"),
    ("/data/thu-api", "Thử API", "api"),
]


def _page(
    title: str,
    active: str,
    sub: str,
    intro: str,
    form: str,
    listing: str,
    flash_html: str = "",
    script: str = "",
) -> str:
    """Bọc nội dung 1 tab vào khung chung (menu trái + topbar + dải tab)."""
    intro_html = f'<p class="intro">{intro}</p>' if intro else ""
    return render_shell(
        title=f"Dữ liệu bot — {title}",
        active="data",
        heading=title,
        sub=sub,
        tabs=tabs_bar(_TABS, active),
        body=flash_html + intro_html + form + listing,
        script=script,
    )


def _del_form(action: str) -> str:
    """Nút xoá (form POST + hỏi xác nhận trước khi gửi)."""
    return (
        f'<form class="del" method="post" action="{action}" '
        f'onsubmit="return confirm(\'Xoá dòng này?\')">'
        f'<button type="submit" title="Xoá">✕</button></form>'
    )


# ---------------------------------------------------------------- kịch bản
def render_scripts(rows: list[dict], ok: str = "", error: str = "") -> str:
    """Màn hình Kịch bản: form thêm bước + danh sách các bước đã có."""
    # Gom các bước theo tên kịch bản để dễ nhìn (rows đã sắp theo ten+buoc).
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("ten_kich_ban") or "(không tên)", []).append(r)

    blocks = []
    for ten, items in groups.items():
        lis = ""
        for r in items:
            dieu_kien = r.get("dieu_kien")
            buoc_tiep = r.get("buoc_tiep")
            meta_bits = []
            if dieu_kien:
                meta_bits.append(f"điều kiện: {escape(str(dieu_kien))}")
            if buoc_tiep is not None:
                meta_bits.append(f"→ bước {escape(str(buoc_tiep))}")
            meta = " · ".join(meta_bits)
            lis += f"""
              <li class="row">
                <span class="step">{escape(str(r.get('buoc')))}</span>
                <div class="rbody">
                  <div class="rtext">{escape(r.get('noi_dung') or '')}</div>
                  <div class="rmeta">{meta}</div>
                </div>
                {_del_form(f"/data/kich-ban/{r.get('id')}/xoa")}
              </li>"""
        blocks.append(
            f'<h3 class="grp">{escape(ten)} '
            f'<span class="count">{len(items)} bước</span></h3>'
            f'<ul class="list">{lis}</ul>'
        )
    listing = "".join(blocks) or '<p class="empty">Chưa có kịch bản nào.</p>'

    form = """
      <form class="card form" method="post" action="/data/kich-ban">
        <div class="grid2">
          <label>Tên kịch bản *
            <input name="ten_kich_ban" required placeholder="vd: tu_van_mat_ngu">
          </label>
          <label>Bước * (số)
            <input name="buoc" type="number" required placeholder="1">
          </label>
        </div>
        <label>Nội dung trả lời *
          <textarea name="noi_dung" rows="3" required
                    placeholder="Câu bot sẽ nói ở bước này…"></textarea>
        </label>
        <div class="grid2">
          <label>Điều kiện (tuỳ chọn)
            <input name="dieu_kien" placeholder="từ khoá / ý định kích hoạt">
          </label>
          <label>Bước tiếp (tuỳ chọn, số)
            <input name="buoc_tiep" type="number" placeholder="2">
          </label>
        </div>
        <button type="submit">Thêm bước kịch bản</button>
      </form>"""

    return _page(
        title="Kịch bản",
        active="kich-ban",
        sub="Các bước kịch bản bán hàng · bảng <code>kich_ban</code>",
        intro="Mỗi dòng là một <b>bước</b> trong kịch bản bán hàng. Khi lưu, nội "
              "dung được tự động tạo embedding.",
        form=form,
        listing=listing,
        flash_html=flash_bar(ok, error),
    )


# ------------------------------------------------------------ hội thoại mẫu
def render_qa(rows: list[dict], ok: str = "", error: str = "") -> str:
    """Màn hình Hội thoại mẫu: form thêm cặp hỏi–đáp + danh sách đã có."""
    lis = ""
    for r in rows:
        nguon = r.get("nguon")
        meta_bits = [_fmt_dt(r.get("created_at"))]
        if nguon:
            meta_bits.append(f"nguồn: {escape(str(nguon))}")
        lis += f"""
          <li class="row qa">
            <div class="rbody">
              <div class="q">Hỏi: {escape(r.get('cau_hoi') or '')}</div>
              <div class="a">Đáp: {escape(r.get('cau_tra_loi') or '')}</div>
              <div class="rmeta">{" · ".join(b for b in meta_bits if b)}</div>
            </div>
            {_del_form(f"/data/hoi-thoai/{r.get('id')}/xoa")}
          </li>"""
    listing = lis and f'<ul class="list">{lis}</ul>' or \
        '<p class="empty">Chưa có hội thoại mẫu nào.</p>'

    form = """
      <form class="card form" method="post" action="/data/hoi-thoai">
        <label>Câu hỏi của khách *
          <textarea name="cau_hoi" rows="2" required
                    placeholder="vd: Magie uống lúc nào?"></textarea>
        </label>
        <label>Câu trả lời của shop *
          <textarea name="cau_tra_loi" rows="3" required
                    placeholder="vd: Dạ uống sau ăn tối 30 phút ạ."></textarea>
        </label>
        <label>Nguồn (tuỳ chọn)
          <input name="nguon" placeholder="vd: chat_da_chot / nhap_tay">
        </label>
        <button type="submit">Thêm cặp hỏi–đáp</button>
      </form>"""

    return _page(
        title="Hội thoại mẫu",
        active="hoi-thoai",
        sub="Kho ngữ cảnh cho RAG · bảng <code>hoi_thoai_mau</code>",
        intro="Cặp hỏi–đáp dùng cho <b>RAG</b>: khi khách nhắn, bot tìm câu hỏi "
              "giống nhất ở đây để lấy ngữ cảnh trả lời. Câu hỏi được tạo embedding.",
        form=form,
        listing=listing,
        flash_html=flash_bar(ok, error),
    )


# ------------------------------------------------------------ thử tin nhắn
def _score_bar(sim: float) -> str:
    """Thanh màu thể hiện độ giống: xanh (khớp tốt) → xám (yếu)."""
    pct = max(0, min(100, int(sim * 100)))
    color = "var(--ok)" if sim >= 0.6 else ("var(--accent)" if sim >= 0.4
                                            else "var(--sub)")
    return (
        f'<div class="score"><span class="snum">{sim:.3f}</span>'
        f'<span class="sbar"><i style="width:{pct}%;background:{color}"></i></span>'
        f"</div>"
    )


def render_simulate(
    q: str = "",
    k: int = 5,
    threshold: float = 0.0,
    tra_loi: bool = False,
    vector: list[float] | None = None,
    result: dict | None = None,
    prompt: str = "",
    answer: str = "",
    answer_error: str = "",
    suggest: dict | None = None,
    suggest_error: str = "",
    error: str = "",
) -> str:
    """Màn hình mô phỏng: gõ tin khách -> xem DB truy xuất ra gì.

    KHÔNG gọi LLM, KHÔNG sửa dữ liệu — chỉ embed câu hỏi rồi chấm điểm tương
    đồng với dữ liệu đang có, và phơi ra đúng truy vấn đã gửi sang Supabase.
    """
    checked = "checked" if tra_loi else ""
    form = f"""
      <form class="card form" method="get" action="/data/thu-tin-nhan">
        <label>Tin nhắn giả lập của khách *
          <textarea name="q" rows="2" required
                    placeholder="vd: magie uống lúc nào ạ">{escape(q)}</textarea>
        </label>
        <div class="grid2">
          <label>Số kết quả mỗi bảng (match_count)
            <input name="k" type="number" min="1" max="20" value="{k}">
          </label>
          <label>Ngưỡng tương đồng (match_threshold)
            <input name="threshold" type="number" step="0.05" min="0" max="1"
                   value="{threshold}">
          </label>
        </div>
        <label class="check">
          <input type="checkbox" name="tra_loi" value="1" {checked}>
          Kèm câu trả lời của bot (gọi {settings.llm_model} — tốn thêm 1 lượt API)
        </label>
        <button type="submit">Thử truy xuất</button>
      </form>"""

    if error:
        return _page(
            title="Thử tin nhắn", active="thu", sub=_SIM_SUB, intro=_SIM_INTRO,
            form=form, listing="", flash_html=flash_bar(error=error))

    if not q or result is None:
        return _page(
            title="Thử tin nhắn", active="thu", sub=_SIM_SUB, intro=_SIM_INTRO,
            form=form,
            listing='<p class="empty">Nhập một tin nhắn rồi bấm '
                    '<b>Thử truy xuất</b> để xem bot lấy được gì từ database.</p>')

    # --- Bước 1: embedding gửi sang OpenAI ---
    dim = len(vector or [])
    head = ", ".join(f"{x:.4f}" for x in (vector or [])[:8])
    step1 = f"""
      <h3 class="grp">Bước 1 — Gửi sang OpenAI để vector hoá</h3>
      <div class="card mono">
        <div class="lbl">Đầu vào</div><div>{escape(q)}</div>
        <div class="lbl">Model</div><div>text-embedding-3-small</div>
        <div class="lbl">Kết quả</div>
        <div>vector <b>{dim}</b> chiều → [{escape(head)}, …]</div>
      </div>"""

    # --- Bước 2: truy vấn thật gửi sang Supabase ---
    r = result
    step2 = f"""
      <h3 class="grp">Bước 2 — Gọi RPC sang Supabase (Postgres tự tính)</h3>
      <div class="card mono">
        <div class="qline">POST /rest/v1/rpc/match_documents</div>
        <div class="qline">POST /rest/v1/rpc/match_kich_ban</div>
        <div class="lbl">Tham số gửi kèm</div>
        <div class="qline">{{ query_embedding: vector({dim}),
 match_count: {k}, match_threshold: {threshold} }}</div>
        <p class="note">Phép so sánh chạy <b>trong Postgres</b> bằng toán tử
        cosine <code>&lt;=&gt;</code> và dùng <b>index HNSW</b> — Python chỉ gửi
        vector rồi nhận kết quả đã xếp hạng (không kéo bảng về nữa).
        Dòng có điểm <b>&lt; {threshold}</b> bị hàm SQL loại.</p>
        <div class="lbl">hoi_thoai_mau</div>
        <div>{r['qa_total']} dòng · <b>{r['qa_with_emb']}</b> dòng có embedding</div>
        <div class="lbl">kich_ban</div>
        <div>{r['kb_total']} dòng · <b>{r['kb_with_emb']}</b> dòng có embedding</div>
      </div>"""

    # --- Bước 3: kết quả xếp hạng ---
    qa_items = ""
    for it in r["qa"]:
        qa_items += f"""
          <li class="row qa">
            <div class="rbody">
              <div class="q">Hỏi: {escape(it.get('cau_hoi') or '')}</div>
              <div class="a">Đáp: {escape(it.get('cau_tra_loi') or '')}</div>
            </div>
            {_score_bar(it['similarity'])}
          </li>"""
    qa_block = (f'<ul class="list">{qa_items}</ul>' if qa_items else
                '<p class="empty">Không có dòng nào trong <code>hoi_thoai_mau</code> '
                'có embedding để so khớp.</p>')

    kb_items = ""
    for it in r["scripts"]:
        kb_items += f"""
          <li class="row">
            <span class="step">{escape(str(it.get('buoc')))}</span>
            <div class="rbody">
              <div class="rtext">{escape(it.get('noi_dung') or '')}</div>
              <div class="rmeta">kịch bản: {escape(str(it.get('ten_kich_ban') or ''))}</div>
            </div>
            {_score_bar(it['similarity'])}
          </li>"""
    kb_block = (f'<ul class="list">{kb_items}</ul>' if kb_items else
                '<p class="empty">Không có dòng nào trong <code>kich_ban</code> '
                'có embedding để so khớp.</p>')

    step3 = (
        '<h3 class="grp">Bước 3 — Dữ liệu truy xuất được '
        '<span class="count">hoi_thoai_mau</span></h3>' + qa_block
        + '<h3 class="grp">Bước 3 — Dữ liệu truy xuất được '
          '<span class="count">kich_ban</span></h3>' + kb_block
        + f'<p class="note">Điểm càng gần <b>1.000</b> càng giống. Đang lọc ở '
          f'ngưỡng <b>{threshold}</b> — không dòng nào đạt thì trả <b>rỗng</b> '
          f'(giống n8n). Bot thật hiện chỉ dùng kết quả của '
          f'<code>hoi_thoai_mau</code> làm ngữ cảnh; <code>kich_ban</code> hiện '
          f'ở đây để bạn đối chiếu.</p>'
    )

    # --- Bước 4 (tuỳ chọn): trả lời dựa TOÀN BỘ tri thức truy xuất được ---
    step4 = ""
    if tra_loi:
        prompt_details = (
            f'<details><summary>Xem prompt đã gửi cho {settings.llm_model}</summary>'
            f'<pre class="prompt">{escape(prompt)}</pre></details>'
        )
        if answer_error:
            body = f'<div class="flash err">✕ {escape(answer_error)}</div>'
        elif NO_MATCH_SENTINEL in (answer or "").upper():
            # Theo persona mới: tri thức không đủ -> bot trả NO_MATCH, không tự bịa.
            body = (
                '<div class="flash err" style="background:'
                'color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn)">'
                f'∅ Tri thức không có thông tin phù hợp → bot trả <b>{NO_MATCH_SENTINEL}'
                '</b> (không tự trả lời)</div>' + prompt_details
            )
        else:
            n_ctx = len(r["qa"])
            canh_bao = (
                '<p class="note">Tri thức <b>rỗng</b> (không dòng nào đạt ngưỡng) '
                '— theo nguyên tắc, bot phải trả <b>NO_MATCH</b> chứ không tự '
                'trả lời.</p>' if n_ctx == 0 else
                f'<p class="note">Dựa trên <b>{n_ctx}</b> đoạn tri thức ở Bước 3.</p>'
            )
            body = f'<div class="answer">{escape(answer)}</div>{canh_bao}{prompt_details}'
        step4 = ('<h3 class="grp">Bước 4 — Trả lời theo toàn bộ tri thức '
                 f'<span class="count">{settings.llm_model} · để đối chiếu</span></h3>'
                 f'<div class="card">{body}</div>'
                 '<p class="note">⚠️ Ô này để model <b>tự viết</b> từ ngữ cảnh — có '
                 'thể sửa nghĩa câu mẫu (lược điều kiện, đổi sắc thái). <b>KHÔNG dùng '
                 'gửi khách</b>; câu gửi khách lấy ở Bước 5 (chọn + nguyên văn).</p>')

    # --- Bước 5 (tuỳ chọn): GIỐNG nút "Gợi ý trả lời" — GPT CHỌN / NO_MATCH ---
    step5 = ""
    if tra_loi:
        if suggest_error:
            body = f'<div class="flash err">✕ {escape(suggest_error)}</div>'
        elif suggest and not suggest.get("no_match"):
            body = (
                f'<div class="answer">{escape(suggest.get("reply") or "")}</div>'
                '<p class="note">GPT chỉ <b>CHỌN</b> 1 câu mẫu ở Bước 3, câu trên là '
                '<b>NGUYÊN VĂN</b> câu trả lời đã duyệt (không sửa chữ nào) — đúng '
                'câu sẽ hiện khi bấm nút <b>Gợi ý trả lời</b> ở màn Tin nhắn.</p>'
            )
        else:  # suggest is None hoặc no_match
            body = (
                '<div class="flash err" style="background:'
                'color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn)">'
                '∅ Không có câu mẫu nào phù hợp → <b>KHÔNG gợi ý</b></div>'
                '<p class="note">GPT xét top 3 câu mẫu ở Bước 3 và thấy không câu '
                'nào thực sự trả lời được — nên nút <b>Gợi ý trả lời</b> sẽ im lặng '
                '(không đổ chữ vào ô soạn).</p>'
            )
        step5 = ('<h3 class="grp">Bước 5 — Gợi ý trả lời '
                 '<span class="count">GPT chọn · NO_MATCH → không gợi ý</span></h3>'
                 f'<div class="card">{body}</div>'
                 '<p class="note">Khác Bước 4 (để model tự VIẾT — có thể lược mất vế '
                 'điều kiện, đổi sắc thái, trộn câu): Bước 5 chỉ <b>CHỌN</b> câu mẫu '
                 'rồi trả <b>NGUYÊN VĂN</b>, hoặc <b>NO_MATCH</b> nếu không câu nào '
                 'hợp. Đây là cách dùng cho nút Gợi ý thật. Nút thật lấy <b>top 5</b> '
                 'rồi đưa <b>top 3</b> lên GPT.</p>')

    return _page(
        title="Thử tin nhắn", active="thu", sub=_SIM_SUB, intro=_SIM_INTRO,
        form=form, listing=step1 + step2 + step3 + step4 + step5)


_SIM_SUB = "Mô phỏng tin khách để kiểm tra bot truy xuất được gì (chỉ đọc)"

_SIM_INTRO = (
    "Gõ một tin nhắn <b>giả làm khách</b> để xem bot moi được dữ liệu gì từ "
    "database. Mặc định <b>không gọi LLM</b> và <b>không sửa dữ liệu</b>; tick "
    "ô bên dưới nếu muốn xem luôn câu trả lời bot sẽ đưa ra."
)


# --------------------------------------------------------------- thử API
# Mẫu sẵn: (nhãn, method, path, "k=v" mỗi tham số, dùng public API?)
# Lấy đúng các endpoint mà app đang gọi thật (xem app/integrations/pancake/client.py).
_API_PRESETS = [
    ("Danh sách page", "GET", "pages", [], False),
    ("Hội thoại của 1 page", "GET", "pages/{page_id}/conversations",
     [("type", "INBOX"), ("limit", "5")], False),
    ("Tin nhắn của 1 hội thoại", "GET",
     "pages/{page_id}/conversations/{conv_id}/messages",
     [("customer_id", "")], False),
    ("Thẻ của 1 page (public API)", "GET", "pages/{page_id}/tags",
     [("page_access_token", "")], True),
]


def _kv_row(key: str = "", value: str = "") -> str:
    """1 dòng key/value trong bảng tham số (kiểu Postman)."""
    return (
        '<div class="pm-row">'
        f'<input class="inp" name="pk" placeholder="tên tham số" value="{escape(key)}">'
        f'<input class="inp" name="pv" placeholder="giá trị" value="{escape(value)}">'
        '<button type="button" class="pm-del" title="Xoá dòng">✕</button>'
        "</div>"
    )


def _json_block(data, limit: int = 200_000) -> tuple[str, str]:
    """Đổi body -> (text đã format, ghi chú nếu bị cắt bớt)."""
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = str(data)
    if len(text) > limit:
        return text[:limit], (
            f" · ⚠️ quá dài, chỉ hiện {limit:,} / {len(text):,} ký tự đầu"
        )
    return text, ""


def _api_reference(
    pages: list[dict], pages_error: str = "", collapsed: bool = False
) -> str:
    """Bảng tra cứu nhanh cho tab test: access_token đầy đủ + mọi page ID.

    ⚠️ CỐ Ý phơi bí mật ra màn hình — chỉ chấp nhận được vì đây là trang TEST
    chạy ở localhost. Xoá cả tab này trước khi mở app ra ngoài Internet
    (xem ghi chú "XOÁ KHI XONG DỰ ÁN" ở đầu mục thử API).
    """
    token = settings.pancake_access_token
    token_html = (
        f'<div class="pm-copy"><code id="pm-tok">{escape(token)}</code>'
        '<button type="button" class="btn pm-cp" data-cp="pm-tok">Copy</button></div>'
        if token else
        '<p class="note">Chưa có <code>PANCAKE_ACCESS_TOKEN</code> trong '
        "<code>.env</code>.</p>"
    )

    if pages_error:
        pages_html = f'<div class="flash err">✕ {escape(pages_error)}</div>'
    elif not pages:
        pages_html = '<p class="note">Chưa lấy được page nào.</p>'
    else:
        rows = ""
        for p in pages:
            pid = escape(str(p.get("id", "")))
            on = is_page_enabled(p.get("id", ""))
            rows += (
                '<tr>'
                f'<td>{escape(p.get("name") or "(không tên)")}</td>'
                f'<td><code class="pm-pid" role="button" tabindex="0" '
                f'title="Bấm để chèn vào ô đường dẫn">{pid}</code></td>'
                f'<td>{escape(p.get("platform") or "")}</td>'
                f'<td>{"● BẬT" if on else "○ TẮT"}</td>'
                "</tr>"
            )
        pages_html = (
            '<div class="tblwrap"><table class="tbl"><thead><tr>'
            "<th>Tên page</th><th>page_id</th><th>Nền tảng</th><th>Công tắc</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>"
            '<p class="note">Bấm vào một <code>page_id</code> để chèn thẳng vào ô '
            "đường dẫn (thay chỗ <code>{page_id}</code>).</p>"
        )

    # Gập lại khi ĐÃ có kết quả: bảng 22 page + token dài đẩy khối Response
    # xuống tận đáy trang, gọi xong tưởng như không có gì hiện ra.
    open_attr = "" if collapsed else " open"
    return f"""
      <details class="card pm-ref"{open_attr}>
        <summary>🔑 access_token + {len(pages)} page ID
          <span class="note">(trang test — bấm để mở/đóng)</span></summary>
        <div class="flash err" style="margin:12px 0">
          ⚠️ <b>Trang TEST</b> — cố ý hiện access_token và mọi page ID ra màn hình
          cho tiện thử. App chưa có lớp bảo mật nào, <b>đừng mở ra Internet</b> khi
          tab này còn tồn tại. Xoá tab trước khi dự án chạy thật.
        </div>
        <div class="lbl">PANCAKE_ACCESS_TOKEN (từ <code>.env</code>)</div>
        {token_html}
        <div class="lbl" style="margin-top:14px">Page ID ({len(pages)} page)</div>
        {pages_html}
      </details>"""


def render_api_test(
    method: str = "GET",
    path: str = "",
    pairs: list[tuple[str, str]] | None = None,
    public: bool = False,
    show_token: bool = True,
    result: dict | None = None,
    error: str = "",
    pages: list[dict] | None = None,
    pages_error: str = "",
) -> str:
    """Tab "Thử API": gọi thẳng endpoint Pancake và xem JSON gốc trả về.

    Bố cục kiểu Postman: thanh [method][URL][Gửi] + bảng tham số key/value,
    bên dưới là khối Response (mã trạng thái, thời gian, dung lượng, body).

    ⚠️ XOÁ KHI XONG DỰ ÁN — tab này phơi access_token + page ID ra màn hình,
    chỉ dùng để thử ở localhost. Muốn bỏ: xoá route `/data/thu-api`
    (app/web/routes/data.py), 3 hàm `render_api_test`/`_api_reference`/
    `_render_api_result` + `_API_JS`/`_API_PRESETS` ở file này, dòng tab trong
    `_TABS`, hàm `raw_call`/`mask_token` (app/integrations/pancake/client.py) và khối CSS
    "tab Thử API" trong app/web/shell.py.
    """
    rows = "".join(_kv_row(k, v) for k, v in (pairs or [])) or _kv_row()
    base = (
        settings.pancake_public_base_url if public else settings.pancake_base_url
    ).rstrip("/") + "/"

    def sel(value: str, current: str) -> str:
        return " selected" if value == current else ""

    preset_opts = "".join(
        f'<option value="{i}">{escape(p[0])}</option>'
        for i, p in enumerate(_API_PRESETS)
    )
    presets_json = json.dumps(
        [{"method": m, "path": p, "params": prm, "public": pub}
         for _lbl, m, p, prm, pub in _API_PRESETS],
        ensure_ascii=False,
    )

    form = f"""
      <form class="card pm" method="get" action="/data/thu-api">
        <div class="pm-bar">
          <select class="inp pm-method" name="http_method">
            <option value="GET"{sel("GET", method)}>GET</option>
            <option value="POST"{sel("POST", method)}>POST</option>
          </select>
          <span class="pm-base" title="Đổi bằng ô 'API' bên dưới">{escape(base)}</span>
          <input class="inp pm-path" name="path" value="{escape(path)}"
                 placeholder="pages/{{page_id}}/conversations" autocomplete="off">
          <button type="submit" class="btn primary pm-send">Gửi</button>
        </div>

        <div class="pm-opts">
          <label class="pm-inline">API
            <select class="inp" name="public">
              <option value="0"{sel("0", "1" if public else "0")}>Nội bộ (v1)</option>
              <option value="1"{sel("1", "1" if public else "0")}>Public API</option>
            </select>
          </label>
          <label class="pm-inline">Mẫu sẵn
            <select class="inp" id="pm-preset">
              <option value="">— chọn để điền nhanh —</option>{preset_opts}
            </select>
          </label>
          <label class="check pm-inline">
            <input type="checkbox" name="che_token" value="1"
                   {"" if show_token else "checked"}>
            Che bớt access_token
          </label>
        </div>

        <div class="pm-kv">
          <div class="pm-kv-head"><b>Tham số truy vấn</b>
            <button type="button" class="btn pm-add">+ Thêm dòng</button></div>
          <div id="pm-rows">{rows}</div>
        </div>
        <p class="note">API nội bộ tự đính kèm <code>access_token</code> từ
        <code>.env</code> — không cần tự gõ. Dòng để trống được bỏ qua.
        <b>POST có thể gửi tin thật tới khách</b> nên phải xác nhận trước khi gửi.</p>
      </form>"""

    if error:
        listing = ""
    elif result is None:
        listing = (
            '<p class="empty">Chọn một <b>mẫu sẵn</b> hoặc gõ đường dẫn rồi bấm '
            "<b>Gửi</b> để xem JSON gốc Pancake trả về.</p>"
        )
    else:
        listing = _render_api_result(result, show_token)

    return _page(
        title="Thử API", active="api",
        sub="Gọi thẳng Pancake API và xem JSON gốc (không qua lớp xử lý của app)",
        intro="Thay cho Postman: xem <b>đúng những gì đã gửi đi</b> (URL đầy đủ + "
              "từng tham số) và <b>đúng những gì máy chủ trả về</b> (mã trạng thái, "
              "thời gian, body chưa qua chuẩn hoá). Chỉ gọi API, "
              "<b>không đụng Supabase, không tốn lượt OpenAI</b>.",
        form=_api_reference(
            pages or [], pages_error, collapsed=result is not None
        ) + form,
        listing=listing,
        flash_html=flash_bar(error=error),
        script=_API_JS.replace("__PRESETS__", presets_json),
    )


def _render_api_result(r: dict, show_token: bool) -> str:
    """Khối Response kiểu Postman: trạng thái + request đã gửi + body."""
    status = int(r.get("status") or 0)
    tone = "ok" if 200 <= status < 300 else "err"
    ctype = (r.get("resp_headers") or {}).get("content-type", "").split(";")[0]
    size_kb = f"{(r.get('size') or 0) / 1024:,.1f} KB"

    # Tham số: che access_token trừ khi người dùng tự tick hiện.
    param_rows = ""
    for key, value in (r.get("params") or {}).items():
        secret = key in ("access_token", "page_access_token")
        shown = str(value) if (show_token or not secret) else mask_token(value)
        cls = ' class="pm-secret"' if secret else ""
        param_rows += (
            f'<div class="pm-prow"><code{cls}>{escape(str(key))}</code>'
            f"<span>{escape(shown)}</span></div>"
        )
    if not param_rows:
        param_rows = '<div class="pm-prow"><span class="note">(không có)</span></div>'

    # URL đầy đủ — cũng phải che token, vì đây là thứ hay bị chụp màn hình nhất.
    query = "&".join(
        f"{key}="
        + (str(val) if (show_token or key not in ("access_token", "page_access_token"))
           else mask_token(val))
        for key, val in (r.get("params") or {}).items()
    )
    full_url = r["url"] + (f"?{query}" if query else "")

    body_text, trimmed = _json_block(r.get("body"))
    kind = "JSON" if r.get("is_json") else "văn bản thô (không phải JSON)"

    return f"""
      <h3 class="grp">Response</h3>
      <div class="card">
        <div class="pm-status">
          <span class="pill {tone}">{status} {escape(str(r.get("reason") or ""))}</span>
          <span class="note">{r.get("elapsed_ms")} ms · {size_kb} ·
            {escape(ctype or "?")}</span>
        </div>
      </div>

      <h3 class="grp">Request đã gửi đi</h3>
      <div class="card">
        <div class="pm-url"><b>{escape(r.get("method") or "")}</b>
          <code>{escape(full_url)}</code></div>
        <div class="lbl">Tham số truyền vào ({len(r.get("params") or {})})</div>
        <div class="pm-params">{param_rows}</div>
      </div>

      <h3 class="grp">Body — {kind}{trimmed}</h3>
      <pre class="pm-json">{escape(body_text)}</pre>"""


# JS nhỏ cho tab Thử API: thêm/xoá dòng tham số + điền nhanh từ mẫu sẵn.
_API_JS = """
(function(){
  var rowsBox = document.getElementById('pm-rows');
  if (!rowsBox) return;
  var form = rowsBox.closest('form');

  function newRow(k, v){
    var d = document.createElement('div');
    d.className = 'pm-row';
    d.innerHTML =
      '<input class="inp" name="pk" placeholder="tên tham số">' +
      '<input class="inp" name="pv" placeholder="giá trị">' +
      '<button type="button" class="pm-del" title="Xoá dòng">✕</button>';
    d.children[0].value = k || '';
    d.children[1].value = v || '';
    return d;
  }

  var add = form.querySelector('.pm-add');
  if (add) add.addEventListener('click', function(){ rowsBox.appendChild(newRow()); });

  // Uỷ quyền sự kiện: nút ✕ của dòng thêm sau vẫn xoá được. Luôn chừa 1 dòng
  // trống để không rơi vào trạng thái không còn ô nào mà nhập.
  rowsBox.addEventListener('click', function(e){
    var btn = e.target.closest && e.target.closest('.pm-del');
    if (!btn) return;
    var row = btn.closest('.pm-row');
    if (row) row.remove();
    if (!rowsBox.querySelector('.pm-row')) rowsBox.appendChild(newRow());
  });

  // Luôn lấy ô qua form.elements[...]: an toàn kể cả khi tên ô trùng property
  // sẵn có của <form> (method/action/target...).
  function fld(name){ return form.elements[name]; }

  var presets = __PRESETS__;
  var sel = document.getElementById('pm-preset');
  if (sel) sel.addEventListener('change', function(){
    var p = presets[parseInt(sel.value, 10)];
    if (!p) return;
    fld('path').value = p.path;
    fld('http_method').value = p.method;
    fld('public').value = p.public ? '1' : '0';
    rowsBox.innerHTML = '';
    for (var i = 0; i < p.params.length; i++) {
      rowsBox.appendChild(newRow(p.params[i][0], p.params[i][1]));
    }
    if (!p.params.length) rowsBox.appendChild(newRow());
    fld('path').focus();
  });

  // Bấm 1 page_id ở bảng tra cứu -> chèn thẳng vào ô đường dẫn: thay chỗ
  // {page_id} nếu có, không thì nối vào sau "pages/". Đỡ phải copy tay.
  function usePageId(pid){
    var el = fld('path'), v = el.value;
    if (v.indexOf('{page_id}') >= 0) el.value = v.replace('{page_id}', pid);
    else if (!v.trim()) el.value = 'pages/' + pid + '/conversations';
    else el.value = v.replace(/pages\\/[^/]*/, 'pages/' + pid);
    el.focus();
  }
  document.querySelectorAll('.pm-pid').forEach(function(el){
    el.addEventListener('click', function(){ usePageId(el.textContent.trim()); });
  });

  // Nút Copy (token): clipboard API, có fallback cho trình duyệt cũ.
  document.querySelectorAll('.pm-cp').forEach(function(btn){
    btn.addEventListener('click', function(){
      var src = document.getElementById(btn.getAttribute('data-cp'));
      if (!src) return;
      var text = src.textContent, old = btn.textContent;
      function done(){ btn.textContent = '✓ Đã copy';
                       setTimeout(function(){ btn.textContent = old; }, 1200); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function(){});
        return;
      }
      var ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      document.body.removeChild(ta);
    });
  });

  // POST tới Pancake có thể GỬI TIN THẬT tới khách -> bắt xác nhận. Chặn ở
  // 'submit' và không preventDefault khi đồng ý, để _NAV_JS vẫn gửi bằng AJAX.
  form.addEventListener('submit', function(e){
    if (fld('http_method').value !== 'POST') return;
    var ok = confirm('POST có thể GỬI TIN THẬT tới khách hoặc đổi dữ liệu trên '
      + 'Pancake — không hoàn tác được.\\n\\nTiếp tục gửi?');
    if (!ok) e.preventDefault();
  });
})();
"""


def render_error(message: str) -> str:
    """Trang lỗi khi không đọc được dữ liệu (vd Supabase lỗi)."""
    return _page(
        title="Lỗi",
        active="",
        sub="Không đọc được dữ liệu từ Supabase",
        intro="Kiểm tra <code>SUPABASE_URL</code> / <code>SUPABASE_KEY</code> trong "
              "<code>.env</code>, hoặc chạy <code>scripts/rpc_match.sql</code> nếu "
              "thiếu hàm RPC.",
        form="",
        listing="",
        flash_html=flash_bar(error=message),
    )
