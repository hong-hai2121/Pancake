const EVENTS_KEY = "pancake_events";

function fmtPlatform(cls) {
  if (!cls) return "";
  if (cls.includes("facebook")) return "Facebook";
  if (cls.includes("zalo")) return "Zalo";
  return cls.replace("platform-", "");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

// Sắp xếp giống Pancake: hội thoại vừa có tin mới nhất luôn ở trên đầu.
function toSortedArray(store) {
  return Object.values(store).sort((a, b) =>
    a.lastDetectedAt < b.lastDetectedAt ? 1 : a.lastDetectedAt > b.lastDetectedAt ? -1 : 0
  );
}

function render(store) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  const items = toSortedArray(store);

  if (!items.length) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  list.innerHTML = "";
  items.forEach((ev) => {
    const li = document.createElement("li");
    li.className = "item" + (ev.read ? " read" : "") + " enter";
    li.innerHTML = `
      <div class="row1">
        <span class="name">${escapeHtml(ev.name || ev.rawId)}</span>
        <span class="time">${escapeHtml(ev.time)}</span>
      </div>
      <div class="snippet">${escapeHtml(ev.snippet)}</div>
      <div class="meta">
        <span class="platform">${escapeHtml(fmtPlatform(ev.platformClass))}</span>
        <span class="page">page: ${escapeHtml(ev.pageId)}</span>
        ${ev.unreadCount > 0 ? `<span class="badge-count">${ev.unreadCount}</span>` : ""}
        ${ev.hitCount > 1 ? `<span class="hit-count">x${ev.hitCount}</span>` : ""}
      </div>
    `;
    li.addEventListener("click", () => markRead(ev.rawId));
    list.appendChild(li);
  });
  // bỏ class "enter" ở frame kế tiếp để trigger transition fade/slide-in mượt.
  requestAnimationFrame(() => {
    list.querySelectorAll(".item.enter").forEach((el) => el.classList.remove("enter"));
  });
}

function load() {
  chrome.storage.local.get(EVENTS_KEY, (res) => render(res[EVENTS_KEY] || {}));
}

function updateBadgeFromStore(store) {
  const unread = Object.values(store).filter((e) => !e.read).length;
  chrome.action.setBadgeText({ text: unread > 0 ? String(unread) : "" });
}

function markRead(rawId) {
  chrome.storage.local.get(EVENTS_KEY, (res) => {
    const store = res[EVENTS_KEY] || {};
    if (store[rawId]) store[rawId].read = true;
    chrome.storage.local.set({ [EVENTS_KEY]: store }, () => {
      render(store);
      updateBadgeFromStore(store);
    });
  });
}

function markAllRead() {
  chrome.storage.local.get(EVENTS_KEY, (res) => {
    const store = res[EVENTS_KEY] || {};
    Object.values(store).forEach((e) => (e.read = true));
    chrome.storage.local.set({ [EVENTS_KEY]: store }, () => {
      render(store);
      updateBadgeFromStore(store);
    });
  });
}

function exportLog() {
  chrome.storage.local.get(EVENTS_KEY, (res) => {
    const items = toSortedArray(res[EVENTS_KEY] || {});
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pancake-messages-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
}

document.getElementById("markAllBtn").addEventListener("click", markAllRead);
document.getElementById("exportBtn").addEventListener("click", exportLog);

// Popup đang mở mà có tin mới tới thì tự render lại ngay, không cần đóng mở lại.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[EVENTS_KEY]) {
    render(changes[EVENTS_KEY].newValue || {});
  }
});

load();
