  

# Pancake New Message Watcher

Extension Chrome (Manifest V3) theo dõi div danh sách hội thoại trên
`pancake.vn` (`#conversationList .rc-virtual-list-holder-inner`) để phát hiện
khi có tin nhắn mới, hiển thị qua popup/panel nổi, và **gửi sang server Python
chạy ở máy** (`ZPancake/server/`, xem README riêng ở đó) để lưu vào SQLite.

## Cấu trúc thư mục & chức năng từng file

**Extension (thư mục gốc `ZPancake/`):**

| File              | Chức năng                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manifest.json` | Khai báo Manifest V3: quyền (`storage`, `alarms`), host permissions (`pancake.vn`, `localhost:8787`), đăng ký `background.js` làm service worker, `content.js` + `panel.js` làm content script chạy trên `pancake.vn`, và `popup.html` làm popup của icon extension.                                                                                                                                                                                                                                                                                                                                                                                                               |
| `content.js`    | Script chèn vào trang`pancake.vn`, đảm nhiệm việc **quét**: gắn `MutationObserver` vào danh sách hội thoại + quét dự phòng mỗi 3 giây, so sánh snapshot để phát hiện tin nhắn mới (2 lớp: theo id hội thoại và theo vị trí đầu danh sách), tự phát hiện `Extension context invalidated`, và xử lý logic cuộn quét toàn bộ danh sách khi bấm nút "Cập nhật" (`sweepFullList`). Gửi sự kiện phát hiện được cho `background.js` qua `chrome.runtime.sendMessage`.                                                                                                                                                                         |
| `background.js` | Service worker nền: nhận sự kiện tin nhắn mới từ`content.js`, lưu vào `chrome.storage.local` (key `pancake_events`, mỗi hội thoại 1 bản ghi, tối đa 300 hội thoại), cập nhật số đếm trên icon, gộp và chuyển tiếp (best-effort, tự thử lại) dữ liệu sang server local (`server/`) — **trừ tin có nhãn `[Botcake]`** (page tự động gửi, không phải tin khách — `isPageMessage()`, vẫn lưu vào `chrome.storage.local`/hiện ở popup/panel như bình thường, chỉ không gửi server) — và định kỳ (`chrome.alarms`, mỗi phút) gọi `GET /api/sentiment` để lấy kết quả quét cảm xúc rồi gộp vào dữ liệu hiển thị. |
| `panel.js`      | Dựng**panel nổi** ngay trên trang `pancake.vn` (Shadow DOM, kéo thả di chuyển tự do, thu gọn/mở rộng, nhớ vị trí qua `pancake_panel_state`). Chỉ đọc/ghi `chrome.storage.local` (không tự quét DOM), luôn đồng bộ real-time với popup qua `chrome.storage.onChanged`.                                                                                                                                                                                                                                                                                                                                                                                                      |
| `popup.html`    | Khung giao diện popup hiện ra khi bấm icon extension: tiêu đề, công tắc bật/tắt theo dõi, nút "Cập nhật", danh sách hội thoại.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `popup.js`      | Logic cho`popup.html`: đọc `pancake_events` để vẽ danh sách (sắp theo tin mới nhất lên đầu, hiện trạng thái gửi server ☁️, nhãn cảnh báo "⚠️ Tiêu cực"), xử lý bấm đánh dấu đã đọc, bật/tắt công tắc tổng, và gửi lệnh "Cập nhật" tới content script qua `chrome.tabs.sendMessage`.                                                                                                                                                                                                                                                                                                                                                                          |
| `popup.css`     | Style riêng cho`popup.html` (kích thước popup, màu trạng thái, hiệu ứng dòng mới nhấp nháy vàng...).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

**Server local (`ZPancake/server/`, FastAPI + SQLite — xem chi tiết ở `server/README.md`):**

| File                        | Chức năng                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main.py`                 | Điểm khởi động server FastAPI (`127.0.0.1:8787`): định nghĩa endpoint `GET /health`, `POST /api/messages` (nhận sự kiện từ extension), `GET /api/sentiment` (trả kết quả quét cảm xúc cho extension poll), và chạy vòng lặp nền `sentiment_worker()` quét cảm xúc mỗi ~8 giây tách biệt khỏi luồng lưu tin. Chạy `uvicorn` không bật `reload` (tắt cố ý — `reload=True` bị treo vĩnh viễn khi bật qua `pythonw.exe`, xem `server/README.md`).                               |
| `db.py`                   | Lớp truy cập SQLite: tạo/migrate bảng`customers` (1 dòng/hội thoại), `save_event()` upsert nguyên tử, `get_unanalyzed()` lấy khách chưa quét cảm xúc, `update_sentiment()` ghi kết quả, `get_recent_sentiments()` cho endpoint poll. Bật `PRAGMA journal_mode=WAL` để an toàn khi nhiều request ghi đồng thời.                                                                                                                                                                                         |
| `sentiment.py`            | Logic phân loại cảm xúc tiêu cực từ snippet:`keyword` (khớp danh sách từ khoá tiếng Việt, offline) hoặc `llm` (gọi OpenAI `gpt-4o-mini`), chọn qua biến `SENTIMENT_METHOD` trong `.env`.                                                                                                                                                                                                                                                                                                                         |
| `telegram.py`             | Gửi thông báo Telegram (`send_negative_alert()`) khi `sentiment_worker()` chấm 1 khách hàng "negative" — cấu hình qua `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` trong `.env`, thiếu thì tự bỏ qua, không lỗi.                                                                                                                                                                                                                                                                                                        |
| `gui.py`                  | GUI desktop (tkinter) để bật/tắt server và chỉnh`SENTIMENT_METHOD`/`OPENAI_API_KEY` mà không cần sửa `.env` bằng tay; tự kiểm tra `/health` mỗi 2s để hiện trạng thái 🟢/🔴, tự khởi động lại server khi lưu cài đặt mới. Có nút gửi thử tin nhắn để kiểm tra kết nối Telegram, nút xem `server.log`, icon cửa sổ riêng (`icon.ico`). Khi bật server, redirect stdout/stderr của tiến trình con ra `server.log` (bắt buộc vì chạy qua `pythonw.exe` không có console). |
| `icon.ico`                | Icon 🥞 (nhiều size 16→256px) cho cửa sổ GUI (`gui.py` gọi `iconbitmap`) và cho shortcut "Pancake Watcher" trên Desktop — thay cho icon mặc định của Python.                                                                                                                                                                                                                                                                                                                                                                |
| `server.log`              | Log của`main.py`/uvicorn khi bật qua GUI (ghi đè mỗi lần bấm "Bật server") — tự tạo, không commit git (`*.log` trong `.gitignore`). Xem qua nút "📄 Xem log server" trong GUI.                                                                                                                                                                                                                                                                                                                                           |
| `start_gui.bat`           | Script chạy tay`gui.py` qua `pythonw.exe` (không hiện cửa sổ console) — vẫn giữ để chạy thủ công, nhưng shortcut Desktop hiện trỏ thẳng vào `pythonw.exe` (không qua file `.bat` này nữa) để tránh flash cửa sổ cmd đen lúc mở.                                                                                                                                                                                                                                                                        |
| `requirements.txt`        | Các thư viện Python cần cài (`fastapi`, `uvicorn`, `python-dotenv`, `httpx`).                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `.env.example`            | Mẫu file cấu hình (`SENTIMENT_METHOD`, `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — kèm hướng dẫn lấy 2 giá trị Telegram), copy thành `.env` rồi chỉnh lại (`.env` đã bị `.gitignore` bỏ qua).                                                                                                                                                                                                                                                                                             |
| `data/pancake_watcher.db` | File SQLite chứa bảng`customers`, tự tạo khi chạy server lần đầu.                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `README.md`               | Tài liệu riêng cho server: cài đặt, schema DB, API, cơ chế an toàn khi ghi đồng thời, giới hạn hiện tại.                                                                                                                                                                                                                                                                                                                                                                                                                    |

## Trạng thái (cập nhật 2026-07-25)

**Đã xong:**

- Phát hiện tin mới theo 2 lớp (id hội thoại + vị trí đầu danh sách, xem mục
  "Cách hoạt động") + quét dự phòng mỗi 3 giây kể cả khi không có mutation,
  để bắt được cả lúc để im màn hình.
- **Chủ trương hiện tại: ưu tiên bắt được nhiều tin nhất, chấp nhận có thể lẫn
  cả hội thoại cũ khi cuộn tay xuống xem lịch sử** (đã thử phiên bản chặt chẽ
  hơn — chỉ báo khi chắc chắn ở đỉnh danh sách hoặc hội thoại đã có lịch sử —
  nhưng bị bỏ sót quá nhiều nên quay lại kiểu báo rộng rãi này theo yêu cầu).
  Có log `[debug] items=... nearTop=... suppressNew=... newEvents=...` ở mỗi
  lượt quét trong Console để dễ dò khi cần.
- Nút "Cập nhật" (tự cuộn quét toàn bộ danh sách) — luôn tự chạy 1 lượt ngay
  khi mở trang (không có tuỳ chọn tắt) — bắt tin nhắn đến trong lúc không mở
  tab.
- **Panel nổi ngay trên trang pancake.vn** (`panel.js`) — kéo thả di chuyển tự
  do, bấm nút thu gọn/mở rộng, nhớ vị trí + trạng thái thu gọn qua
  `chrome.storage.local` (key `pancake_panel_state`). Dùng Shadow DOM nên CSS
  của Pancake và của panel không đụng nhau. Dùng chung dữ liệu với popup — 2
  giao diện luôn đồng bộ real-time qua `chrome.storage.onChanged`. Popup ở
  icon extension vẫn giữ nguyên làm phương án dự phòng (vì popup gốc của
  Chrome **không kéo thả được** — giới hạn cứng của trình duyệt, không phải
  do code). Đã bỏ nút "Đánh dấu tất cả đã xem" và "Xuất log (JSON)" ở cả 2
  giao diện (không dùng tới) — muốn đánh dấu đã xem thì bấm trực tiếp vào
  từng dòng.
- Tự phát hiện và dừng gọn khi extension bị reload trong lúc tab đang mở
  (lỗi "Extension context invalidated") — log 1 dòng nhắc F5 lại tab thay vì
  báo lỗi liên tục.
- **Server local (`ZPancake/server/`, FastAPI + SQLite)** — mỗi sự kiện tin
  nhắn mới đều được `background.js` bắn (best-effort, `fetch`) sang
  `http://localhost:8787/api/messages`, server lưu vào `data/pancake_watcher.db`
  (bảng `customers` duy nhất, mỗi khách 1 dòng chứa tin nhắn cuối cùng gửi
  đến). Độc lập hoàn toàn với backend chính `app/` ở gốc repo — không dùng
  chung DB, không gọi API Pancake nào, chỉ dùng đúng dữ liệu extension tự
  quét được từ DOM. **Mỗi dòng tin nhắn trong popup/panel hiện luôn trạng
  thái gửi server** (☁️✓ đã lưu / ☁️✗ chưa gửi được — server có đang chạy
  không / ☁️… đang gửi) để bạn quan sát trực tiếp, không cần mở DB xem.
- **An toàn khi nhiều tin đến dồn dập**: `background.js` gộp các tin đang chờ
  theo hội thoại (không tạo nhiều request nhỏ), server dùng upsert nguyên tử +
  SQLite WAL mode. Đã kiểm thử 60 lượt ghi đồng thời (kể cả cùng 1 hội thoại)
  → 0 lỗi. Xem chi tiết ở `server/README.md`.
- **Quét cảm xúc tiêu cực** (`server/sentiment.py`) — chạy **nền, tách hẳn
  khỏi lúc lưu tin** (không làm chậm việc lưu/ping của extension): mỗi ~8s,
  server tự quét các hội thoại có snippet mới chưa được chấm cảm xúc. 2 cách,
  đổi qua biến `SENTIMENT_METHOD` trong `server/.env` (copy từ
  `.env.example`): `keyword` (mặc định, offline, khớp từ khoá tiếng Việt) hoặc
  `llm` (gọi OpenAI, chính xác hơn, cần `OPENAI_API_KEY` riêng + tốn phí nhỏ).
  Extension poll kết quả mỗi phút (`chrome.alarms`) — hội thoại "negative"
  hiện viền đỏ + nhãn "⚠️ Tiêu cực" ngay trên popup/panel.
- **Thông báo Telegram khi phát hiện tiêu cực** (`server/telegram.py`) — mỗi
  khi worker cảm xúc chấm 1 khách "negative", server tự gửi tin nhắn (tên
  khách, nền tảng, snippet) qua Telegram Bot API. Tuỳ chọn — cấu hình
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` trong `server/.env` (hướng dẫn lấy 2
  giá trị này ở `.env.example` và `server/README.md`), thiếu thì tự bỏ qua,
  không gửi và không lỗi.
- **GUI desktop quản lý server** (`server/gui.py`, tkinter) — bật/tắt server,
  hiện 🟢/🔴 trạng thái đang chạy hay không (tự kiểm tra `/health` mỗi 2s), và
  chỉnh cách quét cảm xúc + OpenAI API Key ngay trên giao diện (ghi vào
  `.env`, tự khởi động lại server nếu đang chạy để áp dụng ngay). Có nút
  **"🔔 Kiểm tra kết nối Telegram..."** để gửi thử 1 tin nhắn xác nhận setup.
  Đã tạo sẵn shortcut **"Pancake Watcher"** trên Desktop để mở nhanh.

**Việc tiếp theo:**

1. Double-click shortcut "Pancake Watcher" trên Desktop (hoặc chạy
   `ZPancake/server/gui.py`) rồi thử trên trang thật xem tin nhắn có ghi đúng
   vào SQLite không.
2. Nếu muốn dùng cách quét cảm xúc bằng LLM: mở GUI, chọn "llm" + điền OpenAI
   API Key, bấm "Lưu cài đặt". Hoặc chỉnh tay:

   ```bash
   cp server/.env.example server/.env
   ```

   rồi đổi `SENTIMENT_METHOD=llm` + điền `OPENAI_API_KEY` trong file đó.
3. Thử kéo thả + thu gọn panel nổi trên trang thật, kiểm tra panel không bị
   che khuất bởi UI của Pancake (z-index) và ngược lại.
4. Thử nút "Cập nhật" trên trang thật (đóng tab vài tiếng, mở lại, bấm Cập
   nhật, xem có bắt đúng các hội thoại có tin đến trong lúc vắng mặt không).
5. Xử lý các mục ở phần "Giới hạn hiện tại" bên dưới — tuỳ độ ưu tiên.
6. Extension hiện chưa có icon riêng (dùng icon mặc định của Chrome).

## Cài đặt (chế độ unpacked, để dev)

1. Mở `chrome://extensions`.
2. Bật **Chế độ nhà phát triển** (Developer mode) ở góc trên phải.
3. Bấm **Tải tiện ích đã giải nén** (Load unpacked) → chọn thư mục `ZPancake/`.
4. Mở `https://pancake.vn/` và đăng nhập, để trang hiển thị danh sách hội thoại.

**Lưu ý khi dev:** mỗi lần sửa code rồi bấm reload extension ở
`chrome://extensions`, phải **F5 lại tab pancake.vn đang mở** — nếu không,
script cũ trong tab đó mất kết nối tới extension và sẽ báo lỗi
`Extension context invalidated` (không phải bug, xem mục "Cách hoạt động").

## Cách hoạt động

### Phát hiện tin nhắn mới

`content.js` gắn `MutationObserver` vào div danh sách, và **đồng thời quét
định kỳ mỗi 3 giây bất kể có mutation hay không** (dự phòng), rồi so sánh với
snapshot cũ theo 2 lớp:

1. **Theo id hội thoại** — báo khi 1 hội thoại đã biết mà nội dung/số chưa
   đọc đổi khác, **hoặc** hội thoại chưa từng thấy id nhưng đang có tín hiệu
   chưa đọc (kể cả khi đó chỉ là hội thoại cũ vừa cuộn tới lần đầu trong
   phiên này — chấp nhận báo lẫn để không bỏ sót tin thật).
2. **Theo vị trí ở đầu danh sách** (bỏ mục ghim) — vì Pancake luôn đẩy hội
   thoại vừa có tin mới lên đầu (kể cả không cuộn/thao tác gì, virtual list
   tái dùng luôn node đang render để hiện hội thoại mới), lớp này so sánh nội
   dung ở từng vị trí trong 5 vị trí đầu, không quan tâm trước đó id nào từng
   đứng ở đó. Chạy bất kể đang cuộn ở đâu.

Chỉ chặn báo backlog khi **thật sự là lần cài đặt đầu tiên** (chưa từng lưu
lịch sử gì) — không phải mỗi lần mở trang — để lần mở lại sau khi đóng tab
lâu vẫn bắt được tin đến trong lúc vắng mặt ngay từ lượt quét đầu tiên.

Từ id hội thoại (`pzl_g_<page>_<conv>`, `pzl_u_<page>_<conv>` cho Zalo,
`<page>_<conv>` cho Facebook) suy ra được `platform`, `pageId`, `convId`.

### Nút "Cập nhật" (bắt tin đến trong lúc đóng tab)

Vì Pancake chỉ render những hội thoại đang trong khung nhìn, hội thoại có tin
mới nhưng nằm ngoài màn hình lúc vừa mở trang sẽ chưa được quét tới. Nút
**"Cập nhật"** trong popup gửi message tới content script (`chrome.tabs.query`
tìm tab pancake.vn đang mở + `chrome.tabs.sendMessage`), content script sẽ:
tự cuộn khung danh sách (`.rc-virtual-list-holder`) theo từng bước lớn từ đầu
xuống cuối, dừng ~220ms mỗi bước để React kịp render rồi quét-so sánh ngay,
sau đó cuộn trả lại đúng vị trí ban đầu. Việc này **luôn tự chạy 1 lượt ngay
sau khi mở trang** (không cần bấm tay, và không có tuỳ chọn tắt) — đảm bảo
luôn bắt được tin đến trong lúc tab đóng ngay từ lúc mở lại trang.

### Lưu trữ & hiển thị

Khi phát hiện thay đổi → gửi sự kiện cho `background.js`, log ra console.
`background.js` lưu vào `chrome.storage.local` dưới dạng
`{ [id hội thoại]: {...} }` (key `pancake_events`) — **mỗi hội thoại 1 bản
ghi**, tin mới tới thì đè lên bản ghi cũ (không cộng dồn thành nhiều dòng
trùng), giữ tối đa 300 hội thoại gần hoạt động nhất; đồng thời cập nhật số
đếm trên icon.

Cả **panel nổi** (`panel.js`, chèn trực tiếp vào trang pancake.vn) và
**popup** (`popup.html/js`, mở từ icon extension) đều đọc/ghi cùng key
`pancake_events`/`pancake_settings`/`pancake_sweep_status`, và cùng lắng nghe
`chrome.storage.onChanged` — nên mở đồng thời cả 2 vẫn luôn khớp dữ liệu,
không cần đóng/mở lại. Cả hai đều sắp theo `lastDetectedAt` giảm dần (hội
thoại vừa có tin mới nhất nổi lên đầu, giống Pancake), bấm 1 dòng để đánh dấu
đã xem, có nút **Xuất log (JSON)** để tải file log về máy.

Panel nổi kéo thả bằng cách rê thanh tiêu đề (nút thu gọn ở góc phải không
kích hoạt kéo); vị trí cuối cùng (`x`, `y`) và trạng thái thu gọn được lưu ở
key `pancake_panel_state`, tự áp dụng lại mỗi lần vào trang.

### Server local (SQLite)

Ngoài lưu vào `chrome.storage.local`, mỗi khi `background.js` nhận sự kiện
tin mới, nó **đồng thời** gọi `fetch()` (best-effort, không chặn luồng cũ)
sang `http://localhost:8787/api/messages` — endpoint của server FastAPI chạy
ở `ZPancake/server/`. Server upsert vào bảng `customers` (1 dòng/hội thoại)
và insert 1 dòng log vào bảng `messages`, cả 2 nằm trong file SQLite
`server/data/pancake_watcher.db`. Nếu server chưa chạy, extension vẫn hoạt
động bình thường — chỉ log 1 dòng cảnh báo (không lặp lại liên tục) mỗi lần
gửi thất bại. Chi tiết schema/API/cách chạy: xem `server/README.md`.

## Xem log kỹ hơn khi debug

- Log của content script: mở DevTools ngay trên tab `pancake.vn` (F12) →
  tab Console, tìm dòng bắt đầu bằng `[Pancake Watcher]`.
- Log của background service worker: vào `chrome://extensions` → tìm
  extension này → bấm **service worker** để mở DevTools riêng của nó.
- Dòng `This script is on the debugger's ignore list` cạnh 1 frame trong
  stack trace **không phải lỗi** — chỉ là nhãn của DevTools báo script đó bị
  bỏ qua khi step-through. Muốn debug được thì vào tab Sources → chuột phải
  file đó → "Remove from ignore list".

## Giới hạn hiện tại / việc để phát triển sau

- Chưa lấy được nội dung tin nhắn đầy đủ, chỉ có đoạn snippet rút gọn hiển
  thị trong danh sách.
- Chưa tự mở/điều hướng tới đúng hội thoại khi bấm vào 1 dòng (cả popup lẫn
  panel nổi).
- Nút "Cập nhật" ở popup gửi lệnh tới **tab pancake.vn đầu tiên** tìm thấy
  nếu bạn mở nhiều tab cùng lúc (bấm ngay trên panel nổi thì luôn đúng tab vì
  panel nằm sẵn trong tab đó).
- Panel nổi chỉ giới hạn kéo trong phạm vi khung nhìn hiện tại — nếu thu nhỏ
  cửa sổ trình duyệt sau khi đã kéo panel ra ngoài vùng mới, panel có thể bị
  che khuất tới khi kéo lại (chưa tự căn lại vị trí khi resize cửa sổ).
- Server local (`ZPancake/server/`) chưa có auth, chỉ nên chạy trên máy cá
  nhân; chưa có giao diện xem dữ liệu (dùng DB Browser for SQLite).
- Vẫn hoàn toàn độc lập với `app/` ở thư mục gốc repo — server local của
  ZPancake dùng SQLite riêng, không đụng tới Supabase/access token của `app/`.
- Nếu Pancake đổi cấu trúc HTML (tên class `snippet-text`, `time-modul`,
  `ant-badge-count`, `name-text`, id `conversationList`...) thì cần cập nhật
  lại selector trong `content.js`.
