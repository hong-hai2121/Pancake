"""Dựng HTML cho webview hiển thị danh sách page (server-side render)."""

from datetime import datetime, timezone
from html import escape

# Bảng màu cho avatar chữ cái đầu (ổn định theo id).
_AVATAR_COLORS = [
    "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
    "#ca8a04", "#16a34a", "#0891b2", "#4f46e5", "#0d9488",
]


def _avatar(page: dict) -> str:
    name = page.get("name") or "?"
    initial = escape(name.strip()[:1].upper() or "?")
    idx = sum(ord(c) for c in page.get("id", "0")) % len(_AVATAR_COLORS)
    color = _AVATAR_COLORS[idx]
    return (
        f'<span class="avatar" style="background:{color}">{initial}</span>'
    )


def _page_card(page: dict) -> str:
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


def render_error(message: str) -> str:
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
