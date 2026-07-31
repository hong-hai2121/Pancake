# A2 — ĐĂNG NHẬP: MÔ TẢ TRƯỚC KHI LÀM

> Đặc tả gốc: FR-001 (đặc tả chức năng) · màn 1 (danh sách màn hình) ·
> AUTH-001…006 (danh sách API). Trạng thái: **✅ ĐÃ LÀM XONG 31/07/2026 —
> nghiệm thu 27/27 PASS** (đủ 8 điểm mục 5).
>
> 2 điều chỉnh nhỏ so với mô tả khi code thật:
> 1. Danh sách miễn đăng nhập thêm `/api/v1/auth/forgot-password` (người quên
>    mật khẩu đương nhiên chưa đăng nhập được) và `/favicon.ico`.
> 2. Web có thêm tự làm mới ngầm: access hết hạn nhưng cookie refresh còn sống
>    → middleware phát access mới ngay trong request, người dùng không bị đá
>    ra mỗi 30 phút.

## 1. Phạm vi

Làm xong A2 thì:

- Toàn bộ web hiện tại (37 route: `/`, `/tin-nhan`, `/khach-hang`, `/pancake/*`,
  `/data/*`, `/cam-xuc/*`) **bắt buộc đăng nhập mới xem được**. Chưa đăng nhập →
  đá về màn `/dang-nhap`.
- Có 6 API xác thực dưới `/api/v1/auth/*` theo đúng mã AUTH-001…006.
- Có sẵn 9 vai trò + 11 quyền + 1 tài khoản admin trong DB (seed).
- Đăng nhập sai 5 lần liên tiếp → khoá tạm 15 phút (FR-001).
- Mỗi lần đăng nhập/đăng xuất/sai mật khẩu đều ghi `crm.audit_logs` kèm IP +
  thiết bị (màn 1: "ghi nhận thiết bị và lịch sử đăng nhập").

**KHÔNG nằm trong A2** (để bước sau, ghi rõ cho khỏi lẫn):

| Việc | Để ở |
|---|---|
| Chặn từng route theo quyền (`require_permission("customer.view")`) | A3 — A2 mới chặn "đã đăng nhập hay chưa", quyền đã nằm sẵn trong token |
| Màn quản lý nhân viên, tạo/khoá tài khoản, reset mật khẩu hộ | A5 |
| Quên mật khẩu tự động qua email (AUTH-006) | A5 — chưa có hạ tầng gửi mail. Màn đăng nhập ghi "liên hệ Admin". Endpoint vẫn tạo nhưng trả `NOT_IMPLEMENTED` kèm hướng dẫn |
| Dashboard theo vai trò sau đăng nhập (màn 2) | B11 — tạm thời ai đăng nhập xong cũng về `/` |

## 2. Thay đổi database (bảng rỗng nên ALTER thoải mái)

### 2.1 Sửa `crm.users` — thêm 3 cột

| Cột | Kiểu | Vì sao |
|---|---|---|
| `username` | text, UNIQUE | AUTH-001 đăng nhập bằng `username` (vd `sale01`); email giữ nguyên làm liên lạc. Cho phép đăng nhập bằng **username hoặc email** |
| `failed_login_count` | int, default 0 | Đếm số lần sai liên tiếp; đăng nhập đúng thì reset về 0 |
| `locked_until` | timestamptz, null | Sai lần thứ 5 → đặt = now() + 15 phút. Hết giờ tự mở, không cần cron |

### 2.2 Bảng mới `crm.user_sessions` — phiên đăng nhập

Mỗi lần đăng nhập tạo 1 dòng. Vừa là chỗ **thu hồi refresh token khi logout**,
vừa chính là "lịch sử đăng nhập + thiết bị" mà màn 1 đòi.

| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `user_id` | FK → users, NN |
| `refresh_token_hash` | SHA-256 của refresh token — DB **không giữ token thật** |
| `ip_address` (inet) · `user_agent` | thiết bị đăng nhập |
| `expires_at` | hết hạn refresh |
| `revoked_at` | null = còn hiệu lực; logout/đổi mật khẩu thì đặt giá trị |
| `last_used_at` · `created_at` | |

Cập nhật cả `scripts/init_crm.sql` (nguồn sự thật của schema) chứ không chỉ ALTER tay.

### 2.3 Seed (script riêng `scripts/seed_auth.py`, chạy lại không tạo trùng)

- **9 vai trò** (mục 3 BRD): Chủ doanh nghiệp, Admin, Trưởng nhóm Sale, Sale,
  Trưởng nhóm CSKH, CSKH, Marketing, Kế toán, Người chuyên môn
- **11 quyền** (màn 67): `customer.view`, `customer.edit`, `customer.view_phone`,
  `data.export`, `call.listen`, `health.view`, `treatment.edit`, `revenue.view`,
  `commission.edit`, `content.approve`, `integration.manage`
- Gán quyền → vai trò theo ma trận mặc định (Admin + Chủ DN: tất cả; còn lại
  cấp tối thiểu, chỉnh lại được ở A5)
- **1 tài khoản `admin`** — mật khẩu lấy từ biến `.env` `ADMIN_BOOTSTRAP_PASSWORD`,
  không hard-code. Seed xong in nhắc đổi mật khẩu.

## 3. Luồng hoạt động

### 3.1 Hai cách xác thực, chung một bộ token

| | Web (trình duyệt) | API (gọi thẳng) |
|---|---|---|
| Token để đâu | Cookie `HttpOnly` + `SameSite=Lax` (JS không đọc được) | Header `Authorization: Bearer <access>` |
| Chưa đăng nhập | Redirect 302 → `/dang-nhap` | JSON 401 `UNAUTHORIZED` |
| Kiểm tra ở đâu | **1 middleware duy nhất** trên app — không phải sửa 37 route | cùng middleware đó |

Danh sách miễn kiểm tra: `/dang-nhap`, `/api/v1/auth/login`, `/api/v1/auth/refresh`,
`/health`. (`/docs`, `/redoc`, `/poller` cũng bị khoá theo — khớp mục "việc lẻ"
trong TIEN-DO.md.)

### 3.2 Token

- **Access token**: JWT ký HS256 bằng `JWT_SECRET` trong `.env`, sống **30 phút**.
  Payload: `user_id`, `role`, danh sách quyền — `GET /auth/me` và phân quyền A3
  đọc thẳng từ đây, không phải query DB mỗi request.
- **Refresh token**: chuỗi ngẫu nhiên 256-bit, sống **14 ngày**, lưu SHA-256 trong
  `user_sessions`. Ô "Ghi nhớ đăng nhập" (màn 1): tick → cookie sống 14 ngày;
  không tick → cookie phiên, đóng trình duyệt là hết.
- Đổi mật khẩu (AUTH-005) → thu hồi **mọi** session khác của user đó.

### 3.3 Luồng đăng nhập (FR-001)

```
nhập username/email + mật khẩu
 → tài khoản tồn tại?          sai → đếm +1, báo lỗi CHUNG "sai tài khoản hoặc mật khẩu"
 → đang bị khoá tạm?           locked_until > now() → báo còn phải chờ mấy phút
 → status = active?            inactive/suspended (nghỉ việc) → từ chối
 → mật khẩu đúng? (bcrypt)     sai lần 5 → locked_until = now() + 15'
 → phát access + refresh, tạo user_sessions, reset đếm,
   cập nhật users.last_login_at, ghi audit_logs(action='login')
```

Sai ở bước nào cũng ghi `audit_logs(action='login_failed')` kèm IP — không ghi mật khẩu.

## 4. File đụng tới

| File | Mới/Sửa | Nội dung |
|---|---|---|
| `app/core/security.py` | MỚI | băm bcrypt · phát/kiểm JWT · sinh refresh token |
| `app/core/deps.py` | MỚI | `get_current_user()` đọc Bearer hoặc cookie |
| `app/core/config.py` | sửa | thêm `jwt_secret`, TTL token, `admin_bootstrap_password` |
| `app/schemas/auth.py` | MỚI | Pydantic: LoginIn, TokenOut, MeOut, ChangePasswordIn |
| `app/services/auth_service.py` | MỚI | toàn bộ luồng mục 3.3 — **không import FastAPI**, test được chay |
| `app/db/repositories/auth_repo.py` | MỚI | SQL vào `crm.users` / `user_sessions` / roles / permissions (psycopg, đúng nếp repositories hiện có) |
| `app/api/v1/auth.py` | MỚI | 6 endpoint AUTH-001…006 |
| `app/web/routes/auth.py` + `views/auth.py` | MỚI | màn `/dang-nhap` + nút đăng xuất trên shell |
| `app/main.py` | sửa | gắn middleware khoá + 2 router mới |
| `scripts/init_crm.sql` | sửa | mục 2.1 + 2.2 |
| `scripts/seed_auth.py` | MỚI | mục 2.3 |
| `requirements.txt` | sửa | thêm `bcrypt`, `pyjwt` (2 gói nhỏ, không kéo theo gì) |
| `.env` / `.env.example` | sửa | `JWT_SECRET`, `ADMIN_BOOTSTRAP_PASSWORD` |

## 5. Xong khi (nghiệm thu)

1. Mở bất kỳ URL web nào khi chưa đăng nhập → về `/dang-nhap`; gọi API không token → 401.
2. Đăng nhập admin thành công → về `/`, thấy tên + nút đăng xuất trên menu.
3. `GET /api/v1/auth/me` trả đúng tên, vai trò, 11 quyền của admin.
4. Sai mật khẩu 5 lần → lần 6 báo khoá; đợi hết 15 phút (hoặc sửa `locked_until` trong DB) → vào lại được.
5. Logout → refresh token cũ không đổi được access mới.
6. Đổi mật khẩu → session ở máy khác văng ra.
7. `select action, count(*) from crm.audit_logs group by 1` thấy đủ `login`, `login_failed`, `logout`.
8. Bot RAG, poller, sentiment worker chạy như cũ — không đụng gì tới `public.*` / `watcher.*`.

## 6. Quyết định đã chốt trong mô tả này (nói nếu muốn khác)

1. Đăng nhập bằng **username hoặc email** (đặc tả chỉ nói username; thêm email vì đằng nào cột cũng UNIQUE).
2. Khoá tạm **5 lần / 15 phút** — đặc tả chỉ ghi "sai quá số lần quy định", con số lấy từ ghi chú A2 trong lộ trình.
3. Access **30 phút** / refresh **14 ngày**.
4. Refresh lưu **băm** trong DB (lộ DB cũng không dùng lại được token).
5. Dùng `bcrypt` + `pyjwt` trực tiếp, không qua passlib (passlib ngừng bảo trì).
6. Truy cập DB bằng psycopg thẳng theo nếp `repositories/` hiện có — **chưa** đưa SQLAlchemy/Alembic vào (ghi trong kế hoạch bước 2 nhưng chưa cần cho A2, tránh nở phạm vi).
