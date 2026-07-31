# B3 — LEAD & PIPELINE SALE

> Đặc tả gốc: FR-030/031/032 (chia lead, chuyển người, hàng đợi) ·
> FR-040/041/042 (pipeline, lịch sử, SLA) · BRD mục 6-7 ·
> API PIPELINE-001…004 + LEAD-001…011 · màn 11 (Kanban), 12 (bảng việc Sale).
>
> Trạng thái: **✅ tầng luật (25/25 PASS) + tầng API (16/16 PASS) XONG 31/07** —
> còn Kanban màn 11 chờ khung template (B11/Bước 4). Chi tiết phần chờ ở mục 5.
>
> API: `app/api/v1/leads.py` — 15 endpoint (PIPELINE-001…004, LEAD-001…011,
> thêm `/leads/queue` cho FR-032). Quyền: đọc `customer.view` · ghi
> `customer.edit` · sửa cấu trúc pipeline `user.manage`. Kiểm: `scripts/thu_b3_api.py`.
> Sửa kèm 2 chỗ của A2 khi nối: `ip_address` kiểu inet nhận chuỗi không phải IP
> (TestClient/proxy) làm login nổ 500 và audit rơi lặng lẽ — nay lọc ở biên repo.

## 1. Đã làm — tầng luật (không đụng file của A3)

| File | Nội dung |
|---|---|
| `app/db/repositories/lead_repo.py` | SQL thuần vào `crm.leads` + pipeline; mọi câu ghi rõ tiền tố `crm.` |
| `app/services/lead_service.py` | Toàn bộ luật bên dưới; không import FastAPI — API sau này chỉ gọi xuống |
| `scripts/thu_b3.py` | 25 kiểm thử chạy trên DB thật, tự dọn sạch (`python scripts/thu_b3.py`) |
| `scripts/init_crm.sql` | `leads` +5 cột, `lead_stage_history` +1 cột (mục 2) |

## 2. Thay đổi database

`crm.leads` thêm 5 cột (bảng đang rỗng):

| Cột | Vì sao |
|---|---|
| `temperature` (nong/am/lanh) | BRD "gắn lead score nóng/ấm/lạnh"; lọc màn 8/12; LEAD-009 `/leads/hot` |
| `stage_entered_at` | Kanban hiển thị "số ngày ở trạng thái" — không phải join lịch sử mỗi lần vẽ |
| `first_contact_at` | FR-042: đo "tương tác đầu trong 15 phút"; chỉ ghi lần đầu, gọi lặp không đè |
| `sla_due_at` | FR-030 "tạo thời hạn phản hồi"; quá hạn = `sla_due_at < now()` và chưa có tương tác đầu |
| `closed_at` | Vào giai đoạn `is_closed` thì đóng dấu; rời ra thì xoá (cho phép mở lại) |

`crm.lead_stage_history` thêm `note` — FR-041 đòi cả "lý do" lẫn "ghi chú".

Sửa kèm một lỗi có sẵn: hàm trigger `crm.check_lead_stage_pipeline()` gọi
`pipeline_stages` **không có tiền tố schema** — chạy từ psql (đã set search_path)
thì được, chạy từ app (search_path mặc định) thì vỡ. Đã ghi rõ `crm.` trong thân hàm.

## 3. Luật đã cài (nguồn: FR-040 "Luật bắt buộc" + BRD mục 6-7)

### Chuyển giai đoạn — `lead_service.move_stage()`
| Sang giai đoạn | Luật |
|---|---|
| Đang cân nhắc | phải có **lý do + lịch hẹn** (`next_action_at`) |
| Đã báo giá | đặc tả đòi "có liệu trình và giá" — **chưa kiểm tự động được** (dữ liệu thuộc B5/B6), tạm bắt ghi vào lý do; xem mục 5 |
| Đã chốt | khách phải có **đơn hàng** (không tính đơn huỷ) |
| Từ chối / Không phù hợp / Mất liên lạc | phải có **lý do chuẩn** trong `lead_lost_reasons`; tiện tay: truyền `lost_reason_id` ngay trong lời gọi move |
| Mọi giai đoạn | đích phải cùng pipeline; mọi lần chuyển ghi 1 dòng lịch sử (từ đâu, tới đâu, ai, lúc nào, lý do, ghi chú) + 1 dòng audit |

Chuyển sang "Đã kết nối" tự tính là **tương tác đầu** (FR-042).

### Chia lead — `create_lead()` (FR-030)
- Chia **vòng tròn theo tải**: Sale active đang giữ ít lead mở nhất nhận trước.
- Không có Sale nào đủ điều kiện → owner rỗng, lead vào **hàng đợi** (FR-032).
- Lead mới nào cũng có `sla_due_at = now() + 5 phút`.

### Chuyển người — `assign_owner()` (FR-031)
- Nhận lead từ hàng đợi: không cần lý do.
- Lead **đã có người giữ** → chuyển phải có lý do; người cũ nằm lại trong audit.
- Nhận xong đồng hồ SLA đặt lại 15 phút cho tương tác đầu.

### SLA — hằng số trong service, sẽ chuyển vào cấu hình công ty (màn 78)
`SLA_NHAN_LEAD_PHUT = 5` · `SLA_TUONG_TAC_DAU_PHUT = 15` (con số ví dụ của FR-042).

## 4. Đã kiểm — `scripts/thu_b3.py`, 25/25 PASS
Tạo + chia vòng tròn đúng 2 Sale · 5 luật chặn đều chặn đúng mã lỗi · đủ lịch sử
3 dòng · hàng đợi vào/ra đúng · quá hạn SLA xuất hiện rồi biến mất sau tương tác
đầu · lead nóng lọc đúng · ≥8 vết audit · dọn sạch không sót dòng nào.

## 5. Phần CHỜ — làm nốt khi mở khoá

| Việc | Chờ gì | Ghi chú |
|---|---|---|
| API `PIPELINE-001…004`, `LEAD-001…011` | **A3** (bao `{success,data,message}`, phân trang, `require_permission`) | Route chỉ là lớp mỏng gọi `lead_service` — luật đã nằm dưới hết |
| Kanban màn 11 + bảng việc Sale màn 12 | **B11/Bước 4** (khung template Jinja2) | Dữ liệu "số ngày ở trạng thái" đã có sẵn (`stage_entered_at`) |
| Siết luật "Đã báo giá phải có liệu trình + giá" | **B5/B6** | Đổi 1 nhánh trong `move_stage()` — chỗ đã đánh dấu trong code |
| Nguồn lead tự động từ Pancake | **B2** | B2 gọi `create_lead()` + `record_first_contact()` — hàm chờ sẵn |
| Chia theo Page / ca trực / khu vực / chiến dịch (FR-030) | **B2** (page), **A5** (ca/nhóm) | Hiện mới có "vòng tròn theo tải"; các kiểu kia cần dữ liệu chưa tồn tại |
| Nhắc gần quá hạn / báo trưởng nhóm (FR-042 automation) | **notifications** (bảng chưa dựng) + worker | Danh sách quá hạn đã query được (`list_overdue`) — chỉ thiếu kênh báo |

## 6. Quyết định tự chốt (nói nếu muốn khác)

1. "Đã chốt phải có đơn": kiểm **khách có đơn nào không** (không tính huỷ) — schema không có liên kết đơn↔lead trực tiếp. Nếu sau này cần "đơn nào sinh từ lead nào" thì thêm `orders.lead_id` ở B7.
2. Đơn **nháp** (draft) cũng tính là "có đơn" — Sale vừa lên đơn là chuyển được Đã chốt, không phải đợi xác nhận.
3. Mở lại lead từ giai đoạn đóng: **cho phép** (xoá `closed_at`), vì đặc tả không cấm và khách quay lại là chuyện thường; mọi lần mở đều có vết lịch sử.
4. Chia vòng tròn = "ít lead mở nhất nhận trước" — công bằng theo tải, trùng luôn ý "theo tải công việc" của FR-030.
