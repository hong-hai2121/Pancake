# KẾ HOẠCH TÁI CẤU TRÚC — từ bot Pancake sang CRM

Tài liệu này ghi lại **vì sao** dự án được sắp xếp như hiện tại và **còn phải làm gì**.
Đọc kèm 4 tài liệu nghiệp vụ trong cùng thư mục:

| File | Nội dung |
|---|---|
| [dac-ta-chuc-nang-CRM.pdf](dac-ta-chuc-nang-CRM.pdf) | 60 chức năng FR-001 → FR-182 |
| [danh-sach-man-hinh-CRM.pdf](danh-sach-man-hinh-CRM.pdf) | 80 màn hình, có đánh dấu 18 màn MVP |
| [danh-sach-api-CRM.pdf](danh-sach-api-CRM.pdf) | ~250 endpoint, có đánh dấu 17 nhóm MVP |
| [DANH-SACH-BANG-VA-QUAN-HE.md](DANH-SACH-BANG-VA-QUAN-HE.md) | 56 bảng, 6 module — đã dựng thành [scripts/init_crm.sql](../scripts/init_crm.sql) |
| [THU-TU-TRIEN-KHAI-CRM.docx](THU-TU-TRIEN-KHAI-CRM.docx) | Thứ tự thi công: Phần A nền tảng → 11 lát cắt nghiệp vụ → giai đoạn sau. Ghép 3 danh sách MVP (17 nhóm API ↔ 18 màn hình ↔ mã FR) thành một lộ trình, kèm 11 bảng ERD còn thiếu |

---

## 1. Xuất phát điểm

App ban đầu là bot trả lời tin nhắn Pancake: poll hội thoại, tra kho tri thức bằng
vector, gợi ý câu trả lời, quét cảm xúc tiêu cực. Khoảng 60 file, 5 màn hình.

Đặc tả CRM lớn hơn một bậc: 56 bảng, ~250 endpoint, 80 màn hình, thêm rule engine
liệu trình, automation KHI–NẾU–THÌ, SLA, audit log, tổng đài, Facebook Ads.

Quyết định: **giữ nguyên repo, tái cấu trúc tại chỗ** thay vì mở dự án mới. Pancake
sync, RAG và sentiment đều là thành phần của CRM; tách ra sẽ phải nhân đôi tầng dữ liệu.

## 2. Bốn vấn đề cấu trúc cần xử lý

1. **HTML sinh bằng chuỗi Python** — ~3.5k dòng cho 5 màn hình. Nhân lên 80 màn thì không quản được.
2. **Không có ranh giới API / UI** — cùng một router vừa trả HTML vừa trả JSON. Đặc tả coi API là hợp đồng riêng.
3. **Không có tầng model/migration** — 56 bảng mà quản bằng SQL thủ công sẽ vỡ.
4. **Nghiệp vụ nằm trong router** — gộp khách, chia lead, sinh mốc chăm là logic thuần, phải test được mà không cần dựng HTTP.

## 3. Cấu trúc đích

```
app/
├─ main.py            chỉ khởi động + gắn router
├─ core/              config, paths (+ sẽ có security, permissions, errors, audit…)
├─ db/
│  ├─ client.py       tạo kết nối
│  ├─ backends/       postgres · supabase (đổi nơi lưu không sửa chỗ khác)
│  ├─ repositories/   truy vấn theo từng kho
│  └─ models/         ✗ chưa có — 56 bảng CRM
├─ schemas/           ✗ chưa có — Pydantic in/out
├─ api/v1/            ✗ chưa có — REST theo đặc tả
├─ services/          ✗ chưa có — nghiệp vụ thuần, không import FastAPI
├─ automation/        ✗ chưa có — máy luật KHI–NẾU–THÌ
├─ integrations/      pancake · messenger · telegram (+ call_center, facebook_ads)
├─ ai/                llm · embedding · retriever · prompt · brain · session · flow · sentiment
├─ workers/           poller · sentiment · switch
└─ web/               shell · routes/ · views/ (→ sẽ thành templates/)
docs/                 tài liệu nghiệp vụ + kế hoạch này
scripts/              init_pg.sql (bot) · init_crm.sql (56 bảng) · migrate · backfill
ingestion/            nạp kịch bản & hội thoại mẫu vào kho RAG
```

### Bản đồ schema trong Postgres

Một database `pancakebot`, ba schema tách bạch:

| Schema | Thuộc về | Bảng |
|---|---|---|
| `public` | bot RAG | `kich_ban`, `hoi_thoai_mau`, `trang_thai_khach` |
| `watcher` | poller + quét cảm xúc | `customers`, `hoi_thoai`, `canh_bao_tieu_cuc` |
| `crm` | CRM | 56 bảng theo ERD |

⚠️ `crm.customers` (hồ sơ khách) và `watcher.customers` (hàng đợi hội thoại) **trùng tên,
khác nghĩa hoàn toàn**. Code đụng CRM phải ghi rõ tiền tố `crm.` hoặc đặt
`options='-c search_path=crm,public'` trong chuỗi kết nối.

## 4. Tiến độ

### ✅ Bước 1 — Dọn khung (xong)

Di chuyển file, sửa import, không đổi hành vi. Kiểm chứng: bảng route trùng khít
43/43 so với bản trước khi dọn.

| Từ | Sang |
|---|---|
| `app/config.py` | `app/core/config.py` |
| `app/pancake/{client,switches}.py` | `app/integrations/pancake/` |
| `app/pancake/{routes,webview}.py` | `app/web/routes/pancake.py`, `app/web/views/pancake.py` |
| `app/messenger/` | `app/integrations/messenger/` |
| `app/cam_xuc/telegram.py` | `app/integrations/telegram.py` |
| `app/cam_xuc/sentiment_engine.py` + `keywords.json` | `app/ai/sentiment.py` + `app/ai/keywords.json` |
| `app/cam_xuc/{routes,webview}.py` | `app/web/routes/sentiment.py`, `app/web/views/sentiment.py` |
| `app/rag/*` + `app/bot/*` | `app/ai/` |
| `app/ui/shell.py` | `app/web/shell.py` |
| `app/ui/{routes,webview}.py` | `app/web/routes/main.py`, `app/web/views/main.py` |
| `app/data/{routes,webview}.py` | `app/web/routes/data.py`, `app/web/views/data.py` |
| `app/db/{queries,inbox_store,sentiment_log}.py` | `app/db/repositories/` |
| `zdacta/*.pdf` + `DANH-SACH-BANG-VA-QUAN-HE.md` | `docs/` |

Sửa kèm: các file dùng `Path(__file__).resolve().parents[N]` để lần về gốc dự án nay
lấy `PROJECT_ROOT` từ [app/core/paths.py](../app/core/paths.py) — chuyển file sang thư
mục khác không còn làm sai đường dẫn một cách âm thầm.

URL **không đổi**: `/`, `/bang-dieu-khien`, `/tin-nhan`, `/khach-hang`, `/pancake/*`,
`/data/*`, `/cam-xuc/*`, `/health`, `/poller`.

### ☐ Bước 2 — Nền tảng

- SQLAlchemy models cho `crm.*` + Alembic, lấy `scripts/init_crm.sql` làm migration gốc
- `core/security.py` (JWT), `core/permissions.py`, `core/deps.py`
- Bao phản hồi `{success, data, message}` + 12 mã lỗi chuẩn của đặc tả
  (`UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `DUPLICATE_CUSTOMER`,
  `INVALID_STAGE_TRANSITION`, `MISSING_REQUIRED_DATA`, `TREATMENT_BLOCKED`,
  `CLINICAL_REVIEW_REQUIRED`, `COMPLIANCE_VIOLATION`, `INTEGRATION_ERROR`, `RATE_LIMITED`)
- Audit log (FR-180) + `Idempotency-Key` cho API tạo đơn và đồng bộ

### ☐ Bước 3 — API `/api/v1`

Làm theo đúng 17 nhóm MVP mà tài liệu API liệt kê (mục XXXV): auth · users/roles/teams ·
customers · pancake sync · conversations · pipelines · leads · consultations · tasks ·
products · treatment_templates · orders · handovers · care_plans · care_steps ·
repurchase · reports · audit.

Phần Pancake hiện có được viết lại thành `PANCAKE-001…010` thay vì route web như bây giờ.

### ☐ Bước 4 — Giao diện

Chuyển `web/views/*.py` sang template Jinja2 trong `web/templates/`, CSS trong
`web/static/`. Dựng 18 màn MVP theo danh sách màn hình.

## 5. Quy ước

- **Đặt tên**: thư mục và định danh trong code dùng tiếng Anh; chuỗi hiển thị, comment
  và docstring dùng tiếng Việt. URL giữ tiếng Việt không dấu như hiện tại.
- **`services/` không import FastAPI.** Route (web lẫn api) chỉ gọi xuống.
- **`views/` không chạm DB.** Route lấy dữ liệu sẵn rồi truyền vào.
- **Không xoá cứng dữ liệu nghiệp vụ** — theo yêu cầu kỹ thuật của đặc tả API.
