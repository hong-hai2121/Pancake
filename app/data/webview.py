"""Dựng HTML cho mục "Dữ liệu bot" — 3 tab (server-side render).

  - Kịch bản (bảng `kich_ban`): các bước bán hàng theo tên kịch bản.
  - Hội thoại mẫu (bảng `hoi_thoai_mau`): cặp hỏi–đáp dùng cho RAG.
  - Thử tin nhắn: mô phỏng tin khách để xem bot truy xuất được gì.
Hai tab đầu đều có: form thêm mới (tự tạo embedding khi lưu) + danh sách + nút xoá.

Phần khung (menu trái, topbar, CSS) lấy từ `app.ui.shell`.
"""

from datetime import datetime, timezone
from html import escape

from app.ui.shell import flash as flash_bar
from app.ui.shell import render_shell, tabs_bar


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


# 3 tab của mục "Dữ liệu bot": (đường dẫn, nhãn, khoá active)
_TABS = [
    ("/data/kich-ban", "Kịch bản", "kich-ban"),
    ("/data/hoi-thoai", "Hội thoại mẫu", "hoi-thoai"),
    ("/data/thu-tin-nhan", "Thử tin nhắn", "thu"),
]


def _page(
    title: str,
    active: str,
    sub: str,
    intro: str,
    form: str,
    listing: str,
    flash_html: str = "",
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
          Kèm câu trả lời của bot (gọi gpt-4o-mini — tốn thêm 1 lượt API)
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

    # --- Bước 4 (tuỳ chọn): đưa ngữ cảnh cho LLM và lấy câu trả lời ---
    step4 = ""
    if tra_loi:
        if answer_error:
            body = f'<div class="flash err">✕ {escape(answer_error)}</div>'
        else:
            n_ctx = len(r["qa"])
            canh_bao = (
                '<p class="note">⚠️ Ngữ cảnh <b>rỗng</b> (không dòng nào đạt '
                'ngưỡng) — câu trả lời dưới đây do LLM tự bịa, không dựa trên '
                'dữ liệu của bạn.</p>' if n_ctx == 0 else
                f'<p class="note">Dùng <b>{n_ctx}</b> đoạn ngữ cảnh ở Bước 3.</p>'
            )
            body = (
                f'<div class="answer">{escape(answer)}</div>{canh_bao}'
                f'<details><summary>Xem prompt đã gửi cho gpt-4o-mini</summary>'
                f'<pre class="prompt">{escape(prompt)}</pre></details>'
            )
        step4 = ('<h3 class="grp">Bước 4 — Câu trả lời của bot '
                 '<span class="count">gpt-4o-mini</span></h3>'
                 f'<div class="card">{body}</div>')

    return _page(
        title="Thử tin nhắn", active="thu", sub=_SIM_SUB, intro=_SIM_INTRO,
        form=form, listing=step1 + step2 + step3 + step4)


_SIM_SUB = "Mô phỏng tin khách để kiểm tra bot truy xuất được gì (chỉ đọc)"

_SIM_INTRO = (
    "Gõ một tin nhắn <b>giả làm khách</b> để xem bot moi được dữ liệu gì từ "
    "database. Mặc định <b>không gọi LLM</b> và <b>không sửa dữ liệu</b>; tick "
    "ô bên dưới nếu muốn xem luôn câu trả lời bot sẽ đưa ra."
)


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
