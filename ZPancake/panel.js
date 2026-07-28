// Panel nổi trên trang pancake.vn: hiển thị danh sách tin nhắn mới phát hiện,
// kéo thả di chuyển tự do, thu gọn lại còn thanh tiêu đề. Không tự quét DOM —
// chỉ đọc/ghi chrome.storage.local (cùng nguồn dữ liệu với popup.js), việc quét
// vẫn do content.js đảm nhiệm. Dùng Shadow DOM để CSS của trang Pancake và của
// panel không đụng nhau theo cả 2 chiều.

(function () {
  const EVENTS_KEY = "pancake_events";
  const SETTINGS_KEY = "pancake_settings";
  const SWEEP_STATUS_KEY = "pancake_sweep_status";
  const PANEL_STATE_KEY = "pancake_panel_state"; // { x, y, collapsed }
  const DRAG_THRESHOLD_PX = 3;

  function isExtensionContextValid() {
    return typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.id;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function fmtPlatform(cls) {
    if (!cls) return "";
    if (cls.includes("facebook")) return "Facebook";
    if (cls.includes("zalo")) return "Zalo";
    return cls.replace("platform-", "");
  }

  function fmtTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  }

  // Trạng thái đã gửi (POST) sang server local (ZPancake/server) để lưu SQLite
  // chưa — do background.js ghi lại sau mỗi lần fetch xong.
  function fmtServerStatus(status) {
    if (status === "sent") return '<span class="server-status sent" title="Đã lưu vào server">☁️✓</span>';
    if (status === "failed")
      return '<span class="server-status failed" title="Chưa gửi được tới server (server có đang chạy không?)">☁️✗</span>';
    return '<span class="server-status pending" title="Đang gửi tới server...">☁️…</span>';
  }

  function toSortedArray(store) {
    return Object.values(store).sort((a, b) =>
      a.lastDetectedAt < b.lastDetectedAt ? 1 : a.lastDetectedAt > b.lastDetectedAt ? -1 : 0
    );
  }

  // Cảnh báo hội thoại có dấu hiệu tiêu cực (do server quét nền, gán vào
  // ev.sentiment qua background.js pollSentiment()).
  function isNegative(ev) {
    return ev.sentiment === "negative";
  }

  // ---------------------------------------------------------------- dựng UI

  const host = document.createElement("div");
  host.id = "pancake-watcher-panel-host";
  host.style.position = "fixed";
  host.style.zIndex = "2147483647";
  host.style.right = "20px";
  host.style.bottom = "20px";
  document.documentElement.appendChild(host);

  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      * { box-sizing: border-box; }
      .panel {
        width: 320px;
        font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        background: #fff;
        border-radius: 10px;
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.22);
        overflow: hidden;
        border: 1px solid #e5e7eb;
        color: #1f2937;
      }
      .header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        background: #4338ca;
        color: #fff;
        cursor: move;
        user-select: none;
      }
      .header .title {
        flex: 1;
        font-size: 13px;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .header .badge {
        background: #fff;
        color: #4338ca;
        font-size: 11px;
        font-weight: 700;
        padding: 1px 7px;
        border-radius: 999px;
        min-width: 18px;
        text-align: center;
      }
      .header .badge.zero { display: none; }
      .toggle-btn {
        background: rgba(255, 255, 255, 0.15);
        border: none;
        color: #fff;
        width: 22px;
        height: 22px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 12px;
        line-height: 1;
      }
      .toggle-btn:hover { background: rgba(255, 255, 255, 0.28); }
      .power-btn {
        background: rgba(255, 255, 255, 0.15);
        border: none;
        color: #fff;
        width: 22px;
        height: 22px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 12px;
        line-height: 1;
      }
      .power-btn:hover { background: rgba(255, 255, 255, 0.28); }
      .power-btn.off { background: #ef4444; }
      .body { max-height: 420px; display: flex; flex-direction: column; }
      .off-body { display: none; padding: 18px 12px; text-align: center; }
      .off-msg { font-size: 12px; color: #6b7280; margin: 0; }
      .panel.watcher-off .body { display: none; }
      .panel.watcher-off .off-body { display: block; }
      .panel.collapsed .body,
      .panel.collapsed .off-body { display: none; }
      .actions { display: flex; gap: 6px; padding: 8px 8px 0; }
      button.act {
        flex: 1;
        font-size: 11px;
        padding: 5px 6px;
        border: 1px solid #d1d5db;
        background: #f9fafb;
        border-radius: 6px;
        cursor: pointer;
        color: #1f2937;
      }
      button.act:hover { background: #f3f4f6; }
      button.act:disabled { opacity: 0.5; cursor: default; }
      button.act.primary { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; font-weight: 600; }
      .status { padding: 4px 8px 0; font-size: 10px; color: #6b7280; min-height: 12px; }
      #list { list-style: none; margin: 8px 0 0; padding: 0; overflow-y: auto; }
      .item { padding: 8px 10px; border-top: 1px solid #f1f5f9; cursor: pointer; }
      .item:hover { background: #f8fafc; }
      .item.read { opacity: 0.5; }
      .item:not(.read) { background: #fef6f6; }
      .item.negative { border-left: 4px solid #dc2626; }
      .sentiment-warn { background: #fee2e2; color: #b91c1c; font-weight: 700; padding: 2px 6px; border-radius: 999px; }
      .item.just-arrived { animation: flashNew 1.6s ease-out; }
      @keyframes flashNew {
        0% { background: #fde047; }
        100% { background: transparent; }
      }
      .row1 { display: flex; justify-content: space-between; align-items: baseline; font-weight: 600; font-size: 12px; }
      .row1 .time { font-weight: 400; color: #6b7280; font-size: 10px; }
      .snippet { font-size: 11px; color: #374151; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      /* Hội thoại tiêu cực: hiện đầy đủ nội dung, không cắt "..." như dòng thường. */
      .item.negative .snippet { white-space: normal; overflow: visible; text-overflow: unset; }
      .meta { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 9px; color: #9ca3af; }
      .meta .badge-count { margin-left: auto; background: #e2474f; color: #fff; font-weight: 600; padding: 1px 6px; border-radius: 999px; }
      .server-status { font-size: 10px; cursor: default; }
      .server-status.sent { color: #16a34a; }
      .server-status.failed { color: #ef4444; }
      .server-status.pending { color: #9ca3af; }
      .empty { text-align: center; color: #9ca3af; font-size: 11px; padding: 16px 10px; }
    </style>
    <div class="panel" part="panel">
      <div class="header" id="header">
        <span class="title">🐼 Pancake Watcher</span>
        <span class="badge zero" id="badge">0</span>
        <button class="power-btn" id="powerBtn" data-no-drag title="Tắt theo dõi">⏻</button>
        <button class="toggle-btn" id="toggleBtn" data-no-drag title="Thu gọn/Mở rộng">▾</button>
      </div>
      <div class="body" id="body">
        <div class="actions">
          <button class="act primary" id="sweepBtn">🔄 Cập nhật</button>
        </div>
        <p class="status" id="sweepStatus"></p>
        <ul id="list"></ul>
        <p class="empty" id="empty" hidden>Chưa phát hiện tin nhắn mới nào.</p>
      </div>
      <div class="off-body" id="offBody">
        <p class="off-msg">Đã tắt — không quét tin nhắn mới. Bấm ⏻ ở góc trên để bật lại.</p>
      </div>
    </div>
  `;

  const panelEl = shadow.querySelector(".panel");
  const headerEl = shadow.getElementById("header");
  const toggleBtn = shadow.getElementById("toggleBtn");
  const powerBtn = shadow.getElementById("powerBtn");
  const badgeEl = shadow.getElementById("badge");
  const listEl = shadow.getElementById("list");
  const emptyEl = shadow.getElementById("empty");
  const statusEl = shadow.getElementById("sweepStatus");
  const sweepBtn = shadow.getElementById("sweepBtn");

  // -------------------------------------------------------- vị trí & thu gọn

  function applyPosition(state) {
    if (state && typeof state.x === "number" && typeof state.y === "number") {
      host.style.left = state.x + "px";
      host.style.top = state.y + "px";
      host.style.right = "auto";
      host.style.bottom = "auto";
    } else {
      host.style.right = "20px";
      host.style.bottom = "20px";
      host.style.left = "auto";
      host.style.top = "auto";
    }
  }

  function applyCollapsed(collapsed) {
    panelEl.classList.toggle("collapsed", !!collapsed);
    toggleBtn.textContent = collapsed ? "▸" : "▾";
  }

  // Công tắc tổng: tắt thì content.js dừng quét NGAY (xem storage.onChanged bên
  // content.js), panel chuyển sang hiện trạng thái tắt kèm nút bật lại tại chỗ.
  function applyEnabled(enabled) {
    panelEl.classList.toggle("watcher-off", !enabled);
    powerBtn.classList.toggle("off", !enabled);
    powerBtn.title = enabled ? "Tắt theo dõi" : "Bật theo dõi";
  }

  function setEnabled(enabled) {
    if (!isExtensionContextValid()) return;
    try {
      chrome.storage.local.get(SETTINGS_KEY, (res) => {
        const settings = res[SETTINGS_KEY] || {};
        settings.enabled = enabled;
        chrome.storage.local.set({ [SETTINGS_KEY]: settings });
      });
    } catch (err) {
      // bỏ qua
    }
  }

  function savePanelState(patch) {
    if (!isExtensionContextValid()) return;
    try {
      chrome.storage.local.get(PANEL_STATE_KEY, (res) => {
        const merged = { ...(res[PANEL_STATE_KEY] || {}), ...patch };
        chrome.storage.local.set({ [PANEL_STATE_KEY]: merged });
      });
    } catch (err) {
      // context invalidated giữa chừng — bỏ qua, không có gì để dọn ở panel.
    }
  }

  let panelState = {};
  if (isExtensionContextValid()) {
    try {
      chrome.storage.local.get(PANEL_STATE_KEY, (res) => {
        panelState = res[PANEL_STATE_KEY] || {};
        applyPosition(panelState);
        applyCollapsed(panelState.collapsed);
      });
    } catch (err) {
      applyPosition(null);
    }
  } else {
    applyPosition(null);
  }

  // ------------------------------------------------------------------ kéo thả

  let dragState = null;

  headerEl.addEventListener("mousedown", (e) => {
    if (e.target.closest("[data-no-drag]")) return;
    const rect = host.getBoundingClientRect();
    dragState = { startX: e.clientX, startY: e.clientY, origLeft: rect.left, origTop: rect.top, moved: false };
    e.preventDefault();
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragState) return;
    const dx = e.clientX - dragState.startX;
    const dy = e.clientY - dragState.startY;
    if (Math.abs(dx) > DRAG_THRESHOLD_PX || Math.abs(dy) > DRAG_THRESHOLD_PX) {
      dragState.moved = true;
    }
    if (!dragState.moved) return;
    const rect = host.getBoundingClientRect();
    const maxLeft = window.innerWidth - rect.width;
    const maxTop = window.innerHeight - rect.height;
    const newLeft = Math.max(0, Math.min(dragState.origLeft + dx, maxLeft));
    const newTop = Math.max(0, Math.min(dragState.origTop + dy, maxTop));
    host.style.left = newLeft + "px";
    host.style.top = newTop + "px";
    host.style.right = "auto";
    host.style.bottom = "auto";
  });

  document.addEventListener("mouseup", () => {
    if (!dragState) return;
    const moved = dragState.moved;
    dragState = null;
    if (moved) {
      const rect = host.getBoundingClientRect();
      savePanelState({ x: rect.left, y: rect.top });
    }
  });

  toggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const collapsed = !panelEl.classList.contains("collapsed");
    applyCollapsed(collapsed);
    savePanelState({ collapsed });
  });

  powerBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const currentlyOff = panelEl.classList.contains("watcher-off");
    setEnabled(currentlyOff); // đang tắt -> bật lại; đang bật -> tắt
  });

  // -------------------------------------------------------------- dữ liệu

  // Nhớ id đang đứng đầu ở lần vẽ trước, để nhấp nháy vàng dòng nào vừa nhảy
  // lên đầu — dễ nhận ra bằng mắt khi test có nhận được tin mới hay không.
  let lastTopId = null;

  function render(store) {
    const items = toSortedArray(store || {});
    const unread = items.filter((e) => !e.read).length;
    badgeEl.textContent = String(unread);
    badgeEl.classList.toggle("zero", unread === 0);

    listEl.innerHTML = "";
    if (!items.length) {
      emptyEl.hidden = false;
      lastTopId = null;
      return;
    }
    emptyEl.hidden = true;

    const newTopId = items[0].rawId;
    const topChanged = newTopId !== lastTopId;
    lastTopId = newTopId;

    items.forEach((ev, idx) => {
      const li = document.createElement("li");
      li.className =
        "item" +
        (ev.read ? " read" : "") +
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
          <span>${escapeHtml(fmtPlatform(ev.platformClass))}</span>
          ${fmtServerStatus(ev.serverStatus)}
          ${ev.unreadCount > 0 ? `<span class="badge-count">${ev.unreadCount}</span>` : ""}
        </div>
      `;
      li.addEventListener("click", () => markRead(ev.rawId));
      listEl.appendChild(li);
    });
  }

  function load() {
    if (!isExtensionContextValid()) return;
    try {
      chrome.storage.local.get(EVENTS_KEY, (res) => render(res[EVENTS_KEY] || {}));
    } catch (err) {
      // bỏ qua
    }
  }

  function markRead(rawId) {
    if (!isExtensionContextValid()) return;
    try {
      chrome.storage.local.get(EVENTS_KEY, (res) => {
        const store = res[EVENTS_KEY] || {};
        if (store[rawId]) store[rawId].read = true;
        chrome.storage.local.set({ [EVENTS_KEY]: store }, () => render(store));
      });
    } catch (err) {
      // bỏ qua
    }
  }

  sweepBtn.addEventListener("click", () => {
    if (!isExtensionContextValid()) return;
    try {
      chrome.runtime.sendMessage({ type: "PANCAKE_TRIGGER_SWEEP" });
    } catch (err) {
      // bỏ qua
    }
  });

  function renderSweepStatus(status) {
    if (!status) {
      statusEl.textContent = "";
      sweepBtn.disabled = false;
      return;
    }
    if (status.running) {
      statusEl.textContent = "Đang cập nhật...";
      sweepBtn.disabled = true;
    } else if (status.finishedAt) {
      statusEl.textContent = `Cập nhật xong lúc ${fmtTime(status.finishedAt)} (${status.steps || 0} bước).`;
      sweepBtn.disabled = false;
    } else {
      statusEl.textContent = "";
      sweepBtn.disabled = false;
    }
  }

  if (isExtensionContextValid()) {
    try {
      chrome.storage.local.get(SETTINGS_KEY, (res) => {
        const settings = res[SETTINGS_KEY] || {};
        applyEnabled(settings.enabled !== false);
      });
      chrome.storage.local.get(SWEEP_STATUS_KEY, (res) => renderSweepStatus(res[SWEEP_STATUS_KEY]));

      chrome.storage.onChanged.addListener((changes, area) => {
        if (area !== "local") return;
        if (changes[EVENTS_KEY]) render(changes[EVENTS_KEY].newValue || {});
        if (changes[SWEEP_STATUS_KEY]) renderSweepStatus(changes[SWEEP_STATUS_KEY].newValue);
        if (changes[SETTINGS_KEY]) {
          applyEnabled((changes[SETTINGS_KEY].newValue || {}).enabled !== false);
        }
      });
    } catch (err) {
      // context invalidated ngay từ đầu — panel vẫn hiện nhưng không có dữ liệu sống,
      // F5 lại trang là dùng được bình thường.
    }
  }

  load();
})();
