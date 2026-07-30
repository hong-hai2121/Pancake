"""GUI desktop cho Pancake Watcher local server — bật/tắt server + chỉnh cấu
hình (.env) mà không cần mở terminal hay sửa file tay.

Chạy: python gui.py (hoặc double-click "Pancake Watcher.lnk" trên Desktop nếu
đã tạo shortcut — xem README.md). Dùng tkinter (có sẵn trong Python, không
cần cài thêm gì).
"""

import json
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.request import urlopen

import db
import sentiment

SERVER_DIR = Path(__file__).parent
# Cài đặt riêng của ZPancake (cách quét, key OpenAI, hiện log) vẫn ở .env này.
ENV_PATH = SERVER_DIR / ".env"
# RIÊNG token Telegram để ở .env GỐC của dự án — dùng chung cho cả app chính
# (app/workers/sentiment.py) lẫn ZPancake, khỏi phải điền 2 nơi.
ROOT_ENV_PATH = SERVER_DIR.parents[1] / ".env"
TELEGRAM_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
PID_PATH = SERVER_DIR / "server.pid"  # để tắt được server kể cả khi đóng rồi mở lại GUI
ICON_PATH = SERVER_DIR / "icon.ico"  # icon cửa sổ + taskbar, cũng dùng cho shortcut Desktop
LOG_PATH = SERVER_DIR / "server.log"  # log của main.py (uvicorn) khi bật qua GUI, xem mục start_server()
HEALTH_URL = "http://127.0.0.1:8787/health"
HISTORY_URL = "http://127.0.0.1:8787/history"
SCAN_EVENTS_CURSOR_URL = "http://127.0.0.1:8787/api/scan-events/cursor"
SCAN_EVENTS_URL = "http://127.0.0.1:8787/api/scan-events"

# Bảng màu đồng bộ với popup/panel của extension (cùng tông indigo #4338ca).
COLOR_BG = "#f3f4f6"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#e2e5eb"
COLOR_PRIMARY = "#4338ca"
COLOR_PRIMARY_HOVER = "#3730a3"
COLOR_TEXT = "#1f2937"
COLOR_MUTED = "#6b7280"
COLOR_SUCCESS = "#16a34a"
COLOR_SUCCESS_HOVER = "#15803d"
COLOR_DANGER = "#ef4444"
COLOR_DANGER_SOFT = "#fee2e2"
COLOR_WARNING = "#d97706"   # server sống nhưng chưa nối được Postgres
COLOR_LOG_BG = "#111827"
COLOR_LOG_TEXT = "#d1d5db"


def _doc_env(path: Path, values: dict) -> None:
    """Đọc `path` rồi điền vào `values` những khoá đã khai báo sẵn (bỏ dòng #)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in values:
            values[key] = val.strip()


def read_env() -> dict:
    values = {
        "SENTIMENT_METHOD": "keyword",
        "OPENAI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "SHOW_SCAN_LOG": "1",  # bật/tắt hiện log quét tin nhắn trong khung Nhật ký (xem _poll_scan_events)
    }
    # .env GỐC trước (nguồn của token Telegram), .env riêng sau nên vẫn ghi đè
    # được — ai muốn ZPancake bắn sang kênh Telegram khác app chính thì cứ khai
    # lại trong ZPancake/server/.env.
    _doc_env(ROOT_ENV_PATH, values)
    _doc_env(ENV_PATH, values)
    return values


def _center_window(win: tk.Misc, width: int, height: int) -> None:
    """Đặt vị trí cửa sổ ở giữa màn hình theo kích thước width x height cho
    trước — winfo_screenwidth/height lấy đúng độ phân giải màn hình hiện tại
    (kể cả khi có nhiều màn hình, lấy màn hình chứa cửa sổ)."""
    win.update_idletasks()
    x = (win.winfo_screenwidth() - width) // 2
    y = (win.winfo_screenheight() - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")


def write_env(values: dict) -> None:
    """Lưu cài đặt: phần riêng của ZPancake vào .env của nó, Telegram vào .env gốc.

    Token Telegram KHÔNG còn được ghi vào file này nữa — nó nằm ở .env gốc để app
    chính dùng chung; nếu vẫn ghi ở cả 2 nơi thì file nào sửa sau sẽ âm thầm đè
    file kia (ZPancake nạp .env riêng SAU .env gốc).
    """
    lines = [
        "# File này do gui.py tự ghi khi bấm \"Lưu cài đặt\" — có thể chỉnh tay",
        "# nhưng lần sau lưu qua GUI sẽ ghi đè lại theo đúng các dòng dưới.",
        "# Token Telegram nằm ở .env GỐC của dự án, không phải ở đây.",
        f"SENTIMENT_METHOD={values['SENTIMENT_METHOD']}",
        f"OPENAI_API_KEY={values['OPENAI_API_KEY']}",
        f"SHOW_SCAN_LOG={values['SHOW_SCAN_LOG']}",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_telegram_env(values: dict) -> None:
    """Vá TELEGRAM_* vào .env GỐC, GIỮ NGUYÊN mọi dòng khác của file.

    Bắt buộc phải vá tại chỗ chứ không ghi đè cả file như `write_env`: .env gốc
    còn chứa PANCAKE_ACCESS_TOKEN, DATABASE_URL, SUPABASE_*, OPENAI_API_KEY...
    của app chính — ghi đè là mất sạch.
    """
    lines = (
        ROOT_ENV_PATH.read_text(encoding="utf-8").splitlines()
        if ROOT_ENV_PATH.exists() else []
    )
    con_lai = {k: values.get(k, "") for k in TELEGRAM_KEYS}
    for i, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in con_lai:
            lines[i] = f"{key}={con_lai.pop(key)}"
    if con_lai:                                   # chưa có dòng nào -> thêm mới
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Báo Telegram khi phát hiện hội thoại tiêu cực (dùng chung"
                     " cho app chính + ZPancake)")
        lines += [f"{k}={v}" for k, v in con_lai.items()]
    ROOT_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ServerControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🐼 Pancake Watcher — Server Control")
        self.root.configure(bg=COLOR_BG)
        if ICON_PATH.exists():
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass  # icon lỗi định dạng hoặc hệ điều hành không hỗ trợ .ico -> bỏ qua, không crash GUI

        self.process: subprocess.Popen | None = None  # tiến trình do CHÍNH gui này bật
        # Lỗi DB đã ghi ra khung Nhật ký gần nhất — chỉ ghi lại khi ĐỔI nội dung,
        # để đèn vàng poll 2s/lần không spam cùng một dòng lỗi mãi.
        self._last_db_error = ""
        # Con trỏ (seq) đã hiện tới trong /api/scan-events — dùng để chỉ lấy sự
        # kiện MỚI mỗi lần poll (xem _poll_scan_events). Lấy seq hiện tại của
        # server ngay khi mở GUI (nếu server đang chạy) để không dội nguyên
        # buffer cũ vào khung Nhật ký; nếu server chưa chạy thì cứ để 0, sẽ tự
        # đồng bộ lại ở lần poll đầu tiên sau khi server bật (xem _poll_scan_events).
        self._scan_event_cursor = self._fetch_scan_event_cursor()

        self._build_style()
        self._build_ui()

        # Đặt kích thước cửa sổ theo đúng kích thước nội dung thực tế (nút,
        # nhãn...) sau khi dựng UI — thay vì số cố định — để không bị cắt chữ
        # khi nội dung thay đổi (vd. 2 nút chung 1 hàng cần rộng hơn trước).
        self.root.update_idletasks()
        width = max(self.root.winfo_reqwidth(), 820)
        height = max(self.root.winfo_reqheight(), 520)
        _center_window(self.root, width, height)
        self.root.minsize(width, height)

        self._poll_status()
        self._poll_scan_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- style

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        # "clam" là theme ttk duy nhất trên Windows tôn trọng màu nền/viền tuỳ
        # chỉnh qua style.configure() — theme mặc định ("vista") bỏ qua phần
        # lớn các option màu, giao diện sẽ không đổi được gì.
        style.theme_use("clam")

        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        style.configure(
            "CardTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Segoe UI", 10, "bold")
        )
        style.configure("Muted.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=("Segoe UI", 9))
        style.configure(
            "Card.TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Segoe UI", 9)
        )
        style.map("Card.TCheckbutton", background=[("active", COLOR_CARD)])
        style.configure("MutedMain.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", background=COLOR_CARD, font=("Segoe UI", 11, "bold"))

        style.configure(
            "TButton",
            font=("Segoe UI", 9),
            padding=(10, 8),
            background=COLOR_CARD,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            focuscolor=COLOR_CARD,
        )
        style.map("TButton", background=[("active", "#f3f4f6")])

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 9),
            background=COLOR_PRIMARY,
            foreground="#ffffff",
            bordercolor=COLOR_PRIMARY,
            focuscolor=COLOR_PRIMARY,
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLOR_PRIMARY_HOVER)],
        )

        style.configure(
            "Success.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 8),
            background=COLOR_SUCCESS,
            foreground="#ffffff",
            bordercolor=COLOR_SUCCESS,
        )
        style.map("Success.TButton", background=[("active", COLOR_SUCCESS_HOVER)])

        style.configure(
            "Danger.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 8),
            background=COLOR_CARD,
            foreground=COLOR_DANGER,
            bordercolor=COLOR_DANGER,
        )
        style.map("Danger.TButton", background=[("active", COLOR_DANGER_SOFT)])

        style.configure("TCombobox", padding=6, fieldbackground="#ffffff", arrowsize=12)
        style.configure("TEntry", padding=6, fieldbackground="#ffffff")

    # --------------------------------------------------------------- UI

    def _card(self, parent: tk.Widget) -> tuple[tk.Frame, ttk.Frame]:
        # 1px viền quanh card: frame ngoài tô màu viền, frame trong (nội dung
        # thật) chừa đúng 1px mỗi cạnh để lộ màu viền ra — giả lập border mà
        # ttk.Frame không hỗ trợ trực tiếp kiểu này.
        outer = tk.Frame(parent, bg=COLOR_BORDER)
        inner = ttk.Frame(outer, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return outer, inner

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(20, 18, 20, 10))
        header.pack(fill="x")
        ttk.Label(header, text="🐼 Pancake Watcher", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Quản lý server local — 127.0.0.1:8787", style="MutedMain.TLabel").pack(
            anchor="w", pady=(2, 0)
        )

        body = ttk.Frame(self.root, padding=(20, 0, 20, 18))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left_col = ttk.Frame(body, style="TFrame")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_col = ttk.Frame(body, style="TFrame")
        right_col.grid(row=0, column=1, sticky="nsew")

        # ---------------------------------------------------- card trạng thái
        status_outer, status_card = self._card(left_col)
        status_outer.pack(fill="x", pady=(0, 12))

        status_row = ttk.Frame(status_card, style="Card.TFrame", padding=(14, 14, 14, 10))
        status_row.pack(fill="x")
        self.status_dot = tk.Canvas(status_row, width=16, height=16, bg=COLOR_CARD, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_circle = self.status_dot.create_oval(2, 2, 14, 14, fill="#9ca3af", outline="")

        status_text_col = ttk.Frame(status_row, style="Card.TFrame")
        status_text_col.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.status_label = ttk.Label(status_text_col, text="Đang kiểm tra...", style="Status.TLabel")
        self.status_label.pack(anchor="w")
        ttk.Label(status_text_col, text="Tự kiểm tra /health mỗi 2 giây", style="Muted.TLabel").pack(anchor="w")

        btn_row = ttk.Frame(status_card, style="Card.TFrame", padding=(14, 0, 14, 10))
        btn_row.pack(fill="x")
        self.start_btn = ttk.Button(btn_row, text="▶  Bật server", style="Success.TButton", command=self.start_server)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.stop_btn = ttk.Button(btn_row, text="■  Tắt server", style="Danger.TButton", command=self.stop_server)
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        history_row = ttk.Frame(status_card, style="Card.TFrame", padding=(14, 0, 14, 6))
        history_row.pack(fill="x")
        ttk.Button(
            history_row, text="📜  Xem lịch sử hội thoại", command=self.open_history
        ).pack(fill="x")

        log_row = ttk.Frame(status_card, style="Card.TFrame", padding=(14, 0, 14, 14))
        log_row.pack(fill="x")
        ttk.Button(
            log_row, text="📄  Xem log server (server.log)", command=self.open_server_log
        ).pack(fill="x")

        # ----------------------------------------------------- card cài đặt
        settings_outer, settings_card = self._card(left_col)
        settings_outer.pack(fill="x", pady=(0, 12))

        settings_pad = ttk.Frame(settings_card, style="Card.TFrame", padding=14)
        settings_pad.pack(fill="x")
        settings_pad.columnconfigure(1, weight=1)

        ttk.Label(settings_pad, text="Cài đặt (.env)", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(settings_pad, text="Cách quét cảm xúc", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=6
        )
        self.method_var = tk.StringVar()
        method_combo = ttk.Combobox(
            settings_pad, textvariable=self.method_var, values=["keyword", "llm"], state="readonly", width=14
        )
        method_combo.grid(row=1, column=1, sticky="e", pady=6)

        values = read_env()
        self.method_var.set(values["SENTIMENT_METHOD"])
        # OpenAI API Key KHÔNG hiện/sửa trên GUI (đọc thẳng từ .env lúc chạy) —
        # tránh lộ key lên màn hình; muốn đổi thì sửa trực tiếp file .env.

        # Bật/tắt hiện log quét tin nhắn ở khung Nhật ký (xem _poll_scan_events)
        # — có hiệu lực NGAY khi tick/bỏ tick (vòng poll tự đọc biến này mỗi
        # lượt), không cần bấm "Lưu cài đặt"; bấm Lưu chỉ để nhớ lựa chọn cho
        # lần mở GUI sau.
        self.show_scan_log_var = tk.BooleanVar(value=values["SHOW_SCAN_LOG"] != "0")
        ttk.Checkbutton(
            settings_pad,
            text="Hiện log quét tin nhắn trong Nhật ký",
            variable=self.show_scan_log_var,
            style="Card.TCheckbutton",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 6))

        actions_row = ttk.Frame(settings_pad, style="Card.TFrame")
        actions_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions_row.columnconfigure(0, weight=1)
        actions_row.columnconfigure(1, weight=1)

        ttk.Button(
            actions_row,
            text="🏷️  Quản lý từ khoá tiêu cực...",
            command=self.open_keywords_dialog,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ttk.Button(
            actions_row,
            text="🔔  Kiểm tra kết nối Telegram...",
            command=self.test_telegram,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        ttk.Button(settings_pad, text="💾  Lưu cài đặt", style="Primary.TButton", command=self.save_settings).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 6)
        )
        ttk.Label(
            settings_pad,
            text="Lưu khi server đang chạy sẽ tự khởi động lại để áp dụng cài đặt mới.",
            style="Muted.TLabel",
            wraplength=320,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        # --------------------------------------------------------- nhật ký
        ttk.Label(right_col, text="Nhật ký", style="MutedMain.TLabel").pack(anchor="w", pady=(0, 4))
        log_outer, log_card = self._card(right_col)
        log_outer.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_card,
            height=6,
            state="disabled",
            font=("Consolas", 9),
            bg=COLOR_LOG_BG,
            fg=COLOR_LOG_TEXT,
            insertbackground=COLOR_LOG_TEXT,
            relief="flat",
            padx=10,
            pady=8,
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)

    def log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------ logic

    def fetch_health(self) -> dict | None:
        """Gọi /health -> dict, hoặc None nếu server không phản hồi (đã tắt).

        Server trả 200 kể cả khi Postgres chưa bật; trạng thái DB nằm ở khoá
        `db` ("ok" | "down") để đèn phân biệt được 3 tình huống.
        """
        try:
            with urlopen(HEALTH_URL, timeout=0.6) as resp:
                if resp.status != 200:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, OSError, TimeoutError, ValueError):
            return None

    def is_healthy(self) -> bool:
        """Server có sống không (KHÔNG quan tâm DB) — dùng cho bật/tắt/chờ khởi động."""
        return self.fetch_health() is not None

    def start_server(self) -> None:
        if self.is_healthy():
            messagebox.showinfo("Pancake Watcher", "Server đã đang chạy rồi.")
            return
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # QUAN TRỌNG: GUI chạy qua pythonw.exe (không có console) -> nếu không
        # redirect, sys.stdout/sys.stderr của tiến trình con (main.py) là None,
        # và dòng print()/log đầu tiên của uvicorn sẽ ném AttributeError rồi
        # chết ngay lập tức — không có console nào để hiện lỗi đó, nên GUI chỉ
        # thấy PID xuất hiện rồi biến mất, đèn trạng thái không bao giờ chuyển
        # xanh, mà không rõ vì sao. Ghi thẳng ra server.log để: (1) tránh crash,
        # (2) có chỗ xem lại khi cần debug.
        log_file = open(LOG_PATH, "w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(SERVER_DIR),
            creationflags=creationflags,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        log_file.close()  # tiến trình con đã nhận bản sao handle riêng, đóng ở đây an toàn
        PID_PATH.write_text(str(self.process.pid), encoding="utf-8")
        # Server mới -> bộ đếm seq của /api/scan-events bắt đầu lại từ 1, nên
        # con trỏ cũ (có thể lớn hơn nhiều) phải reset về 0, nếu không sự kiện
        # mới sẽ bị coi là "cũ hơn con trỏ" và không hiện lên khung Nhật ký.
        self._scan_event_cursor = 0
        self.log(f"Đã bật server (PID {self.process.pid}). Log: {LOG_PATH.name}")
        # Kiểm tra lại sau 1.5s: is_healthy() lúc đầu có thể báo "chưa chạy" nhầm
        # (vd máy đang lag, hoặc tiến trình cũ chưa kịp nhả cổng) khiến ta bật
        # thêm 1 tiến trình mới ngay khi cổng 8787 vẫn còn bị chiếm — tiến trình
        # mới đó sẽ tự thoát gần như ngay lập tức. Không kiểm tra thì PID_PATH cứ
        # trỏ vào 1 PID đã chết, và người dùng tưởng server đang chạy trong khi
        # thực ra không có gì lắng nghe cổng 8787 (hoặc tệ hơn, tiến trình CŨ vẫn
        # sống nhưng ta đã mất dấu PID của nó).
        self.root.after(1500, self._verify_started, self.process)

    def _verify_started(self, process: subprocess.Popen) -> None:
        if process is not self.process:
            return  # đã bấm Tắt/Bật lại trong lúc chờ -> bỏ qua lần kiểm tra cũ này
        if process.poll() is None:
            return  # vẫn đang chạy bình thường
        tail = ""
        try:
            tail = LOG_PATH.read_text(encoding="utf-8", errors="ignore")[-800:]
        except OSError:
            pass
        self.log(f"Server thoát ngay sau khi bật (exit code {process.returncode}) — xem server.log.")
        self.process = None
        if PID_PATH.exists():
            PID_PATH.unlink()
        messagebox.showerror(
            "Pancake Watcher",
            "Server vừa bật đã tự thoát ngay — thường do cổng 8787 vẫn đang bị 1 "
            "tiến trình khác chiếm (chưa tắt hẳn) hoặc lỗi khi khởi động.\n\n"
            + (f"Log gần nhất:\n{tail}" if tail else "Xem server.log để biết chi tiết."),
        )

    def stop_server(self) -> None:
        pid = None
        if self.process is not None and self.process.poll() is None:
            pid = self.process.pid
        elif PID_PATH.exists():
            # Cửa sổ này có thể đã bị đóng/mở lại sau khi bật server — không còn
            # giữ handle tiến trình trong bộ nhớ nữa, nên đọc lại PID đã lưu.
            try:
                pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pid = None

        if pid is None:
            if self.is_healthy():
                messagebox.showwarning(
                    "Pancake Watcher",
                    "Server đang chạy nhưng không tìm được PID để tắt (có thể đã chạy "
                    "tay bằng terminal khác) — hãy tắt ở đúng nơi đã bật.",
                )
            else:
                messagebox.showinfo("Pancake Watcher", "Server hiện không chạy.")
            return

        killed = False
        try:
            # /T = tắt cả cây tiến trình con — uvicorn chạy reload=True sẽ đẻ ra 1
            # tiến trình worker con, chỉ tắt tiến trình cha sẽ để sót con chạy mồ côi.
            result = subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                killed = True
                self.log(f"Đã tắt server (PID {pid}).")
            else:
                # Không throw exception khi PID không tồn tại/không đủ quyền — chỉ
                # trả returncode khác 0 — nên PHẢI tự kiểm tra, nếu không sẽ báo
                # "Đã tắt" trong khi tiến trình (và cổng 8787) vẫn còn sống.
                stderr = (result.stderr or b"").decode(errors="ignore").strip()
                self.log(f"taskkill PID {pid} thất bại (mã {result.returncode}): {stderr or 'không rõ lỗi'}")
        except Exception as err:  # noqa: BLE001 - báo lỗi cho người dùng thấy, không crash GUI
            self.log(f"Không tắt được server (PID {pid}): {err}")

        self.process = None
        if PID_PATH.exists():
            PID_PATH.unlink()

        if not killed and self.is_healthy():
            messagebox.showwarning(
                "Pancake Watcher",
                f"Không tắt được server (PID {pid}) — tiến trình có thể vẫn đang chạy và "
                "giữ cổng 8787. Kiểm tra Task Manager và tắt tay tiến trình python.exe "
                "tương ứng nếu cần.",
            )

    def open_keywords_dialog(self) -> None:
        KeywordsDialog(self.root, log=self.log)

    def test_telegram(self) -> None:
        values = read_env()
        token = values["TELEGRAM_BOT_TOKEN"].strip()
        chat_id = values["TELEGRAM_CHAT_ID"].strip()
        if not token or not chat_id:
            messagebox.showwarning(
                "Pancake Watcher",
                "Chưa cấu hình TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID.\n\n"
                f"Điền 2 dòng đó vào .env GỐC của dự án:\n{ROOT_ENV_PATH}\n\n"
                "Hướng dẫn lấy token/chat id có trong .env.example cùng thư mục đó.",
            )
            return

        import json
        from urllib.request import Request

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps(
            {"chat_id": chat_id, "text": "🐼 Pancake Watcher: tin nhắn thử — kết nối Telegram thành công!"}
        ).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    raise URLError(f"HTTP {resp.status}")
        except Exception as err:  # noqa: BLE001 - báo lỗi cho người dùng thấy, không crash GUI
            self.log(f"Gửi tin nhắn thử Telegram thất bại: {err}")
            messagebox.showerror(
                "Pancake Watcher",
                f"Gửi thất bại: {err}\n\nKiểm tra lại TELEGRAM_BOT_TOKEN/"
                f"TELEGRAM_CHAT_ID trong .env gốc:\n{ROOT_ENV_PATH}",
            )
            return

        self.log("Đã gửi tin nhắn thử tới Telegram thành công.")
        messagebox.showinfo("Pancake Watcher", "Đã gửi tin nhắn thử — kiểm tra Telegram xem đã nhận được chưa.")

    def open_history(self) -> None:
        if not self.is_healthy():
            messagebox.showwarning("Pancake Watcher", "Bật server trước khi xem lịch sử.")
            return
        webbrowser.open(HISTORY_URL)

    def open_server_log(self) -> None:
        if not LOG_PATH.exists():
            messagebox.showinfo(
                "Pancake Watcher", "Chưa có server.log — bấm \"Bật server\" ít nhất 1 lần trước."
            )
            return
        os.startfile(str(LOG_PATH))  # mở bằng app mặc định của Windows cho .log (thường là Notepad)

    def save_settings(self) -> None:
        # Giữ nguyên OPENAI_API_KEY đang có trong .env — GUI không có ô để sửa
        # giá trị này (xem ghi chú ở _build_ui), chỉ đổi SENTIMENT_METHOD.
        # TELEGRAM_* nằm ở .env GỐC nên KHÔNG ghi vào file này nữa.
        current = read_env()
        values = {
            "SENTIMENT_METHOD": self.method_var.get() or "keyword",
            "OPENAI_API_KEY": current["OPENAI_API_KEY"],
            "SHOW_SCAN_LOG": "1" if self.show_scan_log_var.get() else "0",
        }
        write_env(values)
        self.log(f"Đã lưu cài đặt vào .env (SENTIMENT_METHOD={values['SENTIMENT_METHOD']}).")
        if self.process is not None and self.process.poll() is None:
            self.log("Server đang chạy → tự khởi động lại để áp dụng...")
            self.stop_server()
            self.root.after(800, self.start_server)

    def _poll_status(self) -> None:
        health = self.fetch_health()
        if health is None:
            self.status_dot.itemconfig(self.status_circle, fill=COLOR_DANGER)
            self.status_label.configure(text="🔴 Đã dừng", foreground=COLOR_DANGER)
        elif health.get("db") == "ok":
            self.status_dot.itemconfig(self.status_circle, fill=COLOR_SUCCESS)
            self.status_label.configure(text="🟢 Đang chạy", foreground=COLOR_SUCCESS)
        else:
            # Server sống nhưng Postgres (Docker) chưa lên: tin nhắn extension gửi
            # sang sẽ bị từ chối (503) cho tới khi bật DB, nên phải nói rõ ra đây
            # thay vì để đèn xanh như không có chuyện gì.
            self.status_dot.itemconfig(self.status_circle, fill=COLOR_WARNING)
            self.status_label.configure(
                text="🟡 Chạy nhưng CHƯA nối được Postgres — chạy `docker compose up -d`",
                foreground=COLOR_WARNING,
            )
            err = (health.get("dbError") or "").strip()
            if err and err != self._last_db_error:
                self._last_db_error = err
                self.log(f"⚠️ DB: {err}")
        if health is not None and health.get("db") == "ok":
            self._last_db_error = ""
        self.root.after(2000, self._poll_status)

    def _fetch_scan_event_cursor(self) -> int:
        """Lấy seq mới nhất hiện có ở server (nếu server đang chạy) để dùng làm
        điểm bắt đầu poll — tránh dội nguyên buffer SCAN_EVENTS cũ (tối đa 200
        sự kiện tích luỹ từ lúc server bật) vào khung Nhật ký ngay khi vừa mở
        GUI/bật tính năng. Server chưa chạy hoặc lỗi mạng -> cứ trả 0, lần poll
        đầu tiên sau khi server sẵn sàng sẽ tự đồng bộ lại từ đó."""
        try:
            with urlopen(SCAN_EVENTS_CURSOR_URL, timeout=0.6) as resp:
                return json.loads(resp.read())["latestSeq"]
        except (URLError, OSError, TimeoutError, ValueError, KeyError):
            return 0

    def _poll_scan_events(self) -> None:
        # Tắt qua checkbox "Hiện log quét tin nhắn" -> khỏi gọi mạng luôn, đỡ
        # tốn round-trip vô ích khi người dùng không muốn xem mục này.
        if self.show_scan_log_var.get():
            try:
                url = f"{SCAN_EVENTS_URL}?after={self._scan_event_cursor}"
                with urlopen(url, timeout=0.6) as resp:
                    data = json.loads(resp.read())
                for ev in data.get("items", []):
                    who = ev.get("name") or ev.get("rawId") or "?"
                    snippet = ev.get("snippet") or ""
                    if ev.get("sentiment") == "negative":
                        self.log(f'⚠️ [{who}] TIÊU CỰC: "{snippet}"')
                    else:
                        self.log(f'📩 [{who}] Đã nhận & quét ({ev.get("sentiment")}): "{snippet}"')
                self._scan_event_cursor = data.get("latestSeq", self._scan_event_cursor)
            except (URLError, OSError, TimeoutError, ValueError, KeyError):
                pass  # server chưa chạy/chưa sẵn sàng -> im lặng bỏ qua, thử lại ở lượt poll sau
        self.root.after(2000, self._poll_scan_events)

    def _on_close(self) -> None:
        # Đóng cửa sổ KHÔNG tự tắt server — để server tiếp tục chạy nền bình
        # thường (giống việc chỉ đóng terminal điều khiển, không phải chủ ý
        # tắt server). Muốn tắt hẳn thì bấm "■ Tắt server" trước khi đóng.
        self.root.destroy()


class KeywordsDialog(tk.Toplevel):
    """Cửa sổ phụ quản lý danh sách từ khoá tiêu cực (sentiment.py, cách quét
    "keyword") — tách khỏi cửa sổ chính để cửa sổ chính gọn/vuông, chỉ mở khi
    cần. Đọc/ghi thẳng vào keywords.json qua sentiment.get_keywords()/
    set_keywords() — sentiment.py đọc lại file này mỗi lần quét nên sửa ở
    đây có tác dụng ngay sau khi bấm "Lưu", không cần khởi động lại server.

    Từ khoá hiển thị trong 1 ô văn bản, cách nhau bởi dấu phẩy — có thể gõ
    thêm/sửa/xoá trực tiếp như văn bản thường (Ctrl+Z để hoàn tác), HOẶC bấm
    vào 1 từ khoá để chọn (tự hiện vào ô nhập bên dưới, tô nổi bật) rồi dùng
    nút Thêm/Sửa/Xoá. Bấm "Lưu danh sách" để ghi xuống file rồi đóng cửa sổ
    luôn — trước đó mọi thay đổi chỉ nằm trên giao diện, chưa áp dụng cho lần
    quét sau."""

    def __init__(self, master: tk.Tk, log):
        super().__init__(master)
        self._log = log
        self.selected_kw: str | None = None
        self.title("Từ khoá tiêu cực")
        _center_window(self, 960, 420)
        self.minsize(800, 380)
        self.configure(bg=COLOR_BG)
        self.transient(master)
        self.grab_set()

        pad = ttk.Frame(self, padding=16)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="Từ khoá tiêu cực (quét keyword)", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            pad,
            text="Mỗi từ khoá cách nhau bởi dấu phẩy. Bấm vào 1 từ khoá bên dưới để chọn rồi Sửa/Xoá, "
            "hoặc gõ trực tiếp trong ô như văn bản thường. Nhớ bấm \"Lưu danh sách\" để áp dụng.",
            style="MutedMain.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        text_outer = tk.Frame(pad, bg=COLOR_BORDER)
        text_outer.pack(fill="both", expand=True)
        text_inner = tk.Frame(text_outer, bg=COLOR_CARD)
        text_inner.pack(fill="both", expand=True, padx=1, pady=1)

        scrollbar = ttk.Scrollbar(text_inner, orient="vertical")
        self.text = tk.Text(
            text_inner,
            height=8,  # mặc định của Tk là 24 dòng -> đẩy các nút Thêm/Sửa/Xoá/Lưu
            # ra ngoài rìa cửa sổ (bị "ẩn") vì cửa sổ có chiều cao cố định; giới
            # hạn lại để chừa đủ chỗ, cuộn dọc vẫn dùng được nếu danh sách dài hơn.
            font=("Segoe UI", 10),
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            relief="flat",
            highlightthickness=0,
            wrap="word",
            padx=10,
            pady=8,
            undo=True,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        self.text.tag_configure("selected", background=COLOR_PRIMARY, foreground="#ffffff")
        self.text.bind("<ButtonRelease-1>", self._on_text_click)

        entry_row = ttk.Frame(pad, padding=(0, 10, 0, 0))
        entry_row.pack(fill="x")
        ttk.Label(entry_row, text="Từ khoá:", style="MutedMain.TLabel").pack(side="left", padx=(0, 8))
        self.entry_var = tk.StringVar()
        entry = ttk.Entry(entry_row, textvariable=self.entry_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self._add())

        action_row = ttk.Frame(pad, padding=(0, 8, 0, 0))
        action_row.pack(fill="x")
        ttk.Button(action_row, text="➕ Thêm", style="Primary.TButton", command=self._add).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ttk.Button(action_row, text="✏️ Sửa", command=self._edit).pack(
            side="left", expand=True, fill="x", padx=4
        )
        ttk.Button(action_row, text="🗑️ Xoá", style="Danger.TButton", command=self._delete).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
        )

        btn_row = ttk.Frame(pad, padding=(0, 10, 0, 0))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="↺  Tải lại", command=self._reload).pack(side="left")
        ttk.Button(btn_row, text="💾  Lưu danh sách", style="Success.TButton", command=self._save).pack(
            side="right"
        )

        self._reload()

    # ---------------------------------------------------------- text <-> list

    def _fill(self, keywords: list[str]) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", ", ".join(keywords))
        self._select(None)

    def _parse(self) -> list[str]:
        raw = self.text.get("1.0", "end").replace("\n", ",")
        seen: dict[str, None] = {}
        for part in raw.split(","):
            kw = part.strip().lower()
            if kw:
                seen[kw] = None
        return list(seen)

    # -------------------------------------------------------------- selection

    def _on_text_click(self, event) -> None:
        # Xác định đoạn (giữa 2 dấu phẩy) đang bấm vào bằng cách đếm ký tự từ
        # đầu ô văn bản — cho phép chọn cả cụm từ nhiều tiếng (vd. "không hài
        # lòng"), khác với double-click mặc định của Tk (chỉ chọn 1 từ đơn).
        click_index = self.text.index(f"@{event.x},{event.y}")
        raw = self.text.get("1.0", "end-1c")
        offset = len(self.text.get("1.0", click_index))
        start = 0
        for sep in (",", "\n"):
            pos = raw.rfind(sep, 0, offset)
            start = max(start, pos + 1)
        end_candidates = [p for p in (raw.find(",", offset), raw.find("\n", offset)) if p != -1]
        end = min(end_candidates) if end_candidates else len(raw)
        segment = raw[start:end].strip()
        if segment:
            self._select(segment.lower(), (f"1.0+{start}c", f"1.0+{end}c"))
        else:
            self._select(None)

    def _select(self, kw: str | None, text_range: tuple[str, str] | None = None) -> None:
        self.text.tag_remove("selected", "1.0", "end")
        self.selected_kw = kw
        self.entry_var.set(kw or "")
        if kw and text_range:
            self.text.tag_add("selected", *text_range)

    # ----------------------------------------------------------------- actions

    def _reload(self) -> None:
        self._fill(sentiment.get_keywords())

    def _add(self) -> None:
        kw = self.entry_var.get().strip()
        if not kw:
            return
        keywords = self._parse()
        kw_lower = kw.lower()
        if kw_lower not in keywords:
            keywords.append(kw_lower)
        self._fill(keywords)
        self._log(f'Đã thêm "{kw_lower}" vào danh sách (chưa lưu).')

    def _edit(self) -> None:
        old = self.selected_kw
        if not old:
            messagebox.showinfo("Pancake Watcher", "Bấm chọn 1 từ khoá trong ô danh sách trước.", parent=self)
            return
        new = self.entry_var.get().strip().lower()
        if not new or new == old:
            return
        keywords = self._parse()
        if old in keywords:
            keywords[keywords.index(old)] = new
            keywords = list(dict.fromkeys(keywords))
        self._fill(keywords)
        self._log(f'Đã sửa "{old}" -> "{new}" (chưa lưu).')

    def _delete(self) -> None:
        kw = self.selected_kw
        if not kw:
            messagebox.showinfo("Pancake Watcher", "Bấm chọn 1 từ khoá trong ô danh sách trước.", parent=self)
            return
        if not messagebox.askyesno("Pancake Watcher", f'Xoá từ khoá "{kw}" khỏi danh sách?', parent=self):
            return
        keywords = [k for k in self._parse() if k != kw]
        self._fill(keywords)
        self._log(f'Đã xoá "{kw}" khỏi danh sách (chưa lưu).')

    def _save(self) -> None:
        keywords = self._parse()
        sentiment.set_keywords(keywords)
        self._log(f"Đã lưu danh sách từ khoá tiêu cực ({len(keywords)} từ).")
        try:
            db.init_db()  # đảm bảo bảng đã tồn tại kể cả khi chưa từng bật server
            requeued = db.reset_non_negative_sentiment()
        except Exception as err:  # noqa: BLE001 — Postgres (Docker) có thể chưa bật
            # Từ khoá ĐÃ lưu vào keywords.json ở trên nên không mất; chỉ phần đặt
            # lại hội thoại để quét lại là chưa làm được.
            self._log(
                "⚠️ Chưa nối được Postgres nên chưa đặt lại được các hội thoại cũ "
                "để quét theo từ khoá mới. Chạy `docker compose up -d` rồi lưu lại "
                f"lần nữa. Chi tiết: {err}"
            )
            return
        if requeued:
            self._log(f"Đã đặt lại {requeued} hội thoại (chưa từng tiêu cực) để quét lại theo từ khoá mới.")
        self.destroy()


def main() -> None:
    root = tk.Tk()
    ServerControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
