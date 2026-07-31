# TIẾN ĐỘ CRM — mở file này khi quên đang làm tới đâu

> Chi tiết từng bước (làm gì, vì sao, "xong khi" nào) xem
> [THU-TU-TRIEN-KHAI-CRM.md](THU-TU-TRIEN-KHAI-CRM.md).
> Ký hiệu: ✅ xong · 🔨 đang làm · ⬜ chưa làm.
> **Quy ước cập nhật:** xong bước nào thì đổi ký hiệu + thêm 1 dòng vào Nhật ký cuối file.

## Phần A — Nền tảng

| | Bước | Nội dung một dòng |
|---|---|---|
| ✅ | **A1** | Nạp schema `crm` vào Postgres — *58 bảng đã có trong DB (kiểm 31/07/2026)* |
| ✅ | **A2** | **Đăng nhập** — JWT, 6 API `/api/v1/auth/*`, màn `/dang-nhap`, khoá toàn bộ web, seed 9 vai trò + 11 quyền + admin — *xong 31/07, nghiệm thu 27/27 ([A2-DANG-NHAP.md](A2-DANG-NHAP.md))* |
| ✅ | **A3** | Khung API chuẩn — bao `{success,data,message}`, 12+5 mã lỗi (`core/errors.py`), phân trang trần 100, `require_permission` — *xong 31/07* |
| ✅ | **A4** | Audit log — mọi thao tác ghi lưu ai/làm gì/**chỉ trường đổi** cũ→mới; API AUDIT-001/002 + màn Nhật ký — *xong 31/07* |
| ✅ | **A5** | Quản lý người dùng — USER-001…006 + ROLE + TEAM + reset mật khẩu; 3 màn Quản trị; khoá đòi chuyển khách trước (FR-002); quyền nay 13 (thêm `user.manage`, `audit.view`) — *xong 31/07, nghiệm thu 30/30* |

## Phần B — 11 lát cắt nghiệp vụ (làm theo thứ tự)

| | Lát | Nội dung một dòng |
|---|---|---|
| ✅ | **B1** | Khách hàng 360° — luật + 14 API xong, 38/38 PASS ([B1-KHACH-HANG.md](B1-KHACH-HANG.md)); *màn 8/9/10 chờ khung template B11* |
| ✅ | **B2** | Nối Pancake vào CRM — `crm_sync` 11/11 PASS; công tắc `CRM_SYNC_ENABLED` mặc định **TẮT**; backfill kho cũ: `scripts/backfill_crm_tu_watcher.py` |
| ✅ | **B3** | Lead & pipeline Sale — luật 25/25 + API 16/16 PASS ([B3-LEAD-PIPELINE.md](B3-LEAD-PIPELINE.md)); *riêng Kanban màn 11 chờ khung template B11* |
| ⬜ | **B4** | Công việc — task engine chung, việc hôm nay / quá hạn |
| ⬜ | **B5** | Hồ sơ tư vấn — phiếu triệu chứng, sàng lọc an toàn, chặn + chuyển chuyên môn |
| ⬜ | **B6** | Sản phẩm & liệu trình — danh mục, versioning giá, rule engine đề xuất |
| ⬜ | **B7** | Đơn hàng — 11 trạng thái, ánh xạ Pancake→CRM, đơn đầu/mua lại |
| ⬜ | **B8** | Bàn giao Sale→CSKH — tự động khi giao thành công, phiếu bàn giao |
| ⬜ | **B9** | Chăm sóc 11 bước — mốc 4/10/15/20/25/28 theo ngày bắt đầu thật, automation |
| ⬜ | **B10** | Mua lại & khách ngủ — cơ hội ngày 20, lý do ngày 25, cứu ngày 28, tái kích hoạt |
| ⬜ | **B11** | Báo cáo cơ bản — dashboard + báo cáo Sale/CSKH, mọi số bấm ra danh sách |

## Phần C — Giai đoạn sau (chưa đụng tới khi B chưa xong)

| | Giai đoạn | Nội dung một dòng |
|---|---|---|
| ⬜ | **C-MVP3** | Tổng đài — ghi âm, transcript, AI chấm cuộc gọi |
| ⬜ | **C-MVP4** | Kho kiến thức — duyệt nội dung, cây kịch bản, nâng cấp RAG hiện có |
| ⬜ | **C-MVP5** | Facebook Ads — attribution, ROAS/LTV, insight Marketing |

## Việc lẻ ngoài lộ trình (ghi để khỏi quên)

- ⬜ Xoá tab **Thử API** (`/data/thu-api`) trước khi đưa web ra Internet — đang phơi token Pancake (từ A2 phải đăng nhập mới xem được, nhưng vẫn nên xoá)
- ✅ Tắt `/docs` `/redoc`, chặn `/poller` — *làm luôn trong A2 (middleware khoá + docs_url=None)*
- ⬜ Đưa lên domain: Cloudflare Tunnel + Access (đã bàn 31/07, làm sau A2)
- ⬜ Commit đợt tái cấu trúc thư mục (đang nằm ở working tree, chưa commit)

---

## Nhật ký

| Ngày | Việc |
|---|---|
| 31/07/2026 | Đọc 3 PDF đặc tả; tái cấu trúc thư mục app (core/ai/web/integrations/db-repositories), route giữ nguyên 43/43; chuyển tài liệu vào `docs/` |
| 31/07/2026 | Dựng `scripts/init_crm.sql` và nạp vào Postgres — schema `crm` 58 bảng · 99 FK; sinh ERD mermaid; thêm BRD chi tiết |
| 31/07/2026 | Viết `THU-TU-TRIEN-KHAI-CRM.md` (lộ trình A→B→C) và file tiến độ này. Bước kế: **A2 — Login** |
| 31/07/2026 | Viết mô tả A2 (`A2-DANG-NHAP.md`): 6 API auth, khoá 37 route web bằng 1 middleware, sửa `users` + bảng `user_sessions`, seed 9 vai trò + 11 quyền. Chờ duyệt |
| 31/07/2026 | **A2 XONG** — schema 59 bảng (`users` +3 cột, thêm `user_sessions`); `core/security` + `services/auth_service` + `api/v1/auth` + màn `/dang-nhap` + middleware khoá; seed 9 vai trò · 11 quyền · admin; tắt `/docs`; nghiệm thu **27/27 PASS** (khoá 5 lần sai, thu hồi phiên, audit có IP, worker chạy như cũ). Bước kế: **A3** |
| 31/07/2026 | Đọc BRD mục 14 → seed danh mục (`scripts/seed_danh_muc.py`, chạy lại được): pipeline Bán mới 13 giai đoạn, 9 lý do chưa mua, bảng mới `ref_codes` 78 mã (C01-C09 · CS01-CS11 · RS01-RS12 · AU01-AU13 · 7 bộ giá trị phiếu chăm). **Sửa CHECK `care_plan_steps.step_code`**: bộ D1/D3/D7 đoán trước đây SAI, BRD chuẩn là CS01-CS11 mốc 4/10/15/20/25/28 tính từ ngày BẮT ĐẦU DÙNG thật. DB nay 60 bảng, ERD sinh lại khớp 60/60 |
| 31/07/2026 | **A3+A4+A5 XONG** — khung API chuẩn (`core/errors` + `core/response` + `require_permission` + exception handler chung, auth refactor theo); audit mở rộng (list/get + API + màn 77, ghi CHỈ trường đổi); quản lý nhân viên đủ USER/ROLE/PERMISSION/TEAM + reset MK + chuyển khách (customer_assignments đóng dòng cũ, giữ lịch sử) + luật FR-002 chặn khoá khi còn giữ khách; web 3 màn Quản trị + menu ẩn theo quyền; quyền 11→13. Nghiệm thu **30/30 PASS**, chạy lại bộ A2 **27/27**. Bước kế: **B1 — Khách hàng 360°** |
| 31/07/2026 | **B3 tầng luật xong** — `lead_repo` + `lead_service` (chia vòng tròn theo tải, 5 luật chặn FR-040, lịch sử FR-041, SLA 5'/15', hàng đợi, quá hạn, nóng); `leads` +5 cột, `lead_stage_history` +note; sửa trigger `check_lead_stage_pipeline` thiếu tiền tố `crm.` (vỡ khi gọi từ app); kiểm `scripts/thu_b3.py` **25/25 PASS**. API LEAD-001…011 chờ A3 nối |
| 31/07/2026 | **B3 XONG (trừ Kanban)** — nối API lên khung A3: `api/v1/leads.py` 15 endpoint (PIPELINE-001…004 · LEAD-001…011 · +/leads/queue), quyền customer.view/edit + user.manage cho cấu trúc pipeline; kiểm `scripts/thu_b3_api.py` **16/16 PASS**. Vá kèm A2: cột inet nhận chuỗi không phải IP → login 500 + audit rơi lặng lẽ, nay lọc ở biên repo (`_ip_hop_le`). Bước kế: **B1 — Khách hàng 360°** |
| 31/07/2026 | **B1 XONG (trừ màn)** — chuẩn hoá SĐT (`services/phone.py`); chống trùng 4 bậc FR-011 (SĐT ra nhiều khách thì KHÔNG tự nhận — nhà chung số); `upsert_from_source()` chờ sẵn cho B2, đồng bộ lại không trùng khách/lead; gộp FR-022 dồn 20 bảng 1 transaction, hồ sơ phụ status=merged không xoá; xoá mềm; tag tìm-hoặc-tạo; phân công 3 vai riêng có lịch sử; 14 API + schema `customers` +3 cột +unique external. Kiểm `scripts/thu_b1.py` **38/38 PASS**. Bước kế: **B2** |
| 31/07/2026 | **B2 XONG** — `integrations/pancake/crm_sync.py`: mỗi hội thoại poller → khách (4 bậc chống trùng) + định danh + `crm.conversations` + lead tự động; tự tạo `crm.pages`; lỗi nuốt từng dòng, không vỡ luồng bot. Công tắc `CRM_SYNC_ENABLED` mặc định **TẮT** (bật mới sinh dữ liệu thật); kho cũ 1.5k hội thoại: `scripts/backfill_crm_tu_watcher.py` (idempotent). Kiểm `scripts/thu_b2.py` **11/11 PASS**; chạy lại cả 4 bộ B1/B2/B3/B3-API đều xanh (90 PASS tổng). Bước kế: **B4 — Công việc** |
| 31/07/2026 | **Bộ màn CRM khung (tạm)** — 8 màn `/crm/*`: Tổng quan (màn 4) · Khách hàng (8) · Pipeline Kanban 13 cột (11) · Công việc (12+26) · Đơn hàng (21) · Chăm sóc C01-C09 (26-27) · Mua lại (39-40) · Sản phẩm & liệu trình (42+44). Số liệu ĐẾM THẬT từ schema `crm`, mỗi màn ghi rõ lát cắt nào (B1…B11) đổ dữ liệu; menu chia 2 nhóm **CRM / Bot Pancake**, đăng nhập xong vào thẳng `/crm/tong-quan` (màn bot cũ giữ nguyên URL). Smoke 8/8 · regression A2 27/27 + A3-5 30/30 |
