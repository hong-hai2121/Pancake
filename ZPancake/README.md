# Pancake New Message Watcher

Extension Chrome (Manifest V3) theo dõi div danh sách hội thoại trên
`pancake.vn` (`#conversationList .rc-virtual-list-holder-inner`) để phát hiện
khi có tin nhắn mới, hiện tại **chỉ log lại để xem** — chưa gọi ra hệ thống
nào khác.

## Trạng thái (cập nhật 2026-07-24)

**Đã xong:**
- `manifest.json`, `content.js`, `background.js`, `popup.*` — đủ chạy được ở
  chế độ unpacked.
- Phát hiện tin mới theo 2 lớp (id hội thoại + vị trí đầu danh sách, xem mục
  "Cách hoạt động" bên dưới) + quét dự phòng mỗi 3 giây kể cả khi không có
  mutation, để bắt được cả trường hợp để im màn hình không cuộn/thao tác gì.
- Popup: 1 hội thoại/dòng (không trùng lặp), tự nổi lên đầu khi có tin mới,
  tự vẽ lại khi đang mở, đánh dấu đã xem, xuất log JSON.

**Việc tiếp theo (mai làm):**
1. **Xác nhận lại trên trang thật** — để tab pancake.vn im, chờ có tin nhắn
   khách hàng thật tới, xem trong ~3 giây console có log
   `[Pancake Watcher] Phát hiện N hội thoại có tin mới` không. Nếu vẫn không
   thấy: kiểm tra trước đó có log `Đã nạp baseline...` (xác nhận selector
   đúng `#conversationList`) và có dòng `CẢNH BÁO` nào không.
2. Xử lý các mục ở phần "Giới hạn hiện tại" bên dưới (nội dung tin nhắn đầy
   đủ, mở đúng hội thoại khi bấm popup...) — tuỳ độ ưu tiên lúc đó.
3. Extension hiện chưa có icon riêng (dùng icon mặc định của Chrome) — thêm
   sau nếu cần, không ảnh hưởng chức năng.

## Cài đặt (chế độ unpacked, để dev)

1. Mở `chrome://extensions`.
2. Bật **Chế độ nhà phát triển** (Developer mode) ở góc trên phải.
3. Bấm **Tải tiện ích đã giải nén** (Load unpacked) → chọn thư mục `ZPancake/`.
4. Mở `https://pancake.vn/` và đăng nhập, để trang hiển thị danh sách hội thoại.

## Cách hoạt động

- `content.js` gắn `MutationObserver` vào div danh sách, và **đồng thời quét
  định kỳ mỗi 3 giây bất kể có mutation hay không** (dự phòng), rồi so sánh
  với snapshot cũ theo 2 lớp:
  1. **Theo id hội thoại** — bắt tin mới khi 1 hội thoại vẫn hiển thị đúng id
     cũ nhưng nội dung/số chưa đọc đổi.
  2. **Theo vị trí ở đầu danh sách** (bỏ mục ghim) — vì đây là virtual list,
     Pancake **tái dùng luôn node đang render** để hiện hội thoại mới lên đầu
     ngay cả khi không cuộn/thao tác gì (đẩy hội thoại ở cuối khung nhìn ra
     khỏi vùng render); node đó khi ấy mang 1 id không nằm trong lịch sử đã
     biết, nên lớp 1 một mình sẽ bỏ sót — lớp 2 so sánh trực tiếp nội dung ở
     từng vị trí, không quan tâm trước đó id nào từng đứng ở đó.
- Lần quét đầu tiên sau khi mở trang chỉ dùng để lập baseline (không báo toàn
  bộ tin chưa đọc có sẵn là "mới"), để tránh spam log lúc vừa load trang.
- Từ id hội thoại (`pzl_g_<page>_<conv>`, `pzl_u_<page>_<conv>` cho Zalo,
  `<page>_<conv>` cho Facebook) suy ra được `platform`, `pageId`, `convId`.
- Khi phát hiện thay đổi (số tin chưa đọc tăng, snippet đổi, hoặc hội thoại
  mới xuất hiện đang có tín hiệu chưa đọc) → gửi sự kiện cho `background.js`,
  log ra console.
- `background.js` lưu vào `chrome.storage.local` dưới dạng
  `{ [id hội thoại]: {...} }` — **mỗi hội thoại 1 bản ghi**, tin mới tới thì
  đè lên bản ghi cũ (không cộng dồn thành nhiều dòng trùng), giữ tối đa 300
  hội thoại gần hoạt động nhất; đồng thời cập nhật số đếm trên icon.
- Popup sắp xếp theo `lastDetectedAt` giảm dần — hội thoại vừa có tin mới
  nhất luôn nổi lên đầu, giống hệt cách Pancake tự đẩy hội thoại lên đầu
  danh sách — và tự vẽ lại ngay khi có tin mới trong lúc popup đang mở
  (không cần đóng/mở lại). Bấm icon extension để xem, bấm 1 dòng để đánh dấu
  đã xem, hoặc **Xuất log (JSON)** để tải file log về máy.

## Xem log kỹ hơn khi debug

- Log của content script: mở DevTools ngay trên tab `pancake.vn` (F12) →
  tab Console, tìm dòng bắt đầu bằng `[Pancake Watcher]`.
- Log của background service worker: vào `chrome://extensions` → tìm
  extension này → bấm **service worker** để mở DevTools riêng của nó.

## Giới hạn hiện tại / việc để phát triển sau

- Chưa lấy được nội dung tin nhắn đầy đủ, chỉ có đoạn snippet rút gọn hiển
  thị trong danh sách.
- Chưa tự mở/điều hướng tới đúng hội thoại khi bấm vào 1 dòng trong popup.
- Chưa nối với bất kỳ backend/API nào khác — hoàn toàn độc lập trong phạm vi
  trình duyệt (đúng theo yêu cầu: đây là dự án riêng, không liên quan tới
  `app/` ở thư mục gốc repo).
- Nếu Pancake đổi cấu trúc HTML (tên class `snippet-text`, `time-modul`,
  `ant-badge-count`, `name-text`...) thì cần cập nhật lại selector trong
  `content.js`.
