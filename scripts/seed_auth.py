"""Seed dữ liệu đăng nhập (A2 — docs/A2-DANG-NHAP.md mục 2.3).

Nạp vào schema `crm`: 9 vai trò + 11 quyền + ma trận quyền mặc định + 1 tài
khoản admin. Idempotent — chạy lại bao nhiêu lần cũng không tạo trùng, và
KHÔNG ghi đè mật khẩu admin đã có (muốn cấp lại: --reset-admin-password).

Chạy:  python scripts/seed_auth.py
Cần trong .env:  ADMIN_BOOTSTRAP_PASSWORD (mật khẩu admin lần đầu)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings          # noqa: E402
from app.core.security import hash_password   # noqa: E402
from app.db.client import get_pg_pool         # noqa: E402

# 9 vai trò — mục 3 BRD (phạm vi dữ liệu chi tiết sẽ siết ở A3/A5)
ROLES: list[tuple[str, str]] = [
    ("Chủ doanh nghiệp", "Toàn hệ thống: dashboard, doanh thu, Ads, KPI, audit"),
    ("Admin", "Toàn hệ thống: tài khoản, phân quyền, danh mục, automation, tích hợp"),
    ("Trưởng nhóm Sale", "Khách + nhân viên trong nhóm: chia lead, pipeline, coaching"),
    ("Sale", "Khách được giao: tư vấn, gọi, cập nhật trạng thái, tạo đơn"),
    ("Trưởng nhóm CSKH", "Khách đã bàn giao trong nhóm: điều phối, giám sát mốc chăm"),
    ("CSKH", "Khách được giao: xác nhận đơn, onboarding, chăm theo mốc, mua lại"),
    ("Marketing", "Dữ liệu nguồn + chỉ số được phép: campaign, chất lượng lead, ROAS"),
    ("Kế toán", "Đơn, thanh toán, doanh thu, đối soát"),
    ("Người chuyên môn", "Hồ sơ cần duyệt: kiến thức, nội dung, liệu trình, ngoại lệ"),
]

# 11 quyền nguyên tử — màn 67 (danh sách màn hình) + 2 quyền A5 (quản trị)
PERMISSIONS: list[tuple[str, str]] = [
    ("customer.view", "Xem khách"),
    ("customer.edit", "Sửa khách"),
    ("customer.view_phone", "Xem số điện thoại"),
    ("data.export", "Xuất Excel/dữ liệu"),
    ("call.listen", "Nghe ghi âm"),
    ("health.view", "Xem hồ sơ sức khỏe"),
    ("treatment.edit", "Sửa/chọn liệu trình"),
    ("revenue.view", "Xem doanh thu"),
    ("commission.edit", "Sửa hoa hồng"),
    ("content.approve", "Duyệt nội dung"),
    ("integration.manage", "Quản lý tích hợp"),
    # A5 — FR-002/003 cần quyền riêng cho quản trị tài khoản + xem audit (màn 65-67, 77)
    ("user.manage", "Quản lý nhân viên & phân quyền"),
    ("audit.view", "Xem nhật ký hoạt động"),
]

_ALL = [code for code, _ in PERMISSIONS]

# Ma trận mặc định (mục 2.3: Admin + Chủ DN full; còn lại tối thiểu, chỉnh ở A5)
ROLE_PERMS: dict[str, list[str]] = {
    "Chủ doanh nghiệp": _ALL,
    "Admin": _ALL,
    "Trưởng nhóm Sale": ["customer.view", "customer.edit", "customer.view_phone",
                          "call.listen", "health.view", "revenue.view"],
    "Sale": ["customer.view", "customer.edit", "customer.view_phone",
             "health.view", "treatment.edit"],
    "Trưởng nhóm CSKH": ["customer.view", "customer.edit", "customer.view_phone",
                          "call.listen", "health.view"],
    "CSKH": ["customer.view", "customer.edit", "customer.view_phone", "health.view"],
    "Marketing": ["customer.view"],
    "Kế toán": ["customer.view", "revenue.view", "data.export"],
    "Người chuyên môn": ["customer.view", "health.view", "treatment.edit",
                          "content.approve"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset-admin-password", action="store_true",
        help="Ghi đè mật khẩu admin bằng ADMIN_BOOTSTRAP_PASSWORD trong .env",
    )
    args = parser.parse_args()

    pool = get_pg_pool()
    with pool.connection() as conn:
        # --- vai trò ---
        for name, desc in ROLES:
            conn.execute(
                "insert into crm.roles (name, description) values (%s, %s) "
                "on conflict (name) do nothing",
                (name, desc),
            )
        # --- quyền ---
        for code, name in PERMISSIONS:
            conn.execute(
                "insert into crm.permissions (code, name) values (%s, %s) "
                "on conflict (code) do nothing",
                (code, name),
            )
        # --- ma trận vai trò ↔ quyền ---
        so_gan = 0
        for role_name, perm_codes in ROLE_PERMS.items():
            for code in perm_codes:
                cur = conn.execute(
                    """
                    insert into crm.role_permissions (role_id, permission_id)
                    select r.id, p.id
                      from crm.roles r, crm.permissions p
                     where r.name = %s and p.code = %s
                    on conflict do nothing
                    """,
                    (role_name, code),
                )
                so_gan += cur.rowcount

        # --- tài khoản admin ---
        admin = conn.execute(
            "select id, password_hash from crm.users where username = 'admin'"
        ).fetchone()
        if admin is None:
            if not settings.admin_bootstrap_password:
                sys.exit(
                    "LOI: thieu ADMIN_BOOTSTRAP_PASSWORD trong .env — "
                    "khong tao duoc tai khoan admin."
                )
            conn.execute(
                """
                insert into crm.users (name, email, username, password_hash, role_id)
                select %s, %s, 'admin', %s, r.id
                  from crm.roles r where r.name = 'Admin'
                """,
                (
                    "Quản trị hệ thống",
                    settings.admin_bootstrap_email,
                    hash_password(settings.admin_bootstrap_password),
                ),
            )
            print("[seed] DA TAO tai khoan 'admin' — mat khau lay tu "
                  "ADMIN_BOOTSTRAP_PASSWORD trong .env. Dang nhap xong hay DOI NGAY "
                  "(POST /api/v1/auth/change-password).")
        elif args.reset_admin_password:
            if not settings.admin_bootstrap_password:
                sys.exit("LOI: thieu ADMIN_BOOTSTRAP_PASSWORD trong .env.")
            conn.execute(
                "update crm.users set password_hash = %s, failed_login_count = 0, "
                "locked_until = null where id = %s",
                (hash_password(settings.admin_bootstrap_password), admin["id"]),
            )
            print("[seed] DA DAT LAI mat khau admin theo .env.")
        else:
            print("[seed] Tai khoan 'admin' da co — giu nguyen mat khau "
                  "(muon cap lai: --reset-admin-password).")

        # --- tổng kết ---
        so = conn.execute(
            "select (select count(*) from crm.roles) as roles, "
            "(select count(*) from crm.permissions) as perms, "
            "(select count(*) from crm.role_permissions) as grants, "
            "(select count(*) from crm.users) as users"
        ).fetchone()
    print(f"[seed] Xong: {so['roles']} vai tro · {so['perms']} quyen · "
          f"{so['grants']} luot gan quyen (+{so_gan} moi) · {so['users']} tai khoan.")


if __name__ == "__main__":
    main()
