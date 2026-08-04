"""Màn Chiến dịch 2 tầng + Mẫu tin (C3 — port mẫu Kallet chien-dich.php,
mau-tin.php).

Giao diện phải nói rõ HAI THỨ, vì đây là màn duy nhất bắn tin tới khách thật:

  1. **Đang ở chế độ nào** — dải băng đỏ/xanh ngay đầu trang. Người dùng bấm
     "Chạy đợt" mà không biết công tắc đang bật là tai nạn không hoàn tác được.
  2. **Hai tầng tách bạch** — cột "đã gửi" (máy làm) và cột "đã trả lời → việc"
     (người làm) đứng riêng, kèm tỷ lệ. Gộp lại là mất khả năng biết chiến dịch
     yếu ở tầng nội dung hay tầng chốt.
"""

from html import escape

from app.services import campaign_service as svc
from app.web.shell import render_shell


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else "—"


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _tien_gon(n) -> str:
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return "0k"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"
    return f"{round(v / 1000)}k"


def _pct(v) -> str:
    return f"{v}%" if v is not None else "—"


def _bang_gui_tin() -> str:
    """Dải băng trạng thái công tắc — LUÔN hiện, không cho ẩn."""
    if svc.gui_that():
        return ('<div class="flash err" style="font-weight:600">🔴 CÔNG TẮC '
                "GỬI TIN ĐANG BẬT — bấm “Chạy đợt” là tin bay tới khách thật "
                "và <b>không thu hồi được</b>. Tắt ở "
                '<a href="/quan-tri/cai-dat">Cài đặt → Gửi tin hàng loạt</a>.'
                "</div>")
    return ('<div class="flash warn">✏️ Đang ở <b>chế độ NHÁP</b> — chạy đợt '
            "chỉ đếm và dựng nội dung, <b>không tin nào rời hệ thống</b> và "
            "khách không bị đánh dấu đã gửi. Bật gửi thật ở "
            '<a href="/quan-tri/cai-dat">Cài đặt → Gửi tin hàng loạt</a> '
            "(bước cuối cùng khi triển khai).</div>")


_TT_LOP = {"draft": "chua", "running": "active", "paused": "fading",
           "finished": "sleep"}


def _hang(c: dict) -> str:
    tt = c["status"]
    nut = ""
    if tt in ("draft", "paused"):
        nut += (f'<form method="post" action="/crm/chien-dich/{c["id"]}/trang-thai"'
                ' class="vc-inline"><input type="hidden" name="tt" value="running">'
                '<button class="kh-btn go" type="submit">Chạy</button></form>')
    if tt == "running":
        nut += (f'<form method="post" action="/crm/chien-dich/{c["id"]}/chay-dot"'
                ' class="vc-inline"><input name="so_luong" type="number" min="1" '
                f'value="{int(c["batch_size"] or 500)}" style="width:80px">'
                '<button class="kh-btn go" type="submit">Chạy 1 đợt</button>'
                "</form>"
                f'<form method="post" action="/crm/chien-dich/{c["id"]}/trang-thai"'
                ' class="vc-inline"><input type="hidden" name="tt" value="paused">'
                '<button class="kh-btn" type="submit">Tạm dừng</button></form>')
    if tt != "finished":
        nut += (f'<form method="post" action="/crm/chien-dich/{c["id"]}/trang-thai"'
                ' class="vc-inline" onsubmit="return confirm(\'Đóng chiến dịch? '
                "Khách chưa chốt sẽ được NHẢ ra để vào chiến dịch khác.')\">"
                '<input type="hidden" name="tt" value="finished">'
                '<button class="kh-btn" type="submit">Đóng</button></form>')
    return (
        "<tr>"
        f'<td><a class="kh-name" href="/crm/chien-dich/{c["id"]}">'
        f'{_e(c["name"])}</a>'
        f'<div class="kh-sub">{_e(c.get("description"))}</div></td>'
        f'<td><span class="kh-st {_TT_LOP.get(tt, "chua")}">'
        f'{escape(svc.TRANG_THAI.get(tt, tt))}</span></td>'
        f'<td class="num">{_so(c["so_khach"])}</td>'
        f'<td class="num">{_so(c["da_gui"])}</td>'
        f'<td class="num">{_so(c["da_tra_loi"])}'
        f'<div class="kh-nho">{_pct(c.get("tra_loi_pct"))}</div></td>'
        f'<td class="num">{_so(c["ra_don"])}'
        f'<div class="kh-nho">{_pct(c.get("chot_pct"))} của người trả lời</div></td>'
        f'<td class="money">{_tien_gon(c["doanh_thu"])}</td>'
        f'<td><div class="ds-acts">{nut}</div></td>'
        "</tr>"
    )


def _form_tao(xem_truoc: int | None, loc: dict, mau: list[dict],
              flash: str = "") -> str:
    """Wizard rút gọn thành MỘT form: chọn tệp → xem trước → tạo.

    Mẫu chia 4 bước; ở đây gộp một màn nhưng giữ nguyên điểm cốt lõi: **phải
    xem trước số khách rồi mới tạo được**, và số xem trước với số nạp thật
    dùng chung một bộ lọc."""
    o_nhom = "".join(
        f'<option value="{ma}"{" selected" if loc.get("nhom") == ma else ""}>'
        f"{escape(ten)}</option>" for ma, (ten, _, _) in svc.NHOM_TEP.items())
    o_mau = ('<option value="">— không gửi gì (chỉ gom tệp) —</option>'
             + "".join(f'<option value="{m["id"]}">{escape(m["code"])} · '
                       f'{escape(m["name"] or "")}</option>' for m in mau))
    xt = ""
    if xem_truoc is not None:
        xt = (f'<div class="cd-preview">Bộ lọc này khớp <b>{_so(xem_truoc)} '
              "khách</b> ngay lúc này (đã trừ khách đang nằm ở chiến dịch "
              "khác). Tạo chiến dịch sẽ nạp đúng bấy nhiêu.</div>"
              if xem_truoc else
              '<div class="cd-preview warn">Không khách nào khớp bộ lọc — '
              "đổi nhóm/hạng thẻ rồi xem lại.</div>")
    return (
        '<details class="kh-card" style="padding:16px 18px;margin-bottom:14px"'
        + (" open" if xem_truoc is not None or flash else "") + ">"
        "<summary style=\"font-weight:700;cursor:pointer\">➕ Tạo chiến dịch "
        "mới</summary>"
        '<form method="get" action="/crm/chien-dich" class="vc-form-r" '
        'style="margin-top:12px">'
        f'<label>Nhóm khách<select name="nhom">{o_nhom}</select></label>'
        '<label>Hạng thẻ<select name="hang">'
        '<option value="">Tất cả</option>'
        '<option value="chua_xep">Chưa xếp hạng</option>'
        '<option value="new_member">New Member</option>'
        '<option value="member">Member</option>'
        '<option value="silver">Silver</option>'
        '<option value="gold">Gold</option>'
        '<option value="diamond">Diamond</option></select></label>'
        '<label>Số lần mua<select name="so_mua">'
        '<option value="">Tất cả</option><option value="1">1 lần</option>'
        '<option value="2p">2 lần trở lên</option></select></label>'
        '<input type="hidden" name="xem" value="1">'
        '<button class="kh-btn" type="submit">👁 Xem trước số khách</button>'
        "</form>"
        + xt
        + ('<form method="post" action="/crm/chien-dich/tao" class="vc-form-r" '
           'style="margin-top:12px">'
           f'<input type="hidden" name="nhom" value="{escape(loc.get("nhom") or "")}">'
           f'<input type="hidden" name="hang" value="{escape(loc.get("hang") or "")}">'
           f'<input type="hidden" name="so_mua" value="{escape(loc.get("so_mua") or "")}">'
           '<label style="flex:2 1 220px">Tên chiến dịch'
           '<input name="ten" required placeholder="vd Khơi lại khách ngủ T8"></label>'
           f'<label style="flex:2 1 200px">Mẫu tin tầng 1'
           f'<select name="template_id">{o_mau}</select></label>'
           '<label style="flex:0 1 130px">Mỗi đợt (khách)'
           '<input type="number" name="moi_dot" min="1" max="5000" value="500">'
           "</label>"
           '<label style="flex:0 1 120px">Cách nhau (ngày)'
           '<input type="number" name="cach_ngay" min="1" max="60" value="7">'
           "</label>"
           '<button class="kh-btn go" type="submit">Tạo chiến dịch</button>'
           '</form>'
           '<p class="note">Mẫu chốt nhịp an toàn: <b>đợt đầu 500 khách ngẫu '
           "nhiên</b> để đo phản hồi, sau đó mới 5.000/tuần. Bắn cả tệp một "
           "lượt là cách nhanh nhất để Meta khoá page.</p>"
           if xem_truoc else "")
        + "</details>"
    )


def render_chien_dich(rows: list[dict], *, xem_truoc: int | None = None,
                      loc: dict | None = None, mau: list[dict] | None = None,
                      flash: str = "", loi: str = "") -> str:
    tong = {
        "khach": sum(int(c["so_khach"] or 0) for c in rows),
        "gui": sum(int(c["da_gui"] or 0) for c in rows),
        "tra_loi": sum(int(c["da_tra_loi"] or 0) for c in rows),
        "don": sum(int(c["ra_don"] or 0) for c in rows),
    }
    than = "".join(_hang(c) for c in rows) or (
        '<tr><td colspan="8" class="rong">Chưa có chiến dịch nào. Bấm '
        "<b>Tạo chiến dịch mới</b> ở trên.</td></tr>")
    body = (
        _bang_gui_tin()
        + (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + '<div class="cd-tang">'
          '<div class="cd-t1"><b>TẦNG 1 · máy gửi</b> cho cả tệp — miễn phí, '
          "không tốn người</div>"
          '<div class="cd-mui">→ chỉ khách <b>TRẢ LỜI</b> →</div>'
          '<div class="cd-t2"><b>TẦNG 2 · sinh việc</b> cho nhân viên chăm '
          "tiếp</div></div>"
        + _form_tao(xem_truoc, loc or {}, mau or [], flash)
        + '<div class="vc-tiles">'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#4E7FE8">'
          f'</span><div class="vc-num" style="color:#4E7FE8">{_so(tong["khach"])}'
          '</div><div class="vc-lbl">Khách trong chiến dịch</div>'
          '<div class="vc-sub">&nbsp;</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#a8718f">'
          f'</span><div class="vc-num" style="color:#a8718f">{_so(tong["gui"])}'
          '</div><div class="vc-lbl">Đã gửi tầng 1</div>'
          '<div class="vc-sub">máy làm</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#2EAD6E">'
          f'</span><div class="vc-num" style="color:#2EAD6E">'
          f'{_so(tong["tra_loi"])}</div><div class="vc-lbl">Trả lời → việc tầng 2'
          '</div><div class="vc-sub">người làm</div></div>'
        + f'<div class="vc-tile"><span class="vc-vach" style="background:#7A308F">'
          f'</span><div class="vc-num" style="color:#7A308F">{_so(tong["don"])}'
          '</div><div class="vc-lbl">Ra đơn</div>'
          '<div class="vc-sub">&nbsp;</div></div>'
        + "</div>"
        + '<div class="kh-card"><div class="kh-tblwrap"><table class="kh-tbl">'
          "<thead><tr><th>Chiến dịch</th><th>Trạng thái</th>"
          '<th class="num">Khách</th><th class="num">Đã gửi (T1)</th>'
          '<th class="num">Trả lời (T2)</th><th class="num">Ra đơn</th>'
          '<th class="num">Doanh thu</th><th>Thao tác</th></tr></thead>'
          f"<tbody>{than}</tbody></table></div></div>"
        + '<p class="note" style="margin-top:10px">Ba tỷ lệ trả lời ba câu hỏi '
          "khác nhau: <b>% trả lời</b> = nội dung tầng 1 có đủ hấp dẫn không · "
          "<b>% chốt</b> = nhân viên có chốt được khách đã giơ tay không · "
          "<b>doanh thu</b> = hiệu quả chung. Đừng trộn ba số làm một.</p>"
    )
    return render_shell(
        "Chiến dịch", "crm-campaign", body,
        heading="Chiến dịch",
        sub="Hai tầng: máy gửi cả tệp · người chỉ chăm khách đã trả lời",
    )


def render_chi_tiet(cd: dict, tv1: list[dict], tv2: list[dict],
                    *, flash: str = "") -> str:
    def _bang(rows: list[dict], tang2: bool) -> str:
        than = "".join(
            "<tr>"
            f'<td><a class="kh-name" href="/crm/khach-hang/{r["customer_id"]}">'
            f'{_e(r["full_name"])}</a>'
            f'<div class="kh-sub">{_e(r["primary_phone"])}</div></td>'
            f'<td>{_e(r["assigned_name"])}</td>'
            + (f'<td>{_e(r["task_title"])}'
               f'<div class="kh-nho">{_e(r["task_status"])}</div></td>'
               if tang2 else
               f'<td>{"đã gửi" if r["sent_at"] else "chưa gửi"}</td>')
            + f'<td class="kh-nho">{r["sent_at"].strftime("%d/%m %H:%M") if r["sent_at"] else "—"}</td>'
            "</tr>" for r in rows) or (
            f'<tr><td colspan="4" class="rong">'
            + ("Chưa khách nào trả lời." if tang2 else "Chưa có khách nào.")
            + "</td></tr>")
        cot3 = "Việc tầng 2" if tang2 else "Tình trạng gửi"
        return ('<div class="kh-tblwrap"><table class="kh-tbl"><thead><tr>'
                f"<th>Khách</th><th>Phụ trách</th><th>{cot3}</th>"
                "<th>Gửi lúc</th></tr></thead>"
                f"<tbody>{than}</tbody></table></div>")

    body = (
        _bang_gui_tin()
        + (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + '<div class="kh-card" style="padding:16px 18px">'
          f'<div class="ht-h">{escape(cd["name"])}'
          f'<span class="kh-st {_TT_LOP.get(cd["status"], "chua")}">'
          f'{escape(svc.TRANG_THAI.get(cd["status"], cd["status"]))}</span></div>'
          f'<p class="note">{_e(cd.get("description"))} · mỗi đợt '
          f'<b>{int(cd["batch_size"] or 0)}</b> khách · cách nhau '
          f'<b>{int(cd["batch_interval_days"] or 0)}</b> ngày · người tạo '
          f'{_e(cd.get("created_by_name"))}</p></div>'
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
          f'<div class="ht-h">TẦNG 1 — máy gửi ({len(tv1)} khách chưa trả lời)'
          "</div>" + _bang(tv1, False) + "</div>"
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
          f'<div class="ht-h">TẦNG 2 — khách đã trả lời ({len(tv2)})</div>'
          + _bang(tv2, True)
          + '<p class="note">Mỗi khách trả lời sinh ĐÚNG MỘT việc, dù họ nhắn '
            "bao nhiêu câu.</p></div>"
        + '<p class="note" style="margin-top:10px">'
          '<a href="/crm/chien-dich">← Về danh sách chiến dịch</a></p>'
    )
    return render_shell(
        f'Chiến dịch · {cd["name"]}', "crm-campaign", body,
        heading=cd["name"], sub="Chi tiết hai tầng",
    )


# ------------------------------------------------------------------ Mẫu tin
_KIND_NHAN = {"tu_do": "Tự do (chỉ trong cửa 24h)",
              "meta_duyet": "Meta đã duyệt (gửi được ngoài cửa)"}
_META_NHAN = {"rong": "—", "chi_trong_cua": "chỉ trong cửa",
              "gui_ngoai_cua": "gửi được ngoài cửa"}


def render_mau_tin(rows: list[dict], *, flash: str = "", loi: str = "",
                   xem_thu: str = "") -> str:
    than = "".join(
        "<tr>"
        f'<td><b>{_e(r["code"])}</b><div class="kh-sub">{_e(r["name"])}</div></td>'
        f'<td>{escape(_KIND_NHAN.get(r["kind"], r["kind"]))}</td>'
        f'<td>{escape(_META_NHAN.get(r["meta_status"], r["meta_status"]))}</td>'
        f'<td><code class="mt-body">{escape((r["body"] or "")[:160])}</code></td>'
        f'<td class="kh-nho">{_e(r["variables"])}</td>'
        f'<td class="num">{_so(r["sent_count"])}</td>'
        f'<td><div class="ds-acts">'
        f'<form method="post" action="/crm/mau-tin/{r["id"]}/xem-thu" '
        'class="vc-inline"><button class="kh-btn" type="submit">Xem thử</button>'
        "</form>"
        f'<form method="post" action="/crm/mau-tin/{r["id"]}/trang-thai" '
        'class="vc-inline"><input type="hidden" name="tt" value="'
        + ("inactive" if r["status"] == "active" else "active") + '">'
        '<button class="kh-btn" type="submit">'
        + ("Ngừng dùng" if r["status"] == "active" else "Dùng lại")
        + "</button></form></div></td>"
        "</tr>" for r in rows) or (
        '<tr><td colspan="7" class="rong">Chưa có mẫu tin nào.</td></tr>')
    body = (
        (f'<div class="flash ok">{escape(flash)}</div>' if flash else "")
        + (f'<div class="flash err">{escape(loi)}</div>' if loi else "")
        + (f'<div class="flash ok"><b>Xem thử:</b><br>{escape(xem_thu)}</div>'
           if xem_thu else "")
        + '<div class="flash warn">⚠️ <b>Tự do</b> vs <b>Meta đã duyệt</b> '
          "không thay nhau được: mẫu tự do chỉ gửi được trong cửa 24h kể từ "
          "tin cuối của khách; ngoài cửa phải dùng mẫu Meta đã duyệt. Gửi "
          "nhầm loại là page bị phạt.</div>"
        + '<div class="kh-card"><div class="kh-tblwrap"><table class="kh-tbl">'
          '<thead><tr><th>Mã / tên</th><th>Loại</th><th>Ngoài cửa?</th>'
          '<th>Nội dung</th><th>Biến</th><th class="num">Đã gửi</th>'
          "<th>Thao tác</th></tr></thead>"
          f"<tbody>{than}</tbody></table></div></div>"
        + '<div class="kh-card" style="padding:16px 18px;margin-top:14px">'
          '<div class="ht-h">Thêm / sửa mẫu tin</div>'
          '<form method="post" action="/crm/mau-tin" class="vc-form-r">'
          '<label>Mã (trùng mã = sửa)<input name="code" required '
          'placeholder="VD MOI_LAI_01" style="text-transform:uppercase"></label>'
          '<label style="flex:2 1 200px">Tên<input name="name" '
          'placeholder="Mời khách ngủ quay lại"></label>'
          '<label>Loại<select name="kind">'
          '<option value="tu_do">Tự do (trong cửa 24h)</option>'
          '<option value="meta_duyet">Meta đã duyệt</option></select></label>'
          '<label>Gửi ngoài cửa?<select name="meta_status">'
          '<option value="rong">—</option>'
          '<option value="chi_trong_cua">chỉ trong cửa</option>'
          '<option value="gui_ngoai_cua">gửi được ngoài cửa</option>'
          "</select></label>"
          '<label style="flex:1 1 200px">Biến (cách nhau dấu phẩy)'
          '<input name="variables" placeholder="ten_khach,ma_voucher"></label>'
          '<label style="flex:3 1 100%">Nội dung'
          '<textarea name="body" rows="3" required '
          'placeholder="Chào {{ten_khach}}, bên em có ưu đãi..."></textarea>'
          "</label>"
          '<button class="kh-btn go" type="submit">Lưu mẫu</button>'
          "</form>"
          '<p class="note">Biến viết dạng <code>{{ten_khach}}</code> và phải '
          "khai ở ô Biến — không khai thì lúc lưu bị chặn, tránh việc khách "
          "nhận được nguyên dấu ngoặc.</p></div>"
    )
    return render_shell(
        "Mẫu tin", "crm-template", body,
        heading="Mẫu tin",
        sub="Nội dung dùng cho chiến dịch và gửi hàng loạt",
    )
