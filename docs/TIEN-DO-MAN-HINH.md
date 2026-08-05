# TIẾN ĐỘ MÀN HÌNH — đối chiếu [danh-sach-man-hinh-CRM.pdf](danh-sach-man-hinh-CRM.pdf) (80 màn)

> Cập nhật lần cuối: **01/08/2026** — mọi màn ✅ đã được mở thật bằng tài khoản `admin` (trả 200 kèm nội dung), không chỉ đọc code.
> Ký hiệu: ✅ **làm thật** (thao tác được, dữ liệu thật) · 🔨 **khung/đang làm**
> (route có, số đếm thật nhưng chưa đủ thao tác) · ⬜ **chưa có màn**.
> **Quy ước cập nhật:** xong màn nào thì đổi ký hiệu ở bảng + sửa dòng Tổng kết.
>
> 🔗 **Link bấm mở thẳng màn** — cần app đang chạy (`python -m app.main`, cổng **8000**).
> Máy khác thì thay `localhost` bằng IP máy chạy app.
> Màn cần chọn bản ghi cụ thể (phiếu bàn giao, phiếu chăm, chi tiết 1 quảng cáo)
> thì link trỏ về **danh sách**, bấm tiếp một dòng là vào.
>
> ⚠️ **15 màn ⬜ còn lại đều CHƯA có backend** (tổng đài · kho kiến thức · AI ·
> automation builder · sao lưu) — thuộc phần C của lộ trình, không phải chỉ
> thiếu giao diện. Xem mục "Còn lại cần gì" ở cuối file.

## Tổng kết

| Trạng thái | Số màn | Danh sách |
|---|---|---|
| ✅ Làm thật | **62** | 1-10 · 12-17 · 21-46 · 53-58 · 60-62 · 64-69 · 71-73 · 76 · 77 |
| 🔨 Khung / một phần | **3** | 11 *(Kanban chưa kéo-thả)* · 78 *(thiếu tên/logo/múi giờ)* · 80 *(mới có lỗi đồng bộ)* |
| ⬜ Chưa có màn | **15** | 18-20 · 47-52 · 59 · 63 · 70 · 74 · 75 · 79 — **đều cần backend chưa xây (phần C)** |

> ➕ **Ngoài 80 màn trên**, đã port thêm **15 màn từ dự án mẫu Kallet (PHP)** —
> Bảng việc Sale · Thang bám đuổi · Bảng việc CSKH · Đợt khuyến mãi CSKH ·
> Voucher · Hạng thẻ · Thu nhập của tôi · Lương thưởng · Đối soát · Bậc lương ·
> Chiến dịch · Mẫu tin · Thư viện kịch bản · Kho data · Giám sát soi tin.
> Xem mục **XV-B** ở giữa file.

**Lối vào nhanh:** [Trang chủ](http://localhost:8000/crm/trang-chu) ·
[Thông báo](http://localhost:8000/crm/thong-bao) ·
[Bàn giao](http://localhost:8000/crm/ban-giao) ·
[Công việc](http://localhost:8000/crm/cong-viec) ·
[Quảng cáo](http://localhost:8000/crm/quang-cao) ·
[Quản trị](http://localhost:8000/quan-tri/nhan-vien) ·
[Cài đặt](http://localhost:8000/quan-tri/cai-dat)

---

## I. Màn hình chung

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 1 | Đăng nhập | ✅ | [/dang-nhap](http://localhost:8000/dang-nhap) | A2 — JWT, khoá 5 lần sai, ghi thiết bị + phiên (27/27). *Quên mật khẩu: reset qua admin* |
| 2 | Trang chủ theo vai trò | ✅ | [/crm/trang-chu](http://localhost:8000/crm/trang-chu) | 9 vai trò 9 bộ số + lối tắt; trưởng nhóm thấy CẢ ĐỘI (19/19) |
| 3 | Trung tâm thông báo | ✅ | [/crm/thong-bao](http://localhost:8000/crm/thong-bao) | NOTIFY-001…004 — worker quét **11 loại**, chuông đếm chưa đọc trên mọi trang, tự tắt từng loại (39/39) |

## II. Dashboard quản trị

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 4 | Dashboard tổng quan công ty | ✅ | [/crm/tong-quan](http://localhost:8000/crm/tong-quan) | **B11** — mọi ô số bấm ra danh sách (FR-173); ô doanh thu/chi phí ẩn theo quyền |
| 5 | Dashboard Sale | ✅ | [/crm/dashboard-sale](http://localhost:8000/crm/dashboard-sale) | **B11** — dashboard TỪNG Sale, quản lý chọn người xem |
| 6 | Dashboard CSKH | ✅ | [/crm/dashboard-cskh](http://localhost:8000/crm/dashboard-cskh) | **B11** — dashboard TỪNG CSKH |
| 7 | Dashboard Marketing | ✅ | [/crm/quang-cao](http://localhost:8000/crm/quang-cao) | Chi phí/ROAS/LTV từ POS Ads Manager (47/47) |

## III. Quản lý khách hàng

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 8 | Danh sách tất cả khách hàng | ✅ | [/crm/khach-hang](http://localhost:8000/crm/khach-hang) | **01/08** — thêm bộ lọc trạng thái · người phụ trách · đã mua/chưa (dùng bộ lọc CUSTOMER-001 của B1); bấm tên khách mở hồ sơ 360° |
| 9 | Hồ sơ khách hàng 360° | ✅ | [mở 1 khách ở màn 8](http://localhost:8000/crm/khach-hang) | **XONG 01/08 (40/40)** — đủ 9 khu vực theo PDF thành 9 tab: Tổng quan · Hội thoại (khung chat đọc `crm.messages`) · Cuộc gọi (báo rõ thuộc C-MVP3) · Hồ sơ tư vấn · Liệu trình · Đơn hàng · Chăm sóc · Marketing · Lịch sử thay đổi. Nạp theo tab đang xem |
| 10 | Hợp nhất khách trùng | ✅ | [/crm/khach-hang/gop-trung](http://localhost:8000/crm/khach-hang/gop-trung) | **XONG 01/08** — dò theo **SĐT** (dùng lại CUSTOMER-006 của B1) **+ Facebook ID**; chọn hồ sơ chính rồi gộp, hồ sơ phụ chuyển `merged` KHÔNG xoá (FR-022) |

## IV. Sale và telesale

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 11 | Pipeline Sale Kanban | 🔨 | [/crm/pipeline](http://localhost:8000/crm/pipeline) | 13 cột đủ, `?st=` tô sáng cột; **API B3 xong (25/25 + 16/16)**; kéo-thả chưa → **B11** |
| 12 | Bảng công việc Sale | ✅ | [/crm/cong-viec](http://localhost:8000/crm/cong-viec) | B4 dữ liệu thật (41/41); [xem cả đội](http://localhost:8000/crm/cong-viec?pham_vi=tatca) |
| 13 | Màn hình tư vấn khách | ✅ | [mở 1 khách → Vào tư vấn](http://localhost:8000/crm/khach-hang) | **01/08** — `/crm/tu-van/{id}` 3 tab liền mạch; tab này bày SONG SONG hội thoại khách ↔ checklist 7 câu bắt buộc + sàng lọc + liệu trình gợi ý; nút mở Pancake · gọi · chuyển chuyên môn |
| 14 | Phiếu khai thác tình trạng | ✅ | [↑ tab Khai thác](http://localhost:8000/crm/khach-hang) | **01/08** — nhập triệu chứng (FR-050 đòi mức độ/tần suất, ghi chú không thay được) + 11 mục sàng lọc; ghi mục ĐỎ là cờ đỏ + mở ca chuyên môn ngay |
| 15 | Màn hình đề xuất liệu trình | ✅ | [↑ tab Đề xuất](http://localhost:8000/crm/khach-hang) | **01/08** — chạy rule engine B6: mẫu phù hợp kèm lý do, mẫu bị loại kèm lý do loại; cờ đỏ CHẶN hẳn, cảnh báo → lưu ở trạng thái chờ chuyên môn duyệt |
| 16 | DS khách chưa mua cần bám đuổi | ✅ | [/crm/bam-duoi](http://localhost:8000/crm/bam-duoi) | **01/08** — lead chưa chốt + lý do chưa mua, lọc theo 9 lý do đã seed, số lần chạm & hẹn kế tiếp |
| 17 | Chi tiết chuỗi bám đuổi | ✅ | [mở 1 khách ở màn 16](http://localhost:8000/crm/bam-duoi) | **01/08** — từng lần chạm (thời gian · kênh · kết quả · người) + chuỗi không phản hồi 4 bước |

## V. Tổng đài và cuộc gọi

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 18 | Danh sách cuộc gọi | ⬜ | — | **C-MVP3** |
| 19 | Chi tiết cuộc gọi | ⬜ | — | **C-MVP3** |
| 20 | Dashboard chất lượng telesale | ⬜ | — | **C-MVP3** |

## VI. Đơn hàng

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 21 | Danh sách đơn hàng | ✅ | [/crm/don-hang](http://localhost:8000/crm/don-hang) | **C7 ← `don-hang.php`** (thay bản khung 01/08). 5 thẻ chỉ số · ô tìm · 10 ô lọc (khoảng thời gian, trạng thái, lần mua, công sức, quảng cáo, NV CRM, NV POS, fanpage, kỳ lương) · bảng 11 cột sắp xếp được · thanh tổng lên đơn/thành công · phân trang 30·50·100 · tích chọn GIỮ QUA TRANG + "chọn cả bộ lọc" · xuất Excel 20 cột chọn được (quyền `data.export`). Mã đơn mở thẳng đơn bên POS. Không có `revenue.view` thì chỉ thấy đơn mình phụ trách |
| 22 | Chi tiết đơn hàng | ✅ | [mở 1 đơn ở màn 21](http://localhost:8000/crm/don-hang) | **XONG 01/08** — hàng · tiền · địa chỉ/vận chuyển (moi từ `pos_raw`) · lịch sử trạng thái không xoá · việc & liệu trình liên quan · nguồn quảng cáo · nút mở phiếu bàn giao |
| 23 | Ánh xạ trạng thái đơn | ✅ | [/quan-tri/tich-hop/anh-xa](http://localhost:8000/quan-tri/tich-hop/anh-xa) | 17 mã POS→CRM trong DB, admin sửa là sync ăn ngay |

## VII. Bàn giao Sale sang CSKH

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 24 | DS khách chờ bàn giao | ✅ | [/crm/ban-giao](http://localhost:8000/crm/ban-giao) | **B8 (41/41)** — đơn giao thành công TỰ sinh phiếu, chips lọc, cột hồ sơ Đủ/Thiếu |
| 25 | Phiếu bàn giao | ✅ | [mở 1 dòng ở màn 24](http://localhost:8000/crm/ban-giao) | 8 trường bắt buộc FR-091 (thiếu tô đỏ); nút Nhận (đòi đủ hồ sơ) / Trả lại Sale (kèm việc) / Gán CSKH |

## VIII. Chăm sóc khách đã mua

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 26 | Bảng việc CSKH | ✅ | [/crm/cong-viec](http://localhost:8000/crm/cong-viec) | Chung task engine B4 (41/41) |
| 27 | Pipeline CSKH Kanban | ✅ | [/crm/cham-soc](http://localhost:8000/crm/cham-soc) | **B9 XONG 01/08 (57/57)** — C01-C09 đếm thật từ `care_plans.cskh_state`, mốc chờ làm, kế hoạch đang chạy |
| 28 | Phiếu xác nhận đơn | ✅ | [mở 1 kế hoạch ở màn 27](http://localhost:8000/crm/cham-soc) | Màn 28-37 gộp MỘT màn `/crm/cham-soc/{id}`: 11 mốc + phiếu của mốc đang mở — trường bắt buộc đọc từ `ref_codes` (BRD bảng 18), 3 lần không gặp → báo Sale (AU02) |
| 29 | Phiếu onboarding | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Nhận đủ → sinh CS03 +2 ngày (AU04); thiếu/lỗi hàng → ticket sự cố |
| 30 | Phiếu xác nhận bắt đầu sử dụng | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | **FR-102**: ghi ngày bắt đầu THẬT → sinh CS04-08 đúng ngày 4/10/15/20/25; chưa dùng → không sinh |
| 31 | Phiếu chăm ngày 4 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | 7 bộ giá trị (bảng 19) validate; phản ứng Vừa/Nặng → ca chuyên môn + C05 (AU06) |
| 32 | Phiếu chăm ngày 10 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Cùng luật AU06 |
| 33 | Phiếu đánh giá ngày 15 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Điểm trước/sau từng triệu chứng (ASSESSMENT-001…003, nền = điểm B5); RS04+dùng đúng → chuyên môn (AU07) |
| 34 | Phiếu chăm ngày 20 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Tự tạo cơ hội mua lại (AU08) |
| 35 | Phiếu chăm ngày 25 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Chưa mua → BẮT lý do + sinh CS09 ngày 28 (AU09) |
| 36 | Phiếu xử lý ngày 28 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | Khách đòi dừng → do_not_contact + C09 (AU11) |
| 37 | Phiếu chăm liệu trình 2 và 3 | ✅ | [↑ như trên](http://localhost:8000/crm/cham-soc) | CS10/CS11 — hẹn mua tiếp → việc `mua_lai` |
| 38 | Màn khách không phản hồi | ✅ | [khối 📵 trong màn kế hoạch](http://localhost:8000/crm/cham-soc) | NORESPONSE-001…004 đủ cả web: mở chuỗi, kênh TỰ ép đúng thứ tự nhắn→gọi→nhắn→gọi, đóng chuỗi, nút ⛔ ngừng liên hệ (AU11) — 64/64 |

## IX. Mua lại

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 39 | DS cơ hội mua lại | ✅ | [/crm/mua-lai](http://localhost:8000/crm/mua-lai) | **B10 XONG 01/08 (40/40)** — bảng cơ hội + nút chuyển bước ngay trên dòng ('Chưa mua' bắt lý do chuẩn 9 mã BRD) |
| 40 | Pipeline mua lại | ✅ | [/crm/mua-lai](http://localhost:8000/crm/mua-lai) | Chung màn 39 — **9 nhãn FR-122 suy từ ngày** (chưa/sắp/đến hạn/quá hạn/khách ngủ…), không cần job chạy đêm; đơn giao TC tự chốt "Đã mua" |
| 41 | Danh sách khách ngủ | ✅ | [/crm/khach-ngu](http://localhost:8000/crm/khach-ngu) | **B10** — rổ 30/60/90/180 ngày, lọc theo tổng mua, gán chiến dịch + việc `mua_lai`, doanh thu tái kích hoạt đo TỰ ĐỘNG khi khách có đơn mới |

## X. Sản phẩm và liệu trình

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 42 | Danh sách sản phẩm | ✅ | [/crm/san-pham](http://localhost:8000/crm/san-pham) | **API B6 (43/43)**; bấm tên sản phẩm sang chi tiết (màn 43). ⚠️ bảng `products` đang 0 dòng — chờ nhập danh mục thật |
| 43 | Chi tiết sản phẩm | ✅ | [mở 1 SP ở màn 42](http://localhost:8000/crm/san-pham) | **01/08** — nội dung Sale được nói / **nội dung CẤM** tách riêng, lịch sử phiên bản giá |
| 44 | Danh sách mẫu liệu trình | ✅ | [/crm/san-pham](http://localhost:8000/crm/san-pham) | Bấm tên mẫu sang chi tiết (màn 45) hoặc ⚙️ Luật (màn 46) |
| 45 | Chi tiết mẫu liệu trình | ✅ | [mở 1 mẫu ở màn 44](http://localhost:8000/crm/san-pham) | **01/08** — sản phẩm trong bộ · giá · thời gian · luật áp dụng rút gọn |
| 46 | Màn hình luật liệu trình | ✅ | [⚙️ Luật ở màn 44](http://localhost:8000/crm/san-pham) | **01/08** — 3 loại luật (loại trừ · phù hợp · cảnh báo), thêm luật ngay trên web; engine đọc DB nên sửa xong lần đề xuất sau ăn ngay |

## XI. Kho kiến thức và AI

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 47 | DS tài liệu kiến thức | ⬜ | — | Khu bot đã có [/data/kich-ban](http://localhost:8000/data/kich-ban) làm nền → **C-MVP4** |
| 48 | Chi tiết tài liệu kiến thức | ⬜ | — | **C-MVP4** |
| 49 | Thư viện kịch bản tư vấn | ⬜ | — | Kịch bản bot dạng Q&A đã có (khác cấu trúc đặc tả) → **C-MVP4** |
| 50 | Trình thiết kế cây kịch bản | ⬜ | — | **C-MVP4** |
| 51 | Màn duyệt nội dung | ⬜ | — | Luật approval đã chạy ở B6; màn duyệt chung chưa → **C-MVP4** |
| 52 | Nhật ký AI | ⬜ | — | **C-MVP4** |

## XII. Marketing và quảng cáo

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 53 | Danh sách campaign | ✅ | [/crm/quang-cao?cap=campaign](http://localhost:8000/crm/quang-cao?cap=campaign) | Chi phí theo NGÀY (`ad_metrics_daily`), ROAS, LTV |
| 54 | Danh sách adset | ✅ | [/crm/quang-cao?cap=ad_set](http://localhost:8000/crm/quang-cao?cap=ad_set) | Như campaign nhưng theo adset |
| 55 | Danh sách quảng cáo | ✅ | [/crm/quang-cao?cap=ad](http://localhost:8000/crm/quang-cao?cap=ad) | Ad chưa nối tài khoản QC → chi phí **RỖNG** chứ không phải 0 |
| 56 | Phiếu sức khỏe quảng cáo | ✅ | [mở 1 dòng ở màn 55](http://localhost:8000/crm/quang-cao?cap=ad) | Phễu · lý do chưa chốt · khách minh chứng. *AI nhận định (ADS-007) → C-MVP5* |
| 57 | Báo cáo băn khoăn khách hàng | ✅ | [/crm/bao-cao-ly-do](http://localhost:8000/crm/bao-cao-ly-do) | **01/08** — băn khoăn theo Sale và theo quảng cáo (chạm cuối) |
| 58 | Báo cáo lý do chưa chốt | ✅ | [/crm/bao-cao-ly-do](http://localhost:8000/crm/bao-cao-ly-do) | **01/08** — tỷ trọng từng lý do chưa chốt + lọc khoảng ngày |
| 59 | Trung tâm đề xuất Marketing | ⬜ | — | AI tổng hợp → **C-MVP5** |

## XIII. Báo cáo và KPI

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 60 | Báo cáo Sale | ✅ | [/crm/bao-cao?tab=sale](http://localhost:8000/crm/bao-cao?tab=sale) | **B11** |
| 61 | Báo cáo CSKH | ✅ | [/crm/bao-cao?tab=cskh](http://localhost:8000/crm/bao-cao?tab=cskh) | **B11** |
| 62 | Báo cáo nguồn quảng cáo | ✅ | [/crm/bao-cao?tab=marketing](http://localhost:8000/crm/bao-cao?tab=marketing) | **B11** |
| 63 | Báo cáo chất lượng tư vấn | ⬜ | — | Cần tổng đài (C-MVP3) + chấm chat; API REPORT-008 đã giữ chỗ trung thực |
| 64 | Báo cáo công việc | ✅ | [/crm/bao-cao?tab=cong-viec](http://localhost:8000/crm/bao-cao?tab=cong-viec) | **B11** |

## XIV. Nhân sự và phân quyền

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 65 | Danh sách nhân viên | ✅ | [/quan-tri/nhan-vien](http://localhost:8000/quan-tri/nhan-vien) | A5 — tìm tên/@user/SĐT, chip lọc nhóm, xuất Excel (`data.export`) |
| 66 | Hồ sơ nhân viên | ✅ | [mở 1 dòng ở màn 65](http://localhost:8000/quan-tri/nhan-vien) | Sửa · khoá (ép chuyển khách trước FR-002) · reset MK · chuyển khách |
| 67 | Vai trò và phân quyền | ✅ | [/quan-tri/phan-quyen](http://localhost:8000/quan-tri/phan-quyen) | 9 vai trò × 18 quyền |
| 68 | Phân nhóm và ca làm việc | ✅ | [/crm/nhom-ca](http://localhost:8000/crm/nhom-ca) | **01/08** — nhóm · trưởng nhóm · thành viên · người chưa vào nhóm · quy tắc chia lead. *Ca trực theo khung giờ chưa cấu hình được trên web* |

## XV. Automation và cấu hình

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 69 | Danh sách automation | ✅ | [/crm/automation](http://localhost:8000/crm/automation) | **01/08** — bảng THEO DÕI 14 automation đang chạy thật (KHI · THÌ · nằm ở đâu · công tắc nào). Cố ý không phải bảng cấu hình giả |
| 70 | Trình tạo automation (Khi–Nếu–Thì) | ⬜ | — | **C** |
| 71 | Mẫu chuỗi follow-up | ✅ | [/crm/automation](http://localhost:8000/crm/automation) | **01/08** — 5 chuỗi follow-up, ghi rõ chuỗi nào đang chạy / chuỗi nào chưa có engine |
| 72 | Danh mục dùng chung | ✅ | [/crm/danh-muc](http://localhost:8000/crm/danh-muc) | **01/08** — 78 mã trong `ref_codes` theo nhóm; thêm mã mới ngay trên web, mã cũ **ngừng dùng** chứ không xoá |

## XV-B. Port từ mẫu Kallet (C1–C8) — ngoài 80 màn đặc tả

> Bộ màn này KHÔNG nằm trong `danh-sach-man-hinh-CRM.pdf`; chúng port từ dự án
> mẫu `templatemaux/` (Kallet CRM, PHP) sang Python. Nguồn từng màn ghi ở cột
> cuối. Nghiệm thu: `thu_c1_uu_dai` 53 · `thu_c2_luong` 47 ·
> `thu_c3_chien_dich` 41 · `thu_c4_giam_sat` 57 · `thu_c5_sale` 60 ·
> `thu_c6_cskh` 76 · `thu_c7_don_hang` 60 · `thu_c8_cai_dat` 43 ·
> `thu_dot1` 49 · `thu_dot2` 85 · `thu_dot3` 87 — **659 PASS · 0 FAIL**.

| Màn | TT | Mở màn | Nền phía sau / mẫu gốc |
|---|---|---|---|
| **Cài đặt hệ thống** | ✅ | [/quan-tri/cai-dat](http://localhost:8000/quan-tri/cai-dat) | **C8** ← `cai-dat.php`. Menu mục con dính bên trái, hiện MỘT mục mỗi lần (8 nhóm · 56 cài đặt); ô trống hiện **“chưa điền” màu cam** chứ không phải 0; chuông cam đếm ô còn thiếu; mục có màn riêng thì trỏ thẳng sang; [Nhật ký cấu hình](http://localhost:8000/quan-tri/cai-dat?sec=log) ghi CŨ → MỚI |
| **↳ Mốc thời gian** | ✅ | [?sec=moc](http://localhost:8000/quan-tri/cai-dat?sec=moc) | **Đợt 1** ← phần `#k1a`/`#k1d`/`#k1g` của `cai-dat.php`. Bốn khối MỘT nút Lưu: thang bám đuổi Sale (thẻ từ khoá bấm gỡ · bắt thẻ trùng sau khi bỏ dấu · bật/tắt từng bước · 11 ô số nhịp · ô 🧪 **Thử một câu** chấm thử ngay trên từ khoá CHƯA lưu) · thang mua lại · tên 7 cột Sale + 11 cột CSKH. Gộp trọn nhóm `sale` nên nhóm này không còn mục menu riêng |
| **↳ Ưu đãi** | ✅ | [?sec=uu_dai](http://localhost:8000/quan-tri/cai-dat?sec=uu_dai) | **Đợt 1** (T1+T3). 6 khoá voucher/hạng thẻ gom về đây (trước nằm nhầm nhóm `cskh`), **cộng bảng ngưỡng hạng thẻ** — một cửa duy nhất để sửa. Ô ngưỡng để trống = hạng đó ngừng nhận khách mới, KHÔNG phải 0đ |
| **↳ Gửi tin** | ✅ | [?sec=gui_tin](http://localhost:8000/quan-tri/cai-dat?sec=gui_tin) | **Đợt 2** ← `?sec=msg`. Công tắc **3 trạng thái** (tắt/nháp/thật) + **2 lớp khoá**: `OUTBOUND_HARD_LOCK` chỉ có ở `.env` (web không mở được) và chế độ trên màn. Quyền RIÊNG `gui_tin.bat_cong_tac`, form riêng, lưu ngay khi bấm. Kèm 3 cửa gửi tin của Meta (24h · 7 ngày ads · ngoài cửa) |
| **↳ Vòng đời khách** | ✅ | [?sec=vong_doi](http://localhost:8000/quan-tri/cai-dat?sec=vong_doi) | **Đợt 2** ← `?sec=life` + `?sec=board`. 3 luật tự động **nối thật vào engine** (tự thu hồi — chỉ chặn đường MÁY · giảm quyền lợi ngầm · máy tự tặng voucher đơn đầu) + **nguồn lead vào bảng việc** (chỉ inbox / cả bình luận, kèm số khách thật bị chạm) + ghi chú luật bàn giao Sale→CSKH luôn chạy |
| **↳ Kịch bản nhận diện** | ✅ | [?sec=nhan_dien](http://localhost:8000/quan-tri/cai-dat?sec=nhan_dien) | **Đợt 2** ← `?sec=script`. 4 khối mẫu (đã gọi · chặn · từ voucher · viết tắt) trong `crm.phrase_patterns` — **cộng vào** bộ nền trong mã chứ không thay, nền vẽ viền đứt không xoá được. Dò cho **chèn tối đa N từ lạ**; chặn mẫu 1 từ quá ngắn ngay lúc nhập; ô 🧪 **Thử một câu** chấm tại chỗ (chặn → đã gọi → voucher) |
| **⚡ Luồng tự động** | 🟡 KHUNG | [/quan-tri/luong-tu-dong](http://localhost:8000/quan-tri/luong-tu-dong) | **Đợt 3** ← `luong-tu-dong.php`. 🔴 **CHƯA gửi tin cho ai** — theo yêu cầu: dựng khung trước, đường gửi tự động làm kỹ sau. Khai luật (3 kiểu kích hoạt · 10 điều kiện · 4 mốc neo) và **Chạy thử** trên dữ liệu thật để soi luật trúng ai. Chặn 3 tầng: engine không có mã gửi (kiểm bằng AST) · cửa `xin_phep_gui('auto_flow')` từ chối vô điều kiện · `AUTO_FLOW_HARD_LOCK` riêng trong `.env`. KHÔNG port nút "Test bắn" của mẫu. **Đường tự động DUY NHẤT đang mở: sinh VIỆC** vào `crm.tasks` cho người phụ trách (công tắc `auto_flow_task_enabled`, mặc định TẮT; worker `auto-flow-viec` quét 1 lượt/ngày) |
| **↳ Gợi ý kịch bản** | ✅ | [?sec=goi_y](http://localhost:8000/quan-tri/cai-dat?sec=goi_y) | **Đợt 2** ← `?sec=suggest`. CRUD `crm.script_suggest_rules`: từ khoá khách nói → kịch bản gợi ý trên nút 💡 của thẻ khách. Dò từ khoá, **không dùng AI** — gợi ý phải giải thích được "vì sao ra câu này". Bật/tắt tạm chứ không chỉ xoá |
| **Bảng việc Sale** | ✅ | [/crm/bang-viec](http://localhost:8000/crm/bang-viec) | **C5** ← `trang-chu.php` + `board_rules.php`. Cột do **máy đọc tin nhắn thật** suy ra, 2 chế độ Bảng/Pipeline, 4 ô đếm, câu 📌 việc cần làm + gợi ý câu chữ trên từng thẻ |
| **Thang bám đuổi Sale** | ✅ | [→ ?sec=moc#k1a](http://localhost:8000/quan-tri/cai-dat?sec=moc#k1a) | **C5** ← `sale_buoc.php`. 8 bước, từ khoá NV nói (đã làm bước) + từ khoá khách nói (nhảy cóc). Quyền `user.manage`. **Đợt 1:** màn riêng đã gộp vào Cài đặt → Mốc thời gian; `/crm/thang-sale` giữ lại dưới dạng chuyển hướng cho link cũ |
| **Bảng việc CSKH** | ✅ | [/crm/bang-viec-cskh](http://localhost:8000/crm/bang-viec-cskh) | **C6** ← `cskh_quy_trinh.php` + nửa CSKH của `board_rules.php` + **`index.php?bp=cskh`**. Quy trình 3 giai đoạn neo vào NGÀY NHẬN HÀNG CUỐI: cảm ơn → gọi → tặng voucher → nhắc hạn 15·7·3·0 → thang mua lại D45…D195, buông D210. **Màn dựng lại theo mẫu 05/08**: 2 chế độ Bảng\|Pipeline · 5 ô lọc nối thật (dải ngày nhận sinh từ ngưỡng cột · nhân viên · fanpage · cột · hạng thẻ) · 3 tab đếm cả phạm vi lọc · ẩn khách đã chăm hôm nay · dải khách ngủ · dải đợt khuyến mãi kèm nút Chép · thanh tiến trình mốc (xanh→vàng→đỏ + chữ) · 2 nút đóng khách (🚫 Từ chối không hỏi ↔ ⛔ Ngừng liên hệ bắt buộc lý do) · **focus 1 cột** (bấm tên cột trên Pipeline: trái thẻ · phải danh sách hội thoại → mở khung chat tại chỗ). **Khác** màn 27 (liệu trình C01-C09 của một đơn). Công tắc `cskh_flow_enabled` mặc định TẮT |
| **Đợt khuyến mãi CSKH** | ✅ | [/crm/cskh/khuyen-mai](http://localhost:8000/crm/cskh/khuyen-mai) | **C6** ← `cai-dat.php` phần khuyến mãi. Nhập TAY từng đợt; mốc xen kẽ (D45·75·105·135·165·195) bám đuổi 3 ngày theo đợt đang chạy — không có đợt thì chăm như mốc thường, máy KHÔNG bịa nội dung. Quyền `campaign.manage` |
| Voucher | ✅ | [/crm/voucher](http://localhost:8000/crm/voucher) | **C1** ← `voucher.php`. 4 ô số bấm-lọc, máy/người tặng tách riêng, "chưa báo mã" là VIỆC chứ không phải lỗi. Quyền `voucher.grant` |
| Hạng thẻ | ✅ | [/crm/hang-the](http://localhost:8000/crm/hang-the) | **C1** ← `hang-the.php`. 5 bậc + "Chưa xếp hạng"; tính lại **CHỈ NÂNG**; giảm quyền lợi NGẦM sau 180 ngày (hạng hiển thị giữ nguyên, KHÔNG báo khách). **Đợt 1 (T3):** màn này nay **CHỈ ĐỌC** đúng như mẫu — sửa ngưỡng ở [Cài đặt → Ưu đãi](http://localhost:8000/quan-tri/cai-dat?sec=uu_dai#nguong) |
| Thu nhập của tôi | ✅ | [/crm/thu-nhap](http://localhost:8000/crm/thu-nhap) | **C2** ← `luong.php`. Chỉ xem của chính mình; mọi khoản thưởng tra ngược được |
| Lương thưởng | ✅ | [/crm/luong](http://localhost:8000/crm/luong) | **C2** ← `luong-thuong.php`. Bảng lương cả đội + chốt kỳ. Quyền `payroll.manage` |
| Đối soát & duyệt thưởng | ✅ | [/crm/doi-soat](http://localhost:8000/crm/doi-soat) | **C2** ← `doi-soat.php`. 3 rổ suy từ dữ liệu; đổi phân loại thì TIỀN ĐI THEO. Quyền `payroll.approve` |
| Bậc lương & thưởng | ✅ | [/crm/bac-luong](http://localhost:8000/crm/bac-luong) | **C2** ← `cai-dat.php` phần lương. Hoa hồng · thưởng chăm · thưởng nóng theo vai trò |
| Chiến dịch | ✅ | [/crm/chien-dich](http://localhost:8000/crm/chien-dich) | **C3** ← `chien-dich.php`. HAI TẦNG: máy gửi tầng 1, chỉ khách TRẢ LỜI mới sinh việc tầng 2. Quyền `campaign.manage` |
| Mẫu tin | ✅ | [/crm/mau-tin](http://localhost:8000/crm/mau-tin) | **C3** ← `mau-tin.php`. Tự do (cửa 24h) vs Meta đã duyệt (ngoài cửa) — chặn khai sai lúc lưu |
| Thư viện kịch bản | ✅ | [/crm/kich-ban](http://localhost:8000/crm/kich-ban) | **C4** ← `kich-ban.php`. CHÉP TAY, không gửi gì; tìm được cả khi gõ không dấu; gợi ý 3 câu theo từ khoá |
| Kho data | ✅ | [/crm/kho-data](http://localhost:8000/crm/kho-data) | **C4** ← `kho-data.php`. Khách chưa chia · khách KẸT · nhật ký chia/gộp/xuất. Quyền `data.export` |
| Giám sát & soi tin | ✅ | [/crm/giam-sat](http://localhost:8000/crm/giam-sat) | **C4** ← `lich-su.php` + `includes/xac_minh.php`. 1 công/khách/NV/hành động/NGÀY; soi tin thật trong cửa ±1 ngày; khớp có dấu · bỏ dấu · **viết tắt**. Quyền `audit.view` |

**Quyền mới (chạy `python scripts/seed_auth.py` để nạp):** `voucher.grant` ·
`payroll.view_own` · `payroll.manage` · `payroll.approve` · `campaign.manage`.

**Seed dữ liệu mẫu:** `python scripts/seed_uu_dai.py` (hạng thẻ + bậc lương) ·
`python scripts/seed_kich_ban.py` (12 câu mẫu + 7 luật gợi ý) ·
`python scripts/seed_thang_sale.py` (thang bám đuổi 8 bước).

> 🚩 **C5 — nhớ đặt "Ngày bật thang"** ở
> [Cài đặt → Thang bám đuổi Sale](http://localhost:8000/quan-tri/cai-dat).
> Bộ dò CHỈ đọc tin TỪ ngày đó. Lùi quá xa thì khách đã nhắn qua lại vài tháng
> sẽ nhảy thẳng bước cuối → "hết thang" → rơi khỏi bảng việc, và cả bảng Sale
> trống trong một nốt nhạc. Để trống = hôm nay (an toàn).

> 🔴 **Công tắc gửi tin mặc định TẮT.** Chiến dịch chạy ở chế độ NHÁP: đếm và
> dựng nội dung nhưng không tin nào rời hệ thống, và khách KHÔNG bị đánh dấu
> "đã gửi" (bật thật vẫn gửi đủ). Bật ở
> [Cài đặt → Gửi tin hàng loạt](http://localhost:8000/quan-tri/cai-dat) —
> đây là **bước cuối cùng** khi triển khai, không phải bước đầu.

## XVI. Tích hợp

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 73 | Tích hợp Pancake | ✅ | [/quan-tri/tich-hop](http://localhost:8000/quan-tri/tich-hop) | Kết nối page/tài khoản, token che, nút đồng bộ, công tắc từng page (58/58) |
| 74 | Tích hợp tổng đài | ⬜ | — | **C-MVP3** |
| 75 | Tích hợp Facebook Ads | ⬜ | — | **Có thể không cần** — chi phí đã lấy qua POS Ads Manager → **C-MVP5** |
| 76 | Nhật ký đồng bộ | ✅ | [/quan-tri/tich-hop/nhat-ky](http://localhost:8000/quan-tri/tich-hop/nhat-ky) | Mỗi mẻ 1 dòng; kèm [hàng đợi lỗi](http://localhost:8000/quan-tri/tich-hop/loi) có nút thử lại |

## XVII. Quản trị hệ thống

| Màn | Tên | TT | Mở màn | Nền phía sau / làm ở |
|---|---|---|---|---|
| 77 | Nhật ký hoạt động | ✅ | [/quan-tri/nhat-ky](http://localhost:8000/quan-tri/nhat-ky) | A4 — audit CHỈ trường đổi cũ→mới, kèm IP/thiết bị |
| 78 | Cấu hình công ty | 🔨 | [/quan-tri/cai-dat](http://localhost:8000/quan-tri/cai-dat) | A6 — 22 công tắc + nhịp worker (39/39); **tên/logo/múi giờ/SLA chưa** → **C** |
| 79 | Sao lưu và phục hồi | ⬜ | — | BACKUP-001…003 → **C** |
| 80 | Quản lý lỗi hệ thống | 🔨 | [/quan-tri/tich-hop/loi](http://localhost:8000/quan-tri/tich-hop/loi) | Lỗi ĐỒNG BỘ đã có; lỗi API/automation/AI tổng hợp (SYSTEM-003) chưa → **C** |

---

## Đối chiếu 18 màn ưu tiên MVP (mục XVIII của PDF)

| # | Màn MVP | TT | Mở màn |
|---|---|---|---|
| 1 | Đăng nhập | ✅ | [mở](http://localhost:8000/dang-nhap) |
| 2 | Dashboard tổng quan | ✅ | [mở](http://localhost:8000/crm/tong-quan) *(B11 — 46/46)* |
| 3 | Danh sách khách | ✅ | [mở](http://localhost:8000/crm/khach-hang) |
| 4 | Hồ sơ khách 360° | ✅ | [mở 1 khách](http://localhost:8000/crm/khach-hang) |
| 5 | Pipeline Sale | 🔨 | [mở](http://localhost:8000/crm/pipeline) *(chưa kéo-thả)* |
| 6 | Bảng công việc Sale | ✅ | [mở](http://localhost:8000/crm/cong-viec) |
| 7 | Màn hình tư vấn | ✅ | [mở 1 khách → Vào tư vấn](http://localhost:8000/crm/khach-hang) |
| 8 | DS khách cần bám đuổi | ✅ | [mở](http://localhost:8000/crm/bam-duoi) |
| 9 | Danh sách đơn | ✅ | [mở](http://localhost:8000/crm/don-hang) |
| 10 | Chi tiết đơn | ✅ | [mở 1 đơn](http://localhost:8000/crm/don-hang) |
| 11 | DS khách chờ bàn giao | ✅ | [mở](http://localhost:8000/crm/ban-giao) |
| 12 | Bảng việc CSKH | ✅ | [mở](http://localhost:8000/crm/cong-viec) |
| 13 | Pipeline CSKH | ✅ | [mở](http://localhost:8000/crm/cham-soc) |
| 14 | Phiếu chăm theo mốc | ✅ | [mở](http://localhost:8000/crm/cham-soc) *(B9 — 57/57)* |
| 15 | DS cơ hội mua lại | ✅ | [mở](http://localhost:8000/crm/mua-lai) *(B10 — 40/40)* |
| 16 | DS sản phẩm/liệu trình | ✅ | [mở](http://localhost:8000/crm/san-pham) |
| 17 | Báo cáo cơ bản | ✅ | [mở](http://localhost:8000/crm/bao-cao) *(B11 — màn 60-64 + drill-down FR-173)* |
| 18 | Nhân viên và phân quyền | ✅ | [mở](http://localhost:8000/quan-tri/nhan-vien) |

**MVP: 17 ✅ · 1 🔨 · 0 ⬜** (đầu ngày 01/08: 4 ✅ · 7 🔨 · 7 ⬜).

## Thứ tự làm tiếp

1. ~~B9~~ — **XONG TRỌN 01/08** (64/64; màn 27-38 đều thật).
2. ~~B10~~ — **XONG 01/08** (40/40; màn 39-41 đều thật).
3. ~~B11 phần lõi~~ — **XONG 01/08** (46/46 `thu_b11.py`): màn 4-5-6 + 60-62 + 64,
   drill-down FR-173 (mọi ô số bấm ra danh sách cùng điều kiện), xuất CSV có audit.
   **→ PHẦN B (A1…B11) HOÀN TẤT.**
4. ~~Nợ màn giao diện~~ — **XONG 01/08**: 8 + 21 (bộ lọc) · 13-15 (tư vấn ·
   khai thác · đề xuất) · 16-17 (bám đuổi) · 42-46 (danh mục + chi tiết + luật) ·
   57-58 (báo cáo lý do) · 68 (nhóm & ca) · 69+71 (theo dõi automation) ·
   72 (danh mục dùng chung).

---

## Còn lại cần gì (15 màn ⬜ + 3 màn 🔨)

Khác với các đợt trước, **15 màn còn lại không phải "thiếu giao diện"** — chúng
cần backend chưa xây. Nhóm theo việc phải làm:

| Nhóm | Màn | Cần xây trước |
|---|---|---|
| **Tổng đài** | 18 · 19 · 20 · 63 · 74 | Nối nhà cung cấp tổng đài: bảng `calls`/`call_transcripts` đã có trong schema nhưng **0 dòng**; cần webhook nhận cuộc gọi + file ghi âm, rồi mới bóc băng và chấm điểm AI (C-MVP3) |
| **Kho kiến thức & AI** | 47 · 48 · 49 · 50 · 51 · 52 | KNOWLEDGE-001…009 + SCENARIO-001…006 + nhật ký AI. Bot hiện có RAG riêng ở khu Bot Pancake nhưng **khác cấu trúc đặc tả** (không có duyệt/phiên bản/quyền AI) — phải dựng mới (C-MVP4) |
| **Marketing AI** | 59 | Cần mô hình nhận định "lỗi thuộc Ads hay Sale" + đề xuất thử nghiệm. Dữ liệu đầu vào đã đủ (phễu · lý do chưa chốt · LTV theo ad) |
| **Automation builder** | 70 | FR-161 — trình tạo Khi–Nếu–Thì cho người dùng tự dựng luật. Hiện 14 automation chạy **cứng trong code** và đã liệt kê ở [màn 69](http://localhost:8000/crm/automation) |
| **Sao lưu** | 79 | BACKUP-001…003 — lịch sao lưu, phục hồi, nhật ký. Là việc hạ tầng (pg_dump + nơi lưu), không phải việc màn hình |
| **FB Ads trực tiếp** | 75 | **Có thể không cần**: chi phí/cây quảng cáo đã lấy qua Pancake POS Ads Manager. Chỉ làm nếu muốn số ngoài phạm vi Pancake |

**3 màn 🔨 còn dở** (dùng được nhưng chưa trọn):

- **11 Pipeline Kanban** — 13 cột + số đếm thật, bấm cột lọc được; còn thiếu **kéo-thả** để đổi giai đoạn (hiện đổi qua API/màn tư vấn).
- **78 Cấu hình công ty** — đã có 22 công tắc hệ thống; còn thiếu **tên/logo/múi giờ/định dạng tiền/SLA** của công ty.
- **80 Quản lý lỗi hệ thống** — đã có lỗi ĐỒNG BỘ (`/quan-tri/tich-hop/loi`); còn thiếu gom lỗi API/automation/AI vào một chỗ (SYSTEM-003).

## Ghi chú khi test

- **Đăng nhập:** `admin` + `ADMIN_BOOTSTRAP_PASSWORD` trong `.env`. Muốn thử từng vai trò: 11 tài khoản mẫu đã seed (`scripts/seed_tai_khoan_mau.py`, quên mật khẩu thì chạy lại với `--reset-passwords`).
- **Màn trống chưa chắc là lỗi.** Ba thứ đang thiếu DỮ LIỆU chứ không thiếu tính năng:
  - `products` / `treatment_templates` **0 dòng** → màn 42-46 trống và màn 15 (đề xuất) không có gì để gợi ý. Nhập danh mục thật là dùng được ngay.
  - `handovers` / `care_plans` chưa có bản ghi → màn 25 và 28-38 chưa mở được từ dữ liệu thật. Chuyển tay một đơn sang "giao thành công" ở [màn 21](http://localhost:8000/crm/don-hang) là phiếu tự sinh.
  - `lead_lost_reasons` **0 dòng** → màn 16/57/58 chưa có lý do để thống kê (Sale ghi lý do khi đóng lead).
- **Công tắc đồng bộ** ở [màn Cài đặt](http://localhost:8000/quan-tri/cai-dat) — bật/tắt có hiệu lực sau ~10 giây, không cần khởi động lại.
- Khu **Bot Pancake** ([Bảng điều khiển](http://localhost:8000/bang-dieu-khien) · [Tin nhắn](http://localhost:8000/tin-nhan) · [Cảm xúc](http://localhost:8000/cam-xuc) · [Dữ liệu bot](http://localhost:8000/data/kich-ban)) nằm ngoài 80 màn CRM, chỉ Chủ DN/Admin (`bot.view`) vào được.
