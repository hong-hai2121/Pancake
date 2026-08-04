"""Màn C4 — Thư viện kịch bản · Kho data · Giám sát (soi tin).

Port từ mẫu Kallet: kich-ban.php · kho-data.php · lich-su.php.

Điểm giao diện KHÔNG được bỏ:

  * Màn Thư viện phải nói to là **chép tay, không gửi gì** — nếu không sẽ có
    người bấm "chép" rồi hoảng vì tưởng tin đã bay tới khách.
  * Màn Giám sát phải hiện **lý do máy bác** ngay trên dòng. Bác công của
    người ta mà không nói vì sao là nguồn gốc mọi cuộc cãi vã.
"""

from html import escape
from urllib.parse import quote

from app.services import giam_sat_service as svc
from app.web.shell import _icon, render_shell


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _dt(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tabs(active: str, muc: list[tuple[str, str, str]]) -> str:
    return ('<div class="tabs">' + "".join(
        f'<a class="tab{" on" if ma == active else ""}" href="{escape(href)}">'
        f"{escape(nhan)}</a>" for ma, nhan, href in muc) + "</div>")


# ------------------------------------------------------- Thư viện kịch bản
_LOAI_NHAN = {"sale": "🎯 Sale", "sau_ban": "💗 Sau bán"}


def render_kich_ban(rows: list[dict], tong: int, *, loc: dict,
                    tinh_huong: list[str], goi_y: list[dict] | None = None,
                    da_chep: str = "", flash: str = "",
                    loi: str = "") -> str:
    o_th = ('<option value="">Tất cả tình huống</option>'
            + "".join(f'<option value="{escape(t)}"'
                      f'{" selected" if loc.get("tinh_huong") == t else ""}>'
                      f"{escape(t)}</option>" for t in tinh_huong))
    than = ""
    for r in rows:
        than += (
            '<div class="kb-card">'
            f'<div class="kb-h"><span class="kb-loai">'
            f'{escape(_LOAI_NHAN.get(r["kind"], r["kind"]))}</span>'
            f'<b>{_e(r["title"])}</b>'
            + (f'<span class="kb-th">{_e(r["situation"])}</span>'
               if r["situation"] else "")
            + f'<span class="kh-sp"></span>'
              f'<span class="kh-nho">đã chép {_so(r["use_count"])} lần</span>'
              "</div>"
            f'<div class="kb-body">{escape(r["body"] or "")}</div>'
            f'<div class="kb-f">'
            + (f'<span class="kh-nho">{_e(r["tags"])}</span>' if r["tags"] else "")
            + f'<span class="kh-sp"></span>'
              f'<form method="post" action="/crm/kich-ban/{r["id"]}/chep" '
              'class="vc-inline"><button class="kh-btn" type="submit">'
              "📋 Chép câu này</button></form></div>"
            "</div>")
    than = than or ('<p class="note" style="padding:24px;text-align:center">'
                    "Không có kịch bản nào khớp. Thử bỏ bớt điều kiện lọc.</p>")

    khoi_goi_y = ""
    if goi_y is not None:
        muc = "".join(
            f'<div class="gy-item"><b>{_e(g["title"])}</b>'
            f'<span class="kh-nho"> — {_e(g["vi_sao"])}</span>'
            f'<div class="kb-body">{escape(g["body"] or "")}</div></div>'
            for g in goi_y) or (
            '<p class="note">Không dò được từ khoá nào trong đoạn vừa dán. '
            "Thêm luật gợi ý ở dưới.</p>")
        khoi_goi_y = ('<div class="kh-card" style="padding:14px 16px;'
                      'margin-bottom:14px"><div class="ht-h">💡 Gợi ý cho tin '
                      f"vừa dán</div>{muc}</div>")

    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + (f'<div class="flash ok">📋 Đã chép vào bộ nhớ tạm:<br>'
           f'<code class="mt-body">{escape(da_chep)}</code></div>'
           if da_chep else "")
        + '<div class="flash warn">📚 Đây là <b>THƯ VIỆN để chép tay</b> — mở '
          "hay bấm “Chép câu này” <b>không gửi gì cho khách</b>. Muốn máy bắn "
          'tin thì sang <a href="/crm/chien-dich">Chiến dịch</a>.</div>'
        + '<form class="kh-filters" method="get" action="/crm/kich-ban">'
          f'<label class="kh-find">{_icon("search")}'
          f'<input name="q" value="{escape(loc.get("q") or "")}" '
          'placeholder="Tìm câu mẫu — gõ có dấu hay không dấu đều được…">'
          "</label>"
          '<select name="kind" onchange="this.form.requestSubmit()">'
          '<option value="">Sale &amp; Sau bán</option>'
          + f'<option value="sale"{" selected" if loc.get("kind") == "sale" else ""}>'
            "🎯 Sale</option>"
          + f'<option value="sau_ban"'
            f'{" selected" if loc.get("kind") == "sau_ban" else ""}>'
            "💗 Sau bán</option></select>"
          f'<select name="tinh_huong" onchange="this.form.requestSubmit()">'
          f"{o_th}</select>"
          '<button class="kh-btn go">🔍 Tìm</button>'
          '<span class="kh-sp"></span>'
          f'<span class="cnt">{_so(tong)} câu mẫu</span>'
          "</form>"
        + '<form class="kh-filters" method="post" action="/crm/kich-ban/goi-y" '
          'style="margin-bottom:14px">'
          '<input name="tin" style="flex:1 1 320px;height:34px;border:1px solid '
          'var(--border);border-radius:9px;padding:0 10px;font:inherit;'
          'background:var(--card);color:var(--text)" '
          'placeholder="Dán tin của khách vào đây để máy gợi ý 3 câu…">'
          '<button class="kh-btn" type="submit">💡 Gợi ý</button>'
          "</form>"
        + khoi_goi_y
        + f'<div class="kb-list">{than}</div>'
        + '<details class="kh-card" style="padding:14px 16px;margin-top:14px">'
          "<summary style=\"font-weight:700;cursor:pointer\">➕ Thêm câu mẫu"
          "</summary>"
          '<form method="post" action="/crm/kich-ban" class="vc-form-r" '
          'style="margin-top:12px">'
          '<label>Loại<select name="kind">'
          '<option value="sale">🎯 Sale</option>'
          '<option value="sau_ban">💗 Sau bán</option></select></label>'
          '<label>Tình huống<input name="situation" '
          'placeholder="vd Khách chê đắt"></label>'
          '<label style="flex:2 1 200px">Tiêu đề<input name="title" '
          'placeholder="vd Trả lời khách chê đắt"></label>'
          '<label style="flex:1 1 160px">Thẻ (cách nhau dấu phẩy)'
          '<input name="tags" placeholder="gia,phan-doi"></label>'
          '<label style="flex:3 1 100%">Nội dung'
          '<textarea name="body" rows="3" required></textarea></label>'
          '<button class="kh-btn go" type="submit">Lưu câu mẫu</button>'
          "</form></details>"
    )
    return render_shell(
        "Thư viện kịch bản", "crm-scripts", body,
        heading="Thư viện kịch bản",
        sub="Câu mẫu để CHÉP TAY · tìm được cả khi gõ không dấu",
    )


# ------------------------------------------------------------------ Kho data
def render_kho_data(data: dict, *, nhan_vien: list[dict],
                    flash: str = "", loi: str = "") -> str:
    chua_chia = "".join(
        "<tr>"
        f'<td><a class="kh-name" href="/crm/khach-hang/{r["id"]}">'
        f'{_e(r["full_name"])}</a>'
        f'<div class="kh-sub">{_e(r["primary_phone"])}</div></td>'
        f'<td>{_e(r["source"])}</td>'
        f'<td class="num">{_so(r["so_don"])}</td>'
        f'<td class="kh-nho">{_dt(r["created_at"])}</td>'
        f'<td><form method="post" action="/crm/kho-data/chia" '
        'class="vc-inline">'
        f'<input type="hidden" name="customer_id" value="{r["id"]}">'
        '<select name="user_id">'
        + "".join(f'<option value="{u["id"]}">{escape(u["name"] or "")}'
                  "</option>" for u in nhan_vien)
        + '</select><button class="kh-btn go" type="submit">Chia</button>'
          "</form></td></tr>" for r in data["chua_chia"]) or (
        '<tr><td colspan="5" class="rong">Mọi khách đều đã có người phụ trách.'
        "</td></tr>")

    ket = "".join(
        "<tr>"
        f'<td><a class="kh-name" href="/crm/khach-hang/{r["id"]}">'
        f'{_e(r["full_name"])}</a></td>'
        f'<td class="num">{_so(r["so_khoa"])}</td>'
        f'<td class="kh-nho">{r["khoa_den"].strftime("%d/%m/%Y") if r["khoa_den"] else "—"}</td>'
        "</tr>" for r in data["ket"]) or (
        '<tr><td colspan="3" class="rong">Không có khách nào bị kẹt.</td></tr>')

    chia_log = "".join(
        "<tr>"
        f'<td class="kh-nho">{_dt(r["created_at"])}</td>'
        f'<td>{_e(r["customer_name"])}</td>'
        f'<td>{_e(r["from_name"])} → {_e(r["to_name"])}</td>'
        f'<td>{_e(r["action"])}{" 🤖" if r["by_machine"] else ""}</td>'
        f'<td class="kh-nho">{_e(r["reason"])}</td>'
        "</tr>" for r in data["nhat_ky_chia"]) or (
        '<tr><td colspan="5" class="rong">Chưa có lượt chia nào.</td></tr>')

    gop_log = "".join(
        "<tr>"
        f'<td class="kh-nho">{_dt(r["created_at"])}</td>'
        f'<td>{_e(r["merged_name"])} → {_e(r["primary_name"])}</td>'
        f'<td>{_e(r["by_name"])}</td>'
        f'<td>{"đã tách lại" if r["undone"] else "còn gộp"}</td>'
        "</tr>" for r in data["nhat_ky_gop"]) or (
        '<tr><td colspan="4" class="rong">Chưa gộp hồ sơ nào.</td></tr>')

    xuat_log = "".join(
        "<tr>"
        f'<td class="kh-nho">{_dt(r["created_at"])}</td>'
        f'<td>{_e(r["user_name"])}</td>'
        f'<td>{_e(r["scope"])}</td>'
        f'<td class="num">{_so(r["row_count"])}</td>'
        "</tr>" for r in data["nhat_ky_xuat"]) or (
        '<tr><td colspan="4" class="rong">Chưa ai xuất dữ liệu.</td></tr>')

    def _bang(tieu_de: str, cot: list[str], than: str, ghi: str = "") -> str:
        return ('<div class="kh-card" style="padding:14px 16px;margin-top:14px">'
                f'<div class="ht-h">{escape(tieu_de)}</div>'
                '<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
                + "".join(f"<th>{escape(c)}</th>" for c in cot)
                + f"</tr></thead><tbody>{than}</tbody></table></div>"
                + (f'<p class="note">{ghi}</p>' if ghi else "") + "</div>")

    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<div class="vc-tiles">'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#C25E00">'
          f'</span><div class="vc-num" style="color:#C25E00">'
          f'{_so(data["so_chua_chia"])}</div>'
          '<div class="vc-lbl">Khách chưa có người phụ trách</div>'
          '<div class="vc-sub">không lên bảng việc, không chạy đồng hồ</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#E5484D">'
          f'</span><div class="vc-num" style="color:#E5484D">'
          f'{_so(data["so_ket"])}</div>'
          '<div class="vc-lbl">Khách KẸT không chia được</div>'
          '<div class="vc-sub">mọi người đều đang bị khoá</div></div>'
        + "</div>"
        + _bang("Khách chưa có người phụ trách",
                ["Khách", "Nguồn", "Đơn", "Vào lúc", "Chia cho"], chua_chia,
                "Nhóm này CỐ Ý không lên bảng việc và không chạy đồng hồ SLA — "
                "chưa giao cho ai thì không thể tính là ai đó chậm.")
        + _bang("Khách kẹt không chia được",
                ["Khách", "Số người đang khoá", "Khoá tới"], ket,
                "Khách vừa bị thu hồi thì bị khoá không chia lại cho chính "
                "người đó. Kẹt = mọi nhân viên đều đang khoá.")
        + _bang("Nhật ký chia / thu hồi",
                ["Lúc", "Khách", "Từ → tới", "Hành động", "Lý do"], chia_log,
                "Thu hồi BẮT BUỘC có lý do — mất khách là chuyện lớn với nhân "
                "viên, không được thu hồi im lặng.")
        + _bang("Nhật ký gộp hồ sơ",
                ["Lúc", "Gộp", "Bởi", "Tình trạng"], gop_log,
                "Mỗi lượt gộp giữ nguyên trạng hồ sơ phụ trước khi gộp — có "
                "cái đó mới TÁCH LẠI được khi gộp nhầm.")
        + _bang("Nhật ký xuất dữ liệu",
                ["Lúc", "Người xuất", "Phạm vi", "Số dòng"], xuat_log,
                "Xuất khách hàng ra file là hành vi cần truy vết được.")
    )
    return render_shell(
        "Kho data", "crm-data", body,
        heading="Kho data",
        sub="Khách chưa chia · khách kẹt · nhật ký chia/gộp/xuất",
    )


# ------------------------------------------------------------------ Giám sát
_TT_LOP = {"da_xac_minh": "active", "tu_khai_chua_soi": "chua",
           "bac_bo": "sleep", "dang_xac_minh": "fading"}


def render_giam_sat(rows: list[dict], dem: dict, *, tab: str = "soi-tin",
                    flash: str = "", loi: str = "") -> str:
    than = ""
    for r in rows:
        cho_duyet = r["verify_status"] in ("tu_khai_chua_soi", "bac_bo")
        thao_tac = ""
        if cho_duyet:
            thao_tac = (
                f'<form method="post" action="/crm/giam-sat/{r["id"]}/duyet" '
                'class="vc-inline"><input name="ly_do" required '
                'placeholder="Lý do (bắt buộc)">'
                '<button class="kh-btn go" type="submit" name="ok" value="1">'
                "Vớt</button>"
                '<button class="kh-btn" type="submit" name="ok" value="0">'
                "Bác</button></form>")
        than += (
            "<tr>"
            f'<td class="kh-nho">{_dt(r["action_at"])}</td>'
            f'<td>{_e(r["user_name"])}</td>'
            f'<td><a class="kh-name" href="/crm/khach-hang/{r["customer_id"]}">'
            f'{_e(r["customer_name"])}</a></td>'
            f'<td>{escape(svc.HANH_DONG.get(r["action_kind"], r["action_kind"] or "—"))}</td>'
            f'<td>{escape(svc.NHAN_NGUON.get(r["verify_source"], r["verify_source"]))}</td>'
            f'<td><span class="kh-st {_TT_LOP.get(r["verify_status"], "chua")}">'
            f'{escape(svc.NHAN_TRANG_THAI.get(r["verify_status"], r["verify_status"]))}'
            "</span>"
            + (f'<div class="kh-nho">{_e(r["verify_reason"])}</div>'
               if r["verify_reason"] else "")
            + (f'<div class="kh-nho">bởi {_e(r["verified_by_name"])}</div>'
               if r["verified_by_name"] else "")
            + f'</td><td><div class="ds-acts">{thao_tac}</div></td>'
            "</tr>")
    than = than or ('<tr><td colspan="7" class="rong">Không có bản ghi công '
                    "nào trong rổ này.</td></tr>")
    chip = "".join(
        f'<a class="ds-chip{" on" if tab == ma else ""}" '
        f'href="/crm/giam-sat?tt={quote(ma)}">{escape(nhan)} '
        f"<b>{_so(dem.get(khoa, 0))}</b></a>"
        for ma, nhan, khoa in [
            ("", "Tất cả", "tong"),
            ("tu_khai_chua_soi", "Chờ soi", "cho_soi"),
            ("da_xac_minh", "Đã xác minh", "xac_minh"),
            ("bac_bo", "Bị bác", "bac_bo")])
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<div class="flash warn">🔍 Máy soi tin nhắn thật trong <b>cửa ±'
          f"{svc.cua_soi_ngay()} ngày</b> quanh lúc khai (nhân viên hay nhắn "
          "sáng, tối mới tick). Khớp cả ba kiểu gõ: <b>có dấu · bỏ dấu · viết "
          f"tắt</b>. Quá <b>{svc.han_bac_gio()} giờ</b> không thấy tin thì tự "
          "bác — trưởng nhóm vớt tay được, có ghi lý do.</div>"
        + '<div class="vc-tiles">'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#2EAD6E">'
          f'</span><div class="vc-num" style="color:#2EAD6E">'
          f'{_so(dem.get("xac_minh"))}</div>'
          '<div class="vc-lbl">Đã xác minh</div>'
          '<div class="vc-sub">có bằng chứng</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#C25E00">'
          f'</span><div class="vc-num" style="color:#C25E00">'
          f'{_so(dem.get("cho_soi"))}</div>'
          '<div class="vc-lbl">Chờ soi</div>'
          '<div class="vc-sub">tự khai, chưa có bằng chứng</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#E5484D">'
          f'</span><div class="vc-num" style="color:#E5484D">'
          f'{_so(dem.get("bac_bo"))}</div>'
          '<div class="vc-lbl">Bị bác</div>'
          '<div class="vc-sub">có thể vớt tay</div></div>'
        + "</div>"
        + f'<div class="ds-chips">{chip}'
          '<span class="kh-sp"></span>'
          '<form method="post" action="/crm/giam-sat/soi" class="vc-inline">'
          '<button class="kh-btn go" type="submit">🔍 Soi ngay</button>'
          "</form></div>"
        + '<div class="kh-card"><div class="kh-tblwrap"><table class="kh-tbl">'
          "<thead><tr><th>Lúc khai</th><th>Nhân viên</th><th>Khách</th>"
          "<th>Hành động</th><th>Nguồn</th><th>Kết quả soi</th>"
          "<th>Duyệt tay</th></tr></thead>"
          f"<tbody>{than}</tbody></table></div></div>"
        + '<p class="note" style="margin-top:10px">Luật: <b>1 công / khách / '
          "nhân viên / hành động / NGÀY</b> — nhắn 10 tin vẫn 1 công. Cuộc gọi "
          "không đi qua hệ thống nên bằng chứng là câu nhân viên gõ sau khi "
          'gọi ("e vừa gọi c rồi ạ").</p>'
    )
    return render_shell(
        "Giám sát & soi tin", "crm-audit-work", body,
        heading="Giám sát & soi tin",
        sub="Vòng xác minh công chăm sóc",
    )
