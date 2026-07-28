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
  const STATE_KEY = "pancake_seen_state"; // { [convRawId]: { unreadCount, snippet, time, lastSeenAt } }
  const SETTINGS_KEY = "pancake_settings"; // { enabled: boolean }
  const SWEEP_STATUS_KEY = "pancake_sweep_status";
  const SWEEP_STEP_WAIT_MS = 220; // chờ React render xong sau mỗi bước cuộn trước khi quét
  const SWEEP_MAX_STEPS = 400; // chặn an toàn, phòng danh sách vô hạn/lỗi tính scrollHeight
  // seenState không tự rụng bớt theo thời gian (khác pancake_events đã có cap ở
  // background.js) — mỗi rawId từng lướt qua (kể cả lúc sweepFullList cuộn hết
  // danh sách) đều bị giữ mãi, phình dần chrome.storage.local (quota mặc định
  // 5MB, extension chưa xin unlimitedStorage). Cap theo lastSeenAt gần nhất,
  // giống capByRecency() bên background.js, để tránh phình vô hạn.
  const MAX_SEEN_STATE = 500;
  // Virtual list TÁI DÙNG node khi có hội thoại mới (kể cả không cuộn): hội thoại
  // mới chèn lên đầu, node đang render bị đổi id+nội dung để đại diện cho nó, hội
  // thoại rơi khỏi cuối khung nhìn không còn được render nữa. Vì vậy ngoài so
  // sánh theo id (bên dưới), cần thêm 1 lớp so sánh theo VỊ TRÍ ở đầu danh sách
  // (bỏ qua mục ghim) — không quan tâm node đó trước đó đại diện cho id nào.
  const TOP_WINDOW_SIZE = 5;

  let seenState = {};
  let stateLoaded = false;
  let isFirstScan = true; // đã quét ít nhất 1 lần trong phiên (tab) hiện tại chưa
  // true CHỈ KHI seenState rỗng lúc nạp trang, tức là chưa từng lưu lịch sử gì —
  // dùng để phân biệt "mới cài extension lần đầu" (nên chặn báo backlog có sẵn)
  // với "mở lại tab sau khi đóng lâu, đã có lịch sử" (KHÔNG nên chặn — đây chính
  // là lúc cần bắt tin mới đến trong lúc tắt để "cập nhật" cho đúng).
  let isFreshInstall = true;
  let currentTarget = null;
  let mutationObserver = null;
  let debounceTimer = null;
  let warnedNoTarget = false;
  let warnedEmptyItems = false;
  let lastTopSlots = []; // [{ rawId, snippet, time, unreadCount }] theo đúng vị trí hiển thị
  let attachIntervalId = null;
  let scanIntervalId = null;
  let contextInvalidated = false;
  let sweepInProgress = false;
  let watcherEnabled = true; // công tắc tổng — tắt thì dừng cả quét, panel cũng tự ẩn

  function log(...args) {
    console.log("[Pancake Watcher]", ...args);
  }

  // Mỗi lần reload extension ở chrome://extensions, script đã inject sẵn vào tab
  // đang mở bị mất kết nối tới extension ("Extension context invalidated") — mọi
  // lệnh chrome.storage/chrome.runtime sau đó sẽ ném lỗi. Không có cách nào phục
  // hồi từ phía content script, nên phát hiện sớm rồi tự dừng hẳn (thay vì spam lỗi
  // mỗi lần quét) và nhắc reload lại TAB (không phải extension) để nạp script mới.
  function isExtensionContextValid() {
    return typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.id;
  }

  function stopBecauseContextInvalidated() {
    if (contextInvalidated) return;
    contextInvalidated = true;
    if (mutationObserver) mutationObserver.disconnect();
    if (attachIntervalId) clearInterval(attachIntervalId);
    if (scanIntervalId) clearInterval(scanIntervalId);
    console.log(
      "[Pancake Watcher] Extension vừa được reload nên tab này mất kết nối " +
        "(Extension context invalidated) — F5 lại trang pancake.vn để tiếp tục theo dõi."
    );
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

  // Khung cuộn thật (cha của rc-virtual-list-holder-inner) — dùng cho sweepFullList
  // (đặt scrollTop để cuộn chương trình). CHÚ Ý: khung này có overflow-y: hidden,
  // rc-virtual-list tự quản lý cuộn qua wheel/touch listener rồi set scrollTop
  // bằng JS, nên đọc scrollTop để BIẾT vị trí không chắc luôn khớp thời gian thực.
  function getScrollHolder() {
    return currentTarget ? currentTarget.closest(".rc-virtual-list-holder") : null;
  }

  // Dấu hiệu đáng tin hơn cho "đang ở đỉnh danh sách": chính rc-virtual-list-holder-inner
  // (currentTarget) có inline style transform: translateY(Npx) phản ánh trực tiếp độ
  // lệch đang render — 0px = đỉnh, cuộn xuống thì N tăng dần (đã thấy tận mắt trong
  // HTML mẫu: translateY(0px) lúc đầu, translateY(430px) sau khi cuộn).
  function isNearTop() {
    if (!currentTarget) return true;
    const transform = currentTarget.style.transform || "";
    const match = transform.match(/translateY\((-?[\d.]+)px\)/);
    if (!match) return true; // không đọc được thì tạm coi như ở đỉnh
    return Math.abs(parseFloat(match[1])) <= 8;
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

  // Giữ lại tối đa MAX_SEEN_STATE bản ghi gần được thấy nhất, loại bớt phần cũ
  // nhất. Entry chưa có lastSeenAt (lưu từ trước khi có field này) coi như cũ
  // nhất, bị loại trước tiên.
  function capSeenState(state, max) {
    const keys = Object.keys(state);
    if (keys.length <= max) return state;
    const kept = keys
      .sort((a, b) => (state[b].lastSeenAt || 0) - (state[a].lastSeenAt || 0))
      .slice(0, max);
    const result = {};
    kept.forEach((k) => (result[k] = state[k]));
    return result;
  }

  function scanAndDiff() {
    if (contextInvalidated || !watcherEnabled) return;
    if (!isExtensionContextValid()) {
      stopBecauseContextInvalidated();
      return;
    }
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
    // Chỉ chặn báo backlog khi ĐÂY LÀ LẦN CÀI ĐẦU TIÊN (chưa từng lưu gì) VÀ đang
    // là lần quét đầu của phiên này — mở lại tab sau khi tắt lâu (đã có lịch sử)
    // thì không chặn, để bắt được tin đến lúc vắng mặt ngay từ lượt quét đầu.
    const suppressNew = isFreshInstall && wasFirstScan;
    const nearTop = isNearTop();
    const eventMap = new Map(); // rawId -> event, gộp 2 lớp phát hiện, tránh báo trùng
    const nextState = { ...seenState };

    // Lớp 1: so theo id hội thoại. Báo cả 2 trường hợp: (a) hội thoại đã biết mà
    // nội dung/số chưa đọc đổi, (b) hội thoại chưa từng thấy id nhưng đang có tín
    // hiệu chưa đọc — kể cả khi đó chỉ là hội thoại cũ vừa cuộn tới lần đầu, vẫn cứ
    // báo (ưu tiên bắt được nhiều hơn là ưu tiên tuyệt đối chính xác).
    items.forEach((item) => {
      const prev = seenState[item.rawId];
      const hasSignal = item.isUnread || item.unreadCount > 0;
      if (prev) {
        const changed =
          item.unreadCount > prev.unreadCount ||
          (item.snippet && item.snippet !== prev.snippet) ||
          (item.time && item.time !== prev.time);
        if (changed) {
          eventMap.set(item.rawId, buildEvent(item, "tin_nhan_moi"));
        }
      } else if (!suppressNew && hasSignal) {
        eventMap.set(item.rawId, buildEvent(item, "hoi_thoai_moi"));
      }

      nextState[item.rawId] = {
        unreadCount: item.unreadCount,
        snippet: item.snippet,
        time: item.time,
        lastSeenAt: Date.now(),
      };
    });

    // Lớp 2: so theo VỊ TRÍ ở đầu danh sách (bỏ mục ghim) — bắt hội thoại mới hoàn
    // toàn vừa được Pancake đẩy lên đầu, kể cả khi đang cuộn dở (không chặn theo
    // nearTop nữa — ưu tiên bắt được nhiều hơn).
    {
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
        if (!suppressNew && slotChanged && hasSignal && !eventMap.has(item.rawId)) {
          eventMap.set(item.rawId, buildEvent(item, "tin_nhan_moi"));
        }
      });
      lastTopSlots = topNonPinned.map((it) => ({
        rawId: it.rawId,
        snippet: it.snippet,
        time: it.time,
        unreadCount: it.unreadCount,
      }));
    }

    seenState = capSeenState(nextState, MAX_SEEN_STATE);
    try {
      chrome.storage.local.set({ [STATE_KEY]: seenState });
    } catch (err) {
      stopBecauseContextInvalidated();
      return;
    }
    isFirstScan = false;

    if (wasFirstScan) {
      log(`Đã nạp baseline ${items.length} hội thoại đang hiển thị.`);
    }

    const newEvents = Array.from(eventMap.values());
    log(
      `[debug] items=${items.length} nearTop=${nearTop} suppressNew=${suppressNew} ` +
        `isFreshInstall=${isFreshInstall} seenSize=${Object.keys(seenState).length} ` +
        `newEvents=${newEvents.length}`
    );
    if (newEvents.length) {
      log(`Phát hiện ${newEvents.length} hội thoại có tin mới:`, newEvents);
      try {
        chrome.runtime.sendMessage({ type: "PANCAKE_NEW_MESSAGE", events: newEvents });
      } catch (err) {
        stopBecauseContextInvalidated();
      }
    }
  }

  function scheduleScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scanAndDiff, SCAN_DEBOUNCE_MS);
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setSweepStatus(patch) {
    try {
      chrome.storage.local.get(SWEEP_STATUS_KEY, (res) => {
        const merged = { ...(res[SWEEP_STATUS_KEY] || {}), ...patch };
        chrome.storage.local.set({ [SWEEP_STATUS_KEY]: merged });
      });
    } catch (err) {
      // context có thể vừa invalidated giữa chừng — bỏ qua, sweepFullList tự thoát.
    }
  }

  // "Cập nhật": tự cuộn cả danh sách từ đầu xuống cuối rồi quay lại vị trí ban đầu,
  // để MỌI hội thoại lần lượt được Pancake render vào DOM ít nhất 1 lần trong phiên
  // này — nhờ đó Lớp 1 (so theo id đã biết) có cơ hội so sánh & bắt tin đến trong
  // lúc tab đóng cho những hội thoại nằm ngoài màn hình lúc mới mở trang. Trong lúc
  // cuộn dở (không ở đỉnh), Lớp 2 tự động không hoạt động (xem isNearTop trong
  // scanAndDiff) nên không lo báo nhầm hội thoại cũ thành mới.
  async function sweepFullList() {
    if (sweepInProgress || contextInvalidated || !watcherEnabled) return;
    if (!isExtensionContextValid()) {
      stopBecauseContextInvalidated();
      return;
    }
    const holder = getScrollHolder();
    if (!holder) {
      log("Không tìm thấy khung cuộn của danh sách hội thoại, bỏ qua cập nhật.");
      return;
    }

    sweepInProgress = true;
    setSweepStatus({ running: true, startedAt: new Date().toISOString() });
    log("Bắt đầu cập nhật: cuộn quét toàn bộ danh sách hội thoại...");

    const originalScrollTop = holder.scrollTop;
    const stepPx = Math.max(Math.round(holder.clientHeight * 1.5), 800);
    let steps = 0;

    try {
      while (
        steps < SWEEP_MAX_STEPS &&
        holder.scrollTop + holder.clientHeight < holder.scrollHeight - 4
      ) {
        holder.scrollTop = Math.min(holder.scrollTop + stepPx, holder.scrollHeight);
        steps++;
        await wait(SWEEP_STEP_WAIT_MS);
        if (contextInvalidated) return;
        scanAndDiff();
      }
      holder.scrollTop = originalScrollTop;
      await wait(SWEEP_STEP_WAIT_MS);
      if (!contextInvalidated) scanAndDiff();
    } finally {
      sweepInProgress = false;
      log(`Cập nhật xong — đã cuộn qua ${steps} bước.`);
      setSweepStatus({ running: false, finishedAt: new Date().toISOString(), steps });
    }
  }

  try {
    chrome.runtime.onMessage.addListener((message) => {
      if (message?.type === "PANCAKE_TRIGGER_SWEEP") {
        sweepFullList();
      }
    });
  } catch (err) {
    // context invalidated ngay từ lúc đăng ký listener — bỏ qua, các nơi khác đã
    // tự phát hiện và dừng.
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
    if (contextInvalidated || !watcherEnabled) return;
    if (!isExtensionContextValid()) {
      stopBecauseContextInvalidated();
      return;
    }
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

  // Công tắc tổng (bật/tắt ở popup hoặc panel nổi) — đọc trạng thái TRƯỚC khi
  // gắn observer/quét lần đầu, để không lỡ quét 1 nhịp khi đang tắt.
  try {
    chrome.storage.local.get(SETTINGS_KEY, (settingsRes) => {
      const settings = settingsRes[SETTINGS_KEY] || {};
      watcherEnabled = settings.enabled !== false; // mặc định bật nếu chưa từng lưu
      log(`Trạng thái công tắc lúc nạp trang: enabled=${settings.enabled} -> watcherEnabled=${watcherEnabled}`);

      try {
        chrome.storage.local.get(STATE_KEY, (res) => {
          seenState = res[STATE_KEY] || {};
          isFreshInstall = Object.keys(seenState).length === 0;
          stateLoaded = true;
          attachObserverIfNeeded();
          scanAndDiff();

          // Luôn tự chạy 1 lượt "Cập nhật" ngay sau khi có baseline — không cần
          // bấm nút thủ công mỗi lần, và không có tuỳ chọn tắt việc này (đảm bảo
          // luôn bắt được tin đến trong lúc tab đóng ngay từ lúc mở lại trang).
          if (watcherEnabled) {
            setTimeout(sweepFullList, 800);
          }
        });
      } catch (err) {
        stopBecauseContextInvalidated();
      }
    });
  } catch (err) {
    stopBecauseContextInvalidated();
  }

  // Bật/tắt công tắc tổng trong lúc trang đang mở (từ popup hoặc panel nổi) thì
  // áp dụng ngay, không cần F5 lại trang.
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes[SETTINGS_KEY]) return;
      const nowEnabled = (changes[SETTINGS_KEY].newValue || {}).enabled !== false;
      if (nowEnabled === watcherEnabled) return;
      watcherEnabled = nowEnabled;
      if (watcherEnabled) {
        log("Đã BẬT lại theo dõi.");
        attachObserverIfNeeded();
        scanAndDiff();
      } else {
        log("Đã TẮT theo dõi — dừng quét tin nhắn mới.");
        if (mutationObserver) {
          mutationObserver.disconnect();
          mutationObserver = null;
        }
        currentTarget = null; // ép attachObserverIfNeeded gắn lại từ đầu khi bật lại
      }
    });
  } catch (err) {
    // context invalidated ngay từ đầu — nơi khác đã tự phát hiện và dừng.
  }

  // Dự phòng: SPA có thể thay list container khi chuyển page/hội thoại, và tab bị
  // ẩn có thể làm chậm mutation batching — poll nhẹ để tự gắn lại + quét lại.
  attachIntervalId = setInterval(attachObserverIfNeeded, POLL_FALLBACK_MS);
  scanIntervalId = setInterval(scanAndDiff, POLL_FALLBACK_MS);
})();
