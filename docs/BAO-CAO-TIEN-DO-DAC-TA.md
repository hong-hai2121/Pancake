# BÁO CÁO TIẾN ĐỘ — đối chiếu đặc tả chức năng CRM

> Đối chiếu `dac-ta-chuc-nang-CRM.pdf` (FR-001…FR-182, 29 trang) với code thật, ngày **01/08/2026** *(cập nhật cuối ngày: thêm màn 2 Trang chủ theo vai trò + FR-012 tin nhắn/CONV)*.
> Nguồn kiểm: 16 module API trong `app/api/v1/`, 14 bộ nghiệm thu `scripts/thu_*.py`, nhật ký [TIEN-DO.md](TIEN-DO.md).
> Ký hiệu: ✅ xong · 🔨 một phần · ⬜ chưa làm.

## 1. Tóm tắt

| Chỉ số | Giá trị |
|---|---|
| Nhóm chức năng đã xong (tầng luật + API) | **15 / 18 chương** — **PHẦN B HOÀN TẤT** |
| Số FR ước tính đã phủ | **~80%** (phần còn lại thuộc C: tổng đài, kho kiến thức, automation builder) |
| Test nghiệm thu | **758/758 PASS** (20 bộ — thêm `thu_b11` 46) |
| Tiêu chí nghiệm thu tổng thể (chương XX) | **~14,5/16 đạt** |
| Bước kế theo lộ trình | **Phần C** — tổng đài (C-MVP3, cần tài khoản tổng đài) → kho kiến thức (C-MVP4) → Ads mở rộng (C-MVP5) |

**Vòng đời khách KÍN + đo đếm được toàn trình:** khách (Pancake) → lead → pipeline → hồ sơ tư vấn + sàng lọc an toàn → đề xuất liệu trình → đơn hàng (POS) → quy nguồn quảng cáo + ROAS → bàn giao CSKH tự động (B8) → chăm sóc 11 bước theo ngày bắt đầu dùng thật (B9) → mua lại + khách ngủ & tái kích hoạt (B10) → **dashboard & báo cáo mọi tầng, mọi số bấm ra danh sách (B11)**.
**Chưa có (Phần C):** tổng đài/AI chấm cuộc gọi (C-MVP3 — cần tài khoản tổng đài), kho kiến thức + AI CRM (C-MVP4), Ads mở rộng + automation builder (C-MVP5/C).

## 2. Trạng thái theo từng chương đặc tả

| | Chương | FR | Tình trạng | Ghi chú / còn nợ |
|---|---|---|---|---|
| ✅ | II. Tài khoản & phân quyền | 001–003 | Xong (A2+A3+A5) | 18 quyền · 9 vai trò · phân cấp trưởng nhóm (`user.manage_team`) · khóa đòi chuyển khách trước (đúng FR-002) · nghiệm thu 27/27 + 30/30 + 31/31. **01/08:** FR-001 "vào dashboard theo vai trò" trọn vẹn — màn 2 `/crm/trang-chu`, 9 vai trò 9 bản riêng (19/19 `thu_trang_chu.py`) |
| ✅ | III. Tích hợp Pancake | 010–013 | ~98% (B2 + B-TH + B7 + FR-012 01/08) | Nhiều page, đồng bộ khách/thẻ/nhân viên/đơn, hàng đợi retry, nút mở Pancake — 58/58. **01/08:** FR-012 trọn vẹn — tin nhắn đầy đủ về `crm.messages` (worker `msg-sync`, công tắc TẮT mặc định, backfill `scripts/backfill_tin_nhan.py`) + 7 API CONV-001…006 + PANCAKE-010 — 33/33 (`thu_conv.py`). **Nợ còn lại:** webhook chờ domain (đang poll bù — không mất dữ liệu) |
| ✅ | IV. Quản lý khách hàng | 020–023 | Xong luật + 14 API (B1) | 360°, chống trùng 4 bậc, gộp 20 bảng/1 transaction, tag — 38/38. **Nợ:** màn 8/9/10 là khung tạm chờ B11; tab Hội thoại (màn 9) nay đã đủ API (CONV-001…006, 33/33) — chỉ còn thiếu giao diện |
| ✅ | V. Chia & sở hữu khách | 030–032 | Xong (B3 + A5) | Chia vòng tròn theo tải, hàng đợi lead, SLA; chuyển khách giữ lịch sử |
| ✅ | VI. Pipeline Sale | 040–042 | Xong luật + API (B3) | 13 giai đoạn, 5 luật chặn chuyển trạng thái, lịch sử FR-041, SLA 5'/15' — 25/25 + 16/16. **Nợ:** Kanban kéo-thả (màn 11) chờ khung B11 |
| ✅ | VII. Hồ sơ tư vấn | 050–053 | Xong (B5) | Sàng lọc 11 mục: 6 red flag → cờ đỏ + chặn đề xuất + việc chuyển chuyên môn — 37/37. **Nợ:** FR-051 mới nhận `file_url`, chưa có upload file thật (FILE-001…004); màn 13-14 chờ B11 |
| ✅ | VIII. Sản phẩm & liệu trình | 060–062 | Xong engine (B6) | Versioning giá, rule engine trong DB (`treatment_rules`), cờ vàng phải chuyên môn duyệt — 43/43. **Nợ:** `products` / `treatment_templates` / `treatment_rules` đang **0 dòng** — chưa nhập danh mục thật (có file `Bang-san-pham-CRM-hoan-thien.xlsx` làm nguồn); màn 42-46 chờ B11 |
| 🔨 | IX. Bám đuổi khách chưa mua | 070–073 | ~40% | Có task engine + báo quá hạn (FR-072), 9 lý do đã seed (`ref_codes`). **Chưa:** chuỗi follow-up tự động ngày 0/1/3/7/14/30 (FR-070) + điều kiện dừng chuỗi (FR-073) — thuộc automation |
| ✅ | X. Đơn hàng | 080–082 | Xong (B7) | 11 trạng thái + luật chuyển, ánh xạ 17 mã POS trong DB (admin sửa được), đơn đầu/mua lại tự phân loại, giá chốt thời điểm bán, idempotent — 50/50. **Nợ:** backfill 53k đơn chưa chạy; `POS_SYNC_ENABLED` đang TẮT; order_items POS chưa đồng bộ (chờ ánh xạ SP); màn 21-23 chờ B11 |
| ✅ | XI. Bàn giao Sale→CSKH | 090–091 | **Xong (B8, 01/08)** | Tự động khi giao thành công (cả chuyển tay lẫn POS): gán CSKH vòng tròn theo tải, chép liệu trình + mồi B5, vỏ care_plans + việc onboarding; 8 trường bắt buộc — thiếu không nhận, trả lại Sale kèm việc; 8 API + màn 24-25 THẬT — 41/41 (`thu_b8.py`). Backfill không sinh phiếu |
| ✅ | XII. Chăm sóc sau bán | 100–110 | **Xong TRỌN (B9, 01/08)** | Mốc CS04-08 sinh đúng ngày 4/10/15/20/25 từ ngày bắt đầu DÙNG THẬT (FR-102); phiếu 11 bước một cửa (trường bắt buộc + 7 bộ giá trị từ `ref_codes`); AU02/04/05/06/07/08/09/11; đánh giá trước/sau ngày 15 (nền = điểm B5); chuỗi không phản hồi 4 chạm → C08; worker `care-steps`; 18 route phủ 28 mã API; **màn 27 + 28-38 đều THẬT** (kể cả chuỗi + ngừng liên hệ trên web) — **64/64** (`thu_b9.py`) |
| ✅ | XIII. Mua lại & khách ngủ | 120–123 | **Xong (B10, 01/08)** | FR-120 ngày hết = bắt đầu THẬT × hệ số tuân thủ + tạm dừng + hàng cũ (breakdown minh bạch); FR-122 9 nhãn suy từ ngày + chuyển bước có luật, 'Chưa mua' bắt lý do chuẩn 9 mã BRD; FR-123 khách ngủ 30/60/90/180 + chiến dịch tái kích hoạt + doanh thu đo TỰ ĐỘNG; đơn giao TC tự chốt 'Đã mua'; màn 39-41 THẬT — **40/40** (`thu_b10.py`) |
| ⬜ | XIV. Cuộc gọi & AI chấm | 130–133 | Chưa (C-MVP3) | |
| ⬜ | XV. Kho kiến thức & AI chat | 140–143 | Chưa (C-MVP4) | Bot RAG hiện có là nền sẵn (ngưỡng 0.55, trả nguyên văn, chống injection) |
| ✅ | XVI. Marketing & quảng cáo | 150–154 | ~80% (B-QC) | Cây campaign→adset→ad→creative + **chi phí theo ngày** qua Pancake POS Ads Manager (không cần Facebook Ads API); first/last touch; ROAS/LTV; phiếu sức khỏe ad — 47/47. **Nợ:** phễu đầy đủ FR-152 (mới có FUNNEL-004), màn 57-58-59, nhận định AI (ADS-007/009) |
| 🔨 | XVII. Công việc & automation | 160–162 | ~55% | FR-160 xong (B4 — 41/41, không đóng thiếu kết quả); **01/08 thêm màn 3 Trung tâm thông báo** (NOTIFY-001…004, worker quét 11 nguồn — 39/39). **Chưa:** automation builder Khi–Nếu–Thì (FR-161) + quản lý lỗi automation (FR-162) — hoãn sang C; hiện chỉ có automation cứng (chia lead, cảnh báo SLA, task quá hạn, bàn giao B8, quét thông báo) |
| ✅ | XVIII. Báo cáo | 170–173 | **Xong (B11, 01/08)** | 12 route REPORT-001…011; sổ METRICS 24 chỉ số — số tổng và drill-down CÙNG điều kiện (FR-173); lead vào bước đếm theo lịch sử FR-041; quyền theo nội dung + export CSV có audit (FR-181); màn 4-5-6 + 60-62 + 64 THẬT (biểu đồ SVG, phễu bấm được) — **46/46** (`thu_b11.py`). **Nợ:** màn 63 + điểm AI chấm (chờ tổng đài C-MVP3) |
| 🔨 | XIX. Nhật ký & bảo mật | 180–182 | ~60% | FR-180 audit xong (chỉ ghi trường đổi, A4). FR-181 mới có xuất Excel nhân viên (quyền `data.export` + audit) — chưa có ẩn SĐT / giới hạn dòng / cảnh báo nhạy cảm cho xuất khách. FR-182 sao lưu chưa làm (màn 79, để sau C) |

## 3. Tiêu chí nghiệm thu tổng thể (chương XX) — 14,5/16 đạt

| # | Tiêu chí | Trạng thái |
|---|---|---|
| 1 | Lead Pancake đồng bộ đúng, không trùng | ✅ B1/B2 (chống trùng 4 bậc, idempotent) |
| 2 | Mỗi lead có người phụ trách | ✅ B3 chia tự động + hàng đợi |
| 3 | Lead quá hạn được cảnh báo | ✅ SLA 5'/15' + worker |
| 4 | Không đóng lead thiếu dữ liệu bắt buộc | ✅ 5 luật chặn FR-040 |
| 5 | Liệu trình chỉ đề xuất theo rule | ✅ B6 rule engine + chặn cờ đỏ |
| 6 | Đơn giao thành công tự tạo hồ sơ chăm | ✅ B8 phiếu + care_plans + CSKH; B9 sinh mốc CS01/CS02 ngay (AU03) |
| 7 | Mốc chăm theo ngày bắt đầu thực tế | ✅ B9 — FR-102, chưa bắt đầu = chưa sinh mốc đánh giá |
| 8 | Ngày 15 có đánh giá trước/sau | ✅ B9 — ASSESSMENT-001…003, nền = điểm B5 |
| 9 | Ngày 20 tự tạo cơ hội mua lại | ✅ B9 (AU08) + B10 pipeline trọn vòng đời (chuyển bước, lý do, tự 'won' khi có đơn) |
| 10 | Ngày 25 chưa mua bắt buộc có lý do | ✅ B9 — thiếu lý do là phiếu bị chặn (AU09) |
| 11 | Ngày 28 tạo đúng điều kiện | ✅ B9 — CS09 chỉ sinh khi CS08 chưa chốt, đúng ngày 28 từ bắt đầu thật |
| 12 | Cuộc gọi có ghi âm, transcript, điểm AI | ⬜ C-MVP3 |
| 13 | Nội dung rủi ro bị chặn | 🔨 bot Pancake có chống injection; phía CRM (FR-143) chưa |
| 14 | Quảng cáo đánh giá tới đơn giao và mua lại | 🔨 quy nguồn + ROAS có; doanh thu = 0 vì chưa bật đồng bộ POS + chưa backfill |
| 15 | Mọi số liệu báo cáo drill-down được | ✅ B11 — sổ METRICS: số và danh sách CÙNG điều kiện, có test đối chiếu từng metric |
| 16 | Mọi chỉnh sửa quan trọng có audit log | ✅ A4 |

## 4. Việc treo cần quyết định (chờ user chốt)

- [ ] **Bật `POS_SYNC_ENABLED` + chạy backfill 53k đơn** (`scripts/backfill_don_pos.py`) — điều kiện để ROAS/doanh thu quy nguồn có số thật
- [ ] **Nối thêm tài khoản quảng cáo vào Pancake POS** — hiện 1/64 ad_id trên đơn khớp được (chỉ 1 tài khoản QC đang nối)
- [ ] **Nhập danh mục sản phẩm/liệu trình thật** vào B6 (từ `Bang-san-pham-CRM-hoan-thien.xlsx`) — bảng đang 0 dòng, chưa nhập thì đề xuất liệu trình chưa dùng được thật
- [ ] **Xóa tab Thử API** (`/data/thu-api`) trước khi đưa web ra Internet — đang phơi token Pancake
- [ ] **Commit đợt tái cấu trúc thư mục** đang nằm ở working tree
- [ ] Đưa lên domain (Cloudflare Tunnel + Access) → khi có domain thì bật **webhook POS** thay poll bù

## 5. Đề xuất thứ tự làm tiếp

1. ~~B8 — Bàn giao Sale→CSKH~~ — **XONG 01/08** (41/41 PASS, màn 24-25 thật)
2. ~~B9 — Chăm sóc 11 bước~~ — **XONG TRỌN 01/08** (64/64 PASS, màn 27 + 28-38 đều thật; mở khóa 6 tiêu chí nghiệm thu 6-11)
3. ~~B10 — Mua lại & khách ngủ~~ — **XONG 01/08** (40/40 PASS, màn 39-41 thật; pipeline FR-122 + khách ngủ + doanh thu tái kích hoạt tự đo)
4. ~~B11 — Báo cáo cơ bản~~ — **XONG 01/08** (46/46 PASS; màn 4-6 + 60-62 + 64 thật, drill-down FR-173, export có audit). **→ PHẦN B HOÀN TẤT.**
5. **Phần C (kế tiếp):** tổng đài C-MVP3 (màn 18-20 · 63 · 74 — **cần user cấp tài khoản tổng đài**) → kho kiến thức C-MVP4 (47-52, nâng RAG bot sẵn có) → Ads mở rộng C-MVP5 (57-59 · 75) → automation builder (69-71) + sao lưu (79)
6. **Nợ màn nhỏ không chặn vận hành:** 8 (13 bộ lọc) · 11 (kéo-thả) · 21 (bộ lọc đơn) · 42-46 (chờ NHẬP DANH MỤC sản phẩm thật) · 16-17 (chuỗi bám đuổi, gộp automation C)

---
*File sinh tự động từ đối chiếu đặc tả ngày 01/08/2026. Bản text của PDF đặc tả: `spec_extract_tmp.txt` (tạm).*
