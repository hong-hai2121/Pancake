"""Màn đăng nhập (màn 1) — trang ĐỘC LẬP, không dùng render_shell.

Vì sao không dùng shell: người CHƯA đăng nhập không được thấy menu trái (tên
các màn cũng là thông tin nội bộ). Trang tự mang CSS riêng, lấy đúng bảng màu
tím–hồng của shell để nhìn cùng một app.
"""

from html import escape

_CSS = """
:root{
  --bg:#f5eff6; --card:#fff; --text:#2b2230; --sub:#8a7f98; --border:#eee3f0;
  --accent:#6f5a9c; --hot:#e91e8c; --err:#e5484d; --err-bg:#fdecec;
  --side:linear-gradient(185deg,#6f5a9c 0%,#8c6a9b 48%,#c4868f 100%);
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#15111a; --card:#1d1824; --text:#ece6f2; --sub:#9d92ab;
         --border:#2f2739; --err-bg:#3a2026; }
}
*{box-sizing:border-box;margin:0}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;
     background:var(--bg);color:var(--text);
     font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
.card{width:min(400px,92vw);background:var(--card);border:1px solid var(--border);
      border-radius:16px;box-shadow:0 8px 30px rgba(111,90,156,.15);overflow:hidden}
.head{background:var(--side);color:#fff;padding:26px 28px 22px}
.head .logo{display:inline-flex;width:40px;height:40px;border-radius:11px;
      background:rgba(255,255,255,.18);align-items:center;justify-content:center;
      font-weight:800;margin-bottom:10px}
.head h1{font-size:19px;font-weight:700}
.head p{opacity:.85;font-size:13px;margin-top:2px}
form{padding:26px 28px 28px}
label{display:block;font-size:13px;color:var(--sub);margin:0 0 6px}
input[type=text],input[type=password]{width:100%;padding:10px 12px;margin-bottom:16px;
      border:1px solid var(--border);border-radius:10px;background:transparent;
      color:var(--text);font-size:15px}
input:focus{outline:2px solid var(--accent);outline-offset:0;border-color:transparent}
.row{display:flex;align-items:center;gap:8px;margin-bottom:18px;font-size:13.5px;color:var(--sub)}
.row input{accent-color:var(--accent)}
button{width:100%;padding:11px;border:0;border-radius:10px;cursor:pointer;
      background:var(--accent);color:#fff;font-size:15px;font-weight:600}
button:hover{filter:brightness(1.08)}
.err{background:var(--err-bg);color:var(--err);border-radius:10px;
     padding:10px 12px;font-size:13.5px;margin-bottom:16px}
.foot{padding:0 28px 24px;font-size:12.5px;color:var(--sub);text-align:center}
"""


def render_login(error: str = "", next_url: str = "", username: str = "") -> str:
    """Form đăng nhập. `error` hiện dải đỏ; `username` giữ lại giá trị đã gõ."""
    err_html = f'<div class="err">{escape(error)}</div>' if error else ""
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Đăng nhập — FB Sales Bot</title>"
        f"<style>{_CSS}</style></head><body>"
        '<div class="card">'
        '<div class="head"><span class="logo">FB</span>'
        "<h1>Đăng nhập</h1><p>Sales Bot · CRM nội bộ</p></div>"
        '<form method="post" action="/dang-nhap" autocomplete="on">'
        + err_html
        + f'<input type="hidden" name="next" value="{escape(next_url)}">'
        '<label for="u">Tài khoản (username hoặc email)</label>'
        f'<input id="u" type="text" name="username" value="{escape(username)}" '
        'autofocus autocomplete="username" required>'
        '<label for="p">Mật khẩu</label>'
        '<input id="p" type="password" name="password" autocomplete="current-password" required>'
        '<div class="row"><input id="r" type="checkbox" name="remember" value="1" checked>'
        '<label for="r" style="margin:0">Ghi nhớ đăng nhập (14 ngày)</label></div>'
        "<button>Đăng nhập</button>"
        "</form>"
        '<div class="foot">Quên mật khẩu? Liên hệ Admin để được cấp lại.</div>'
        "</div></body></html>"
    )
