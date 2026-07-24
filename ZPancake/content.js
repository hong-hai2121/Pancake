// Theo dõi div danh sách hội thoại (rc-virtual-list-holder-inner) trên pancake.vn.
// Vì đây là virtual list của antd, node DOM bị tái sử dụng khi cuộn — không thể
// suy ra "có tin mới" chỉ từ việc có mutation. Thay vào đó: mỗi lần có mutation,
// quét lại toàn bộ item đang render và so sánh với snapshot theo id hội thoại.

(function () {
  // rc-virtual-list-holder-inner được antd dùng ở NHIỀU nơi trên trang (dropdown,
  // table...), nên phải khoanh vùng trong #conversationList (id ổn định của khung
  // danh sách hội thoại) rồi mới tìm xuống — nếu không sẽ vớ nhầm virtual-list khác
  // và không bao giờ tìm thấy .conversation-list-item nào.
  const SCOPED_SELECTOR = "#conversationList .rc-virtual-list-holder-inner";
  const FALLBACK_SELECTOR = ".rc-virtual-list-holder-inner";
  const SCAN_DEBOUNCE_MS = 400;
  const POLL_FALLBACK_MS = 3000;
  const STATE_KEY = "pancake_seen_state"; // { [convRawId]: { unreadCount, snippet, time } }
  // Virtual list TÁI DÙNG node khi có hội thoại mới (kể cả không cuộn): hội thoại
  // mới chèn lên đầu, node đang render bị đổi id+nội dung để đại diện cho nó, hội
  // thoại rơi khỏi cuối khung nhìn không còn được render nữa. Vì vậy ngoài so
  // sánh theo id (bên dưới), cần thêm 1 lớp so sánh theo VỊ TRÍ ở đầu danh sách
  // (bỏ qua mục ghim) — không quan tâm node đó trước đó đại diện cho id nào.
  const TOP_WINDOW_SIZE = 5;

  let seenState = {};
  let stateLoaded = false;
  let isFirstScan = true; // seed đầu tiên: không báo backlog có sẵn khi vừa mở trang
  let currentTarget = null;
  let mutationObserver = null;
  let debounceTimer = null;
  let warnedNoTarget = false;
  let warnedEmptyItems = false;
  let lastTopSlots = []; // [{ rawId, snippet, time, unreadCount }] theo đúng vị trí hiển thị

  function log(...args) {
    console.log("[Pancake Watcher]", ...args);
  }

  // Parse id kiểu "1067361523117844_37430975803183099" (Facebook)
  // hoặc "pzl_g_843446568918153388_2011884553293740019" (Zalo, nhóm/cá nhân qua Pancake).
  function parseConvKey(rawId) {
    if (!rawId) return { platform: "unknown", kind: "unknown", pageId: null, convId: null };
    const parts = rawId.split("_");
    if (parts[0] === "pzl") {
      return {
        platform: "zalo",
        kind: parts[1] === "g" ? "group" : "personal",
        pageId: parts[2] || null,
        convId: parts.slice(3).join("_") || null,
      };
    }
    if (parts.length >= 2) {
      return {
        platform: "facebook",
        kind: "personal",
        pageId: parts[0],
        convId: parts.slice(1).join("_"),
      };
    }
    return { platform: "unknown", kind: "unknown", pageId: null, convId: rawId };
  }

  function extractItems() {
    if (!currentTarget) return [];
    const items = [];
    const wrappers = currentTarget.querySelectorAll(":scope > div[id]");
    wrappers.forEach((wrapper) => {
      const rawId = wrapper.getAttribute("id");
      const card = wrapper.querySelector(".conversation-list-item");
      if (!rawId || !card) return;

      const nameEl = card.querySelector(".name-text");
      const timeEl = card.querySelector(".time-modul");
      const snippetEl = card.querySelector(".snippet-text");
      const badgeEl = card.querySelector(".ant-badge-count");
      const platformEl = card.querySelector('[class*="platform-"]');

      let platformClass = "";
      if (platformEl) {
        platformClass =
          Array.from(platformEl.classList).find((c) => c.startsWith("platform-")) || "";
      }

      const unreadCount = badgeEl
        ? parseInt(badgeEl.getAttribute("title") || badgeEl.textContent || "0", 10) || 0
        : 0;

      items.push({
        rawId,
        convKey: parseConvKey(rawId),
        name: nameEl ? nameEl.textContent.trim() : "",
        time: timeEl ? timeEl.textContent.trim() : "",
        snippet: snippetEl ? snippetEl.textContent.trim() : "",
        unreadCount,
        isUnread: card.classList.contains("unread"),
        isPinned: card.classList.contains("is-pinned"),
        platformClass,
      });
    });
    return items;
  }

  function buildEvent(item, reason) {
    return {
      ...item.convKey,
      rawId: item.rawId,
      name: item.name,
      snippet: item.snippet,
      time: item.time,
      unreadCount: item.unreadCount,
      platformClass: item.platformClass,
      reason, // 'hoi_thoai_moi' | 'tin_nhan_moi'
      detectedAt: new Date().toISOString(),
    };
  }

  function scanAndDiff() {
    if (!stateLoaded) return;
    const items = extractItems();
    if (!items.length) {
      if (!warnedEmptyItems) {
        log("Quét được 0 hội thoại — kiểm tra lại selector nếu tình trạng này kéo dài.");
        warnedEmptyItems = true;
      }
      return;
    }
    warnedEmptyItems = false;

    const wasFirstScan = isFirstScan;
    const eventMap = new Map(); // rawId -> event, gộp 2 lớp phát hiện, tránh báo trùng
    const nextState = { ...seenState };

    // Lớp 1: so theo id hội thoại — bắt tin mới khi 1 hội thoại vẫn đang hiển thị
    // đúng id cũ nhưng nội dung/số chưa đọc thay đổi.
    items.forEach((item) => {
      const prev = seenState[item.rawId];
      const hasSignal = item.isUnread || item.unreadCount > 0;

      if (!prev) {
        // Hội thoại chưa từng thấy: nếu là backlog lúc mới nạp trang thì bỏ qua
        // (isFirstScan), nếu xuất hiện sau đó và đang có tín hiệu chưa đọc -> tin mới thật.
        if (!isFirstScan && hasSignal) {
          eventMap.set(item.rawId, buildEvent(item, "hoi_thoai_moi"));
        }
      } else {
        const changed =
          item.unreadCount > prev.unreadCount ||
          (item.snippet && item.snippet !== prev.snippet) ||
          (item.time && item.time !== prev.time);
        if (changed) {
          eventMap.set(item.rawId, buildEvent(item, "tin_nhan_moi"));
        }
      }

      nextState[item.rawId] = {
        unreadCount: item.unreadCount,
        snippet: item.snippet,
        time: item.time,
      };
    });

    // Lớp 2: so theo VỊ TRÍ ở đầu danh sách (bỏ mục ghim) — bắt đúng trường hợp
    // Pancake tái dùng node để hiện hội thoại mới lên đầu mà không cuộn/thao tác gì,
    // nên node đó có thể mang 1 id "chưa từng thấy" (vì trước giờ nó đại diện cho
    // hội thoại khác, nằm ngoài baseline) — không phụ thuộc lịch sử theo id.
    const topNonPinned = items.filter((it) => !it.isPinned).slice(0, TOP_WINDOW_SIZE);
    topNonPinned.forEach((item, idx) => {
      const prevSlot = lastTopSlots[idx];
      const hasSignal = item.isUnread || item.unreadCount > 0;
      const slotChanged =
        !prevSlot ||
        prevSlot.rawId !== item.rawId ||
        prevSlot.snippet !== item.snippet ||
        prevSlot.time !== item.time ||
        item.unreadCount > (prevSlot.unreadCount || 0);
      if (!wasFirstScan && slotChanged && hasSignal && !eventMap.has(item.rawId)) {
        eventMap.set(item.rawId, buildEvent(item, "tin_nhan_moi"));
      }
    });
    lastTopSlots = topNonPinned.map((it) => ({
      rawId: it.rawId,
      snippet: it.snippet,
      time: it.time,
      unreadCount: it.unreadCount,
    }));

    seenState = nextState;
    chrome.storage.local.set({ [STATE_KEY]: seenState });
    isFirstScan = false;

    if (wasFirstScan) {
      log(`Đã nạp baseline ${items.length} hội thoại đang hiển thị.`);
    }

    const newEvents = Array.from(eventMap.values());
    if (newEvents.length) {
      log(`Phát hiện ${newEvents.length} hội thoại có tin mới:`, newEvents);
      try {
        chrome.runtime.sendMessage({ type: "PANCAKE_NEW_MESSAGE", events: newEvents });
      } catch (err) {
        log("Không gửi được message tới background:", err);
      }
    }
  }

  function scheduleScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scanAndDiff, SCAN_DEBOUNCE_MS);
  }

  function findListTarget() {
    const scoped = document.querySelector(SCOPED_SELECTOR);
    if (scoped) return scoped;
    // Không thấy #conversationList (Pancake có thể đổi id) -> tạm lùi về selector
    // chung, nhưng cảnh báo rõ vì có nguy cơ vớ nhầm virtual-list khác trên trang.
    const fallback = document.querySelector(FALLBACK_SELECTOR);
    if (fallback) {
      log(
        "CẢNH BÁO: không tìm thấy #conversationList, đang dùng selector chung " +
          FALLBACK_SELECTOR +
          " — có thể vớ nhầm virtual-list khác (dropdown/table)."
      );
    }
    return fallback;
  }

  function attachObserverIfNeeded() {
    const target = findListTarget();
    if (!target) {
      if (!warnedNoTarget) {
        log("Chưa tìm thấy danh sách hội thoại trên trang, sẽ thử lại...");
        warnedNoTarget = true;
      }
      return;
    }
    warnedNoTarget = false;
    if (target === currentTarget) return;
    if (mutationObserver) mutationObserver.disconnect();
    currentTarget = target;
    mutationObserver = new MutationObserver(scheduleScan);
    mutationObserver.observe(target, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "id"], // "id" đổi khi node bị tái dùng cho hội thoại khác
    });
    log("Đã gắn observer vào danh sách hội thoại.");
    scheduleScan();
  }

  chrome.storage.local.get(STATE_KEY, (res) => {
    seenState = res[STATE_KEY] || {};
    stateLoaded = true;
    attachObserverIfNeeded();
    scanAndDiff();
  });

  // Dự phòng: SPA có thể thay list container khi chuyển page/hội thoại, và tab bị
  // ẩn có thể làm chậm mutation batching — poll nhẹ để tự gắn lại + quét lại.
  setInterval(attachObserverIfNeeded, POLL_FALLBACK_MS);
  setInterval(scanAndDiff, POLL_FALLBACK_MS);
})();
