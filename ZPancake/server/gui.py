"""GUI desktop cho Pancake Watcher local server — bật/tắt server + chỉnh cấu
hình (.env) mà không cần mở terminal hay sửa file tay.

Chạy: python gui.py (hoặc double-click "Pancake Watcher.lnk" trên Desktop nếu
đã tạo shortcut — xem README.md). Dùng tkinter (có sẵn trong Python, không
cần cài thêm gì).
"""

import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.request import urlopen

import sentiment

SERVER_DIR = Path(__file__).parent
ENV_PATH = SERVER_DIR / ".env"
PID_PATH = SERVER_DIR / "server.pid"  # để tắt được server kể cả khi đóng rồi mở lại GUI
HEALTH_URL = "http://127.0.0.1:8787/health"
HISTORY_URL = "http://127.0.0.1:8787/history"

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
COLOR_LOG_BG = "#111827"
COLOR_LOG_TEXT = "#d1d5db"


def read_env() -> dict:
    values = {"SENTIMENT_METHOD": "keyword", "OPENAI_API_KEY": ""}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in values:
                values[key] = val.strip()
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
    lines = [
        "# File này do gui.py tự ghi khi bấm \"Lưu cài đặt\" — có thể chỉnh tay",
        "# nhưng lần sau lưu qua GUI sẽ ghi đè lại theo đúng 2 dòng dưới.",
        f"SENTIMENT_METHOD={values['SENTIMENT_METHOD']}",
        f"OPENAI_API_KEY={values['OPENAI_API_KEY']}",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


class ServerControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🐼 Pancake Watcher — Server Control")
        _center_window(self.root, 460, 500)
        self.root.minsize(420, 460)
        self.root.configure(bg=COLOR_BG)

        self.process: subprocess.Popen | None = None  # tiến trình do CHÍNH gui này bật

        self._build_style()
        self._build_ui()
        self._poll_status()
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

        # ---------------------------------------------------- card trạng thái
        status_outer, status_card = self._card(body)
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

        history_row = ttk.Frame(status_card, style="Card.TFrame", padding=(14, 0, 14, 14))
        history_row.pack(fill="x")
        ttk.Button(
            history_row, text="📜  Xem lịch sử hội thoại", command=self.open_history
        ).pack(fill="x")

        # ----------------------------------------------------- card cài đặt
        settings_outer, settings_card = self._card(body)
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

        ttk.Button(
            settings_pad,
            text="🏷️  Quản lý từ khoá tiêu cực...",
            command=self.open_keywords_dialog,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(settings_pad, text="💾  Lưu cài đặt", style="Primary.TButton", command=self.save_settings).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 6)
        )
        ttk.Label(
            settings_pad,
            text="Lưu khi server đang chạy sẽ tự khởi động lại để áp dụng cài đặt mới.",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        # --------------------------------------------------------- nhật ký
        ttk.Label(body, text="Nhật ký", style="MutedMain.TLabel").pack(anchor="w", pady=(0, 4))
        log_outer, log_card = self._card(body)
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

    def is_healthy(self) -> bool:
        try:
            with urlopen(HEALTH_URL, timeout=0.6) as resp:
                return resp.status == 200
        except (URLError, OSError, TimeoutError):
            return False

    def start_server(self) -> None:
        if self.is_healthy():
            messagebox.showinfo("Pancake Watcher", "Server đã đang chạy rồi.")
            return
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [sys.executable, "main.py"], cwd=str(SERVER_DIR), creationflags=creationflags
        )
        PID_PATH.write_text(str(self.process.pid), encoding="utf-8")
        self.log(f"Đã bật server (PID {self.process.pid}).")

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

        try:
            # /T = tắt cả cây tiến trình con — uvicorn chạy reload=True sẽ đẻ ra 1
            # tiến trình worker con, chỉ tắt tiến trình cha sẽ để sót con chạy mồ côi.
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.log(f"Đã tắt server (PID {pid}).")
        except Exception as err:  # noqa: BLE001 - báo lỗi cho người dùng thấy, không crash GUI
            self.log(f"Không tắt được server (PID {pid}): {err}")

        self.process = None
        if PID_PATH.exists():
            PID_PATH.unlink()

    def open_keywords_dialog(self) -> None:
        KeywordsDialog(self.root, log=self.log)

    def open_history(self) -> None:
        if not self.is_healthy():
            messagebox.showwarning("Pancake Watcher", "Bật server trước khi xem lịch sử.")
            return
        webbrowser.open(HISTORY_URL)

    def save_settings(self) -> None:
        # Giữ nguyên OPENAI_API_KEY đang có trong .env — GUI không có ô để sửa
        # giá trị này (xem ghi chú ở _build_ui), chỉ đổi SENTIMENT_METHOD.
        current = read_env()
        values = {
            "SENTIMENT_METHOD": self.method_var.get() or "keyword",
            "OPENAI_API_KEY": current["OPENAI_API_KEY"],
        }
        write_env(values)
        self.log(f"Đã lưu cài đặt vào .env (SENTIMENT_METHOD={values['SENTIMENT_METHOD']}).")
        if self.process is not None and self.process.poll() is None:
            self.log("Server đang chạy → tự khởi động lại để áp dụng...")
            self.stop_server()
            self.root.after(800, self.start_server)

    def _poll_status(self) -> None:
        if self.is_healthy():
            self.status_dot.itemconfig(self.status_circle, fill=COLOR_SUCCESS)
            self.status_label.configure(text="🟢 Đang chạy", foreground=COLOR_SUCCESS)
        else:
            self.status_dot.itemconfig(self.status_circle, fill=COLOR_DANGER)
            self.status_label.configure(text="🔴 Đã dừng", foreground=COLOR_DANGER)
        self.root.after(2000, self._poll_status)

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
        self.destroy()


def main() -> None:
    root = tk.Tk()
    ServerControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
