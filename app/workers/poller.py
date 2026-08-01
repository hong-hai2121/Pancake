"""Worker nền: kéo hội thoại mới của MỌI page đang BẬT về kho `watcher.hoi_thoai`.

Đây là **nguồn ghi duy nhất** của kho. Màn Tin nhắn chỉ đọc kho (không gọi
Pancake lúc render), nhờ vậy không page nào bị page khác đẩy văng, hội thoại rơi
khỏi top-N giữa 2 vòng vẫn còn nguyên, và trang hiện ra tức thì.

BỐN VAN GIẢM TẢI (Pancake trả 429 khá sớm — chỉ vài lời gọi liên tiếp là dính,
mà bản đầu tiên của worker này bắn 22 request/20 giây ≈ 95.000 request/ngày,
gần như toàn nhận về đúng dữ liệu cũ):

  1. **Bỏ qua sớm** — nhớ `updated_at` mới nhất từng thấy của mỗi page (`moc`).
     Response về mà không dòng nào mới hơn mốc -> KHÔNG đụng DB lượt đó.
     An toàn: danh sách Pancake trả về đã sắp mới -> cũ, nên một hội thoại chỉ
     lọt vào top-N khi nó mới hơn mốc; không có gì mới hơn mốc nghĩa là top-N
     y nguyên như lượt trước.
  2. **Nhịp thích ứng từng page** — có tin mới thì hỏi lại sau `inbox_poll_interval`
     giây; im lặng thì giãn gấp đôi mỗi lượt tới trần `inbox_poll_max_interval`.
  3. **Ngắt mạch page lỗi** — page bị Pancake vô hiệu hoá/mất quyền, lỗi liên
     tiếp `inbox_poll_error_threshold` lượt thì nghỉ hẳn nửa tiếng mới thử lại.
  4. **Xin ít, chỉ xin thêm khi nghi sót** — mỗi lượt chỉ lấy 5 hội thoại; nếu
     CẢ 5 đều mới hơn mốc (dấu hiệu giữa 2 lượt có hơn 5 hội thoại đổi) thì mới
     gọi tiếp mức 20 rồi 50 cho tới khi thấy dòng cũ (`_CATCH_UP`).

Mọi thứ ở trên chỉ đổi *nhịp hỏi* và *lượng ghi*, KHÔNG đổi dữ liệu thu được:
hội thoại nào đã vào kho thì ở lại vĩnh viễn.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core import runtime_config as cfg
from app.core.config import settings
from app.db.repositories import inbox_store
from app.integrations.pancake.client import (
    enabled_pages,
    fetch_conversations_fresh,
    refresh_tags_all_pages,
)

# Số page gọi song song trong 1 lượt.
_CONCURRENCY = 5

# Làm tươi kho tên thẻ mỗi ngần này giây (chỉ vài page có quyền Admin -> vài lời
# gọi/ngày, không đáng kể so với trần 429).
_TAG_REFRESH = 6 * 60 * 60

# Giữ tối đa ngần này mục chi tiết trong `last_run` (log thì in hết).
_KEEP_DETAIL = 50

# Vòng lặp "tích tắc" mỗi ngần này giây rồi mới xét page nào tới hạn.
_TICK = 5.0


def _catch_up_sizes() -> list[int]:
    """Các mức limit tăng dần cho 1 lượt: xin ít trước, nghi sót mới xin thêm."""
    sizes = [
        settings.inbox_poll_limit_small,
        settings.inbox_poll_limit,
        settings.inbox_poll_limit_max,
    ]
    # Bỏ mức trùng/ngược và giữ thứ tự tăng dần.
    out: list[int] = []
    for s in sizes:
        if s > 0 and (not out or s > out[-1]):
            out.append(s)
    return out or [20]


@dataclass
class _PageState:
    """Trạng thái nhịp của 1 page (chỉ trong RAM, mất khi restart là bình thường)."""

    ten: str = ""
    moc: str = ""             # updated_at mới nhất đã thấy
    nhip: float = 0.0         # giây tới lượt hỏi kế tiếp
    ke_tiep: float = 0.0      # mốc monotonic được phép hỏi lại
    loi_lien_tiep: int = 0
    loi_cuoi: str = ""


_state: dict[str, _PageState] = {}
_da_nap_moc = False


async def _nap_moc_tu_kho() -> None:
    """Nạp mốc `updated_at` từ kho vào RAM — chạy 1 lần cho cả tiến trình.

    Không có bước này thì sau MỖI lần restart (chạy `uvicorn --reload` là restart
    mỗi lần sửa file), mọi page đều coi như "chưa biết gì" và phải leo thang
    5→20→50 — cả cụm 22 page tốn ~55 lời gọi chỉ để nhận về dữ liệu đã có sẵn
    trong kho, rất dễ dính 429.
    """
    global _da_nap_moc
    if _da_nap_moc:
        return
    try:
        moc = await asyncio.to_thread(inbox_store.max_updated_at_by_page)
    except Exception as err:  # noqa: BLE001 — DB chưa sẵn sàng thì lát nữa thử lại
        _log(f"[poller] Chưa nạp được mốc từ kho: {type(err).__name__}: {err}")
        return
    for pid, m in moc.items():
        st = _state.setdefault(str(pid), _PageState())
        if not st.moc:
            st.moc = m or ""
    _da_nap_moc = True
    _log(f"[poller] Nạp mốc từ kho cho {len(moc)} page — khỏi quét lại từ đầu.")


# Mốc monotonic được phép làm tươi thẻ lần kế tiếp (0 = làm ngay lượt đầu).
_the_ke_tiep = 0.0


async def _lam_tuoi_the() -> None:
    """Định kỳ gọi public API lấy tên/màu thẻ rồi ghi xuống kho `watcher.the_pancake`.

    Vì sao cần ở đây: `list_tags` chỉ ghi kho khi có người MỞ màn Tin nhắn của
    đúng page đó. Ai chỉ dùng hộp thư GỘP (chế độ đọc kho, không gọi Pancake) sẽ
    không bao giờ có tên thẻ để hiện. Lượt này cũng bắt kịp việc đổi tên thẻ trên
    Pancake mà không ai phải vào từng page.
    """
    global _the_ke_tiep
    now = time.monotonic()
    if now < _the_ke_tiep:
        return
    _the_ke_tiep = now + _TAG_REFRESH
    try:
        ket_qua = await refresh_tags_all_pages()
    except Exception as err:  # noqa: BLE001 — thẻ hỏng không được cản việc poll tin
        _log(f"[poller] Chưa làm tươi được thẻ: {type(err).__name__}: {err}")
        return
    if ket_qua:
        tong = sum(ket_qua.values())
        _log(f"[poller] Làm tươi thẻ: {tong} thẻ / {len(ket_qua)} page.")

# Kết quả vòng chạy gần nhất — cho `GET /poller` và Bảng điều khiển.
last_run: dict = {
    "luc": "", "page_toi_han": 0, "page_bo_qua": 0, "goi_api": 0,
    "convs": 0, "moi": 0, "loi": 0, "giay": 0.0,
    "tin_moi": [], "loi_chi_tiet": [],
}


def _log(msg: str) -> None:
    """In ra stdout kèm flush — không flush thì log bị đệm khi chạy nền/ghi ra file."""
    print(msg, flush=True)


async def _fetch_page(st: _PageState, page: dict) -> tuple[list[dict], int]:
    """Lấy hội thoại MỚI HƠN mốc của 1 page. Trả về (dòng mới, số lời gọi API).

    Leo thang limit chỉ khi NGHI SÓT: mọi dòng trả về đều mới hơn mốc, tức mức
    limit hiện tại có thể chưa chạm tới dòng cũ nào — giữa 2 lượt có thể còn hội
    thoại nữa mà ta chưa thấy.
    """
    goi = 0
    moi: list[dict] = []
    for size in _catch_up_sizes():
        convs = await fetch_conversations_fresh(page["id"], limit=size)
        goi += 1
        if not convs:
            return [], goi
        moi = [c for c in convs if (c.get("updated_at") or "") > st.moc] if st.moc else convs
        # Thấy ít nhất 1 dòng KHÔNG mới hơn mốc -> đã chạm vùng dữ liệu cũ, đủ.
        if len(moi) < len(convs):
            break
    return moi, goi


async def poll_once() -> dict:
    """Chạy 1 lượt: chỉ hỏi những page TỚI HẠN, ghi DB nếu thật sự có gì mới."""
    t0 = time.monotonic()
    await _nap_moc_tu_kho()
    await _lam_tuoi_the()
    pages = await enabled_pages()
    now = time.monotonic()

    # Page mới xuất hiện (vừa BẬT) -> hỏi ngay lượt này.
    toi_han = []
    for p in pages:
        st = _state.setdefault(str(p["id"]), _PageState(ten=p.get("name") or p["id"]))
        st.ten = p.get("name") or p["id"]
        if now >= st.ke_tiep:
            toi_han.append(p)

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def one(page: dict) -> dict:
        """Xử lý 1 page. Tự nuốt lỗi và GẮN TÊN PAGE vào, để biết page nào hỏng."""
        st = _state[str(page["id"])]
        try:
            async with sem:
                moi, goi = await _fetch_page(st, page)
            if moi:
                # CHỈ ghi phần thật sự mới/đổi — thường 0-3 dòng thay vì cả mẻ.
                them = await asyncio.to_thread(
                    inbox_store.upsert_conversations,
                    page["id"], page.get("name") or "", moi,
                )
                st.moc = max([c.get("updated_at") or "" for c in moi] + [st.moc])
                # B2: đổ thêm vào CRM (khách + định danh + hội thoại + lead —
                # FR-011). Công tắc CRM_SYNC_ENABLED, mặc định TẮT. sync_batch
                # tự nuốt lỗi từng dòng — CRM hỏng không được vỡ luồng bot.
                if cfg.bat("crm_sync_enabled"):
                    from app.integrations.pancake import crm_sync

                    await asyncio.to_thread(
                        crm_sync.sync_batch,
                        str(page["id"]), page.get("name") or "", moi,
                    )
            else:
                them = []
            st.loi_lien_tiep, st.loi_cuoi = 0, ""
            # Có tin mới -> quay lại nhịp nhanh nhất; im lặng -> giãn gấp đôi.
            st.nhip = (
                cfg.so("inbox_poll_interval", 20) if moi
                else min(
                    max(st.nhip * 2, cfg.so("inbox_poll_interval", 20)),
                    cfg.so("inbox_poll_max_interval", 300),
                )
            )
            st.ke_tiep = time.monotonic() + st.nhip
            return {"page": st.ten, "goi": goi, "so_moi": len(moi), "them": them}
        except Exception as err:  # noqa: BLE001 — 1 page hỏng không được làm hỏng lượt
            st.loi_lien_tiep += 1
            st.loi_cuoi = f"{type(err).__name__}: {err}"
            if st.loi_lien_tiep >= cfg.so("inbox_poll_error_threshold", 3):
                st.nhip = cfg.so("inbox_poll_error_backoff", 1800)      # ngắt mạch
            else:
                st.nhip = min(
                    max(st.nhip * 2, cfg.so("inbox_poll_interval", 20)),
                    cfg.so("inbox_poll_max_interval", 300),
                )
            st.ke_tiep = time.monotonic() + st.nhip
            return {"page": st.ten, "loi": st.loi_cuoi, "lan": st.loi_lien_tiep,
                    "nghi": round(st.nhip)}

    results = await asyncio.gather(*(one(p) for p in toi_han))

    goi_api = convs = 0
    tin_moi: list[dict] = []
    loi_chi_tiet: list[dict] = []
    for res in results:
        if "loi" in res:
            loi_chi_tiet.append(res)
            continue
        goi_api += res["goi"]
        convs += res["so_moi"]
        for c in res["them"]:
            tin_moi.append({
                "page": res["page"],
                "khach": c.get("name") or "",
                "snippet": (c.get("snippet") or "")[:120],
                "luc": c.get("updated_at") or "",
                "conv_id": c.get("conv_id") or "",
            })

    giay = round(time.monotonic() - t0, 2)
    last_run.update(
        luc=datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S %d/%m/%Y"),
        page_toi_han=len(toi_han), page_bo_qua=len(pages) - len(toi_han),
        goi_api=goi_api, convs=convs, moi=len(tin_moi), loi=len(loi_chi_tiet),
        giay=giay,
        tin_moi=tin_moi[:_KEEP_DETAIL], loi_chi_tiet=loi_chi_tiet[:_KEEP_DETAIL],
    )

    if tin_moi or loi_chi_tiet:
        _log(
            f"[poller] {len(toi_han)}/{len(pages)} page tới hạn · {goi_api} lời gọi"
            f" · {len(tin_moi)} mới · {len(loi_chi_tiet)} lỗi · {giay}s"
        )
        for t in tin_moi:
            _log(f"[poller]   + MỚI · {t['page']} · {t['khach']}: {t['snippet']}")
        for e in loi_chi_tiet:
            _log(
                f"[poller]   ✗ LỖI · {e['page']} (lần {e['lan']}, nghỉ {e['nghi']}s):"
                f" {e['loi']}"
            )

    return dict(last_run)


def trang_thai_page() -> list[dict]:
    """Nhịp hiện tại của từng page — cho `GET /poller` soi xem ai đang bị giãn."""
    now = time.monotonic()
    return sorted(
        (
            {
                "page": st.ten,
                "nhip_giay": round(st.nhip),
                "hoi_lai_sau_giay": max(0, round(st.ke_tiep - now)),
                "loi_lien_tiep": st.loi_lien_tiep,
                "loi_cuoi": st.loi_cuoi,
            }
            for st in _state.values()
        ),
        key=lambda r: (-r["nhip_giay"], r["page"]),
    )


def page_loi() -> dict[str, dict]:
    """Page nào đang lỗi -> {page_id: {"lan", "loi", "ngat_mach", "hoi_lai_sau_giay"}}.

    Dùng cho danh sách page ở Bảng điều khiển: page bị Pancake vô hiệu hoá/mất
    quyền sẽ được tô vàng cảnh báo để người dùng biết mà TẮT đi, thay vì phải
    ngồi đọc log mới thấy.
    """
    now = time.monotonic()
    return {
        pid: {
            "lan": st.loi_lien_tiep,
            "loi": st.loi_cuoi,
            "ngat_mach": st.loi_lien_tiep >= cfg.so("inbox_poll_error_threshold", 3),
            "hoi_lai_sau_giay": max(0, round(st.ke_tiep - now)),
        }
        for pid, st in _state.items()
        if st.loi_lien_tiep
    }


async def poll_loop() -> None:
    """Vòng lặp vô hạn — tích tắc mỗi `_TICK` giây rồi hỏi các page tới hạn.

    Công tắc `inbox_poll_enabled` đọc lại MỖI vòng (màn Cài đặt đổi được lúc đang
    chạy): TẮT thì vòng lặp vẫn sống nhưng không hỏi Pancake, bật lại là chạy tiếp
    — giống cách worker cảm xúc làm.
    """
    while True:
        try:
            if not cfg.bat("inbox_poll_enabled"):
                await asyncio.sleep(_TICK)
                continue
            await poll_once()
        except Exception as err:  # noqa: BLE001 — không để 1 lỗi giết cả vòng lặp
            _log(f"[poller] Lỗi vòng lặp: {type(err).__name__}: {err}")
        await asyncio.sleep(_TICK)
