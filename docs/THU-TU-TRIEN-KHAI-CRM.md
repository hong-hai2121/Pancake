# THỨ TỰ TRIỂN KHAI CRM — làm gì trước, làm gì sau

Tài liệu này dành cho người **chưa nắm hết hệ thống**: phần 1 kể lại CRM này là gì
bằng một câu chuyện khách hàng; phần 2 trả lời "bắt đầu từ đâu"; phần 3 trở đi là
danh sách bước đánh số — muốn làm bước nào chỉ cần nói mã bước (A2, B3...).

Nguồn: gộp từ 3 danh sách MVP trong bộ đặc tả (17 nhóm API · 18 màn hình · mã FR)
và 5 giai đoạn MVP của [BRD](BRD-CRM-Quan-tri-khach-hang-tieu-hoa-chi-tiet.docx).

---

## 1. Hệ thống này là gì — kể bằng vòng đời một khách

Chị A thấy quảng cáo Facebook về liệu trình dạ dày, bấm nhắn tin cho page.

| # | Chuyện gì xảy ra | CRM phải làm gì | Ai lo |
|---|---|---|---|
| 1 | Chị A nhắn tin qua page | Pancake nhận tin → CRM kéo về, **tạo hồ sơ khách + lead**, ghi nhớ đến từ quảng cáo nào | (tự động) |
| 2 | Lead mới nằm chờ | **Chia cho một Sale** trong vòng 5 phút, quá hạn thì cảnh báo | Trưởng nhóm |
| 3 | Sale nhắn/gọi tư vấn | Ghi **phiếu triệu chứng** (đau ở đâu, bao lâu, thuốc đang dùng, bệnh nền), máy **sàng lọc an toàn** — có dấu hiệu nguy hiểm thì khoá tư vấn, chuyển người chuyên môn | Sale |
| 4 | Sale đề xuất liệu trình | **Rule engine chọn** liệu trình nào được phép hiển thị dựa trên phiếu — AI/Sale không tự nghĩ ra | Sale |
| 5 | Chị A còn băn khoăn | Ghi **lý do chưa mua** (giá? sợ tác dụng phụ? hỏi chồng?) → chạy chuỗi **bám đuổi** ngày 1-3-7-14-30 | Sale |
| 6 | Chốt — lên đơn | Đơn hàng, trạng thái giao, tiền | Sale + Kế toán |
| 7 | Giao thành công | **Tự động bàn giao sang CSKH** kèm phiếu: tình trạng, liệu trình, lưu ý, cam kết Sale đã hứa | (tự động) |
| 8 | Chị A bắt đầu uống | Ghi **ngày bắt đầu thật** → máy tự sinh lịch chăm **ngày 4-10-15-20-25** tính từ ngày đó | CSKH |
| 9 | Chăm theo mốc | Ngày 4: có phản ứng không? · Ngày 10: uống đúng không? · Ngày 15: **chấm điểm triệu chứng trước/sau** · Ngày 20: còn mấy hộp, tạo **cơ hội mua lại** · Ngày 25: chốt liệu trình 2 · Ngày 28: cứu cơ hội nếu chưa mua | CSKH |
| 10 | Có phản ứng / nặng hơn | **Khoá bán lại**, chuyển người chuyên môn — không được cố bán | (tự động) |
| 11 | Mua liệu trình 2, 3 | Lặp lại chu kỳ chăm; lâu không mua thì vào danh sách **khách ngủ** → tái kích hoạt | CSKH |
| 12 | Tổng kết | Marketing nhìn được: quảng cáo nào ra khách mua thật, hoàn nhiều, LTV cao → đổ tiền cho đúng chỗ | Marketing |

**Tóm một câu:** CRM là bộ máy bảo đảm 12 bước trên không bước nào bị bỏ quên,
ai làm gì đều có ghi vết, và mọi con số bấm ra được danh sách khách cụ thể.

## 2. Đã có gì — thiếu gì

| Đã chạy được (app hiện tại) | Chưa có (phải xây) |
|---|---|
| Kéo hội thoại Pancake về kho, xem + trả lời trên web | Hồ sơ khách CRM, lead, pipeline (mới có **bảng trống** trong DB) |
| Bot RAG gợi ý câu trả lời từ kho tri thức | Đăng nhập / phân quyền — **web đang mở toang, ai vào cũng được** |
| Quét cảm xúc tiêu cực + báo Telegram | Toàn bộ API `/api/v1` (~250 endpoint trong đặc tả) |
| 58 bảng CRM đã tạo trong Postgres (schema `crm`, đang trống) | Đơn hàng, bàn giao, lịch chăm, mua lại, automation, báo cáo |

## 3. Bắt đầu từ đâu? → **Login. Đúng.**

Bạn hỏi làm login trước là đúng hay sai — **đúng**, vì 3 lý do:

1. **Mọi thứ sau đều cần biết "ai đang thao tác"** — chia lead cho ai, audit ghi ai
   sửa, phân quyền ai được xem số điện thoại... đều đứng trên tài khoản người dùng.
2. Cả 3 tài liệu đều xếp nó **đầu tiên**: FR-001 (đặc tả chức năng), AUTH-001 (API),
   màn số 1 (danh sách màn hình).
3. Bảng `crm.users`, `roles`, `permissions` **đã có sẵn** trong DB — làm login là
   thổi hồn vào bảng có sẵn, không phải thiết kế gì mới.

Nhưng login chỉ là bước đầu của **Phần A — nền tảng** (4 bước nhỏ dưới đây). Làm
xong Phần A rồi mới vào nghiệp vụ, vì mọi lát cắt sau đều dùng lại nó.

---

## PHẦN A — NỀN TẢNG (làm một lần, dùng mãi)

### A1. Nạp schema CRM vào Postgres ✅ *(đã có sẵn script)*

Chạy `scripts/init_crm.sql` (idempotent, chạy lại không sao):

```powershell
docker exec -i pancakebot-pg psql -U postgres -d pancakebot -f - < scripts/init_crm.sql
```

**Xong khi:** `\dt crm.*` trong psql liệt kê 58 bảng.

### A2. Đăng nhập + tài khoản  ← **bắt đầu từ đây**

- `core/security.py`: băm mật khẩu (bcrypt), phát/kiểm JWT
- API: `POST /api/v1/auth/login` · `refresh` · `logout` · `GET /auth/me` ·
  `change-password` (AUTH-001…006)
- Seed dữ liệu: 1 tài khoản admin + các vai trò (Chủ DN, Admin, Trưởng nhóm Sale,
  Sale, Trưởng nhóm CSKH, CSKH, Marketing, Kế toán, Người chuyên môn — mục 3 BRD)
- Màn đăng nhập + **khoá toàn bộ web hiện tại sau đăng nhập** (đang mở toang)

**Xong khi:** không đăng nhập thì không xem được trang nào; đăng nhập sai 5 lần bị
khoá tạm; `GET /auth/me` trả đúng vai trò.

### A3. Khung API chuẩn

- Bao phản hồi `{success, data, message}` / `{success, error_code, message, errors}`
- 12 mã lỗi chuẩn (VALIDATION_ERROR, DUPLICATE_CUSTOMER, TREATMENT_BLOCKED...)
- Phân trang `?page=&per_page=` · lọc ngày · sắp xếp — viết một lần, mọi API dùng chung
- Dependency phân quyền: `require_permission("customer.view")` gắn vào từng route

**Xong khi:** có 1 API mẫu (vd `GET /api/v1/users`) trả đúng khuôn, Sale gọi API
của Admin bị chặn bằng `FORBIDDEN`.

### A4. Audit log

Mọi API **ghi** dữ liệu tự động lưu vào `crm.audit_logs`: ai, làm gì, giá trị
cũ/mới, lúc nào (FR-180). Bảng đã có sẵn — chỉ cần viết 1 hàm dùng chung.

**Xong khi:** sửa bất kỳ bản ghi nào cũng thấy 1 dòng audit tương ứng.

### A5. Quản lý người dùng

API USER-001…006 + ROLE + TEAM, và 2 màn: danh sách nhân viên · phân quyền
(màn 65-67). Gồm cả nút "chuyển toàn bộ khách khi nhân viên nghỉ" (FR-002).

**Xong khi:** Admin tạo được tài khoản Sale mới qua giao diện, khoá thì hết đăng nhập được.

---

## PHẦN B — 11 LÁT CẮT NGHIỆP VỤ (theo đúng thứ tự)

Nguyên tắc: mỗi lát = **bảng (đã có) + API + màn hình + chạy thử được** rồi mới
sang lát sau. Không làm hết API rồi mới quay lại làm màn hình.

### B1. Khách hàng 360°

Trái tim của CRM — mọi lát sau đều trỏ về đây.

- API CUSTOMER-001…012, IDENTITY-001/002 (tạo, sửa, tìm trùng, **gộp khách**, gắn tag, đổi người phụ trách)
- Chuẩn hoá số điện thoại; luật chống trùng theo thứ tự: external ID → PSID → SĐT → page+conversation (FR-011)
- Màn 8 (danh sách khách) + màn 9 (hồ sơ 360° — trước mắt 3 tab: Tổng quan, Hội thoại, Lịch sử)

**Xong khi:** tạo khách trùng SĐT bị cảnh báo; gộp 2 hồ sơ không mất lịch sử.

### B2. Nối Pancake vào CRM ⭐ *(điểm ghép app cũ với CRM)*

Worker poll hiện có (`app/workers/poller.py`) đang đổ vào kho `watcher` — thêm
bước: mỗi hội thoại kéo về thì **tạo/cập nhật `crm.customers` + `crm.conversations`
+ `crm.messages`** theo luật chống trùng B1, và tạo lead nếu khách chưa có.
Thêm bảng `sync_logs` (BRD yêu cầu, schema chưa có) + API PANCAKE-001…010.

**Xong khi:** khách nhắn tin mới trên Pancake → 30 giây sau có hồ sơ + lead trong
CRM, chạy đồng bộ lại không tạo bản ghi trùng.

### B3. Lead & pipeline Sale

- 13 trạng thái (Lead mới → ... → Đã chốt / Từ chối / Mất liên lạc), API PIPELINE + LEAD-001…011
- **Luật chặn** khi chuyển trạng thái: "đã báo giá" phải có liệu trình+giá, "đã chốt" phải có đơn, "từ chối" phải có lý do (FR-040)
- Chia lead tự động (vòng tròn / theo page / theo ca — FR-030) + hàng đợi lead + SLA 5 phút
- Màn 11 (Kanban kéo thả) + màn 12 (bảng công việc Sale)

**Xong khi:** lead mới tự có người phụ trách; kéo thẻ sang "đã chốt" khi chưa có đơn bị từ chối.

### B4. Công việc (task engine)

Một bộ máy việc dùng chung cho Sale lẫn CSKH: API TASK-001…009 (tạo, hoàn thành,
dời lịch, chuyển người), việc hôm nay / quá hạn, quá hạn hiện đỏ + báo quản lý.
**Không đóng việc nếu thiếu kết quả** (mục 19 BRD).

**Xong khi:** màn "việc hôm nay" của từng người đúng; việc quá hạn tự đổi màu.

### B5. Hồ sơ tư vấn + sàng lọc an toàn

- Phiếu triệu chứng (mức 0-10, tần suất, liên quan bữa ăn...), API CONSULT + SYMPTOM + MEDICAL + SAFETY
- **Thêm 3 bảng còn thiếu**: `examinations`, `current_medications`, `previous_treatments`
- Rule sàng lọc: nôn máu / sụt cân / thai kỳ... → **cảnh báo đỏ, chặn đề xuất, tạo việc chuyển chuyên môn** (FR-053)
- Màn 13 (tư vấn 2 cột: chat trái, hồ sơ phải) + màn 14 (phiếu khai thác)

**Xong khi:** nhập "phân đen" → hồ sơ bị gắn cảnh báo đỏ và không cho đề xuất liệu trình.

### B6. Sản phẩm & liệu trình + rule engine

- Danh mục sản phẩm (versioning giá — đổi giá không đổi đơn cũ), mẫu liệu trình, API PRODUCT + TREATMENT-001…014
- **Rule engine**: điều kiện phù hợp / loại trừ nằm trong DB (`treatment_rules`), không hardcode (mục 10 BRD)
- Đề xuất liệu trình FR-062: máy lọc theo rule → Sale chọn → cần thì gửi người chuyên môn duyệt
- Màn 42-46

**Xong khi:** khách có bệnh nền nằm trong điều kiện loại trừ thì liệu trình đó không hiện ra.

### B7. Đơn hàng

- 11 trạng thái chuẩn + **ánh xạ trạng thái Pancake → CRM** (admin cấu hình được, màn 23)
- API ORDER-001…011; phân loại đơn đầu / mua lại; lưu giá tại thời điểm tạo; không xoá lịch sử trạng thái
- Màn 21-22

**Xong khi:** đơn Pancake đồng bộ về đúng trạng thái CRM; đơn thứ 2 của khách tự gắn nhãn "mua lại".

### B8. Bàn giao Sale → CSKH

Đơn giao thành công → **tự động**: gán CSKH, tạo hồ sơ chăm, chép phiếu bàn giao
(tình trạng, liệu trình, lưu ý, cam kết Sale đã nói). Hồ sơ thiếu → CSKH trả lại
Sale bổ sung. API HANDOVER-001…006, màn 24-25.

**Xong khi:** chuyển đơn sang "giao thành công" thì hàng đợi CSKH tự có khách mới kèm phiếu.

### B9. Chăm sóc 11 bước (CS01→CS11) — *phần nặng nhất, giá trị nhất*

- Nhập **ngày bắt đầu dùng thật** → tự sinh mốc 4/10/15/20/25 (API CARE + CARE-STEP-001…011)
- Mỗi mốc một phiếu bắt buộc (màn 28-37); **không đóng mốc nếu thiếu dữ liệu**
- Ngày 15 chấm điểm triệu chứng trước/sau; kết quả chuẩn RS01…RS12 (mục 14.5 BRD)
- Phản ứng / nặng hơn → ticket chuyên môn + **khoá bán lại** (AU06)
- Chuỗi không phản hồi: nhắn-gọi-nhắn-gọi rồi tạm mất liên lạc; khách đòi dừng là dừng hết
- 13 luật automation AU01…AU13 (mục 14.6 BRD) — cần thêm bảng `automation_rules` + `automation_runs`
- Pipeline CSKH C01…C09 (Kanban màn 27) + bảng việc CSKH (màn 26)

**Xong khi:** nghiệm thu đúng câu của BRD — "actual_start_date sinh đúng các mốc
4-10-15-20-25; mỗi mốc không hoàn tất được nếu thiếu dữ liệu bắt buộc".

### B10. Mua lại & khách ngủ

- Ngày 20 tự tạo cơ hội mua lại; tính ngày dự kiến hết theo liều thật (REPURCHASE-001…010)
- Pipeline mua lại 9 trạng thái (màn 40); ngày 25 chưa mua **bắt buộc chọn lý do** → sinh việc ngày 28
- Khách ngủ 30/60/90/180 ngày + chiến dịch tái kích hoạt (màn 41)

**Xong khi:** đủ chuỗi ngày 20 → 25 → 28 chạy tự động đúng điều kiện.

### B11. Báo cáo cơ bản

Dashboard tổng quan + báo cáo Sale + CSKH (REPORT-001…003), **mọi con số bấm ra
danh sách chi tiết** (drill-down — FR-173). Màn 4-6.

**Xong khi:** bấm số "đơn giao thành công" mở đúng danh sách đơn với cùng bộ lọc.

---

## PHẦN C — GIAI ĐOẠN SAU (đúng lộ trình MVP 3-5 của BRD)

| | Nội dung | Tương ứng |
|---|---|---|
| C-MVP3 | Tổng đài, ghi âm, transcript, AI chấm cuộc gọi | CALL + AI-CALL, màn 18-20 |
| C-MVP4 | Kho kiến thức có duyệt, cây kịch bản, RAG nâng cấp (nối phần bot hiện có vào) | KNOWLEDGE + SCENARIO + AI, màn 47-52 |
| C-MVP5 | Đồng bộ Facebook Ads, attribution, ROAS/LTV, insight Marketing | ADS + FUNNEL, màn 53-59 |

## Bảng BRD nhắc nhưng schema chưa có — thêm khi chạm tới, đừng thêm trước

| Cần ở bước | Bảng |
|---|---|
| B2 | `sync_logs` |
| B5 | `examinations`, `current_medications`, `previous_treatments` |
| B7 (nếu cần đối soát) | `payments`, `shipments` |
| B9 | `automation_rules`, `automation_runs` |
| C-MVP3 | `call_recordings`, `coaching_notes` |
| C-MVP4 | `knowledge_chunks`, `ai_sessions`, `ai_citations`, `restricted_phrases` |
| C-MVP5 | `ad_creatives`, `ad_daily_metrics` |
| Khi chạm tới | `notifications`, `files`, `user_sessions`, `customer_status_history` |

## 3 điều nhớ khi làm bất kỳ bước nào

1. **Không xoá cứng dữ liệu nghiệp vụ** — chỉ soft delete (yêu cầu chung của đặc tả API).
2. **Mọi API ghi phải: kiểm quyền → kiểm dữ liệu bắt buộc → ghi audit** (Phần A lo sẵn khung).
3. Số liệu, trạng thái, mốc chăm, SLA đều **cấu hình trong DB, không hardcode** (mục 23 BRD).
