"""Route khu Quản trị (A5): /quan-tri/... — cần quyền `user.manage`
(riêng nhật ký: `audit.view`). Tab Nhân viên mở thêm cho `user.manage_team`:
trưởng nhóm Sale/CSKH chỉ thấy đội mình, chỉ TẠO + reset mật khẩu cho thành
viên đội (phạm vi ép trong `user_service.pham_vi_doi`). Gọi chung services
với API nên luật + audit chỉ có một chỗ; lỗi nghiệp vụ (ApiError) hiện thành
dải đỏ trên trang.
"""

import csv
import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                               Response)

from app.core import runtime_config
from app.core.deps import co_quyen
from app.core.errors import ApiError
from app.db.repositories import audit_repo, integration_repo, org_repo, user_repo
from app.services import (
    cai_dat_service, integration_service, org_service, user_service,
)
from app.services import tieng_viet as tv
from app.web.views.admin import (
    render_403,
    render_cai_dat,
    render_audit,
    render_roles,
    render_the_pancake,
    render_user_detail,
    render_users,
)

router = APIRouter(prefix="/quan-tri", tags=["web-admin"])


def _user(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


def _chan(request: Request, quyen: str = "user.manage") -> HTMLResponse | None:
    if not co_quyen(_user(request), quyen):
        return HTMLResponse(render_403(), status_code=403)
    return None


def _chan_nv(request: Request) -> HTMLResponse | None:
    """Tab Nhân viên: Admin/Chủ DN (`user.manage`) hoặc trưởng nhóm
    (`user.manage_team`) đều vào được — phạm vi hẹp/rộng do service quyết."""
    user = _user(request)
    if not (co_quyen(user, "user.manage") or co_quyen(user, "user.manage_team")):
        return HTMLResponse(render_403(), status_code=403)
    return None


def _ip_ua(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
    }


def _back(path: str, ok: str = "", error: str = "") -> RedirectResponse:
    # `path` có thể đã mang sẵn query (vd /quan-tri/cai-dat?sec=sale) — nối
    # tiếp bằng "&", nối bằng "?" nữa là hỏng tham số cuối.
    noi = "&" if "?" in path else "?"
    tham_so = (f"{noi}ok={quote(ok)}" if ok else
               (f"{noi}error={quote(error)}" if error else ""))
    return RedirectResponse(path + tham_so, status_code=303)


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v).strip() for k, v in form.items()}


def _to_int(v: str) -> int | None:
    return int(v) if v.strip().isdigit() else None


# ------------------------------------------------------------ nhân viên
@router.get("/nhan-vien", response_class=HTMLResponse)
async def users_page(
    request: Request, q: str = "", nhom: str = "", ok: str = "", error: str = ""
):
    if chan := _chan_nv(request):
        return chan
    try:
        pham_vi = user_service.pham_vi_doi(_user(request))
    except ApiError as err:
        return HTMLResponse(render_403(err.message), status_code=403)
    # Chip nhóm lọc NGAY trên trình duyệt nên admin luôn nhận đủ danh sách;
    # `nhom` trên URL chỉ để chọn sẵn chip lúc mở. Trưởng nhóm vẫn bị cắt
    # về đội mình từ server (an ninh, không phải giao diện).
    if pham_vi:
        nhom = ""
    users, _total = user_repo.list_users(
        q=q, team_id=pham_vi["team_id"] if pham_vi else None, limit=100,
    )
    return HTMLResponse(render_users(
        users, org_repo.list_roles(), org_repo.list_teams(), q=q, nhom=nhom,
        co_xuat=co_quyen(_user(request), "data.export"),
        ok=ok, error=error, gioi_han=pham_vi,
        **_pancake_nhan_vien(),
    ))


def _pancake_nhan_vien() -> dict:
    """Dữ liệu cho cột 'Ghép Pancake'. DB lỗi thì trả rỗng — cột hiện 'CHƯA GHÉP'
    chứ màn Nhân viên KHÔNG được chết vì khu tích hợp."""
    try:
        return {"pancake": integration_repo.staff_theo_user(),
                "pancake_thua": integration_repo.staff_chua_ghep()}
    except Exception:  # noqa: BLE001
        return {}


@router.get("/nhan-vien/xuat-excel")
async def users_export(request: Request):
    """Xuất danh sách nhân viên ra CSV mở được bằng Excel (BOM UTF-8, chấm
    phẩy — khớp Excel bản địa VN). Cần thêm quyền `data.export`; trưởng nhóm
    có quyền đó cũng chỉ xuất được đội mình. Mỗi lần xuất đều ghi audit."""
    if chan := _chan_nv(request):
        return chan
    actor = _user(request)
    if not co_quyen(actor, "data.export"):
        return HTMLResponse(
            render_403("Xuất Excel cần quyền data.export"), status_code=403
        )
    try:
        pham_vi = user_service.pham_vi_doi(actor)
    except ApiError as err:
        return HTMLResponse(render_403(err.message), status_code=403)
    users, _ = user_repo.list_users(
        team_id=pham_vi["team_id"] if pham_vi else None, limit=100,
    )

    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Username", "Họ tên", "Email", "SĐT", "Vai trò", "Nhóm",
                "Trạng thái", "Đăng nhập cuối"])
    for u in users:
        w.writerow([
            u["username"], u["name"], u["email"], u["phone"] or "",
            u["role_name"] or "", u["team_name"] or "", u["status"],
            u["last_login_at"].strftime("%d/%m/%Y %H:%M") if u["last_login_at"] else "",
        ])
    audit_repo.ghi(
        action="users_export", object_type="user", user_id=actor.get("id"),
        reason=f"xuất {len(users)} nhân viên", **_ip_ua(request),
    )
    ten = f"nhan-vien-{datetime.now():%Y%m%d}.csv"
    # BOM đầu file: Excel cần nó mới nhận UTF-8, thiếu là tiếng Việt vỡ font
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ten}"'},
    )


@router.post("/nhan-vien")
async def create_user(request: Request):
    if chan := _chan_nv(request):
        return chan
    f = await _form(request)
    try:
        data = user_service.create_user(
            {
                "name": f.get("name", ""), "email": f.get("email", ""),
                "username": f.get("username", ""),
                "password": f.get("password") or None,
                "phone": f.get("phone") or None,
                "role_id": _to_int(f.get("role_id", "")),
                "team_id": _to_int(f.get("team_id", "")),
            },
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/nhan-vien", error=err.message)
    return _back(
        "/quan-tri/nhan-vien",
        ok=f"Đã tạo {data['username']} — mật khẩu (hiện MỘT lần): {data['initial_password']}",
    )


@router.get("/nhan-vien/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: int, ok: str = "", error: str = ""):
    if chan := _chan(request):
        return chan
    u = user_repo.get_user(user_id)
    if not u:
        return _back("/quan-tri/nhan-vien", error="Không tìm thấy nhân viên")
    others = [
        x for x in user_repo.list_users(status="active", limit=100)[0]
        if x["id"] != user_id
    ]
    return HTMLResponse(render_user_detail(
        u, org_repo.list_roles(), org_repo.list_teams(), others,
        user_repo.list_sessions(user_id), ok=ok, error=error,
    ))


@router.post("/nhan-vien/{user_id}/sua")
async def edit_user(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        user_service.update_user(
            user_id,
            {
                "name": f.get("name") or None, "email": f.get("email") or None,
                "username": f.get("username") or None,
                "phone": f.get("phone") or None,
                "role_id": _to_int(f.get("role_id", "")),
                "team_id": _to_int(f.get("team_id", "")),
            },
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error=err.message)

    # Ô "Ghép Pancake" của hộp thoại sửa nhanh ở màn danh sách. Giá trị dạng
    # "provider|uuid", rỗng = gỡ ghép. Chỉ áp khi người bấm có integration.manage
    # — sửa hồ sơ là user.manage, ghép Pancake là quyền KHÁC, không gộp làm một.
    ve = ("/quan-tri/nhan-vien" if f.get("ve") == "ds"
          else f"/quan-tri/nhan-vien/{user_id}")
    if "pancake_staff" in f and co_quyen(_user(request), "integration.manage"):
        nguon, _, uuid = f.get("pancake_staff", "").partition("|")
        try:
            if uuid:
                integration_service.gan_nhan_vien(
                    nguon, uuid, user_id, actor=_user(request))
            else:
                _go_ghep_pancake(user_id, _user(request))
        except ApiError as err:
            return _back(ve, error=err.message)
    return _back(ve, ok="Đã lưu thay đổi")


def _go_ghep_pancake(user_id: int, actor: dict) -> None:
    """Gỡ mọi ánh xạ Pancake đang trỏ về tài khoản CRM này."""
    for row in integration_repo.list_staff():
        if row["user_id"] == user_id:
            integration_service.gan_nhan_vien(
                row["provider"], row["external_staff_id"], None, actor=actor)


@router.post("/nhan-vien/{user_id}/trang-thai")
async def user_status(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        u = user_service.set_status(
            user_id, f.get("status", ""), actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        chi_tiet = "; ".join(f"{k} {v}" for k, v in err.errors.items())
        return _back("/quan-tri/nhan-vien",
                     error=err.message + (f" ({chi_tiet})" if chi_tiet else ""))
    return _back("/quan-tri/nhan-vien", ok=f"{u['username']}: {u['status']}")


@router.post("/nhan-vien/{user_id}/reset-mat-khau")
async def user_reset_password(request: Request, user_id: int):
    if chan := _chan_nv(request):
        return chan
    try:
        data = user_service.reset_password(
            user_id, actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        return _back("/quan-tri/nhan-vien", error=err.message)
    return _back(
        "/quan-tri/nhan-vien",
        ok=f"Mật khẩu mới (hiện MỘT lần): {data['new_password']}",
    )


@router.post("/nhan-vien/{user_id}/chuyen-khach")
async def user_transfer(request: Request, user_id: int):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    nguoi_nhan = _to_int(f.get("new_owner_id", ""))
    if not nguoi_nhan:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error="Chưa chọn người nhận")
    try:
        kq = user_service.transfer_customers(
            user_id, {"new_owner_id": nguoi_nhan},
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back(f"/quan-tri/nhan-vien/{user_id}", error=err.message)
    so = ", ".join(f"{k}: {v}" for k, v in kq.items() if isinstance(v, int))
    return _back(f"/quan-tri/nhan-vien/{user_id}",
                 ok=f"Đã chuyển sang {kq['to']} ({so or 'không có gì để chuyển'})")


# ------------------------------------------------------------ vai trò & quyền
@router.get("/phan-quyen", response_class=HTMLResponse)
async def roles_page(request: Request, ok: str = "", error: str = ""):
    if chan := _chan(request):
        return chan
    users, _ = user_repo.list_users(status="active", limit=100)
    return HTMLResponse(render_roles(
        org_repo.list_roles(), org_repo.list_permissions(),
        org_repo.list_teams(), users, ok=ok, error=error,
    ))


@router.post("/phan-quyen/{role_id:int}")
async def save_role_perms(request: Request, role_id: int):
    if chan := _chan(request):
        return chan
    form = await request.form()
    perms = [str(v) for v in form.getlist("perm")]
    try:
        org_service.set_role_permissions(
            role_id, perms, actor=_user(request), **_ip_ua(request)
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã lưu {len(perms)} quyền cho vai trò")


@router.post("/phan-quyen/vai-tro")
async def create_role(request: Request):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        role = org_service.create_role(
            f.get("name", ""), f.get("description") or None,
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã tạo vai trò {role['name']}")


@router.post("/phan-quyen/nhom")
async def create_team(request: Request):
    if chan := _chan(request):
        return chan
    f = await _form(request)
    try:
        team = org_service.create_team(
            f.get("name", ""), f.get("department") or None,
            _to_int(f.get("manager_id", "")),
            actor=_user(request), **_ip_ua(request),
        )
    except ApiError as err:
        return _back("/quan-tri/phan-quyen", error=err.message)
    return _back("/quan-tri/phan-quyen", ok=f"Đã tạo nhóm {team['name']}")


# ------------------------------------------------------------ nhật ký
@router.get("/nhat-ky", response_class=HTMLResponse)
async def audit_page(
    request: Request, action: str = "", page: int = 1, ok: str = "", error: str = ""
):
    if chan := _chan(request, "audit.view"):
        return chan
    page = max(page, 1)
    rows, total = audit_repo.list_logs(action=action, limit=30, offset=(page - 1) * 30)
    return HTMLResponse(render_audit(
        rows, total, action=action, page=page, ok=ok, error=error,
    ))


# ------------------------------------------------------------ cài đặt (màn 78)
@router.get("/cai-dat", response_class=HTMLResponse)
async def cai_dat_page(request: Request, sec: str = "", ok: str = "",
                       error: str = ""):
    """Công tắc bật/tắt + nhịp chạy worker, đổi được ngay trên web (SYSTEM-001).

    `?sec=` chọn mục con (bố cục menu bên trái port từ mẫu Kallet). `?sec=log`
    là Nhật ký cấu hình — đọc `audit_logs` lọc theo hai action của cài đặt, chứ
    KHÔNG đẻ bảng `config_log` riêng như mẫu (một nguồn sự thật).
    """
    if (chan := _chan(request)):
        return chan
    nhat_ky = audit_repo.nhat_ky_cai_dat() if sec == "log" else []
    than_moc, js = "", ""
    nhom = cai_dat_service.theo_nhom()
    # Mục "Mốc thời gian" là mục MẶC ĐỊNH (đứng đầu menu) nên phải dựng cho MỌI
    # `sec` sẽ rơi về nó: rỗng, "moc", nhóm đã ẩn (`sale` — nay nằm trọn trong
    # mục này), hay `sec` bịa. Không dựng thì view lặng lẽ lùi về nhóm đầu bảng
    # và người bấm link cũ `?sec=sale` lạc sang màn Đồng bộ.
    from app.web.views import cai_dat as v_cai_dat

    hien = [g["ma"] for g in nhom if g["ma"] not in v_cai_dat.NHOM_AN]
    dac_biet: dict[str, str] = {}
    if sec not in hien and sec != "log" and sec not in v_cai_dat.MA_DAC_BIET:
        sec = "moc"
    if sec == "moc":
        dac_biet["moc"], js = _than_moc(nhom)
    elif sec == "nhan_dien":
        dac_biet["nhan_dien"], js = _than_nhan_dien(nhom)
    elif sec == "goi_y":
        dac_biet["goi_y"] = _than_goi_y()
    truoc, sau = {}, {}
    # T3 — ngưỡng hạng thẻ nay sửa ở đây (mục Ưu đãi), không còn ở /crm/hang-the.
    if sec == "uu_dai":
        from app.services import voucher_service

        tc = voucher_service.toan_canh()
        sau["uu_dai"] = v_cai_dat.bang_nguong_hang(
            tc["bac"], tc["quyen_loi"], bool(tc.get("la_khung")))
    # Đ2 — mục Vòng đời: 3 luật + nguồn lead, kèm số khách THẬT đang bị chạm.
    if sec == "vong_doi":
        from app.core import runtime_config as _rc
        from app.db.repositories import sale_repo

        sau["vong_doi"] = (
            v_cai_dat.khoi_nguon_lead(sale_repo.dem_theo_loai_hoi_thoai(),
                                      bool(_rc.bat("board_chi_inbox")))
            + v_cai_dat.khoi_ban_giao())
    # Đ2 — công tắc gửi tin: form RIÊNG, quyền riêng, lưu ngay khi bấm.
    if sec == "gui_tin":
        from app.services import cong_tac_gui_tin as ct

        truoc["gui_tin"] = v_cai_dat.khoi_cong_tac_gui_tin(
            ct.dien_giai(), ct.CHE_DO,
            co_quyen(_user(request), "gui_tin.bat_cong_tac"))
    return HTMLResponse(render_cai_dat(
        nhom, sec=sec, nhat_ky=nhat_ky, dac_biet=dac_biet, script=js,
        truoc=truoc, sau=sau, ok=ok, error=error))


def _than_nhan_dien(nhom: list[dict]) -> tuple[str, str]:
    """Đ2 — mục Kịch bản nhận diện: mẫu NỀN (hằng trong mã) + mẫu admin khai."""
    from app.db.repositories import nhan_dien_repo
    from app.services import nhan_dien
    from app.web.views import cai_dat as v_cai_dat
    from app.web.views import cai_dat_nhan_dien as v_nd

    them: dict[str, list[dict]] = {k: [] for k in nhan_dien_repo.LOAI}
    for r in nhan_dien_repo.tat_ca():
        them.setdefault(r["kind"], []).append(dict(r))
    nen = {
        "goi": list(tv.MAU_DA_GOI), "chan": list(tv.MAU_CHAN_GOI),
        "voucher": list(nhan_dien.TU_VOUCHER_NEN),
        "viet_tat": [f"{k} → {v}" for k, v in sorted(tv.VIET_TAT.items())],
    }
    theo_ma = {m["code"]: m for g in nhom for m in g["muc"]}
    o_gap = (v_cai_dat._o(theo_ma["nhandien_goi_gap"])
             if "nhandien_goi_gap" in theo_ma else "")
    return v_nd.render_nhan_dien(nen, them, o_gap, True), _ND_JS


def _than_goi_y() -> str:
    """Đ2 — mục Gợi ý kịch bản: luật từ khoá → kịch bản."""
    from app.db.repositories import giam_sat_repo
    from app.web.views import cai_dat_nhan_dien as v_nd

    return v_nd.render_goi_y(giam_sat_repo.luat_goi_y_tat_ca(),
                             giam_sat_repo.kich_ban_chon(), True)


@router.post("/cai-dat/che-do-gui-tin")
async def cai_dat_che_do_gui_tin(request: Request):
    """Đ2 — gạt công tắc gửi tin. Quyền RIÊNG `gui_tin.bat_cong_tac`.

    Không đi chung nút Lưu của nhóm: đây là quyết định không thu hồi được, phải
    là một hành động cố ý riêng biệt chứ không phải hệ quả phụ của việc ai đó
    sửa nhịp worker rồi bấm Lưu cả mục.
    """
    from app.services import cong_tac_gui_tin as ct

    if (chan := _chan(request, "gui_tin.bat_cong_tac")):
        return chan
    ve = "/quan-tri/cai-dat?sec=gui_tin"
    form = await _form(request)
    try:
        ma = ct.dat_che_do(form.get("che_do", ""), actor=_user(request))
    except ApiError as err:
        return _back(ve, error=err.message)
    nhan = ct.CHE_DO[ma][0]
    if ma == "that" and ct.khoa_cung():
        return _back(ve, ok=f"Đã đặt chế độ {nhan}, nhưng KHOÁ CỨNG hệ thống "
                            "vẫn đóng nên máy chưa gửi tin ra ngoài.")
    return _back(ve, ok=f"Đã chuyển chế độ gửi tin sang {nhan}.")


def _than_moc(nhom: list[dict]) -> tuple[str, str]:
    """Dựng thân mục Mốc thời gian + JS của nó. Gom 3 nguồn: bước thang (C5) ·
    mốc chăm (C6) · khoá tự do của cột (1G/1H)."""
    from app.core import runtime_config
    from app.db.repositories import cskh_repo, sale_repo
    from app.web.views import cai_dat as v_cai_dat
    from app.web.views import cai_dat_moc as v_moc

    # 11 ô số của thang Sale (T2) — dựng bằng đúng bộ ô của màn Cài đặt để
    # trông y hệt các mục khác, khỏi đẻ kiểu ô thứ hai.
    theo_ma = {m["code"]: m for g in nhom for m in g["muc"]}
    o_so = ""
    for tieu_de, ma_list in v_moc.SO_1A:
        o = "".join(v_cai_dat._o(theo_ma[c]) for c in ma_list if c in theo_ma)
        if o:
            o_so += (f'<div class="mnhom">{tieu_de}</div>'
                     f'<div class="cd-grid">{o}</div>')
    dat_cot = runtime_config.lay_tu_do_theo_tien_to("bn_")
    dat_cot.update(runtime_config.lay_tu_do_theo_tien_to("bw_"))
    return (
        v_moc.render(sale_repo.thang_tat_ca(),
                     cskh_repo.moc(chi_active=False), dat_cot, o_so),
        _MOC_JS,
    )


@router.post("/cai-dat")
async def cai_dat_luu(request: Request):
    """Lưu MỘT nhóm cài đặt (SYSTEM-002), hoặc trả cả nhóm về mặc định .env.

    Checkbox không tick thì trình duyệt KHÔNG gửi ô đó lên — nên phải dựng lại
    đủ danh sách công tắc của nhóm rồi coi ô vắng mặt là TẮT, nếu không thì tắt
    công tắc sẽ chẳng bao giờ lưu được.
    """
    if (chan := _chan(request)):
        return chan
    form = await _form(request)
    nhom = form.pop("nhom", "")
    if nhom == "moc":
        return await _luu_moc(request, form)
    ve_mac_dinh = form.pop("mac_dinh", "") == "1"
    ma_trong_nhom = [m["code"] for m in runtime_config.danh_sach()
                     if m["nhom"] == nhom]
    # Lưu xong quay lại ĐÚNG mục đang mở — bố cục mẫu: bắn người dùng về mục
    # đầu tiên sau mỗi lần Lưu là họ phải đi tìm lại chỗ vừa sửa.
    ve = f"/quan-tri/cai-dat?sec={quote(nhom)}" if nhom else "/quan-tri/cai-dat"
    if not ma_trong_nhom:
        return _back("/quan-tri/cai-dat", error="Nhóm cài đặt không hợp lệ")

    try:
        if ve_mac_dinh:
            for code in ma_trong_nhom:
                cai_dat_service.dat_lai_mac_dinh(code, actor=_user(request))
            return _back(ve, ok="Đã trả mục này về mặc định .env")

        du_lieu: dict = {}
        for code in ma_trong_nhom:
            muc = runtime_config.THEO_MA[code]
            if muc.kieu == "bool":
                du_lieu[code] = code in form          # vắng mặt = tắt
            elif code in form:
                # Ô CHỮ để trống là một giá trị hợp lệ ("chưa điền" — module ăn
                # theo nó tự tắt), phải ghi được. Ô SỐ để trống thì bỏ qua:
                # xoá số đi không có nghĩa gì, muốn về mặc định thì bấm nút.
                if form[code] != "" or muc.kieu == "str":
                    du_lieu[code] = form[code]
        cai_dat_service.dat_nhieu(du_lieu, actor=_user(request))
        if nhom == "uu_dai":
            _luu_nguong_hang(request, form)
    except ApiError as err:
        return _back(ve, error=err.message)
    return _back(ve, ok="Đã lưu — worker dùng giá trị mới ở lượt kế")


def _luu_nguong_hang(request: Request, form: dict[str, str]) -> None:
    """T3 — ghi ngưỡng từng hạng thẻ đi kèm lượt Lưu của mục Ưu đãi.

    Ô để TRỐNG = XOÁ ngưỡng ("chưa điền"): hạng đó ngừng nhận khách mới cho tới
    khi điền lại — KHÔNG hiểu là ngưỡng 0đ, vì 0đ sẽ nuốt sạch khách chưa mua.
    Chỉ ghi hạng nào ĐỔI, để nhật ký không đầy những dòng "sửa" mà chẳng sửa gì.
    """
    from app.db.repositories import audit_repo, voucher_repo
    from app.services import voucher_service

    cu = {h["code"]: h["min_spent"] for h in voucher_service.bac_thang()}
    doi: dict[str, str] = {}
    for ma, truoc in cu.items():
        khoa = f"nguong_{ma}"
        if khoa not in form:
            continue
        tho = form[khoa].strip().replace(".", "").replace(",", "")
        if tho:
            try:
                moi = float(tho)
            except ValueError:
                raise ApiError(f"Ngưỡng hạng {ma} phải là một con số.")
            if moi < 0:
                raise ApiError(f"Ngưỡng hạng {ma} không thể âm.")
        else:
            moi = None
        if (truoc is None) != (moi is None) or (
                moi is not None and float(truoc) != moi):
            voucher_repo.dat_nguong(ma, moi)
            doi[ma] = "(chưa điền)" if moi is None else f"{moi:.0f}"
    if doi:
        audit_repo.ghi(action="sua_nguong_hang_the", object_type="card_rank",
                       user_id=int(_user(request).get("sub") or 0) or None,
                       old_value={k: ("(chưa điền)" if cu[k] is None
                                      else f"{float(cu[k]):.0f}") for k in doi},
                       new_value=doi)


# JS của mục Mốc thời gian. Ô ẩn vẫn giữ nguyên chuỗi "a, b, c" như cũ nên
# phần lưu ở server không phải biết gì về thẻ — thẻ chỉ là cách VẼ chuỗi đó.
# Phép chuẩn hoá ở đây phải khớp `tieng_viet.chuan_hoa` bên Python, nếu không
# thẻ trùng hiện trên màn một kiểu mà máy dò hiểu một kiểu.
_MOC_JS = r"""
(function () {
  var f = document.getElementById('mocForm'); if (!f) return;
  var SP = {'#gia':'tin có số tiền','#anh':'tin có ảnh','#ma':'tin có mã giảm'};
  function kd(s){ return String(s).toLowerCase().normalize('NFD')
      .replace(/[̀-ͯ]/g,'').replace(/đ/g,'d').trim(); }
  function cat(v){ return String(v||'').split(',').map(function(x){return x.trim();}).filter(Boolean); }
  function ghi(box, ds){
    var h = box.querySelector('input[type=hidden]');
    h.value = ds.join(', '); h.dispatchEvent(new Event('input',{bubbles:true})); ve(box);
  }
  function ve(box){
    var ds = cat(box.querySelector('input[type=hidden]').value);
    var add = box.querySelector('.kwadd');
    box.querySelectorAll('.kwtag').forEach(function(e){ e.remove(); });
    var dau = {}, trung = 0;
    ds.forEach(function(t, i){
      var k = kd(t), sp = SP[t.toLowerCase()], la = Object.prototype.hasOwnProperty.call(dau, k);
      if (!la) dau[k] = t; else trung++;
      var el = document.createElement('span');
      el.className = 'kwtag' + (sp ? ' sp' : '') + (la ? ' dup' : '');
      el.title = sp ? ('Cụm đặc biệt — máy tự hiểu: ' + sp)
               : (la ? ('Thừa: máy bỏ dấu rồi nên cụm này y hệt “' + dau[k] + '”')
                     : 'Máy thấy cụm này trong tin là tính đã đi bước');
      var b = document.createElement('b'); b.textContent = sp ? (t + ' · ' + sp) : t;
      el.appendChild(b);
      var x = document.createElement('button');
      x.type='button'; x.className='kwx'; x.dataset.i=i; x.textContent='×'; x.title='Gỡ cụm này';
      el.appendChild(x); box.insertBefore(el, add || null);
    });
    var side = box.parentNode.querySelector('.kwside');
    if (side) {
      side.textContent = ds.length + ' cụm';
      if (trung) {
        var n = document.createElement('button');
        n.type='button'; n.className='kwdup'; n.textContent='gỡ ' + trung + ' thẻ thừa';
        n.title='Gỡ các cụm chỉ khác nhau ở dấu — máy coi chúng là một';
        side.appendChild(n);
      }
    }
  }
  f.querySelectorAll('[data-kw]').forEach(ve);
  f.addEventListener('keydown', function(e){
    var i = e.target; if (!i.classList || !i.classList.contains('kwadd')) return;
    var box = i.closest('[data-kw]');
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();          // Enter trong form = GỬI FORM, phải chặn
      if (i.value.trim() !== '') { var d = cat(box.querySelector('input[type=hidden]').value);
        cat(i.value).forEach(function(t){ d.push(t); }); ghi(box, d); i.value=''; }
    } else if (e.key === 'Backspace' && i.value === '') {
      var d2 = cat(box.querySelector('input[type=hidden]').value);
      if (d2.length) { d2.pop(); ghi(box, d2); }
    }
  });
  f.addEventListener('blur', function(e){        // rời ô mà còn chữ → vẫn nhận
    var i = e.target;
    if (i.classList && i.classList.contains('kwadd') && i.value.trim() !== '') {
      var box = i.closest('[data-kw]'), d = cat(box.querySelector('input[type=hidden]').value);
      cat(i.value).forEach(function(t){ d.push(t); }); ghi(box, d); i.value='';
    }
  }, true);
  f.addEventListener('click', function(e){
    var x = e.target.closest('.kwx');
    if (x) { var box = x.closest('[data-kw]'), d = cat(box.querySelector('input[type=hidden]').value);
      d.splice(parseInt(x.dataset.i,10),1); ghi(box, d); return; }
    var nut = e.target.closest('.kwdup');
    if (nut) { var b2 = nut.closest('.kwrow').querySelector('[data-kw]'), giu=[], thay={};
      cat(b2.querySelector('input[type=hidden]').value).forEach(function(t){
        var k = kd(t); if (!Object.prototype.hasOwnProperty.call(thay,k)) { thay[k]=1; giu.push(t); } });
      ghi(b2, giu); return; }
    var ab = e.target.closest('.aib');
    if (ab) { var w = ab.closest('.aigui');
      w.querySelectorAll('.aib').forEach(function(z){ z.classList.toggle('on', z===ab); });
      w.querySelector('.aiv').value = ab.getAttribute('data-v'); dirty(); return; }
    if (e.target.closest('.keep')) { e.target.closest('.critw').hidden = true; return; }
    if (e.target.closest('.force')) { var it = e.target.closest('.mitem');
      var sw = it.querySelector('.msw'); sw.checked = false; it.classList.add('off');
      e.target.closest('.critw').hidden = true; dirty(); return; }
    var bx = e.target.closest('[data-kw]');
    if (bx) { var a = bx.querySelector('.kwadd'); if (a) a.focus(); }
  });
  // Mốc GẮT: tắt thì hỏi lại tại chỗ (không dùng confirm — dễ bấm nhầm Enter)
  f.addEventListener('change', function(e){
    var t = e.target;
    if (t.classList && t.classList.contains('msw')) {
      var it = t.closest('.mitem');
      if (!t.checked && it.classList.contains('crit')) {
        t.checked = true; it.classList.remove('off');
        var w = it.querySelector('.critw'); if (w) w.hidden = false; return;
      }
      it.classList.toggle('off', !t.checked);
    }
    dirty();
  });
  f.addEventListener('input', dirty);
  var d = f.querySelector('.dirty'), cham = false;
  function dirty(){ if (cham || !d) return; cham = true;
    d.textContent = 'Có thay đổi chưa lưu — bấm Lưu để áp ngay.'; d.classList.add('on'); }

  /* 🧪 Thử một câu — gửi từ khoá ĐANG TRÊN MÀN lên máy chủ chấm */
  var go = document.getElementById('kwtGo'), cau = document.getElementById('kwtCau'),
      ckAnh = document.getElementById('kwtAnh'), kq = document.getElementById('kwtKq');
  if (!go || !cau) return;
  function esc(s){ var x = document.createElement('span'); x.textContent = s; return x.innerHTML; }
  function hien(h){ kq.hidden = false; kq.innerHTML = h; }
  function thu(){
    var r = f.querySelector('input[name=kwtAi]:checked'), ai = r ? r.value : 'nv';
    var fd = new FormData(); fd.append('cau', cau.value); fd.append('ai', ai);
    if (ai === 'nv' && ckAnh.checked) fd.append('anh', '1');
    f.querySelectorAll('.mitem').forEach(function(it){
      var nm = it.querySelector('.mname'); if (!nm) return;
      var m = /(\d+)/.exec(nm.textContent || ''); if (!m) return;
      var oNv = it.querySelector('.kwrow:not(.kh) [data-kw] input[type=hidden]');
      var oKh = it.querySelector('.kwrow.kh [data-kw] input[type=hidden]');
      if (oNv) fd.append('kw[' + m[1] + ']', oNv.value);
      if (oKh) fd.append('kwkh[' + m[1] + ']', oKh.value);
    });
    go.disabled = true; hien('Đang chấm…');
    fetch('/quan-tri/cai-dat/thu-cau', {method:'POST', body:fd, credentials:'same-origin'})
      .then(function(r){ return r.json(); })
      .then(function(j){
        go.disabled = false;
        var kh = j.ai === 'kh';
        if (!j.khop || !j.khop.length) {
          hien(kh
            ? '<span class="no">Không cụm nào khớp.</span> Câu khách này <b>không làm nhảy cóc</b> — con trỏ đứng yên.'
            : '<span class="no">Máy KHÔNG nhận ra bước nào.</span> Câu này vẫn được tính <b>1 bước</b> theo luật dự phòng (mỗi lượt nhắn = 1 bước) — nhưng máy không biết là bước nào.');
          return;
        }
        var h = j.khop.map(function(k){
          return '<div style="margin-top:4px">' + (kh ? '🐸' : '✅') + ' <b>'
            + (kh ? 'Nhảy tới bước ' : 'Bước ') + k.buoc + '</b>'
            + (k.ten ? ' · ' + esc(k.ten) : '') + ' — bắt bởi: '
            + k.cum.map(function(c){ return '<span class="hit">' + esc(c) + '</span>'; }).join('')
            + '</div>'; }).join('');
        if (kh) h += '<div style="margin-top:6px;color:var(--sub)">Chỉ nhảy khi khách đang đứng <b>trong ' + j.nhay + ' bước</b> trước đích. Xa hơn thì máy <b>đứng yên</b>.</div>';
        else if (j.khop.length > 1) h += '<div style="margin-top:6px;color:var(--sub)">Khớp ' + j.khop.length + ' bước — máy lấy bước <b>CAO NHẤT</b>, nhưng không nhảy quá <b>' + j.cua_so + ' bước</b>.</div>';
        hien(h);
      })
      .catch(function(){ go.disabled = false; hien('<span class="no">Không gọi được máy chủ.</span>'); });
  }
  go.addEventListener('click', thu);
  cau.addEventListener('keydown', function(e){ if (e.key === 'Enter') { e.preventDefault(); thu(); } });
  f.addEventListener('change', function(e){
    if (!e.target || e.target.name !== 'kwtAi') return;
    var w = document.getElementById('kwtAnhWrap');
    if (w) w.style.display = (e.target.value === 'kh') ? 'none' : '';
    cau.placeholder = (e.target.value === 'kh')
      ? 'vd: sao đắt thế em ơi' : 'vd: dạ bên em gửi chị bảng giá ạ';
  });
})();
"""


async def _luu_moc(request: Request, form: dict[str, str]):
    """Lưu mục "Mốc thời gian" — bốn khối trong MỘT form.

    Form gửi khoá dạng `b[3][ten]` / `m[12][nhan]` (giữ đúng nếp mẫu) nên phải
    tự bóc; `bn_*`/`bw_*` là khoá tự do; còn lại là cài đặt trong danh mục.
    Bốn khối chung một nút Lưu vì chúng là MỘT quyết định nghiệp vụ — tách nút
    thì admin sửa bước xong quên lưu mốc, thang và bảng lệch nhau ngay.
    """
    import re as _re

    from app.core import runtime_config
    from app.db.repositories import cskh_repo
    from app.services import sale_service

    ve = "/quan-tri/cai-dat?sec=moc"
    actor = _user(request)
    uid = int(actor.get("sub") or 0) or None

    # --- gom theo chỉ số: b[<n>][<truong>] và m[<id>][<truong>] ---
    buoc: dict[int, dict[str, str]] = {}
    moc: dict[int, dict[str, str]] = {}
    for k, v in form.items():
        if (m := _re.fullmatch(r"b\[(\d+)]\[(\w+)]", k)):
            buoc.setdefault(int(m[1]), {})[m[2]] = v
        elif (m := _re.fullmatch(r"m\[(\d+)]\[(\w+)]", k)):
            moc.setdefault(int(m[1]), {})[m[2]] = v

    try:
        # 1A — bước thang. Ô tích VẮNG MẶT nghĩa là TẮT (trình duyệt không gửi
        # checkbox chưa tick), nên phải xét theo danh sách bước có trong form.
        for so, f in sorted(buoc.items()):
            sale_service.luu_buoc(
                so, name=f.get("ten", ""), work=f.get("viec", ""),
                kw_nv=f.get("tu_khoa", ""), kw_kh=f.get("tu_khoa_kh", ""),
                bat="active" in f)
        # 1D — mốc chăm
        for mid, f in moc.items():
            cskh_repo.sua_moc(
                mid,
                offset_days=_to_int(f.get("offset_days", "")),
                label=f.get("nhan", ""),
                sender=f.get("ai_gui") if f.get("ai_gui") in ("may", "nguoi")
                else None,
                active="active" in f)
        # 1G/1H — tên cột + câu việc 📌 (khoá tự do, trống = xoá về mặc định)
        for k, v in form.items():
            if k.startswith(("bn_", "bw_")):
                runtime_config.dat_tu_do(k, v, uid)
        # 11 con số của thang (T2) — vẫn đi đường cài đặt có danh mục
        du_lieu = {c: v for c, v in form.items() if c in runtime_config.THEO_MA}
        for c, muc in runtime_config.THEO_MA.items():
            if muc.nhom == "sale" and muc.kieu == "bool":
                du_lieu[c] = c in form          # vắng mặt = tắt
        if du_lieu:
            cai_dat_service.dat_nhieu(du_lieu, actor=actor)
    except ApiError as err:
        return _back(ve, error=err.message)
    except (ValueError, KeyError) as err:
        return _back(ve, error=f"Dữ liệu không hợp lệ: {err}")

    audit_repo.ghi(action="setting_update", object_type="app_settings",
                   user_id=uid,
                   new_value={"muc": "moc", "buoc": len(buoc), "moc": len(moc)},
                   reason="Sửa mục Mốc thời gian")
    return _back(ve, ok="Đã lưu mục Mốc thời gian.")


@router.post("/cai-dat/thu-cau")
async def cai_dat_thu_cau(request: Request):
    """🧪 Ô "Thử một câu" của 1A — chấm trên TỪ KHOÁ ĐANG GÕ, KHÔNG ghi gì.

    Trả JSON cho JS trên màn. Gọi thẳng hàm bộ dò thật dùng nên kết quả ô thử
    không bao giờ lệch với lúc chạy thật."""
    from app.services import sale_service

    if (chan := _chan(request)):
        return chan
    import re as _re

    f = await _form(request)
    kw_nv: dict[int, str] = {}
    kw_kh: dict[int, str] = {}
    for k, v in f.items():
        if (m := _re.fullmatch(r"kw\[(\d+)]", k)):
            kw_nv[int(m[1])] = v
        elif (m := _re.fullmatch(r"kwkh\[(\d+)]", k)):
            kw_kh[int(m[1])] = v
    kq = sale_service.thu_mot_cau(
        f.get("cau", ""), ai="kh" if f.get("ai") == "kh" else "nv",
        co_anh=f.get("anh") == "1", kw_nv=kw_nv, kw_kh=kw_kh)
    return JSONResponse({"ok": True, **kq})


@router.post("/cai-dat/nhan-dien")
async def cai_dat_nhan_dien(request: Request):
    """Đ2 — thêm/bật-tắt/xoá một mẫu câu nhận diện.

    Một form cho cả bốn khối: nút mang theo `viec=them|doi:<id>|xoa:<id>` nên
    không phải đẻ bốn đường riêng cho cùng một việc.
    """
    from app.db.repositories import nhan_dien_repo
    from app.services import nhan_dien

    if (chan := _chan(request)):
        return chan
    ve = "/quan-tri/cai-dat?sec=nhan_dien"
    f = await _form(request)
    viec = f.get("viec", "")
    uid = int(_user(request).get("sub") or 0) or None
    try:
        if viec == "them":
            loai = f.get("loai", "")
            if loai not in nhan_dien_repo.LOAI:
                raise ApiError("VALIDATION_ERROR", f"Loại mẫu lạ: {loai!r}")
            mau = (f.get("mau") or "").strip()
            if not mau:
                raise ApiError("VALIDATION_ERROR", "Chưa nhập mẫu câu.")
            thay = (f.get("thay_the") or "").strip() or None
            if loai == "viet_tat" and not thay:
                raise ApiError("VALIDATION_ERROR",
                               "Bảng viết tắt cần cả chữ đầy đủ để bung ra.")
            nhan_dien.kiem_mau(loai, mau)
            nhan_dien_repo.them(loai, mau, thay if loai == "viet_tat" else None,
                                uid)
            tin = f"Đã thêm mẫu «{mau}»."
        elif viec.startswith(("doi:", "xoa:")):
            pid = int(viec.split(":", 1)[1])
            if viec.startswith("doi:"):
                dong = nhan_dien_repo.doi_trang_thai(pid)
                tin = ("Đã bật lại mẫu." if dong and dong["status"] == "active"
                       else "Đã tắt tạm mẫu.")
            else:
                nhan_dien_repo.xoa(pid)
                tin = "Đã xoá mẫu."
        else:
            return _back(ve, error="Không rõ thao tác.")
    except ApiError as err:
        return _back(ve, error=err.message)
    except ValueError:
        return _back(ve, error="Dữ liệu không hợp lệ.")
    nhan_dien.xoa_cache()          # bộ dò thấy ngay, khỏi chờ hết 10 giây cache
    audit_repo.ghi(action="setting_update", object_type="phrase_patterns",
                   user_id=uid, new_value={"viec": viec},
                   reason="Sửa mẫu câu nhận diện")
    return _back(ve, ok=tin)


@router.post("/cai-dat/nhan-dien/thu")
async def cai_dat_nhan_dien_thu(request: Request):
    """🧪 Thử một câu — chấm bằng ĐÚNG bộ dò thật, nên kết quả ô thử không bao
    giờ lệch với lúc chạy thật."""
    from app.services import nhan_dien

    if (chan := _chan(request)):
        return chan
    f = await _form(request)
    try:
        gia = float(f.get("menh_gia") or 0) or None
    except ValueError:
        gia = None
    return JSONResponse({"ok": True,
                         **nhan_dien.soi(f.get("cau", ""),
                                         ma=(f.get("ma") or "").strip(),
                                         menh_gia=gia)})


@router.post("/cai-dat/goi-y")
async def cai_dat_goi_y(request: Request):
    """Đ2 — CRUD luật gợi ý kịch bản (từ khoá khách nói → kịch bản)."""
    from app.db.repositories import giam_sat_repo

    if (chan := _chan(request)):
        return chan
    ve = "/quan-tri/cai-dat?sec=goi_y"
    f = await _form(request)
    viec = f.get("viec", "")
    try:
        if viec == "them":
            kw = (f.get("tu_khoa") or "").strip()
            sid = int(f.get("script_id") or 0)
            if not kw:
                return _back(ve, error="Chưa nhập từ khoá.")
            if not sid:
                return _back(ve, error="Chưa chọn kịch bản để gợi ý.")
            giam_sat_repo.luu_luat_goi_y(kw, sid)
            tin = f"Đã thêm luật «{kw}»."
        elif viec.startswith("doi:"):
            dong = giam_sat_repo.doi_trang_thai_luat_goi_y(
                int(viec.split(":", 1)[1]))
            tin = ("Đã bật lại luật." if dong and dong["status"] == "active"
                   else "Đã tắt tạm luật.")
        elif viec.startswith("xoa:"):
            giam_sat_repo.xoa_luat_goi_y(int(viec.split(":", 1)[1]))
            tin = "Đã xoá luật."
        else:
            return _back(ve, error="Không rõ thao tác.")
    except ApiError as err:
        return _back(ve, error=err.message)
    except ValueError:
        return _back(ve, error="Dữ liệu không hợp lệ.")
    audit_repo.ghi(action="setting_update", object_type="script_suggest_rules",
                   user_id=int(_user(request).get("sub") or 0) or None,
                   new_value={"viec": viec}, reason="Sửa luật gợi ý kịch bản")
    return _back(ve, ok=tin)


# JS của mục Kịch bản nhận diện — chỉ ô 🧪 Thử một câu. Gọi JSON tại chỗ thay vì
# nạp lại trang như mẫu: lúc đang chỉnh mẫu, người ta thử liên tiếp cả chục câu.
_ND_JS = r"""
(function(){
  var nut = document.getElementById('ndThu');
  if (!nut) return;
  var cau = document.getElementById('ndCau'),
      ma  = document.getElementById('ndMa'),
      gia = document.getElementById('ndGia'),
      kq  = document.getElementById('ndKq');
  function thu(){
    var d = new FormData();
    d.append('cau', cau.value);
    d.append('ma', ma.value);
    d.append('menh_gia', gia.value);
    kq.innerHTML = '<i class="note">Đang chấm…</i>';
    fetch('/quan-tri/cai-dat/nhan-dien/thu', {method:'POST', body:d,
      headers:{'X-Requested-With':'fetch'}})
      .then(function(r){ return r.json(); })
      .then(function(j){
        var lop = j.goi ? 'goi' : (j.voucher ? 'vc' : (j.chan ? 'chan' : ''));
        kq.innerHTML = '<span class="ndtag ' + lop + '">' + j.nhan + '</span>'
                     + '<span class="ndwhy"></span>';
        kq.querySelector('.ndwhy').textContent = j.vi_sao;
      })
      .catch(function(){ kq.innerHTML = '<i class="note">Không chấm được.</i>'; });
  }
  nut.addEventListener('click', thu);
  cau.addEventListener('keydown', function(e){
    if (e.key === 'Enter'){ e.preventDefault(); thu(); }
  });
})();
"""


# ------------------------------------------------------ Đ3 · luồng tự động
@router.get("/luong-tu-dong", response_class=HTMLResponse)
async def luong_tu_dong(request: Request, ok: str = "", error: str = ""):
    """Màn khai + SOI luật tự động. CHƯA gửi tin — xem services/auto_flow."""
    from app.db.repositories import auto_flow_repo
    from app.services import auto_flow
    from app.web.views import luong_tu_dong as v_af

    if (chan := _chan(request)):
        return chan
    flows = auto_flow_repo.tat_ca()
    return HTMLResponse(_shell_af(
        v_af.render(flows, None, auto_flow.khong_gui_duoc(),
                    lich_su=_lich_su_af(flows)),
        ok, error))


def _lich_su_af(flows) -> dict[int, str]:
    """Lịch sử chạy thử + việc đã sinh, cho từng luồng."""
    from app.db.repositories import auto_flow_repo
    from app.web.views import luong_tu_dong as v_af

    ra = {}
    for f in flows:
        fid = int(f["id"])
        ra[fid] = v_af._lich_su(auto_flow_repo.lan_chay(fid, 5),
                                auto_flow_repo.viec_cua_luong(fid, 10))
    return ra


def _shell_af(body: str, ok: str, error: str) -> str:
    from app.web.views.admin import _shell

    return _shell("Luồng tự động", "cai-dat", body, ok, error,
                  sub="Khai luật máy tự chạy — Đợt 3 mới dựng khung, CHƯA gửi tin")


@router.post("/luong-tu-dong")
async def luong_tu_dong_luu(request: Request):
    """Thêm/bật-tắt/xoá/CHẠY THỬ một luồng.

    "Chạy thử" ở đây là chạy KHÔ: đếm khách trúng luật và nêu lý do. Mẫu Kallet
    có thêm nút "Test bắn" gửi thật một tin — CỐ Ý không port: nút đó tự nhận là
    "vượt mọi lớp chặn lẫn công tắc", đúng thứ không nên tồn tại khi đường gửi
    tự động còn chưa được kiểm chứng.
    """
    from app.db.repositories import auto_flow_repo
    from app.services import auto_flow
    from app.web.views import luong_tu_dong as v_af

    if (chan := _chan(request)):
        return chan
    ve = "/quan-tri/luong-tu-dong"
    f = await _form(request)
    viec = f.get("viec", "")
    uid = int(_user(request).get("sub") or 0) or None
    kq = kq_viec = None
    try:
        if viec.startswith("viec:"):
            flow = auto_flow_repo.get(int(viec.split(":", 1)[1]))
            if not flow:
                return _back(ve, error="Không tìm thấy luồng.")
            if not flow["tao_viec"]:
                return _back(ve, error="Luồng này không bật «sinh việc cho "
                                       "nhân viên» — sửa luồng rồi thử lại.")
            kq_viec = auto_flow.sinh_viec(dict(flow), boi=uid)
            tin = (f'Đã đặt {kq_viec["da_sinh"]} việc cho nhân viên — '
                   "0 tin gửi đi.")
        elif viec.startswith("sua:"):
            fid = int(viec.split(":", 1)[1])
            ds_ma = [m for m in (await request.form()).getlist("s_dk_ma")
                     if m in auto_flow.DIEU_KIEN]
            gt = (f.get("s_dk_gia_tri") or "").strip()
            moi = auto_flow_repo.luu(
                fid, name=(f.get("s_name") or "").strip() or None,
                moc_neo=f.get("s_moc_neo"),
                so_ngay=_to_int(f.get("s_so_ngay", "")),
                khop=f.get("s_khop"),
                dieu_kien=[{"ma": m,
                            "phep": ">=" if auto_flow.DIEU_KIEN[m]["kieu"] == "num"
                            else "=", "gia_tri": gt} for m in ds_ma],
                tao_viec=f.get("s_tao_viec") == "1")
            auto_flow.dung_loc(dict(moi))     # luật sai lộ ra NGAY lúc lưu
            tin = f'Đã sửa luồng «{moi["name"]}».'
        elif viec == "them":
            ds_ma = [m for m in (await request.form()).getlist("dk_ma")
                     if m in auto_flow.DIEU_KIEN]
            gt = (f.get("dk_gia_tri") or "").strip()
            dieu_kien = [{"ma": m,
                          "phep": ">=" if auto_flow.DIEU_KIEN[m]["kieu"] == "num"
                          else "=",
                          "gia_tri": gt} for m in ds_ma]
            moi = auto_flow_repo.luu(
                None, name=(f.get("name") or "").strip(),
                kind=f.get("kind"), status="inactive",
                su_kien=f.get("su_kien"), moc_neo=f.get("moc_neo"),
                so_ngay=_to_int(f.get("so_ngay", "")),
                truong=f.get("truong"),
                truong_gia_tri=(f.get("truong_gia_tri") or "").strip(),
                khop=f.get("khop"), dieu_kien=dieu_kien,
                tao_viec=f.get("tao_viec") == "1", created_by=uid)
            # Dựng thử câu lọc NGAY để luật sai lộ ra lúc lưu, không phải lúc
            # chạy — luồng khai sai mà nằm im trong bảng là thứ khó tìm nhất.
            auto_flow.dung_loc(dict(moi))
            tin = f'Đã lưu luồng «{moi["name"]}» ở trạng thái TẮT.'
        elif viec.startswith("thu:"):
            flow = auto_flow_repo.get(int(viec.split(":", 1)[1]))
            if not flow:
                return _back(ve, error="Không tìm thấy luồng.")
            kq = auto_flow.chay_kho(dict(flow), boi=uid)
            tin = f'Chạy thử xong — {kq["so_trung"]} khách trúng luật, 0 tin gửi đi.'
        elif viec.startswith("doi:"):
            dong = auto_flow_repo.doi_trang_thai(int(viec.split(":", 1)[1]))
            tin = ("Đã bật luồng (vẫn CHƯA gửi tin — engine không có mã gửi)."
                   if dong and dong["status"] == "active" else "Đã tắt luồng.")
        elif viec.startswith("xoa:"):
            auto_flow_repo.xoa(int(viec.split(":", 1)[1]))
            tin = "Đã xoá luồng."
        else:
            return _back(ve, error="Không rõ thao tác.")
    except ApiError as err:
        return _back(ve, error=err.message)
    except ValueError:
        return _back(ve, error="Dữ liệu không hợp lệ.")
    audit_repo.ghi(action="setting_update", object_type="auto_flows",
                   user_id=uid, new_value={"viec": viec},
                   reason="Sửa luồng tự động")
    if kq is not None or kq_viec is not None:
        # Kết quả chạy thử / sinh việc phải hiện NGAY trên màn, không nhét vào
        # query string rồi mất — dựng lại trang tại chỗ thay vì chuyển hướng.
        flows = auto_flow_repo.tat_ca()
        return HTMLResponse(_shell_af(
            v_af.render(flows, kq, auto_flow.khong_gui_duoc(),
                        kq_viec=kq_viec, lich_su=_lich_su_af(flows)),
            tin, ""))
    return _back(ve, ok=tin)


# ------------------------------------------------ thẻ Pancake (màn kho tên thẻ)
@router.get("/the-pancake", response_class=HTMLResponse)
async def the_pancake_page(request: Request, ok: str = "", error: str = ""):
    """Kho tên/màu thẻ Pancake: xem đang có gì, hỏi API lần cuối lúc nào.

    Chỉ ĐỌC kho + danh sách page (đã cache) — mở màn này không sinh lời gọi lấy
    thẻ nào. Muốn làm tươi phải bấm nút, xem POST bên dưới.
    """
    if (chan := _chan(request)):
        return chan
    import asyncio

    from app.db.repositories import tag_store
    from app.integrations.pancake.client import (
        TAG_SYNC_MOI, PancakeError, list_pages,
    )

    try:
        pages = await list_pages()
    except (PancakeError, Exception) as exc:  # noqa: BLE001 — vẫn vẽ được kho
        pages, error = [], error or f"Không lấy được danh sách page: {exc}"
    the = await asyncio.to_thread(tag_store.load_all_tags)
    moc = await asyncio.to_thread(tag_store.doc_moc)
    # Page đã có thẻ trong kho mà Pancake không liệt kê nữa (page bị gỡ quyền)
    # vẫn phải hiện, không thì thẻ của nó biến mất khỏi màn mà không ai biết.
    da_co = {str(p.get("id")) for p in pages}
    pages = list(pages) + [{"id": pid, "name": f"(page không còn trong danh sách)",
                            "role": ""}
                           for pid in sorted(set(the) - da_co)]
    return HTMLResponse(render_the_pancake(
        pages, the, moc, moi_giay=TAG_SYNC_MOI, ok=ok, error=error))


@router.post("/the-pancake/cap-nhat")
async def the_pancake_cap_nhat(request: Request):
    """Bấm tay: hỏi lại thẻ của MỌI page ngay, bỏ qua lịch 1 ngày/lần.

    Mỗi page tốn 1 lời gọi `pages/{id}/settings`, nên đây là hành động có giá —
    để người dùng chủ động bấm chứ không tự chạy.
    """
    if (chan := _chan(request)):
        return chan
    from app.integrations.pancake.client import PancakeError, refresh_tags_all_pages

    try:
        ket_qua = await refresh_tags_all_pages(ep=True)
    except (PancakeError, Exception) as exc:  # noqa: BLE001
        return _back("/quan-tri/the-pancake",
                     error=f"Cập nhật thẻ hỏng: {exc}")
    tong = sum(ket_qua.values())
    if not tong:
        return _back("/quan-tri/the-pancake",
                     error="Không lấy được thẻ nào — xem cột lỗi từng page.")
    return _back("/quan-tri/the-pancake",
                 ok=f"Đã cập nhật {tong} thẻ của {len(ket_qua)} page.")
