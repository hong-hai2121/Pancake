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
from app.web.views import crm as views
from app.web.views.admin import render_403

router = APIRouter(prefix="/crm", tags=["web-crm"])


def _nguoi(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


def _ve(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    duoi = f"?ok={quote(ok)}" if ok else (f"?error={quote(error)}" if error else "")
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
async def trang_chu(request: Request) -> HTMLResponse:
    """Màn 2 — Trang chủ theo vai trò (FR-001 'chuyển tới dashboard theo vai
    trò'): 9 vị trí mỗi vị trí một bộ số + lối tắt; đăng nhập xong vào đây.

    Phạm vi số liệu: Sale/CSKH thấy CỦA MÌNH; trưởng nhóm thấy CẢ ĐỘI (tra
    teams.manager_id trong DB, không tin token); các vai còn lại xem số chung
    đúng mảng mình phụ trách."""
    user = getattr(request.state, "user", None) or {}
    nhom = _NHOM_VAI_TRO.get(user.get("role") or "", "khac")
    data = repo.trang_chu(nhom, int(user.get("sub", 0) or 0))
    return HTMLResponse(views.render_trang_chu(nhom, data, user))


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


@router.get("/khach-hang", response_class=HTMLResponse)
async def khach_hang(q: str = "", status: str = "", owner_id: int = 0,
                     has_order: str = "") -> HTMLResponse:
    """Màn 8 — danh sách khách CRM + bộ lọc (khác /khach-hang của bot Pancake).

    Dùng `customer_repo.list_customers` (bộ lọc CUSTOMER-001 của B1) khi có lọc;
    không lọc gì thì đi đường cũ để giữ nguyên cột hội thoại Pancake."""
    from app.db.repositories import customer_repo, user_repo

    co_loc = bool(status or owner_id or has_order)
    if co_loc:
        rows, total = customer_repo.list_customers(
            keyword=q, status=status or None,
            owner_id=owner_id or None,
            has_order=None if has_order == "" else has_order == "1",
            limit=100)
    else:
        rows, total = repo.list_customers(q=q)
    nv = user_repo.list_users(status="active", limit=200)[0]
    return HTMLResponse(views.render_khach_hang(
        rows, total, q,
        loc={"status": status, "owner_id": owner_id, "has_order": has_order},
        nhan_vien=nv))


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
async def pipeline(st: int = 0) -> HTMLResponse:
    """Màn 11 (khung) — Kanban 13 giai đoạn. `?st=<stage_id>` tô sáng + cuộn
    tới cột đó (đường vào từ khối Sale ở menu trái)."""
    return HTMLResponse(views.render_pipeline(repo.pipeline_board(), st=st))


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


@router.get("/don-hang", response_class=HTMLResponse)
async def don_hang(q: str = "", status: str = "", order_type: str = "",
                   tu: str = "") -> HTMLResponse:
    """Màn 21 — danh sách đơn + đếm theo trạng thái + bộ lọc.

    Có lọc thì đi `order_repo.list_orders` (bộ lọc của B7); không lọc thì giữ
    đường cũ (30 đơn mới nhất) cho nhẹ."""
    from app.db.repositories import order_repo

    data = repo.orders_summary()
    if q or status or order_type or tu:
        from app.db.repositories import user_repo

        rows, tong = order_repo.list_orders(
            status=status, order_type=order_type, q=q, tu=tu, limit=100)
        # list_orders (B7) trả `customer_name` + `sale_owner_id`, còn view dùng
        # khuôn `khach`/`sale` — quy về một khuôn, tra tên Sale một lần cho cả mẻ
        ten_nv = {u["id"]: u["name"]
                  for u in user_repo.list_users(limit=500)[0]}
        data["rows"] = [
            {**r, "khach": r.get("customer_name"),
             "sale": ten_nv.get(r.get("sale_owner_id"))}
            for r in rows
        ]
        data["tong"] = tong
    return HTMLResponse(views.render_don_hang(
        data, loc={"q": q, "status": status, "order_type": order_type, "tu": tu}))


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
