const EVENTS_KEY = "pancake_events";
const SETTINGS_KEY = "pancake_settings";
const SWEEP_STATUS_KEY = "pancake_sweep_status";

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

// Trạng thái đã gửi (POST) sang server local (ZPancake/server) để lưu SQLite
// chưa — do background.js ghi lại sau mỗi lần fetch xong.
function fmtServerStatus(status) {
  if (status === "sent") return '<span class="server-status sent" title="Đã lưu vào server">☁️✓</span>';
  if (status === "failed") return '<span class="server-status failed" title="Chưa gửi được tới server (server có đang chạy không?)">☁️✗</span>';
  return '<span class="server-status pending" title="Đang gửi tới server...">☁️…</span>';
}

// Cảnh báo hội thoại có dấu hiệu tiêu cực (do server quét nền, gán vào
// ev.sentiment qua background.js pollSentiment()).
function isNegative(ev) {
  return ev.sentiment === "negative";
}

// Sắp xếp giống Pancake: hội thoại vừa có tin mới nhất luôn ở trên đầu.
function toSortedArray(store) {
  return Object.values(store).sort((a, b) =>
    a.lastDetectedAt < b.lastDetectedAt ? 1 : a.lastDetectedAt > b.lastDetectedAt ? -1 : 0
  );
}

// Nhớ id đang đứng đầu ở lần vẽ trước, để phát hiện khi có hội thoại MỚI nhảy
// lên đầu (khác id cũ) — dòng đó sẽ được nhấp nháy vàng để dễ nhận ra bằng mắt.
let lastTopId = null;

function render(store) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  const items = toSortedArray(store);

  if (!items.length) {
    list.innerHTML = "";
    empty.hidden = false;
    lastTopId = null;
    return;
  }
  empty.hidden = true;

  const newTopId = items[0].rawId;
  const topChanged = newTopId !== lastTopId;
  lastTopId = newTopId;

  list.innerHTML = "";
  items.forEach((ev, idx) => {
    const li = document.createElement("li");
    li.className =
      "item" +
      (ev.read ? " read" : "") +
      " enter" +
      (idx === 0 && topChanged ? " just-arrived" : "") +
      (isNegative(ev) ? " negative" : "");
    li.innerHTML = `
      <div class="row1">
        <span class="name">${escapeHtml(ev.name || ev.rawId)}</span>
        <span class="time">${escapeHtml(ev.time)}</span>
      </div>
      <div class="snippet">${escapeHtml(ev.snippet)}</div>
      <div class="meta">
        ${isNegative(ev) ? '<span class="sentiment-warn" title="Có dấu hiệu tiêu cực về dịch vụ">⚠️ Tiêu cực</span>' : ""}
        <span class="platform">${escapeHtml(fmtPlatform(ev.platformClass))}</span>
        <span class="page">page: ${escapeHtml(ev.pageId)}</span>
        ${ev.hitCount > 1 ? `<span class="hit-count">x${ev.hitCount}</span>` : ""}
        ${fmtServerStatus(ev.serverStatus)}
        ${ev.unreadCount > 0 ? `<span class="badge-count">${ev.unreadCount}</span>` : ""}
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

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function renderSweepStatus(status) {
  const el = document.getElementById("sweepStatus");
  const btn = document.getElementById("sweepBtn");
  if (!status) {
    el.textContent = "";
    btn.disabled = false;
    return;
  }
  if (status.running) {
    el.textContent = "Đang cập nhật (đang cuộn quét toàn bộ danh sách)...";
    btn.disabled = true;
  } else if (status.finishedAt) {
    el.textContent = `Đã cập nhật xong lúc ${fmtTime(status.finishedAt)} (${status.steps || 0} bước cuộn).`;
    btn.disabled = false;
  } else {
    el.textContent = "";
    btn.disabled = false;
  }
}

// Gửi lệnh cập nhật xuống content script trên tab pancake.vn đang mở. Nếu có
// nhiều tab pancake.vn, tạm chọn tab đầu tiên tìm thấy (đủ dùng cho v1).
function triggerSweep() {
  chrome.tabs.query({ url: "https://pancake.vn/*" }, (tabs) => {
    if (!tabs || !tabs.length) {
      document.getElementById("sweepStatus").textContent =
        "Chưa thấy tab pancake.vn nào đang mở — mở trang đó trước rồi bấm lại.";
      return;
    }
    chrome.tabs.sendMessage(tabs[0].id, { type: "PANCAKE_TRIGGER_SWEEP" });
  });
}

function applyEnabled(enabled) {
  document.getElementById("enabledToggle").checked = enabled;
  document.getElementById("enabledLabel").textContent = enabled ? "Đang bật" : "Đang tắt";
}

function loadSettings() {
  chrome.storage.local.get(SETTINGS_KEY, (res) => {
    const settings = res[SETTINGS_KEY] || {};
    document.getElementById("autoSweepToggle").checked = !!settings.autoSweepOnLoad;
    applyEnabled(settings.enabled !== false);
  });
  chrome.storage.local.get(SWEEP_STATUS_KEY, (res) => renderSweepStatus(res[SWEEP_STATUS_KEY]));
}

document.getElementById("sweepBtn").addEventListener("click", triggerSweep);
document.getElementById("autoSweepToggle").addEventListener("change", (e) => {
  chrome.storage.local.get(SETTINGS_KEY, (res) => {
    const settings = res[SETTINGS_KEY] || {};
    settings.autoSweepOnLoad = e.target.checked;
    chrome.storage.local.set({ [SETTINGS_KEY]: settings });
  });
});
// Công tắc tổng — tắt thì content.js dừng quét ngay (áp dụng qua storage.onChanged
// bên content.js/panel.js, không cần F5 lại trang pancake.vn).
document.getElementById("enabledToggle").addEventListener("change", (e) => {
  chrome.storage.local.get(SETTINGS_KEY, (res) => {
    const settings = res[SETTINGS_KEY] || {};
    settings.enabled = e.target.checked;
    chrome.storage.local.set({ [SETTINGS_KEY]: settings });
  });
});

// Popup đang mở mà có tin mới tới / trạng thái cập nhật đổi thì tự render lại
// ngay, không cần đóng mở lại.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[EVENTS_KEY]) {
    render(changes[EVENTS_KEY].newValue || {});
  }
  if (changes[SWEEP_STATUS_KEY]) {
    renderSweepStatus(changes[SWEEP_STATUS_KEY].newValue);
  }
  if (changes[SETTINGS_KEY]) {
    applyEnabled((changes[SETTINGS_KEY].newValue || {}).enabled !== false);
  }
});

load();
loadSettings();
