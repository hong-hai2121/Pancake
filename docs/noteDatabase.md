# GHI CHÉP DATABASE — bảng nào đang giữ thông tin gì

Sổ tay **vận hành**: dữ liệu THẬT đang nằm ở đâu, bảng nào giữ cái gì, ai ghi vào.

Khác với [DANH-SACH-BANG-VA-QUAN-HE.md](DANH-SACH-BANG-VA-QUAN-HE.md) — file đó là
**đặc tả thiết kế** đọc từ ERD (55 bảng dự kiến). File này ghi cái **đang chạy**.

> Cập nhật: 04/08/2026 · **84 bảng** — `crm` 76 · `watcher` 5 · `public` 3

---

## Database nằm ở đâu

```
Docker container  pancakebot-pg        pgvector/pgvector:pg17   127.0.0.1:5432
                  pancakebot-adminer   adminer:5                127.0.0.1:8080
   └─ database  pancakebot                                        445 MB
       ├─ schema  crm       76 bảng  ← nghiệp vụ CRM (nguồn sự thật)
       ├─ schema  watcher    5 bảng  ← kho đệm poll từ Pancake (bản sao)
       └─ schema  public     3 bảng  ← bot trả lời tự động (đời đầu)
```

- Chuỗi kết nối ở `.env` → `DATABASE_URL`, **phải dùng `127.0.0.1`** (không phải
  `localhost`, xem ghi chú trong `app/db/client.py`).
- Dựng lại từ đầu: `scripts/init_crm.sql` (idempotent — chạy lại được, dùng
  `create table if not exists` + `alter table … add column if not exists`).
- Soi bằng mắt: mở `http://127.0.0.1:8080` (Adminer), chọn DB `pancakebot`,
  schema `crm`.

---

## `crm.staff_mappings` — NHÂN SỰ BÊN PANCAKE

**Giữ cái gì:** danh sách người làm việc bên Pancake (cả POS lẫn luồng chat) và
người đó ứng với tài khoản nào trong CRM.

**Vì sao cần:** đơn hàng POS và hội thoại chỉ mang **id trần** của người xử lý
(`assigning_seller_id`, `assigning_care_id`, `assignee_ids`) — không có tên. Không
có bảng này thì màn Ánh xạ chỉ bày ra một dãy uuid, Admin không biết gán cho ai.

**Số liệu hiện tại** (04/08/2026): 149 dòng · 232 kB

| provider | dòng | có hồ sơ | ý nghĩa |
|---|---|---|---|
| `pancake_pos` | 110 | 65 | 65 người trong danh sách POS + 45 id chỉ còn trong đơn cũ (đã nghỉ) |
| `pancake_pages` | 39 | 39 | người có quyền trên các page (luồng chat) |

Gộp theo uuid: **113 con người**, trong đó 69 còn làm (36 có ở cả hai nguồn ·
30 chỉ POS · 3 chỉ chat).

### Từng cột giữ gì

| Cột | Kiểu | Giá trị lấy từ đâu |
|---|---|---|
| `id` | bigint PK | tự tăng |
| `provider` | text NN | `pancake_pos` \| `pancake_pages` (CHECK) |
| `external_staff_id` | text NN | **uuid người dùng Pancake** — khoá ghép với đơn/hội thoại |
| `external_name` | text | tên người, POS lấy `user.name`, chat lấy `name` |
| `user_id` | bigint FK→`users` | tài khoản CRM đã ghép; **rỗng = chưa ghép** |
| `role_hint` | text | vai đoán từ nơi gặp id: `seller`/`care`/`marketer`/`inbox` |
| `shop_id` | text | shop POS thấy lần cuối (api_key POS cấp theo từng shop) |
| `email` · `phone` | text | **chỉ POS có**, từ `user.email` / `user.phone_number` |
| `department` | text | **chỉ POS có** — `department.name` (SALE OCP · CSKH NT · ADS…) |
| `fb_id` · `avatar_url` | text | cả hai nguồn |
| `raw` | jsonb | nguyên văn 1 dòng API, **đã lọc bỏ api_key** |
| `last_seen_at` | timestamptz | lần cuối gặp id này ở bất kỳ đâu (kể cả trong đơn) |
| `synced_at` | timestamptz | lần cuối lấy từ **danh sách** API. **Rỗng = người đã nghỉ** (chỉ còn trong đơn/hội thoại cũ) |

**Khoá & ràng buộc**
- `UNIQUE (provider, external_staff_id)` — một người ở hai nguồn là **hai dòng**
- `FK user_id → crm.users(id) ON DELETE SET NULL` — xoá tài khoản CRM thì ánh xạ tự gỡ, không mất dòng
- `CHECK provider IN ('pancake_pages','pancake_pos')`
- Index `idx_staff_mappings_email` trên `lower(email)` — để dò ghép theo email

### Ba đường ghi vào bảng này

| Đường | Khi nào | Ghi được gì |
|---|---|---|
| `crm_sync._nhan_vien()` | đồng bộ hội thoại (nền) | **chỉ id trần** + `last_seen_at` |
| `pos_sync._nhan_vien_pos()` | đồng bộ đơn POS (nền) | **chỉ id trần** + `last_seen_at` |
| **Nút bấm tay** ở Tích hợp → Ánh xạ | Admin bấm | **hồ sơ đầy đủ** + `synced_at` |

Nút bấm tay gọi:
- `↻ Lấy NV từ POS` → `GET /shops/{shop_id}/users` (api_key theo shop) → 1 lượt gọi
- `↻ Lấy NV từ Pancake (chat)` → `GET /pages/{page_id}/users` (JWT) → **lặp từng page**

Cả hai đều ghi thêm 1 dòng `crm.sync_logs` (`entity='staff'`, `run_type='manual'`).

### Bốn luật phải nhớ

1. **KHÔNG lưu `api_key`.** Mỗi dòng nhân viên POS trả về mang api_key riêng của
   người đó. Đã lọc trước khi vào `raw` và trước khi ghi log
   (`pos_sync._BI_MAT_NHAN_VIEN`). Cùng luật với token ở màn Cài đặt.
2. **POS và chat dùng CHUNG không gian uuid.** Đo 04/08: 36 uuid nằm ở cả hai
   bảng, và `assigning_seller_id` của đơn = `user.id` của roster = `assignee_ids`
   của hội thoại. Vì vậy `gan_staff()` **lan sang mọi provider cùng uuid** — gán
   một lần ăn cả hai. ⚠ Luật này dựa vào việc mọi provider đều là Pancake; thêm
   nguồn thứ ba có id kiểu khác thì phải chặn lan lại.
3. **Ghép nhân viên KHÔNG phân công khách.** Quyền sở hữu khách theo luật riêng
   của Sale/CSKH (FR-030…032) — máy đồng bộ không được đè lên.
4. **Dữ liệu là ảnh chụp, không tự tươi.** Màn hình chỉ đọc DB, **không gọi API
   khi vẽ trang** (nếu gọi thì mỗi lần F5 là 1 lượt POS + 8 lượt pages.fm → bị
   Pancake chặn 429). Người mới vào/nghỉ bên Pancake thì phải bấm nút lấy lại;
   `synced_at` là mốc chụp lần cuối.

### Ai đọc bảng này

| Màn | Đọc gì |
|---|---|
| Quản trị → Nhân viên | cột **Ghép Pancake** (`staff_theo_user`) + khối "Nhân viên Pancake chưa ghép" (`staff_chua_ghep`) |
| Tích hợp → Ánh xạ | bảng gán nhân viên (`list_staff`) |
| Đồng bộ hội thoại | `map_staff()` → điền `conversations.assignee_user_id` |

### Câu SQL soi nhanh

```sql
-- Ai chưa ghép mà còn đang làm — ĐẾM THEO NGƯỜI.
-- distinct on là bắt buộc: người có ở cả hai nguồn là 2 dòng, bỏ distinct ra
-- 104 dòng trong khi thực tế chỉ 69 người (đúng con số màn Nhân viên hiện).
select distinct on (external_staff_id)
       external_name, department, email, phone, provider
  from crm.staff_mappings
 where user_id is null and synced_at is not null
 order by external_staff_id, (provider = 'pancake_pos') desc;

-- Một người ở mấy nguồn
select external_staff_id, array_agg(provider order by provider) nguon,
       max(external_name) ten
  from crm.staff_mappings group by 1 having count(*) > 1;

-- Lần lấy danh sách gần nhất
select provider, entity, status, created_count, updated_count, message, started_at
  from crm.sync_logs where entity = 'staff' order by started_at desc limit 5;
```

---

## `crm.sync_logs` — nhật ký mỗi mẻ đồng bộ

Mỗi lượt đồng bộ (đơn · hội thoại · tin nhắn · nhân viên…) ghi đúng 1 dòng:
`provider` · `entity` · `scope` · `run_type` · `status` · số tạo/sửa/bỏ/lỗi ·
`message` · thời gian chạy.

`entity` hợp lệ: `conversation` · `message` · `order` · `customer` · `tag` ·
`page` · `staff`.

> ⚠ **Đã vá 04/08:** `init_crm.sql` trước đây thiếu `'message'` trong CHECK dù
> `message_sync.py` ghi giá trị đó từ lâu — DB nào dựng đúng file init là gãy
> nhật ký đồng bộ tin nhắn. DB máy này không lộ vì ràng buộc đã bị gỡ tay từ trước.

## Bản đồ 3 schema — cái gì nằm ở đâu

> Đo 04/08/2026 · database `pancakebot` tổng **445 MB**

| Schema | Bảng | Của ai | Vai trò |
|---|---|---|---|
| `crm` | 76 (38 có dữ liệu) | CRM tự dựng (`scripts/init_crm.sql`) | **Nguồn sự thật** của nghiệp vụ |
| `watcher` | 5 | worker nền poll Pancake | **Kho đệm** — bản sao, xoá dựng lại được |
| `public` | 3 | bot trả lời tự động (đời đầu) | kịch bản + câu mẫu của bot |

Luật đặt tên phải nhớ: **`crm.customers` ≠ `watcher.customers`** — hai bảng khác
hẳn nhau, trùng tên. Mọi câu SQL trong repo đều ghi rõ tiền tố schema, đừng bỏ.

### `crm` — 38 bảng đang có dữ liệu

| Bảng | Dòng | Cỡ | Bảng | Dòng |
|---|---|---|---|---|
| `orders` | 53.671 | **364 MB** | `conversations` | 142 |
| `lead_attributions` | 53.706 | 15 MB | `sync_errors` | 92 |
| `order_status_history` | 53.696 | 7,6 MB | `ref_codes` | 78 |
| `customer_identities` | 37.987 | 10 MB | `role_permissions` | 76 |
| `audit_logs` | 37.826 | 14 MB | `pages` | 56 |
| `customers` | 29.597 | 7 MB | `tasks` | 24 |
| `ads` | 2.862 | 776 kB | `symptoms` | 19 |
| `messages` | 2.107 | 1,3 MB | `permissions` | 18 |
| `sync_logs` | 1.123 | 480 kB | `order_status_mappings` | 17 |
| `user_sessions` | 274 | | `care_plan_steps` · `products` · `product_versions` | 15-16 |
| `notifications` | 235 | | `users` | 14 |
| `leads` · `lead_stage_history` | 163 | | `pipeline_stages` | 13 |
| `staff_mappings` | 149 | | `roles` · `lead_reasons` | 9 |

38 bảng còn lại đang rỗng (lát cắt chưa chạy tới).

`orders` chiếm 364 MB / 445 MB — **82% cả database**, do cột `raw` giữ nguyên văn
JSON mỗi đơn POS. Cần dọn thì nhắm vào đó trước.

---

## `watcher.hoi_thoai` — KHO HỘI THOẠI PANCAKE

**Giữ cái gì:** ảnh chụp danh sách hội thoại của mọi page — tên khách, câu cuối,
số chưa đọc, thẻ, cảm xúc. Không giữ nội dung tin nhắn.

**Vì sao cần:** trước đây màn Tin nhắn gọi thẳng Pancake mỗi lần render và chỉ
giữ **20 hội thoại mới nhất toàn cục**. Với 11 page đang bật, page ít khách bị
page đông khách đẩy văng, hội thoại rơi khỏi top-20 giữa 2 lần gọi là **mất
luôn**. Có kho thì mỗi lượt poll chỉ bổ sung/cập nhật, không xoá.

**Số liệu hiện tại** (04/08/2026): **2.788 dòng · 8,4 MB**

**Khoá chính `(page_id, conv_id)`** — 1 hội thoại 1 dòng, giống cách Pancake định
danh. `conv_id` chỉ duy nhất TRONG một page, ví dụ
`1067361523117844_27584035061260887` — **không bao giờ được tra cứu bằng mỗi
`conv_id`**.

### Các cột đáng chú ý

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `updated_at` | **text** | giữ NGUYÊN chuỗi Pancake (`2026-07-30T10:54:08.907000`, không múi giờ) để so sánh/sắp xếp đúng dữ liệu gốc |
| `last_customer_at` | text | mốc tin CUỐI của khách → dùng tính **cửa gửi tin 24 giờ** của Meta. **~11% dòng bỏ trống** → màn Hội thoại phải hiện "Chưa rõ cửa", không được kết luận hết cửa |
| `snippet` | text | câu cuối, hiện ở danh sách |
| `unread_count` · `seen` | int · bool | quyết định dòng có tô đậm không |
| `tags` | jsonb `[]` | **chỉ ID số** — tên/màu tra ở `watcher.the_pancake` |
| `phones` · `has_phone` | jsonb · bool | 42/100 hội thoại KHÔNG có SĐT |
| `assignee_ids` | jsonb `[]` | uuid người phụ trách bên Pancake → ghép qua `crm.staff_mappings` |
| `sentiment` · `sentiment_method` | text | kết quả quét cảm xúc |
| `sentiment_updated_at` | text | so **BẰNG NHAU** với `updated_at` để biết "đã quét bản này chưa" — không so lớn/bé, khỏi phụ thuộc định dạng thời gian |
| `raw` | jsonb | nguyên văn ~5 kB/dòng. **Cố ý không nằm trong `_COLS`** — liệt kê 100-500 hội thoại mà kéo theo là thừa vài MB |

### Ai ghi · ai đọc

| | Ai | Ghi chú |
|---|---|---|
| Ghi | `app/workers/poller.py` | poll nền, chỉ upsert, **không xoá** |
| Đọc | màn **Tin nhắn** (`/tin-nhan`) | hộp thư gộp đọc thẳng kho |
| Đọc | màn **Hội thoại** (`/crm/hoi-thoai`) | `list_recent(100)` |
| Đọc | quét cảm xúc | `take_unscanned()` |

**Phân trang kiểu KEYSET, không phải `offset`.** Kho được cập nhật liên tục, hội
thoại vừa có tin mới nhảy lên đầu làm mọi dòng sau nó dịch một bậc — `offset`
khi đó vừa trả trùng vừa bỏ sót. Xem `before=(updated_at, conv_id)` trong
`list_recent`.

---

## `watcher.the_pancake` — TÊN + MÀU THẺ

**Giữ cái gì:** định nghĩa thẻ của từng page: `tag_id` → tên + mã màu.

**Vì sao cần:** `watcher.hoi_thoai.tags` chỉ có **ID số**. Không có bảng này thì
mọi màn hiện `Thẻ #171` thay vì `1 Phản Hồi`. Hộp thư GỘP lại đọc kho chứ không
gọi Pancake lúc render → nếu chỉ dựa vào lời gọi lúc vẽ trang thì chế độ gộp
chẳng bao giờ có tên thẻ.

**Số liệu hiện tại** (04/08/2026): **223 dòng / 10 page · 112 kB**

| Nhóm page | Số thẻ/page |
|---|---|
| 3 page `pzl_…` (Bs Hội · Bác sĩ Hội · Trung Tâm Tiêu Hoá) | 52 |
| 5 page Thạc sĩ A. Đức | 13 |
| 3 page "Chưa kích hoạt" | 0 |

**Khoá chính `(page_id, tag_id)`** — thẻ là dữ liệu RIÊNG của từng page, cùng số
ID ở 2 page là 2 thẻ khác nhau.

| Cột | Ghi chú |
|---|---|
| `ten` · `mau` | từ API; `mau` là mã hex (`#a06fdc`) |
| `updated_at` | **chỉ nhích khi tên/màu THẬT SỰ đổi** (mệnh đề `where` cuối câu upsert) — nhìn cột này biết thẻ nào vừa bị đổi tên bên Pancake, chứ không phải dấu vết lần đồng bộ gần nhất |

**KHÔNG xoá dòng của thẻ đã bị xoá trên Pancake** — hội thoại cũ vẫn gắn ID đó,
giữ lại thì còn biết thẻ ấy tên gì.

### Lấy thẻ về bằng đường nào

| Đường | Lời gọi | Phủ được | Dùng khi |
|---|---|---|---|
| `GET pages/{id}/settings` → `settings.tags` | **1**, JWT thường | **mọi page** kể cả EDIT_PROFILE | ĐƯỜNG CHÍNH |
| `generate_page_access_token` + public API `/tags` | **2**, cần quyền ADMINISTER | 3/11 page | dự phòng |

Đo thực tế 04/08: đường `settings` lấy đủ **221 thẻ/8 page trong 1,2 giây**;
đường public API chỉ với tới 156 thẻ của 3 page.

---

## `watcher.the_pancake_dong_bo` — MỐC ĐỒNG BỘ THẺ

**Giữ cái gì:** lần cuối **hỏi Pancake** về thẻ của từng page — kể cả lượt hỏi hụt.

**Vì sao cần bảng riêng, không nhét vào `the_pancake`:** hai câu hỏi khác nhau.
`the_pancake.updated_at` = *"thẻ này đổi tên lúc nào"* (chỉ nhích khi tên đổi).
Câu cần trả lời để tiết kiệm lời gọi là *"lần cuối mình HỎI page này là lúc nào"*
— không cột nào của bảng thẻ trả lời được.

Mốc **phải nằm trong DB, không phải RAM**: để trong biến thì chạy `--reload`
(restart liên tục) là reset lịch liên tục → gọi API liên tục. Đây chính là chỗ
đốt quota trước khi vá.

**Số liệu hiện tại**: 11 dòng (đủ 11 page) · 32 kB

| Cột | Ghi chú |
|---|---|
| `luc` | mốc hỏi gần nhất |
| `so_the` | lấy được mấy thẻ (0 = hụt) |
| `nguon` | `settings` \| rỗng |
| `loi` | lý do hụt, hiện ở cột cuối màn Quản trị |

**Ghi mốc CẢ KHI HỤT** — không thì 3 page chưa kích hoạt bị hỏi lại mỗi vòng poll,
mãi mãi.

**Nhịp:** `TAG_SYNC_MOI = 24 giờ`/page (`app/integrations/pancake/client.py`).
Poller ngó mỗi giờ nhưng chỉ gọi API khi có page tới hạn.

### Ai đọc / bấm tay

| Màn | Làm gì |
|---|---|
| **Quản trị → Thẻ Pancake** (`/quan-tri/the-pancake`) | xem kho, mở màn **không** sinh lời gọi nào |
| Nút **🔄 Cập nhật thẻ ngay** | `refresh_tags_all_pages(ep=True)` — bỏ qua lịch, 1 lời gọi/page |

---

## `watcher.canh_bao_tieu_cuc` — NHẬT KÝ PHÁT HIỆN TIÊU CỰC

12 dòng · 80 kB. Mỗi lần quét thấy hội thoại tiêu cực ghi 1 dòng:
`page_id` · `conv_id` · `snippet` · `cach_quet` · `tu_khoa_khop` (jsonb).
Repo: `app/db/repositories/sentiment_log.py`.

## `watcher.customers` — BẢNG CỦA EXTENSION ZPANCAKE

**0 dòng — đang không dùng.** Của extension ngoài, khoá `raw_id`. Cố ý KHÔNG
dùng chung khoá với `watcher.hoi_thoai` để hai luồng ghi không giẫm chân nhau.
⚠ Trùng tên với `crm.customers` (29.597 dòng) — luôn ghi rõ tiền tố schema.

## `public.*` — BOT TRẢ LỜI TỰ ĐỘNG (đời đầu)

| Bảng | Dòng | Giữ gì |
|---|---|---|
| `hoi_thoai_mau` | 3 | câu hỏi-đáp mẫu + embedding vector(1536) |
| `kich_ban` | 0 | kịch bản nhiều bước |
| `trang_thai_khach` | 0 | khách đang ở bước nào của kịch bản |

Dựng trong `app/db/backends/postgres_be.py`, không phải `init_crm.sql`.

---

## SQL soi nhanh

```sql
-- Bảng nào đang phình
select schemaname||'.'||relname bang, n_live_tup dong,
       pg_size_pretty(pg_total_relation_size(relid)) co
  from pg_stat_user_tables order by pg_total_relation_size(relid) desc limit 10;

-- Kho hội thoại: mỗi page bao nhiêu, mới nhất tới đâu
select page_name, count(*) so_hoi_thoai, max(updated_at) moi_nhat,
       count(*) filter (where unread_count > 0) chua_doc,
       count(*) filter (where last_customer_at is null) thieu_moc_cua
  from watcher.hoi_thoai group by 1 order by 2 desc;

-- Thẻ: page nào chưa lấy được, vì sao
select d.page_id, d.luc, d.so_the, d.nguon, d.loi, count(t.tag_id) trong_kho
  from watcher.the_pancake_dong_bo d
  left join watcher.the_pancake t using (page_id)
 group by 1,2,3,4,5 order by d.so_the;

-- Thẻ vừa bị đổi tên bên Pancake (updated_at > first_seen_at)
select page_id, tag_id, ten, mau, updated_at
  from watcher.the_pancake
 where updated_at > first_seen_at + interval '1 minute'
 order by updated_at desc;
```

---

## Ghi tiếp bảng khác ở đây

Mỗi bảng một mục, theo khuôn: *giữ cái gì · vì sao cần · từng cột lấy từ đâu ·
ai ghi vào · ai đọc · luật phải nhớ · SQL soi nhanh*.
