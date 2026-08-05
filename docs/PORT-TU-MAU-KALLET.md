# Port từ mẫu Kallet CRM (PHP) sang Python — C1…C8

Nguồn: `templatemaux/` (Kallet CRM v2, PHP thuần + MariaDB, 51 bảng).
Đích: dự án này (FastAPI + Postgres, schema `crm`).

Mẫu có 6 nhóm chức năng mà bên ta **chưa có gì** — đã port xong **cả 6**, cộng
lát **C7** màn Đơn hàng và **C8** màn Cài đặt. Tài liệu này ghi **đã port cái
gì · quyết định thiết kế nào khác mẫu · và những luật nghiệp vụ tuyệt đối đừng
"sửa cho gọn"**.

---

## Đã port

| Lát | Mẫu PHP | Bên ta | Nghiệm thu |
|---|---|---|---|
| **C1** Voucher · Hạng thẻ | `voucher.php` · `hang-the.php` | `/crm/voucher` · `/crm/hang-the` | `scripts/thu_c1_uu_dai.py` — 53 PASS |
| **C2** Lương · Thưởng · Đối soát | `luong.php` · `luong-thuong.php` · `doi-soat.php` | `/crm/thu-nhap` · `/crm/luong` · `/crm/doi-soat` · `/crm/bac-luong` | `scripts/thu_c2_luong.py` — 47 PASS |
| **C3** Chiến dịch · Mẫu tin | `chien-dich.php` · `mau-tin.php` | `/crm/chien-dich` · `/crm/mau-tin` | `scripts/thu_c3_chien_dich.py` — 41 PASS |
| **C4** Kịch bản · Kho data · Giám sát | `kich-ban.php` · `kho-data.php` · `lich-su.php` · `includes/xac_minh.php` | `/crm/kich-ban` · `/crm/kho-data` · `/crm/giam-sat` | `scripts/thu_c4_giam_sat.py` — 57 PASS |
| **C5** Bộ phận SALE | `trang-chu.php` · `includes/sale_buoc.php` · `includes/board_rules.php` | `/crm/bang-viec` · `/crm/thang-sale` | `scripts/thu_c5_sale.py` — 60 PASS |
| **C6** Bộ phận CSKH — quy trình 3 giai đoạn + **màn bảng việc dựng lại theo mẫu** | `includes/cskh_quy_trinh.php` (bản chốt 02/08/2026) · nửa CSKH của `includes/board_rules.php` · `index.php?bp=cskh` · `cham-soc.php` | `/crm/bang-viec-cskh` · `/crm/cskh/khuyen-mai` | `scripts/thu_c6_cskh.py` — 105 PASS |
| **C7** Đơn hàng | `don-hang.php` | `/crm/don-hang` (thay bản khung cũ) | `scripts/thu_c7_don_hang.py` — 60 PASS |
| **C8** Màn Cài đặt | `cai-dat.php` | `/quan-tri/cai-dat` (bố cục menu mục con) | `scripts/thu_c8_cai_dat.py` — 43 PASS |

Tổng **466 PASS · 0 FAIL**.

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

## 🔴 Ba mươi lăm luật nghiệp vụ ĐỪNG SỬA CHO GỌN

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

**Màn bảng việc dựng lại theo mẫu (đợt 05/08).** Trong mẫu, CSKH KHÔNG phải một
nhóm màn: `cham-soc.php` chỉ là 10 dòng chuyển hướng sang `index.php?bp=cskh`.
Toàn bộ nghiệp vụ gói trong MỘT bảng việc bốn tầng, và bản ta dựng lại đúng bốn
tầng đó, dùng chung bộ CSS `bv-*` với bảng việc Sale.

23b. **Đếm TRƯỚC khi lọc, cắt danh sách SAU CÙNG.** Ô "trạng thái" bày số thật
    của từng cột, tab bày số thật của cả phạm vi lọc. Đếm sau khi lọc thì mọi
    cột không được chọn đều về 0 — mà chính mấy con số đó là thứ người dùng
    nhìn để quyết định bấm vào đâu. → `cskh_service.bang_viec`
23c. **Dải "ngày nhận hàng" SINH TỪ ngưỡng cột, không chép tay.** Đổi mốc đầu
    hay khoảng cách ở Cài đặt là dải lọc tự đi theo, nên chọn "Chăm định kỳ"
    luôn ra đúng nhóm khách của cột đó. Mẫu từng chép công thức ba nơi và lệch.
    → `cskh_service.dai_presets`
23d. **Ẩn khách ĐÃ CHĂM HÔM NAY, mốc so là GIỜ chứ không phải ngày.** Nhân viên
    nhắn 9h, khách đáp 14h thì việc CHƯA xong. Và phải nói ra đã ẩn bao nhiêu —
    bảng ngắn hơn mình tưởng mà không giải thích là người dùng tưởng mất khách.
    → `cskh_service._da_cham_xong` · dải "Đã ẩn N khách"
23e. **Không bày băng-rôn báo "mọi thứ đang chạy tốt".** Trên màn mở suốt ngày,
    băng-rôn trạng thái bình thường đọc vài hôm là mắt bỏ qua luôn — kể cả hôm
    nó đổi thành báo lỗi thật. Thông tin ở lại dưới dạng một dòng ghi chú; chỉ
    thứ cần người XỬ (công tắc đang tắt · mệnh giá voucher = 0) mới được lên
    băng-rôn. → `views/cskh._dai_luat` vs `_bang_bao`
23f. **Tên 11 cột + câu việc 📌 đọc từ Cài đặt 1H** (`bn_cskh_*`/`bw_cskh_*`),
    và màn Cài đặt lấy danh sách cột THẲNG từ `cac_cot(goc=True)` — trước đây
    `cai_dat_moc.COT_CSKH` là bản chép tay thứ hai, đổi tên cột một bên là bên
    kia bày chữ mờ sai.
23g. **Focus 1 cột (bấm tên cột trên Pipeline) là màn LÀM VIỆC THẬT**, không
    phải trang trí: trái là thẻ của đúng cột đó, phải là hội thoại của chính
    những khách đó — nhân viên cày hết một cột mà không phải nhảy qua lại sang
    màn Hội thoại. Khi focus, cả suất bày 500 thẻ dồn cho một cột thay vì chia
    đều 12 cột rồi cột đang cày bị cắt mất. → route `?col=<cột>&kh=<khách>`
23h. **Khung chat trong focus dựng ở SERVER, không đẻ API riêng.** Mẫu nạp tin
    bằng JS qua endpoint riêng; bên ta cả màn vốn đã là form + tải lại trang,
    thêm một tầng API chỉ để đỡ một lượt tải là thêm một nguồn dữ liệu thứ hai
    phải giữ cho khớp với `crm.messages`. Khung này CHỈ ĐỌC — gõ tin vẫn ở màn
    Hội thoại/Pancake, nói rõ ngay dưới khung.
23i. **Bảng việc của mẫu KHÔNG có thanh thao tác hàng loạt.** Bản mô tả giao
    diện có nhắc, nhưng `index.php` chưa bao giờ dựng — `bulkbar.php` chỉ được
    `khach-hang.php` và `kho-data.php` gọi. Đừng "port cho đủ" một thứ mẫu
    không có; muốn thêm thì đó là quyết định thiết kế mới, và luật của bản mô tả
    phải giữ: **cấm** tặng voucher và tự khai đã nhắn hàng loạt.

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

### C8 — Màn Cài đặt

30. **Ô trống hiện chữ "chưa điền" MÀU CAM, KHÔNG phải số 0** (luật B3.3 của
    mẫu). `0` là một giá trị *đã đặt* — vd `voucher_first_value = 0` nghĩa là
    "máy KHÔNG tự tặng"; còn trống nghĩa là *chưa ai đặt* và module ăn theo nó
    đang tự tắt. Hiện `0` cho ô trống là người dùng tưởng cấu hình xong rồi
    ngồi chờ một thứ không bao giờ chạy. → `views/cai_dat.chua_dien`
31. **Hiện MỘT mục mỗi lần, menu mục con dính bên trái.** Người ta vào Cài đặt
    để sửa một thứ đang nghĩ tới; bắt cuộn qua 7 nhóm không liên quan là thiết
    kế sai. Menu còn đếm **số ô chưa điền** của từng mục (chuông cam) — không
    có nó thì phải mở từng mục ra mới biết chỗ nào còn thiếu.
32. **Mục đã có MÀN RIÊNG thì menu TRỎ THẲNG sang, không đẻ ô nhập thứ hai.**
    Hạng thẻ · bậc lương · thang bám đuổi · ánh xạ đơn · kết nối đều có màn
    riêng. Hai nơi sửa cùng một dữ liệu là hai nơi lệch nhau.
    → `views/cai_dat.MAN_RIENG`
33. **Ô CHỮ để trống VẪN ghi được; ô SỐ để trống thì bỏ qua.** Xoá chuỗi về
    rỗng là một thao tác có nghĩa (vd `sale_ladder_start` rỗng = "hôm nay");
    xoá một con số thì không, muốn về mặc định phải bấm nút *Trả về mặc định*.
34. **Lưu xong quay lại ĐÚNG mục đang mở.** Bắn người dùng về mục đầu sau mỗi
    lần Lưu là họ phải đi tìm lại chỗ vừa sửa. (`_back` phải nối `&` khi đường
    dẫn đã có `?` — nối `?` lần nữa là hỏng tham số.)
35. **Token/mật khẩu CỐ Ý không nằm ở màn Cài đặt.** Chúng chỉ ở `.env` và màn
    Kết nối. Mẫu để token ngay trong Cài đặt kèm cơ chế che `••••`; bên ta
    chọn đường an toàn hơn là không phơi lên web chút nào.

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

## Đợt 1 — gộp các mục Cài đặt còn thiếu (nghiệm thu `scripts/thu_dot1.py`, 49 PASS)

36. **Hết ghi cứng 180/210 (T4).** Dải "chăm cuối → rời bảng" nay do
    `crm_screens_repo.dai_cham_soc()` suy ra: cận trên là `cskh_leave_days`, cận
    dưới là mốc chăm CUỐI CÙNG đang bật của thang C6. Nhãn màn Khách hàng
    (`views/crm._kh_tinh_trang_dinh`) và nhóm tệp Chiến dịch
    (`campaign_service.nhom_tep`) đọc theo nó, nên đổi một con số ở Cài đặt là
    cả SQL lẫn chữ trên màn đổi theo — không còn cảnh nhãn ghi "181–210" mà
    truy vấn lọc mốc khác. **Khoá** của nhóm tệp (`151_180`, `181_210`,
    `ngu210`) CỐ Ý giữ nguyên dù nhãn đổi: chiến dịch đã lưu bộ lọc theo khoá,
    đổi khoá là mất lọc của chúng.

37. **Sáu khoá voucher/hạng thẻ về đúng nhóm `uu_dai` (T1).** Trước nằm trong
    nhóm `cskh` nên admin đi tìm ở mục CSKH không thấy.

38. **Lớp khoá TỰ DO, tách khỏi danh mục `MUC`.** Tên 7 cột Sale + 11 cột CSKH
    (`bn_*`) và câu việc 📌 của cột (`bw_*`) là dữ liệu người dùng đặt, không
    phải cài đặt có mô tả/khoảng hợp lệ — nhét vào `MUC` sẽ phình danh mục và
    hỏng mọi phép đếm "chưa điền". Chúng đi đường `runtime_config.lay_tu_do` /
    `dat_tu_do`, cùng bảng `crm.app_settings` nhưng khác lớp. Đặt giá trị RỖNG =
    **xoá hẳn dòng**, tức trả cột về tên gốc trong mã.

39. **Một cửa để sửa, không hai (T2 + T3).** `/crm/thang-sale` và ô nhập ngưỡng ở
    `/crm/hang-the` đều bị gỡ; hai đường cũ giữ lại dưới dạng **chuyển hướng**
    chứ không xoá, để link/bookmark/tab đang mở vẫn tới đúng chỗ sửa mới thay
    vì ăn 404. Cùng một cột mà hai màn ghi được thì sớm muộn cũng lệch nhau —
    đây đúng là cách mẫu chia `hang-the.php` (chỉ đọc) với `cai-dat.php?sec=tier`.

40. **Ngưỡng hạng thẻ vào chung nút Lưu của mục Ưu đãi**, và chỉ ghi hạng nào
    THỰC SỰ đổi — nếu ghi cả 5 hạng mỗi lượt lưu thì Nhật ký cấu hình đầy những
    dòng "sửa" mà chẳng sửa gì. Nhật ký (`audit_repo.nhat_ky_cai_dat`) đã nới
    để nhận thêm `sua_nguong_hang_the`: việc làm trên màn Cài đặt thì phải thấy
    ở nhật ký của màn Cài đặt.

41. **`?sec=` của nhóm đã gộp phải rơi về mục đã gộp nó.** Nhóm `sale` nay nằm
    trọn trong mục "Mốc thời gian" (`NHOM_AN`), nên `?sec=sale` dẫn tới đó chứ
    không lặng lẽ lùi về nhóm đầu bảng.

42. **`sale_repo.luu_buoc` sửa TỪNG PHẦN.** `None` = "không đụng tới", chuỗi
    RỖNG = "admin xoá trắng ô này" và vẫn ghi. Nhờ vậy đổi mỗi tên bước không
    thổi bay từ khoá, và `status=None` không bật lại bước admin đã tắt.

43. **Ô 🧪 "Thử một câu" chấm trên từ khoá CHƯA lưu.** Admin gõ thêm một cụm rồi
    thử ngay, thấy nó bắt vào bước nào trước khi bấm Lưu — thay vì lưu bừa rồi
    đợi khách nhắn mới biết mình đặt nhầm.

---

## Đợt 2 — năm mục Cài đặt còn thiếu (nghiệm thu `scripts/thu_dot2.py`, 85 PASS)

44. **Công tắc gửi tin BA trạng thái, không phải bật/tắt.** `tắt` · `nháp` ·
    `thật` (`outbound_messaging_mode`). "Nháp" là trạng thái làm việc thật sự:
    chạy đủ quy trình trên dữ liệu thật, không tin nào rời hệ thống, khách
    không bị đánh dấu "đã gửi". Gộp nó vào "tắt" là bỏ mất bước duy nhất bắt
    được lỗi trước khi tin ra ngoài.

45. **HAI lớp khoá, phải mở cả hai máy mới gửi.** Lớp 1 là `outbound_hard_lock`
    — **CỐ Ý chỉ có trong `.env`**, không bày lên màn Cài đặt: còn đóng thì tài
    khoản admin bị chiếm cũng không bắn được tin thật, mở nó phải vào được máy
    chủ. Lớp 2 là chế độ trên web. Màn hình nói thẳng cả ba con số (khoá cứng ·
    chế độ đang đặt · **thực tế đang gửi thật CÓ/KHÔNG**) thay vì để người dùng
    tự suy — đặt "THẬT" mà khoá cứng còn đóng là tình huống dễ hiểu nhầm nhất.

46. **Quyền `gui_tin.bat_cong_tac` tách khỏi `user.manage`.** Sửa nhịp worker là
    việc thường ngày; gạt sang "gửi THẬT" là quyết định không thu hồi được. Hai
    việc khác hạng thì không dùng chung một chìa. Công tắc cũng có **form
    riêng**, không đi chung nút "Lưu mục này" — nó không được là hệ quả phụ của
    việc ai đó sửa một con số rồi bấm Lưu cả mục.

47. **Ba luật vòng đời nối THẬT vào engine, không phải công tắc chết.** Mẫu để
    chúng ở dạng "ghi nhận ý muốn, engine nối sau"; bên ta nối ngay:
    `luat_giam_quyenloi_on` → `voucher_service.toan_canh()` (tắt thì đếm về **0**
    chứ không hiện số khách "đang bị giảm" trong khi chẳng ai bị gì) ·
    `voucher_first_auto_on` → đường máy tặng voucher ·
    `luat_thu_hoi_on` → **chỉ chặn đường MÁY** (`thu_hoi(may=True)`), thu hồi TAY
    ở Kho data vẫn chạy: người bấm nút đã ghi lý do và tự chịu trách nhiệm, khoá
    họ lại chỉ tổ làm khách kẹt không ai gỡ được.

48. **`voucher_first_auto_on` tách khỏi mệnh giá.** Mệnh giá `0` = **chưa cấu
    hình**; tắt công tắc = **đã cấu hình xong nhưng tạm ngưng**. Gộp làm một thì
    muốn tạm ngưng phải xoá mệnh giá, bật lại phải nhớ mà gõ lại con số.

49. **Nguồn lead vào bảng việc — làm thật chứ không phải cái nút giả.** Thêm cột
    `conversations.kind` (dịch từ `type` của Pancake), poller **chỉ kéo thêm
    COMMENT khi công tắc tắt** (mặc định bật = hành vi y hệt trước, và bật lại
    tiết kiệm một lượt gọi Pancake mỗi page mỗi vòng). Điều kiện loại lead là
    "khách KHÔNG có hội thoại inbox nào", không phải "có hội thoại bình luận" —
    khách vừa bình luận vừa nhắn tin thì vẫn còn việc. Màn Cài đặt hiện **số
    khách thật** đang bị công tắc chạm tới; một công tắc không cho thấy hậu quả
    thì không ai dám gạt.

50. **Mẫu nhận diện: bảng THÊM vào hằng trong mã, không THAY.** `phrase_patterns`
    cộng vào `tieng_viet.MAU_DA_GOI` / `MAU_CHAN_GOI` / `VIET_TAT`. Bộ nền luôn
    có hiệu lực và **admin không xoá được** — bảng rỗng thì bộ dò vẫn chạy đúng
    như trước, chứ không lặng lẽ ngừng nhận diện. Trên màn, thẻ nền vẽ **viền
    đứt, không có nút xoá**: nhìn là biết cái gì là móng.

51. **Dò có CHÈN từ lạ (`nhandien_goi_gap`, mặc định 2).** "em vừa gọi" phải bắt
    được "em vừa mới alo gọi". Mẫu được dịch thành regex có `\b` hai đầu — thiếu
    ràng buộc biên từ thì "goi" khớp vào giữa "ngoi" và mọi thống kê thành rác.

52. **Chặn mẫu MỘT TỪ ngắn ngay lúc nhập** (`nhan_dien.kiem_mau`). Khai "goi" thì
    "gợi ý" bỏ dấu thành "goi y" và khớp — lỗi kiểu này chỉ lộ ra hàng tuần sau,
    lúc có người soi lại công. `viet_tat` được miễn: viết tắt ngắn là bản chất
    của nó, và bảng bung chỉ đổi TỪ ĐỨNG RIÊNG.

53. **Nhận voucher hai kênh, không cắt giữa số.** Kênh A dò đúng mã đã phát;
    kênh B cần **đúng con số mệnh giá VÀ một từ voucher trong cùng một tin**.
    "50000" không được khớp vào "150000" — tin báo giảm 150k mà tính thành mã
    50k thì đối soát tiền sai.

54. **Kết quả soi luôn GIẢI THÍCH ĐƯỢC.** `nhan_dien.soi()` trả về khớp mẫu nào
    và vì sao; lý do xác minh công nay ghi thẳng tên mẫu đã khớp. Bác hay nhận
    công của người ta thì phải chỉ ra được đã dò cái gì.

55. **Ô 🧪 "Thử một câu" gọi JSON tại chỗ**, không nạp lại trang như mẫu — lúc
    đang chỉnh mẫu người ta thử liên tiếp cả chục câu.

56. **Bật/tắt chứ không chỉ xoá** (mẫu nhận diện · luật gợi ý). Tắt tạm là cách
    thử "bỏ cái này đi thì sao" mà không mất luôn cụm chữ đã nghĩ ra.

---

## Đợt 3 — KHUNG luồng tự động, CHƯA gửi tin (`scripts/thu_dot3.py`, 87 PASS)

> 🔴 Đây là đợt duy nhất cố ý **làm thiếu**. Người dùng chốt: dựng khung trước,
> nhưng phải **bảo đảm nó không gửi được tin**; đường gửi tự động làm kỹ sau.

57. **Chặn bằng CẤU TRÚC, không bằng lời hứa.** `services/auto_flow.py` không
    có một lời gọi gửi tin nào — không import `app.integrations`, không import
    `httpx`/`requests`. Không thể bật cái không tồn tại. Muốn gửi thật phải
    viết thêm mã, tức là một quyết định có người ký, không phải hệ quả của việc
    ai đó gạt nhầm công tắc.

58. **Chứng minh lại mỗi lần chạy test, bằng ba cách độc lập** (một cách thì dễ
    tự ru ngủ):
    * **Tầng 0 — đọc mã bằng AST.** Duyệt cây cú pháp ba file của Đợt 3, bắt
      mọi `import` và mọi lời gọi hàm; cấm `app.integrations` · `httpx` ·
      `requests` · `aiohttp` · `urllib` · `socket` và các hàm `send_message` ·
      `send_flow` · `gui_tin` · `chay_dot`. **Dò chuỗi thì không đủ**: chính câu
      cảnh báo trong docstring cũng bị tính là vi phạm, còn `send_message` viết
      tách dòng thì lọt.
    * **Tầng 1 — hành vi.** Vá MỌI hàm gửi thành "gọi là nổ", rồi chạy cả engine
      trên dữ liệu thật (khai luồng · chạy thử · bật luồng · chạy lại · chạy hết
      luồng đang bật). Kèm một phép thử ngược: gọi thẳng hàm gửi để chắc chắn
      bẫy **có tác dụng thật**, không phải vá hụt.
    * **Tầng 2 — công tắc.** Mở HẾT khoá gửi tin thường (khoá cứng mở + chế độ
      THẬT) rồi kiểm lại: chiến dịch gửi được, còn `auto_flow` **vẫn bị từ chối**.

59. **`AUTO_FLOW_HARD_LOCK` tách khỏi `OUTBOUND_HARD_LOCK`.** Hai quyết định
    khác hạng: gửi tay sai một tin thì xin lỗi một khách; luật tự động sai thì
    sai với hàng chục nghìn khách trong một đêm và không ai kịp nhận ra.

60. **Cửa gửi có luật KHÁC NHAU theo nguồn** (`cong_tac_gui_tin.xin_phep_gui`).
    `tay` **không** gác — gác thì bật công tắc an toàn của chiến dịch lên là cả
    phòng Sale không trả lời được khách. `chien_dich` cần khoá cứng mở + chế độ
    THẬT. `auto_flow` có khoá riêng, từ chối vô điều kiện. Cửa **ném lỗi** chứ
    không trả `False`: bỏ quên một `if` là tin bay ra ngoài, bỏ quên một `except`
    thì cùng lắm là báo lỗi — chọn hướng hỏng an toàn.

61. **KHÔNG port nút "Test bắn" của mẫu.** Mẫu có nút gửi thật một tin và tự
    nhận là *"vượt mọi lớp chặn lẫn công tắc"* — đúng thứ không nên tồn tại khi
    đường gửi tự động còn chưa được kiểm chứng. Thay bằng nút **Chạy thử**: chạy
    khô trên dữ liệu thật, trả lời "luật này hôm nay trúng ai, vì sao".

62. **Vì sao vẫn đáng dựng khung trước.** Chạy khô trên dữ liệu thật là cách
    **duy nhất** kiểm chứng một luật trước khi nó có quyền bắn tin. Nhật ký
    `auto_flow_runs` ghi `che_do` cố định `'kho'` — repo **không có tham số** để
    truyền `'that'` vào, nên không thể có dòng nhật ký nói dối rằng đã gửi.

63. **Catalog điều kiện CHỈ khai trường có thật.** Mẫu có vài điều kiện dựa trên
    cột bên ta không có (`ad_at`, `ngung_cham_soc`); bỏ hẳn chứ không khai rồi
    để trả rỗng — một điều kiện lúc nào cũng không khớp là cái bẫy im lặng, admin
    tưởng luật chặt mà thật ra luật chẳng lọc gì. Bài kiểm chạy **từng điều kiện
    trong catalog** trên DB thật để không có mục nào chỉ đẹp trên giấy.

64. **Luật LUÔN loại khách đã xin ngừng nhận tin**, kể cả admin không tick ô nào
    — cùng với khách đã xoá/gộp. Gửi cho người đã bảo "đừng nhắn nữa" không được
    phép xảy ra vì ai đó quên một ô tick.

66. **Đường tự động DUY NHẤT đang mở: SINH VIỆC, không gửi tin.** Máy quét
    theo luật rồi đặt một dòng vào `crm.tasks` cho người phụ trách; **người**
    vẫn đọc, **người** vẫn bấm gửi. Đây là toàn bộ giá trị của tự động hoá
    (không ai phải nhớ mốc, không ai bị bỏ sót) mà không có rủi ro của nó (tin
    sai bay tới hàng nghìn khách trước khi kịp nhận ra). Công tắc
    `auto_flow_task_enabled` mặc định **TẮT**: kéo mã về mà bảng việc cả phòng
    tự nhiên đầy việc máy đẻ ra là mất lòng tin ngay ngày đầu.

67. **Chống trùng ở DB, không ở phần mềm.** Khoá duy nhất
    `(auto_flow_id, customer_id, ngay)` trên `auto_flow_tasks` + `on conflict do
    nothing`. Kiểm-rồi-ghi phía Python vẫn lọt khi hai lượt worker chạy chồng
    nhau; chỉ ràng buộc ở DB mới chắc. Nhờ vậy worker chạy 10 lượt một ngày vẫn
    đúng 1 việc, và lượt sau thành không-làm-gì.

68. **Không nhắc lại khi việc cũ CÒN MỞ.** Nhân viên mở bảng thấy ba dòng y hệt
    cho cùng một khách thì họ ngừng tin cả bảng việc.

69. **Ba lý do bỏ qua được đếm RIÊNG** (chưa có người phụ trách · việc cũ còn mở
    · hôm nay đã sinh rồi) và bày thẳng lên màn. "Trúng 500 mà chỉ sinh 12 việc"
    mà không giải thích được thì không ai dám bật công tắc. Trên dữ liệu hiện
    tại lý do số 1 chiếm gần hết: `customer_assignments` đang rỗng, mới có 161
    lead có `owner_id`.

70. **Việc sinh ra trỏ ngược về luồng** (`related_type='auto_flows'` +
    `related_id`), nên thẻ việc trả lời được câu "việc này ở đâu ra". Phải nới
    CHECK `tasks_related_type_check` — nới bằng cách DROP rồi ADD lại ĐỦ danh
    sách, KHÔNG thêm CHECK thứ hai: hai ràng buộc trên cùng một cột thì phải
    thoả cả hai, và cái cũ sẽ chặn đúng giá trị mới.

71. **Hạn việc là CUỐI ngày hôm nay** (giờ VN), không phải "ngay bây giờ": đặt
    hạn bằng thời điểm sinh thì việc vừa ra đời đã quá hạn và worker leo thang
    bắn cảnh báo oan.

72. **Sửa được luồng đã khai** (trước chỉ thêm/xoá). Gõ sai một con số mà phải
    xoá đi khai lại là mất luôn lịch sử chạy thử của luồng đó — thứ duy nhất
    chứng minh luật từng đúng.

65. **Luật khai sai thì báo NGAY lúc lưu**, không nằm im trong bảng: route dựng
    thử câu lọc ngay sau khi ghi. Luồng sai mà im lìm chờ tới ngày chạy là thứ
    khó tìm nhất. Và luồng mới khai luôn ở trạng thái **TẮT**.

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
