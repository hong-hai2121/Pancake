    

# FB Sales Bot

Bot bán hàng chạy trên **Pancake (pages.fm)**: xem danh sách page, đọc hội thoại
inbox, trả lời khách, và có **"não" RAG + LLM (gpt-4o-mini)** để gợi ý/soạn câu
trả lời tự nhiên.

> Không dùng webhook Facebook. Tin nhắn được lấy bằng cách **gọi (poll) API
> Pancake** định kỳ. Thư mục `app/webhook/` cũ đã bỏ; `app/messenger/` (Facebook
> Send API) vẫn giữ nhưng hiện không dùng.

## Kiến trúc

```
pancakebot/
├── .env                    # khóa API + Supabase (KHÔNG commit — đã gitignore)
├── .env.example            # mẫu các biến cần khai báo
├── requirements.txt
│
├── app/
│   ├── main.py             # khởi động FastAPI, đăng ký 3 router (ui/pancake/data)
│   ├── config.py           # đọc .env -> settings dùng chung
│   │
│   ├── ui/                 # ⭐ khung giao diện chung + 3 mục menu đầu
│   │   ├── shell.py        # menu trái + topbar + TOÀN BỘ CSS của dự án
│   │   ├── webview.py       # render Bảng điều khiển / Tin nhắn / Khách hàng
│   │   └── routes.py        # /, /bang-dieu-khien, /tin-nhan, /khach-hang
│   │
│   ├── pancake/            # ⭐ tích hợp Pancake (đang dùng chính)
│   │   ├── client.py       # gọi Pancake API: list page (cache 60s), hội thoại, gửi
│   │   ├── webview.py       # render HTML: danh sách page, người nhắn, khung chat
│   │   └── routes.py        # các endpoint /pancake/... (webview + JSON + reply)
│   │
│   ├── data/               # ⭐ giao diện tự nhập dữ liệu cho bot (menu "Dữ liệu bot")
│   │   ├── webview.py       # render 3 tab: kịch bản / hội thoại mẫu / thử tin nhắn
│   │   └── routes.py        # /data/kich-ban, /data/hoi-thoai, /data/thu-tin-nhan
│   │
│   ├── bot/                # "não" quyết định trả lời
│   │   ├── brain.py         # điều phối: kịch bản trước, không thì RAG + LLM
│   │   ├── flow.py          # kịch bản Bảng 1 (khung, chưa cài logic khớp)
│   │   ├── session.py       # phiên khách theo (page_id, psid) — đã căn schema
│   │   └── prompt.py        # ghép persona + ngữ cảnh RAG + câu hỏi
│   │
│   ├── rag/                # tìm kiếm ngữ nghĩa + sinh câu trả lời
│   │   ├── embedding.py     # vector hóa câu (OpenAI text-embedding-3-small, 1536d)
│   │   ├── retriever.py     # embed câu hỏi -> tìm cặp Q&A gần nhất
│   │   └── llm.py           # gọi LLM (OpenAI gpt-4o-mini)
│   │
│   ├── db/
│   │   ├── client.py        # kết nối Supabase (REST)
│   │   └── queries.py       # đọc/ghi bảng + insert kèm embedding + gọi RPC tìm kiếm
│   │
│   └── messenger/
│       └── send_api.py      # Facebook Send API (giữ lại, hiện không dùng)
│
├── ingestion/              # chạy OFFLINE để nạp dữ liệu vào DB
│   ├── load_scripts.py      # nạp kịch bản (data/kich_ban.json) -> kich_ban
│   ├── distill.py           # dùng LLM chưng cất chat -> cặp hỏi–đáp
│   └── run_ingest.py        # chat thô (data/chats.json) -> distill -> embed -> lưu
│
├── scripts/
│   ├── rpc_match.sql        # ⭐ tạo 2 hàm RPC tìm kiếm vector — PHẢI chạy 1 lần
│   └── init_db.sql          # ⚠ CŨ — schema thật trong Supabase đã khác (xem dưới)
│
└── supabase/functions/
    └── embed-insert/        # Edge Function — KHÔNG dùng (đã chọn chạy ở máy mình)
```

### Luồng trả lời (khi dùng não)

```
Tin khách ──> bot/brain ──┬── bot/flow (kịch bản) ──> trả lời luôn nếu khớp
                          │
                          └── rag/retriever ─embed─> rag/embedding
                                    │  RPC match_documents (Postgres tính cosine)
                                    ▼
                              db/queries ──> Supabase (hoi_thoai_mau, vector 1536)
                                    │
                                    ▼
                       bot/prompt ──> rag/llm (gpt-4o-mini) ──> câu trả lời
```

## Cấu hình `.env`

| Biến                                                                                                 | Ý nghĩa                                                                                        |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `PANCAKE_ACCESS_TOKEN`                                                                              | JWT lấy từ Pancake POS (bắt buộc cho mọi tính năng Pancake)                               |
| `LLM_PROVIDER=openai` · `LLM_MODEL=gpt-4o-mini`                                                  | Não LLM                                                                                         |
| `OPENAI_API_KEY`                                                                                    | Key OpenAI (dùng cho cả LLM và embedding)                                                     |
| `EMBEDDING_PROVIDER=openai` · `EMBEDDING_MODEL=text-embedding-3-small` · `EMBEDDING_DIM=1536` | Vector hóa;**1536 phải khớp cột `embedding` trong DB**                               |
| `SUPABASE_URL` · `SUPABASE_KEY`                                                                  | `SUPABASE_KEY` = **secret key** `sb_secret_...` (chạy phía server)                   |
| `RAG_TOP_K=5` · `RAG_MATCH_THRESHOLD=0.0`                                                        | Số kết quả lấy về · ngưỡng lọc (đặt`0.6` để "không đủ giống thì trả rỗng") |
| `RAG_SUGGEST_THRESHOLD=0.55`                                                                        | **Ngưỡng chặn (code)** cho nút **"Gợi ý trả lời"**: bỏ câu mẫu có similarity < ngưỡng **TRƯỚC** khi gọi LLM; không câu nào đạt → NO_MATCH luôn, **không tốn 1 lượt gọi model**. **PHẢI tune** trên bộ test thật (xem điểm ở trang Thử tin nhắn). `0` = tắt |
| `FB_*`, `GEMINI_API_KEY`, `DATABASE_URL`                                                        | Không bắt buộc (luồng Graph/Gemini hiện không dùng)                                       |

## Database (Supabase)

> ⚠️ **`scripts/init_db.sql` đã lỗi thời** — dùng schema chuẩn dưới đây thay thế.
> Điểm khác chính: `embedding` là **`vector(1536)`**, `hoi_thoai_mau` không có
> `noi_dung`, `trang_thai_khach` dùng `page_id`/`psid`/`ngu_canh`. Code bám theo
> schema này. Các bảng đã được tạo sẵn trong project.

Tóm tắt cột: `kich_ban`(ten_kich_ban, buoc, noi_dung, dieu_kien, buoc_tiep,
**embedding vector(1536)**, meta) · `hoi_thoai_mau`(cau_hoi, cau_tra_loi, nguon,
**embedding vector(1536)**, meta) · `trang_thai_khach`(page_id, psid, kich_ban,
buoc_hien_tai, ngu_canh, trang_thai).

### Phân chia công việc: nhập ở Python, tìm ở Postgres

| Việc                                      | Chạy ở đâu                    | Chi tiết                                                        |
| ------------------------------------------ | --------------------------------- | ---------------------------------------------------------------- |
| **Nhập dữ liệu** (tạo embedding) | **Python** (máy chạy app) | Gọi OpenAI lấy vector rồi`INSERT` qua PostgREST             |
| **Tìm kiếm** (so sánh vector)     | **Postgres**                | Gọi RPC — dùng toán tử cosine`<=>` + index **HNSW** |

Vì PostgREST **không hỗ trợ toán tử pgvector** trực tiếp, phép so sánh phải bọc
trong hàm SQL rồi gọi qua RPC (đúng cách n8n làm). Hai hàm cần có:

| Hàm RPC            | Tìm trong bảng  | Trả về                                              |
| ------------------- | ----------------- | ----------------------------------------------------- |
| `match_documents` | `hoi_thoai_mau` | id, cau_hoi, cau_tra_loi, nguon,**similarity**  |
| `match_kich_ban`  | `kich_ban`      | id, ten_kich_ban, buoc, noi_dung,**similarity** |

Cả hai nhận `(query_embedding vector(1536), match_count int, match_threshold float)`.
Tạo bằng cách chạy [scripts/rpc_match.sql](scripts/rpc_match.sql) trong SQL Editor.

**`match_threshold`** = ngưỡng lọc: chỉ trả dòng có `similarity >= ngưỡng`.
Đặt qua `RAG_MATCH_THRESHOLD` trong `.env` (mặc định `0.0` = không lọc).
Đặt `0.6` để có hành vi "không đủ giống thì trả **rỗng**" giống n8n.

### Schema chuẩn (chạy trong Supabase → SQL Editor)

```sql
-- Bật extension vector TRƯỚC mọi cột vector(...)
create extension if not exists vector;

-- Hàm tự cập nhật updated_at
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- Bảng 1: kich_ban
create table kich_ban (
    id           bigint generated always as identity primary key,
    ten_kich_ban text        not null,
    buoc         int         not null,
    noi_dung     text        not null,
    dieu_kien    text,
    buoc_tiep    int,
    embedding    vector(1536),
    meta         jsonb       not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (ten_kich_ban, buoc)
);
create index idx_kich_ban_flow on kich_ban (ten_kich_ban, buoc);
create index idx_kich_ban_embedding
    on kich_ban using hnsw (embedding vector_cosine_ops);
create trigger trg_kich_ban_updated
    before update on kich_ban
    for each row execute function set_updated_at();

-- Bảng 2: hoi_thoai_mau
create table hoi_thoai_mau (
    id           bigint generated always as identity primary key,
    cau_hoi      text        not null,
    cau_tra_loi  text        not null,
    nguon        text,
    embedding    vector(1536),
    meta         jsonb       not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);
create index idx_hoi_thoai_mau_embedding
    on hoi_thoai_mau using hnsw (embedding vector_cosine_ops);

-- Bảng 3: trang_thai_khach
create table trang_thai_khach (
    id             bigint generated always as identity primary key,
    page_id        text        not null,
    psid           text        not null,
    kich_ban       text,
    buoc_hien_tai  int,
    ngu_canh       jsonb       not null default '{}'::jsonb,
    trang_thai     text        not null default 'active',
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (page_id, psid)
);
create index idx_trang_thai_khach_lookup on trang_thai_khach (page_id, psid);
create trigger trg_trang_thai_khach_updated
    before update on trang_thai_khach
    for each row execute function set_updated_at();
```

## Supabase — file nào làm chức năng gì

### 1. Kết nối & cấu hình

| File                                | Chức năng                                                                                                                           |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `.env`                            | Khai báo`SUPABASE_URL`, `SUPABASE_KEY` (**secret key** `sb_secret_...`), `RAG_TOP_K`, `RAG_MATCH_THRESHOLD`          |
| [app/config.py](app/config.py)       | Đọc`.env` → `settings.supabase_url`, `settings.supabase_key`, `settings.rag_*`                                             |
| [app/db/client.py](app/db/client.py) | `get_supabase()` — tạo client REST dùng chung (cache 1 lần). `get_pg_pool()` nối thẳng Postgres, **chưa cài đặt** |

### 2. Đọc/ghi dữ liệu — [app/db/queries.py](app/db/queries.py) (file trung tâm)

Mọi truy vấn Supabase đều nằm ở đây.

| Nhóm                      | Hàm                                                    | Chức năng                                                                                                                               |
| -------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Tiện ích                 | `_pgvector()`                                         | Đổi list số → chuỗi`[a,b,c]` để Postgres hiểu là `vector`                                                                    |
|                            | `_rpc()`                                              | Gọi 1 hàm RPC; báo lỗi rõ nếu hàm chưa được tạo                                                                               |
|                            | `_count()`                                            | Đếm số dòng (tuỳ chọn: chỉ dòng đã có embedding)                                                                               |
| `kich_ban`               | `load_scripts()`                                      | Lấy toàn bộ kịch bản (cho bot)                                                                                                       |
|                            | `list_scripts()`                                      | Danh sách cho giao diện (**không** kéo cột embedding cho nhẹ)                                                                 |
|                            | `insert_script()`                                     | **Python gọi OpenAI** tạo embedding → `INSERT`                                                                                 |
|                            | `delete_script()`                                     | Xoá 1 bước theo id                                                                                                                     |
| `hoi_thoai_mau`          | `list_qa_pairs()`                                     | Danh sách cặp hỏi–đáp cho giao diện                                                                                                |
|                            | `insert_qa()`                                         | Embed câu hỏi →`INSERT` (text gốc lưu vào `meta.embed_text`)                                                                    |
|                            | `delete_qa()`                                         | Xoá 1 cặp theo id                                                                                                                       |
| **Tìm kiếm (RPC)** | `search_similar()`                                    | Gọi`match_documents` → **Postgres tính**, trả Q&A gần nhất                                                                  |
|                            | `search_similar_scripts()`                            | Gọi`match_kich_ban` → bước kịch bản gần nhất                                                                                    |
|                            | `debug_search()`                                      | Gọi cả 2 RPC + số liệu chẩn đoán (cho tab "Thử tin nhắn")                                                                        |
| `trang_thai_khach`       | `load_customer_state(page_id, psid)` / `upsert_customer_state(...)` | Phiên khách theo **(page_id, psid)** — ✅ đã căn đúng schema thật (`kich_ban`/`buoc_hien_tai`/`ngu_canh`/`trang_thai`), upsert `on_conflict=page_id,psid` |

### 3. SQL phải chạy trên Supabase

| File                                          | Chức năng                                                                                                                                             |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [scripts/rpc_match.sql](scripts/rpc_match.sql) | Tạo 2 hàm RPC`match_documents` + `match_kich_ban`. **Bắt buộc chạy 1 lần** trong SQL Editor, nếu không phần tìm kiếm sẽ báo lỗi |
| [scripts/init_db.sql](scripts/init_db.sql)     | ⚠️**CŨ, không dùng** — schema chuẩn nằm ở mục *Database* phía trên                                                                  |

### 4. Nơi gọi tới Supabase

| File                                                                                                       | Dùng để làm gì                                                                                                             |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| [app/data/routes.py](app/data/routes.py) · [app/data/webview.py](app/data/webview.py)                       | Giao diện`/data`: thêm/xem/xoá kịch bản & hội thoại mẫu, và tab **Thử tin nhắn** (xem RPC truy xuất ra gì) |
| [app/rag/retriever.py](app/rag/retriever.py)                                                                | Gọi`search_similar()` lấy ngữ cảnh cho bot trả lời                                                                      |
| [ingestion/load_scripts.py](ingestion/load_scripts.py) · [ingestion/run_ingest.py](ingestion/run_ingest.py) | Nạp hàng loạt từ file JSON vào 2 bảng                                                                                     |

### 5. File Supabase KHÔNG dùng

| File                                                                                | Ghi chú                                                                                                                                                                                |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [supabase/functions/embed-insert/index.ts](supabase/functions/embed-insert/index.ts) | Edge Function (để Supabase tự embed + insert). Đã cân nhắc rồi**chọn chạy ở máy mình** nên **không dùng, chưa deploy**. Giữ lại phòng khi đổi hướng |

> **Nhắc lại:** embedding **luôn** do OpenAI sinh ra — Postgres không tự tạo được.
> Khác biệt chỉ là *ai gọi OpenAI*: hiện tại là **Python ở máy bạn**.

## Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt

copy .env.example .env            # rồi điền PANCAKE_ACCESS_TOKEN, OPENAI_API_KEY, SUPABASE_*
```

## Chạy server

### Windows (PowerShell)

```powershell
$env:PYTHONUTF8=1     # để log/HTML tiếng Việt hiển thị đúng trên console
python -m uvicorn app.main:app --reload --port 8000
```

Thấy `Uvicorn running on http://127.0.0.1:8000` là chạy. Dừng bằng `Ctrl + C`.

### Linux / macOS

```bash
uvicorn app.main:app --reload --port 8000
```

## Các endpoint

| Endpoint                                                            | Chức năng                                             |
| ------------------------------------------------------------------- | ------------------------------------------------------- |
| `GET /`                                                           | Chuyển thẳng sang Bảng điều khiển                 |
| `GET /bang-dieu-khien`                                            | **Bảng điều khiển** — số liệu + cấu hình |
| `GET /tin-nhan`                                                   | **Tin nhắn** — hộp thư 2 cột (list + chat)   |
| `POST /tin-nhan/tra-loi`                                          | Gửi tin trả lời từ màn 2 cột                      |
| `POST /tin-nhan/goi-y`                                            | **Gợi ý trả lời** (RAG+LLM) cho tin cuối của khách — trả JSON, KHÔNG gửi |
| `GET /tin-nhan/fragment/list`, `.../thread`                     | Fragment auto-refresh của màn Tin nhắn               |
| `GET /khach-hang`                                                 | **Khách hàng** — bảng khách + tìm nhanh     |
| `GET /health`                                                     | Kiểm tra server sống (`{"status":"ok"}`)            |
| `GET /docs`                                                       | Swagger UI (liệt kê toàn bộ endpoint)               |
| `GET /pancake/webview`                                            | Trang HTML danh sách Page có quyền                   |
| `GET /pancake/pages`                                              | Danh sách Page dạng JSON                              |
| `GET /pancake/pages/{id}/recent?limit=10`                         | Người nhắn tin (INBOX) mới nhất                    |
| `GET /pancake/pages/{id}/conversations/{conv_id}?customer_id=...` | Khung chat + ô trả lời                               |
| `POST /pancake/pages/{id}/conversations/{conv_id}/reply`          | Gửi tin trả lời (qua Pancake)                        |
| `GET .../recent/fragment`, `.../{conv_id}/fragment`             | Fragment cho auto-refresh (JS gọi ngầm)               |
| `GET /data/kich-ban`                                              | Giao diện thêm/xem/xoá**kịch bản**           |
| `POST /data/kich-ban`                                             | Thêm 1 bước kịch bản (tự tạo embedding)          |
| `POST /data/kich-ban/{id}/xoa`                                    | Xoá 1 bước kịch bản                                |
| `GET /data/hoi-thoai`                                             | Giao diện thêm/xem/xoá**hội thoại mẫu**     |
| `POST /data/hoi-thoai`                                            | Thêm 1 cặp hỏi–đáp (tự tạo embedding)           |
| `POST /data/hoi-thoai/{id}/xoa`                                   | Xoá 1 cặp hỏi–đáp                                 |

> **Chỉ dùng phần xem Pancake?** Chỉ cần `PANCAKE_ACCESS_TOKEN` là các trang
> `/pancake/...` chạy được — chưa cần OpenAI/Supabase. Não RAG + gửi liên quan
> mới cần thêm `OPENAI_API_KEY` và `SUPABASE_*`.

Trang danh sách người nhắn và khung chat **tự cập nhật** (auto-refresh 8–10 giây)
mà không cần F5; bấm vào một người để xem hội thoại và trả lời tay.

### Giao diện web — menu bên trái

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000) là vào thẳng giao diện quản trị.
Mọi trang dùng chung một khung: **menu dọc bên trái** + thanh tiêu đề, bố cục rộng
cho màn hình máy tính (dưới 900px menu tự thu thành thanh ngang có icon).

| Mục menu                       | Đường dẫn        | Nội dung                                                                         |
| ------------------------------- | -------------------- | --------------------------------------------------------------------------------- |
| 📊**Bảng điều khiển** | `/bang-dieu-khien` | Số page, hội thoại, tin chưa đọc, kho dữ liệu bot, cấu hình đang chạy |
| 💬**Tin nhắn**           | `/tin-nhan`        | Hộp thư 2 cột: danh sách hội thoại ↔ khung chat + ô trả lời             |
| 👥**Khách hàng**        | `/khach-hang`      | Bảng khách đã nhắn (tên, FB ID, số tin, chưa đọc, lần cuối) + ô tìm |
| 🧠**Dữ liệu bot**       | `/data/kich-ban`   | 3 tab: Kịch bản · Hội thoại mẫu · Thử tin nhắn                           |

Màn **Tin nhắn** và **Bảng điều khiển** tự chọn page đang hoạt động đầu tiên; đổi
page bằng ô chọn ở góc phải trên. Danh sách hội thoại làm mới mỗi 10 giây, khung
chat mỗi 8 giây — không phải F5.

> ### ⚠️ "Tự cập nhật" chạy tới đâu — đọc kỹ chỗ này
>
> Việc làm mới nằm **hoàn toàn ở trình duyệt** (JavaScript trong tab đang mở),
> **không phải** ở server. Nghĩa là:
>
> | Câu hỏi                                       | Trả lời                                                                                                   |
> | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
> | Làm mới bao nhiêu page?                      | **Đúng 1 page** — page đang chọn trong URL. Các page khác không bị đụng tới               |
> | Thu nhỏ cửa sổ / chuyển tab khác thì sao? | **Dừng hẳn** (`if (document.hidden) return;`), quay lại mới chạy tiếp — đỡ tốn lượt API |
> | Đóng trình duyệt thì sao?                  | **Hết luôn.** Không có tiến trình nào chạy nền trên server                                  |
> | Mở 3 tab cùng lúc?                           | 3 luồng gọi**độc lập** → gấp 3 số lượt gọi Pancake                                         |
>
> **Hệ quả:** khách nhắn vào **page B** trong lúc bạn đang xem **page A** thì hệ
> thống **không biết gì cả** — không thông báo, không lưu, không đếm. Chỉ khi bạn
> tự chuyển sang page B mới thấy.
>
> Muốn theo dõi **mọi page kể cả khi không mở trình duyệt** thì cần phần
> **Bot tự động poll** (vòng lặp chạy nền trên server) — đã chốt thiết kế nhưng
> **chưa code**, xem bảng *Trạng thái tính năng*.

**Hai nguồn dữ liệu, không trộn nhau:**

```
Pancake API (pages.fm)          Supabase (Postgres + pgvector)
   tin nhắn, khách hàng            kịch bản, hội thoại mẫu, vector
        │                                    │
        ├── Bảng điều khiển ◄────────────────┤   (đọc cả 2 để hiện số liệu)
        ├── Tin nhắn                         │
        ├── Khách hàng                       │
        │                                    └── Dữ liệu bot
        └── (gửi tin trả lời)
```

Nói ngắn: **Tin nhắn + Khách hàng** chỉ nói chuyện với Pancake, **Dữ liệu bot**
chỉ nói chuyện với Supabase/OpenAI, **Bảng điều khiển** đọc cả hai.

#### 📊 Bảng điều khiển — `/bang-dieu-khien`

|                            |                                                                                                                                                                                                                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lấy dữ liệu**   | 3 khối**độc lập**: (1) Pancake — `list_pages()` + `list_conversations(limit=50)`; (2) Supabase — 4 lệnh đếm; (3) cấu hình — đọc `settings` từ `.env`, không gọi mạng                                                                                                     |
| **Xử lý**          | Tin chưa đọc =**cộng dồn** `unread_count` của mọi hội thoại. Khách gần nhất = hội thoại đầu danh sách (đã sắp mới→cũ), đổi sang chữ "5 phút trước". Tên chủ token lấy bằng cách **giải mã payload JWT tại chỗ** (`token_owner()`), không gọi API |
| **Đếm kiểu nhẹ** | `_count()` dùng `select("id", count="exact").limit(1)` — Postgres trả về **con số**, không kéo dòng nào về. Cột `embedding` (1536 số/dòng) không bao giờ bị tải                                                                                                             |
| **Chịu lỗi**       | Mỗi khối`try/except` riêng: Pancake hỏng thì khối Supabase vẫn hiện bình thường, lỗi chỉ đỏ trong đúng ô của nó — không 500 trắng màn                                                                                                                                          |
| **Ghi gì?**         | **Không ghi gì cả**, thuần đọc                                                                                                                                                                                                                                                               |
| **File**             | [app/ui/routes.py](app/ui/routes.py) → `dashboard()` · [app/ui/webview.py](app/ui/webview.py) → `render_dashboard()`                                                                                                                                                                                |

#### 💬 Tin nhắn — `/tin-nhan`

|                          |                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Cột trái**     | `GET /pages/{id}/conversations?type=INBOX` → `_normalize_conv()` rút gọn còn tên, ảnh, tin cuối, số tin, chưa đọc → **sắp theo `updated_at` giảm dần** rồi cắt 20 dòng                                                                                                                                                 |
| **Cột phải**     | Chỉ tải khi đã bấm chọn một hội thoại:`GET .../conversations/{conv_id}/messages` (**bắt buộc kèm `customer_id`**) → `_normalize_msg()` → sắp **cũ → mới**; so `from.id` với `page_id` để biết tin nào của shop (bong bóng xanh phải) hay của khách (xám trái)                                    |
| **Nội dung tin**  | Ưu tiên`original_message`; nếu không có thì bóc thẻ HTML nhưng **giữ xuống dòng** (`<br>`, `</div>` → `\n`). Ảnh/sticker hiện thumbnail, tệp khác hiện link                                                                                                                                                          |
| **Tự cập nhật** | JS gọi 2 endpoint mảnh:`/tin-nhan/fragment/list` (10s) và `/tin-nhan/fragment/thread` (8s). Nhận HTML về **so với lần trước, khác mới thay** → không nháy màn, không mất ảnh đang tải. Nhịp đầu chỉ "mồi" để so sánh. Lỗi mạng trả 502 → JS **bỏ qua nhịp đó**, giữ nguyên nội dung đang xem |
| **Gửi trả lời** | `POST /tin-nhan/tra-loi` → `send_message()` → `POST .../messages?action=reply_inbox` → redirect **303** về đúng hội thoại kèm `?sent=1` (F5 không gửi lại tin)                                                                                                                                                             |
| **Ghi gì?**       | ⚠️**Gửi tin THẬT tới khách** — chỉ khi bạn tự bấm nút Gửi. Không ghi Supabase                                                                                                                                                                                                                                                    |
| **File**           | [app/ui/routes.py](app/ui/routes.py) → `inbox()` · [app/pancake/client.py](app/pancake/client.py) → `list_conversations` / `get_conversation` / `send_message`                                                                                                                                                                              |

#### 👥 Khách hàng — `/khach-hang`

|                          |                                                                                                                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lấy dữ liệu** | **Cùng một nguồn với màn Tin nhắn** — `list_conversations(limit=100)`. Mỗi hội thoại INBOX = một khách                                                                                                                                              |
| **Xử lý**        | Đổ thẳng vào bảng: tên,`fb_id`, `message_count`, `unread_count`, `updated_at` (đổi sang "2 ngày trước", di chuột hiện giờ chính xác). Nút *Nhắn tin* dựng sẵn link kèm `conv_id` + `customer_id` để bấm là mở đúng khung chat |
| **Ô tìm nhanh**  | Lọc**ngay tại trình duyệt** bằng JS trên bảng đã tải (khớp tên + FB ID) — gõ không gọi lại server, không tốn thêm 1 lượt Pancake                                                                                                            |
| **Ghi gì?**       | Không ghi. ⚠️ Danh sách khách**chưa được lưu vào Supabase** — mỗi lần mở là đọc mới từ Pancake, nên chưa có lịch sử/ghi chú theo khách                                                                                                 |
| **File**           | [app/ui/routes.py](app/ui/routes.py) → `customers()` · [app/ui/webview.py](app/ui/webview.py) → `render_customers()`                                                                                                                                               |

#### 🧠 Dữ liệu bot — `/data/...` (3 tab)

| Tab                        | Luồng dữ liệu                                                                                                                                                                                                                                                                                                                                                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Kịch bản**       | *Xem*: `list_scripts()` đọc bảng `kich_ban`, **cố ý không lấy cột `embedding`** cho nhẹ, rồi gom nhóm theo tên kịch bản. *Thêm*: nội dung → `embed()` gọi **OpenAI** → nhận vector 1536 chiều → ghi 1 dòng kèm vector dạng literal `[0.1,0.2,…]`                                                                                                                                      |
| **Hội thoại mẫu** | Giống trên, ghi vào`hoi_thoai_mau`. Điểm khác: **vector hoá CÂU HỎI** (không phải câu trả lời) — vì lúc chạy thật ta so tin nhắn của khách với câu hỏi mẫu                                                                                                                                                                                                                                              |
| **Thử tin nhắn**   | Gõ tin giả làm khách →`embed()` → gọi **2 RPC** `match_documents` + `match_kich_ban`. Phép so sánh cosine `<=>` chạy **trong Postgres** và dùng **index HNSW** — Python chỉ gửi vector rồi nhận về kết quả đã xếp hạng sẵn (không kéo cả bảng về). Tick ô *kèm câu trả lời* hiện **2 ô để đối chiếu**: **Bước 4 — Trả lời theo toàn bộ tri thức** (`build_prompt()` để LLM **tự viết** — chỉ để đối chiếu, KHÔNG gửi khách vì có thể sửa nghĩa) và **Bước 5 — Gợi ý trả lời** (`choose_reply()` — GPT **chỉ CHỌN** 1 trong top 3 câu mẫu rồi trả **NGUYÊN VĂN** câu đã duyệt, không hợp → **NO_MATCH → không gợi ý**; đúng logic nút "Gợi ý trả lời" ở màn Tin nhắn) |

- **Chống gửi lại form**: mọi thao tác thêm/xoá đều POST rồi **redirect 303** kèm thông báo trên URL — bấm F5 sau khi thêm sẽ không tạo trùng dòng.
- **Ngưỡng lọc**: `RAG_MATCH_THRESHOLD` trong `.env`. Để `0` là luôn trả top-k; đặt `0.6` thì câu lạc đề sẽ trả **rỗng** (giống cách n8n hoạt động).
- **File**: [app/data/routes.py](app/data/routes.py) · [app/db/queries.py](app/db/queries.py) · [app/rag/](app/rag/)

#### Khung giao diện dùng chung

Cả 4 mục render **phía server** (không dùng React/Vue). [app/ui/shell.py](app/ui/shell.py)
giữ menu trái, thanh tiêu đề và **toàn bộ CSS của dự án trong một chỗ**; ba module
webview (`ui`, `pancake`, `data`) chỉ dựng phần thân rồi gọi `render_shell()`. Muốn
đổi màu/bố cục toàn site thì sửa đúng một file. Giao diện tự theo chế độ sáng/tối
của hệ điều hành.

### Link mở nhanh (server chạy ở `http://127.0.0.1:8000`)

Các link đang hoạt động (ví dụ với page **1087376544458941 — Thạc sĩ A. Đức -
Phục Hồi Giấc Ngủ Từ Gốc**):

- **Bảng điều khiển**: [http://127.0.0.1:8000/bang-dieu-khien](http://127.0.0.1:8000/bang-dieu-khien)
- **Tin nhắn (2 cột)**: [http://127.0.0.1:8000/tin-nhan](http://127.0.0.1:8000/tin-nhan)
- **Khách hàng**: [http://127.0.0.1:8000/khach-hang](http://127.0.0.1:8000/khach-hang)
- **Thử tin nhắn**: [http://127.0.0.1:8000/data/thu-tin-nhan](http://127.0.0.1:8000/data/thu-tin-nhan)
- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Swagger UI (mọi endpoint): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Danh sách Page (JSON): [http://127.0.0.1:8000/pancake/pages](http://127.0.0.1:8000/pancake/pages)
- Webview danh sách Page: [http://127.0.0.1:8000/pancake/webview](http://127.0.0.1:8000/pancake/webview)
- **Người nhắn mới nhất**: [http://127.0.0.1:8000/pancake/pages/1087376544458941/recent?limit=10](http://127.0.0.1:8000/pancake/pages/1087376544458941/recent?limit=10)
- **Khung chat 1 khách** (ví dụ): [http://127.0.0.1:8000/pancake/pages/1087376544458941/conversations/1087376544458941_27084336667903395?customer_id=ee67b19d-c5c3-4b70-8178-0a377734fb16](http://127.0.0.1:8000/pancake/pages/1087376544458941/conversations/1087376544458941_27084336667903395?customer_id=ee67b19d-c5c3-4b70-8178-0a377734fb16)
- **Nhập Kịch bản**: [http://127.0.0.1:8000/data/kich-ban](http://127.0.0.1:8000/data/kich-ban)
- **Nhập Hội thoại mẫu**: [http://127.0.0.1:8000/data/hoi-thoai](http://127.0.0.1:8000/data/hoi-thoai)

> Link khung chat là **động** (mỗi khách một `conv_id` + `customer_id`) — bình
> thường bạn **bấm từ trang "Người nhắn mới nhất"** chứ không gõ tay. Đổi page
> bằng cách thay số `1087376544458941` bằng page id khác (lấy ở `/pancake/pages`).
> Danh sách page được **nhớ đệm 60 giây** trong `app/pancake/client.py` để không
> gọi Pancake dồn dập (trước đây hay dính 429 → trang trả 502 khi mở nhiều tab).

## Nạp/ import dữ liệu có embedding

Có 3 cách, dùng cách nào cũng **tự tạo embedding** rồi ghi Supabase.

### 1. Giao diện web (dễ nhất — tự nhập tay)

Hai màn hình, chuyển qua lại bằng tab ở đầu trang:

| Màn hình                                                 | Nhập gì                                                                  | Ghi vào bảng    |
| ---------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------- |
| [`/data/kich-ban`](http://127.0.0.1:8000/data/kich-ban)   | Tên kịch bản\*, Bước\* (số), Nội dung\*, Điều kiện, Bước tiếp | `kich_ban`      |
| [`/data/hoi-thoai`](http://127.0.0.1:8000/data/hoi-thoai) | Câu hỏi\*, Câu trả lời\*, Nguồn                                      | `hoi_thoai_mau` |

(\* = bắt buộc). Dưới mỗi form là **danh sách đã có** — kịch bản gom theo tên và
sắp theo bước, hội thoại mẫu mới nhất trước — mỗi dòng có **nút ✕ xoá** (hỏi xác
nhận trước khi xoá).

Ràng buộc & báo lỗi sẵn có:

- Trùng `(tên kịch bản, bước)` → báo *"Bước này đã tồn tại trong kịch bản"*.
- Bước không phải số → báo *"bước phải là số nguyên"*.

### 2. Gọi hàm trong code (`app/db/queries.py`)

- `insert_qa(cau_hoi, cau_tra_loi, nguon=...)` — tự embed rồi lưu vào `hoi_thoai_mau`.
- `insert_script(noi_dung, ten_kich_ban=..., buoc=..., ...)` — lưu vào `kich_ban`.

### 3. Chạy offline từ file JSON (nạp hàng loạt)

```bash
python -m ingestion.load_scripts        # đọc data/kich_ban.json -> kich_ban
python -m ingestion.run_ingest          # data/chats.json -> distill (LLM) -> embed -> hoi_thoai_mau
```

## Trạng thái tính năng

| Tính năng                                                                      | Trạng thái                                                  |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Giao diện web có menu trái** (4 mục, bố cục cho máy tính)        | ✅ đã verify (8 trang, HTML hợp lệ)                       |
| Bảng điều khiển / Khách hàng / Tin nhắn 2 cột                            | ✅ đã verify                                                |
| Xem page / người nhắn / khung chat + trả lời tay (Pancake)                  | ✅ chạy                                                      |
| Auto-refresh giao diện (poll fragment)                                          | ✅ chạy —**chỉ page đang mở trên trình duyệt**  |
| Cache danh sách page 60s (tránh Pancake chặn 429)                             | ✅ đã verify (hết 502 khi mở dồn dập)                   |
| Cache **SWR** `list_conversations` (chuyển trang lần sau hết khựng)         | ✅ đã verify (trả bản cũ ngay + refresh nền, gọi đồng bộ chỉ lần đầu/ quá 10ph) |
| **Công tắc BẬT/TẮT từng page** (Bảng điều khiển → danh sách page)             | ✅ đã verify — TẮT chặn lấy+gửi tin của page đó ở MỌI nơi (guard trong `pancake/client`), lưu `page_switches.json`, mặc định BẬT |
| RAG: embed, retrieve, LLM gpt-4o-mini, insert kèm embedding, distill            | ✅ đã verify                                                |
| Tìm kiếm vector chạy**trong Postgres** (RPC + index HNSW)               | ✅ đã verify (RPC đã tạo trên DB)                       |
| Ngưỡng lọc`match_threshold` (lạc đề → trả rỗng)                       | ✅ đã verify (0.6 → 0 dòng với câu lạc đề)           |
| Giao diện tự nhập**kịch bản** &**hội thoại mẫu** (`/data`) | ✅ đã verify (thêm/xoá/báo lỗi trùng)                  |
| Nút**"Gợi ý trả lời"** trong khung chat (human-in-the-loop, không tự gửi) | ✅ đã verify (test mock: happy-path, thiếu tin, lỗi LLM không 500) |
| Bot**tự động poll + gợi ý/trả lời** hội thoại                     | 🟡 đã chốt thiết kế,**chưa code**                 |
| Phiên khách`trang_thai_khach` (session.py)                                   | ✅ đã căn theo schema thật (page_id/psid/ngu_canh) — round-trip verify trên bảng thật |
| Kịch bản Bảng 1 (`bot/flow`)                                                | ⏳ khung, chưa cài logic khớp                              |
| Tab**Thử tin nhắn** kèm câu trả lời của bot                         | ✅ đã verify (tick ô để gọi gpt-4o-mini)                |
| API`/api/chat` cho phần mềm ngoài + bảo mật API key                       | 📋 chưa làm — xem mục*Kế hoạch: mở API* ở cuối     |

## 🧭 Gợi ý lộ trình (NOTE) — nối 2 tính năng thành quy trình tự động

> **Bối cảnh:** các mảnh đã có đủ (lấy tin Pancake, "não" RAG+LLM, nạp tri thức),
> nhưng **chưa nối vào nhau và chưa chạm dữ liệu thật**. Cụ thể:
> `bot/brain.generate_reply` đã xong nhưng **không endpoint nào gọi** (mồ côi);
> `ingestion` đọc từ `data/chats.json` **chép tay**, chưa kéo từ Pancake;
> `bot/flow.next_step` còn là stub; `bot/session` ✅ **đã căn schema thật**
> (`page_id/psid/ngu_canh`) — sẵn sàng cho poll/Tầng 2.
> Thứ thiếu **không phải mảnh mới, mà là những "cây cầu"** nối mảnh sẵn có.
> Làm theo 3 tầng dưới (an toàn → tự động dần):

### Tầng 1 — nối cái đang có (nhỏ, lợi ngay, ít rủi ro) ⭐ nên làm trước

1. ✅ **ĐÃ LÀM — Nút "Gợi ý trả lời" trong khung chat `/tin-nhan`**. Bấm nút →
   `POST /tin-nhan/goi-y` lấy **tin chữ gần nhất của khách** → `bot.suggest_reply`
   (**không đụng phiên** — nút Gợi ý stateless theo thiết kế, **không gửi
   tin**) → câu gợi ý **đổ sẵn vào ô trả lời để người sửa rồi tự bấm Gửi**
   (human-in-the-loop).
   **Logic (GPT là người chọn, không phải cosine):**
   1. Nhúng câu hỏi → Supabase lấy **top 5** câu mẫu tương đồng (`hoi_thoai_mau`),
      **không cắt cứng** theo điểm cosine.
   2. Gửi câu hỏi + **top 3** câu mẫu (có đánh SỐ) lên GPT để GPT **CHỌN** câu phù
      hợp nhất (trả về SỐ). Câu gửi khách lấy **NGUYÊN VĂN** câu trả lời đã duyệt —
      **model KHÔNG được viết lại** (an toàn y tế: tránh lược vế điều kiện, đổi sắc
      thái, hay trộn câu mẫu). Model chỉ đóng vai *người chọn*, không phải *người viết*.
   3. GPT thấy **không câu nào hợp → trả `NO_MATCH` → KHÔNG gợi ý** (chỉ hiện dòng
      "Câu hỏi này chưa có trong tri thức — không gợi ý", giữ nguyên ô soạn). Output
      lạ / số ngoài phạm vi cũng coi là không gợi ý (an toàn).

   **3 lớp chặn (defense-in-depth) trong `choose_reply`:** (a) **ngưỡng code**
   `RAG_SUGGEST_THRESHOLD` (0.55, tune được) bỏ câu lạc đề **trước khi gọi LLM** —
   dưới ngưỡng thì NO_MATCH luôn, không tốn tiền; (b) model trả **JSON** `{"chon":
   <số>}` (0 = không có) nên **hết lệ thuộc so chuỗi** NO_MATCH; (c) tin khách được
   bọc trong ranh giới `<<<KHACH … KHACH>>>` + dặn model coi là **dữ liệu, không
   phải mệnh lệnh** (chống prompt injection). Câu gửi khách **luôn nguyên văn câu
   mẫu hoặc NO_MATCH** — kể cả khi khách cố "bỏ qua hướng dẫn, kê liều thuốc…".
   `RAG_SUGGEST_THRESHOLD` chỉ là bộ **sàng thô tuỳ chọn** (mặc định `0` = tắt, để
   GPT tự phán xử). Kho tri thức rỗng thì bỏ qua luôn, không gọi GPT.
   *File*: [app/bot/brain.py](app/bot/brain.py) `suggest_reply` ·
   [app/bot/prompt.py](app/bot/prompt.py) `build_suggest_prompt` ·
   [app/ui/routes.py](app/ui/routes.py) `inbox_suggest` ·
   [app/ui/webview.py](app/ui/webview.py) (nút + JS) · [app/ui/shell.py](app/ui/shell.py) (CSS).
2. **Nút "Học từ hội thoại này"** ngay trong khung chat → kéo hội thoại hiện tại
   từ Pancake → `distill` → `embed` → lưu `hoi_thoai_mau`. Chính là feature
   "nạp tri thức" **trên dữ liệu thật**, thay cho chép tay vào `chats.json`.

→ Hai nút này biến 2 tính năng rời thành **1 vòng dùng được hằng ngày**, chưa cần bot nền.

### Tầng 2 — nền cho tự động

3. ✅ **ĐÃ LÀM — Căn lại `session.py` theo schema thật** (`page_id/psid/ngu_canh`):
   `get/save/reset_session(page_id, psid, …)`, `upsert on_conflict=page_id,psid`,
   history lưu vào `ngu_canh`. `generate_reply` đổi sang `(page_id, psid, text)`.
   Đã verify round-trip trên bảng thật. (Động cơ luồng `flow.next_step` vẫn là
   việc kế tiếp.)
4. **Vòng lặp poll nền trên server** (đã chốt thiết kế, chưa code): con trỏ
   `last_seen` mỗi hội thoại để phát hiện tin mới trên **mọi page kể cả khi không
   mở trình duyệt**.
5. **Cơ chế an toàn tự-trả-lời**: gate theo `similarity` (đủ giống → gợi ý/gửi,
   lạc đề → nhường người), **không trả tin của chính shop**, chống trả trùng,
   công tắc bật/tắt từng page.

### Tầng 3 — khép vòng & mở rộng

6. **Hàng đợi duyệt (approval queue)**: bot soạn sẵn, người bấm *Duyệt/Sửa* rồi
   mới gửi — cầu nối từ tay sang tự động hoàn toàn.
7. **Vòng phản hồi tri thức**: câu người đã sửa/duyệt (mục 6) → tự thành **ứng
   viên `hoi_thoai_mau` mới** → khép kín 2 feature (khách hỏi → bot học từ chính
   câu trả lời tốt của shop).
8. **Chống trùng khi nạp tri thức**: trước khi `insert_qa`, so vector với cái đã
   có, > ngưỡng thì gộp/bỏ — tránh phình DB và **câu trả lời mâu thuẫn**.
9. **Nhật ký & thống kê bot**: tỉ lệ bot tự trả được, điểm similarity trung bình,
   số lần người ghi đè → biết tri thức đang **thiếu chỗ nào**.
10. **`/api/chat` + API key** (xem mục *Kế hoạch: mở API* ở cuối) — làm sau cùng
    khi cần cho phần mềm ngoài.

> **Khuyến nghị:** bắt đầu từ **mục 1 & 2** — đúng 2 tính năng đang muốn, nối thẳng
> vào UI đã chạy, không cần bot nền, không rủi ro gửi nhầm. Xong 2 nút đó là đã có
> vòng "trả lời theo tri thức + học từ hội thoại" chạy thật; rồi mới tính poll nền (3–5).

## Xử lý lỗi thường gặp

- **`ModuleNotFoundError: No module named 'app.webhook'`** — đã bỏ webhook; đảm bảo
  `main.py` chỉ `include_router(pancake_router)`.
- **`[WinError 10013] socket forbidden`** — cổng 8000 bị chiếm/chặn. Đổi cổng
  (`--port 8080`) hoặc giải phóng:
  ```powershell
  netstat -ano | findstr :8000
  taskkill /PID <PID> /F
  ```
- **Pancake trả `429 Too many requests`** (trang hiện 502) — gọi API quá dồn; chờ
  vài giây rồi tải lại.
- **Tiếng Việt lỗi font trên console** — đặt `$env:PYTHONUTF8=1` trước khi chạy.

## 🔒 Kế hoạch: mở API cho phần mềm ngoài gọi vào

> **Trạng thái: CHƯA LÀM** — ghi lại để triển khai sau khi xong phần chính.

### Có cần mua domain không?

**Không bắt buộc.** Tuỳ người gọi ở đâu:

| Cách                                    | Cần domain? | URL nhận được                                                                             |
| ---------------------------------------- | ------------ | --------------------------------------------------------------------------------------------- |
| Cùng mạng LAN                          | ❌           | `http://192.168.x.x:8000` (chạy `--host 0.0.0.0` + mở tường lửa)                     |
| **Cloudflare Tunnel** (miễn phí) | ❌           | `https://ngau-nhien.trycloudflare.com` — có HTTPS sẵn, đổi mỗi lần khởi động lại |
| ngrok (miễn phí)                       | ❌           | `https://xxxx.ngrok-free.app`                                                               |
| Deploy cloud (Render/Railway/Fly.io)     | ❌           | `https://tenapp.onrender.com` — **máy bạn không cần bật**                       |
| Domain riêng                            | ✅           | `https://bot.tenmien.com` — URL cố định, đẹp                                          |

Domain chỉ cần khi muốn **URL cố định, chuyên nghiệp**. Test/nội bộ thì tunnel miễn phí là đủ.

### ⚠️ Cảnh báo: hiện code KHÔNG có lớp bảo mật nào

Mọi endpoint đang mở toang. **Phơi thẳng ra Internet là rất nguy hiểm** — bất kỳ ai
biết URL đều có thể:

- 📖 Đọc toàn bộ **tin nhắn khách hàng thật** (`/pancake/.../conversations/...`)
- 📨 **Gửi tin nhắn tới khách hàng thật** qua `/reply` — không hoàn tác được
- 🗑️ Thêm/xoá dữ liệu Supabase qua `/data/...`
- 💸 **Tiêu tiền OpenAI** của bạn bằng cách spam endpoint gọi LLM

Vì token Pancake / key OpenAI / secret Supabase đều nằm phía server, người lạ gọi
endpoint là đang dùng **danh nghĩa và ví tiền của bạn**.
→ Thứ tự đúng: **thêm bảo mật trước, rồi mới mở ra ngoài.**

### Cơ chế bảo mật API — 6 lớp

**1. Xác thực — "ai đang gọi?"** (cốt lõi)

| Kiểu             | Mô tả                                         | Hợp với dự án này?                                        |
| ----------------- | ----------------------------------------------- | -------------------------------------------------------------- |
| **API Key** | Chuỗi bí mật gửi kèm mỗi request          | ✅**nên dùng** — đơn giản, đủ cho máy gọi máy |
| JWT               | Đăng nhập → cấp token có hạn (vd 1 giờ) | Thừa, hợp khi có nhiều người dùng đăng nhập          |
| OAuth             | Đăng nhập bằng Google/Facebook              | Quá nặng                                                     |

**2. Phân quyền — "được làm gì?"** → chỉ mở đúng `/api/chat` ra ngoài; `/data/...`
và khung chat Pancake **không nhận key ngoài**, chỉ chạy nội bộ.

**3. HTTPS** (bắt buộc) — chạy `http://` thì key bị gửi dạng **chữ trần**, ai đứng
giữa đường truyền cũng đọc được rồi dùng lại. Tunnel đã cho HTTPS miễn phí sẵn.

**4. Rate limit** — giới hạn vd **60 lần/phút/key**. Không có thì bị spam là
**cháy tiền OpenAI** (mỗi lần gọi tốn 1 lượt embedding + 1 lượt gpt-4o-mini).

**5. Giới hạn đầu vào** — chặn `text` quá dài (vd > 2000 ký tự) để khỏi ngốn token.

**6. Ghi log** — ai gọi (key nào), lúc nào, hỏi gì → để truy vết khi có sự cố.

### API Key hoạt động thế nào

```
1. Sinh key:      openssl rand -hex 32   →  a3f9c2e8...
2. Lưu .env:      API_KEY=a3f9c2e8...
3. Đưa key cho người kia (kênh riêng — KHÔNG dán lên chat/git)

4. Mỗi lần gọi:
   POST https://abc.trycloudflare.com/api/chat
   Header:  X-API-Key: a3f9c2e8...
   Body:    {"text": "magie uống lúc nào"}

5. Server kiểm tra header:
   ✅ khớp     → xử lý, trả {"reply": "..."}
   ❌ sai/thiếu → 401 Unauthorized, KHÔNG làm gì
```

> **Chi tiết nhỏ nhưng quan trọng:** so sánh key phải dùng
> `secrets.compare_digest`, **không** dùng `==`. Vì `==` dừng ngay khi gặp ký tự
> khác nhau — kẻ tấn công đo thời gian phản hồi có thể dò ra từng ký tự của key.

### Lỗi hay gặp — tránh

| ❌ Đừng                         | Vì sao                                                          |
| --------------------------------- | ---------------------------------------------------------------- |
| Để key trong URL`?key=abc`    | Bị ghi vào log server, lịch sử trình duyệt, header Referer |
| Commit key lên git               | Lộ vĩnh viễn — xoá rồi vẫn còn trong lịch sử git       |
| Key ngắn kiểu`123456`         | Dò ra trong vài giây                                          |
| Dùng chung 1 key cho nhiều bên | Lộ một chỗ phải đổi hết, không biết ai làm lộ         |

### Thiết kế dự kiến

Đủ và không thừa: **API Key qua header** + **HTTPS bằng tunnel** + **rate limit**

+ **chỉ mở mỗi `/api/chat`**. Khoảng 40–50 dòng, không cần thêm thư viện.

```
POST /api/chat          Header: X-API-Key: <key>
Body:  {"text": "magie uống lúc nào ạ"}
Trả:   {"reply": "Dạ uống sau ăn tối 30 phút ạ.",
        "nguon": [{"cau_hoi": "...", "similarity": 0.728}]}
```

Trả kèm `nguon` để bên gọi biết câu trả lời **dựa trên dữ liệu nào** — hoặc biết
là **không có dữ liệu** (khi ngưỡng lọc hết, `nguon` rỗng).

Việc cần quyết khi làm: dùng **một key chung** hay **mỗi bên gọi một key riêng**
(key riêng thì thu hồi từng bên được, không ảnh hưởng bên khác).

## Chạy 24/7 (dùng máy này làm server)

1. **Không cho máy ngủ:** Settings → Power → Sleep = *Never* (khi cắm điện).
2. **Phơi ra Internet** (nếu cần gọi từ xa) bằng **Cloudflare Tunnel**:
   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared tunnel --url http://localhost:8000      # test nhanh, URL ngẫu nhiên
   ```
3. **uvicorn tự chạy nền + tự bật lại khi crash** bằng NSSM:
   ```powershell
   winget install nssm
   nssm install PancakeBot
   # Path: python.exe | Startup dir: thư mục dự án
   # Arguments: -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   # Environment: PYTHONUTF8=1
   ```
