"""Dựng HTML cho giao diện quản lý dữ liệu bot (server-side render).

Hai màn hình:
  - Kịch bản (bảng `kich_ban`): các bước bán hàng theo tên kịch bản.
  - Hội thoại mẫu (bảng `hoi_thoai_mau`): cặp hỏi–đáp dùng cho RAG.
Cả hai đều: form thêm mới (tự tạo embedding khi lưu) + danh sách đã có + nút xoá.
"""

from datetime import datetime, timezone
from html import escape


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


def _nav(active: str) -> str:
    """Thanh chuyển màn hình; `active` = 'kich-ban' | 'hoi-thoai' | 'thu'."""
    def tab(href: str, label: str, key: str) -> str:
        cls = "tab on" if key == active else "tab"
        return f'<a class="{cls}" href="{href}">{label}</a>'

    return (
        '<nav class="tabs">'
        + tab("/data/kich-ban", "Kịch bản", "kich-ban")
        + tab("/data/hoi-thoai", "Hội thoại mẫu", "hoi-thoai")
        + tab("/data/thu-tin-nhan", "Thử tin nhắn", "thu")
        + "</nav>"
    )


def _flash(ok: str, error: str) -> str:
    """Dải thông báo kết quả sau khi thêm/xoá."""
    if ok:
        return f'<div class="flash ok">✓ {escape(ok)}</div>'
    if error:
        return f'<div class="flash err">✕ {escape(error)}</div>'
    return ""


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

    return _TEMPLATE.format(
        title="Kịch bản",
        nav=_nav("kich-ban"),
        flash=_flash(ok, error),
        intro="Mỗi dòng là một <b>bước</b> trong kịch bản bán hàng. Khi lưu, nội "
              "dung được tự động tạo embedding.",
        form=form,
        listing=listing,
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

    return _TEMPLATE.format(
        title="Hội thoại mẫu",
        nav=_nav("hoi-thoai"),
        flash=_flash(ok, error),
        intro="Cặp hỏi–đáp dùng cho <b>RAG</b>: khi khách nhắn, bot tìm câu hỏi "
              "giống nhất ở đây để lấy ngữ cảnh trả lời. Câu hỏi được tạo embedding.",
        form=form,
        listing=listing,
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
        return _TEMPLATE.format(
            title="Thử tin nhắn", nav=_nav("thu"),
            flash=f'<div class="flash err">✕ {escape(error)}</div>',
            intro=_SIM_INTRO, form=form, listing="")

    if not q or result is None:
        return _TEMPLATE.format(
            title="Thử tin nhắn", nav=_nav("thu"), flash="",
            intro=_SIM_INTRO, form=form,
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

    return _TEMPLATE.format(
        title="Thử tin nhắn", nav=_nav("thu"), flash="",
        intro=_SIM_INTRO, form=form, listing=step1 + step2 + step3 + step4)


_SIM_INTRO = (
    "Gõ một tin nhắn <b>giả làm khách</b> để xem bot moi được dữ liệu gì từ "
    "database. Mặc định <b>không gọi LLM</b> và <b>không sửa dữ liệu</b>; tick "
    "ô bên dưới nếu muốn xem luôn câu trả lời bot sẽ đưa ra."
)


def render_error(message: str) -> str:
    """Trang lỗi khi không đọc được dữ liệu (vd Supabase lỗi)."""
    return _TEMPLATE.format(
        title="Lỗi",
        nav=_nav(""),
        flash=f'<div class="flash err">✕ {escape(message)}</div>',
        intro="",
        form="",
        listing="",
    )


_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Dữ liệu bot</title>
<style>
  :root {{
    --bg: #f5f6f8; --card: #ffffff; --text: #1f2328; --sub: #6b7280;
    --border: #e5e7eb; --accent: #2563eb; --ok: #16a34a; --err: #dc2626;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --sub: #9198a1;
      --border: #30363d; --accent: #4493f8; --ok: #3fb950; --err: #f85149;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text); padding: 20px;
    font-family: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
    line-height: 1.45;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 10px; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 14px; }}
  .tab {{
    padding: 7px 14px; border-radius: 20px; text-decoration: none;
    border: 1px solid var(--border); color: var(--sub); font-size: 14px;
  }}
  .tab.on {{ background: var(--accent); border-color: var(--accent); color: #fff;
             font-weight: 600; }}
  .intro {{ color: var(--sub); font-size: 13px; margin-bottom: 14px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
  }}
  .form label {{ display: block; font-size: 13px; color: var(--sub);
                 margin-bottom: 10px; }}
  .form input, .form textarea {{
    display: block; width: 100%; margin-top: 4px; padding: 8px 10px;
    border: 1px solid var(--border); border-radius: 8px; font: inherit;
    font-size: 14px; background: var(--bg); color: var(--text); resize: vertical;
  }}
  .grid2 {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .grid2 > label {{ flex: 1 1 200px; }}
  .form button {{
    border: 0; background: var(--accent); color: #fff; border-radius: 8px;
    padding: 9px 18px; font: inherit; font-weight: 600; cursor: pointer;
  }}
  .grp {{ font-size: 14px; margin: 22px 0 8px; color: var(--sub);
          text-transform: uppercase; letter-spacing: .03em; }}
  .count {{ background: var(--border); color: var(--text); border-radius: 10px;
            padding: 1px 8px; font-size: 12px; margin-left: 4px;
            text-transform: none; letter-spacing: 0; }}
  .list {{ list-style: none; margin: 0; padding: 0; display: flex;
           flex-direction: column; gap: 8px; }}
  .row {{
    display: flex; gap: 12px; align-items: flex-start; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
  }}
  .step {{
    flex: 0 0 auto; min-width: 28px; height: 28px; border-radius: 8px;
    background: var(--accent); color: #fff; font-weight: 700; font-size: 13px;
    display: grid; place-items: center;
  }}
  .rbody {{ flex: 1; min-width: 0; }}
  .rtext {{ font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }}
  .qa .q {{ font-weight: 600; font-size: 14px; overflow-wrap: anywhere; }}
  .qa .a {{ font-size: 14px; margin-top: 2px; color: var(--text);
            overflow-wrap: anywhere; }}
  .rmeta {{ color: var(--sub); font-size: 12px; margin-top: 4px; }}
  .del button {{
    border: 1px solid var(--border); background: transparent; color: var(--err);
    border-radius: 8px; width: 30px; height: 30px; cursor: pointer;
    font-size: 14px; line-height: 1;
  }}
  .del button:hover {{ border-color: var(--err); }}
  .flash {{ padding: 9px 12px; border-radius: 8px; font-size: 13px;
            margin-bottom: 12px; }}
  .flash.ok {{ background: color-mix(in srgb, var(--ok) 15%, transparent);
               color: var(--ok); }}
  .flash.err {{ background: color-mix(in srgb, var(--err) 15%, transparent);
                color: var(--err); }}
  .empty {{ background: var(--card); border: 1px solid var(--border);
            border-radius: 12px; padding: 20px; color: var(--sub); }}
  .mono {{ font-size: 13px; }}
  .mono .lbl {{ color: var(--sub); font-size: 12px; margin-top: 8px; }}
  .qline {{
    font-family: ui-monospace, Consolas, monospace; font-size: 12px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 9px; margin-bottom: 6px; overflow-x: auto; white-space: nowrap;
  }}
  code {{ font-family: ui-monospace, Consolas, monospace; font-size: 12px;
          background: var(--bg); padding: 1px 5px; border-radius: 5px; }}
  .note {{ color: var(--sub); font-size: 12px; margin: 10px 0 0; }}
  .score {{ flex: 0 0 auto; width: 92px; text-align: right; }}
  .snum {{ font-size: 12px; color: var(--sub);
           font-family: ui-monospace, Consolas, monospace; }}
  .sbar {{ display: block; height: 5px; border-radius: 3px;
           background: var(--border); margin-top: 4px; overflow: hidden; }}
  .sbar i {{ display: block; height: 100%; border-radius: 3px; }}
  .check {{ display: flex; align-items: center; gap: 8px; font-size: 13px;
            color: var(--sub); margin-bottom: 12px; }}
  .check input {{ width: auto; margin: 0; }}
  .answer {{
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border-left: 3px solid var(--accent); border-radius: 8px;
    padding: 12px 14px; font-size: 14px; white-space: pre-wrap;
    overflow-wrap: anywhere;
  }}
  details {{ margin-top: 10px; font-size: 13px; color: var(--sub); }}
  summary {{ cursor: pointer; }}
  .prompt {{
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 10px; margin-top: 8px; font-size: 12px; white-space: pre-wrap;
    overflow-x: auto; font-family: ui-monospace, Consolas, monospace;
    color: var(--text);
  }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>Dữ liệu bot — {title}</h1>
    {nav}
    {flash}
    <p class="intro">{intro}</p>
    {form}
    {listing}
  </div>
</body>
</html>"""
