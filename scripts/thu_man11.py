"""Kiểm thử MÀN 11 — Bảng chăm sóc theo mốc (/crm/pipeline).

Màn này vừa được dựng lại theo bố cục Kallet: dải chỉ số · thanh lọc · quy tắc
tự động · bảng cột theo giai đoạn (chia dải theo mốc chăm) · khung làm việc bên
phải có thao tác THẬT (chuyển giai đoạn, đặt nhắc, đổi nhiệt độ, chia lại khách).

Script dựng dữ liệu giả mang dấu `__m11__`, mở màn, bấm từng thao tác rồi soi
lại DB xem có ăn không — kể cả các đường LỖI (luật FR-040/FR-031) và chặn quyền.
Dọn sạch đầu/cuối, KHÔNG gọi mạng.

Chạy:  python scripts/thu_man11.py
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.main import app                           # noqa: E402

DAU = "__m11__"
MK = "M11-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def don_dep(conn) -> None:
    kh = f"(select id from crm.customers where full_name like '{DAU}%')"
    conn.execute(f"delete from crm.lead_stage_history where lead_id in "
                 f"(select id from crm.leads where customer_id in {kh})")
    conn.execute(f"delete from crm.lead_lost_reasons where lead_id in "
                 f"(select id from crm.leads where customer_id in {kh})")
    conn.execute(f"delete from crm.leads where customer_id in {kh}")
    conn.execute(f"delete from crm.customers where full_name like '{DAU}%'")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")


def main() -> None:  # noqa: PLR0915 — script nghiệm thu, chạy tuần tự cho dễ đọc
    pool = get_pg_pool()
    gio = datetime.now(timezone.utc)
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        uid = {}
        for ten, vai in (("sale", "Sale"), ("sale2", "Sale"),
                         ("mkt", "Marketing"), ("ad", "Admin")):
            uid[ten] = conn.execute(
                "insert into crm.users (name, email, username, password_hash, "
                "status, role_id) values (%s, %s, %s, %s, 'active', %s) returning id",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]),
            ).fetchone()["id"]

        pipe = conn.execute(
            "select p.id as pid from crm.pipelines p order by p.id limit 1"
        ).fetchone()
        gd = {r["code"]: r["id"] for r in conn.execute(
            "select code, id from crm.pipeline_stages where pipeline_id = %s",
            (pipe["pid"],)).fetchall()}

        # 3 khách: quá hạn chăm · hẹn hôm nay · chưa đặt hẹn (đủ 3 dải trên cột)
        lead = {}
        for ten, hen, nhiet in (("QuaHan", gio - timedelta(days=2), "nong"),
                                ("HomNay", gio + timedelta(hours=3), "am"),
                                ("ChuaHen", None, None)):
            kh = conn.execute(
                "insert into crm.customers (full_name, primary_phone, province, "
                "status) values (%s, %s, 'Hà Nội', 'new') returning id",
                (f"{DAU}{ten}", "0900000001"),
            ).fetchone()["id"]
            lead[ten] = conn.execute(
                "insert into crm.leads (customer_id, pipeline_id, stage_id, "
                "owner_id, temperature, next_action_at) "
                "values (%s, %s, %s, %s, %s, %s) returning id",
                (kh, pipe["pid"], gd["lead_moi"], uid["sale"], nhiet, hen),
            ).fetchone()["id"]

    web = TestClient(app)

    def dang_nhap(u: str) -> None:
        r = web.post("/dang-nhap", data={"username": u, "password": MK},
                     follow_redirects=False)
        assert r.status_code == 303, r.status_code

    def loi(r) -> str:
        """Thông báo lỗi route nhét vào ?error= của redirect 303."""
        d = r.headers.get("location", "")
        return unquote(d.split("error=", 1)[1]) if "error=" in d else ""

    def doc_lead(lead_id: int) -> dict:
        with pool.connection() as c:
            return c.execute(
                "select l.*, s.code as stage_code from crm.leads l "
                "join crm.pipeline_stages s on s.id = l.stage_id where l.id = %s",
                (lead_id,)).fetchone()

    dang_nhap(f"{DAU}sale")

    print("== 1. Bố cục màn ==")
    r = web.get("/crm/pipeline")
    ok("trả 200", r.status_code == 200, str(r.status_code))
    t = r.text
    ok("tiêu đề 'Bảng chăm sóc theo mốc'", "Bảng chăm sóc theo mốc" in t)
    ok("dải chỉ số + tỉ lệ chốt", 'class="lp-kpi"' in t and "Tỉ lệ chốt" in t)
    ok("thanh lọc (tìm · nhân viên · nhiệt độ · mốc)",
       'name="q"' in t and 'name="owner_id"' in t
       and 'name="temperature"' in t and 'name="moc"' in t)
    ok("lọc theo thời điểm tạo có nút sẵn",
       "Lọc theo thời điểm tạo" in t and "30 ngày qua" in t)
    ok("khối quy tắc tự động", 'class="lp-rules"' in t and "FR-042" in t)
    ok("bảng cột + đủ 13 giai đoạn",
       'class="lp-board' in t and t.count('class="lp-col-t"') == 13)
    ok("3 khách giả lên thẻ",
       all(f"{DAU}{x}" in t for x in ("QuaHan", "HomNay", "ChuaHen")))
    ok("chia dải theo mốc chăm",
       "Quá hạn" in t and "Hôm nay" in t and "Chưa đặt hẹn" in t)
    ok("thẻ quá hạn được đánh dấu", 'class="lp-card od' in t and "quá hạn" in t)

    print("== 2. Xem 1 cột + khung làm việc ==")
    r = web.get(f"/crm/pipeline?st={gd['lead_moi']}")
    ok("cột đơn -> bảng 'one'", 'class="lp-board one"' in r.text)
    ok("chỉ vẽ 1 cột", r.text.count('class="lp-col-t"') == 1)
    ok("chưa chọn khách -> lời mời chọn",
       "Chọn một khách để bắt đầu chăm" in r.text)
    ok("có chip 'Đang xem cột'", "Đang xem cột:" in r.text)

    r = web.get(f"/crm/pipeline?lead={lead['QuaHan']}")
    t = r.text
    ok("mở khách -> khung làm việc", 'class="lp-pane"' in t
       and f"{DAU}QuaHan" in t)
    ok("khung có đủ 13 nút giai đoạn",
       t.count('class="lp-step"') + t.count('class="lp-step on"') == 13)
    ok("có form chuyển giai đoạn · đặt nhắc · nhiệt độ · chia lại",
       all(f'action="/crm/pipeline/{lead["QuaHan"]}/{x}"' in t
           for x in ("giai-doan", "hen", "nhiet", "chia-lai")))
    ok("có nhật ký + lối sang hồ sơ 360°",
       "Nhật ký chăm sóc" in t and "Hồ sơ 360°" in t)

    print("== 3. Chuyển giai đoạn (luật FR-040) ==")
    ve = f"/crm/pipeline?st={gd['lead_moi']}&lead={lead['QuaHan']}"
    r = web.post(f"/crm/pipeline/{lead['QuaHan']}/giai-doan",
                 data={"stage_id": gd["da_ket_noi"], "ve": ve},
                 follow_redirects=False)
    l = doc_lead(lead["QuaHan"])
    ok("sang 'Đã kết nối' được", r.status_code == 303
       and l["stage_code"] == "da_ket_noi", str(r.status_code))
    ok("tự ghi mốc chạm đầu tiên (FR-042)", l["first_contact_at"] is not None)

    r = web.post(f"/crm/pipeline/{lead['QuaHan']}/giai-doan",
                 data={"stage_id": gd["dang_can_nhac"], "ve": ve},
                 follow_redirects=False)
    ok("'Đang cân nhắc' thiếu lý do -> chặn + báo lỗi",
       "lý do" in loi(r).lower()
       and doc_lead(lead["QuaHan"])["stage_code"] == "da_ket_noi", loi(r))
    # Đi tiếp cái 303 đó: URL quay về đã có sẵn query nên `_ve` phải nối bằng
    # "&" — nối "?" là trang đích 422 và người dùng không thấy lỗi bao giờ.
    r2 = web.get(r.headers["location"])
    ok("theo redirect -> vẫn 200, hiện dải lỗi, giữ nguyên khách đang mở",
       r2.status_code == 200 and 'class="flash err"' in r2.text
       and f"{DAU}QuaHan" in r2.text, str(r2.status_code))

    r = web.post(f"/crm/pipeline/{lead['QuaHan']}/giai-doan",
                 data={"stage_id": gd["dang_can_nhac"], "reason": "khách hỏi giá",
                       "next_action_at": (datetime.now() + timedelta(days=1)
                                          ).strftime("%Y-%m-%dT09:00"), "ve": ve},
                 follow_redirects=False)
    ok("đủ lý do + lịch hẹn -> qua",
       doc_lead(lead["QuaHan"])["stage_code"] == "dang_can_nhac", loi(r))

    r = web.post(f"/crm/pipeline/{lead['ChuaHen']}/giai-doan",
                 data={"stage_id": gd["da_chot"], "reason": "chốt", "ve": ve},
                 follow_redirects=False)
    ok("'Đã chốt' mà chưa có đơn -> chặn",
       "đơn hàng" in loi(r) and doc_lead(lead["ChuaHen"])["stage_code"] == "lead_moi",
       loi(r))

    print("== 3b. Đóng hồ sơ phải có lý do chuẩn (LEAD-010) ==")
    r = web.get(f"/crm/pipeline?lead={lead['QuaHan']}")
    ok("khung làm việc có ô lý do chưa mua",
       'name="lost_reason_id"' in r.text and "Giá cao" in r.text)
    r = web.post(f"/crm/pipeline/{lead['QuaHan']}/giai-doan",
                 data={"stage_id": gd["tu_choi"], "ve": ve},
                 follow_redirects=False)
    ok("'Từ chối' không chọn lý do -> chặn",
       "lý do chuẩn" in loi(r)
       and doc_lead(lead["QuaHan"])["stage_code"] == "dang_can_nhac", loi(r))
    with pool.connection() as c:
        ld = c.execute("select id from crm.lead_reasons where code = 'gia_cao'"
                       ).fetchone()["id"]
    web.post(f"/crm/pipeline/{lead['QuaHan']}/giai-doan",
             data={"stage_id": gd["tu_choi"], "lost_reason_id": ld, "ve": ve},
             follow_redirects=False)
    l = doc_lead(lead["QuaHan"])
    ok("chọn lý do -> đóng được, có closed_at",
       l["stage_code"] == "tu_choi" and l["closed_at"] is not None)
    r = web.get(f"/crm/pipeline?st={gd['tu_choi']}")
    ok("hồ sơ đóng nằm ở dải 'Đã đóng', không bị tô quá hạn",
       "Đã đóng" in r.text and f"{DAU}QuaHan" in r.text
       and "quá hạn" not in r.text.split(f"{DAU}QuaHan")[0][-400:])

    print("== 4. Thao tác nhanh ==")
    mai = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT15:30")
    web.post(f"/crm/pipeline/{lead['HomNay']}/hen",
             data={"next_action_at": mai, "ve": ve}, follow_redirects=False)
    l = doc_lead(lead["HomNay"])
    ok("đặt nhắc lại ghi đúng mốc",
       l["next_action_at"] is not None
       and l["next_action_at"].astimezone().strftime("%Y-%m-%dT%H:%M") == mai,
       str(l["next_action_at"]))

    web.post(f"/crm/pipeline/{lead['ChuaHen']}/nhiet",
             data={"temperature": "nong", "ve": ve}, follow_redirects=False)
    ok("đổi nhiệt độ", doc_lead(lead["ChuaHen"])["temperature"] == "nong")
    r = web.post(f"/crm/pipeline/{lead['ChuaHen']}/nhiet",
                 data={"temperature": "xyz", "ve": ve}, follow_redirects=False)
    ok("nhiệt độ lạ bị chặn (CHECK của bảng)",
       "nóng / ấm / lạnh" in loi(r)
       and doc_lead(lead["ChuaHen"])["temperature"] == "nong", loi(r))

    r = web.post(f"/crm/pipeline/{lead['HomNay']}/chia-lai",
                 data={"owner_id": uid["sale2"], "ve": ve},
                 follow_redirects=False)
    ok("chuyển người mà không có lý do -> chặn (FR-031)",
       "lý do" in loi(r).lower()
       and doc_lead(lead["HomNay"])["owner_id"] == uid["sale"], loi(r))
    web.post(f"/crm/pipeline/{lead['HomNay']}/chia-lai",
             data={"owner_id": uid["sale2"], "reason": "nghỉ phép", "ve": ve},
             follow_redirects=False)
    ok("có lý do -> chuyển được",
       doc_lead(lead["HomNay"])["owner_id"] == uid["sale2"])

    print("== 5. Bộ lọc + chế độ Bảng ==")
    r = web.get(f"/crm/pipeline?q={DAU}ChuaHen")
    ok("lọc theo tên", f"{DAU}ChuaHen" in r.text and f"{DAU}HomNay" not in r.text)
    r = web.get("/crm/pipeline?temperature=nong")
    ok("lọc nhiệt độ nóng",
       f"{DAU}ChuaHen" in r.text and f"{DAU}HomNay" not in r.text)
    r = web.get("/crm/pipeline?moc=chua_hen")
    ok("lọc mốc 'chưa đặt hẹn'",
       f"{DAU}ChuaHen" in r.text and f"{DAU}HomNay" not in r.text)
    r = web.get(f"/crm/pipeline?owner_id={uid['sale2']}")
    ok("lọc theo nhân viên",
       f"{DAU}HomNay" in r.text and f"{DAU}ChuaHen" not in r.text)
    hom_qua = (datetime.now() - timedelta(days=1)).date().isoformat()
    r = web.get(f"/crm/pipeline?tu=2000-01-01&den={hom_qua}")
    ok("lọc khoảng ngày tạo (khách hôm nay rơi ra ngoài)",
       f"{DAU}ChuaHen" not in r.text)
    r = web.get("/crm/pipeline?xem=bang")
    ok("chế độ Bảng", 'class="lp-tbl"' in r.text and f"{DAU}ChuaHen" in r.text)

    print("== 6. Chặn quyền ==")
    dang_nhap(f"{DAU}mkt")               # Marketing: không có customer.edit
    r = web.post(f"/crm/pipeline/{lead['ChuaHen']}/nhiet",
                 data={"temperature": "lanh"}, follow_redirects=False)
    ok("không có customer.edit -> 403",
       r.status_code == 403 and doc_lead(lead["ChuaHen"])["temperature"] == "nong",
       str(r.status_code))

    print("== 7. Thứ tự menu trái ==")
    dang_nhap(f"{DAU}ad")                # Admin mới thấy mục Quản trị
    nav = web.get("/crm/pipeline").text.split('<nav class="nav">')[1].split("</nav>")[0]
    i_sale = nav.find("<span>Sale</span>")
    i_cskh = nav.find("<span>Chăm sóc khách hàng</span>")
    i_bot = nav.find(">Bot Pancake<")
    i_qt = nav.find("<span>Quản trị</span>")
    ok("khối Sale rồi tới khối Chăm sóc khách hàng", 0 < i_sale < i_cskh,
       f"sale={i_sale} cskh={i_cskh}")
    # Giữa 2 khối chỉ được có con của khối Sale (nd-link) và 2 link phẳng
    # mobile-only (màn hẹp) — không còn mục nav-item thường nào chen vào
    chen = [m for m in re.findall(r'<a class="nav-item[^"]*"', nav[i_sale:i_cskh])
            if "mobile-only" not in m]
    ok("giữa 2 khối không còn mục thường nào chen vào", not chen, str(chen))
    ok("Quản trị nằm cuối menu, dưới nhóm Bot Pancake", i_bot < i_qt,
       f"bot={i_bot} quantri={i_qt}")
    ok("Quản trị có vạch ngăn thay tiêu đề nhóm",
       'class="nav-sep"' in nav[i_bot:i_qt])

    with pool.connection() as conn:
        don_dep(conn)
    print(f"\n== TỔNG: {PASS} PASS · {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
