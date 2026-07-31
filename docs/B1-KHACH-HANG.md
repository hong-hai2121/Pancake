# B1 — KHÁCH HÀNG 360°

> Đặc tả gốc: FR-011 (chống trùng) · FR-020/021/022/023 · BRD mục 5-6 ·
> API CUSTOMER-001…012 + IDENTITY-001/002 · màn 8/9/10.
> Trạng thái: **✅ luật + API xong 31/07, kiểm 38/38 PASS (`scripts/thu_b1.py`)**
> — màn 8/9/10 chờ khung template (B11/Bước 4), như Kanban của B3.

## 1. File

| File | Nội dung |
|---|---|
| `app/services/phone.py` | Chuẩn hoá SĐT Việt Nam — MỌI chỗ ghi số phải đi qua đây |
| `app/db/repositories/customer_repo.py` | SQL: CRUD, 4 phép tìm chống trùng, gộp, tag, phân công, timeline |
| `app/services/customer_service.py` | Luật FR-011/020/022/023 + phân công |
| `app/schemas/customer.py` · `app/api/v1/customers.py` | 14 endpoint (12 CUSTOMER + 2 IDENTITY) |
| `scripts/thu_b1.py` | 38 kiểm thử, tự dọn |

## 2. Schema thêm (đã cập nhật cả `init_crm.sql`)

- `customers` + `source` (FR-020) · `merged_into_id` (FR-022) · `deleted_at`
  (CUSTOMER-005 xoá mềm) · status thêm giá trị **`merged`**
- `customer_identities` + unique `(platform, external_customer_id)` — FR-022
  "external ID không được trùng sau hợp nhất" chặn từ gốc

## 3. Luật chính

**Chống trùng FR-011** — 4 bậc đúng thứ tự: external_customer_id → PSID →
SĐT chuẩn hoá → page+conversation. Điểm tinh: SĐT tra ra **nhiều** khách sống
(nhà chung số) thì KHÔNG tự nhận — tạo hồ sơ mới, để màn nghi trùng (CUSTOMER-006)
xử lý bằng mắt người, tránh gộp bừa hai người nhà.

**`upsert_from_source()`** — cửa duy nhất cho B2 đổ khách từ Pancake vào: tự
chuẩn hoá SĐT, bồi thông tin thiếu (không đè thông tin đã có), bảo đảm dòng định
danh, và "tạo lead nếu khách chưa có pipeline" — đồng bộ lại bao nhiêu lần vẫn
1 khách + 1 lead mở (tiêu chí nghiệm thu FR-011, đã kiểm).

**Gộp FR-022** — một transaction dồn 20 bảng con về hồ sơ chính; bảng có ràng
buộc duy nhất theo khách (tags, symptoms, identities, reactivation_members,
assignments đang mở) xử lý riêng bỏ-dòng-trùng; hồ sơ phụ **không xoá**:
`status='merged'` + `merged_into_id`, vẫn xem được (không mất lịch sử).

**Phân công** — Sale/CSKH/chuyên môn là 3 ownership riêng (BRD mục 6); thay
người đang giữ bắt buộc lý do; đóng dòng cũ + mở dòng mới, lịch sử giữ nguyên.

**Tạo thủ công FR-020** — thiếu tên / thiếu (SĐT hoặc định danh) / thiếu nguồn
đều chặn; nghi trùng trả `DUPLICATE_CUSTOMER` **kèm danh sách ứng viên** trong
`errors.candidates`, client gửi lại `force=true` nếu chọn "vẫn tạo mới".

## 4. Quyền

Đọc `customer.view` · ghi `customer.edit` · **gộp = `user.manage`** (FR-022
ghi "Admin, quản lý có quyền" — gộp sai là dồn nhầm lịch sử hai con người).

## 5. Chờ / hoãn

| Việc | Chờ |
|---|---|
| Màn 8 (danh sách) · 9 (hồ sơ 360°) · 10 (hợp nhất) | khung template B11/Bước 4 — API + timeline đã đủ dữ liệu |
| Bộ lọc màn 8 phần chưa có dữ liệu (repurchase_due, sleeping, warning) | B9/B10 |
| ATTRIBUTION-001/002 | C-MVP5 (Facebook Ads) |
| Tab hồ sơ 360° phần tư vấn/liệu trình/chăm sóc | B5-B9 — timeline tự nở khi bảng có dữ liệu |
| "Tạo tag tự động theo luật" (FR-023) | Phần C automation |
