// Nhận sự kiện tin nhắn mới từ content script.
//
// Lưu theo dạng { [rawId]: {...} } — MỖI HỘI THOẠI 1 BẢN GHI, cập nhật đè lên
// bản cũ và nhảy lên đầu (sort theo lastDetectedAt lúc render), giống đúng cách
// Pancake tự đẩy hội thoại vừa có tin mới lên đầu danh sách. Tránh cộng dồn
// thành nhiều dòng trùng lặp cho cùng 1 hội thoại mỗi lần có tin.

const EVENTS_KEY = "pancake_events";
const MAX_CONVERSATIONS = 300;
const LOCAL_SERVER_URL = "http://localhost:8787/api/messages";
const SENTIMENT_URL = "http://localhost:8787/api/sentiment";
const SENTIMENT_ALARM_NAME = "pancake_sentiment_poll";

let localServerWarned = false;

// Hàng đợi gửi sang server local — gộp theo rawId (Map) thay vì mảng các đợt
// riêng lẻ. Trong lúc đang gửi 1 đợt (hoặc đang chờ giữa các lần thử lại), tin
// mới đến sẽ được GỘP THẲNG vào đợi tiếp theo (ghi đè nếu trùng rawId, vì chỉ
// cần bản mới nhất) thay vì xếp thành 1 request riêng — gửi xong đợt hiện tại
// là gom hết những gì vừa tích luỹ được thành 1 request duy nhất, ít request
// hơn hẳn so với gửi từng đợt một lúc bấm "Cập nhật" (sweep quét dồn dập).
const pendingEvents = new Map(); // rawId -> event mới nhất chưa gửi
let sendingInProgress = false;
const MAX_SEND_ATTEMPTS = 3;

// Trần số event rút ra khỏi hàng đợi cho MỖI request — phòng trường hợp dội
// tin quá nhiều cùng lúc (vd lần đầu cài, hoặc cuộn nhanh qua hàng trăm hội
// thoại) khiến 1 request duy nhất phải cõng hết cả pendingEvents. Phần vượt
// trần vẫn nằm nguyên trong hàng đợi, được gửi tiếp ở (các) đợt kế — không
// gửi lại thứ vừa gửi, không mất tin, chỉ rải nhỏ ra thành nhiều request hơn.
const MAX_EVENTS_PER_REQUEST = 50;
const CHUNK_GAP_MS = 250; // nghỉ giữa 2 request liên tiếp khi hàng đợi còn dư, tránh dồn dập server local

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Cập nhật trạng thái gửi server (serverStatus) cho từng rawId, để popup/panel
// hiển thị cho người dùng biết tin đã lưu vào SQLite chưa hay server đang tắt.
function updateServerStatus(rawIds, status) {
  chrome.storage.local.get(EVENTS_KEY, (res) => {
    const store = res[EVENTS_KEY] || {};
    let changed = false;
    rawIds.forEach((id) => {
      if (store[id]) {
        store[id].serverStatus = status; // "sending" | "sent" | "failed"
        store[id].serverStatusAt = new Date().toISOString();
        changed = true;
      }
    });
    if (changed) chrome.storage.local.set({ [EVENTS_KEY]: store });
  });
}

async function sendWithRetry(events, attempt = 1) {
  const rawIds = events.map((e) => e.rawId);
  try {
    const res = await fetch(LOCAL_SERVER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    localServerWarned = false;
    updateServerStatus(rawIds, "sent");
  } catch (err) {
    if (attempt < MAX_SEND_ATTEMPTS) {
      await wait(attempt * 600); // chờ tăng dần giữa các lần thử (600ms, 1200ms...)
      return sendWithRetry(events, attempt + 1);
    }
    if (!localServerWarned) {
      console.log(
        "[Pancake Watcher][background] Không gửi được tới server local " +
          `(${LOCAL_SERVER_URL}) sau ${MAX_SEND_ATTEMPTS} lần thử — có thể server chưa ` +
          "chạy. Sẽ không log lại lỗi này liên tục, chỉ log 1 lần cho tới khi gửi " +
          "thành công trở lại.",
        err
      );
      localServerWarned = true;
    }
    updateServerStatus(rawIds, "failed");
  }
}

async function processSendQueue() {
  if (sendingInProgress) return;
  if (pendingEvents.size === 0) return;
  sendingInProgress = true;

  // Chỉ rút tối đa MAX_EVENTS_PER_REQUEST mục rồi xoá đúng những mục đó khỏi
  // hàng đợi NGAY — để bất kỳ tin nào đến trong lúc fetch() này đang chạy sẽ
  // gộp vào đợt KẾ TIẾP, không lẫn vào đợt đang gửi dở. Phần còn dư (nếu hàng
  // đợi lớn hơn trần) vẫn nằm trong pendingEvents, gửi tiếp ở đợt sau.
  const keys = Array.from(pendingEvents.keys()).slice(0, MAX_EVENTS_PER_REQUEST);
  const batch = keys.map((k) => pendingEvents.get(k));
  keys.forEach((k) => pendingEvents.delete(k));

  await sendWithRetry(batch);

  const hasMore = pendingEvents.size > 0;
  sendingInProgress = false;
  if (!hasMore) return;

  if (batch.length >= MAX_EVENTS_PER_REQUEST) {
    console.log(
      `[Pancake Watcher][background] Hàng đợi còn ${pendingEvents.size} sự kiện sau khi gửi ` +
        `${batch.length} — nghỉ ${CHUNK_GAP_MS}ms rồi gửi tiếp đợt kế.`
    );
    await wait(CHUNK_GAP_MS);
  }
  // Trong lúc gửi đợt vừa rồi, nếu có tin mới tích luỹ thêm thì gửi tiếp luôn.
  processSendQueue();
}

// Bắn dữ liệu sang server Python chạy ở máy (ZPancake/server) để lưu SQLite.
// Best-effort: server có thể chưa bật, không được để lỗi này làm hỏng luồng
// lưu chrome.storage.local (vẫn phải chạy dù server local có sống hay không).
function forwardToLocalServer(events) {
  events.forEach((ev) => pendingEvents.set(ev.rawId, ev));
  processSendQueue();
}

// Snippet "[Botcake] ..." là tin PAGE tự động gửi ra (kịch bản chatbot), không
// phải tin của khách — không gửi lên server (server chỉ cần lưu tin khách gửi
// tới; snippet dạng này lỡ ghi đè vào bản ghi khách sẽ làm sai "tin cuối cùng"
// hiển thị ở /history + quét cảm xúc nhầm nội dung page tự nói). Vẫn giữ
// nguyên hiển thị ở popup/panel — chỉ chặn đúng phần gửi server.
const PAGE_MESSAGE_MARKERS = ["[botcake]"];

function isPageMessage(ev) {
  const text = (ev.snippet || "").toLowerCase();
  return PAGE_MESSAGE_MARKERS.some((marker) => text.includes(marker));
}

function updateBadge(store) {
  const unread = Object.values(store).filter((e) => !e.read).length;
  chrome.action.setBadgeText({ text: unread > 0 ? String(unread) : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#e2474f" });
}

function capByRecency(store, max) {
  const keys = Object.keys(store);
  if (keys.length <= max) return store;
  const kept = keys
    .sort((a, b) => (store[a].lastDetectedAt < store[b].lastDetectedAt ? 1 : -1))
    .slice(0, max);
  const result = {};
  kept.forEach((k) => (result[k] = store[k]));
  return result;
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "PANCAKE_NEW_MESSAGE") return;
  const events = message.events || [];
  if (!events.length) return;

  console.log("[Pancake Watcher][background] Nhận", events.length, "sự kiện tin nhắn mới:", events);

  const serverEvents = events.filter((ev) => !isPageMessage(ev));
  if (serverEvents.length) forwardToLocalServer(serverEvents);

  chrome.storage.local.get(EVENTS_KEY, (res) => {
    const store = res[EVENTS_KEY] || {};
    events.forEach((ev) => {
      const prev = store[ev.rawId];
      store[ev.rawId] = {
        ...ev,
        read: false, // có tin mới -> luôn đưa về chưa đọc, kể cả trước đó đã đánh dấu đã xem
        firstDetectedAt: prev ? prev.firstDetectedAt : ev.detectedAt,
        lastDetectedAt: ev.detectedAt,
        hitCount: (prev?.hitCount || 0) + 1,
        serverStatus: "sending", // updateServerStatus() sẽ ghi đè thành sent/failed ngay sau
      };
    });
    const capped = capByRecency(store, MAX_CONVERSATIONS);
    chrome.storage.local.set({ [EVENTS_KEY]: capped }, () => updateBadge(capped));
  });
});

// Lấy kết quả quét cảm xúc (server chạy nền, xem ZPancake/server/main.py) và
// gộp vào danh sách đang hiển thị — popup/panel sẽ tự vẽ lại (storage.onChanged)
// để hiện cảnh báo cho hội thoại có dấu hiệu tiêu cực, không cần thao tác gì thêm.
function pollSentiment() {
  fetch(SENTIMENT_URL)
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then((data) => {
      const items = data.items || [];
      if (!items.length) return;
      chrome.storage.local.get(EVENTS_KEY, (res) => {
        const store = res[EVENTS_KEY] || {};
        let changed = false;
        items.forEach((item) => {
          const ev = store[item.rawId];
          if (ev && ev.sentiment !== item.sentiment) {
            ev.sentiment = item.sentiment;
            ev.sentimentMethod = item.sentimentMethod;
            changed = true;
          }
        });
        if (changed) chrome.storage.local.set({ [EVENTS_KEY]: store });
      });
    })
    .catch(() => {
      // Best-effort — server có thể chưa bật, đã có log riêng ở forwardToLocalServer
      // rồi nên không log lại nữa ở đây để tránh trùng lặp.
    });
}

// chrome.alarms thay vì setInterval — service worker MV3 có thể bị tạm ngưng,
// setInterval sẽ mất theo, còn alarms được Chrome tự đánh thức lại đúng giờ.
// 1 phút là chu kỳ tối thiểu Chrome cho phép với alarm lặp lại.
chrome.alarms.create(SENTIMENT_ALARM_NAME, { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SENTIMENT_ALARM_NAME) pollSentiment();
});
pollSentiment(); // gọi ngay lúc service worker khởi động, không cần chờ đủ 1 phút đầu

chrome.storage.local.get(EVENTS_KEY, (res) => updateBadge(res[EVENTS_KEY] || {}));
