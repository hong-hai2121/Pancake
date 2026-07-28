# Hướng dẫn chạy lại ZPancake — đọc file này trước tiên

Viết ngày 2026-07-28. Nếu bạn đang đọc file này sau khi đã quên sạch mọi thứ
về dự án (kể cả 80 năm sau) — đọc đúng thứ tự từ trên xuống, đừng nhảy cóc.
File này không giả định bạn còn nhớ gì cả.

## 1. Cái này là gì

**ZPancake** = 1 extension Chrome + 1 server chạy trên máy cá nhân, dùng để
theo dõi hội thoại khách hàng trên trang web `pancake.vn`:

- Extension quét trang `pancake.vn` (đã đăng nhập sẵn trong Chrome), phát
  hiện tin nhắn mới, hiện ra ở 1 panel nổi ngay trên trang + 1 popup ở icon
  extension.
- Đồng thời gửi dữ liệu đó (chỉ đoạn snippet rút gọn, không phải nội dung đầy
  đủ) sang 1 server Python chạy ngay trên máy này (`127.0.0.1:8787`), server
  lưu vào file SQLite và tự chấm cảm xúc tiêu cực (2 cách: so khớp từ khoá,
  hoặc gọi OpenAI).
- Khi phát hiện khách "tiêu cực", server gửi thông báo qua Telegram.

Toàn bộ giải thích chi tiết (kiến trúc, từng file làm gì, cách hoạt động) nằm
ở 2 file:
- [`README.md`](README.md) (thư mục này) — extension.
- [`server/README.md`](server/README.md) — server.

File hiện tại (`HUONG_DAN_CHAY_LAI.md`) chỉ tập trung vào **các bước để chạy
được từ con số 0**, không lặp lại phần giải thích kiến trúc.

## 2. VIỆC ĐẦU TIÊN — kiểm tra cái gì chắc chắn đã hỏng

Đã lâu không đụng tới dự án này thì gần như chắc chắn những thứ sau **không
còn dùng được nữa**, phải làm lại chứ đừng mất thời gian debug:

1. **`server/.env`** — chứa `OPENAI_API_KEY` và `TELEGRAM_BOT_TOKEN` — các
   key/token này gần như chắc chắn đã hết hạn, bị thu hồi, hoặc tài khoản
   liên kết không còn tồn tại. → Làm lại từ mục 5 bên dưới.
2. **Selector HTML trong `content.js`** (`#conversationList`,
   `.rc-virtual-list-holder-inner`, class `snippet-text`, `time-modul`,
   `ant-badge-count`, `name-text`, `platform-*`...) — nếu `pancake.vn` đổi
   giao diện (rất có thể sau nhiều năm), extension sẽ **không phát hiện được
   gì cả** dù không báo lỗi rõ ràng. Cách kiểm tra: mở `pancake.vn`, F12 →
   Console, tìm log bắt đầu bằng `[Pancake Watcher]`. Không thấy log nào dù
   trang đang mở đúng danh sách hội thoại → selector đã lỗi thời, phải mở
   DevTools → tab Elements, dò lại đúng tên class/id hiện tại rồi sửa vào
   `content.js`.
3. **Phiên bản Python/Chrome/Manifest V3** — API của Chrome extension và
   Python có thể đã thay đổi. Nếu cài đặt/chạy báo lỗi lạ không có trong mục
   9 (Xử lý sự cố) bên dưới, khả năng cao là do phiên bản công cụ đã khác quá
   nhiều so với lúc viết code này (`Python 3.12`, Chrome Manifest V3, cuối
   2026) — cần tra cứu lại tài liệu chính thức tương ứng phiên bản bạn đang
   có.
4. **File SQLite cũ** (`server/data/pancake_watcher.db`, nếu còn) — vẫn đọc
   được bình thường (SQLite rất ổn định lâu dài), dữ liệu cũ không tự mất,
   nhưng dĩ nhiên không còn phản ánh khách hàng hiện tại.

## 3. Yêu cầu trước khi cài

- **Windows** (hướng dẫn này viết cho Windows — dự án dùng đường dẫn kiểu
  `taskkill`, shortcut `.lnk`... nếu chạy hệ điều hành khác phải tự đổi
  tương đương).
- **Google Chrome** (hoặc trình duyệt tương thích Manifest V3) đã cài, đã
  đăng nhập tài khoản Pancake trên `pancake.vn`.
- **Python 3.10+** đã cài, có trong PATH. Kiểm tra bằng cách mở PowerShell/
  Terminal, gõ:
  ```powershell
  python --version
  ```
  Không thấy lệnh `python` → tải lại tại https://www.python.org/downloads/
  (chọn bản Windows installer, nhớ tick "Add python.exe to PATH" lúc cài).

## 4. Cài extension Chrome

1. Mở Chrome, vào địa chỉ `chrome://extensions`.
2. Bật **Chế độ nhà phát triển** (Developer mode) — công tắc ở góc trên phải.
3. Bấm **Tải tiện ích đã giải nén** (Load unpacked) → chọn đúng thư mục này
   (`ZPancake/`, thư mục chứa `manifest.json`).
4. Mở `https://pancake.vn/`, đăng nhập nếu chưa, để trang hiện danh sách hội
   thoại. Extension tự chạy — không cần bấm gì thêm.
5. **Mỗi lần sửa code rồi reload extension**: phải F5 lại tab `pancake.vn`
   đang mở, nếu không sẽ thấy lỗi "Extension context invalidated" (không
   phải bug — xem `README.md` mục "Cách hoạt động").

## 5. Cài & cấu hình server (Python)

### 5.1. Cài thư viện

Mở terminal, vào đúng thư mục `server/`:

```bash
cd ZPancake/server
pip install -r requirements.txt
```

### 5.2. Tạo file cấu hình `.env`

```bash
cp .env.example .env
```

Mở file `.env` vừa tạo, có 2 nhóm cấu hình:

**a) Cách chấm cảm xúc tiêu cực** — để mặc định `SENTIMENT_METHOD=keyword`
là chạy được ngay, không cần key gì (offline, so khớp từ khoá tiếng Việt
trong `keywords.json`). Muốn chính xác hơn thì đổi sang `llm` + điền
`OPENAI_API_KEY` (tạo tại https://platform.openai.com/api-keys — cần tài
khoản OpenAI còn hoạt động và có phương thức thanh toán).

**b) Thông báo Telegram khi phát hiện khách tiêu cực** (tuỳ chọn, để trống
thì tắt tính năng này, không lỗi gì cả) — làm lại từ đầu vì bot token cũ gần
chắc chắn đã chết:

1. Mở Telegram, chat với **@BotFather** → gõ `/newbot` → đặt tên bot + đặt
   username (phải kết thúc bằng `bot`, vd `pancake_watcher_bot`) →
   BotFather trả về 1 chuỗi dạng `123456789:AAExxxxxxxxxxxxxxxxxxxxxxx` —
   đó là `TELEGRAM_BOT_TOKEN`, copy vào `.env`.
2. Mở chat với bot vừa tạo, bấm **Start**, nhắn 1 tin bất kỳ (vd "hi").
3. Mở trình duyệt, vào:
   `https://api.telegram.org/bot<TOKEN vừa copy>/getUpdates`
   (thay `<TOKEN vừa copy>` bằng chuỗi ở bước 1). Tìm số ở
   `"chat":{"id": ...}` trong kết quả JSON — đó là `TELEGRAM_CHAT_ID`, copy
   vào `.env`. (Muốn nhận vào 1 nhóm thay vì chat riêng: thêm bot vào nhóm,
   nhắn 1 tin trong nhóm rồi lấy id tương tự — id nhóm là số **âm**.)
4. Lưu file `.env`.

Toàn bộ chi tiết + ảnh minh hoạ dạng text nằm ở `server/.env.example` và
mục "Thông báo Telegram khi phát hiện tiêu cực" trong `server/README.md`.

### 5.3. Chạy server

**Cách khuyên dùng — GUI desktop** (không cần nhớ lệnh gì):

```bash
python gui.py
```

(hoặc double-click shortcut **"Pancake Watcher"** trên Desktop nếu vẫn còn —
nếu mất, xem `server/README.md` mục cài lại shortcut).

Cửa sổ hiện ra có:
- Trạng thái 🟢 đang chạy / 🔴 đã dừng, nút bật/tắt server.
- Nút **"📜 Xem lịch sử hội thoại"** — mở webview xem toàn bộ khách hàng đã
  lưu trong SQLite (`http://127.0.0.1:8787/history`).
- Nút **"🏷️ Quản lý từ khoá tiêu cực..."** — sửa danh sách từ khoá chấm cảm
  xúc mà không cần sửa file tay.
- Nút **"🔔 Kiểm tra kết nối Telegram..."** — gửi thử 1 tin nhắn để xác nhận
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` ở mục 5.2 đã đúng, không cần chờ có
  khách tiêu cực thật mới biết.
- Ô đổi cách chấm cảm xúc + nút **"💾 Lưu cài đặt"** (ghi vào `.env`, tự
  khởi động lại server nếu đang chạy).

**Cách 2 — chạy tay bằng terminal** (để xem log trực tiếp lúc debug):

```bash
cd ZPancake/server
python main.py
```

Kiểm tra server còn sống: mở `http://127.0.0.1:8787/health` trên trình
duyệt, phải thấy `{"status":"ok"}`.

## 6. Kiểm tra mọi thứ chạy đúng (checklist nhanh)

1. `http://127.0.0.1:8787/health` → `{"status":"ok"}`.
2. Mở `pancake.vn`, F12 → Console → thấy log `[Pancake Watcher]` xuất hiện
   khi có hoạt động trong danh sách hội thoại.
3. Panel nổi xuất hiện ngay trên trang `pancake.vn` (góc màn hình, kéo thả
   được) — nếu không thấy, kiểm tra lại bước 4 (cài extension) và mục 2 câu
   2 (selector lỗi thời).
4. Bấm icon extension trên thanh Chrome → popup hiện danh sách hội thoại,
   mỗi dòng có biểu tượng ☁️ báo trạng thái gửi server (☁️✓ = đã lưu vào
   SQLite).
5. Mở `http://127.0.0.1:8787/history` → thấy đúng danh sách khách hàng vừa
   quét được.
6. (Nếu đã cấu hình Telegram) Bấm "🔔 Kiểm tra kết nối Telegram..." trong
   GUI → nhận được tin nhắn thử trên Telegram.

Tất cả đều đúng → hệ thống đã chạy lại hoàn chỉnh.

## 7. Bản đồ file (tra cứu nhanh, xem README để biết chi tiết)

```
ZPancake/
├── manifest.json     khai báo extension (quyền, script nào chạy ở đâu)
├── content.js        quét DOM pancake.vn, phát hiện tin nhắn mới
├── background.js     service worker: lưu local + gửi sang server + poll sentiment
├── panel.js          panel nổi trên trang pancake.vn
├── popup.html/js/css giao diện popup ở icon extension
├── README.md         tài liệu đầy đủ của extension (đọc khi cần hiểu SÂU)
├── HUONG_DAN_CHAY_LAI.md   chính là file bạn đang đọc
└── server/
    ├── main.py        server FastAPI (127.0.0.1:8787) + worker chấm cảm xúc nền
    ├── db.py           SQLite (bảng customers)
    ├── sentiment.py    logic chấm cảm xúc (keyword/llm) + đọc/ghi keywords.json
    ├── telegram.py      gửi thông báo Telegram khi phát hiện "negative"
    ├── gui.py           GUI desktop bật/tắt server + chỉnh cấu hình
    ├── history.html     webview xem lịch sử khách hàng (/history)
    ├── keywords.json    danh sách từ khoá tiêu cực (chỉnh qua GUI hoặc sửa tay)
    ├── requirements.txt thư viện Python cần cài
    ├── .env.example     mẫu cấu hình, copy thành .env rồi điền giá trị thật
    ├── .env             cấu hình thật (KHÔNG commit git, chứa key/token)
    ├── data/pancake_watcher.db   file SQLite chứa toàn bộ dữ liệu đã quét
    └── README.md         tài liệu đầy đủ của server (đọc khi cần hiểu SÂU)
```

## 8. Việc này KHÔNG đụng tới đâu

`ZPancake/` (extension + server ở đây) hoàn toàn độc lập với thư mục `app/`
ở gốc repo (backend FastAPI + Supabase chính của dự án) — không dùng chung
DB, không dùng chung token/API key nào. Đừng đi tìm liên kết giữa 2 phần
này, không có.

## 9. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `pip install` báo lỗi không tìm thấy `python`/`pip` | Chưa cài Python hoặc chưa có trong PATH | Cài lại Python, tick "Add to PATH" lúc cài |
| Extension không phát hiện tin nhắn nào, Console không có log `[Pancake Watcher]` | `pancake.vn` đã đổi giao diện, selector trong `content.js` lỗi thời | Xem mục 2 câu 2 — dò lại selector bằng DevTools |
| Console báo "Extension context invalidated" | Bình thường — vừa reload extension nhưng chưa F5 lại tab | F5 lại tab `pancake.vn` |
| Popup/panel hiện ☁️✗ ở mọi dòng | Server (`python main.py`/GUI) chưa chạy | Bật server, kiểm tra `http://127.0.0.1:8787/health` |
| Bấm "Kiểm tra kết nối Telegram" báo lỗi | Token/chat id sai hoặc hết hạn | Làm lại từ đầu mục 5.2b |
| GUI báo "database is locked" | Hiếm khi xảy ra (đã có WAL + upsert nguyên tử) — có thể do 1 tiến trình `python main.py` khác đang chạy ngầm không qua GUI | Mở Task Manager, tắt hết các tiến trình `python.exe`/`pythonw.exe` liên quan, bật lại qua GUI |
| Nút "Tắt server" trong GUI không tắt được gì | Server được bật bằng terminal riêng (không qua GUI), GUI không có PID để tắt | Tắt đúng ở terminal đã bật (Ctrl+C), hoặc Task Manager |
| Bấm "Bật server" trong GUI xong, log hiện có PID nhưng đèn trạng thái không bao giờ chuyển xanh | Đã từng gặp (2026-07-28, đã sửa): tiến trình con chạy qua `pythonw.exe` không có console → `print()`/log của uvicorn ném lỗi rồi chết ngay không dấu vết. `gui.py` hiện đã tự redirect log ra `server.log` để tránh lỗi này | Bấm nút **"📄 Xem log server"** trong GUI để đọc `server.log` — nếu vẫn gặp lỗi tương tự (đèn không xanh, log dừng ngang giữa chừng không rõ lý do), đó là manh mối đầu tiên cần xem |

## 10. Lời nhắn

Nếu bạn thật sự đang đọc file này sau 80 năm — chúc mừng bạn còn dùng máy
tính chạy được Python và Chrome còn tồn tại. Nếu 2 thứ đó không còn tồn tại
nữa thì file này cũng hết tác dụng rồi, đành phải viết lại từ đầu thôi.
