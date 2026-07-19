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
│   ├── main.py             # khởi động FastAPI, đăng ký route Pancake
│   ├── config.py           # đọc .env -> settings dùng chung
│   │
│   ├── pancake/            # ⭐ tích hợp Pancake (đang dùng chính)
│   │   ├── client.py       # gọi Pancake API: list page, hội thoại, tin nhắn, gửi
│   │   ├── webview.py       # render HTML: danh sách page, người nhắn, khung chat
│   │   └── routes.py        # các endpoint /pancake/... (webview + JSON + reply)
│   │
│   ├── bot/                # "não" quyết định trả lời
│   │   ├── brain.py         # điều phối: kịch bản trước, không thì RAG + LLM
│   │   ├── flow.py          # kịch bản Bảng 1 (khung, chưa cài logic khớp)
│   │   ├── session.py       # phiên khách (⚠ lệch schema trang_thai_khach)
│   │   └── prompt.py        # ghép persona + ngữ cảnh RAG + câu hỏi
│   │
│   ├── rag/                # tìm kiếm ngữ nghĩa + sinh câu trả lời
│   │   ├── embedding.py     # vector hóa câu (OpenAI text-embedding-3-small, 1536d)
│   │   ├── retriever.py     # embed câu hỏi -> tìm cặp Q&A gần nhất
│   │   └── llm.py           # gọi LLM (OpenAI gpt-4o-mini)
│   │
│   ├── db/
│   │   ├── client.py        # kết nối Supabase (REST)
│   │   └── queries.py       # đọc/ghi bảng + insert kèm embedding + cosine
│   │
│   └── messenger/
│       └── send_api.py      # Facebook Send API (giữ lại, hiện không dùng)
│
├── ingestion/              # chạy OFFLINE để nạp dữ liệu vào DB
│   ├── load_scripts.py      # nạp kịch bản (data/kich_ban.json) -> kich_ban
│   ├── distill.py           # dùng LLM chưng cất chat -> cặp hỏi–đáp
│   └── run_ingest.py        # chat thô (data/chats.json) -> distill -> embed -> lưu
│
└── scripts/
    └── init_db.sql          # ⚠ CŨ — schema thật trong Supabase đã khác (xem dưới)
```

### Luồng trả lời (khi dùng não)

```
Tin khách ──> bot/brain ──┬── bot/flow (kịch bản) ──> trả lời luôn nếu khớp
                          │
                          └── rag/retriever ─embed─> rag/embedding
                                    │  tìm cặp Q&A gần nhất (cosine)
                                    ▼
                              db/queries ──> Supabase (hoi_thoai_mau, vector 1536)
                                    │
                                    ▼
                       bot/prompt ──> rag/llm (gpt-4o-mini) ──> câu trả lời
```

## Cấu hình `.env`

| Biến                                                                                                 | Ý nghĩa                                                                      |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `PANCAKE_ACCESS_TOKEN`                                                                              | JWT lấy từ Pancake POS (bắt buộc cho mọi tính năng Pancake)             |
| `LLM_PROVIDER=openai` · `LLM_MODEL=gpt-4o-mini`                                                  | Não LLM                                                                       |
| `OPENAI_API_KEY`                                                                                    | Key OpenAI (dùng cho cả LLM và embedding)                                   |
| `EMBEDDING_PROVIDER=openai` · `EMBEDDING_MODEL=text-embedding-3-small` · `EMBEDDING_DIM=1536` | Vector hóa;**1536 phải khớp cột `embedding` trong DB**             |
| `SUPABASE_URL` · `SUPABASE_KEY`                                                                  | `SUPABASE_KEY` = **secret key** `sb_secret_...` (chạy phía server) |
| `FB_*`, `GEMINI_API_KEY`, `DATABASE_URL`                                                        | Không bắt buộc (luồng Graph/Gemini hiện không dùng)                     |

## Database (Supabase)

> ⚠️ **`scripts/init_db.sql` đã lỗi thời** — dùng schema chuẩn dưới đây thay thế.
> Điểm khác chính: `embedding` là **`vector(1536)`**, `hoi_thoai_mau` không có
> `noi_dung`, `trang_thai_khach` dùng `page_id`/`psid`/`ngu_canh`. Code bám theo
> schema này. Các bảng đã được tạo sẵn trong project.

Tóm tắt cột: `kich_ban`(ten_kich_ban, buoc, noi_dung, dieu_kien, buoc_tiep,
**embedding vector(1536)**, meta) · `hoi_thoai_mau`(cau_hoi, cau_tra_loi, nguon,
**embedding vector(1536)**, meta) · `trang_thai_khach`(page_id, psid, kich_ban,
buoc_hien_tai, ngu_canh, trang_thai).

DB **chưa có RPC** `match_documents`, nên tìm kiếm tương đồng được tính **cosine
phía Python** (`db/queries.search_similar`) — đủ nhanh cho bảng Q&A nhỏ. Nếu muốn
dùng index HNSW cho nhanh khi dữ liệu lớn thì thêm RPC pgvector sau.

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

| Endpoint                                                            | Chức năng                                  |
| ------------------------------------------------------------------- | -------------------------------------------- |
| `GET /health`                                                     | Kiểm tra server sống (`{"status":"ok"}`) |
| `GET /docs`                                                       | Swagger UI (liệt kê toàn bộ endpoint)    |
| `GET /pancake/webview`                                            | Trang HTML danh sách Page có quyền        |
| `GET /pancake/pages`                                              | Danh sách Page dạng JSON                   |
| `GET /pancake/pages/{id}/recent?limit=10`                         | Người nhắn tin (INBOX) mới nhất         |
| `GET /pancake/pages/{id}/conversations/{conv_id}?customer_id=...` | Khung chat + ô trả lời                    |
| `POST /pancake/pages/{id}/conversations/{conv_id}/reply`          | Gửi tin trả lời (qua Pancake)             |
| `GET .../recent/fragment`, `.../{conv_id}/fragment`             | Fragment cho auto-refresh (JS gọi ngầm)    |

> **Chỉ dùng phần xem Pancake?** Chỉ cần `PANCAKE_ACCESS_TOKEN` là các trang
> `/pancake/...` chạy được — chưa cần OpenAI/Supabase. Não RAG + gửi liên quan
> mới cần thêm `OPENAI_API_KEY` và `SUPABASE_*`.

Trang danh sách người nhắn và khung chat **tự cập nhật** (auto-refresh 8–10 giây)
mà không cần F5; bấm vào một người để xem hội thoại và trả lời tay.

### Link mở nhanh (server chạy ở `http://127.0.0.1:8000`)

Các link đang hoạt động (ví dụ với page **1087376544458941 — Thạc sĩ A. Đức -
Phục Hồi Giấc Ngủ Từ Gốc**):

- Health: <http://127.0.0.1:8000/health>
- Swagger UI (mọi endpoint): <http://127.0.0.1:8000/docs>
- Danh sách Page (JSON): <http://127.0.0.1:8000/pancake/pages>
- Webview danh sách Page: <http://127.0.0.1:8000/pancake/webview>
- **Người nhắn mới nhất**: <http://127.0.0.1:8000/pancake/pages/1087376544458941/recent?limit=10>
- **Khung chat 1 khách** (ví dụ): <http://127.0.0.1:8000/pancake/pages/1087376544458941/conversations/1087376544458941_27084336667903395?customer_id=ee67b19d-c5c3-4b70-8178-0a377734fb16>

> Link khung chat là **động** (mỗi khách một `conv_id` + `customer_id`) — bình
> thường bạn **bấm từ trang "Người nhắn mới nhất"** chứ không gõ tay. Đổi page
> bằng cách thay số `1087376544458941` bằng page id khác (lấy ở `/pancake/pages`).
> `/pancake/webview` thỉnh thoảng trả **502** do Pancake giới hạn tần suất (429) —
> chờ vài giây rồi tải lại.

## Nạp/ import dữ liệu có embedding

Trong code (`app/db/queries.py`):

- `insert_qa(cau_hoi, cau_tra_loi, nguon=...)` — tự embed rồi lưu vào `hoi_thoai_mau`.
- `insert_script(noi_dung, ten_kich_ban=..., buoc=..., ...)` — lưu vào `kich_ban`.

Chạy offline từ file JSON:

```bash
python -m ingestion.load_scripts        # đọc data/kich_ban.json -> kich_ban
python -m ingestion.run_ingest          # data/chats.json -> distill (LLM) -> embed -> hoi_thoai_mau
```

## Trạng thái tính năng

| Tính năng                                                           | Trạng thái                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------- |
| Xem page / người nhắn / khung chat + trả lời tay (Pancake)       | ✅ chạy                                                      |
| Auto-refresh giao diện (poll fragment)                               | ✅ chạy                                                      |
| RAG: embed, retrieve, LLM gpt-4o-mini, insert kèm embedding, distill | ✅ đã verify                                                |
| Bot**tự động poll + gợi ý/trả lời** hội thoại          | 🟡 đã chốt thiết kế,**chưa code**                 |
| Phiên khách`trang_thai_khach` (session.py)                        | ⚠️ lệch schema thật (sender_id vs psid) — cần căn lại |
| Kịch bản Bảng 1 (`bot/flow`)                                     | ⏳ khung, chưa cài logic khớp                              |

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
