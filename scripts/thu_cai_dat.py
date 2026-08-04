"""Kiểm thử màn CÀI ĐẶT hệ thống (màn 78 · SYSTEM-001/002).

Nghiệm thu:
  đọc     thứ tự ưu tiên app_settings → .env; chưa đổi gì thì y hệt .env
  ghi     ép kiểu, chặn ngoài khoảng hợp lệ, ghi audit, trả về mặc định được
  hiệu lực  worker đọc lại qua runtime_config (không phải restart) — kiểm bằng
            cách đổi rồi đọc lại đúng hàm mà worker gọi
  form    checkbox KHÔNG tick = TẮT (trình duyệt không gửi ô đó lên)
  quyền   chỉ user.manage vào được; Sale bị 403

Chạy:  python scripts/thu_cai_dat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from app.core import runtime_config as cfg         # noqa: E402
from app.core.config import settings               # noqa: E402
from app.core.errors import ApiError               # noqa: E402
from app.core.security import hash_password        # noqa: E402
from app.db.client import get_pg_pool              # noqa: E402
from app.main import app                           # noqa: E402
from app.services import cai_dat_service           # noqa: E402

DAU = "__cdtest__"
MK = "CD-test-1234"
PASS = 0
FAIL = 0


def ok(ten: str, dk: bool, them: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if dk else (PASS, FAIL + 1)
    print(f"  {'PASS' if dk else 'FAIL'}  {ten}  {'' if dk else them}")


def phai_loi(ten: str, ma: str, fn, *a, **kw) -> None:
    try:
        fn(*a, **kw)
        ok(ten, False, "không raise gì cả")
    except ApiError as e:
        ok(ten, e.code == ma, f"raise {e.code} thay vì {ma}")


def don_dep(conn) -> None:
    conn.execute("delete from crm.app_settings")
    conn.execute(f"delete from crm.users where email like '{DAU}%'")
    conn.execute("delete from crm.audit_logs where object_type = 'app_settings'")
    cfg.xoa_cache()


def main() -> None:
    pool = get_pg_pool()
    with pool.connection() as conn:
        don_dep(conn)
        role = {r["name"]: r["id"] for r in conn.execute(
            "select id, name from crm.roles").fetchall()}
        for ten, vai in (("admin", "Admin"), ("sale", "Sale")):
            conn.execute(
                "insert into crm.users (name, email, username, password_hash, status, role_id) "
                "values (%s, %s, %s, %s, 'active', %s)",
                (f"{DAU}{ten}", f"{DAU}{ten}@x.com", f"{DAU}{ten}",
                 hash_password(MK), role[vai]))

    print("== 1. Chưa đổi gì -> chạy đúng theo .env ==")
    ok("đọc công tắc = giá trị .env",
       cfg.bat("pos_sync_enabled") == settings.pos_sync_enabled)
    ok("đọc nhịp = giá trị .env",
       cfg.so("pos_sync_interval") == settings.pos_sync_interval)
    ok("chưa ghi đè -> da_doi() False", not cfg.da_doi("pos_sync_interval"))
    ds = cfg.danh_sach()
    ok("danh mục đủ nhóm + mã", len(ds) >= 15
       and {"dong_bo", "quang_cao", "bot"} <= {m["nhom"] for m in ds})
    # So với DANH SÁCH BÍ MẬT THẬT trong .env, không so theo chuỗi con: có cài đặt
    # tên chứa "token" mà hoàn toàn vô hại (sync_token_check_hours = nhịp KIỂM token).
    bi_mat = {
        "pancake_access_token", "pancake_page_tokens", "pancake_pos_api_key",
        "fb_page_access_token", "fb_verify_token", "fb_app_secret",
        "gemini_api_key", "openai_api_key", "telegram_bot_token", "jwt_secret",
        "admin_bootstrap_password", "database_url", "supabase_url", "supabase_key",
    }
    ok("KHÔNG bày token/mật khẩu/chuỗi kết nối lên màn cài đặt",
       not ({m["code"] for m in ds} & bi_mat),
       str({m["code"] for m in ds} & bi_mat))

    print("== 2. Ghi đè + hiệu lực ngay (không restart) ==")
    cai_dat_service.dat("pos_sync_interval", 900)
    ok("đổi xong đọc lại ra giá trị mới", cfg.so("pos_sync_interval") == 900)
    ok("đánh dấu đã đổi so với .env", cfg.da_doi("pos_sync_interval"))
    ok("giá trị trong .env KHÔNG bị đụng tới",
       settings.pos_sync_interval == 300.0, str(settings.pos_sync_interval))
    cai_dat_service.dat("pos_sync_enabled", True)
    ok("bật công tắc -> hàm worker gọi trả True", cfg.bat("pos_sync_enabled"))
    cai_dat_service.dat("pos_sync_enabled", False)
    ok("tắt lại -> False", not cfg.bat("pos_sync_enabled"))

    print("== 3. Ép kiểu + chặn ngoài khoảng ==")
    ok("chuỗi '1'/'true' -> bật", cai_dat_service.dat(
        "crm_sync_enabled", "true")["gia_tri"] is True)
    ok("số thực cho ô kiểu int -> cắt về int",
       isinstance(cai_dat_service.dat("sync_retry_batch", 12.7)["gia_tri"], int))
    phai_loi("nhịp nhỏ hơn mức tối thiểu -> VALIDATION_ERROR", "VALIDATION_ERROR",
             cai_dat_service.dat, "pos_sync_interval", 1)
    phai_loi("nhịp lớn hơn mức tối đa -> VALIDATION_ERROR", "VALIDATION_ERROR",
             cai_dat_service.dat, "pos_sync_interval", 999999)
    phai_loi("chữ vào ô số -> VALIDATION_ERROR", "VALIDATION_ERROR",
             cai_dat_service.dat, "pos_sync_interval", "nhanh")
    phai_loi("cách quét lạ -> VALIDATION_ERROR", "VALIDATION_ERROR",
             cai_dat_service.dat, "sentiment_method", "magic")
    phai_loi("mã cài đặt không có -> NOT_FOUND", "NOT_FOUND",
             cai_dat_service.dat, "khong_co_muc_nay", 1)
    ok("sai khoảng thì KHÔNG ghi gì (giữ 900)", cfg.so("pos_sync_interval") == 900)

    print("== 4. Lưu cả nhóm — sai 1 ô thì không ô nào được ghi ==")
    phai_loi("dat_nhieu có 1 ô sai -> VALIDATION_ERROR", "VALIDATION_ERROR",
             cai_dat_service.dat_nhieu,
             {"pos_sync_interval": 600, "sync_retry_batch": 9999})
    ok("ô hợp lệ trong mẻ hỏng cũng KHÔNG được ghi",
       cfg.so("pos_sync_interval") == 900, str(cfg.so("pos_sync_interval")))
    cai_dat_service.dat_nhieu({"pos_sync_interval": 600, "sync_retry_batch": 20})
    ok("mẻ hợp lệ ghi hết", cfg.so("pos_sync_interval") == 600
       and cfg.so("sync_retry_batch") == 20)

    print("== 5. Trả về mặc định ==")
    cai_dat_service.dat_lai_mac_dinh("pos_sync_interval")
    ok("bỏ ghi đè -> quay về .env",
       cfg.so("pos_sync_interval") == settings.pos_sync_interval
       and not cfg.da_doi("pos_sync_interval"))

    print("== 6. Audit ==")
    with pool.connection() as conn:
        so_dong = conn.execute(
            "select count(*) n from crm.audit_logs where object_type = 'app_settings'"
        ).fetchone()["n"]
    ok("mỗi lần đổi/reset đều vào nhật ký", so_dong >= 5, str(so_dong))

    print("== 7. Công tắc dùng chung với màn Cảm xúc (không đẻ nguồn thứ hai) ==")
    from app.workers import switch

    truoc = switch.is_on()
    cai_dat_service.dat("sentiment_enabled", not truoc)
    ok("đổi ở màn Cài đặt -> công tắc của worker cảm xúc đổi theo",
       switch.is_on() == (not truoc))
    cai_dat_service.dat("sentiment_enabled", truoc)
    ok("trả lại như cũ", switch.is_on() == truoc)
    ok("cài đặt riêng được đánh dấu để giao diện biết",
       any(m["rieng"] for m in cfg.danh_sach() if m["code"] == "sentiment_enabled"))

    print("== 8. API SYSTEM-001/002 + phân quyền ==")
    client = TestClient(app)

    def dang_nhap(u: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"username": u, "password": MK})
        assert r.status_code == 200, r.text[:200]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    ha = dang_nhap(f"{DAU}admin")
    hs = dang_nhap(f"{DAU}sale")

    r = client.get("/api/v1/settings", headers=ha)
    # CỐ Ý không khoá cứng SỐ nhóm: thêm một cài đặt mới là bài này đỏ oan
    # (đã xảy ra khi port C1-C4). Kiểm cấu trúc + các nhóm PHẢI có thay vì đếm.
    nhom = {n["ma"] for n in r.json().get("data", {}).get("nhom", [])} \
        if r.status_code == 200 else set()
    ok("SYSTEM-001 trả cài đặt theo nhóm",
       r.status_code == 200 and {"dong_bo", "quang_cao", "bot"} <= nhom,
       r.text[:200])
    r = client.get("/api/v1/settings?nhom=false", headers=ha)
    ok("SYSTEM-001 bản phẳng", r.status_code == 200
       and len(r.json()["data"]["items"]) >= 15)
    r = client.put("/api/v1/settings/ads_sync_interval", headers=ha,
                   json={"gia_tri": 7200})
    ok("SYSTEM-002 đổi 1 cài đặt", r.status_code == 200
       and cfg.so("ads_sync_interval") == 7200, r.text[:200])
    r = client.put("/api/v1/settings/ads_sync_interval", headers=ha,
                   json={"gia_tri": 5})
    ok("API chặn giá trị ngoài khoảng -> 422", r.status_code == 422)
    r = client.post("/api/v1/settings/ads_sync_interval/mac-dinh", headers=ha)
    ok("API trả về mặc định", r.status_code == 200
       and cfg.so("ads_sync_interval") == settings.ads_sync_interval)
    r = client.get("/api/v1/settings", headers=hs)
    ok("Sale không có user.manage -> 403", r.status_code == 403)

    print("== 9. Màn Cài đặt (form thật) ==")
    client.post("/dang-nhap", data={"username": f"{DAU}admin", "password": MK})
    r = client.get("/quan-tri/cai-dat")
    ok("màn mở được, có đủ 3 nhóm", r.status_code == 200
       and all(t in r.text for t in ("Đồng bộ Pancake", "Quảng cáo", "Bot Pancake")))

    # Bật bằng form (checkbox có gửi lên)
    r = client.post("/quan-tri/cai-dat", follow_redirects=False, data={
        "nhom": "dong_bo", "pos_sync_enabled": "on", "pos_sync_interval": "450",
        "sync_retry_enabled": "on", "sync_retry_interval": "300",
        "sync_retry_batch": "50", "sync_token_check_hours": "6",
        "crm_sync_enabled": "on"})
    ok("lưu form -> 303 về lại màn", r.status_code == 303)
    ok("form bật được công tắc + đổi nhịp",
       cfg.bat("pos_sync_enabled") and cfg.so("pos_sync_interval") == 450)

    # Bỏ tick: trình duyệt KHÔNG gửi ô đó -> phải hiểu là TẮT
    r = client.post("/quan-tri/cai-dat", follow_redirects=False, data={
        "nhom": "dong_bo", "pos_sync_interval": "450",
        "sync_retry_interval": "300", "sync_retry_batch": "50",
        "sync_token_check_hours": "6"})
    ok("bỏ tick checkbox -> lưu thành TẮT (không phải giữ nguyên)",
       not cfg.bat("pos_sync_enabled") and not cfg.bat("crm_sync_enabled"))

    r = client.post("/quan-tri/cai-dat", follow_redirects=False, data={
        "nhom": "dong_bo", "pos_sync_interval": "1"})
    ok("form nhập sai khoảng -> báo lỗi, không ghi",
       r.status_code == 303 and "error=" in r.headers["location"]
       and cfg.so("pos_sync_interval") == 450, r.headers.get("location", "")[:80])

    r = client.post("/quan-tri/cai-dat", follow_redirects=False,
                    data={"nhom": "dong_bo", "mac_dinh": "1"})
    ok("nút Trả về mặc định xoá hết ghi đè của nhóm",
       cfg.so("pos_sync_interval") == settings.pos_sync_interval
       and not cfg.da_doi("pos_sync_interval"))

    client.post("/dang-xuat")
    client.post("/dang-nhap", data={"username": f"{DAU}sale", "password": MK})
    r = client.get("/quan-tri/cai-dat")
    ok("Sale mở màn Cài đặt -> 403", r.status_code == 403)

    with pool.connection() as conn:
        don_dep(conn)

    print(f"\n=== KẾT QUẢ: {PASS} PASS · {FAIL} FAIL ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
