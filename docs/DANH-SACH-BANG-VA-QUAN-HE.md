# CRM TIÊU HÓA — DANH SÁCH BẢNG & QUAN HỆ

Bản đặc tả cấu trúc dữ liệu, đọc từ sơ đồ ERD tổng quan.
Tổng: **55 bảng**, chia 6 module.

**Ký hiệu**
- `PK` khóa chính · `FK` khóa ngoại · `UQ` duy nhất · `NN` bắt buộc nhập
- ⚠️ = chỗ ERD chưa rõ hoặc cần bạn xác nhận trước khi chốt

**Quy ước chung áp dụng cho mọi bảng**
- Khóa chính: số nguyên lớn tự tăng (`BIGINT IDENTITY`)
- Mọi bảng có `created_at`; bảng có sửa đổi thì thêm `updated_at`
- Mốc thời gian dùng kiểu có múi giờ; tiền dùng số thập phân 14 chữ số, 2 chữ số lẻ
- Trạng thái dùng chuỗi + ràng buộc kiểm tra giá trị, **không** dùng ENUM gốc của Postgres (sau này khó sửa)

**Hai bảng trục** — gần như mọi module đều trỏ về đây:
`customers` (khách hàng) và `users` (nhân sự).

---

## MODULE 1 — TỔ CHỨC & PHÂN QUYỀN (6 bảng)

### `pages` — Fanpage / kênh chat kết nối vào CRM
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `external_page_id` | ID do nền tảng cấp; UQ cùng `platform` |
| `name` | NN |
| `platform` | facebook / zalo / tiktok / website |
| `status` | active / paused / disconnected |

### `permissions` — Danh mục quyền nguyên tử
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `code` | UQ, dạng `customer.view`, `order.approve` |
| `name` | NN |

### `roles` — Vai trò
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | UQ |
| `description` | |

### `role_permissions` — Nối vai trò ↔ quyền
| Cột | Ghi chú |
|---|---|
| `role_id` | PK + FK → `roles` |
| `permission_id` | PK + FK → `permissions` |

### `teams` — Phòng ban / đội
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | UQ |
| `department` | ⚠️ cần chốt danh mục: sale / cskh / marketing / chuyên môn |
| `manager_id` | FK → `users` |

### `users` — Nhân sự vận hành
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | NN |
| `email` | UQ, NN |
| `phone` | |
| `status` | active / inactive / suspended |
| `team_id` | FK → `teams` |
| `role_id` | FK → `roles` |

⚠️ ERD không có cột mật khẩu. Nếu CRM tự đăng nhập (không dùng SSO của công ty) cần bổ sung `password_hash`, `last_login_at`.

**Quan hệ module 1**
- `roles` 1–N `role_permissions` N–1 `permissions` (quan hệ nhiều–nhiều)
- `teams` 1–N `users` (một đội nhiều nhân sự)
- `users` 1–N `teams` qua `manager_id` (một người quản lý nhiều đội) — **phụ thuộc vòng**, khi tạo bảng phải tạo `teams` trước, `users` sau, rồi mới gắn khóa ngoại `manager_id`
- `roles` 1–N `users`

---

## MODULE 2 — KHÁCH HÀNG & TƯƠNG TÁC (10 bảng)

### `customers` — Hồ sơ khách hàng (bảng trục)
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_code` | UQ |
| `full_name` | NN |
| `primary_phone` | ⚠️ **không** đặt UQ — nhà có nhiều người dùng chung 1 số. Nếu nghiệp vụ bắt 1 số = 1 khách thì phải nói rõ |
| `gender` | male / female / other |
| `birth_date` | |
| `province` | |
| `status` | new / consulting / customer / treating / completed / churned / blocked |
| `created_at` | |

### `customer_identities` — Một khách, nhiều danh tính trên các nền tảng
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `platform` | |
| `external_customer_id` | |
| `psid` | ID phạm vi trang, chỉ duy nhất trong 1 page |
| `page_id` | FK → `pages` |

### `conversations` — Hội thoại
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, **cho phép rỗng** (chat về trước khi kịp định danh khách) |
| `page_id` | FK → `pages` |
| `external_conversation_id` | UQ cùng `page_id` |
| `status` | open / pending / closed / spam |
| `last_message_at` | |

### `messages` — Tin nhắn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `conversation_id` | FK → `conversations`, NN |
| `external_message_id` | |
| `sender_type` | customer / agent / bot / system |
| `sender_user_id` | FK → `users` |
| `content` | |
| `sent_at` | NN |

⚠️ Bảng phình nhanh nhất hệ thống. Sau 1–2 năm nên chia mảnh theo tháng (`partition by range on sent_at`).

### `calls` — Cuộc gọi
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers` |
| `user_id` | FK → `users` |
| `external_call_id` | UQ, ID từ tổng đài |
| `direction` | inbound / outbound |
| `started_at` | NN |
| `duration_sec` | ≥ 0 |
| `status` | answered / missed / busy / failed / voicemail |
| `recording_url` | |

### `call_transcripts` — Bóc băng theo đoạn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `call_id` | FK → `calls`, NN |
| `speaker` | agent / customer / unknown |
| `content` | |
| `start_sec`, `end_sec` | giây, `end_sec ≥ start_sec` |
| `confidence` | 0–1, độ tin cậy nhận dạng |

### `call_evaluations` — Chấm chất lượng cuộc gọi
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `call_id` | FK → `calls`, NN |
| `score_total` | |
| `risk_level` | low / medium / high / critical |
| `summary` | |
| `review_status` | pending / reviewed / disputed / closed |

Ý nghĩa `risk_level`: rủi ro tuân thủ — tư vấn viên hứa công dụng vượt hồ sơ công bố. Đối chiếu với `product_versions.prohibited_claims`.

### `tags` — Nhãn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | UQ cùng `type` |
| `type` | |

### `customer_tags` — Nối khách ↔ nhãn
| Cột | Ghi chú |
|---|---|
| `customer_id` | PK + FK → `customers` |
| `tag_id` | PK + FK → `tags` |

### `customer_assignments` — Lịch sử giao khách cho nhân sự
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `user_id` | FK → `users`, NN |
| `assignment_type` | sale / cskh / chuyên môn |
| `start_at` | NN |
| `end_at` | rỗng = đang phụ trách |

Ràng buộc quan trọng: **mỗi khách, mỗi loại vai trò chỉ có đúng 1 người đang phụ trách** tại một thời điểm (dùng chỉ mục duy nhất có điều kiện `end_at IS NULL`).

**Quan hệ module 2**
- `customers` 1–N `customer_identities` (khách có nhiều tài khoản mạng xã hội)
- `customers` 1–N `conversations` 1–N `messages`
- `pages` 1–N `conversations`, `pages` 1–N `customer_identities`
- `customers` 1–N `calls` 1–N `call_transcripts`
- `calls` 1–N `call_evaluations`
- `customers` N–N `tags` qua `customer_tags`
- `customers` 1–N `customer_assignments` N–1 `users`
- `users` 1–N `messages` (qua `sender_user_id`), 1–N `calls`

---

## MODULE 3 — SALE & TƯ VẤN (11 bảng)

### `pipelines` — Quy trình bán
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | UQ |
| `type` | ⚠️ new_sale / upsell / reactivation — cần chốt |

### `pipeline_stages` — Giai đoạn trong quy trình
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `pipeline_id` | FK → `pipelines`, NN |
| `code` | UQ cùng `pipeline_id` |
| `name` | NN |
| `sort_order` | thứ tự hiển thị |
| `is_closed` | true = giai đoạn kết thúc (thắng hoặc thua) |

### `lead_reasons` — Danh mục lý do (thắng/thua/hoãn)
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `code` | UQ |
| `name` | NN |
| `category` | ⚠️ giá / niềm tin / thời điểm / đối thủ / sức khỏe — cần chốt |

### `leads` — Cơ hội bán
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `pipeline_id` | FK → `pipelines`, NN |
| `stage_id` | FK → `pipeline_stages`, NN |
| `owner_id` | FK → `users` |
| `source` | |
| `priority` | low / normal / high / urgent |
| `next_action_at` | |

⚠️ Cần ràng buộc `stage_id` phải thuộc đúng `pipeline_id`. Postgres không làm được bằng khóa ngoại thường, phải viết trigger kiểm tra.

### `lead_stage_history` — Nhật ký chuyển giai đoạn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `lead_id` | FK → `leads`, NN |
| `from_stage_id` | FK → `pipeline_stages`, rỗng khi mới tạo |
| `to_stage_id` | FK → `pipeline_stages`, NN |
| `changed_by` | FK → `users` |
| `changed_at` | NN |
| `reason` | |

### `lead_lost_reasons` — Lý do mất khách (1 lead có thể nhiều lý do)
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `lead_id` | FK → `leads`, NN |
| `lost_reason_id` | FK → `lead_reasons`, NN |
| `note` | |
| `evidence_type` | message / call / note |
| `evidence_id` | ⚠️ **quan hệ đa hình** — trỏ sang `messages` hoặc `calls` tùy `evidence_type`, không đặt được khóa ngoại, phần mềm phải tự kiểm |

### `consultation_sessions` — Phiên tư vấn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `lead_id` | FK → `leads` |
| `user_id` | FK → `users` |
| `channel` | chat / call / zalo / trực tiếp |
| `started_at`, `completed_at` | |
| `risk_level` | low / medium / high / critical |

### `consultation_answers` — Câu trả lời trong phiên tư vấn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `session_id` | FK → `consultation_sessions`, NN |
| `question_code` | NN |
| `answer_text` | |
| `answer_value` | bản số hóa để tính điểm/so sánh |
| `captured_at` | |

### `symptoms` — Danh mục triệu chứng
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `code` | UQ |
| `name` | NN |
| `group_name` | nhóm: dạ dày / đại tràng / tiêu hóa chung |

### `customer_symptoms` — Triệu chứng của từng khách
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `symptom_id` | FK → `symptoms`, NN |
| `severity` | ⚠️ giả định thang 0–10, cần xác nhận thang thực tế |
| `frequency` | hiếm / thỉnh thoảng / thường / hằng ngày / liên tục |
| `started_at` | |
| `is_primary` | triệu chứng chính |

UQ trên cặp (`customer_id`, `symptom_id`).

### `safety_screenings` — Sàng lọc cờ đỏ
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `screening_type` | NN |
| `value` | |
| `risk_level` | low / medium / high / critical |
| `requires_review` | cần người có chuyên môn duyệt |
| `created_at` | |

Đây là bảng an toàn: sụt cân không rõ nguyên nhân, đi ngoài ra máu, nuốt nghẹn, đang mang thai, đang dùng thuốc chống đông… → phải chuyển khám, không tư vấn bán hàng tiếp. Nên là bảng **bắt buộc kiểm tra trước khi tạo `customer_treatments`**.

**Quan hệ module 3**
- `pipelines` 1–N `pipeline_stages` 1–N `leads`
- `customers` 1–N `leads` 1–N `lead_stage_history`
- `leads` 1–N `lead_lost_reasons` N–1 `lead_reasons`
- `customers` 1–N `consultation_sessions` 1–N `consultation_answers`
- `leads` 1–N `consultation_sessions`
- `customers` N–N `symptoms` qua `customer_symptoms`
- `customers` 1–N `safety_screenings`
- `users` 1–N `leads` (owner), 1–N `consultation_sessions`, 1–N `lead_stage_history`

---

## MODULE 4 — SẢN PHẨM, LIỆU TRÌNH & ĐƠN HÀNG (10 bảng)

### `products` — Sản phẩm
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `product_code` | UQ |
| `name` | NN |
| `product_type` | |
| `price` | ≥ 0 |
| `package` | quy cách đóng gói |
| `units_per_package` | > 0 |
| `status` | active / inactive / discontinued |
| `approval_status` | draft / pending / approved / rejected |

`approval_status` = trạng thái duyệt nội dung công bố. **Chỉ sản phẩm `approved` mới được đưa vào tư vấn.**

### `product_versions` — Hồ sơ công dụng theo phiên bản
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `product_id` | FK → `products`, NN |
| `version_no` | UQ cùng `product_id` |
| `usage_text` | |
| `approved_claims` | JSON — các câu **được phép** nói |
| `prohibited_claims` | JSON — các câu **cấm** nói |
| `effective_from` | NN |
| `effective_to` | rỗng = còn hiệu lực |

Bảng này là chỗ dựa pháp lý. Khi chấm `call_evaluations` thì đối chiếu lời tư vấn với `prohibited_claims` của phiên bản đang có hiệu lực **tại thời điểm gọi**, không phải phiên bản mới nhất.

### `treatment_templates` — Phác đồ mẫu
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `template_code` | UQ cùng `version_no` |
| `name` | NN |
| `problem_group` | nhóm vấn đề |
| `level` | ⚠️ nhẹ / trung bình / nặng — cần chốt |
| `base_price` | ≥ 0 |
| `duration_days` | > 0 |
| `status` | draft / active / archived |
| `version_no` | |

### `treatment_template_items` — Sản phẩm trong phác đồ mẫu
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `template_id` | FK → `treatment_templates`, NN |
| `product_id` | FK → `products`, NN |
| `quantity` | > 0 |
| `dose_text` | cách dùng |
| `sort_order` | |

### `treatment_rules` — Luật điều chỉnh phác đồ
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `template_id` | FK → `treatment_templates`, NN |
| `rule_type` | NN |
| `condition_json` | JSON điều kiện |
| `action_json` | JSON hành động |
| `priority` | số lớn chạy trước |
| `status` | active / inactive |

Dùng cho: chống chỉ định, tăng/giảm liều theo triệu chứng, loại trừ khi có cờ đỏ.

### `orders` — Đơn hàng
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `external_order_id` | UQ, ID từ hệ bán hàng/vận đơn |
| `order_type` | new / repurchase / upsell / exchange |
| `sale_owner_id` | FK → `users` |
| `cskh_owner_id` | FK → `users` |
| `status` | draft / confirmed / packing / shipping / delivered / returned / cancelled |
| `total_amount` | ≥ 0 |
| `delivered_at` | |

`delivered_at` là **mốc khởi tính** liệu trình và lịch CSKH — cần chỉ mục riêng.

### `order_items` — Chi tiết đơn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `order_id` | FK → `orders`, NN |
| `product_id` | FK → `products`, NN |
| `treatment_template_id` | FK → `treatment_templates` |
| `quantity` | > 0 |
| `unit_price` | giá **tại thời điểm bán**, không tra ngược `products.price` |
| `line_total` | |

### `order_status_history` — Nhật ký trạng thái đơn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `order_id` | FK → `orders`, NN |
| `from_status`, `to_status` | |
| `changed_at` | |
| `changed_by` | FK → `users` |

### `customer_treatments` — Phác đồ đã cá nhân hóa cho khách
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `template_id` | FK → `treatment_templates` |
| `approved_by` | FK → `users` |
| `start_date` | |
| `expected_end_date` | |
| `status` | planned / active / paused / completed / stopped |

### `customer_treatment_items` — Chi tiết phác đồ của khách
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_treatment_id` | FK → `customer_treatments`, NN |
| `product_id` | FK → `products`, NN |
| `quantity` | > 0 |
| `dose_text` | |
| `actual_start_date` | |
| `actual_end_date` | |

**Quan hệ module 4**
- `products` 1–N `product_versions` (lưu vết theo phiên bản)
- `treatment_templates` 1–N `treatment_template_items` N–1 `products`
- `treatment_templates` 1–N `treatment_rules`
- `customers` 1–N `orders` 1–N `order_items` N–1 `products`
- `orders` 1–N `order_status_history`
- `treatment_templates` 1–N `order_items` (bán theo gói liệu trình)
- `customers` 1–N `customer_treatments` 1–N `customer_treatment_items` N–1 `products`
- `treatment_templates` 1–N `customer_treatments` (mẫu → bản cá nhân hóa)
- `users` 1–N `orders` (2 đường: `sale_owner_id`, `cskh_owner_id`), 1–N `customer_treatments` (approved_by)

⚠️ **Điểm cần quyết định:** ERD hiện **không nối trực tiếp `orders` với `customer_treatments`**. Nghĩa là không truy được "đơn nào sinh ra phác đồ này". Nếu nghiệp vụ cần (rất có khả năng cần, để tính doanh thu theo liệu trình), nên thêm cột `order_id` vào `customer_treatments`.

---

## MODULE 5 — CSKH, CÔNG VIỆC & MUA LẠI (8 bảng)

### `care_plans` — Kế hoạch chăm sóc
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `customer_treatment_id` | FK → `customer_treatments` |
| `owner_id` | FK → `users` |
| `status` | active / paused / completed / cancelled |
| `started_at`, `ended_at` | |

### `care_plan_steps` — Các mốc chăm sóc
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `care_plan_id` | FK → `care_plans`, NN |
| `step_code` | ⚠️ cần chốt bộ mã: D1_giao_hàng, D3_kiểm_tra, D7_đánh_giá, D30_tổng_kết… |
| `planned_at` | |
| `completed_at` | |
| `status` | pending / due / done / skipped / failed |
| `result_code` | |

### `care_interactions` — Lần liên hệ chăm sóc thực tế
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `care_plan_step_id` | FK → `care_plan_steps` |
| `customer_id` | FK → `customers`, NN |
| `user_id` | FK → `users` |
| `channel` | call / chat / zalo / sms / trực tiếp |
| `contacted` | có liên hệ được không |
| `summary` | |
| `next_action_at` | |

### `symptom_assessments` — Đo chuyển biến triệu chứng
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `care_interaction_id` | FK → `care_interactions`, NN |
| `symptom_id` | FK → `symptoms`, NN |
| `before_score` | |
| `current_score` | |
| `change_score` | nên là **cột tính tự động** = `before_score - current_score`; dương = cải thiện |

Đây là bảng đo hiệu quả — nguồn dữ liệu cho báo cáo "tỷ lệ khách cải thiện" và cho quyết định nâng/hạ liệu trình.

### `tasks` — Việc cần làm
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers` |
| `assigned_to` | FK → `users` |
| `task_type` | NN |
| `due_at` | |
| `priority` | low / normal / high / urgent |
| `status` | open / in_progress / done / cancelled / overdue |
| `related_type` | lead / order / care_plan_step / customer_treatment / repurchase_opportunity |
| `related_id` | ⚠️ **quan hệ đa hình**, không đặt được khóa ngoại |

### `repurchase_opportunities` — Cơ hội mua lại / nâng liệu trình
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers`, NN |
| `current_treatment_id` | FK → `customer_treatments` |
| `next_template_id` | FK → `treatment_templates` |
| `owner_id` | FK → `users` |
| `expected_close_date` | |
| `expected_value` | ≥ 0 |
| `stage` | identified / contacted / negotiating / won / lost / postponed |
| `lost_reason_id` | FK → `lead_reasons` |

Sinh tự động bằng job quét `customer_treatments` sắp đến `expected_end_date`.

### `reactivation_campaigns` — Chiến dịch đánh thức khách cũ
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | NN |
| `segment_rule_json` | JSON điều kiện chọn tệp |
| `start_at`, `end_at` | |
| `status` | draft / running / paused / finished |

### `reactivation_members` — Khách trong chiến dịch
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `campaign_id` | FK → `reactivation_campaigns`, NN |
| `customer_id` | FK → `customers`, NN |
| `assigned_to` | FK → `users` |
| `status` | pending / contacted / responded / converted / refused / unreachable |
| `result` | |

UQ trên cặp (`campaign_id`, `customer_id`) — tránh nhập trùng khách trong 1 chiến dịch.

**Quan hệ module 5**
- `customers` 1–N `care_plans` 1–N `care_plan_steps` 1–N `care_interactions`
- `customer_treatments` 1–N `care_plans` (liệu trình sinh ra kế hoạch chăm sóc)
- `care_interactions` 1–N `symptom_assessments` N–1 `symptoms`
- `customers` 1–N `tasks`, `users` 1–N `tasks`
- `customers` 1–N `repurchase_opportunities` N–1 `treatment_templates` (liệu trình kế tiếp)
- `customer_treatments` 1–N `repurchase_opportunities` (liệu trình hiện tại)
- `lead_reasons` 1–N `repurchase_opportunities` (dùng chung danh mục lý do với module 3)
- `reactivation_campaigns` 1–N `reactivation_members` N–1 `customers`

---

## MODULE 6 — KHO KIẾN THỨC, AI & MARKETING (10 bảng)

### `knowledge_documents` — Tài liệu chuyên môn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `title` | NN |
| `category` | |
| `status` | |
| `approved_by` | FK → `users` |
| `effective_from`, `effective_to` | |

⚠️ Trong ERD có một cột đọc không rõ, khả năng là `is_permission` hoặc quyền xem tài liệu. Cần bạn xác nhận.

### `knowledge_versions` — Phiên bản nội dung tài liệu
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `document_id` | FK → `knowledge_documents`, NN |
| `version_no` | UQ cùng `document_id` |
| `content` | |
| `created_by` | FK → `users` |
| `approved_at` | |

### `consultation_scenarios` — Kịch bản tư vấn
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `name` | NN |
| `problem_group` | |
| `version_no` | |
| `status` | |

### `scenario_rules` — Luật rẽ nhánh kịch bản
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `scenario_id` | FK → `consultation_scenarios`, NN |
| `condition_json` | |
| `action_json` | |
| `priority` | |
| `status` | |

### `scenario_steps` — Các bước trong kịch bản
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `scenario_id` | FK → `consultation_scenarios`, NN |
| `step_code` | |
| `step_type` | |
| `question_text` | câu hỏi cho tư vấn viên |
| `customer_message` | mẫu câu nói với khách |
| `required` | bước bắt buộc |
| `next_step_code` | bước kế tiếp |

⚠️ Có một cột đọc không rõ, khả năng `role_level` (bước này dành cho cấp nào). Cần xác nhận.

### `funnel_events` — Sự kiện phễu
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers` |
| `lead_id` | FK → `leads` |
| `order_id` | FK → `orders` |
| `event_type` | NN |
| `event_at` | NN |
| `value` | |

Bảng nhật ký, phình nhanh. Chỉ mục theo (`customer_id`, `event_at`).

### `ad_campaigns` — Chiến dịch quảng cáo
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `external_campaign_id` | UQ cùng `platform` |
| `name` | NN |
| `platform` | |
| `status` | |

### `ad_sets` — Nhóm quảng cáo
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `campaign_id` | FK → `ad_campaigns`, NN |
| `external_adset_id` | UQ |
| `name` | |

### `ads` — Mẫu quảng cáo
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `ad_set_id` | FK → `ad_sets`, NN |
| `external_ad_id` | UQ |
| `name` | |
| `creative_id` | |
| `status` | |

### `lead_attributions` — Quy nguồn khách về quảng cáo
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers` |
| `lead_id` | FK → `leads` |
| `campaign_id` | FK → `ad_campaigns` |
| `ad_set_id` | FK → `ad_sets` |
| `ad_id` | FK → `ads` |
| `touch_type` | first / last / assisted |
| `attributed_at` | |

Một lead có nhiều bản ghi quy nguồn (chạm đầu, chạm cuối, chạm hỗ trợ) — đây là thiết kế đúng để tính được cả hai mô hình quy nguồn.

### `ai_recommendations` — Gợi ý của AI
| Cột | Ghi chú |
|---|---|
| `id` | PK |
| `customer_id` | FK → `customers` |
| `session_id` | FK → `consultation_sessions` |
| `recommendation_type` | |
| `content` | |
| `source_refs` | nguồn trích dẫn, nên trỏ về `knowledge_versions` |
| `risk_level` | |
| `accepted_by` | FK → `users` |
| `created_at` | |

`accepted_by` là cột quan trọng: ghi nhận **người thật đã duyệt** gợi ý của máy trước khi nói với khách.

**Quan hệ module 6**
- `knowledge_documents` 1–N `knowledge_versions`
- `consultation_scenarios` 1–N `scenario_rules`, 1–N `scenario_steps`
- `ad_campaigns` 1–N `ad_sets` 1–N `ads` (phân cấp 3 tầng)
- `lead_attributions` trỏ đồng thời tới `customers`, `leads`, `ad_campaigns`, `ad_sets`, `ads`
- `funnel_events` trỏ tới `customers`, `leads`, `orders`
- `consultation_sessions` 1–N `ai_recommendations` N–1 `users` (accepted_by)

---

## BẢN ĐỒ QUAN HỆ TỔNG

Luồng chính của dữ liệu, đọc từ trái sang phải:

```
quảng cáo → khách vào chat/gọi → lead → tư vấn → sàng lọc an toàn
   → chốt đơn → phác đồ cá nhân hóa → chăm sóc → đo triệu chứng
   → mua lại / đánh thức lại
```

Ánh xạ sang bảng:

| Bước | Bảng chính |
|---|---|
| Quảng cáo | `ad_campaigns` → `ad_sets` → `ads` → `lead_attributions` |
| Tiếp xúc | `conversations` + `messages`, `calls` |
| Định danh | `customers`, `customer_identities` |
| Bán hàng | `leads` + `pipeline_stages` + `lead_stage_history` |
| Tư vấn | `consultation_sessions` + `consultation_answers`, `customer_symptoms` |
| An toàn | `safety_screenings` (chốt chặn bắt buộc) |
| Đơn hàng | `orders` + `order_items` |
| Điều trị | `customer_treatments` + `customer_treatment_items` |
| Chăm sóc | `care_plans` → `care_plan_steps` → `care_interactions` |
| Đo hiệu quả | `symptom_assessments` |
| Mua lại | `repurchase_opportunities`, `reactivation_campaigns` |

**Số lượng khóa ngoại trỏ về hai bảng trục**
- `customers`: 20 bảng trỏ về
- `users`: 17 bảng trỏ về

Đây chính là lý do sơ đồ ERD có đám đường nối dày đặc ở giữa.

---

## DANH SÁCH VIỆC CẦN BẠN CHỐT TRƯỚC KHI DỰNG

**Nhóm A — bắt buộc, ảnh hưởng cấu trúc**

1. `customers.primary_phone` có bắt buộc duy nhất không? Trong ngành này người nhà thường dùng chung số.
2. Có thêm `orders.id` vào `customer_treatments` không? Hiện không truy được đơn hàng ↔ liệu trình.
3. `users` có tự đăng nhập (cần `password_hash`) hay dùng SSO?
4. Ba quan hệ đa hình (`tasks.related_id`, `lead_lost_reasons.evidence_id`, `ai_recommendations.source_refs`) — chấp nhận không có ràng buộc khóa ngoại, hay tách thành bảng nối riêng?

**Nhóm B — chốt danh mục giá trị**

5. `teams.department`
6. `pipelines.type`, `lead_reasons.category`
7. `treatment_templates.level`
8. `care_plan_steps.step_code` — bộ mốc chăm sóc chuẩn
9. Thang điểm `customer_symptoms.severity` và `symptom_assessments` (hiện giả định 0–10)

**Nhóm C — cột đọc không rõ trên ảnh ERD**

10. `knowledge_documents` — cột thứ 6
11. `scenario_steps` — cột gần cuối
12. `funnel_events.value` — kiểu số tiền hay số điểm?

**Nhóm D — vận hành, quyết định sau**

13. `messages`, `funnel_events`, `call_transcripts` có chia mảnh theo tháng không?
14. Chính sách lưu trữ ghi âm và bóc băng (thời hạn xóa)
15. Ai được xem `call_transcripts` — dữ liệu này nhạy cảm
