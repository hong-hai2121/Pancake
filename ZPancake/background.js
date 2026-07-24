// Nhận sự kiện tin nhắn mới từ content script.
//
// Lưu theo dạng { [rawId]: {...} } — MỖI HỘI THOẠI 1 BẢN GHI, cập nhật đè lên
// bản cũ và nhảy lên đầu (sort theo lastDetectedAt lúc render), giống đúng cách
// Pancake tự đẩy hội thoại vừa có tin mới lên đầu danh sách. Tránh cộng dồn
// thành nhiều dòng trùng lặp cho cùng 1 hội thoại mỗi lần có tin.

const EVENTS_KEY = "pancake_events";
const MAX_CONVERSATIONS = 300;

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
      };
    });
    const capped = capByRecency(store, MAX_CONVERSATIONS);
    chrome.storage.local.set({ [EVENTS_KEY]: capped }, () => updateBadge(capped));
  });
});

chrome.storage.local.get(EVENTS_KEY, (res) => updateBadge(res[EVENTS_KEY] || {}));
