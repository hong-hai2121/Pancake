"""Màn đăng nhập (màn 1) — trang ĐỘC LẬP, không dùng render_shell.

Vì sao không dùng shell: người CHƯA đăng nhập không được thấy menu trái (tên
các màn cũng là thông tin nội bộ). Trang tự mang CSS riêng, lấy đúng bảng màu
tím–hồng của shell để nhìn cùng một app.

Thông báo trên màn này có 2 loại, khác nhau về màu để nhìn là biết:
- `error`  (dải đỏ / vàng) — đăng nhập hỏng: sai mật khẩu, khoá tạm, nghỉ việc.
  Câu chữ do app/services/auth_service.py quyết định, ở đây chỉ hiển thị.
- `notice` (dải xám-tím) — không phải lỗi của người dùng: vừa đăng xuất, hết
  phiên bị đá về đây.
"""

from html import escape

# Mã lỗi -> (biểu tượng, có phải cảnh báo "vàng" không). Sai mật khẩu là lỗi đỏ;
# khoá tạm / nghỉ việc là tình trạng tài khoản nên để vàng, gõ lại cũng vô ích.
_KIEU_LOI: dict[str, tuple[str, bool]] = {
    "UNAUTHORIZED": ("✕", False),
    "ACCOUNT_LOCKED": ("⏱", True),
    "ACCOUNT_DISABLED": ("🚫", True),
}

# Thông báo không phải lỗi, truyền qua query ?thongbao=
THONG_BAO: dict[str, str] = {
    "dang-xuat": "Bạn đã đăng xuất khỏi hệ thống.",
    "het-phien": "Phiên đăng nhập đã hết hạn — đăng nhập lại để tiếp tục.",
    "can-dang-nhap": "Bạn cần đăng nhập để xem trang này.",
    "doi-mat-khau": "Đã đổi mật khẩu — đăng nhập lại bằng mật khẩu mới.",
}

_CSS = """
:root{
  --bg:#f5eff6; --card:#fff; --text:#2b2230; --sub:#8a7f98; --border:#eee3f0;
  --accent:#6f5a9c; --hot:#e91e8c; --err:#e5484d; --err-bg:#fdecec;
  --warn:#a15c00; --warn-bg:#fff4e0; --note-bg:#f2edf8;
  --side:linear-gradient(185deg,#6f5a9c 0%,#8c6a9b 48%,#c4868f 100%);
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#15111a; --card:#1d1824; --text:#ece6f2; --sub:#9d92ab;
         --border:#2f2739; --err-bg:#3a2026; --warn:#e8b060; --warn-bg:#37280f;
         --note-bg:#251e2f; }
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
input[type=text],input[type=password]{width:100%;padding:10px 12px;
      border:1px solid var(--border);border-radius:10px;background:transparent;
      color:var(--text);font-size:15px}
input::placeholder{color:var(--sub);opacity:.7}
input:focus{outline:2px solid var(--accent);outline-offset:0;border-color:transparent}
.field{margin-bottom:16px}
/* Ô mật khẩu: `.pw` chỉ bọc RIÊNG ô nhập + nút, KHÔNG bọc label. Nếu bọc cả
   label thì mốc `top` của nút con mắt là đỉnh khối, tức ngang chữ "Mật khẩu"
   — con mắt trôi lên khỏi ô. Căn giữa bằng top:50% nên ô cao bao nhiêu cũng
   đúng, không phải đo tay theo padding. */
.pw{position:relative}
.pw input{padding-right:44px}
.eye{position:absolute;right:5px;top:50%;transform:translateY(-50%);
     width:34px;height:34px;padding:0;border-radius:8px;
     background:none;border:0;cursor:pointer;color:var(--sub);font-size:17px;
     line-height:1;display:flex;align-items:center;justify-content:center}
.eye:hover{color:var(--accent);filter:none;background:var(--note-bg)}
.eye:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.row{display:flex;align-items:center;gap:8px;margin-bottom:18px;font-size:13.5px;color:var(--sub)}
.row input{accent-color:var(--accent)}
button{width:100%;padding:11px;border:0;border-radius:10px;cursor:pointer;
      background:var(--accent);color:#fff;font-size:15px;font-weight:600}
button:hover{filter:brightness(1.08)}
/* dải thông báo: đỏ = sai, vàng = tình trạng tài khoản, xám-tím = tin thường */
.msg{display:flex;gap:8px;align-items:flex-start;border-radius:10px;
     padding:10px 12px;font-size:13.5px;margin-bottom:16px}
.msg .ico{flex:0 0 auto;line-height:1.4}
.err{background:var(--err-bg);color:var(--err)}
.warn{background:var(--warn-bg);color:var(--warn)}
.note{background:var(--note-bg);color:var(--sub)}
.caps{display:none;font-size:12.5px;color:var(--warn);margin:-10px 0 14px}
.caps.on{display:block}
.foot{padding:0 28px 24px;font-size:12.5px;color:var(--sub);text-align:center}
"""

# Con mắt bật/tắt xem mật khẩu + nhắc Caps Lock (nguyên nhân sai mật khẩu hay gặp
# nhất). Không có JS thì ô mật khẩu vẫn dùng bình thường, chỉ mất 2 tiện ích này.
_JS = """
(function(){
  var p=document.getElementById('p'), e=document.getElementById('eye'),
      c=document.getElementById('caps');
  e.hidden=false;
  e.addEventListener('click',function(){
    var hien = p.type==='password';
    p.type = hien ? 'text' : 'password';
    e.textContent = hien ? '🙈' : '👁';
    e.setAttribute('aria-pressed', hien ? 'true' : 'false');
    e.setAttribute('aria-label', hien ? 'Ẩn mật khẩu' : 'Hiện mật khẩu');
    p.focus();
  });
  function caps(ev){
    if(ev.getModifierState) c.classList.toggle('on', ev.getModifierState('CapsLock'));
  }
  p.addEventListener('keyup',caps); p.addEventListener('focus',caps);
  p.addEventListener('blur',function(){c.classList.remove('on');});
})();
"""


def _dai_thong_bao(error: str, code: str, notice: str) -> str:
    """Dựng dải thông báo phía trên form (lỗi ưu tiên hơn tin thường)."""
    if error:
        ico, vang = _KIEU_LOI.get(code, ("✕", False))
        lop = "warn" if vang else "err"
        return (
            f'<div class="msg {lop}" role="alert" aria-live="assertive">'
            f'<span class="ico" aria-hidden="true">{ico}</span>'
            f"<span>{escape(error)}</span></div>"
        )
    if notice:
        return (
            '<div class="msg note" role="status">'
            '<span class="ico" aria-hidden="true">ℹ</span>'
            f"<span>{escape(notice)}</span></div>"
        )
    return ""


def render_login(
    error: str = "",
    next_url: str = "",
    username: str = "",
    code: str = "",
    notice: str = "",
) -> str:
    """Form đăng nhập.

    `error` + `code` -> dải đỏ/vàng kèm lý do (xem `_KIEU_LOI`);
    `notice` -> dải xám-tím (vừa đăng xuất, hết phiên...);
    `username` giữ lại giá trị đã gõ để khỏi nhập lại.
    """
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Đăng nhập — FB Sales Bot</title>"
        f"<style>{_CSS}</style></head><body>"
        '<div class="card">'
        '<div class="head"><span class="logo">FB</span>'
        "<h1>Đăng nhập</h1><p>Sales Bot · CRM nội bộ</p></div>"
        '<form method="post" action="/dang-nhap" autocomplete="on">'
        + _dai_thong_bao(error, code, notice)
        + f'<input type="hidden" name="next" value="{escape(next_url)}">'
        '<div class="field">'
        '<label for="u">Tài khoản (username hoặc email)</label>'
        f'<input id="u" type="text" name="username" value="{escape(username)}" '
        'placeholder="vd: sale01 hoặc sale01@congty.com" '
        'autofocus autocomplete="username" required></div>'
        '<div class="field">'
        '<label for="p">Mật khẩu</label>'
        '<div class="pw">'
        '<input id="p" type="password" name="password" placeholder="Nhập mật khẩu" '
        'autocomplete="current-password" required>'
        '<button type="button" id="eye" class="eye" hidden '
        'aria-label="Hiện mật khẩu" aria-pressed="false" '
        'aria-controls="p" title="Hiện/ẩn mật khẩu">👁</button></div></div>'
        '<div class="caps" id="caps">⚠ Đang bật Caps Lock — mật khẩu phân biệt '
        "chữ hoa/thường.</div>"
        '<div class="row"><input id="r" type="checkbox" name="remember" value="1" checked>'
        '<label for="r" style="margin:0">Ghi nhớ đăng nhập (14 ngày)</label></div>'
        "<button>Đăng nhập</button>"
        "</form>"
        '<div class="foot">Quên mật khẩu? Liên hệ Admin để được cấp lại.</div>'
        f"</div><script>{_JS}</script></body></html>"
    )
