"""Chiều NGƯỢC lại của app/web/api_catalog.py: dự án GỌI RA Pancake.

api_catalog = web local gọi VÀO dự án (/api/v1). File này lo phần đi ra:
lấy page · thẻ · hội thoại · tin nhắn từ Pancake, rồi ĐỔ VÀO CRM đúng bằng các
hàm mà worker `poll_loop`/`messages_loop` đang dùng thật (không viết lại logic
riêng cho màn test — test mà khác hàng thật thì test vô nghĩa).

Mỗi việc là một "op": khai báo tham số ở `OPS`, chạy ở `chay()`. Danh sách hiện
ra màn dưới dạng endpoint giả `/data/thu-api/goi/<mã>` để dùng chung đúng giao
diện bấm-là-chạy của tab "Thử API dự án":
    op ĐỌC  -> GET  -> bấm dòng là chạy luôn
    op GHI  -> POST -> phải bấm "Chạy thật" + xác nhận
"""

from __future__ import annotations

import time
from typing import Any

from app.core.errors import ApiError
from app.db.repositories import conversation_repo, integration_repo
from app.integrations.pancake import client, crm_sync, message_sync

GOC = "/data/thu-api/goi"

# Ba nhóm theo đúng đường đi của dữ liệu: gọi ra -> đổ vào -> soi lại.
_LAY = "1. Lấy dữ liệu từ Pancake (chỉ đọc)"
_DONG_BO = "2. Đồng bộ vào CRM (GHI dữ liệu thật)"
_SOI = "3. Soi lại dữ liệu đã vào CRM"


def _ts(ten: str, kieu: str = "chữ", mac_dinh: str = "",
        bat_buoc: bool = False, goi_y: str = "") -> dict:
    return {"ten": ten, "kieu": kieu, "mac_dinh": mac_dinh,
            "bat_buoc": bat_buoc, "goi_y": goi_y}


# (mã, nhóm, ghi dữ liệu?, mô tả, tham số)
OPS: list[dict] = [
    {
        "ma": "chu-token", "nhom": _LAY, "ghi": False,
        "mo_ta": "Token trong .env là của ai, còn sống không (client.token_owner).",
        "tham_so": [],
    },
    {
        "ma": "pages", "nhom": _LAY, "ghi": False,
        "mo_ta": "Mọi page token với tới được — bỏ cache, gọi Pancake tươi "
                 "(client.list_pages).",
        "tham_so": [],
    },
    {
        "ma": "pages-dang-bat", "nhom": _LAY, "ghi": False,
        "mo_ta": "Page đang BẬT công tắc bot (client.enabled_pages).",
        "tham_so": [],
    },
    {
        "ma": "the", "nhom": _LAY, "ghi": False,
        "mo_ta": "Thẻ của 1 page: id → tên + màu (client.list_tags). Rỗng nghĩa "
                 "là page chưa có page_access_token và kho thẻ cũng chưa có gì.",
        "tham_so": [_ts("page_id", "chữ", "", True, "id page bên Pancake")],
    },
    {
        "ma": "hoi-thoai", "nhom": _LAY, "ghi": False,
        "mo_ta": "Hội thoại tươi của 1 page — đúng dữ liệu poller nhận "
                 "(client.fetch_conversations_fresh).",
        "tham_so": [
            _ts("page_id", "chữ", "", True, "id page bên Pancake"),
            _ts("type", "chữ", "INBOX", False, "INBOX | PHONE | COMMENT"),
            _ts("limit", "số", "5", False, "lấy mấy hội thoại"),
        ],
    },
    {
        "ma": "tin-nhan", "nhom": _LAY, "ghi": False,
        "mo_ta": "Toàn bộ tin nhắn của 1 hội thoại (client.get_conversation).",
        "tham_so": [
            _ts("page_id", "chữ", "", True),
            _ts("conv_id", "chữ", "", True, "lấy ở cột conv_id của op Hội thoại"),
            _ts("customer_id", "chữ", "", False, "uuid khách bên Pancake, có thì chuẩn hơn"),
        ],
    },
    {
        "ma": "dong-bo-hoi-thoai", "nhom": _DONG_BO, "ghi": True,
        "mo_ta": "Kéo hội thoại tươi rồi đổ vào CRM: khách · hội thoại · thẻ · "
                 "nhân viên xử lý (crm_sync.sync_batch — đúng hàm poller gọi).",
        "tham_so": [
            _ts("page_id", "chữ", "", True),
            _ts("type", "chữ", "INBOX", False, "INBOX | PHONE | COMMENT"),
            _ts("limit", "số", "5", False, "đồng bộ mấy hội thoại mới nhất"),
        ],
    },
    {
        "ma": "dong-bo-tin-nhan", "nhom": _DONG_BO, "ghi": True,
        "mo_ta": "Chạy 1 vòng kéo NỘI DUNG tin nhắn về crm.messages "
                 "(message_sync.dong_bo_lo — đúng hàm worker msg-sync gọi).",
        "tham_so": [_ts("limit", "số", "5", False, "tối đa mấy hội thoại 1 vòng")],
    },
    {
        "ma": "lam-tuoi-the", "nhom": _DONG_BO, "ghi": True,
        "mo_ta": "Gọi lại thẻ của MỌI page và ghi vào kho thẻ "
                 "(client.refresh_tags_all_pages).",
        "tham_so": [],
    },
    {
        "ma": "doi-chieu", "nhom": _SOI, "ghi": False,
        "mo_ta": "1 hội thoại Pancake đã thành gì trong CRM: khách · hội thoại · "
                 "thẻ · nhân viên xử lý · số tin đã lưu.",
        "tham_so": [_ts("conv_id", "chữ", "", True, "id hội thoại bên Pancake")],
    },
    {
        "ma": "ton-dong", "nhom": _SOI, "ghi": False,
        "mo_ta": "Còn bao nhiêu hội thoại chưa kéo tin / có tin mới chưa về.",
        "tham_so": [],
    },
    {
        "ma": "page-trong-crm", "nhom": _SOI, "ghi": False,
        "mo_ta": "Page đã nối vào CRM: công tắc đồng bộ + số hội thoại đã đổ về.",
        "tham_so": [],
    },
]

_TRA = {o["ma"]: o for o in OPS}


def page_mac_dinh() -> str:
    """Điền sẵn page_id cho khỏi phải đi tra.

    Chọn page ĐÃ đổ về nhiều hội thoại nhất (bật đồng bộ ưu tiên trước): đó là
    bằng chứng token còn quyền trên page đó, nên bấm chạy là ra dữ liệu thật —
    lấy đại page đầu danh sách rất hay dính "Không có quyền hạn trên trang này".
    """
    try:
        pages = integration_repo.list_pages()
    except Exception:  # noqa: BLE001 — DB chưa lên thì để trống, màn vẫn dùng được
        return ""
    xep = sorted(
        (p for p in pages if p.get("external_page_id")),
        key=lambda p: (bool(p.get("sync_enabled")), p.get("so_hoi_thoai") or 0),
        reverse=True,
    )
    return str(xep[0]["external_page_id"]) if xep else ""


def liet_ke() -> list[dict]:
    """Đưa OPS về ĐÚNG khuôn của api_catalog.liet_ke để dùng chung giao diện."""
    mac_dinh = page_mac_dinh()
    ra: list[dict] = []
    for o in OPS:
        tham_so = [
            dict(t, mac_dinh=(mac_dinh if t["ten"] == "page_id" and not t["mac_dinh"]
                              else t["mac_dinh"]))
            for t in o["tham_so"]
        ]
        ra.append({
            "method": "POST" if o["ghi"] else "GET",
            "path": f"{GOC}/{o['ma']}",
            "ten": o["ma"],
            "tag": o["nhom"][:1],
            "nhom": o["nhom"],
            "mo_ta": o["mo_ta"],
            "quyen": ["bot.view"],
            "path_params": [],
            "query": tham_so,
            "body": "",
            "chi_doc": not o["ghi"],
        })
    return ra


def _so(gia_tri: str, mac_dinh: int, tran: int = 50) -> int:
    try:
        return max(1, min(int(gia_tri or mac_dinh), tran))
    except (TypeError, ValueError):
        return mac_dinh


def _bat_buoc(tham_so: dict, ten: str) -> str:
    gia_tri = (tham_so.get(ten) or "").strip()
    if not gia_tri:
        raise ApiError("MISSING_REQUIRED_DATA", f"Thiếu tham số {ten}")
    return gia_tri


async def chay(ma: str, tham_so: dict, ghi_duoc: bool) -> dict:
    """Chạy 1 op theo whitelist. `ghi_duoc` = request tới bằng POST.

    Op ghi dữ liệu mà gọi bằng GET thì từ chối — để không ai lỡ tay đồng bộ chỉ
    vì dán đường dẫn vào thanh địa chỉ.
    """
    op = _TRA.get(ma)
    if not op:
        raise ApiError("NOT_FOUND", f"Không có việc nào tên '{ma}'")
    if op["ghi"] and not ghi_duoc:
        raise ApiError("VALIDATION_ERROR",
                       f"'{ma}' ghi dữ liệu thật — phải gọi bằng POST")

    t0 = time.monotonic()
    du_lieu: Any = await _lam(ma, tham_so)
    return {
        "viec": ma,
        "ghi_du_lieu": op["ghi"],
        "mo_ta": op["mo_ta"],
        "ms": round((time.monotonic() - t0) * 1000),
        "ket_qua": du_lieu,
    }


async def _lam(ma: str, ts: dict) -> Any:  # noqa: PLR0911 — bảng phân việc, phẳng là dễ đọc
    if ma == "chu-token":
        return client.token_owner()
    if ma == "pages":
        pages = await client.list_pages(force=True)
        return {"so_page": len(pages), "items": pages}
    if ma == "pages-dang-bat":
        pages = await client.enabled_pages()
        return {"so_page": len(pages), "items": pages}
    if ma == "the":
        the = await client.list_tags(_bat_buoc(ts, "page_id"))
        return {
            "so_the": len(the),
            "items": {str(k): v for k, v in the.items()},
            "ghi_chu": "" if the else
                       ("Không lấy được tên thẻ: page này chưa sinh được "
                        "page_access_token (cần quyền Admin trên page) và kho "
                        "thẻ đang trống — hội thoại vẫn đồng bộ được, chỉ là thẻ "
                        "hiện dưới dạng 'Thẻ #id'."),
        }
    if ma == "hoi-thoai":
        convs = await client.fetch_conversations_fresh(
            _bat_buoc(ts, "page_id"), ts.get("type") or "INBOX",
            _so(ts.get("limit"), 5))
        return {"so_hoi_thoai": len(convs), "items": convs}
    if ma == "tin-nhan":
        return await client.get_conversation(
            _bat_buoc(ts, "page_id"), _bat_buoc(ts, "conv_id"),
            (ts.get("customer_id") or "").strip() or None)
    if ma == "dong-bo-hoi-thoai":
        return await _dong_bo_hoi_thoai(ts)
    if ma == "dong-bo-tin-nhan":
        return await message_sync.dong_bo_lo(_so(ts.get("limit"), 5))
    if ma == "lam-tuoi-the":
        return await client.refresh_tags_all_pages()
    if ma == "doi-chieu":
        conv_id = _bat_buoc(ts, "conv_id")
        row = conversation_repo.doi_chieu_pancake(conv_id)
        if not row:
            return {"tim_thay": False,
                    "ghi_chu": f"Hội thoại {conv_id} chưa có trong CRM — chạy "
                               "'Đồng bộ hội thoại' của page tương ứng rồi soi lại"}
        return {"tim_thay": True, "crm": row}
    if ma == "ton-dong":
        return conversation_repo.dem_ton_dong()
    if ma == "page-trong-crm":
        pages = integration_repo.list_pages()
        return {"so_page": len(pages), "items": pages}
    raise ApiError("NOT_FOUND", f"Chưa cài đặt việc '{ma}'")


async def _dong_bo_hoi_thoai(ts: dict) -> dict:
    """Gọi Pancake lấy hội thoại tươi -> đổ vào CRM -> soi ngay kết quả.

    Trả kèm bản đối chiếu của từng hội thoại vừa đồng bộ: nhìn phát biết khách
    nào mới tạo, thẻ nào bám vào, ai đang là nhân viên xử lý.
    """
    page_id = _bat_buoc(ts, "page_id")
    convs = await client.fetch_conversations_fresh(
        page_id, ts.get("type") or "INBOX", _so(ts.get("limit"), 5))
    ten_page = ""
    for p in await client.list_pages():
        if str(p.get("id")) == page_id:
            ten_page = p.get("name") or ""
            break
    dem = crm_sync.sync_batch(page_id, ten_page or page_id, convs)
    soi = []
    for conv in convs:
        row = conversation_repo.doi_chieu_pancake(str(conv.get("conv_id") or ""))
        if row:
            soi.append({
                "conv_id": row["external_conversation_id"],
                "khach": row["khach"], "sdt": row["sdt"],
                "the": row["the"], "nhan_vien_xu_ly": row["nhan_vien_xu_ly"],
                "so_tin_da_luu": row["so_tin_da_luu"],
            })
    return {
        "page": {"external_page_id": page_id, "name": ten_page},
        "lay_ve": len(convs),
        "ket_qua_dong_bo": dem,
        "doi_chieu_trong_crm": soi,
        # `bo_qua` giờ có 2 nghĩa: page bị tắt (bỏ qua CẢ mẻ, không đụng dòng
        # nào) hoặc dòng lẻ không có định danh (crm_sync._khong_khop_duoc).
        # Chỉ nghĩa thứ nhất mới đáng nhắc người dùng đi bật lại page.
        "ghi_chu": ("Page đang TẮT đồng bộ CRM ở màn Tích hợp nên bị bỏ qua — "
                    "bật rồi chạy lại."
                    if dem.get("bo_qua") and not (dem.get("tao_moi")
                                                  or dem.get("cap_nhat")
                                                  or dem.get("loi"))
                    else ""),
    }
