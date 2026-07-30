# Pancake Watcher — Local Server

Server FastAPI chạy **ở máy của bạn** (`127.0.0.1:8787`), nhận dữ liệu tin
nhắn mới do extension quét được và lưu vào **Postgres** — cùng container Docker
với dự án gốc nhưng **schema riêng `watcher`** (xem `db.py`). Vẫn không dùng
access token Pancake nào cả, chỉ lưu lại đúng những gì extension gửi sang
(snippet rút gọn + metadata hội thoại, chưa phải nội dung tin nhắn đầy đủ).

> **Cần bật DB trước:** `docker compose up -d` ở **thư mục gốc repo**. Quên bật
> thì server vẫn chạy nhưng GUI hiện đèn 🟡 và các endpoint cần DB trả **503**
> kèm câu hướng dẫn; bật DB lên là tự chạy tiếp, **không phải khởi động lại
> server**.

## Cài đặt & chạy

**Cách 1 — GUI desktop (khuyên dùng hàng ngày):**

Double-click shortcut **"Pancake Watcher"** trên Desktop (đã tạo sẵn, icon
🥞 riêng — `icon.ico`), hoặc chạy `pythonw gui.py` (dùng `pythonw`, không
phải `python`, để không hiện cửa sổ đen console — shortcut đã cấu hình sẵn
đúng như vậy, không còn qua `start_gui.bat`/`cmd.exe` nên không có màn hình
đen nào flash lên lúc mở nữa). Cửa sổ hiện:
- 🟢/🔴 trạng thái server đang chạy hay không (tự kiểm tra mỗi 2s qua
  `/health`), nút **Bật/Tắt server**.
- Ô chỉnh **cách quét cảm xúc** (`keyword`/`llm`) và **OpenAI API Key**, bấm
  **"Lưu cài đặt"** để ghi vào `.env` — nếu server đang chạy sẽ tự khởi động
  lại ngay để áp dụng, không cần tắt/mở tay.
- Nút **"📄 Xem log server"** — mở `server.log` (log của `main.py`/uvicorn khi
  bật qua GUI, ghi đè mỗi lần bấm "Bật server"). Vì GUI chạy qua `pythonw.exe`
  (không có console) nên đây là cách DUY NHẤT xem được log của server khi bật
  theo Cách 1 — không redirect ra file thì output của tiến trình con sẽ mất
  hẳn (`sys.stdout`/`stderr` là `None` dưới `pythonw`, xem chú thích trong
  `gui.py` hàm `start_server()`).

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

Target trỏ thẳng vào `pythonw.exe` (không qua `start_gui.bat`/`cmd.exe`) —
đây là điểm mấu chốt để không có cửa sổ đen nào flash lên lúc bấm shortcut.
Đổi đường dẫn `pythonw.exe` bên dưới nếu Python cài ở nơi khác trên máy bạn
(kiểm tra bằng `python -c "import sys; print(sys.executable)"` rồi đổi đuôi
`python.exe` thành `pythonw.exe`).

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Pancake Watcher.lnk")
$Shortcut.TargetPath = "C:\Users\Admin\AppData\Local\Programs\Python\Python312\pythonw.exe"
$Shortcut.Arguments = "gui.py"
$Shortcut.WorkingDirectory = "D:\HONGHAI\Pancake\ZPancake\server"
$Shortcut.IconLocation = "D:\HONGHAI\Pancake\ZPancake\server\icon.ico,0"
$Shortcut.Save()
```

</details>

> Extension (`background.js`) gọi cố định tới `http://localhost:8787/api/messages`
> — server phải đang chạy thì dữ liệu mới được lưu. Nếu server tắt, extension
> vẫn hoạt động bình thường (popup/panel/log console không phụ thuộc server
> này), chỉ là không có bản sao trong DB; `background.js` sẽ log 1 dòng
> cảnh báo (không lặp lại liên tục) mỗi lần gửi thất bại.

## Schema

`watcher.customers` trong database `pancakebot` (schema + bảng + index tự tạo ở
lần chạy đầu) — **1 bảng duy nhất**: mỗi khách hàng (hội thoại, khoá `raw_id`)
1 dòng, chứa đúng tin nhắn cuối cùng gửi đến (ghi đè mỗi khi có tin mới, không
giữ log lịch sử):

```
raw_id, platform, kind, page_id, conv_id, name,
snippet, time_text, unread_count, reason, detected_at,
first_seen_at, last_seen_at,
sentiment, sentiment_method, sentiment_checked_at
```

Các cột thời gian cố ý giữ kiểu **text ISO-8601 UTC** (không đổi sang
`timestamptz`) để mọi so sánh `sentiment_checked_at < detected_at`, dữ liệu
extension gửi lên và JSON trả về giữ nguyên hành vi như bản SQLite cũ.

Xem nhanh qua webview `/history` (mục bên dưới); cần truy vấn SQL tuỳ ý thì:

```powershell
# psql trong container (chạy ở thư mục gốc repo)
docker compose exec db psql -U postgres -d pancakebot -c "select * from watcher.customers;"

# hoặc giao diện web Adminer
docker compose --profile ui up -d      # rồi mở http://127.0.0.1:8080/?pgsql=db
```

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

## Thông báo Telegram khi phát hiện tiêu cực (`telegram.py`)

Mỗi khi `sentiment_worker()` (trong `main.py`) chấm 1 khách hàng là
"negative", nó gọi thêm `telegram.send_negative_alert()` — gửi tin nhắn qua
Telegram Bot API (best-effort, lỗi/timeout chỉ log ra console, không làm chết
worker). Tin nhắn gồm tên khách, nền tảng (Zalo/Facebook) và snippet.

**Bật tính năng này (tuỳ chọn — thiếu cấu hình thì tự bỏ qua, không lỗi):**

1. Tạo bot: mở Telegram, chat với **@BotFather** → gõ `/newbot` → đặt tên và
   username (phải kết thúc bằng `bot`) → BotFather trả về 1 chuỗi dạng
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxx`, đó là `TELEGRAM_BOT_TOKEN`.
2. Lấy chat id: mở chat với bot vừa tạo, bấm **Start**, nhắn 1 tin bất kỳ
   (vd "hi"). Sau đó mở trình duyệt vào
   `https://api.telegram.org/bot<TOKEN>/getUpdates`, tìm số ở
   `"chat":{"id": ...}` trong JSON trả về — đó là `TELEGRAM_CHAT_ID`. (Muốn
   nhận vào 1 nhóm thay vì chat riêng: thêm bot vào nhóm, nhắn 1 tin trong
   nhóm đó rồi lấy id tương tự — id nhóm là số **âm**.)
3. Điền 2 giá trị trên vào **`.env` ở thư mục GỐC của dự án** (không phải
   `server/.env` nữa — 2 dòng này dùng chung cho cả app chính lẫn ZPancake nên
   để một chỗ, khỏi điền 2 nơi rồi lệch nhau):
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAExxxxxxxxxxxxxxxxxxxxxxx
   TELEGRAM_CHAT_ID=987654321
   ```
   > Muốn ZPancake bắn sang **kênh Telegram khác** app chính thì khai lại 2 dòng
   > đó trong `server/.env` — file này được nạp SAU nên ghi đè `.env` gốc.
4. Khởi động lại server (hoặc mở `gui.py` → **"🔔 Kiểm tra kết nối
   Telegram..."** để gửi thử ngay 1 tin nhắn xác nhận, không cần chờ có
   khách hàng tiêu cực thật).

`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` không có ô sửa trên GUI chính (giống
`OPENAI_API_KEY`, coi là thông tin nhạy cảm) — chỉnh trực tiếp trong `.env` gốc.
Chỉ gửi thông báo khi có **tin mới** khiến 1 khách chuyển sang "negative"
(dựa theo cùng điều kiện `get_unanalyzed()` ở trên) — không gửi lặp lại mỗi
8 giây cho cùng 1 khách nếu không có gì thay đổi.

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
- **Phía server**: Postgres xử lý ghi đồng thời sẵn (không còn cảnh "database
  is locked" như SQLite), cộng với `INSERT ... ON CONFLICT DO UPDATE` (upsert
  nguyên tử trong 1 câu lệnh) thay vì kiểu "kiểm tra rồi ghi" — loại bỏ khoảng
  hở race giữa 2 bước đó khi 2 request cùng đến cho cùng 1 hội thoại.
- Connection pool dùng CHUNG với dự án gốc (`app/db/client.py::get_pg_pool`),
  nên không mở kết nối mới cho từng truy vấn và an toàn khi FastAPI chạy handler
  trong nhiều thread.

## API

- `GET /health` → `{"status": "ok"|"degraded", "db": "ok"|"down", "dbError": "..."}`
  — luôn 200 khi tiến trình server còn sống (GUI dùng để biết server bật/tắt);
  `db` cho biết Postgres đã lên chưa. Trả lời trong ~0.05s kể cả khi DB tắt.
- `POST /api/messages` — body `{"events": [...]}`, mỗi phần tử khớp shape sự
  kiện extension gửi (`rawId`, `platform`, `kind`, `pageId`, `convId`, `name`,
  `snippet`, `time`, `unreadCount`, `platformClass`, `reason`, `detectedAt`).
  Trả về `{"status": "ok", "inserted": N}` — `N` có thể nhỏ hơn số phần tử gửi
  lên nếu có event bị loại vì `sentiment.is_page_message()` nhận diện là tin
  PAGE tự động gửi (nhãn `[Botcake]`, xem mục Telegram bên dưới) — không lưu
  DB, không tính vào `inserted`. Extension (`background.js`) đã tự lọc trước
  khi gửi rồi nên trường hợp này hiếm khi xảy ra ở endpoint, chỉ là lớp chặn
  dự phòng thứ 2.
- `GET /api/sentiment` → `{"items": [{"rawId", "sentiment", "sentimentMethod",
  "sentimentCheckedAt"}, ...]}` — tối đa 200 kết quả gần nhất, cho extension
  poll định kỳ.
- `GET /api/customers?sort=<cột>&order=asc|desc` → `{"items": [...]}` — toàn bộ
  khách hàng (không phân trang), dùng cho webview `/history`. `sort` chỉ nhận
  các cột trong whitelist `SORTABLE_COLUMNS` (`db.py`), sai tên tự rơi về
  `detected_at`.
- `DELETE /api/customers/{raw_id}` — xoá hẳn 1 khách hàng khỏi DB (không thể
  hoàn tác). 404 nếu `raw_id` không tồn tại.
- Mọi endpoint chạm DB trả **503** kèm câu "Chưa nối được Postgres. Chạy
  `docker compose up -d`..." khi DB chưa lên, thay vì 500 khó hiểu.

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
