"""Người dùng của request hiện tại, đặt vào contextvar (A2).

Vì sao cần: `render_shell` (app/web/shell.py) muốn hiện tên người đăng nhập +
nút đăng xuất, nhưng 37 route hiện có không truyền `request` xuống view. Thay vì
sửa chữ ký của tất cả, middleware trong app/main.py đặt payload token vào đây,
ai cần thì đọc. Contextvar an toàn theo từng request (asyncio task/thread).
"""

from contextvars import ContextVar

# Payload access token của người đang đăng nhập, hoặc None (route miễn đăng nhập).
current_user: ContextVar[dict | None] = ContextVar("current_user", default=None)
