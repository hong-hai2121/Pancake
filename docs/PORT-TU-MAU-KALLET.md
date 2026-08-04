# Port từ mẫu Kallet CRM (PHP) sang Python — C1…C7

Nguồn: `D:\Python\templatemaux` (Kallet CRM v2, PHP thuần + MariaDB, 51 bảng).
Đích: dự án này (FastAPI + Postgres, schema `crm`).

Mẫu có 6 nhóm chức năng mà bên ta **chưa có gì** — đã port xong **cả 6**, cộng lát **C7** màn Đơn hàng. Tài
liệu này ghi **đã port cái gì · quyết định thiết kế nào khác mẫu · và những
luật nghiệp vụ tuyệt đối đừng "sửa cho gọn"**.

---

## Đã port

| Lát | Mẫu PHP | Bên ta | Nghiệm thu |
|---|---|---|---|
| **C1** Voucher · Hạng thẻ | `voucher.php` · `hang-the.php` | `/crm/voucher` · `/crm/hang-the` | `scripts/thu_c1_uu_dai.py` — 53 PASS |
| **C2** Lương · Thưởng · Đối soát | `luong.php` · `luong-thuong.php` · `doi-soat.php` | `/crm/thu-nhap` · `/crm/luong` · `/crm/doi-soat` · `/crm/bac-luong` | `scripts/thu_c2_luong.py` — 47 PASS |
| **C3** Chiến dịch · Mẫu tin | `chien-dich.php` · `mau-tin.php` | `/crm/chien-dich` · `/crm/mau-tin` | `scripts/thu_c3_chien_dich.py` — 41 PASS |
| **C4** Kịch bản · Kho data · Giám sát | `kich-ban.php` · `kho-data.php` · `lich-su.php` · `includes/xac_minh.php` | `/crm/kich-ban` · `/crm/kho-data` · `/crm/giam-sat` | `scripts/thu_c4_giam_sat.py` — 57 PASS |
| **C5** Bộ phận SALE | `trang-chu.php` · `includes/sale_buoc.php` · `includes/board_rules.php` | `/crm/bang-viec` · `/crm/thang-sale` | `scripts/thu_c5_sale.py` — 60 PASS |
| **C6** Bộ phận CSKH — quy trình 3 giai đoạn | `includes/cskh_quy_trinh.php` (bản chốt 02/08/2026) · nửa CSKH của `includes/board_rules.php` · `cham-soc.php` | `/crm/bang-viec-cskh` · `/crm/cskh/khuyen-mai` | `scripts/thu_c6_cskh.py` — 76 PASS |
| **C7** Đơn hàng | `don-hang.php` | `/crm/don-hang` (thay bản khung cũ) | `scripts/thu_c7_don_hang.py` — 60 PASS |

Tổng **394 PASS · 0 FAIL**.

## Chạy sau khi pull

```bash
docker exec -i pancakebot-pg psql -U postgres -d pancakebot < scripts/init_crm.sql
python scripts/seed_auth.py        # 5 quyền mới
python scripts/seed_uu_dai.py      # hạng thẻ + bậc lương/thưởng
python scripts/seed_kich_ban.py    # thư viện câu mẫu + luật gợi ý
python scripts/seed_thang_sale.py  # thang bám đuổi Sale 8 bước
python scripts/seed_cskh.py        # xem trước thang mốc CSKH (chạy khô)
python scripts/seed_cskh.py --ghi  # dựng thang mốc D45…D195 + buông D210
```

> 🚩 Xong rồi vào **Cài đặt → Thang bám đuổi Sale** đặt **"Ngày bật thang"**.
> Xem luật 11 ở dưới để hiểu vì sao thiếu bước này là hỏng cả bảng Sale.
>
> 🔒 **C6 mặc định TẮT** (`cskh_flow_enabled = false`) — bảng việc CSKH vẫn mở
> được nhưng xếp cột theo dải ngày cũ. Chỉ bật ở **Cài đặt → Quy trình CSKH**
> sau khi đã dựng thang mốc *và* điền `voucher_first_value` (mệnh giá máy tự
> tặng; để 0 thì máy không tặng, nhân viên tặng tay).

---

## Khác mẫu ở đâu (và vì sao)

| Mẫu PHP | Bên ta | Lý do |
|---|---|---|
| Bảng `campaigns` riêng | Nới `reactivation_campaigns` (B10) | Hai bảng campaign song song kiểu gì cũng có ngày đếm số lệch nhau |
| Bậc lương treo theo `positions` | Treo theo `crm.roles` | Vai trò bên ta đã đóng đúng vai đó, khỏi đẻ cây chức danh thứ hai |
| Bảng `care_actions` riêng | Nới `care_interactions` (B9) | Cùng khái niệm "một lần chạm khách" |
| `customers.hang_the` + `tong_chi_tieu` | Giữ nguyên nếp — cột đệm trên `customers` | Luật "chỉ nâng hạng" là luật CÓ TRẠNG THÁI: phải nhớ hạng cũ mới biết được đổi hay không. Suy từ orders là mất luật này |
| `OUTBOUND_MESSAGING_KILL_SWITCH` trong `config.php` | `outbound_messaging_enabled` ở màn Cài đặt | Đổi được lúc đang chạy, không phải sửa file rồi restart |
| Con trỏ bước trên `customers` | Trên `crm.leads` | `leads` mới là thực thể Sale bên ta; một khách có thể có nhiều lead qua thời gian |
| Thang bước hardcode trong PHP | Bảng `crm.sale_steps` | Sửa từ khoá trên web (`/crm/thang-sale`), không phải sửa code rồi deploy |
| Ngày lấy bằng `date()` của PHP | `app/core/ngay.py` (UTC+7) | Cùng một cái bẫy: Postgres trong Docker chạy UTC, `current_date` lệch 7 tiếng |
| "Chưa xếp hạng" là 1 dòng trong `card_ranks` | `customers.card_rank = NULL` | Thêm nó thành hạng thật thì luật "chỉ nâng" coi nó là bậc và không ai thoát ra được |
| `orders.pos_order_id` là mã đơn NGƯỜI DÙNG THẤY | Ta tách đôi: `pos_display_id` (mã thấy) + `pos_order_id` (system_id) | 1.535 đơn nhập từ hệ cũ có mã dạng chuỗi `C430270742.88` — ép số là mất sạch đơn cũ |
| Bảng `pos_order_map` học id đơn từ webhook | Không cần — `orders.pos_shop_id` + `pos_order_id` đã đủ dựng link POS | Mẫu phải đợi webhook mới mở được đơn ở POS; ta lấy thẳng từ lúc đồng bộ |
| `orders.tra_truoc` · `cod` · `staff_id` là cột thật | Rút từ `orders.pos_raw` ra cột `cod_amount` · `prepaid_amount` · `pos_seller_name` | jsonb bị TOAST: moi 5 khoá cho 53k đơn mỗi lần lọc/xuất là đọc lại cả bảng ngoài dòng; và ô tìm/ô lọc cần index |
| Một ô lọc "Nhân viên" | HAI ô: **Nhân viên CRM** (`sale_owner_id`) và **Nhân viên POS** (`pos_seller_name`) | POS dùng UUID riêng, chưa có bảng nối sang `crm.users` — gộp một ô là chọn ai cũng ra 0 dòng |
| Phạm vi xem theo `data.xem_toan_bo_khach` | Theo `revenue.view` | Bên ta không có quyền đó; ai xem được doanh thu công ty thì xem được mọi đơn |
| Bảng `care_actions` + cột `ket_qua_goi` (lượt gọi CSKH) | Cột `call_result` trên `care_interactions` | Vẫn là "một lần chạm khách". Hai bảng là hai nguồn đá nhau lúc đếm công (C4) |
| Bảng `cskh_ctkm` | `crm.cskh_promos` | Chỉ đổi tên cho khớp nếp đặt tên bảng bên ta |
| `customers.ngay_nhan_hang_cuoi` | `customers.last_delivered_at` | C1 đã có sẵn cột này, luồng đơn hàng tự đóng dấu |
| `customers.stage_code` + `stage_manual` (cột CSKH đặt tay) | `customers.cskh_column` (+`_at`/`_by`) | Cột đặt tay của Sale nằm trên `leads`, của CSKH nằm trên `customers` — hai bảng việc không giẫm chân nhau |
| `CSKH_QT_SCHEMA_V` + `ALTER TABLE` chạy lúc runtime (né WAF của host) | DDL nằm hẳn trong `scripts/init_crm.sql` | Bên ta deploy bằng psql, không có WAF chặn — vá schema lúc chạy chỉ tổ giấu lỗi |
| Thang mốc seed bằng file SQL chép tay (`seed_care.sql`) | `cskh_service.thang_mong_muon()` sinh từ 3 con số ở Cài đặt | Đổi mốc đầu / khoảng cách là thang tự đi theo; chép tay thì sửa một chỗ quên ba chỗ |

---

## 🔴 Hai mươi chín luật nghiệp vụ ĐỪNG SỬA CHO GỌN

Đây là những chỗ nhìn qua tưởng sai/thừa nên rất dễ bị "sửa lỗi" rồi hỏng
nghiệp vụ. Mỗi luật đều đã có bài kiểm khoá lại.

### C1 — Voucher & hạng thẻ

1. **Xếp hạng CHỈ NÂNG, không ai bị tụt.** Đơn hoàn làm tổng chi tiêu giảm thì
   hạng vẫn giữ. Hạ hạng khách là mất lòng khách, không phải việc của máy.
   → `voucher_service.tinh_lai_hang`
2. **Giảm quyền lợi NGẦM sau 180 ngày không nhận hàng.** Hạng *hiển thị* giữ
   nguyên, chỉ *quyền lợi* tụt 1 bậc, và **TUYỆT ĐỐI không gửi tin báo khách**.
   Đổi chữ hạng trên màn = người dùng tưởng khách đã bị hạ hạng thật.
3. **Ngưỡng chưa điền hiện chữ "chưa điền" MÀU CAM, không phải số 0.** Số 0 làm
   người dùng tưởng đã cấu hình xong.
4. **"Chưa báo mã" là VIỆC CẦN LÀM, không phải lỗi dữ liệu.** Voucher tạo không
   kèm mã nằm ở `chua_bao_ma` cho tới khi nhân viên báo mã.

### C2 — Lương & thưởng

5. **Thưởng chăm sóc CỘNG CHỒNG lên hoa hồng** (không thay thế). Nhìn qua tưởng
   trả hai lần cho cùng một đơn. Cố ý: hoa hồng trả cho *doanh thu*, thưởng chăm
   trả cho *công kéo khách cũ quay lại*. → `payroll_service.tinh_luong`
6. **Thưởng nóng có HAI KIỂU chạy song song và CỘNG DỒN**: theo doanh thu NGÀY
   và theo giá trị TỪNG ĐƠN. Một đơn to trong một ngày to thì ăn cả hai.
   → `payroll_service.thuong_nong`
7. **Đơn hoàn/huỷ sau khi CHỐT LƯƠNG → trừ KỲ SAU**, không sửa ngược kỳ cũ
   (tiền đã trả rồi). `payrolls.frozen` khoá kỳ; truy thu ghi một dòng
   `payroll_adjustments` âm, mỗi đơn đúng một lần.
   → `payroll_service.truy_thu_don_hoan`

### C3 — Chiến dịch

8. **Chiến dịch HAI TẦNG, đừng gộp.** Máy gửi tầng 1 cho cả tệp (miễn phí); chỉ
   khách **TRẢ LỜI** mới sinh việc tầng 2 cho nhân viên. Gộp một tầng = ném cả
   tệp mấy chục nghìn khách vào bảng việc của vài người → quá tải, nhân viên bỏ
   luôn cả khách thật sự quan tâm.
9. **Chế độ NHÁP không được "tiêu" khách.** Công tắc tắt thì chạy đợt vẫn duyệt
   hết danh sách nhưng KHÔNG đóng dấu `sent_at` — bật gửi thật vẫn gửi đủ.
   Và **đóng chiến dịch phải NHẢ khách chưa chốt**, không thì họ kẹt vĩnh viễn.

### C4 — Giám sát

10. **1 CÔNG / khách / nhân viên / hành động / NGÀY** (nhắn 10 tin vẫn 1 công) —
    chặn bằng unique index ở DB, không tin vào việc client ẩn nút. **Cửa soi
    ±1 NGÀY** vì nhân viên hay nhắn sáng, tối mới tick; soi gọn trong ngày là
    bác oan hàng loạt. Chưa tới hạn thì **chờ thêm, không bác vội**.
    → `giam_sat_service.soi_mot`

### C5 — Bộ phận Sale

11. **NGÀY BẬT THANG là chốt chặn quan trọng nhất.** Bộ dò CHỈ đọc tin TỪ ngày
    đó. Không có nó, lượt dò đầu tiên đọc CẢ LỊCH SỬ → khách đã nhắn qua lại
    vài tháng nhảy thẳng bước cuối → "hết thang" → rơi khỏi bảng việc. **Cả
    bảng Sale trống trong một nốt nhạc.** → `sale_service.ngay_bat_thang`
12. **Con trỏ CHỈ TIẾN.** Chặn ngay ở SQL (`where sale_step < %s`). Đường DUY
    NHẤT lùi được là nhân viên kéo thẻ tay — và có ghi dấu ai kéo.
13. **Mỗi tin nhảy tối đa `cua_so` bước**, và **nhảy cóc ăn cả ngã về không**:
    đích xa hơn trần thì không nhảy tí nào. Nhảy nửa vời đẩy khách vào một bước
    chẳng liên quan gì tới điều họ vừa nói — tệ hơn đứng yên.
14. **Khách đang chờ trả lời thì con trỏ ĐỨNG YÊN.** Việc lúc đó là ĐÁP KHÁCH,
    không phải đẩy bước tiếp. → `sale_service.cho_nhan_vien`
15. **Dự phòng "1 lượt nhắn = 1 bước" CHỈ dành cho NGƯỜI THẬT.** Tin máy/bot
    chỉ được tính bước khi dò ra ĐÚNG từ khoá — nếu không, bot chào tự động sẽ
    đẩy hết khách lên bước cao rồi cả tệp bị buông.
16. **🚫 Từ chối ≠ ⛔ Ngừng chăm sóc.** Từ chối đóng đợt này, KHÔNG hỏi xác
    nhận (bấm mấy chục lần/ngày), và thẻ **tự nhả** khi khách nhắn lại. Ngừng
    chăm sóc dừng hẳn, CÓ hỏi + bắt buộc lý do, thẻ **không tự nhả**.

### 🪤 Cái bẫy ngôn ngữ — mẫu đo trên 53.000 tin thật rồi mới chốt

Máy **bỏ dấu** trước khi so khớp, nên từ ĐƠN hay đụng nhau. Ví dụ có thật:

| Khai | Bỏ dấu thành | Đụng nhầm | Hậu quả |
|---|---|---|---|
| `đắt` | `dat` | `đặt hàng` | 619 tin bị tính sai bước |
| `mắc` | `mac` | `mặc` | — |
| `cao quá` | `cao qua` | `cạp cao qua rốn` | 186 tin sai |

⇒ **Từ khoá phải là CỤM NHIỀU CHỮ** (`"đắt quá"`, `"sao đắt"`).
`sale_service.luu_buoc` chặn thẳng từ khoá quá ngắn lúc lưu.

Và một ranh giới không thuộc danh sách trên nhưng dễ chết người:

> 📚 **THƯ VIỆN kịch bản** (`/crm/kich-ban`) = kho câu chữ để nhân viên CHÉP
> TAY. Mở/bấm chép **không gửi gì cho ai**.
> 🤖 **GỬI kịch bản / chiến dịch** (`/crm/chien-dich`) = máy BẮN tin thật.
> Gộp hai thứ này là có ngày ai đó bấm "xem câu mẫu" rồi tin bay tới khách.

Và một ranh giới nữa của C5:

> 🎯 **Pipeline giai đoạn** (`/crm/pipeline`) — 13 giai đoạn do NGƯỜI tự kéo.
> Trả lời: *"khách đang ở đâu trong quy trình bán"*.
> 📋 **Bảng việc thang bám đuổi** (`/crm/bang-viec`) — cột do MÁY đọc tin nhắn
> thật suy ra. Trả lời: *"câu tiếp theo cần nói với khách là gì"*.
> Hai thứ chạy **song song trên cùng một lead** (`stage_id` vs `sale_step`).
> Đừng gộp — gộp là mất một trong hai câu trả lời.

### C6 — Bộ phận CSKH (quy trình 3 giai đoạn)

Ba giai đoạn nối nhau, tất cả neo vào **NGÀY NHẬN HÀNG CUỐI**
(`customers.last_delivered_at`):

    GĐ1 · ngày 0 → trước D45   cảm ơn → khách im thì gọi → tặng voucher
    GĐ2 · voucher còn hạn      nhắc 15 · 7 · 3 · 0 ngày TRƯỚC hết hạn
    GĐ3 · từ D45, mỗi 15 ngày  mốc XEN KẼ có khuyến mãi → bám đuổi 3 ngày,
                               buông ở D210

17. **Đơn giao thành công: TIÊU mã cũ TRƯỚC, rồi mới xét tặng mã mới.** Làm
    ngược thứ tự thì luật "mỗi khách 1 mã sống" tự chặn, khách vĩnh viễn không
    được mã mới. → `cskh_service.don_thanh_cong` bước 1 → bước 2.
18. **Xét mã sống tại NGÀY ĐẶT ĐƠN, KHÔNG phải ngày giao.** Khách đặt ngày 28
    (mã còn hạn) mà hàng về ngày 35 (mã hết hạn ngày 33): xét lúc giao thì
    khách đã mua rồi vẫn bị coi là "không dùng voucher", bị đẩy sang GĐ3 và mất
    luôn mã mới. Ngày đặt = `coalesce(pos_inserted_at, created_at)`.
19. **Việc "cần tặng voucher" CÒN NẰM ĐÓ tới khi tặng xong.** Bản đầu của mẫu
    kẹp `d <= lưới` với `d >= lưới` nên cột chỉ mở **đúng 1 ngày** — nhân viên
    bận hôm đó là khách rơi khỏi cột vĩnh viễn và **GĐ2 không bao giờ khởi
    động**. → `cskh_service.cot_gap`
20. **Mệnh giá 0 = máy KHÔNG tặng.** Voucher là tiền: thà không phát còn hơn
    phát bừa một mệnh giá đoán mò. `voucher_first_value` mặc định 0.
21. **Mốc khuyến mãi không có đợt nào đang chạy thì chăm như mốc thường** —
    máy KHÔNG bịa nội dung ưu đãi ra gửi khách. Đợt nhập tay ở
    `/crm/cskh/khuyen-mai`, cố ý không lấy tự động từ Chiến dịch/Flash sale.
22. **Khách đang có ĐƠN CHẠY thì rời hẳn bảng việc, kể cả cột gấp.** Hàng đang
    trên đường mà nhân viên nhắn mời mua lại là mất mặt với khách. Khách không
    biến mất khỏi hệ thống — chỉ không tính là việc phải làm hôm nay.
23. **Câu việc 📌 của cột gấp CẤM chung chung.** "Voucher còn 7 ngày — nhắc lần
    2" khác hẳn "HẾT HẠN HÔM NAY — nhắc gấp". Nhãn tính ĐỘNG theo số ngày còn
    lại THẬT, nên nhân viên bỏ lỡ nhịp 15 thì khách trôi sang nhịp 7 vẫn hiện
    đúng. → `cskh_service.cau_nhac_han`

Và ranh giới quan trọng nhất của C6 — **hai màn "chăm sóc" khác hẳn nhau**:

> 💚 **Chăm sóc C01-C09** (`/crm/cham-soc`, B9) = liệu trình của **MỘT ĐƠN**:
> onboarding, phiếu chăm ngày 4/10/15/20/25, đánh giá triệu chứng. **Kết thúc**
> khi hết liệu trình.
> 🎯 **Bảng việc CSKH** (`/crm/bang-viec-cskh`, C6) = **vòng đời KHÁCH** sau khi
> nhận hàng: cảm ơn → voucher → thang mua lại. Chạy tới khi khách rời bảng.
> Gộp hai thứ này là mất luôn một trong hai vòng.

---

### C7 — Đơn hàng

24. **Doanh thu "lên đơn" TRỪ đơn *Đã hoàn* nhưng GIỮ đơn *Đang hoàn*.** Nhìn
    qua tưởng sót một trạng thái. Cố ý: hàng chưa về kho thì tiền chưa mất —
    trừ sớm là mỗi lần khách đòi đổi hàng, doanh thu tụt rồi hôm sau lại vọt.
    → `don_hang_repo.DA_HOAN`
25. **Thẻ chỉ số đếm trên CẢ BỘ LỌC, không phải trang đang xem.** Đổi bộ lọc là
    5 con số đổi theo. Đếm trên trang thì "tỉ lệ hoàn" của 30 dòng đầu bị đọc
    nhầm thành tỉ lệ hoàn của cả kỳ.
26. **`đến ngày` là ngày BAO GỒM** — route cộng 1 ngày trước khi xuống SQL (SQL
    so `<`). Quên bước này là mất trọn đơn của chính ngày cuối kỳ, mà đúng ngày
    cuối tháng lại là ngày người ta chốt số.
27. **Ô trống ≠ 0đ.** POS không gửi COD/trả trước thì cột để TRỐNG. Điền 0 vào
    chỗ chưa biết là người đối soát tưởng đơn không thu tiền mặt.
28. 🔒 **Xuất theo `ids[]` vẫn phải gắn lại phạm vi xem.** Id đơn là số tăng
    dần nên đoán được: người chỉ có `data.export` mà tự POST `ids[]` tuỳ ý sẽ
    dump được tên/SĐT/doanh số đơn của nhân viên khác. Mẫu đã vá đúng lỗ này.
    → `don_hang_repo.theo_ids(nguoi_xem=…)`
29. **`o.id` phải có trong mọi `ORDER BY` của bảng và của xuất file.** Cột sắp
    chính trùng giá trị hàng loạt (đơn 0đ, cùng ngày đặt) — thứ tự không duy
    nhất thì mỗi lô Postgres xếp một kiểu, lô này trùng hàng lô kia lọt hàng.

---

## Bốn con số 180/180/210/180 KHÁC NGHĨA

Mẫu đã cảnh báo, chép lại đây vì rất dễ sửa nhầm:

| Con số | Nghĩa | Ở đâu |
|---|---|---|
| **180** | Không nhận hàng bấy lâu thì **giảm quyền lợi hạng thẻ** | `card_rank_downgrade_days` |
| **180** | Mốc **nhắc cuối** trong thang mua lại | B9/B10 |
| **180** | **Thôi phân công** khách cho nhân viên | quy tắc chia lead |
| **210** | Khách **rời bảng việc** (coi là ngủ) | `crm_screens_repo` bộ lọc `sleep` · C6 `cskh_leave_days` |

---

## Còn lại chưa port (nếu muốn làm tiếp)

| Nhóm mẫu | File PHP | Ghi chú |
|---|---|---|
| Panel extension Chrome | `panel.php` · `api-panel.php` | Cột ~390px cắm cạnh Pancake, gọi CÙNG API web. Cần build extension MV3 riêng |
| Botcake gửi kịch bản | `includes/botcake.php` | Gửi mẫu Meta đã duyệt ra ngoài cửa 24h — `message_templates` đã có chỗ, thiếu lớp gọi Botcake |
| Tìm kiếm toàn cục | `tim-kiem.php` | Ô tìm chung khách/đơn/hội thoại |
| Hồ sơ cá nhân | `ho-so.php` | Nhân viên tự đổi mật khẩu/ảnh |
| Cài đặt AI | `ai-caidat.php` | Trùng phần lớn với khu Bot Pancake sẵn có |
| Flash sale | `san-pham.php` phần flash | Bảng `flash_sales` chưa port — thuộc màn Sản phẩm |
| Ngăn hội thoại trượt ở màn Đơn hàng | `includes/chatdock.php` | Mẫu mở khung chat NGAY TRONG trang đơn. Bên ta nút 💬 dẫn sang `/crm/khach-hang/{id}?tab=hoi-thoai` (đủ việc, nhưng rời trang) |
| Lịch chọn dải ngày 2 tháng | phần `dp=1` của `don-hang.php` | Bên ta dùng menu chọn nhanh 10 mốc + 2 ô `<input type=date>` — ít mã hơn, cùng kết quả |

### ⚠️ Ba cột của màn Đơn hàng đang TRỐNG vì thiếu dữ liệu, không phải thiếu mã

Bộ lọc và cột đã dựng đủ, nhưng đơn đổ từ POS chưa có gì để điền:

| Cột | Vì sao trống | Điền được khi |
|---|---|---|
| **Công sức** (`effort_axis`) · **Quảng cáo** (`ads_attributed`) · **Kỳ lương** (`payroll_period`) | C2 chỉ ghi 3 cột này lúc đơn CHUYỂN sang giao thành công. 13.377 đơn đã giao trước khi có C2 nên chưa ai gán | Chạy một lượt backfill gọi `payroll_service.ghi_ky_luong` cho đơn `delivered`/`collected` cũ |
| **Nhân viên CRM** (`sale_owner_id`) | `pos_sync` chưa nối được nhân viên POS (UUID) sang `crm.users` | Có bảng nối POS↔CRM. Trong lúc chờ, dùng cột/ô lọc **Nhân viên POS** — cột này CÓ dữ liệu thật (18.617/53.651 đơn) |
