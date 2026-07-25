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
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.request import urlopen

SERVER_DIR = Path(__file__).parent
ENV_PATH = SERVER_DIR / ".env"
PID_PATH = SERVER_DIR / "server.pid"  # để tắt được server kể cả khi đóng rồi mở lại GUI
HEALTH_URL = "http://127.0.0.1:8787/health"


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
        self.root.title("Pancake Watcher — Server Control")
        self.root.geometry("380x340")
        self.root.resizable(False, False)

        self.process: subprocess.Popen | None = None  # tiến trình do CHÍNH gui này bật

        self._build_ui()
        self._poll_status()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", **pad)
        self.status_dot = tk.Canvas(status_frame, width=14, height=14, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_circle = self.status_dot.create_oval(2, 2, 12, 12, fill="#9ca3af", outline="")
        self.status_label = ttk.Label(status_frame, text="Đang kiểm tra...", font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="left", padx=8)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btn_frame, text="▶ Bật server", command=self.start_server)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.stop_btn = ttk.Button(btn_frame, text="■ Tắt server", command=self.stop_server)
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

        ttk.Separator(self.root).pack(fill="x", padx=12, pady=8)

        settings_frame = ttk.LabelFrame(self.root, text="Cài đặt (.env)")
        settings_frame.pack(fill="x", padx=12)

        ttk.Label(settings_frame, text="Cách quét cảm xúc:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.method_var = tk.StringVar()
        method_combo = ttk.Combobox(
            settings_frame, textvariable=self.method_var, values=["keyword", "llm"], state="readonly", width=15
        )
        method_combo.grid(row=0, column=1, padx=8, pady=6)

        ttk.Label(settings_frame, text="OpenAI API Key:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.api_key_var = tk.StringVar()
        api_key_entry = ttk.Entry(settings_frame, textvariable=self.api_key_var, show="•", width=26)
        api_key_entry.grid(row=1, column=1, padx=8, pady=6)

        values = read_env()
        self.method_var.set(values["SENTIMENT_METHOD"])
        self.api_key_var.set(values["OPENAI_API_KEY"])

        ttk.Button(self.root, text="💾 Lưu cài đặt", command=self.save_settings).pack(
            fill="x", padx=12, pady=(10, 4)
        )
        ttk.Label(
            self.root,
            text="Lưu khi server đang chạy sẽ tự khởi động lại để áp dụng cài đặt mới.",
            foreground="#6b7280",
            wraplength=340,
            justify="left",
        ).pack(fill="x", padx=12)

        self.log_text = tk.Text(self.root, height=5, state="disabled", font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(8, 12))

    def log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # --------------------------------------------------------------- logic

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

    def save_settings(self) -> None:
        values = {
            "SENTIMENT_METHOD": self.method_var.get() or "keyword",
            "OPENAI_API_KEY": self.api_key_var.get(),
        }
        write_env(values)
        self.log(f"Đã lưu cài đặt vào .env (SENTIMENT_METHOD={values['SENTIMENT_METHOD']}).")
        if self.process is not None and self.process.poll() is None:
            self.log("Server đang chạy → tự khởi động lại để áp dụng...")
            self.stop_server()
            self.root.after(800, self.start_server)

    def _poll_status(self) -> None:
        if self.is_healthy():
            self.status_dot.itemconfig(self.status_circle, fill="#16a34a")
            self.status_label.configure(text="🟢 Đang chạy (127.0.0.1:8787)")
        else:
            self.status_dot.itemconfig(self.status_circle, fill="#dc2626")
            self.status_label.configure(text="🔴 Đã dừng")
        self.root.after(2000, self._poll_status)

    def _on_close(self) -> None:
        # Đóng cửa sổ KHÔNG tự tắt server — để server tiếp tục chạy nền bình
        # thường (giống việc chỉ đóng terminal điều khiển, không phải chủ ý
        # tắt server). Muốn tắt hẳn thì bấm "■ Tắt server" trước khi đóng.
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ServerControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
