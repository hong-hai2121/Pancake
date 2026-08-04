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
    ("Trưởng nhóm Sale",
     "Khách + nhân viên trong nhóm: chia khách tiềm năng, pipeline, coaching"),
    ("Sale", "Khách được giao: tư vấn, gọi, cập nhật trạng thái, tạo đơn"),
    ("Trưởng nhóm CSKH", "Khách đã bàn giao trong nhóm: điều phối, giám sát mốc chăm"),
    ("CSKH", "Khách được giao: xác nhận đơn, onboarding, chăm theo mốc, mua lại"),
    ("Marketing",
     "Dữ liệu nguồn + chỉ số được phép: campaign, chất lượng khách tiềm năng, ROAS"),
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
    # BRD mục 4 (nguồn quảng cáo) — báo cáo chi phí/ROAS/LTV theo campaign·adset·ad
    # (màn 7, 53-56, 62). Marketing sống bằng màn này nên phải có quyền riêng,
    # không gộp vào revenue.view (doanh thu toàn công ty).
    ("ads.view", "Xem báo cáo quảng cáo (chi phí, ROAS, LTV)"),
    # B7 — đơn hàng (màn 21-23): xem tách khỏi sửa vì Kế toán/Marketing chỉ cần đọc
    ("order.view", "Xem đơn hàng"),
    ("order.edit", "Tạo/sửa đơn & chuyển trạng thái"),
    # C1 — voucher (màn /crm/voucher). Tặng voucher = phát tiền: quyền RIÊNG,
    # cấp cho CSKH chứ không phải ai xem được khách cũng tặng được.
    ("voucher.grant", "Tặng voucher cho khách"),
    # C2 — lương. TÁCH BA mức vì lộ lương là chuyện lớn:
    #   payroll.view_own  — ai cũng có, chỉ xem thu nhập CỦA MÌNH
    #   payroll.manage    — bảng lương cả đội + chốt kỳ + cấu hình bậc
    #   payroll.approve   — duyệt/bác thưởng chăm sóc ở màn Đối soát
    ("payroll.view_own", "Xem thu nhập của chính mình"),
    ("payroll.manage", "Xem bảng lương cả đội & chốt kỳ"),
    ("payroll.approve", "Duyệt/bác thưởng chăm sóc"),
    # C3 — chiến dịch + mẫu tin. Gộp MỘT quyền vì cùng một việc: người dựng
    # chiến dịch cũng là người soạn nội dung tầng 1. Bấm "Chạy đợt" là bắn tin
    # tới hàng nghìn khách thật nên KHÔNG mở cho nhân viên thường.
    ("campaign.manage", "Tạo & chạy chiến dịch, soạn mẫu tin"),
    # A5 — FR-002/003 cần quyền riêng cho quản trị tài khoản + xem audit (màn 65-67, 77)
    ("user.manage", "Quản lý nhân viên & phân quyền"),
    ("user.manage_team", "Quản lý tài khoản trong đội (trưởng nhóm)"),
    ("audit.view", "Xem nhật ký hoạt động"),
    # Khu Bot Pancake (điều khiển bot, tin nhắn, dữ liệu bot, cảm xúc) — chỉ cấp
    # toàn hệ thống: quyền này KHÔNG nằm trong danh sách của vai trò nào bên dưới,
    # chỉ Chủ DN + Admin nhận qua _ALL.
    ("bot.view", "Xem khu Bot Pancake (điều khiển bot, tin nhắn, dữ liệu bot)"),
]

_ALL = [code for code, _ in PERMISSIONS]

# Ma trận mặc định (mục 2.3: Admin + Chủ DN full; còn lại tối thiểu, chỉnh ở A5)
ROLE_PERMS: dict[str, list[str]] = {
    "Chủ doanh nghiệp": _ALL,
    "Admin": _ALL,
    # Trưởng nhóm có payroll.approve (duyệt thưởng đội mình) nhưng KHÔNG có
    # payroll.manage — chốt kỳ lương là việc của Kế toán/Admin.
    "Trưởng nhóm Sale": ["customer.view", "customer.edit", "customer.view_phone",
                          "call.listen", "health.view", "revenue.view",
                          "user.manage_team", "order.view", "order.edit",
                          "payroll.view_own", "payroll.approve"],
    "Sale": ["customer.view", "customer.edit", "customer.view_phone",
             "health.view", "treatment.edit", "order.view", "order.edit",
             "payroll.view_own"],
    "Trưởng nhóm CSKH": ["customer.view", "customer.edit", "customer.view_phone",
                          "call.listen", "health.view", "user.manage_team",
                          "order.view", "order.edit", "voucher.grant",
                          "payroll.view_own", "payroll.approve"],
    # CSKH có order.edit vì bước CS01 là "Xác nhận đơn" (đổi trạng thái đơn);
    # voucher.grant vì tặng voucher là việc chăm khách cũ (C1), không phải Sale
    "CSKH": ["customer.view", "customer.edit", "customer.view_phone", "health.view",
             "order.view", "order.edit", "voucher.grant", "payroll.view_own"],
    # Marketing: xem khách (chất lượng lead) + báo cáo quảng cáo (mục 4)
    # + dựng chiến dịch/mẫu tin (C3) — đúng nghề của họ
    "Marketing": ["customer.view", "ads.view", "payroll.view_own",
                  "campaign.manage"],
    # Kế toán là người CHỐT KỲ LƯƠNG → payroll.manage
    "Kế toán": ["customer.view", "revenue.view", "data.export", "order.view",
                "payroll.view_own", "payroll.manage", "payroll.approve"],
    "Người chuyên môn": ["customer.view", "health.view", "treatment.edit",
                          "content.approve", "payroll.view_own"],
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
