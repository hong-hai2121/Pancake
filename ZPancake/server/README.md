# Pancake Watcher — Local Server

Server FastAPI chạy **ở máy của bạn** (`127.0.0.1:8787`), nhận dữ liệu tin
nhắn mới do extension quét được và lưu vào file SQLite. Hoàn toàn độc lập với
backend chính ở thư mục gốc repo (`app/`) — không dùng chung DB, không dùng
access token Pancake nào cả, chỉ lưu lại đúng những gì extension gửi sang
(snippet rút gọn + metadata hội thoại, chưa phải nội dung tin nhắn đầy đủ).

## Cài đặt & chạy

**Cách 1 — GUI desktop (khuyên dùng hàng ngày):**

Double-click shortcut **"Pancake Watcher"** trên Desktop (đã tạo sẵn), hoặc
chạy `python gui.py` (hoặc `pythonw gui.py` để không hiện cửa sổ đen console).
Cửa sổ hiện:
- 🟢/🔴 trạng thái server đang chạy hay không (tự kiểm tra mỗi 2s qua
  `/health`), nút **Bật/Tắt server**.
- Ô chỉnh **cách quét cảm xúc** (`keyword`/`llm`) và **OpenAI API Key**, bấm
  **"Lưu cài đặt"** để ghi vào `.env` — nếu server đang chạy sẽ tự khởi động
  lại ngay để áp dụng, không cần tắt/mở tay.

Muốn tạo lại shortcut trên Desktop (nếu lỡ xoá): xem đoạn PowerShell ở cuối
mục này.

**Cách 2 — chạy tay bằng terminal (để xem log trực tiếp lúc debug):**

```bash
cd ZPancake/server
pip install -r requirements.txt
python main.py
```

Server chạy ở `http://127.0.0.1:8787`. Kiểm tra còn sống:
`curl http://127.0.0.1:8787/health` → `{"status":"ok"}`.

<details>
<summary>Tạo lại shortcut "Pancake Watcher" trên Desktop (PowerShell)</summary>

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Pancake Watcher.lnk")
$Shortcut.TargetPath = "D:\HONGHAI\Pancake\ZPancake\server\start_gui.bat"
$Shortcut.WorkingDirectory = "D:\HONGHAI\Pancake\ZPancake\server"
$Shortcut.Save()
```

</details>

> Extension (`background.js`) gọi cố định tới `http://localhost:8787/api/messages`
> — server phải đang chạy thì dữ liệu mới được lưu. Nếu server tắt, extension
> vẫn hoạt động bình thường (popup/panel/log console không phụ thuộc server
> này), chỉ là không có bản sao trong SQLite; `background.js` sẽ log 1 dòng
> cảnh báo (không lặp lại liên tục) mỗi lần gửi thất bại.

## Schema

`data/pancake_watcher.db` (tự tạo khi chạy lần đầu) — **1 bảng duy nhất**
`customers`: mỗi khách hàng (hội thoại, khoá `raw_id`) 1 dòng, chứa đúng tin
nhắn cuối cùng gửi đến (ghi đè mỗi khi có tin mới, không giữ log lịch sử):

```
raw_id, platform, kind, page_id, conv_id, name,
snippet, time_text, unread_count, reason, detected_at,
first_seen_at, last_seen_at,
sentiment, sentiment_method, sentiment_checked_at
```

Xem nhanh qua webview `/history` (xem mục bên dưới), hoặc dùng [DB Browser for SQLite](https://sqlitebrowser.org/) (miễn phí) — mở file `data/pancake_watcher.db` — khi cần truy vấn SQL tuỳ ý.

## Quét cảm xúc tiêu cực (`sentiment.py`)

Chạy **nền, tách hẳn khỏi `POST /api/messages`** — mỗi ~8 giây, worker
(`sentiment_worker()` trong `main.py`, khởi động cùng server) tự lấy tối đa
10 khách hàng có snippet mới hơn lần quét gần nhất (`sentiment_checked_at IS
NULL OR sentiment_checked_at < detected_at`), phân loại rồi ghi kết quả
ngược lại — **không bao giờ làm chậm việc lưu tin nhắn của extension**.

Cấu hình qua `.env` (copy từ `.env.example`):

```bash
cp .env.example .env
```

- `SENTIMENT_METHOD=keyword` (mặc định) — khớp danh sách từ khoá/cụm từ tiêu
  cực tiếng Việt trong `sentiment.py` (vd "thất vọng", "không hiệu quả", "hủy
  dịch vụ"...). Offline, không tốn phí, nhưng snippet ngắn + chỉ khớp từ khoá
  nên độ chính xác giới hạn — có thể bỏ sót hoặc báo nhầm.
- `SENTIMENT_METHOD=llm` — gọi OpenAI (`gpt-4o-mini`) để phân loại, hiểu được
  ngữ cảnh/mỉa mai tốt hơn nhiều. Cần thêm `OPENAI_API_KEY` (key riêng cho
  ZPancake, không dùng chung với `app/` ở gốc repo), tốn phí nhỏ mỗi lần gọi,
  cần internet. Chưa cấu hình key thì tự động coi như "neutral", không lỗi.

Extension poll `GET /api/sentiment` mỗi phút (`chrome.alarms` trong
`background.js`) để lấy kết quả mới, hội thoại "negative" hiện viền đỏ + nhãn
"⚠️ Tiêu cực" trên popup/panel.

## An toàn khi nhiều request tới cùng lúc

Lúc bấm "Cập nhật" (sweep cuộn cả danh sách) hoặc nhiều hội thoại có tin mới
cùng lúc, `background.js` có thể tạo ra nhiều lượt gửi gần như liên tiếp. Để
không mất/lỗi dữ liệu:

- **Phía extension**: `background.js` gộp các tin đang chờ theo `rawId` (Map,
  giữ bản mới nhất) và gửi **tuần tự từng đợt một** (không gửi đồng thời) —
  tin nào đến trong lúc đợt trước đang gửi dở sẽ tự gộp vào đợt kế tiếp thành
  1 request duy nhất, thay vì tạo thêm request riêng. Tự thử lại tối đa 3 lần
  (chờ tăng dần 600ms/1200ms) nếu server chưa phản hồi kịp trước khi đánh dấu
  thất bại (☁️✗ trên popup/panel).
- **Phía server**: bật `PRAGMA journal_mode=WAL` (SQLite) để đọc/ghi đồng thời
  tốt hơn, và dùng `INSERT ... ON CONFLICT DO UPDATE` (upsert nguyên tử trong
  1 câu lệnh) thay vì kiểu "kiểm tra rồi ghi" — loại bỏ khoảng hở race giữa 2
  bước đó khi 2 request cùng đến cho cùng 1 hội thoại.
- Đã kiểm thử: 60 luồng ghi đồng thời (kể cả nhiều luồng cùng ghi 1 `raw_id`
  — tình huống xấu nhất) → 0 lỗi, dữ liệu đúng.

## API

- `GET /health` → `{"status": "ok"}`
- `POST /api/messages` — body `{"events": [...]}`, mỗi phần tử khớp shape sự
  kiện extension gửi (`rawId`, `platform`, `kind`, `pageId`, `convId`, `name`,
  `snippet`, `time`, `unreadCount`, `platformClass`, `reason`, `detectedAt`).
  Trả về `{"status": "ok", "inserted": N}`.
- `GET /api/sentiment` → `{"items": [{"rawId", "sentiment", "sentimentMethod",
  "sentimentCheckedAt"}, ...]}` — tối đa 200 kết quả gần nhất, cho extension
  poll định kỳ.
- `GET /api/customers?sort=<cột>&order=asc|desc` → `{"items": [...]}` — toàn bộ
  khách hàng (không phân trang), dùng cho webview `/history`. `sort` chỉ nhận
  các cột trong whitelist `SORTABLE_COLUMNS` (`db.py`), sai tên tự rơi về
  `detected_at`.
- `DELETE /api/customers/{raw_id}` — xoá hẳn 1 khách hàng khỏi SQLite (không
  thể hoàn tác). 404 nếu `raw_id` không tồn tại.

## Webview lịch sử (`/history`)

Mở `http://127.0.0.1:8787/history` (hoặc bấm **"📜 Xem lịch sử hội thoại"**
trong `gui.py`) để xem toàn bộ hội thoại đã lưu, kèm trạng thái quét cảm xúc
("⏳ Chưa quét" / "✅ Đã quét" / "⚠️ Tiêu cực"). Bấm tiêu đề cột (Khách hàng,
Nền tảng, Phát hiện lúc, Lần cuối thấy, Trạng thái quét) để sắp xếp; có ô lọc
theo tên/nội dung/trang, và nút **Xóa** mỗi dòng (có xác nhận trước khi xoá —
xoá thẳng khỏi DB, không có thùng rác).

Trang này là 1 file HTML tĩnh tự chứa (`history.html`, CSS/JS inline), server
chỉ đọc và trả về — không cần build/bundle gì. Không có xác thực (giống toàn
bộ server) — chỉ nên truy cập từ máy cá nhân.

## Giới hạn / việc để phát triển sau

- Chỉ lưu snippet rút gọn, không phải nội dung tin nhắn đầy đủ (extension chỉ
  thấy được đến vậy từ danh sách hội thoại) — quét cảm xúc cũng vì vậy mà bị
  giới hạn độ chính xác theo đúng snippet đó, dù chọn cách nào (keyword/llm).
- Danh sách từ khoá tiêu cực trong `sentiment.py` là bộ khởi điểm, nên tinh
  chỉnh thêm theo thực tế khách hàng phàn nàn gì (thêm/bớt trực tiếp trong
  file, không cần khởi động lại server nhờ đọc lại mỗi lần gọi).
- Sentiment chỉ có 2 nhãn thực dụng cho mục đích cảnh báo: "negative" (tô đỏ
  trên UI) và mọi thứ khác coi là "neutral"/"positive" (không cảnh báo).
- Hàng đợi gửi ở `background.js` chỉ tồn tại trong bộ nhớ (không persist) —
  nếu Chrome tắt hẳn service worker giữa lúc hàng đợi còn phần tử chưa gửi
  (hiếm, thường chỉ xảy ra khi rất nhiều lượt dồn lại), phần đó sẽ mất; tin
  nhắn thật sự mới hơn từ cùng hội thoại sẽ tự ghi đè đúng ở lần gửi kế tiếp.
- Chạy local, không có auth — chỉ nên chạy trên máy cá nhân, không expose ra
  mạng ngoài. Webview `/history` cho xoá dữ liệu trực tiếp (DELETE), cũng
  không có auth nên áp dụng đúng giới hạn này.
- GUI (`gui.py`) chỉ quản lý được tiến trình do chính nó bật (nhờ file
  `server.pid`, vẫn tắt được kể cả sau khi đóng rồi mở lại GUI) — nếu bạn tự
  chạy `python main.py` bằng terminal riêng, GUI thấy server "đang chạy"
  nhưng nút "Tắt server" sẽ không tắt được (báo bạn tự tắt ở đúng terminal
  đó), vì không có PID để tắt an toàn.
