"""Route bộ màn CRM tạm (khung) — /crm/*.

Chỉ đọc, chưa có thao tác ghi nên chưa gắn quyền riêng (middleware đã bắt đăng
nhập). Khi lát cắt nào làm thật thì thêm kiểm quyền màn đó (vd customer.view
cho /crm/khach-hang) cùng lúc với form thao tác.
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import co_quyen
from app.core.errors import ApiError
from app.db.repositories import crm_screens_repo as repo
from app.services import ads_service
from app.web.views import ads as views_ads
from app.web.views import chien_dich as views_cd
from app.web.views import crm as views
from app.web.views import cskh as views_cskh
from app.web.views import giam_sat as views_gs
from app.web.views import luong as views_luong
from app.web.views import sale as views_sale
from app.web.views import uu_dai as views_uu_dai
from app.web.views.admin import render_403

router = APIRouter(prefix="/crm", tags=["web-crm"])


def _nguoi(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


def _ve(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    # `path` có thể đã mang sẵn query (vd /crm/pipeline?st=3&lead=9) — nối tiếp
    # bằng "&", nối bằng "?" nữa là hỏng tham số cuối và trang đích trả 422.
    noi = "&" if "?" in path else "?"
    duoi = f"{noi}ok={quote(ok)}" if ok else (
        f"{noi}error={quote(error)}" if error else "")
    return RedirectResponse(path + duoi, status_code=303)

# Màn 2 — ánh xạ TÊN vai trò (nằm trong token, cột crm.roles.name) → nhóm
# dashboard. Vai trò lạ (tự tạo thêm ở màn phân quyền) rơi về "khac".
_NHOM_VAI_TRO = {
    "Chủ doanh nghiệp": "chu_dn",
    "Admin": "admin",
    "Trưởng nhóm Sale": "sale_tn",
    "Sale": "sale",
    "Trưởng nhóm CSKH": "cskh_tn",
    "CSKH": "cskh",
    "Marketing": "marketing",
    "Kế toán": "ke_toan",
    "Người chuyên môn": "chuyen_mon",
}


@router.get("/trang-chu", response_class=HTMLResponse)
async def trang_chu(request: Request, tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 2 — Trang chủ theo vai trò (FR-001 'chuyển tới dashboard theo vai
    trò'): 9 vị trí mỗi vị trí một bộ số + lối tắt; đăng nhập xong vào đây.

    Phạm vi số liệu: Sale/CSKH thấy CỦA MÌNH; trưởng nhóm thấy CẢ ĐỘI (tra
    teams.manager_id trong DB, không tin token); các vai còn lại xem số chung
    đúng mảng mình phụ trách.

    Chủ DN/Admin còn có khối "báo cáo cả team" theo KỲ (`?tu=&den=`, mặc định
    30 ngày gần nhất) — dùng chung tầng số liệu B11 với màn Báo cáo."""
    from app.services import report_service

    user = getattr(request.state, "user", None) or {}
    nhom = _NHOM_VAI_TRO.get(user.get("role") or "", "khac")
    data = repo.trang_chu(nhom, int(user.get("sub", 0) or 0))
    if nhom in ("chu_dn", "admin"):
        try:
            data["bc"] = report_service.bao_cao_ca_doi(tu, den, user=user)
        except ApiError:
            # kỳ lọc gõ sai (tu > den, sai định dạng) — lùi về kỳ mặc định
            data["bc"] = report_service.bao_cao_ca_doi(user=user)
    return HTMLResponse(views.render_trang_chu(nhom, data, user))


# Số hội thoại nạp cho màn Hội thoại. Đọc KHO nên không tốn lời gọi Pancake
# nào; giữ bằng mức hộp thư gộp ở màn Tin nhắn cho hai màn thấy như nhau.
_HT_LIMIT = 100


@router.get("/hoi-thoai", response_class=HTMLResponse)
async def hoi_thoai(tab: str = "all", chon: str = "", sent: int = 0,
                    error: str = "") -> HTMLResponse:
    """Màn Hội thoại — giao diện port từ mẫu crmv2.kallet.vn, DỮ LIỆU THẬT.

    Lấy CHUNG nguồn với màn Tin nhắn: danh sách đọc kho `watcher.hoi_thoai`
    (worker nền đổ về), kho rỗng mới hỏi Pancake; thread thì gọi Pancake như
    /tin-nhan. Không mở đường lấy dữ liệu thứ hai để hai màn không lệch nhau.

    `chon` = "<page_id>:<conv_id>" — phải có cả hai mới mở đúng thread, vì
    conv_id chỉ duy nhất TRONG một page.

    Chỉ đọc nên chưa gắn quyền riêng (middleware đã bắt đăng nhập); khi thêm
    thao tác ghi thì kiểm quyền ngay tại đây.
    """
    import asyncio

    from app.db.repositories import inbox_store, integration_repo, tag_store
    from app.integrations.pancake.client import (
        PancakeError, get_conversation, list_all_conversations,
    )

    convs: list[dict] = []
    tags_meta: dict = {}
    # `sent`/`error` do POST /tin-nhan/tra-loi đá ngược về sau khi gửi tin.
    loi = error
    try:
        convs = await asyncio.to_thread(inbox_store.list_recent, _HT_LIMIT)
        if not convs:
            # Kho rỗng = worker vừa bật lần đầu (hoặc bị TẮT trong .env) -> quay
            # về cách cũ để trang không bao giờ trống trơn. Giống _merged_convs.
            convs = await list_all_conversations(limit=50)
    except (PancakeError, Exception) as exc:  # noqa: BLE001 — hiện lỗi tại chỗ
        loi = f"Không nạp được danh sách hội thoại: {exc}"
    try:
        tags_meta = await asyncio.to_thread(tag_store.load_all_tags)
    except Exception:  # noqa: BLE001 — kho thẻ hỏng thì chip lùi về "Thẻ #id"
        tags_meta = {}

    mo, thread = None, None
    if chon and ":" in chon:
        pid, _, cid = chon.partition(":")
        mo = next((c for c in convs
                   if str(c.get("page_id") or "") == pid
                   and str(c.get("conv_id") or "") == cid), None)
        if mo:
            try:
                thread = await get_conversation(
                    pid, cid, str(mo.get("customer_id") or "") or None)
            except (PancakeError, Exception) as exc:  # noqa: BLE001
                loi = loi or f"Không nạp được tin nhắn: {exc}"

    # Tên người phụ trách: hội thoại chỉ mang uuid Pancake, tra một lô sang
    # `crm.staff_mappings`. KHÔNG cần uuid đã ghép tài khoản CRM — `external_name`
    # có sẵn từ lúc đồng bộ nên tên hiện được ngay.
    try:
        nhan_su = await asyncio.to_thread(
            integration_repo.ten_staff_theo_uuid,
            [u for c in convs for u in (c.get("assignee_ids") or [])])
    except Exception:  # noqa: BLE001 — thiếu tên thì nút lùi về "Chưa gán"
        nhan_su = {}

    return HTMLResponse(views.render_hoi_thoai(
        convs, mo, thread, tab=tab, tags_meta=tags_meta, loi=loi,
        da_gui=bool(sent), nhan_su=nhan_su))


@router.get("/tong-quan", response_class=HTMLResponse)
async def tong_quan(request: Request, tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 4 (B11 — THẬT) — dashboard công ty: mọi ô số bấm ra danh sách
    (FR-173); ô doanh thu/chi phí tự ẩn theo quyền người xem."""
    from app.services import report_service
    from app.web.views import reports as views_bc

    user = _nguoi(request)
    return HTMLResponse(views_bc.render_tong_quan(
        report_service.dashboard(tu, den, user=user), user))


def _ds_nhan_vien(vai: tuple[str, ...]) -> list[dict]:
    from app.db.repositories import user_repo

    return [u for u in user_repo.list_users(status="active", limit=200)[0]
            if u.get("role_name") in vai]


def _chon_user(request: Request, users: list[dict], user_id: int) -> int:
    """Màn 5-6: quản lý chọn người; không truyền thì lấy CHÍNH MÌNH nếu có
    trong danh sách, rớt xuống người đầu tiên."""
    if user_id and any(u["id"] == user_id for u in users):
        return user_id
    minh = int(_nguoi(request).get("sub", 0) or 0)
    if any(u["id"] == minh for u in users):
        return minh
    return users[0]["id"] if users else 0


@router.get("/dashboard-sale", response_class=HTMLResponse)
async def dashboard_sale(request: Request, user_id: int = 0,
                         tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 5 (B11 — THẬT) — dashboard TỪNG Sale."""
    from app.services import report_service
    from app.web.views import reports as views_bc

    users = _ds_nhan_vien(("Sale", "Trưởng nhóm Sale"))
    chon = _chon_user(request, users, user_id)
    return HTMLResponse(views_bc.render_dashboard_sale(
        report_service.dashboard_sale(chon, tu, den), users, chon))


@router.get("/dashboard-cskh", response_class=HTMLResponse)
async def dashboard_cskh(request: Request, user_id: int = 0,
                         tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 6 (B11 — THẬT) — dashboard TỪNG CSKH."""
    from app.services import report_service
    from app.web.views import reports as views_bc

    users = _ds_nhan_vien(("CSKH", "Trưởng nhóm CSKH"))
    chon = _chon_user(request, users, user_id)
    return HTMLResponse(views_bc.render_dashboard_cskh(
        report_service.dashboard_cskh(chon, tu, den), users, chon))


@router.get("/bao-cao", response_class=HTMLResponse)
async def bao_cao(request: Request, tab: str = "sale",
                  tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 60-64 (B11 — THẬT) — báo cáo kỳ theo tab; tab đòi quyền nào thì
    kiểm quyền đó (doanh thu = revenue.view, marketing = ads.view)."""
    from app.services import report_service
    from app.web.views import reports as views_bc

    user = _nguoi(request)
    can = {"sale": "revenue.view", "don-hang": "revenue.view",
           "doanh-thu": "revenue.view", "marketing": "ads.view"}
    loi = ""
    data: dict = {"ky": {"tu": tu, "den": den}}
    quyen = can.get(tab, "customer.view")
    if not co_quyen(user, quyen):
        loi = f"Tab này cần quyền {quyen} — liên hệ Admin nếu cần cấp"
    else:
        try:
            data = {
                "sale": report_service.bao_cao_sale,
                "cskh": report_service.bao_cao_cskh,
                "marketing": report_service.bao_cao_marketing,
                "don-hang": report_service.bao_cao_don_hang,
                "doanh-thu": report_service.bao_cao_doanh_thu,
                "mua-lai": report_service.bao_cao_mua_lai,
                "cong-viec": report_service.bao_cao_cong_viec,
            }.get(tab, report_service.bao_cao_sale)(tu, den)
        except ApiError as err:
            loi = err.message
    if tab not in ("sale", "cskh", "marketing", "don-hang", "doanh-thu",
                   "mua-lai", "cong-viec"):
        tab = "sale"
    return HTMLResponse(views_bc.render_bao_cao(tab, data, loi=loi))


@router.get("/bao-cao/chi-tiet", response_class=HTMLResponse)
async def bao_cao_chi_tiet(request: Request, metric: str,
                           tu: str = "", den: str = "",
                           user_id: int = 0) -> HTMLResponse:
    """REPORT-010 trên web — trang danh sách mà mọi ô số trỏ tới (FR-173)."""
    from app.services import report_service
    from app.web.views import reports as views_bc

    try:
        kq = report_service.drill_down(metric, tu, den, user_id or None,
                                       user=_nguoi(request))
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Chi tiết báo cáo"),
                            status_code=403 if err.code == "FORBIDDEN" else 404)
    return HTMLResponse(views_bc.render_chi_tiet(kq))


@router.get("/bao-cao/xuat")
async def bao_cao_xuat(request: Request, metric: str,
                       tu: str = "", den: str = "", user_id: int = 0):
    """REPORT-011 trên web — tải CSV (quyền data.export + quyền metric)."""
    from fastapi.responses import PlainTextResponse

    from app.services import report_service

    try:
        noi_dung, ten_file = report_service.xuat_csv(
            metric, tu, den, user_id or None, user=_nguoi(request))
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Xuất báo cáo"),
                            status_code=403)
    return PlainTextResponse(
        noi_dung, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ten_file}"'})


def _so_tien(v: str) -> float | None:
    """Ô "Chi tiêu từ … đến …" nhập bằng TRIỆU -> đồng. Rỗng/rác -> bỏ lọc."""
    try:
        return float(str(v).replace(",", ".")) * 1_000_000
    except (TypeError, ValueError):
        return None


@router.get("/khach-hang", response_class=HTMLResponse)
async def khach_hang(q: str = "", tt: str = "", bucket: str = "",
                     owner_id: int = 0, page_id: int = 0, mua: str = "",
                     chi_tu: str = "", chi_den: str = "", tier: str = "",
                     size: int = 30, trang: int = 1) -> HTMLResponse:
    """Màn 8 — danh sách khách CRM (khác /khach-hang của bot Pancake).

    Bố cục port từ mẫu Kallet: 5 ô đếm · dải lọc · bảng 11 cột · phân trang.
    Mọi con số đếm thẳng từ schema `crm` (xem quy ước ở `khach_hang_bang`);
    phần mẫu có mà dữ liệu chưa dựng nổi thì view khoá lại (lớp `ht-todo`).
    """
    from app.db.repositories import user_repo
    from app.services import voucher_service

    size = size if size in (30, 50, 100) else 30
    trang = max(1, trang)
    tien_tu, tien_den = _so_tien(chi_tu), _so_tien(chi_den)
    rows, total = repo.khach_hang_bang(
        q=q, tt=tt, bucket=bucket, owner_id=owner_id, page_id=page_id,
        so_mua=mua, chi_tu=tien_tu, chi_den=tien_den, tier=tier,
        limit=size, offset=(trang - 1) * size)
    # Bấm nút "trang sau" rồi siết bộ lọc lại: trang đang đứng có thể vượt quá
    # số trang mới -> bảng trống hoác dù vẫn còn khách. Kéo về trang cuối.
    so_trang = max(1, -(-total // size))
    if trang > so_trang:
        trang = so_trang
        rows, total = repo.khach_hang_bang(
            q=q, tt=tt, bucket=bucket, owner_id=owner_id, page_id=page_id,
            so_mua=mua, chi_tu=tien_tu, chi_den=tien_den, tier=tier,
            limit=size, offset=(trang - 1) * size)
    nv = user_repo.list_users(status="active", limit=200)[0]
    return HTMLResponse(views.render_khach_hang(
        rows, total,
        dem=repo.khach_hang_dem(),
        loc={"q": q, "tt": tt, "bucket": bucket, "owner_id": owner_id,
             "page_id": page_id, "mua": mua, "chi_tu": chi_tu,
             "chi_den": chi_den, "tier": tier, "size": size, "trang": trang},
        nhan_vien=nv, fanpages=repo.khach_hang_fanpages(),
        hang_the=voucher_service.bac_thang()))


# ------------------------------------------------------- hồ sơ 360° (màn 9-10)
@router.get("/khach-hang/gop-trung", response_class=HTMLResponse)
async def gop_trung(ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 10 — hợp nhất khách trùng. Khai TRƯỚC `/{customer_id}` để không bị
    route số nuốt mất."""
    from app.db.repositories import profile_repo
    from app.web.views import profile as views_hs

    return HTMLResponse(views_hs.render_gop_trung(
        profile_repo.nghi_trung(), ok_msg=ok, error=error))


@router.post("/gop-trung")
async def gop_trung_chay(request: Request):
    """FR-022 — gộp các hồ sơ phụ vào hồ sơ chính (hồ sơ phụ -> merged)."""
    from app.services import customer_service

    if not co_quyen(_nguoi(request), "customer.edit"):
        return HTMLResponse(
            render_403("Gộp khách cần quyền customer.edit", heading="Gộp khách"),
            status_code=403)
    form = await request.form()
    try:
        chinh = int(form.get("chinh") or 0)
        tat_ca = [int(x) for x in form.getlist("ids")]
    except (TypeError, ValueError):
        return _ve("/crm/khach-hang/gop-trung", error="Dữ liệu không hợp lệ")
    phu = [i for i in tat_ca if i != chinh]
    try:
        kq = customer_service.merge_customers(
            primary_id=chinh, duplicate_ids=phu,
            actor_id=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/khach-hang/gop-trung", error=err.message)
    # merge_customers trả {"primary": <khách>, "da_don": {bảng: số dòng}}
    da_don = sum((kq.get("da_don") or {}).values())
    return _ve("/crm/khach-hang/gop-trung",
               ok=f"Đã gộp {len(phu)} hồ sơ vào #{chinh} — dồn {da_don} bản ghi")


@router.get("/khach-hang/{customer_id}", response_class=HTMLResponse)
async def ho_so_khach(customer_id: int, tab: str = "tong-quan",
                      conv: int = 0) -> HTMLResponse:
    """Màn 9 — hồ sơ khách hàng 360°, 9 khu vực theo tab (nạp đúng tab đang xem)."""
    from app.db.repositories import profile_repo
    from app.web.views import profile as views_hs

    kh = profile_repo.tong_quan(customer_id)
    if not kh:
        return HTMLResponse(
            render_403("Không tìm thấy khách hàng", heading="Hồ sơ khách"),
            status_code=404)

    if tab == "hoi-thoai":
        ds = profile_repo.hoi_thoai(customer_id)
        for r in ds:                      # view cần biết đang ở hồ sơ nào để dựng link
            r["customer_id"] = customer_id
        data = {"hoi_thoai": ds,
                "tin": profile_repo.tin_nhan_gan_nhat(conv) if conv else []}
    elif tab == "tu-van":
        data = profile_repo.ho_so_tu_van(customer_id)
    elif tab == "lieu-trinh":
        data = profile_repo.lieu_trinh(customer_id)
    elif tab == "don-hang":
        data = profile_repo.don_hang(customer_id)
    elif tab == "cham-soc":
        data = profile_repo.cham_soc(customer_id)
    elif tab == "marketing":
        data = profile_repo.marketing(customer_id)
    elif tab == "lich-su":
        data = profile_repo.lich_su(customer_id)
    elif tab == "cuoc-goi":
        data = None            # C-MVP3 chưa làm — view tự bày lời nhắn
    else:
        tab, data = "tong-quan", None
    return HTMLResponse(views_hs.render_ho_so(kh, tab, data, conv_mo=conv))


# ------------------------------------------------- tư vấn (màn 13 · 14 · 15)
def _du_lieu_tu_van(customer_id: int, tab: str) -> dict:
    """Gom dữ liệu cho đúng tab đang mở của khu Tư vấn."""
    from app.db.repositories import catalog_repo, consult_repo, profile_repo
    from app.services import consult_service, treatment_service

    d: dict = {
        "sang_loc": consult_service.SANG_LOC,
        "cau_hoi": consult_service.CAU_HOI_BAT_BUOC,
        "da_sang_loc": {r["screening_type"]: r
                        for r in consult_repo.list_active_screenings(customer_id)},
    }
    if tab == "khai-thac":
        d["trieu_chung"] = consult_repo.list_customer_symptoms(customer_id)
        d["danh_muc_trieu_chung"] = consult_repo.list_symptom_catalog()
        return d

    if tab == "de-xuat":
        d["da_de_xuat"] = profile_repo.lieu_trinh(customer_id)["de_xuat"]
        try:
            d["ket_qua"] = treatment_service.recommend(customer_id)
        except ApiError as err:
            # Cờ đỏ (TREATMENT_BLOCKED) và thiếu dữ liệu là hai tình huống KHÁC
            # nhau — màn phải nói rõ cái nào, đừng gộp thành "có lỗi".
            if err.code in ("TREATMENT_BLOCKED", "CLINICAL_REVIEW_REQUIRED"):
                d["bi_chan"] = err.message
            else:
                d["thieu_du_lieu"] = err.message
        return d

    # tab tư vấn (màn 13)
    hoi = profile_repo.hoi_thoai_moi_nhat(customer_id) or {}
    d["external_page_id"] = hoi.get("external_page_id")
    d["external_conversation_id"] = hoi.get("external_conversation_id")
    d["tin"] = (profile_repo.tin_nhan_gan_nhat(hoi["id"], 30)
                if hoi.get("id") else [])
    d["da_co"] = profile_repo.checklist_tu_van(customer_id)
    try:
        d["lieu_trinh_goi_y"] = treatment_service.recommend(customer_id).get(
            "de_xuat") or []
    except ApiError:
        d["lieu_trinh_goi_y"] = catalog_repo.list_active_templates_with_rules()[:5]
    return d


@router.get("/tu-van/{customer_id}", response_class=HTMLResponse)
async def tu_van(customer_id: int, tab: str = "tu-van", ok: str = "",
                 error: str = "") -> HTMLResponse:
    """Màn 13-14-15 — khu làm việc tư vấn của Sale, 3 tab liền mạch."""
    from app.db.repositories import profile_repo
    from app.web.views import consult as views_tv

    kh = profile_repo.tong_quan(customer_id)
    if not kh:
        return HTMLResponse(render_403("Không tìm thấy khách hàng",
                                       heading="Tư vấn"), status_code=404)
    if tab not in ("tu-van", "khai-thac", "de-xuat"):
        tab = "tu-van"
    return HTMLResponse(views_tv.render_tu_van(
        kh, tab, _du_lieu_tu_van(customer_id, tab), ok_msg=ok, error=error))


@router.post("/tu-van/{customer_id}/trieu-chung")
async def luu_trieu_chung(request: Request, customer_id: int):
    """SYMPTOM-002 — lưu 1 dòng triệu chứng (FR-050 đòi dữ liệu cấu trúc)."""
    from app.services import consult_service

    if chan := _chan_sua(request):
        return chan
    f = await request.form()
    ve = f"/crm/tu-van/{customer_id}?tab=khai-thac"
    try:
        consult_service.save_symptom(
            customer_id, symptom_id=int(f.get("symptom_id") or 0),
            data={
                "severity": int(f["severity"]) if f.get("severity") else None,
                "frequency": str(f.get("frequency") or "") or None,
                "meal_relation": str(f.get("meal_relation") or "") or None,
                "occurs_when": str(f.get("occurs_when") or "") or None,
                "note": str(f.get("note") or "") or None,
            },
            actor=_nguoi(request))
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok="Đã lưu triệu chứng")


@router.post("/tu-van/{customer_id}/sang-loc")
async def luu_sang_loc(request: Request, customer_id: int):
    """SAFETY-001 — ghi 1 mục sàng lọc; đỏ thì service tự mở ca + gắn cờ."""
    from app.services import consult_service

    if chan := _chan_sua(request):
        return chan
    f = await request.form()
    ve = f"/crm/tu-van/{customer_id}?tab=khai-thac"
    try:
        kq = consult_service.add_screening(
            customer_id, screening_type=str(f.get("screening_type") or ""),
            value=str(f.get("value") or "") or None, actor=_nguoi(request))
    except ApiError as err:
        return _ve(ve, error=err.message)
    co = (kq.get("safety_check") or {}).get("flag")
    them = " — khách chuyển CỜ ĐỎ, đề xuất bị chặn" if co == "red" else ""
    return _ve(ve, ok=f"Đã ghi mục sàng lọc{them}")


@router.post("/tu-van/{customer_id}/chon-lieu-trinh")
async def chon_lieu_trinh(request: Request, customer_id: int):
    """TREATMENT-010 — Sale chọn mẫu -> LƯU phiên bản đề xuất (có cảnh báo thì
    tự chuyển chờ chuyên môn duyệt)."""
    from app.services import treatment_service

    if chan := _chan_sua(request):
        return chan
    f = await request.form()
    ve = f"/crm/tu-van/{customer_id}?tab=de-xuat"
    try:
        kq = treatment_service.recommend(
            customer_id, template_id=int(f.get("template_id") or 0),
            note=str(f.get("note") or "") or None, actor=_nguoi(request))
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    cho_duyet = (kq or {}).get("status") == "pending_approval"
    return _ve(ve, ok="Đã lưu đề xuất"
               + (" — CHỜ Người chuyên môn duyệt mới tạo được liệu trình"
                  if cho_duyet else ""))


@router.post("/tu-van/{customer_id}/chuyen-chuyen-mon")
async def chuyen_chuyen_mon(request: Request, customer_id: int):
    """SAFETY-003 — Sale chủ động chuyển ca cho Người chuyên môn."""
    from app.services import consult_service

    if chan := _chan_sua(request):
        return chan
    f = await request.form()
    ve = f"/crm/tu-van/{customer_id}"
    try:
        consult_service.create_escalation(
            customer_id, reason=str(f.get("reason") or ""), actor=_nguoi(request))
    except ApiError as err:
        return _ve(ve, error=err.message)
    return _ve(ve, ok="Đã chuyển ca cho Người chuyên môn")


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline(request: Request, st: int = 0, lead: int = 0, q: str = "",
                   owner_id: int = 0, temperature: str = "", moc: str = "",
                   tu: str = "", den: str = "", xem: str = "",
                   ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 11 — bảng chăm sóc theo mốc (khách tiềm năng của Sale).

    `st`   cột đang mở (khối Sale ở menu trái trỏ vào đây);
    `lead` khách đang chọn — mở khung làm việc bên phải, luôn kéo theo cột của
           chính khách đó nên bấm thẳng từ chế độ Bảng cũng vào đúng cột;
    còn lại là bộ lọc: tìm kiếm · nhân viên · nhiệt độ · mốc chăm · ngày tạo.
    """
    from app.db.repositories import catalog_screen_repo

    ho_so = repo.pipeline_lead(lead) if lead else None
    if ho_so is not None:
        st = ho_so["stage_id"]          # chọn khách = mở đúng cột khách đứng
    board = repo.pipeline_board(
        # chế độ Bảng liệt kê MỌI giai đoạn (st chỉ còn dùng để mở sẵn đúng khối)
        st=0 if xem == "bang" else st,
        q=q, owner_id=owner_id or None, temperature=temperature,
        moc=moc, tu=tu, den=den,
        # xem 1 cột / chế độ Bảng thì lấy dày hơn (bày 13 cột một lúc mới cần gọn)
        moi_cot=60 if (st or xem == "bang") else 10,
    )
    return HTMLResponse(views.render_pipeline(
        board, st=st, lead=ho_so,
        loc={"st": st, "lead": lead if ho_so else 0, "q": q,
             "owner_id": owner_id, "temperature": temperature, "moc": moc,
             "tu": tu, "den": den, "xem": xem},
        nhan_vien=_ds_nhan_vien(("Sale", "Trưởng nhóm Sale")),
        ly_do=catalog_screen_repo.danh_muc_ly_do() if ho_so else [],
        ok_msg=ok, error=error))


# --- thao tác trên khung làm việc màn 11 (luật nằm ở app/services/lead_service)
def _chan_sua_lead(request: Request) -> HTMLResponse | None:
    if not co_quyen(_nguoi(request), "customer.edit"):
        return HTMLResponse(
            render_403("Chăm khách tiềm năng cần quyền customer.edit",
                       heading="Bảng chăm sóc"), status_code=403)
    return None


def _gio(v: str):
    """`<input type=datetime-local>` trả 'YYYY-MM-DDTHH:MM' (giờ máy người dùng)
    — gắn múi giờ máy chủ vào cho thành mốc tuyệt đối. Chuỗi lạ -> None."""
    from datetime import datetime

    try:
        return datetime.fromisoformat((v or "").strip()).astimezone()
    except ValueError:
        return None


def _so(v) -> int:
    """Số trong form (do người dùng gửi lên) — không phải số thì coi như 0."""
    try:
        return int(str(v or "").strip() or 0)
    except ValueError:
        return 0


@router.post("/pipeline/{lead_id}/giai-doan")
async def lead_chuyen_giai_doan(request: Request, lead_id: int):
    """Chuyển cột — đi qua đủ luật chặn FR-040, sai luật thì hiện lỗi lên màn."""
    from app.services import lead_service

    if chan := _chan_sua_lead(request):
        return chan
    f = await request.form()
    ve = str(f.get("ve") or f"/crm/pipeline?lead={lead_id}")
    try:
        kq = lead_service.move_stage(
            lead_id=lead_id, to_stage_id=_so(f.get("stage_id")),
            actor_id=int(_nguoi(request).get("sub", 0)) or None,
            reason=str(f.get("reason") or "").strip() or None,
            next_action_at=_gio(str(f.get("next_action_at") or "")),
            # Đóng ở Từ chối / Không phù hợp / Mất liên lạc: service tự ghi
            # lead_lost_reasons rồi mới cho đóng (FR-040, LEAD-010)
            lost_reason_id=_so(f.get("lost_reason_id")) or None)
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok=f"Đã chuyển sang '{kq['stage_name']}'")


@router.post("/pipeline/{lead_id}/hen")
async def lead_dat_hen(request: Request, lead_id: int):
    """Đặt mốc chăm tiếp theo (next_action_at) — dải 'Hôm nay/Sắp tới' đọc mốc này."""
    from app.services import lead_service

    if chan := _chan_sua_lead(request):
        return chan
    f = await request.form()
    ve = str(f.get("ve") or f"/crm/pipeline?lead={lead_id}")
    try:
        lead_service.update_lead(
            lead_id, {"next_action_at": _gio(str(f.get("next_action_at") or ""))},
            actor_id=int(_nguoi(request).get("sub", 0)) or None)
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok="Đã đặt lịch nhắc lại")


@router.post("/pipeline/{lead_id}/nhiet")
async def lead_doi_nhiet(request: Request, lead_id: int):
    """Đổi nhiệt độ lead (nóng/ấm/lạnh) — dùng cho bộ lọc và ô '🔥 Đang nóng'."""
    from app.services import lead_service

    if chan := _chan_sua_lead(request):
        return chan
    f = await request.form()
    ve = str(f.get("ve") or f"/crm/pipeline?lead={lead_id}")
    nhiet = str(f.get("temperature") or "")
    if nhiet not in ("nong", "am", "lanh"):   # CHECK ck_leads_temperature
        return _ve(ve, error="Nhiệt độ chỉ nhận nóng / ấm / lạnh")
    try:
        lead_service.update_lead(
            lead_id, {"temperature": nhiet},
            actor_id=int(_nguoi(request).get("sub", 0)) or None)
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok="Đã đổi nhiệt độ khách")


@router.post("/pipeline/{lead_id}/chia-lai")
async def lead_chia_lai(request: Request, lead_id: int):
    """Chuyển khách sang nhân viên khác — FR-031 bắt buộc lý do khi đã có người giữ."""
    from app.services import lead_service

    if chan := _chan_sua_lead(request):
        return chan
    f = await request.form()
    ve = str(f.get("ve") or f"/crm/pipeline?lead={lead_id}")
    try:
        lead_service.assign_owner(
            lead_id=lead_id, new_owner_id=_so(f.get("owner_id")),
            reason=str(f.get("reason") or "").strip() or None,
            actor_id=int(_nguoi(request).get("sub", 0)) or None)
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok="Đã chuyển khách cho nhân viên khác")


@router.get("/cong-viec", response_class=HTMLResponse)
async def cong_viec(request: Request, pham_vi: str = "minh") -> HTMLResponse:
    """Màn 12 + 26 — việc quá hạn / hôm nay / sắp tới (B4 đổ dữ liệu thật).

    Mặc định chỉ việc CỦA NGƯỜI ĐANG ĐĂNG NHẬP (BRD: màn 'việc hôm nay' là
    của từng người); `?pham_vi=tatca` xem cả đội — trưởng nhóm/giám sát dùng.
    """
    user = getattr(request.state, "user", None) or {}
    cua_ai = None if pham_vi == "tatca" else int(user.get("sub", 0)) or None
    return HTMLResponse(views.render_cong_viec(
        repo.tasks_groups(assigned_to=cua_ai), pham_vi=pham_vi,
    ))


# ------------------------------------------------------------ Đơn hàng (màn 21)
# Bộ lọc của màn — TÊN Ở ĐÂY LÀ HỢP ĐỒNG với view (`_url` dựng lại link từ
# chính bộ này) và với don_hang_repo._loc. Thêm ô lọc thì thêm cả ba chỗ.
_DH_LOC = ("q", "status", "order_type", "effort", "ads", "nv", "nv_pos",
           "page", "ky", "ky_han", "tu", "den")


def _dh_doc_loc(tham: dict) -> tuple[dict, dict]:
    """(bộ lọc gửi xuống repo, bộ lọc để vẽ lại màn) từ tham số URL.

    Khoảng thời gian: ô chọn nhanh (`ky_han`) đặt tu/den; người gõ tay ngày thì
    `ky_han` tự thành 'tuy_chon'. `den` cộng 1 ngày trước khi xuống repo vì SQL
    so `<` — không cộng là mất trọn đơn của chính ngày cuối kỳ.
    """
    from datetime import date, timedelta

    from app.services import don_hang_service as dv

    tu, den = (tham.get("tu") or ""), (tham.get("den") or "")
    ma_ky = tham.get("ky_han") or ("tuy_chon" if (tu or den) else "all")
    _, tu, den = dv.khoang_ngay(ma_ky, tu, den)
    ve = {k: (tham.get(k) or "") for k in _DH_LOC}
    ve.update({"ky_han": ma_ky, "tu": tu, "den": den})
    den_sql = ""
    if den:
        try:
            den_sql = (date.fromisoformat(den) + timedelta(days=1)).isoformat()
        except ValueError:
            den_sql = ""
    xuong = {k: ve[k] for k in ("q", "status", "order_type", "effort", "ads",
                                "nv_pos", "ky")}
    xuong.update({"nv": int(ve["nv"]) if str(ve["nv"]).isdigit() else 0,
                  "page": ve["page"], "tu": tu, "den": den_sql})
    return xuong, ve


@router.get("/don-hang", response_class=HTMLResponse)
async def don_hang(request: Request, q: str = "", status: str = "",
                   order_type: str = "", effort: str = "", ads: str = "",
                   nv: str = "", nv_pos: str = "", page: str = "",
                   ky: str = "", ky_han: str = "", tu: str = "", den: str = "",
                   sort: str = "ngay", dir: str = "desc",  # noqa: A002
                   size: int = 30, trang: int = 1) -> HTMLResponse:
    """Màn 21 — danh sách đơn (C7, port `don-hang.php` của mẫu Kallet).

    5 thẻ chỉ số · dải lọc 10 ô · bảng 11 cột · phân trang · tích chọn hàng
    loạt · xuất Excel chọn cột. Phạm vi xem do `don_hang_service.pham_vi` quyết
    (không có `revenue.view` thì chỉ thấy đơn mình phụ trách).
    """
    from app.db.repositories import don_hang_repo, user_repo
    from app.services import don_hang_service as dv
    from app.web.views import don_hang as views_dh

    user = _nguoi(request)
    xuong, ve = _dh_doc_loc(locals())
    try:
        data = dv.man_hinh(xuong, sort=sort, dir_=dir, size=size,
                           trang=trang, user=user)
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Đơn hàng"),
                            status_code=403)
    ve.update({"sort": sort, "dir": dir, "size": data["size"],
               "trang": data["trang"]})
    return HTMLResponse(views_dh.render(
        data, ve,
        nhan_vien=user_repo.list_users(limit=500)[0],
        nv_pos=don_hang_repo.nhan_vien_pos(),
        pages=don_hang_repo.fanpages(),
        ky_luong=don_hang_repo.ky_luong(),
        co_xuat=co_quyen(user, "data.export"),
    ))


@router.get("/don-hang/xuat")
async def don_hang_xuat(request: Request, q: str = "", status: str = "",
                        order_type: str = "", effort: str = "", ads: str = "",
                        nv: str = "", nv_pos: str = "", page: str = "",
                        ky: str = "", ky_han: str = "", tu: str = "",
                        den: str = "", sort: str = "ngay",
                        dir: str = "desc") -> HTMLResponse:  # noqa: A002
    """Xuất CSV TOÀN BỘ đơn khớp bộ lọc (nút ở dải lọc). `cols` lặp nhiều lần.

    Đọc `cols` từ request.query_params chứ không khai tham số: FastAPI cần
    `Query(...)` cho danh sách, mà cả màn này đang dùng tham số trơn — đọc tay
    một chỗ gọn hơn đổi chữ ký cả hai route.
    """
    from fastapi.responses import PlainTextResponse

    from app.services import don_hang_service as dv

    xuong, _ = _dh_doc_loc(locals())
    try:
        noi_dung, ten = dv.xuat_csv(
            xuong, request.query_params.getlist("cols"),
            sort=sort, dir_=dir, user=_nguoi(request))
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Xuất đơn hàng"),
                            status_code=403)
    return PlainTextResponse(
        noi_dung, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ten}"'})


@router.post("/don-hang/xuat")
async def don_hang_xuat_tich(request: Request):
    """Xuất CSV những đơn ĐÃ TÍCH (thanh nổi). `ca_bo_loc=1` thì bỏ qua danh
    sách id và xuất cả bộ lọc — 53k id nhét vào form POST là request vài trăm
    KB, để server tự truy vấn lại nhẹ hơn nhiều."""
    from fastapi.responses import PlainTextResponse

    from app.services import don_hang_service as dv

    form = await request.form()
    tham = {k: (form.get(k) or "") for k in (*_DH_LOC, "sort", "dir")}
    xuong, _ = _dh_doc_loc(tham)
    ids = None
    if form.get("ca_bo_loc") != "1":
        ids = [int(x) for x in form.getlist("ids") if str(x).isdigit()]
    try:
        noi_dung, ten = dv.xuat_csv(
            xuong, form.getlist("cols"), ids=ids,
            sort=tham.get("sort") or "ngay", dir_=tham.get("dir") or "desc",
            user=_nguoi(request))
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Xuất đơn hàng"),
                            status_code=403)
    return PlainTextResponse(
        noi_dung, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ten}"'})


@router.get("/don-hang/{order_id}", response_class=HTMLResponse)
async def chi_tiet_don(order_id: int) -> HTMLResponse:
    """Màn 22 — chi tiết đơn: hàng · tiền · giao nhận · lịch sử · liên quan."""
    from app.db.repositories import profile_repo
    from app.web.views import profile as views_hs

    don = profile_repo.chi_tiet_don(order_id)
    if not don:
        return HTMLResponse(
            render_403("Không tìm thấy đơn hàng", heading="Đơn hàng"),
            status_code=404)
    return HTMLResponse(views_hs.render_chi_tiet_don(don))


# ------------------------------------------------------------ thông báo (màn 3)
@router.get("/thong-bao", response_class=HTMLResponse)
async def thong_bao(request: Request, type: str = "", chua_doc: int = 0,
                    ok: str = "") -> HTMLResponse:
    """Màn 3 — trung tâm thông báo của NGƯỜI ĐANG ĐĂNG NHẬP (11 loại)."""
    from app.services import notification_service as tb

    uid = int(_nguoi(request).get("sub") or 0)
    rows, total = tb.danh_sach(uid, chua_doc=bool(chua_doc), type_=type, limit=100)
    return HTMLResponse(views.render_thong_bao(
        rows, total, tb.dem_chua_doc(uid), tb.LOAI, type, bool(chua_doc),
        tb.lay_cai_dat(_nguoi(request))["items"], ok_msg=ok,
    ))


@router.post("/thong-bao/doc-het")
async def thong_bao_doc_het(request: Request):
    from app.services import notification_service as tb

    kq = tb.danh_dau_doc_het(_nguoi(request))
    return _ve("/crm/thong-bao", ok=f"Đã đánh dấu {kq['da_danh_dau']} thông báo")


@router.post("/thong-bao/cai-dat")
async def thong_bao_cai_dat(request: Request):
    """NOTIFY-004 trên web. Checkbox KHÔNG tick thì trình duyệt không gửi lên —
    phải dựng đủ 11 loại từ danh mục rồi mới biết cái nào tắt."""
    from app.services import notification_service as tb

    form = await request.form()
    doi = {ma: (ma in form) for ma in tb.LOAI}
    try:
        tb.dat_cai_dat(doi, _nguoi(request))
    except ApiError as err:
        return _ve("/crm/thong-bao", error=err.message)
    return _ve("/crm/thong-bao", ok="Đã lưu cài đặt thông báo")


@router.post("/thong-bao/{notification_id}/da-doc")
async def thong_bao_da_doc(request: Request, notification_id: int):
    from app.services import notification_service as tb

    try:
        tb.danh_dau_doc(notification_id, _nguoi(request))
    except ApiError as err:
        return _ve("/crm/thong-bao", error=err.message)
    return _ve("/crm/thong-bao")


# ------------------------------------------------------------ bàn giao (B8)
@router.get("/ban-giao", response_class=HTMLResponse)
async def ban_giao(tt: str = "") -> HTMLResponse:
    """Màn 24 (B8 — THẬT) — danh sách phiếu bàn giao, lọc `?tt=` trạng thái."""
    from app.db.repositories import handover_repo
    from app.services import handover_service

    rows, total = handover_service.danh_sach(status=tt, limit=100)
    return HTMLResponse(views.render_ban_giao(
        rows, total, handover_repo.dem_theo_trang_thai(), tt))


def _phieu(handover_id: int, ok: str = "", error: str = "") -> HTMLResponse:
    from app.db.repositories import user_repo
    from app.services import handover_service

    try:
        h = handover_service.chi_tiet(handover_id)
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Bàn giao"),
                            status_code=404)
    cskh = [u for u in user_repo.list_users(status="active", limit=100)[0]
            if u.get("role_name") == "CSKH"]
    return HTMLResponse(views.render_phieu_ban_giao(h, cskh, ok_msg=ok, error=error))


@router.get("/ban-giao/{handover_id}", response_class=HTMLResponse)
async def phieu_ban_giao(handover_id: int, ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 25 (B8 — THẬT) — phiếu bàn giao + hành động nhận/trả/gán."""
    return _phieu(handover_id, ok=ok, error=error)


def _chan_sua(request: Request) -> HTMLResponse | None:
    if not co_quyen(_nguoi(request), "customer.edit"):
        return HTMLResponse(
            render_403("Thao tác bàn giao cần quyền customer.edit",
                       heading="Bàn giao"), status_code=403)
    return None


@router.post("/ban-giao/{handover_id}/luu")
async def luu_phieu(request: Request, handover_id: int):
    from app.services import handover_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    data = {k: (str(v).strip() or None) for k, v in form.items()}
    try:
        handover_service.cap_nhat_phieu(handover_id, data, actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/ban-giao/{handover_id}", error=err.message)
    return _ve(f"/crm/ban-giao/{handover_id}", ok="Đã lưu phiếu")


@router.post("/ban-giao/{handover_id}/nhan")
async def nhan_ban_giao(request: Request, handover_id: int):
    from app.services import handover_service

    if chan := _chan_sua(request):
        return chan
    try:
        handover_service.nhan(handover_id, actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/ban-giao/{handover_id}", error=err.message)
    return _ve(f"/crm/ban-giao/{handover_id}", ok="Đã nhận bàn giao — khách thuộc CSKH này")


@router.post("/ban-giao/{handover_id}/tra-lai")
async def tra_lai_ban_giao(request: Request, handover_id: int):
    from app.services import handover_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    try:
        handover_service.tra_lai(handover_id, str(form.get("reason") or ""),
                                 actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/ban-giao/{handover_id}", error=err.message)
    return _ve(f"/crm/ban-giao/{handover_id}", ok="Đã trả lại Sale kèm việc bổ sung")


@router.post("/ban-giao/{handover_id}/gan")
async def gan_cskh_ban_giao(request: Request, handover_id: int):
    from app.services import handover_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    try:
        handover_service.gan_cskh(handover_id, int(form.get("user_id") or 0),
                                  actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/ban-giao/{handover_id}", error=err.message)
    return _ve(f"/crm/ban-giao/{handover_id}", ok="Đã gán CSKH")


@router.get("/cham-soc", response_class=HTMLResponse)
async def cham_soc() -> HTMLResponse:
    """Màn 27 (B9 — THẬT) — pipeline C01-C09 + mốc chờ làm + kế hoạch chạy."""
    return HTMLResponse(views.render_cham_soc(repo.care_board()))


def _man_ke_hoach(plan_id: int, ok: str = "", error: str = "") -> HTMLResponse:
    from app.db.repositories import care_repo
    from app.services import care_service

    try:
        plan = care_service.chi_tiet(plan_id)
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Chăm sóc"),
                            status_code=404)
    bo = {t: care_repo.bo_gia_tri(t)
          for t in ("adherence_level", "diet_compliance", "adverse_event",
                    "bowel_status", "repurchase_readiness", "contact_result",
                    "next_action")}
    from app.db.client import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        rs = [(r["code"], r["name"]) for r in conn.execute(
            "select code, name from crm.ref_codes where group_code='care_result' "
            "and status='active' order by code limit 6").fetchall()]
    # màn 38: chuỗi không phản hồi đang chạy của khách (kèm các lần chạm)
    chuoi = care_repo.chuoi_dang_chay(plan["customer_id"])
    if chuoi:
        chuoi = care_repo.get_chuoi(chuoi["id"])
    return HTMLResponse(views.render_ke_hoach_cham(
        plan, care_repo.buoc_chuan(), bo, rs, chuoi=chuoi,
        ok_msg=ok, error=error))


@router.get("/cham-soc/{plan_id}", response_class=HTMLResponse)
async def ke_hoach_cham(plan_id: int, ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 28-38 (B9 — THẬT, gộp 1 màn) — 11 mốc + phiếu của mốc đang mở."""
    return _man_ke_hoach(plan_id, ok=ok, error=error)


@router.post("/cham-soc/{plan_id}/phieu/{duong}")
async def luu_phieu_cham(request: Request, plan_id: int, duong: str):
    """Nộp phiếu chăm từ web — cùng luật với API CARE-STEP (một service)."""
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    data = {k: str(v).strip() for k, v in form.items() if str(v).strip()}
    plan = None
    try:
        from app.db.repositories import care_repo

        plan = care_repo.get_plan(plan_id)
        if not plan:
            raise ApiError("NOT_FOUND", "Không tìm thấy kế hoạch chăm")
        kq = care_service.ghi_phieu(duong, plan["customer_id"], data,
                                    actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/cham-soc/{plan_id}", error=err.message)
    loi_nhan = "; ".join(kq.get("canh_bao") or []) or "Đã lưu phiếu"
    return _ve(f"/crm/cham-soc/{plan_id}", ok=loi_nhan)


@router.post("/cham-soc/moc/{step_id}/bo-qua")
async def bo_qua_moc_web(request: Request, step_id: int):
    from app.db.repositories import care_repo
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    step = care_repo.get_step(step_id)
    ve = f"/crm/cham-soc/{step['care_plan_id']}" if step else "/crm/cham-soc"
    form = await request.form()
    try:
        care_service.bo_qua_moc(step_id, reason=str(form.get("reason") or ""),
                                actor=_nguoi(request))
    except ApiError as err:
        return _ve(ve, error=err.message)
    return _ve(ve, ok="Đã bỏ qua mốc (có lý do)")


# ------------------------------------------------ màn 38: chuỗi không phản hồi
def _plan_cua_chuoi(sequence_id: int) -> int | None:
    """Đóng/ghi chuỗi xong quay về đúng màn kế hoạch của khách đó."""
    from app.db.repositories import care_repo

    seq = care_repo.get_chuoi(sequence_id)
    if not seq:
        return None
    plan = care_repo.plan_dang_chay_cua_khach(seq["customer_id"])
    return plan["id"] if plan else None


@router.post("/cham-soc/{plan_id}/chuoi/mo")
async def mo_chuoi_web(request: Request, plan_id: int):
    """NORESPONSE-001 từ web — mở chuỗi cho khách của kế hoạch này."""
    from app.db.repositories import care_repo
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    plan = care_repo.get_plan(plan_id)
    if not plan:
        return _ve("/crm/cham-soc", error="Không tìm thấy kế hoạch")
    try:
        care_service.mo_chuoi(plan["customer_id"], actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/cham-soc/{plan_id}", error=err.message)
    return _ve(f"/crm/cham-soc/{plan_id}",
               ok="Đã mở chuỗi — lần 1 là NHẮN TIN (FR-110)")


@router.post("/cham-soc/chuoi/{sequence_id}/cham")
async def ghi_lan_cham_web(request: Request, sequence_id: int):
    """NORESPONSE-002 từ web — kênh do form đặt sẵn đúng thứ tự chuẩn."""
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    ve_plan = _plan_cua_chuoi(sequence_id)
    ve = f"/crm/cham-soc/{ve_plan}" if ve_plan else "/crm/cham-soc"
    form = await request.form()
    try:
        kq = care_service.ghi_lan_cham(
            sequence_id, channel=str(form.get("channel") or ""),
            result=str(form.get("result") or ""),
            note=str(form.get("note") or ""), actor=_nguoi(request))
    except ApiError as err:
        return _ve(ve, error=err.message)
    loi = "Đã ghi lần chạm"
    if kq["status"] == "closed":
        loi = ("Khách đã phản hồi — chuỗi đóng" if kq["outcome"] == "responded"
               else "Đủ 4 lần không phản hồi — chuyển Tạm mất liên lạc (C08)")
    return _ve(ve, ok=loi)


@router.post("/cham-soc/chuoi/{sequence_id}/dong")
async def dong_chuoi_web(request: Request, sequence_id: int):
    """NORESPONSE-003 từ web."""
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    ve_plan = _plan_cua_chuoi(sequence_id)
    ve = f"/crm/cham-soc/{ve_plan}" if ve_plan else "/crm/cham-soc"
    form = await request.form()
    try:
        care_service.dong_chuoi(
            sequence_id, outcome=str(form.get("outcome") or ""),
            reason=str(form.get("reason") or ""), actor=_nguoi(request))
    except ApiError as err:
        return _ve(ve, error=err.message)
    return _ve(ve, ok="Đã đóng chuỗi")


@router.post("/cham-soc/{plan_id}/ngung-lien-he")
async def ngung_lien_he_web(request: Request, plan_id: int):
    """NORESPONSE-004 + AU11 từ web — khách yêu cầu dừng mọi liên hệ."""
    from app.db.repositories import care_repo
    from app.services import care_service

    if chan := _chan_sua(request):
        return chan
    plan = care_repo.get_plan(plan_id)
    if not plan:
        return _ve("/crm/cham-soc", error="Không tìm thấy kế hoạch")
    form = await request.form()
    try:
        care_service.ngung_lien_he(
            plan["customer_id"], reason=str(form.get("reason") or ""),
            actor=_nguoi(request))
    except ApiError as err:
        return _ve(f"/crm/cham-soc/{plan_id}", error=err.message)
    return _ve(f"/crm/cham-soc/{plan_id}",
               ok="Đã bật NGỪNG liên hệ — mọi automation dừng (AU11)")


@router.get("/mua-lai", response_class=HTMLResponse)
async def mua_lai(ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 39-40 (B10 — THẬT) — pipeline mua lại, nhãn FR-122 suy từ ngày."""
    from app.services import repurchase_service

    rows, _ = repurchase_service.danh_sach(limit=100)
    dem: dict[str, int] = {}
    for r in rows:
        dem[r["display_state"]] = dem.get(r["display_state"], 0) + 1
    nhan_dem = [(ma, ten, dem.get(ma, 0))
                for ma, ten in repurchase_service.NHAN_HIEN_THI]
    return HTMLResponse(views.render_mua_lai(rows, nhan_dem,
                                             ok_msg=ok, error=error))


@router.post("/mua-lai/{opportunity_id}/chuyen")
async def chuyen_mua_lai(request: Request, opportunity_id: int):
    """REPURCHASE-005 từ web — 'Chưa mua' service tự bắt lý do."""
    from app.services import repurchase_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    try:
        kq = repurchase_service.chuyen_stage(
            opportunity_id, str(form.get("stage") or ""),
            reason=str(form.get("reason") or ""), actor=_nguoi(request))
    except ApiError as err:
        return _ve("/crm/mua-lai", error=err.message)
    return _ve("/crm/mua-lai", ok=f"Đã chuyển sang '{kq['display_label']}'")


@router.get("/khach-ngu", response_class=HTMLResponse)
async def khach_ngu(tu_ngay: int = 30, gia_tri_tu: str = "",
                    ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 41 (B10 — THẬT) — khách ngủ 30/60/90/180 + chiến dịch tái kích hoạt."""
    from app.db.repositories import user_repo
    from app.services import repurchase_service

    gt = None
    try:
        gt = float(gia_tri_tu) if gia_tri_tu.strip() else None
    except ValueError:
        gia_tri_tu = ""
    data = repurchase_service.khach_ngu(max(tu_ngay, 1), gt)
    cskh = [u for u in user_repo.list_users(status="active", limit=100)[0]
            if u.get("role_name") in ("CSKH", "Trưởng nhóm CSKH")]
    return HTMLResponse(views.render_khach_ngu(
        data, repurchase_service.bao_cao_chien_dich(), cskh,
        tu_ngay=tu_ngay, gia_tri_tu=gia_tri_tu, ok_msg=ok, error=error))


@router.post("/khach-ngu/gan")
async def gan_chien_dich_web(request: Request):
    """FR-123 từ web — gán khách đã tick vào chiến dịch (+ việc mua lại)."""
    from app.services import repurchase_service

    if chan := _chan_sua(request):
        return chan
    form = await request.form()
    try:
        ids = [int(x) for x in form.getlist("ids")]
        cd_id = int(form.get("campaign_id") or 0) or None
        giao = int(form.get("assigned_to") or 0) or None
    except (TypeError, ValueError):
        return _ve("/crm/khach-ngu", error="Dữ liệu không hợp lệ")
    try:
        kq = repurchase_service.gan_chien_dich(
            campaign_id=cd_id, ten_moi=str(form.get("ten_moi") or ""),
            customer_ids=ids, assigned_to=giao,
            tao_viec=form.get("tao_viec") == "1", actor=_nguoi(request))
    except ApiError as err:
        return _ve("/crm/khach-ngu", error=err.message)
    return _ve("/crm/khach-ngu",
               ok=f"Chiến dịch '{kq['campaign']['name']}': thêm {kq['them']} khách"
                  + (f", bỏ qua {kq['bo_qua']}" if kq["bo_qua"] else ""))


@router.get("/san-pham", response_class=HTMLResponse)
async def san_pham() -> HTMLResponse:
    """Màn 42 + 44 (khung) — danh mục sản phẩm & mẫu liệu trình."""
    return HTMLResponse(views.render_san_pham(repo.products_treatments()))


# ------------------------------------------------------------ nguồn quảng cáo
# ------------------------------- bám đuổi · báo cáo lý do · automation · danh mục
@router.get("/bam-duoi", response_class=HTMLResponse)
async def bam_duoi(ly_do: int = 0) -> HTMLResponse:
    """Màn 16 — khách chưa mua cần bám đuổi, lọc theo lý do chưa mua."""
    from app.db.repositories import catalog_screen_repo as kho
    from app.web.views import ops as views_ops

    return HTMLResponse(views_ops.render_bam_duoi(
        kho.khach_can_bam_duoi(ly_do or None), kho.danh_muc_ly_do(), ly_do))


@router.get("/bam-duoi/{customer_id}", response_class=HTMLResponse)
async def chuoi_bam_duoi(customer_id: int) -> HTMLResponse:
    """Màn 17 — chi tiết chuỗi bám đuổi của một khách."""
    from app.db.repositories import catalog_screen_repo as kho
    from app.db.repositories import profile_repo
    from app.web.views import ops as views_ops

    kh = profile_repo.tong_quan(customer_id)
    if not kh:
        return HTMLResponse(render_403("Không tìm thấy khách hàng",
                                       heading="Bám đuổi"), status_code=404)
    return HTMLResponse(views_ops.render_chuoi_bam_duoi(
        kh, kho.chuoi_bam_duoi(customer_id)))


@router.get("/bao-cao-ly-do", response_class=HTMLResponse)
async def bao_cao_ly_do(request: Request, tu: str = "", den: str = "") -> HTMLResponse:
    """Màn 57 + 58 — băn khoăn khách hàng & lý do chưa chốt."""
    from app.db.repositories import catalog_screen_repo as kho
    from app.web.views import ops as views_ops

    if not co_quyen(_nguoi(request), "customer.view"):
        return HTMLResponse(render_403("Cần quyền customer.view",
                                       heading="Báo cáo"), status_code=403)
    return HTMLResponse(views_ops.render_bao_cao_ly_do(
        kho.bao_cao_ly_do(tu, den), tu, den))


@router.get("/automation", response_class=HTMLResponse)
async def automation() -> HTMLResponse:
    """Màn 69 + 71 — bảng THEO DÕI automation đang chạy + chuỗi follow-up.

    Cố ý không phải bảng cấu hình: builder Khi–Nếu–Thì (FR-161, màn 70) thuộc
    giai đoạn sau; bày bảng cấu hình giả sẽ khiến người dùng tưởng sửa được."""
    from app.web.views import ops as views_ops

    return HTMLResponse(views_ops.render_automation())


@router.get("/danh-muc", response_class=HTMLResponse)
async def danh_muc(nhom: str = "", ok: str = "", error: str = "") -> HTMLResponse:
    """Màn 72 — danh mục dùng chung (`ref_codes`)."""
    from app.db.repositories import catalog_screen_repo as kho
    from app.web.views import ops as views_ops

    ds_nhom = kho.nhom_danh_muc()
    if not nhom and ds_nhom:
        nhom = ds_nhom[0]["group_code"]
    return HTMLResponse(views_ops.render_danh_muc(
        ds_nhom, nhom, kho.danh_muc(nhom) if nhom else [],
        ok_msg=ok, error=error))


@router.post("/danh-muc")
async def them_danh_muc(request: Request):
    """MASTER — thêm mã mới vào danh mục (quyền user.manage)."""
    from app.db.repositories import catalog_screen_repo as kho

    if not co_quyen(_nguoi(request), "user.manage"):
        return HTMLResponse(render_403("Sửa danh mục cần quyền user.manage",
                                       heading="Danh mục"), status_code=403)
    f = await request.form()
    nhom = str(f.get("group_code") or "").strip()
    ve = f"/crm/danh-muc?nhom={quote(nhom)}"
    if not (nhom and f.get("code") and f.get("name")):
        return _ve(ve, error="Thiếu nhóm / mã / tên")
    moi = kho.them_ma(nhom, str(f["code"]).strip(), str(f["name"]).strip(),
                      sort_order=int(f.get("sort_order") or 0))
    if moi is None:
        return _ve(ve, error="Mã này đã có trong nhóm")
    return _ve(ve, ok=f"Đã thêm mã {moi['code']}")


@router.post("/danh-muc/{ma_id}/trang-thai")
async def doi_trang_thai_danh_muc(request: Request, ma_id: int):
    from app.db.repositories import catalog_screen_repo as kho

    if not co_quyen(_nguoi(request), "user.manage"):
        return HTMLResponse(render_403("Sửa danh mục cần quyền user.manage",
                                       heading="Danh mục"), status_code=403)
    f = await request.form()
    r = kho.doi_trang_thai_ma(ma_id, str(f.get("status") or "active"))
    nhom = quote(r["group_code"]) if r else ""
    return _ve(f"/crm/danh-muc?nhom={nhom}",
               ok="Đã đổi trạng thái mã" if r else "")


@router.get("/nhom-ca", response_class=HTMLResponse)
async def nhom_ca(request: Request) -> HTMLResponse:
    """Màn 68 — phân nhóm, trưởng nhóm, quy tắc chia lead."""
    from app.db.repositories import catalog_screen_repo as kho
    from app.web.views import ops as views_ops

    if not (co_quyen(_nguoi(request), "user.manage")
            or co_quyen(_nguoi(request), "user.manage_team")):
        return HTMLResponse(render_403("Cần quyền quản lý nhân sự",
                                       heading="Nhóm & ca"), status_code=403)
    return HTMLResponse(views_ops.render_nhom_ca(
        kho.nhom_va_thanh_vien(), kho.nhan_vien_chua_nhom()))


# ------------------------------------------- danh mục chi tiết (màn 43·45·46)
@router.get("/san-pham/sp/{product_id}", response_class=HTMLResponse)
async def chi_tiet_san_pham(product_id: int) -> HTMLResponse:
    """Màn 43 — chi tiết sản phẩm: nội dung được nói / cấm nói / phiên bản giá."""
    from app.db.repositories import catalog_repo
    from app.web.views import catalog as views_dm

    sp = catalog_repo.get_product(product_id)
    if not sp:
        return HTMLResponse(render_403("Không tìm thấy sản phẩm",
                                       heading="Sản phẩm"), status_code=404)
    return HTMLResponse(views_dm.render_chi_tiet_sp(
        sp, catalog_repo.list_product_versions(product_id)))


@router.get("/san-pham/lieu-trinh/{template_id}", response_class=HTMLResponse)
async def chi_tiet_lieu_trinh(template_id: int) -> HTMLResponse:
    """Màn 45 — chi tiết mẫu liệu trình (sản phẩm trong bộ + luật rút gọn)."""
    from app.db.repositories import catalog_repo
    from app.web.views import catalog as views_dm

    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        return HTMLResponse(render_403("Không tìm thấy mẫu liệu trình",
                                       heading="Liệu trình"), status_code=404)
    return HTMLResponse(views_dm.render_chi_tiet_lt(tpl))


@router.get("/san-pham/lieu-trinh/{template_id}/luat", response_class=HTMLResponse)
async def luat_lieu_trinh(template_id: int, ok: str = "",
                          error: str = "") -> HTMLResponse:
    """Màn 46 — cấu hình luật: khi nào được chọn / bị chặn / cần duyệt."""
    from app.db.repositories import catalog_repo
    from app.web.views import catalog as views_dm

    tpl = catalog_repo.get_template(template_id)
    if not tpl:
        return HTMLResponse(render_403("Không tìm thấy mẫu liệu trình",
                                       heading="Liệu trình"), status_code=404)
    return HTMLResponse(views_dm.render_luat_lt(tpl, ok_msg=ok, error=error))


@router.post("/san-pham/lieu-trinh/{template_id}/luat")
async def them_luat(request: Request, template_id: int):
    """TREATMENT-007 — thêm luật. Quyền `treatment.edit` (chuyên môn/quản trị)."""
    from app.services import treatment_service

    if not co_quyen(_nguoi(request), "treatment.edit"):
        return HTMLResponse(
            render_403("Sửa luật liệu trình cần quyền treatment.edit",
                       heading="Luật liệu trình"), status_code=403)
    f = await request.form()
    ve = f"/crm/san-pham/lieu-trinh/{template_id}/luat"
    cond: dict = {"type": str(f.get("cond_type") or "")}
    ma = str(f.get("code") or "").strip()
    # engine đọc 'group' cho kiểu nhóm triệu chứng, 'code' cho các kiểu còn lại
    cond["group" if cond["type"] == "symptom_group" else "code"] = ma
    if f.get("min_severity"):
        try:
            cond["min_severity"] = int(f["min_severity"])
        except ValueError:
            return _ve(ve, error="Mức tối thiểu phải là số")
    try:
        treatment_service.add_rule(
            template_id,
            {"rule_type": str(f.get("rule_type") or ""), "condition": cond,
             "action": {"message": str(f.get("message") or "")},
             "priority": int(f.get("priority") or 0)},
            actor=_nguoi(request))
    except (ApiError, ValueError) as err:
        return _ve(ve, error=getattr(err, "message", str(err)))
    return _ve(ve, ok="Đã thêm luật — lần đề xuất sau ăn ngay")


@router.get("/quang-cao", response_class=HTMLResponse)
async def quang_cao(
    request: Request, cap: str = "ad", tu: str = "", den: str = "",
) -> HTMLResponse:
    """Màn 7 + 53-55 — hiệu quả quảng cáo theo chiến dịch / nhóm / quảng cáo.

    Quyền `ads.view` (Marketing + Chủ DN + Admin): màn này bày chi phí và doanh
    thu, không phải ai đăng nhập cũng được xem.
    """
    if not co_quyen(getattr(request.state, "user", None), "ads.view"):
        return HTMLResponse(
            render_403("Màn Nguồn quảng cáo cần quyền ads.view",
                       heading="Nguồn quảng cáo"),
            status_code=403,
        )
    if cap not in ("campaign", "ad_set", "ad"):
        cap = "ad"
    if not (tu or den):
        tu, den = ads_service.ky_mac_dinh(30)
    return HTMLResponse(views_ads.render_quang_cao(
        cap, ads_service.bao_cao(cap, tu, den), ads_service.tong_quan(tu, den),
        tu=tu, den=den,
    ))


@router.get("/quang-cao/{external_ad_id}", response_class=HTMLResponse)
async def quang_cao_chi_tiet(
    request: Request, external_ad_id: str, window: int = 30,
) -> HTMLResponse:
    """Màn 56 — phiếu sức khỏe 1 quảng cáo (phễu · lý do chưa chốt · khách)."""
    if not co_quyen(getattr(request.state, "user", None), "ads.view"):
        return HTMLResponse(
            render_403("Màn Nguồn quảng cáo cần quyền ads.view",
                       heading="Nguồn quảng cáo"),
            status_code=403,
        )
    try:
        data = ads_service.chi_tiet_ad(external_ad_id, window)
    except ApiError as err:
        return HTMLResponse(
            render_403(err.message, heading="Nguồn quảng cáo"), status_code=404)
    return HTMLResponse(views_ads.render_chi_tiet_ad(data, window=window))


# =============================================================== C1 — ƯU ĐÃI
# Voucher + Hạng thẻ, port từ mẫu Kallet (voucher.php · hang-the.php).
# Luật ở services/voucher_service.py; SQL ở db/repositories/voucher_repo.py.
_VC_TRANG = 30          # voucher / trang — mẫu chốt 30, giữ nguyên


@router.get("/voucher", response_class=HTMLResponse)
async def voucher(request: Request, tt: str = "", kw: str = "", by: str = "",
                  nv: int = 0, tang: int = 0, trang: int = 1,
                  ok: str = "", error: str = "") -> HTMLResponse:
    """Màn Voucher — theo dõi voucher đã tặng.

    Voucher là việc của người được cấp quyền `voucher.grant` (CSKH); Sale/
    Marketing không cần. Người KHÔNG có `customer.view_all` chỉ thấy voucher
    của khách mình phụ trách — chặn ở tầng dữ liệu, không phải ẩn nút.
    """
    from app.db.repositories import user_repo, voucher_repo
    from app.services import voucher_service

    user = _nguoi(request)
    if not co_quyen(user, "voucher.grant"):
        return HTMLResponse(
            render_403("Màn Voucher cần quyền voucher.grant", heading="Voucher"),
            status_code=403,
        )
    # Quản lý (user.manage) xem hết; còn lại bó về khách mình phụ trách.
    pham_vi = None if co_quyen(user, "user.manage") else int(user.get("sub") or 0)
    trang = max(1, trang)
    rows, tong = voucher_repo.danh_sach(
        status=tt, kind=by, granted_by=nv or None, tu_khoa=kw.strip(),
        owner_id=pham_vi, limit=_VC_TRANG, offset=(trang - 1) * _VC_TRANG)
    so_trang = max(1, -(-tong // _VC_TRANG))
    if trang > so_trang:                       # siết lọc xong trang cũ hết dòng
        trang = so_trang
        rows, tong = voucher_repo.danh_sach(
            status=tt, kind=by, granted_by=nv or None, tu_khoa=kw.strip(),
            owner_id=pham_vi, limit=_VC_TRANG, offset=(trang - 1) * _VC_TRANG)
    return HTMLResponse(views_uu_dai.render_voucher(
        rows, tong,
        so=voucher_repo.o_so(owner_id=pham_vi),
        loc={"tt": tt, "kw": kw, "by": by, "nv": nv, "trang": trang},
        nhan_vien=voucher_repo.nguoi_tang(owner_id=pham_vi)
                  or user_repo.list_users(status="active", limit=200)[0],
        user=user, mo_form=bool(tang), flash=ok, loi=error))


@router.post("/voucher/tang")
async def voucher_tang(request: Request):
    """Tạo & tặng voucher. KHÔNG gửi tin cho khách — báo mã là việc của người."""
    from app.services import voucher_service

    user = _nguoi(request)
    if not co_quyen(user, "voucher.grant"):
        return HTMLResponse(
            render_403("Cần quyền voucher.grant để tặng voucher",
                       heading="Voucher"), status_code=403)
    f = await request.form()
    try:
        v = voucher_service.tang_voucher(
            sdt=str(f.get("sdt") or ""),
            menh_gia=str(f.get("menh_gia") or "0"),
            ma=str(f.get("ma") or ""),
            han_ngay=int(str(f.get("han_ngay") or "0") or 0),
            ghi_chu=str(f.get("ghi_chu") or ""),
            nguoi_tang=int(user.get("sub") or 0) or None,
            la_admin=co_quyen(user, "user.manage"))
    except (ApiError, ValueError) as err:
        return _ve("/crm/voucher?tang=1",
                   error=getattr(err, "message", str(err)))
    from app.db.repositories import audit_repo

    audit_repo.ghi(action="tang_voucher", object_type="voucher",
                   object_id=int(v["id"]), user_id=int(user.get("sub") or 0),
                   new_value={"khach": v.get("customer_name"),
                              "menh_gia": str(v.get("amount")),
                              "ma": v.get("code") or "(chưa báo mã)"})
    return _ve("/crm/voucher",
               ok=f'Đã tặng voucher cho {v.get("customer_name") or "khách"}.')


@router.post("/voucher/{voucher_id}/bao-ma")
async def voucher_bao_ma(request: Request, voucher_id: int):
    """Báo mã cho voucher đang ở trạng thái 'chưa báo mã' → 'còn hạn'."""
    from app.services import voucher_service

    user = _nguoi(request)
    if not co_quyen(user, "voucher.grant"):
        return HTMLResponse(render_403("Cần quyền voucher.grant",
                                       heading="Voucher"), status_code=403)
    f = await request.form()
    try:
        voucher_service.bao_ma(voucher_id, str(f.get("ma") or ""),
                               nguoi_sua=int(user.get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/voucher", error=err.message)
    return _ve("/crm/voucher", ok="Đã lưu mã voucher.")


@router.post("/voucher/{voucher_id}/trang-thai")
async def voucher_trang_thai(request: Request, voucher_id: int):
    from app.services import voucher_service

    user = _nguoi(request)
    if not co_quyen(user, "voucher.grant"):
        return HTMLResponse(render_403("Cần quyền voucher.grant",
                                       heading="Voucher"), status_code=403)
    f = await request.form()
    try:
        voucher_service.doi_trang_thai(
            voucher_id, str(f.get("trang_thai") or ""),
            nguoi_sua=int(user.get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/voucher", error=err.message)
    return _ve("/crm/voucher", ok="Đã đổi tình trạng voucher.")


@router.get("/hang-the", response_class=HTMLResponse)
async def hang_the(request: Request, ok: str = "") -> HTMLResponse:
    """Màn Hạng thẻ — toàn cảnh 6 hạng (5 bậc + "Chưa xếp hạng")."""
    from app.services import voucher_service

    return HTMLResponse(views_uu_dai.render_hang_the(
        voucher_service.toan_canh(), _nguoi(request), flash=ok))


@router.post("/hang-the/nguong")
async def hang_the_nguong(request: Request):
    """Sửa ngưỡng một hạng. Ô để TRỐNG = xoá ngưỡng ("chưa điền") — hạng đó
    ngừng nhận khách mới cho tới khi điền lại, KHÔNG hiểu là ngưỡng 0đ."""
    from app.db.repositories import audit_repo, voucher_repo

    user = _nguoi(request)
    if not co_quyen(user, "user.manage"):
        return HTMLResponse(render_403("Sửa ngưỡng hạng thẻ cần quyền "
                                       "user.manage", heading="Hạng thẻ"),
                            status_code=403)
    f = await request.form()
    ma = str(f.get("ma") or "")
    thoi = str(f.get("nguong") or "").strip()
    try:
        nguong = float(thoi.replace(".", "").replace(",", "")) if thoi else None
    except ValueError:
        return _ve("/crm/hang-the", error="Ngưỡng phải là một con số.")
    voucher_repo.dat_nguong(ma, nguong)
    audit_repo.ghi(action="sua_nguong_hang_the", object_type="card_rank",
                   user_id=int(user.get("sub") or 0),
                   new_value={"ma": ma, "nguong": thoi or "(chưa điền)"})
    return _ve("/crm/hang-the",
               ok=f"Đã lưu ngưỡng hạng {ma}. Bấm “Tính lại hạng” để áp cho "
                  "khách cũ.")


@router.post("/hang-the/tinh-lai")
async def hang_the_tinh_lai(request: Request):
    """Xếp lại hạng toàn bộ khách — CHỈ NÂNG, không ai bị tụt (xem luật 1 ở
    services/voucher_service.py)."""
    from app.services import voucher_service

    user = _nguoi(request)
    if not co_quyen(user, "user.manage"):
        return HTMLResponse(render_403("Tính lại hạng thẻ cần quyền "
                                       "user.manage", heading="Hạng thẻ"),
                            status_code=403)
    kq = voucher_service.tinh_lai_hang(nguoi_chay=int(user.get("sub") or 0))
    return _ve("/crm/hang-the",
               ok=f'Đã tính lại: {kq["chi_tieu"]} khách cập nhật chi tiêu, '
                  f'{kq["len_hang"]} khách LÊN hạng (không ai bị tụt).')


# ================================================= C2 — LƯƠNG · THƯỞNG · ĐỐI SOÁT
# Port từ mẫu Kallet (luong.php · luong-thuong.php · doi-soat.php).
# Ba luật tiền bạc nằm ở services/payroll_service.py — route chỉ là lớp mỏng.
def _chan(request: Request, quyen: str, ten_man: str):
    """Chặn theo quyền, trả nguyên trang 403 (không phải JSON) cho màn web."""
    if not co_quyen(_nguoi(request), quyen):
        return HTMLResponse(
            render_403(f"Màn {ten_man} cần quyền {quyen}", heading=ten_man),
            status_code=403)
    return None


@router.get("/thu-nhap", response_class=HTMLResponse)
async def thu_nhap(request: Request, ky: str = "", nv: int = 0,
                   ok: str = "", error: str = "") -> HTMLResponse:
    """Màn "Thu nhập của tôi" — mặc định CHỈ xem của chính mình.

    `?nv=` xem người khác: đòi `payroll.manage` (quản lý lương). Không có quyền
    đó thì tham số bị bỏ qua, không báo lỗi — người dùng gõ tay URL cũng chỉ
    thấy lương mình.
    """
    from app.db.repositories import payroll_repo
    from app.services import payroll_service

    if chan := _chan(request, "payroll.view_own", "Thu nhập của tôi"):
        return chan
    user = _nguoi(request)
    uid = int(user.get("sub") or 0)
    if nv and nv != uid and co_quyen(user, "payroll.manage"):
        uid = nv
    ky = payroll_service.ky_hop_le(ky)
    try:
        data = payroll_service.tinh_luong(uid, ky)
    except ApiError as err:
        return HTMLResponse(render_403(err.message, heading="Thu nhập của tôi"),
                            status_code=404)
    return HTMLResponse(views_luong.render_thu_nhap(
        data, cac_ky=payroll_repo.cac_ky(),
        don=payroll_repo.don_trong_ky(uid, ky),
        muc_tieu=payroll_repo.muc_tieu(uid, ky) or 0.0,
        flash=ok, loi=error))


@router.post("/thu-nhap/muc-tieu")
async def thu_nhap_muc_tieu(request: Request):
    """Mục tiêu do CHÍNH nhân viên đặt — luôn ghi cho người đang đăng nhập."""
    from app.db.repositories import payroll_repo
    from app.services import payroll_service

    if chan := _chan(request, "payroll.view_own", "Thu nhập của tôi"):
        return chan
    f = await request.form()
    ky = payroll_service.ky_hop_le(str(f.get("ky") or ""))
    try:
        trieu = max(1, min(999, int(str(f.get("trieu") or "0") or 0)))
    except ValueError:
        return _ve(f"/crm/thu-nhap?ky={ky}", error="Mục tiêu phải là số.")
    payroll_repo.dat_muc_tieu(int(_nguoi(request).get("sub") or 0), ky,
                              trieu * 1_000_000)
    return _ve(f"/crm/thu-nhap?ky={ky}", ok=f"Đã đặt mục tiêu {trieu} triệu.")


@router.get("/luong", response_class=HTMLResponse)
async def luong(request: Request, ky: str = "", ok: str = "") -> HTMLResponse:
    """Màn Lương thưởng — bảng lương CẢ ĐỘI theo kỳ (đòi payroll.manage)."""
    from app.db.repositories import payroll_repo
    from app.services import payroll_service

    if chan := _chan(request, "payroll.manage", "Lương thưởng"):
        return chan
    ky = payroll_service.ky_hop_le(ky)
    return HTMLResponse(views_luong.render_bang_luong(
        payroll_repo.bang_luong(ky), ky, cac_ky=payroll_repo.cac_ky(),
        co_chot=True, flash=ok))


@router.post("/luong/tinh-lai")
async def luong_tinh_lai(request: Request):
    from app.services import payroll_service

    if chan := _chan(request, "payroll.manage", "Lương thưởng"):
        return chan
    f = await request.form()
    ky = payroll_service.ky_hop_le(str(f.get("ky") or ""))
    ds = payroll_service.tinh_ca_doi(ky, ghi=True)
    return _ve(f"/crm/luong?ky={ky}",
               ok=f"Đã tính lại kỳ {ky} cho {len(ds)} người.")


@router.post("/luong/chot")
async def luong_chot(request: Request):
    """Chốt kỳ = ĐÓNG BĂNG. Sai lệch sau đó ghi vào kỳ sau, không sửa ngược."""
    from app.services import payroll_service

    if chan := _chan(request, "payroll.manage", "Lương thưởng"):
        return chan
    f = await request.form()
    ky = payroll_service.ky_hop_le(str(f.get("ky") or ""))
    kq = payroll_service.chot_ky(ky, int(_nguoi(request).get("sub") or 0))
    return _ve(f"/crm/luong?ky={ky}",
               ok=f'Đã chốt kỳ {ky} — {kq["so_dong"]} dòng lương đóng băng.')


@router.get("/doi-soat", response_class=HTMLResponse)
async def doi_soat(request: Request, ro: str = "all", ok: str = "",
                   error: str = "") -> HTMLResponse:
    """Màn Đối soát & duyệt thưởng chăm sóc — 3 rổ suy từ dữ liệu."""
    from app.services import payroll_service

    if chan := _chan(request, "payroll.approve", "Đối soát & duyệt thưởng"):
        return chan
    if ro not in ("all", "fixed", "wonder", "done"):
        ro = "all"
    return HTMLResponse(views_luong.render_doi_soat(
        payroll_service.bang_doi_soat(ro), flash=ok, loi=error))


@router.post("/doi-soat/{order_id}/duyet")
async def doi_soat_duyet(request: Request, order_id: int):
    from app.services import payroll_service

    if chan := _chan(request, "payroll.approve", "Đối soát & duyệt thưởng"):
        return chan
    try:
        kq = payroll_service.duyet_thuong_cham(
            order_id, nguoi=int(_nguoi(request).get("sub") or 0))
    except ApiError as err:
        return _ve("/crm/doi-soat", error=err.message)
    return _ve("/crm/doi-soat",
               ok=f'Đã duyệt thưởng +{float(kq["amount"]):,.0f}đ.'
                  .replace(",", "."))


@router.post("/doi-soat/{order_id}/bac")
async def doi_soat_bac(request: Request, order_id: int):
    from app.services import payroll_service

    if chan := _chan(request, "payroll.approve", "Đối soát & duyệt thưởng"):
        return chan
    f = await request.form()
    try:
        payroll_service.bac_thuong_cham(
            order_id, str(f.get("ly_do") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0))
    except ApiError as err:
        return _ve("/crm/doi-soat", error=err.message)
    return _ve("/crm/doi-soat", ok="Đã bác thưởng (có ghi lý do).")


@router.post("/doi-soat/{order_id}/phan-loai")
async def doi_soat_phan_loai(request: Request, order_id: int):
    """Đổi phân loại đơn — "đổi phân loại thì TIỀN ĐI THEO"."""
    from app.services import payroll_service

    if chan := _chan(request, "payroll.approve", "Đối soát & duyệt thưởng"):
        return chan
    f = await request.form()
    try:
        payroll_service.doi_phan_loai(
            order_id, str(f.get("sang") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0),
            ly_do=str(f.get("ly_do") or ""))
    except ApiError as err:
        return _ve("/crm/doi-soat", error=err.message)
    return _ve("/crm/doi-soat", ok="Đã đổi phân loại đơn — thưởng đi theo.")


@router.get("/bac-luong", response_class=HTMLResponse)
async def bac_luong(request: Request, ok: str = "",
                    error: str = "") -> HTMLResponse:
    """Cấu hình bậc hoa hồng · thưởng chăm · thưởng nóng theo VAI TRÒ."""
    from app.db.repositories import org_repo, payroll_repo

    if chan := _chan(request, "payroll.manage", "Bậc lương & thưởng"):
        return chan
    return HTMLResponse(views_luong.render_bac_luong(
        payroll_repo.bac_hoa_hong(), payroll_repo.bac_thuong_cham(),
        payroll_repo.bac_thuong_nong(), org_repo.list_roles(),
        flash=ok, loi=error))


@router.post("/bac-luong/them")
async def bac_luong_them(request: Request):
    from app.db.repositories import payroll_repo

    if chan := _chan(request, "payroll.manage", "Bậc lương & thưởng"):
        return chan
    f = await request.form()
    bang = str(f.get("bang") or "")
    try:
        nguong = float(str(f.get("nguong") or "0").replace(".", "").replace(",", ""))
        gia_tri = float(str(f.get("value") or "0").replace(".", "").replace(",", ""))
        du = {"role_id": int(f.get("role_id") or 0),
              "kind": str(f.get("kind") or "phan_tram"),
              "value": gia_tri, "sort_order": 0}
        if bang == "hot_bonus_tiers":
            du.update({"basis": str(f.get("basis") or "doanh_thu_ngay"),
                       "threshold": nguong})
        else:
            du["min_revenue"] = nguong
        payroll_repo.luu_bac(bang, **du)
    except (ValueError, KeyError) as err:
        return _ve("/crm/bac-luong", error=f"Số nhập không hợp lệ: {err}")
    return _ve("/crm/bac-luong", ok="Đã thêm bậc.")


@router.post("/bac-luong/xoa")
async def bac_luong_xoa(request: Request):
    from app.db.repositories import payroll_repo

    if chan := _chan(request, "payroll.manage", "Bậc lương & thưởng"):
        return chan
    f = await request.form()
    try:
        payroll_repo.xoa_bac(str(f.get("bang") or ""), int(f.get("id") or 0))
    except ValueError as err:
        return _ve("/crm/bac-luong", error=str(err))
    return _ve("/crm/bac-luong", ok="Đã xoá bậc.")


# ============================================ C3 — CHIẾN DỊCH 2 TẦNG & MẪU TIN
# Port từ mẫu Kallet (chien-dich.php · mau-tin.php). Luật ở
# services/campaign_service.py; công tắc gửi tin ở Cài đặt → Gửi tin hàng loạt.
@router.get("/chien-dich", response_class=HTMLResponse)
async def chien_dich(request: Request, xem: int = 0, nhom: str = "",
                     hang: str = "", so_mua: str = "", ok: str = "",
                     error: str = "") -> HTMLResponse:
    """Danh sách chiến dịch + form tạo. `?xem=1` chỉ ĐẾM XEM TRƯỚC, không ghi gì."""
    from app.db.repositories import campaign_repo
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Chiến dịch"):
        return chan
    loc = campaign_service.chuan_hoa_loc(
        {"nhom": nhom, "hang": hang, "so_mua": so_mua})
    truoc = campaign_service.xem_truoc(loc) if xem else None
    return HTMLResponse(views_cd.render_chien_dich(
        campaign_service.so_sanh(), xem_truoc=truoc, loc=loc,
        mau=campaign_repo.mau_tin(), flash=ok, loi=error))


@router.post("/chien-dich/tao")
async def chien_dich_tao(request: Request):
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Chiến dịch"):
        return chan
    f = await request.form()
    try:
        cd = campaign_service.tao(
            ten=str(f.get("ten") or ""),
            loc={"nhom": str(f.get("nhom") or ""),
                 "hang": str(f.get("hang") or ""),
                 "so_mua": str(f.get("so_mua") or "")},
            template_id=int(f.get("template_id") or 0) or None,
            moi_dot=int(str(f.get("moi_dot") or "500") or 500),
            cach_ngay=int(str(f.get("cach_ngay") or "7") or 7),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except (ApiError, ValueError) as err:
        return _ve("/crm/chien-dich", error=getattr(err, "message", str(err)))
    return _ve("/crm/chien-dich",
               ok=f'Đã tạo "{cd["name"]}" với {cd["so_khach"]} khách. '
                  "Bấm Chạy rồi Chạy 1 đợt để bắt đầu tầng 1.")


@router.get("/chien-dich/{campaign_id}", response_class=HTMLResponse)
async def chien_dich_chi_tiet(request: Request, campaign_id: int,
                              ok: str = "") -> HTMLResponse:
    from app.db.repositories import campaign_repo

    if chan := _chan(request, "campaign.manage", "Chiến dịch"):
        return chan
    cd = campaign_repo.get(campaign_id)
    if not cd:
        return HTMLResponse(render_403("Không tìm thấy chiến dịch",
                                       heading="Chiến dịch"), status_code=404)
    return HTMLResponse(views_cd.render_chi_tiet(
        dict(cd), campaign_repo.thanh_vien(campaign_id, tang="1"),
        campaign_repo.thanh_vien(campaign_id, tang="2"), flash=ok))


@router.post("/chien-dich/{campaign_id}/trang-thai")
async def chien_dich_trang_thai(request: Request, campaign_id: int):
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Chiến dịch"):
        return chan
    f = await request.form()
    try:
        kq = campaign_service.doi_trang_thai(
            campaign_id, str(f.get("tt") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/chien-dich", error=err.message)
    them = (f' Đã NHẢ {kq["nha_khach"]} khách chưa chốt để họ vào được chiến '
            "dịch khác." if kq.get("nha_khach") else "")
    return _ve("/crm/chien-dich", ok="Đã đổi trạng thái chiến dịch." + them)


@router.post("/chien-dich/{campaign_id}/chay-dot")
async def chien_dich_chay_dot(request: Request, campaign_id: int):
    """Chạy MỘT đợt tầng 1. Công tắc TẮT thì chỉ chạy nháp (không gửi gì)."""
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Chiến dịch"):
        return chan
    f = await request.form()
    try:
        kq = await campaign_service.chay_dot(
            campaign_id, int(str(f.get("so_luong") or "0") or 0),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except (ApiError, ValueError) as err:
        return _ve("/crm/chien-dich", error=getattr(err, "message", str(err)))
    if not kq["gui_that"]:
        return _ve("/crm/chien-dich",
                   ok=f'✏️ Chạy NHÁP: chọn được {kq["chon"]} khách, KHÔNG gửi '
                      "tin nào và không đánh dấu ai. Bật công tắc ở Cài đặt "
                      "để gửi thật.")
    return _ve("/crm/chien-dich",
               ok=f'Đã gửi {kq["da_gui"]}/{kq["chon"]} tin'
                  + (f', {kq["loi"]} lỗi.' if kq["loi"] else "."))


@router.get("/mau-tin", response_class=HTMLResponse)
async def mau_tin(request: Request, ok: str = "", error: str = "",
                  thu: str = "") -> HTMLResponse:
    from app.db.repositories import campaign_repo

    if chan := _chan(request, "campaign.manage", "Mẫu tin"):
        return chan
    return HTMLResponse(views_cd.render_mau_tin(
        campaign_repo.mau_tin(trang_thai=""), flash=ok, loi=error, xem_thu=thu))


@router.post("/mau-tin")
async def mau_tin_luu(request: Request):
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Mẫu tin"):
        return chan
    f = await request.form()
    try:
        campaign_service.luu_mau_tin(
            code=str(f.get("code") or ""), name=str(f.get("name") or ""),
            body=str(f.get("body") or ""), kind=str(f.get("kind") or "tu_do"),
            meta_status=str(f.get("meta_status") or "rong"),
            variables=str(f.get("variables") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/mau-tin", error=err.message)
    return _ve("/crm/mau-tin", ok="Đã lưu mẫu tin.")


@router.post("/mau-tin/{template_id}/xem-thu")
async def mau_tin_xem_thu(request: Request, template_id: int):
    from app.services import campaign_service

    if chan := _chan(request, "campaign.manage", "Mẫu tin"):
        return chan
    try:
        noi_dung = campaign_service.xem_thu(template_id)
    except ApiError as err:
        return _ve("/crm/mau-tin", error=err.message)
    return RedirectResponse(f"/crm/mau-tin?thu={quote(noi_dung)}",
                            status_code=303)


@router.post("/mau-tin/{template_id}/trang-thai")
async def mau_tin_trang_thai(request: Request, template_id: int):
    """Mẫu cũ NGỪNG DÙNG chứ không xoá — tin đã gửi phải tra ngược được."""
    from app.db.repositories import campaign_repo

    if chan := _chan(request, "campaign.manage", "Mẫu tin"):
        return chan
    f = await request.form()
    tt = str(f.get("tt") or "")
    if tt not in ("active", "inactive"):
        return _ve("/crm/mau-tin", error=f"Trạng thái lạ: {tt}")
    campaign_repo.doi_trang_thai_mau(template_id, tt)
    return _ve("/crm/mau-tin",
               ok="Đã ngừng dùng mẫu." if tt == "inactive" else "Đã dùng lại mẫu.")


# ================== C4 — THƯ VIỆN KỊCH BẢN · KHO DATA · GIÁM SÁT (SOI TIN)
# Port từ mẫu Kallet (kich-ban.php · kho-data.php · lich-su.php ·
# includes/xac_minh.php). Luật ở services/giam_sat_service.py.
@router.get("/kich-ban", response_class=HTMLResponse)
async def kich_ban(request: Request, q: str = "", kind: str = "",
                   tinh_huong: str = "", chep: str = "", ok: str = "",
                   error: str = "") -> HTMLResponse:
    """📚 THƯ VIỆN câu mẫu để chép tay — mở màn này KHÔNG gửi gì cho ai.

    Ai đăng nhập cũng xem được: đây là công cụ làm việc hằng ngày của Sale và
    CSKH, khoá lại chỉ tổ vướng."""
    from app.db.repositories import giam_sat_repo

    rows, tong = giam_sat_repo.kich_ban(kind=kind, tu_khoa=q,
                                        tinh_huong=tinh_huong)
    return HTMLResponse(views_gs.render_kich_ban(
        rows, tong, loc={"q": q, "kind": kind, "tinh_huong": tinh_huong},
        tinh_huong=giam_sat_repo.tinh_huong_co(), da_chep=chep,
        flash=ok, loi=error))


@router.post("/kich-ban")
async def kich_ban_luu(request: Request):
    from app.services import giam_sat_service

    f = await request.form()
    try:
        giam_sat_service.luu_kich_ban(
            kind=str(f.get("kind") or "sale"),
            situation=str(f.get("situation") or ""),
            title=str(f.get("title") or ""), body=str(f.get("body") or ""),
            tags=str(f.get("tags") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/kich-ban", error=err.message)
    return _ve("/crm/kich-ban", ok="Đã lưu câu mẫu.")


@router.post("/kich-ban/{script_id}/chep")
async def kich_ban_chep(request: Request, script_id: int):
    """Chép một câu mẫu. CHỈ đếm lượt dùng — tuyệt đối không sinh tin nhắn."""
    from app.services import giam_sat_service

    try:
        kq = giam_sat_service.chep(script_id)
    except ApiError as err:
        return _ve("/crm/kich-ban", error=err.message)
    return RedirectResponse(f'/crm/kich-ban?chep={quote(kq["body"][:400])}',
                            status_code=303)


@router.post("/kich-ban/goi-y", response_class=HTMLResponse)
async def kich_ban_goi_y(request: Request) -> HTMLResponse:
    """💡 Gợi ý 3 câu theo TỪ KHOÁ trong tin khách (dò từ khoá, không AI)."""
    from app.db.repositories import giam_sat_repo
    from app.services import giam_sat_service

    f = await request.form()
    tin = str(f.get("tin") or "")
    rows, tong = giam_sat_repo.kich_ban()
    return HTMLResponse(views_gs.render_kich_ban(
        rows, tong, loc={}, tinh_huong=giam_sat_repo.tinh_huong_co(),
        goi_y=giam_sat_service.goi_y(tin)))


@router.get("/kho-data", response_class=HTMLResponse)
async def kho_data(request: Request, ok: str = "",
                   error: str = "") -> HTMLResponse:
    from app.db.repositories import user_repo
    from app.services import giam_sat_service

    if chan := _chan(request, "data.export", "Kho data"):
        return chan
    return HTMLResponse(views_gs.render_kho_data(
        giam_sat_service.tong_quan_kho(),
        nhan_vien=user_repo.list_users(status="active", limit=200)[0],
        flash=ok, loi=error))


@router.post("/kho-data/chia")
async def kho_data_chia(request: Request):
    from app.services import giam_sat_service

    if chan := _chan(request, "data.export", "Kho data"):
        return chan
    f = await request.form()
    try:
        giam_sat_service.chia(
            int(f.get("customer_id") or 0), int(f.get("user_id") or 0),
            ly_do="chia tay ở màn Kho data",
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except (ApiError, ValueError) as err:
        return _ve("/crm/kho-data", error=getattr(err, "message", str(err)))
    return _ve("/crm/kho-data", ok="Đã chia khách.")


@router.post("/kho-data/thu-hoi")
async def kho_data_thu_hoi(request: Request):
    """Thu hồi khách — BẮT BUỘC lý do, kèm khoá không chia lại cho người đó."""
    from app.services import giam_sat_service

    if chan := _chan(request, "data.export", "Kho data"):
        return chan
    f = await request.form()
    try:
        giam_sat_service.thu_hoi(
            int(f.get("customer_id") or 0), int(f.get("user_id") or 0),
            str(f.get("ly_do") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except (ApiError, ValueError) as err:
        return _ve("/crm/kho-data", error=getattr(err, "message", str(err)))
    return _ve("/crm/kho-data", ok="Đã thu hồi khách (có ghi lý do).")


@router.get("/giam-sat", response_class=HTMLResponse)
async def giam_sat(request: Request, tt: str = "", ok: str = "",
                   error: str = "") -> HTMLResponse:
    """Vòng xác minh công — soi tin nhắn thật làm bằng chứng."""
    from app.db.repositories import giam_sat_repo

    if chan := _chan(request, "audit.view", "Giám sát & soi tin"):
        return chan
    if tt not in ("", "da_xac_minh", "tu_khai_chua_soi", "bac_bo"):
        tt = ""
    return HTMLResponse(views_gs.render_giam_sat(
        giam_sat_repo.bang_cong(trang_thai=tt), giam_sat_repo.dem_cong(),
        tab=tt, flash=ok, loi=error))


@router.post("/giam-sat/soi")
async def giam_sat_soi(request: Request):
    from app.services import giam_sat_service

    if chan := _chan(request, "audit.view", "Giám sát & soi tin"):
        return chan
    kq = giam_sat_service.soi_hang_loat()
    return _ve("/crm/giam-sat",
               ok=f'Đã soi {kq["soi"]} bản: {kq.get("da_xac_minh", 0)} xác '
                  f'minh · {kq.get("bac_bo", 0)} bác · '
                  f'{kq.get("cho_them", 0)} chờ thêm.')


@router.post("/giam-sat/{cong_id}/duyet")
async def giam_sat_duyet(request: Request, cong_id: int):
    """Trưởng nhóm vớt/bác tay. Lý do BẮT BUỘC — công là tiền của người ta."""
    from app.services import giam_sat_service

    if chan := _chan(request, "audit.view", "Giám sát & soi tin"):
        return chan
    f = await request.form()
    try:
        giam_sat_service.duyet_tay(
            cong_id, str(f.get("ok") or "0") == "1",
            str(f.get("ly_do") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/giam-sat", error=err.message)
    return _ve("/crm/giam-sat", ok="Đã ghi quyết định (kèm lý do).")


# ================================= C5 — BỘ PHẬN SALE: BẢNG VIỆC + THANG BÁM ĐUỔI
# Port từ mẫu Kallet (trang-chu.php · includes/sale_buoc.php ·
# includes/board_rules.php). Luật ở services/sale_service.py.
@router.get("/bang-viec", response_class=HTMLResponse)
async def bang_viec(request: Request, cd: str = "bang", q: str = "",
                    loc: str = "", tatca: int = -1, hien_da_cham: int = 0,
                    ok: str = "", error: str = "") -> HTMLResponse:
    """Bảng việc Sale — cột do MÁY ĐỌC TIN NHẮN THẬT suy ra.

    Phạm vi mặc định (`tatca=-1` = người dùng CHƯA bấm ô tích):
      * **Quản lý (`user.manage`/`user.manage_team`) -> XEM HẾT CỦA TẤT CẢ.**
        Admin không phải người ôm lead; mặc định "chỉ của tôi" khiến họ mở màn
        ra thấy trống trơn mà không hiểu vì sao.
      * Nhân viên -> khách CỦA MÌNH (đúng việc hằng ngày của họ).
    Bấm ô tích thì `tatca` thành 0/1 và ý người dùng thắng — quản lý vẫn bó về
    "chỉ của tôi" được nếu họ có ôm lead riêng.
    """
    from app.services import sale_service

    user = _nguoi(request)
    uid = int(user.get("sub") or 0) or None
    quan_ly = (co_quyen(user, "user.manage")
               or co_quyen(user, "user.manage_team"))
    ca_doi = quan_ly if tatca < 0 else (bool(tatca) and quan_ly)
    data = sale_service.bang_viec(
        owner_id=None if ca_doi else uid, q=q, an_da_cham=not hien_da_cham)
    # Lọc theo ô đếm (bấm ô nào thì bảng chỉ còn nhóm đó)
    if loc:
        chon = {
            "hom_nay": lambda x: x["buoc_ke"] and x["buoc_ke"]["san_sang"],
            "qua_han": lambda x: bool(x.get("qua_han")),
            "vua_phan_hoi": lambda x: x["cho_dap"],
            "yeu_cau_chia": lambda x: not x.get("owner_id"),
        }.get(loc)
        if chon:
            data["the"] = [x for x in data["the"] if chon(x)]
            giu = {x["id"] for x in data["the"]}
            data["theo_cot"] = {k: [x for x in v if x["id"] in giu]
                                for k, v in data["theo_cot"].items()}
    return HTMLResponse(views_sale.render_bang_viec(
        data, loc={"q": q, "loc": loc, "tatca": 1 if ca_doi else 0,
                   "hien_da_cham": hien_da_cham},
        che_do="pipeline" if cd == "pipeline" else "bang",
        ca_doi=ca_doi, quan_ly=quan_ly, flash=ok, loi=error))


@router.post("/bang-viec/{lead_id}/keo")
async def bang_viec_keo(request: Request, lead_id: int):
    """Kéo thẻ sang cột khác. Cột "Bước N" đặt luôn con trỏ = N-1."""
    from app.services import sale_service

    f = await request.form()
    try:
        sale_service.keo_the(lead_id, str(f.get("cot") or ""),
                             nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec", error=err.message)
    return _ve("/crm/bang-viec", ok="Đã chuyển cột.")


@router.post("/bang-viec/{lead_id}/tu-choi")
async def bang_viec_tu_choi(request: Request, lead_id: int):
    """🚫 Từ chối — đóng ĐỢT NÀY. CỐ Ý không hỏi xác nhận."""
    from app.services import sale_service

    try:
        sale_service.tu_choi(lead_id,
                             nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec", error=err.message)
    return _ve("/crm/bang-viec",
               ok="Đã đóng đợt này — khách nhắn lại là thẻ tự quay về bảng.")


@router.post("/bang-viec/{lead_id}/ngung")
async def bang_viec_ngung(request: Request, lead_id: int):
    """⛔ Ngừng chăm sóc — dừng HẲN, bắt buộc lý do."""
    from app.services import sale_service

    f = await request.form()
    try:
        sale_service.ngung_cham_soc(
            lead_id, str(f.get("ly_do") or ""),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec", error=err.message)
    return _ve("/crm/bang-viec",
               ok="Đã ngừng chăm sóc — thẻ không tự quay lại, phải chờ khách "
                  "nhắn trước.")


@router.post("/bang-viec/{lead_id}/mo-lai")
async def bang_viec_mo_lai(request: Request, lead_id: int):
    from app.services import sale_service

    try:
        sale_service.mo_lai(lead_id,
                            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec", error=err.message)
    return _ve("/crm/bang-viec", ok="Đã trả thẻ về cho máy xếp cột.")


@router.post("/bang-viec/do-lai")
async def bang_viec_do_lai(request: Request):
    """Chạy lại bộ dò con trỏ ngay (không chờ worker)."""
    from app.services import sale_service

    kq = sale_service.quet_tat_ca()
    return _ve("/crm/bang-viec",
               ok=f'Đã dò lại: {kq["doi_con_tro"]} thẻ đổi con trỏ · '
                  f'{kq["nha_cot"]} thẻ tự nhả khỏi cột đặt tay.')


@router.get("/thang-sale", response_class=HTMLResponse)
async def thang_sale(request: Request, ok: str = "",
                     error: str = "") -> HTMLResponse:
    """Cấu hình thang bám đuổi — từ khoá của từng bước."""
    from app.db.repositories import sale_repo

    if chan := _chan(request, "user.manage", "Thang bám đuổi Sale"):
        return chan
    return HTMLResponse(views_sale.render_thang(
        sale_repo.thang(), flash=ok, loi=error))


@router.post("/thang-sale")
async def thang_sale_luu(request: Request):
    from app.services import sale_service

    if chan := _chan(request, "user.manage", "Thang bám đuổi Sale"):
        return chan
    f = await request.form()
    try:
        sale_service.luu_buoc(
            int(str(f.get("step_no") or "0") or 0),
            name=str(f.get("name") or ""), work=str(f.get("work") or ""),
            kw_nv=str(f.get("kw_nv") or ""), kw_kh=str(f.get("kw_kh") or ""))
    except (ApiError, ValueError) as err:
        return _ve("/crm/thang-sale", error=getattr(err, "message", str(err)))
    return _ve("/crm/thang-sale", ok="Đã lưu bước.")


# =====================================================================
# C6 — BẢNG VIỆC CSKH + đợt khuyến mãi (port mẫu Kallet cskh_quy_trinh.php).
# Luật ở services/cskh_service.py; SQL ở db/repositories/cskh_repo.py.
#
# ⚠️ KHÔNG phải màn /crm/cham-soc (B9 — liệu trình C01-C09 của MỘT đơn). Đây là
# vòng đời khách SAU khi nhận hàng: cảm ơn → voucher → thang mua lại.
# =====================================================================
@router.get("/bang-viec-cskh", response_class=HTMLResponse)
async def bang_viec_cskh(request: Request, q: str = "", viec: int = 0,
                         toi: int = 0, ok: str = "",
                         error: str = "") -> HTMLResponse:
    """Bảng việc CSKH — cột do máy suy ra từ NGÀY NHẬN HÀNG CUỐI."""
    from app.services import cskh_service

    if chan := _chan(request, "customer.view", "Bảng việc CSKH"):
        return chan
    user = _nguoi(request)
    # "Khách của tôi": người không có customer.view_all luôn bị bó về khách mình
    # phụ trách, dù có tick ô hay không — chặn ở tầng dữ liệu, không ẩn nút.
    minh = int(user.get("sub") or 0) or None
    pham_vi = minh if (toi or not co_quyen(user, "user.manage")) else None
    data = cskh_service.bang_viec(owner_id=pham_vi, q=q.strip(),
                                  chi_viec=bool(viec))
    return HTMLResponse(views_cskh.render_bang_viec(
        data, user, {"q": q, "viec": viec, "toi": toi},
        sua=co_quyen(user, "customer.edit"), flash=ok, loi=error))


@router.post("/bang-viec-cskh/{customer_id}/cot")
async def cskh_keo_the(request: Request, customer_id: int):
    """Kéo thẻ sang cột khác. Cột máy suy ra hoàn toàn thì service từ chối."""
    from app.services import cskh_service

    if chan := _chan(request, "customer.edit", "Bảng việc CSKH"):
        return chan
    f = await request.form()
    cot = str(f.get("cot") or "").strip()
    if not cot:
        return _ve("/crm/bang-viec-cskh")
    try:
        cskh_service.keo_the(customer_id, cot,
                             nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec-cskh", error=err.message)
    return _ve("/crm/bang-viec-cskh", ok="Đã chuyển cột.")


@router.post("/bang-viec-cskh/{customer_id}/mo-lai")
async def cskh_mo_lai(request: Request, customer_id: int):
    from app.services import cskh_service

    if chan := _chan(request, "customer.edit", "Bảng việc CSKH"):
        return chan
    try:
        cskh_service.mo_lai(customer_id,
                            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/bang-viec-cskh", error=err.message)
    return _ve("/crm/bang-viec-cskh", ok="Đã trả thẻ về cho máy xếp.")


@router.post("/bang-viec-cskh/{customer_id}/cham")
async def cskh_ghi_cham(request: Request, customer_id: int):
    """Ghi một lượt chăm — ĐÓNG mốc đang mở của khách."""
    from app.services import cskh_service

    if chan := _chan(request, "customer.edit", "Bảng việc CSKH"):
        return chan
    f = await request.form()
    cskh_service.ghi_cham(customer_id,
                          nguoi=int(_nguoi(request).get("sub") or 0) or None,
                          tom_tat=str(f.get("tom_tat") or ""))
    return _ve("/crm/bang-viec-cskh", ok="Đã ghi lượt chăm.")


@router.post("/bang-viec-cskh/{customer_id}/goi")
async def cskh_ghi_goi(request: Request, customer_id: int):
    """Ghi kết quả cuộc gọi GĐ1 — "nghe máy" là tín hiệu đủ điều kiện tặng
    voucher, "không nghe" thì việc gọi coi như đã làm (không gọi lần 2)."""
    from app.services import cskh_service

    if chan := _chan(request, "customer.edit", "Bảng việc CSKH"):
        return chan
    f = await request.form()
    try:
        cskh_service.ghi_goi(customer_id, str(f.get("ket_qua") or ""),
                             nguoi=int(_nguoi(request).get("sub") or 0) or None,
                             tom_tat=str(f.get("tom_tat") or ""))
    except ApiError as err:
        return _ve("/crm/bang-viec-cskh", error=err.message)
    return _ve("/crm/bang-viec-cskh", ok="Đã ghi cuộc gọi.")


@router.get("/cskh/khuyen-mai", response_class=HTMLResponse)
async def cskh_khuyen_mai(request: Request, ok: str = "",
                          error: str = "") -> HTMLResponse:
    """Đợt khuyến mãi cho mốc CSKH có cờ khuyến mãi — NHẬP TAY từng đợt."""
    from app.db.repositories import cskh_repo

    if chan := _chan(request, "customer.view", "Đợt khuyến mãi CSKH"):
        return chan
    user = _nguoi(request)
    return HTMLResponse(views_cskh.render_khuyen_mai(
        cskh_repo.ctkm_ds(), user, sua=co_quyen(user, "campaign.manage"),
        flash=ok, loi=error))


@router.post("/cskh/khuyen-mai")
async def cskh_khuyen_mai_luu(request: Request):
    from app.services import cskh_service

    if chan := _chan(request, "campaign.manage", "Đợt khuyến mãi CSKH"):
        return chan
    f = await request.form()
    try:
        cskh_service.luu_ctkm(
            None, ten=str(f.get("ten") or ""),
            noi_dung=str(f.get("noi_dung") or ""),
            tu_ngay=str(f.get("tu_ngay") or "") or None,
            den_ngay=str(f.get("den_ngay") or "") or None,
            active=bool(f.get("bat")),
            nguoi=int(_nguoi(request).get("sub") or 0) or None)
    except ApiError as err:
        return _ve("/crm/cskh/khuyen-mai", error=err.message)
    return _ve("/crm/cskh/khuyen-mai", ok="Đã lưu đợt khuyến mãi.")


@router.post("/cskh/khuyen-mai/{promo_id}/bat")
async def cskh_khuyen_mai_bat(request: Request, promo_id: int):
    """Bật/tắt một đợt. Nhiều đợt cùng bật thì mốc lấy đợt MỚI NHẤT."""
    from app.db.repositories import cskh_repo
    from app.services import cskh_service

    if chan := _chan(request, "campaign.manage", "Đợt khuyến mãi CSKH"):
        return chan
    cu = next((r for r in cskh_repo.ctkm_ds() if int(r["id"]) == promo_id), None)
    if not cu:
        return _ve("/crm/cskh/khuyen-mai", error="Không thấy đợt khuyến mãi.")
    cskh_service.luu_ctkm(
        promo_id, ten=cu["name"], noi_dung=cu["content"],
        tu_ngay=cu["start_on"], den_ngay=cu["end_on"],
        active=not cu["active"])
    return _ve("/crm/cskh/khuyen-mai",
               ok="Đã tắt đợt." if cu["active"] else "Đã bật đợt.")


@router.post("/cskh/khuyen-mai/{promo_id}/xoa")
async def cskh_khuyen_mai_xoa(request: Request, promo_id: int):
    from app.services import cskh_service

    if chan := _chan(request, "campaign.manage", "Đợt khuyến mãi CSKH"):
        return chan
    cskh_service.xoa_ctkm(promo_id)
    return _ve("/crm/cskh/khuyen-mai", ok="Đã xoá đợt.")


@router.post("/cskh/dung-thang")
async def cskh_dung_thang(request: Request):
    """Dựng lại thang mốc từ 3 con số ở Cài đặt.

    Đây là dữ liệu điều khiển bảng việc của cả đội nên đóng sau quyền quản trị,
    và luôn kể ra đã sửa mấy mốc để người bấm biết mình vừa làm gì.
    """
    from app.services import cskh_service

    if chan := _chan(request, "user.manage", "Bảng việc CSKH"):
        return chan
    viec = cskh_service.seed_thang(dry=False)
    return _ve("/crm/bang-viec-cskh",
               ok=f"Đã dựng lại thang mốc ({len(viec)} thay đổi).")
