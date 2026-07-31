# FB Sales Bot

Bot bán hàng chạy trên **Pancake (pages.fm)**: xem danh sách page, đọc hội thoại
inbox, trả lời khách, và có **"não" RAG + LLM (gpt-4o-mini)** để gợi ý/soạn câu
trả lời tự nhiên.

> Không dùng webhook Facebook. Tin nhắn được lấy bằng cách **gọi (poll) API
> Pancake** định kỳ. Thư mục `app/webhook/` cũ đã bỏ; `app/messenger/` (Facebook
> Send API) vẫn giữ nhưng hiện không dùng.

## 🚀 Chạy dự án

Dự án cần **2 thứ chạy song song**: DB (Postgres trong Docker) và app (uvicorn).

### Mỗi ngày — 2 lệnh

```powershell
cd d:\Python\pancakebot
docker compose up -d                                   # 1) bật DB
$env:PYTHONUTF8=1                                      #    log tiếng Việt không lỗi font
python -m uvicorn app.main:app --reload --port 8000    # 2) chạy app (Ctrl+C để dừng)
```

Mở **http://127.0.0.1:8000** → tự nhảy vào Bảng điều khiển. Ô *"Nơi lưu dữ liệu"*
phải hiện `postgres` màu xanh; nếu đỏ là DB chưa lên.

> `docker compose up -d` chạy 1 lần là container tự bật lại mỗi khi mở máy
> (`restart: unless-stopped`), nên thường chỉ cần lệnh uvicorn. Chạy lại lệnh
> Docker cũng vô hại — đang chạy rồi thì nó không làm gì.

### Lần đầu trên máy mới — 4 bước

```powershell
# 1) Thư viện Python (cần Python 3.11+)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2) Docker Desktop — cài xong PHẢI khởi động lại máy
winget install Docker.DockerDesktop

# 3) Khoá API: copy mẫu rồi điền PANCAKE_ACCESS_TOKEN + OPENAI_API_KEY
copy .env.example .env

# 4) Bật DB — bảng + index HNSW TỰ TẠO ở lần chạy đầu, không phải chạy SQL tay
docker compose up -d
docker compose ps            # phải thấy pancakebot-pg ... (healthy)
```

Xong bước 4 thì quay lại phần "Mỗi ngày" ở trên. Có sẵn dữ liệu ở Supabase hoặc
file `.db` cũ thì chép sang bằng
[script chuyển dữ liệu](#chuyển-dữ-liệu-sẵn-có-sang).

**Linux / macOS**: giống hệt, chỉ đổi `.venv\Scripts\activate` → `source .venv/bin/activate`, bỏ dòng `$env:PYTHONUTF8=1`, và cài Docker theo cách của
hệ điều hành đó.

### Dừng lại

| Muốn gì                               | Lệnh                                        |
| --------------------------------------- | -------------------------------------------- |
| Tắt app                                | `Ctrl + C` ở cửa sổ đang chạy uvicorn |
| Tắt DB (dữ liệu**vẫn còn**)  | `docker compose down`                      |
| Tắt DB +**XOÁ SẠCH** dữ liệu | `docker compose down -v`                   |

### Cổng nào đang dùng gì

| Địa chỉ                      | Là gì                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------ |
| http://127.0.0.1:8000           | App (uvicorn) — giao diện chính                                                               |
| `127.0.0.1:5432`              | Postgres (container`pancakebot-pg`) — **cổng thuần TCP, mở bằng trình duyệt KHÔNG ra gì** |
| http://127.0.0.1:8080/?pgsql=db | Adminer xem DB —**không tự bật**, xem [Xem dữ liệu trong DB](#xem-dữ-liệu-trong-db) |

### App đang chạy thì vào link nào

Vào thẳng **http://127.0.0.1:8000** là được — nó tự chuyển sang Bảng điều khiển.
Còn lại đi bằng menu bên trái, hoặc gõ thẳng:

| Trang                                        | Link                                                                        | Làm gì ở đó                                                                       |
| ---------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Bảng điều khiển                          | [/bang-dieu-khien](http://127.0.0.1:8000/bang-dieu-khien)                     | Số liệu tổng quan, BẬT/TẮT từng page, xem cấu hình đang chạy                |
| Tin nhắn                                    | [/tin-nhan](http://127.0.0.1:8000/tin-nhan)                                   | Hộp thư 2 cột: trả lời khách, gợi ý trả lời, trích tri thức                  |
| Khách hàng                                 | [/khach-hang](http://127.0.0.1:8000/khach-hang)                               | Bảng khách đã nhắn tin, có ô tìm nhanh                                         |
| Cảm xúc                                    | [/cam-xuc](http://127.0.0.1:8000/cam-xuc)                                     | Công tắc quét tiêu cực, từ khoá, **sổ cảnh báo vĩnh viễn**              |
| Dữ liệu bot                                | [/data/kich-ban](http://127.0.0.1:8000/data/kich-ban)                         | Kịch bản, hội thoại mẫu, thử tin nhắn, thử API                                |
| API docs                                     | [/docs](http://127.0.0.1:8000/docs)                                           | Swagger tự sinh — bấm "Try it out" gọi thử được luôn                          |
| Adminer (xem DB)                             | [:8080/?pgsql=db](http://127.0.0.1:8080/?pgsql=db)                            | Server `db` · user `postgres` · pass `postgres` · database `pancakebot`      |

> Chạy `--port 8001` thì đổi số 8000 trong mọi link trên thành 8001.

### Chạy không lên thì xem đây

| Triệu chứng                                              | Nguyên nhân & cách sửa                                                                                                           |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `Không nối được Postgres (...)`                     | DB chưa bật →`docker compose up -d`, kiểm tra `docker compose ps` thấy `healthy`                                          |
| Treo ~10 giây rồi mới báo lỗi                         | `DATABASE_URL` đang để `localhost` → đổi thành **`127.0.0.1`** (Docker chỉ nghe IPv4)                            |
| `error while attaching to network` / lệnh docker đứng | Docker Desktop chưa chạy — mở app Docker Desktop lên trước                                                                    |
| `[Errno 10048] address already in use`                   | Cổng 8000 đang bận → chạy`--port 8001`                                                                                        |
| `ModuleNotFoundError: psycopg`                           | Chưa`pip install -r requirements.txt` (hoặc quên `activate` venv)                                                             |
| `KHÔNG có extension pgvector`                          | Đang dùng Postgres cài tay thiếu pgvector → dùng image`pgvector/pgvector:pg17` trong [docker-compose.yml](docker-compose.yml) |

## Kiến trúc

```
pancakebot/
├── .env                    # khóa API + chọn nơi lưu dữ liệu (KHÔNG commit — đã gitignore)
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
│   ├── db/                  # đổi nơi lưu dữ liệu bằng DB_BACKEND, không sửa code
│   │   ├── queries.py       # ⭐ API dùng chung — mọi nơi khác chỉ import từ đây
│   │   ├── client.py        # tạo kết nối (pool psycopg / client Supabase)
│   │   └── backends/
│   │       ├── base.py         # hợp đồng chung mọi backend phải theo
│   │       ├── postgres_be.py  # ⭐ Postgres + pgvector trên máy này (mặc định)
│   │       └── supabase_be.py  # Postgres cloud, tìm kiếm qua RPC (dự phòng)
│   │
│   └── messenger/
│       └── send_api.py      # Facebook Send API (giữ lại, hiện không dùng)
│
├── ingestion/              # chạy OFFLINE để nạp dữ liệu vào DB
│   ├── load_scripts.py      # nạp kịch bản (data/kich_ban.json) -> kich_ban
│   ├── distill.py           # dùng LLM chưng cất chat -> cặp hỏi–đáp
│   └── run_ingest.py        # chat thô (data/chats.json) -> distill -> embed -> lưu
│
├── docker-compose.yml       # ⭐ bật Postgres + pgvector trên máy: docker compose up -d
│
├── scripts/
│   ├── init_pg.sql          # schema Postgres local (app tự tạo, file này để tham khảo)
│   ├── rpc_match.sql        # 2 hàm RPC tìm kiếm — CHỈ cần cho backend supabase
│   ├── migrate_supabase_to_postgres.py  # chép dữ liệu cloud -> Postgres máy mình
│   └── migrate_sqlite_to_postgres.py    # cứu dữ liệu từ file .db cũ (chạy 1 lần)
│
└── supabase/functions/
    └── embed-insert/        # Edge Function — KHÔNG dùng (đã chọn chạy ở máy mình)
```

### Luồng trả lời (khi dùng não)

```
Tin khách ──> bot/brain ──┬── bot/flow (kịch bản) ──> trả lời luôn nếu khớp
                          │
                          └── rag/retriever ─embed─> rag/embedding
                                    │  tìm cosine trên hoi_thoai_mau (vector 1536)
                                    ▼
                              db/queries ──> db/backends ──┬─ postgres (pgvector, máy mình)
                                    │                      └─ supabase (pgvector qua RPC)
                                    │
                                    ▼
                       bot/prompt ──> rag/llm (gpt-4o-mini) ──> câu trả lời
```

## Cấu hình `.env`

| Biến                                                                                                 | Ý nghĩa                                                                                                                                                                                                                                                                                                                         |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PANCAKE_ACCESS_TOKEN`                                                                              | JWT lấy từ Pancake POS (bắt buộc cho mọi tính năng Pancake)                                                                                                                                                                                                                                                                |
| `LLM_PROVIDER=openai` · `LLM_MODEL=gpt-4o-mini`                                                  | Não LLM                                                                                                                                                                                                                                                                                                                          |
| `OPENAI_API_KEY`                                                                                    | Key OpenAI (dùng cho cả LLM và embedding)                                                                                                                                                                                                                                                                                      |
| `EMBEDDING_PROVIDER=openai` · `EMBEDDING_MODEL=text-embedding-3-small` · `EMBEDDING_DIM=1536` | Vector hóa;**1536 phải khớp cột `embedding` trong DB**                                                                                                                                                                                                                                                                |
| `DB_BACKEND=postgres` · `DATABASE_URL`                                                           | Nơi lưu dữ liệu. Mặc định Postgres trên máy:`postgresql://postgres:postgres@127.0.0.1:5432/pancakebot` (**127.0.0.1**, không phải `localhost`)                                                                                                                                                               |
| `SUPABASE_URL` · `SUPABASE_KEY`                                                                  | Chỉ cần khi`DB_BACKEND=supabase`. `SUPABASE_KEY` = **secret key** `sb_secret_...` (chạy phía server)                                                                                                                                                                                                              |
| `RAG_TOP_K=5` · `RAG_MATCH_THRESHOLD=0.0`                                                        | Số kết quả lấy về · ngưỡng lọc (đặt`0.6` để "không đủ giống thì trả rỗng")                                                                                                                                                                                                                                  |
| `RAG_SUGGEST_THRESHOLD=0.55`                                                                        | **Ngưỡng chặn (code)** cho nút **"Gợi ý trả lời"**: bỏ câu mẫu có similarity < ngưỡng **TRƯỚC** khi gọi LLM; không câu nào đạt → NO_MATCH luôn, **không tốn 1 lượt gọi model**. **PHẢI tune** trên bộ test thật (xem điểm ở trang Thử tin nhắn). `0` = tắt |
| `FB_*`, `GEMINI_API_KEY`                                                                          | Không bắt buộc (luồng Graph/Gemini hiện không dùng)                                                                                                                                                                                                                                                                        |

## Database — schema 3 bảng

> Schema dưới đây là **nguồn sự thật**: `embedding` là **`vector(1536)`**,
> `hoi_thoai_mau` **không** có `noi_dung`, `trang_thai_khach` dùng
> `page_id`/`psid`/`ngu_canh`. Backend `postgres` **tự tạo** đúng schema này ở
> lần chạy đầu (bản SQL đọc được ở [scripts/init_pg.sql](scripts/init_pg.sql));
> trên Supabase thì các bảng đã tạo sẵn từ trước.

Tóm tắt cột: `kich_ban`(ten_kich_ban, buoc, noi_dung, dieu_kien, buoc_tiep,
**embedding vector(1536)**, meta) · `hoi_thoai_mau`(cau_hoi, cau_tra_loi, nguon,
**embedding vector(1536)**, meta) · `trang_thai_khach`(page_id, psid, kich_ban,
buoc_hien_tai, ngu_canh, trang_thai).

> **Tên cột, kiểu cột giống hệt nhau ở cả hai backend** — cùng là Postgres +
> pgvector, chỉ khác chỗ đặt (máy mình / cloud) và cách nói chuyện (psycopg /
> REST).

### Phân chia công việc: nhập ở Python, tìm ở tầng lưu trữ

| Việc                                      | Chạy ở đâu                    | Chi tiết                                                                                                                              |
| ------------------------------------------ | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Nhập dữ liệu** (tạo embedding) | **Python** (máy chạy app) | Gọi OpenAI lấy vector rồi`INSERT` — giống nhau ở mọi backend                                                                  |
| **Tìm kiếm** (so sánh vector)     | **Postgres**                | Cosine`<=>` + index **HNSW** chạy trong DB · `postgres`: SQL thẳng qua psycopg · `supabase`: phải bọc trong hàm RPC |

Phần dưới của mục này chỉ áp dụng cho `DB_BACKEND=supabase`.

Vì PostgREST **không hỗ trợ toán tử pgvector** trực tiếp, phép so sánh phải bọc
trong hàm SQL rồi gọi qua RPC (đúng cách n8n làm). Hai hàm cần có:

| Hàm RPC            | Tìm trong bảng  | Trả về                                              |
| ------------------- | ----------------- | ----------------------------------------------------- |
| `match_documents` | `hoi_thoai_mau` | id, cau_hoi, cau_tra_loi, nguon,**similarity**  |
| `match_kich_ban`  | `kich_ban`      | id, ten_kich_ban, buoc, noi_dung,**similarity** |

Cả hai nhận `(query_embedding vector(1536), match_count int, match_threshold float)`.
Tạo bằng cách chạy [scripts/rpc_match.sql](scripts/rpc_match.sql) trong SQL Editor.

> Backend `postgres` **không cần** 2 hàm này: nối thẳng bằng psycopg nên chạy
> được `<=>` ngay trong câu `SELECT` (xem `_match()` trong
> [postgres_be.py](app/db/backends/postgres_be.py)) — cùng công thức, cùng index.

**`match_threshold`** = ngưỡng lọc: chỉ trả dòng có `similarity >= ngưỡng`.
Đặt qua `RAG_MATCH_THRESHOLD` trong `.env` (mặc định `0.0` = không lọc).
Đặt `0.6` để có hành vi "không đủ giống thì trả **rỗng**" giống n8n.

### Schema chuẩn (backend `postgres`: app tự tạo; backend `supabase`: chạy trong SQL Editor)

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

## Nơi lưu dữ liệu: Postgres + pgvector trên máy này

| `DB_BACKEND`                       | Lưu ở đâu            | Cần cài gì                    | Tìm kiếm tương đồng                              |
| ------------------------------------ | ------------------------ | -------------------------------- | ------------------------------------------------------ |
| `postgres` **(mặc định)** | Postgres ngay trên máy | Docker (image có sẵn pgvector) | pgvector + index**HNSW**, SQL thẳng qua psycopg |
| `supabase`                         | Postgres cloud           | tài khoản Supabase             | pgvector + index HNSW, gọi qua**RPC**           |

Cả hai đều là Postgres + pgvector nên **cùng schema, cùng công thức cosine, cùng
kết quả**; đổi qua lại chỉ bằng 1 dòng `.env` (backend `sqlite` cũ đã bị bỏ).

### Bật DB — 3 bước

```powershell
# 1) Bật Postgres (lần đầu tự tải image ~150 MB, dữ liệu nằm trong volume `pgdata`)
docker compose up -d

# 2) .env trỏ vào đó (đã có sẵn giá trị này trong .env.example)
#    DB_BACKEND=postgres
#    DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/pancakebot

# 3) Chạy app — bảng + index HNSW TỰ TẠO ở lần chạy đầu
python -m uvicorn app.main:app --reload --port 8000
```

> ⚠️ **Dùng `127.0.0.1`, đừng dùng `localhost`.** Docker chỉ nghe trên IPv4
> (`127.0.0.1:5432`), còn Windows phân giải `localhost` ra `::1` **trước** →
> kết nối treo cho tới khi hết `connect_timeout`. Pool đã đặt sẵn timeout để
> báo lỗi rõ thay vì đứng im, nhưng cứ để `127.0.0.1` cho khỏi chậm.

Kiểm tra nhanh: `docker compose ps` (phải thấy `healthy`), rồi vào
`/bang-dieu-khien` — ô "Nơi lưu dữ liệu" hiện `postgres` kèm chuỗi kết nối đã che
mật khẩu.

### Xem dữ liệu trong DB

```powershell
# 1) Dòng lệnh — nhanh nhất, không cài gì
docker compose exec db psql -U postgres -d pancakebot
#    trong psql:  \dt   \d hoi_thoai_mau   select id, cau_hoi from hoi_thoai_mau;   \q

# 2) Giao diện web Adminer (đã cấu hình sẵn, chỉ bật khi cần)
docker compose --profile ui up -d
#    mở http://127.0.0.1:8080/?pgsql=db  · user postgres / pass postgres / db pancakebot
#    tắt: docker compose stop adminer
```

Cách 3: dùng app desktop ([DBeaver](https://dbeaver.io/), pgAdmin, TablePlus) hoặc
extension PostgreSQL của VS Code — kết nối `127.0.0.1:5432`, db `pancakebot`,
user/pass `postgres`/`postgres`.

> Cột `embedding` có 1536 số nên nhìn bằng mắt vô nghĩa; muốn xem cho gọn thì
> `select id, cau_hoi, vector_dims(embedding) from hoi_thoai_mau;`

Không dùng Docker cũng được: cài Postgres 14+ bất kỳ **đã có extension pgvector**,
tạo 1 database rỗng rồi sửa `DATABASE_URL` cho khớp. Nếu user của app không có
quyền `create extension` thì chạy tay [scripts/init_pg.sql](scripts/init_pg.sql)
bằng tài khoản superuser trước.

### Lệnh Docker hay dùng

| Lệnh                                                     | Làm gì                                                               |
| --------------------------------------------------------- | ---------------------------------------------------------------------- |
| `docker compose up -d`                                  | Bật DB (tự bật lại khi mở máy nhờ`restart: unless-stopped`)   |
| `docker compose ps`                                     | Xem trạng thái — phải thấy`healthy`                             |
| `docker compose logs -f db`                             | Xem log Postgres                                                       |
| `docker compose down`                                   | Tắt container —**dữ liệu vẫn còn** trong volume `pgdata` |
| `docker compose down -v`                                | Tắt +**XOÁ SẠCH** dữ liệu                                   |
| `docker compose exec db psql -U postgres -d pancakebot` | Mở psql để chạy SQL tuỳ ý                                        |

Sao lưu / khôi phục:

```powershell
docker compose exec -T db pg_dump -U postgres pancakebot > data\backup.dump.sql
docker compose exec -T db psql -U postgres -d pancakebot < data\backup.dump.sql
```

### Kho hội thoại + quét tiêu cực chạy nền (`watcher.hoi_thoai`)

Hai worker trong [app/workers/](app/workers/) được bật ở `lifespan` của
[app/main.py](app/main.py), nên **chạy suốt lúc server sống, không cần ai mở
trình duyệt**:

```
mỗi 20s ┌─ poller ────────────────────────────────────────────────┐
        │ 22 page đang BẬT × 20 hội thoại mới nhất (song song ≤5)  │
        │        upsert theo khoá (page_id, conv_id)               │
        └──────────────► watcher.hoi_thoai ◄──────────────────────┘
mỗi 8s  ┌─ sentiment ─────────────────────────────────────────────┐
        │ lấy ≤10 dòng có updated_at ≠ sentiment_updated_at        │
        │ ZPancake sentiment.analyze() -> ghi kết quả + Telegram   │
        └─────────────────────────────────────────────────────────┘
```

**Giải quyết đúng 2 vấn đề cũ** của hộp thư gộp:

- Trước đây trộn xong **cắt còn 20 toàn cục** → page ít khách bị đẩy văng, và
  hội thoại rơi khỏi top-20 giữa 2 lần gọi thì mất hẳn. Nay mỗi page đều được
  kéo đủ 20 hội thoại **của chính nó** mỗi vòng, và kho chỉ **bổ sung/cập nhật**,
  không xoá → không bỏ sót.
- Màn Tin nhắn giờ **đọc từ kho** (1 câu SELECT, hiện tới 500 dòng qua
  `?limit=`), không gọi Pancake lúc render. Kho rỗng (worker vừa bật, hoặc
  `INBOX_POLL_ENABLED=false`) thì tự quay về cách gọi trực tiếp như cũ.

**5 van giảm tải** (Pancake trả `429` chỉ sau vài lời gọi liên tiếp — bản đầu
tiên của worker bắn 22 request/20 giây ≈ **95.000 request/ngày**, gần như toàn
nhận về dữ liệu cũ):

| Van                   | Cách làm                                                                                                        | Đo được                                      |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| Bỏ qua sớm          | Nhớ`updated_at` mới nhất mỗi page (`moc`); không dòng nào mới hơn mốc → **không đụng DB** | phần lớn lượt: 0 dòng ghi thay vì 322      |
| Chỉ ghi dòng đổi  | `on conflict ... where updated_at is distinct from excluded.updated_at`                                         | khỏi ghi WAL vô ích                           |
| Nhịp thích ứng     | Có tin → 20s · im lặng → gấp đôi mỗi lượt tới trần**300s**                                     | quan sát thật: 40/80/160 → 300                |
| Ngắt mạch page lỗi | Lỗi liên tiếp 3 lượt → nghỉ**30 phút**                                                              | 3 page vô hiệu hoá nằm im ở 1800s           |
| Xin ít + catch-up    | Mỗi lượt xin**5**; cả 5 đều mới hơn mốc (nghi sót) mới leo lên 20 → 50                         | 18 page tới hạn = đúng**18 lời gọi** |

Mốc `updated_at` còn được **nạp lại từ kho lúc khởi động**
(`max_updated_at_by_page`) — không có bước này thì mỗi lần `--reload` restart,
cả 22 page lại phải leo thang 5→20→50 ≈ 55 lời gọi chỉ để lấy về thứ đã có.

Kết quả: lúc mọi page im lặng còn **~4 request/phút ≈ 5.600/ngày** (giảm ~94%);
page nào có khách nhắn thì tự về nhịp 20s ngay lượt kế tiếp. Đánh đổi duy nhất:
page đang im lặng phát hiện tin mới chậm nhất 300s.

Page bị Pancake vô hiệu hoá chỉ làm hỏng lượt của chính nó, không ảnh hưởng page
khác. Xem nhịp hiện tại của từng page ở `GET /poller` → `nhip_tung_page`.

Phần quét cảm xúc **dùng lại nguyên bộ não của ZPancake** —
[sentiment.py](ZPancake/server/sentiment.py) + [telegram.py](ZPancake/server/telegram.py)
— nên `keywords.json` vẫn là nguồn duy nhất (sửa bằng GUI "Quản lý từ khoá tiêu
cực" là cả hai bên ăn theo), tin báo Telegram giữ nguyên định dạng. Hội thoại
tiêu cực hiện badge **⚠ tiêu cực** ngay trên thẻ ở màn Tin nhắn.

**Giao diện: menu trái → "Cảm xúc"** (`/cam-xuc`) — [app/cam_xuc/](app/cam_xuc/):

| Khu vực                         | Làm gì                                                                                                                                                                                                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Công tắc**             | BẬT/TẮT worker quét ngay lúc đang chạy (**không cần restart**); TẮT thì hội thoại vẫn được kéo về kho, chỉ ngừng quét                                                                                                                  |
| **Cách quét**            | Đổi giữa`Từ khoá` (miễn phí, chạy tại máy) và `LLM (OpenAI)` (chính xác hơn, mỗi hội thoại mới tốn 1 lượt gọi)                                                                                                                          |
| **Quét lại**             | Xoá dấu đã quét của hội thoại CHƯA từng tiêu cực → worker quét lại theo danh sách từ khoá mới (hội thoại đã tiêu cực giữ nguyên, khỏi báo Telegram trùng)                                                                           |
| **Số liệu**              | Hội thoại trong kho · đã quét · đang chờ · tiêu cực                                                                                                                                                                                                   |
| **Hội thoại tiêu cực** | Danh sách kèm nút**Mở hội thoại →** nhảy thẳng vào đúng cuộc chat ở màn Tin nhắn                                                                                                                                                            |
| **Từ khoá tiêu cực**   | Thêm 1 từ · xoá từng chip · hoặc mở "Sửa hàng loạt" dán cả danh sách (mỗi dòng 1 từ, tự bỏ dòng trống + trùng). Ghi thẳng vào`keywords.json` — **dùng chung** với app Pancake Watcher, có hiệu lực ngay không cần restart |
| **Báo Telegram**          | Hiện đã cấu hình hay chưa (kèm chat id) + nút**Gửi tin thử** — bấm là bắn 1 tin đúng bố cục cảnh báo thật, sai token/chat id sẽ hiện nguyên văn lý do Telegram từ chối                                                          |
| **Nhật ký quét**        | 25 lượt quét gần nhất — nhìn là biết worker có đang chạy hay không                                                                                                                                                                                   |

**Báo Telegram khi có hội thoại tiêu cực**: điền `TELEGRAM_BOT_TOKEN` +
`TELEGRAM_CHAT_ID` vào `.env` **gốc** (thiếu 1 trong 2 = tắt hẳn, không gửi và
cũng không báo lỗi). Hai biến này **dùng chung** cho cả app chính lẫn ZPancake —
GUI "Pancake Watcher" đọc/ghi thẳng vào `.env` gốc, có nút *Gửi thử Telegram* để
kiểm tra đường dây. Muốn ZPancake bắn sang kênh khác thì khai lại trong
`ZPancake/server/.env` (file này nạp sau nên ghi đè).

Trạng thái công tắc lưu ở `sentiment_switch.json` (đã gitignore) nên giữ qua các
lần khởi động; worker đọc lại **mỗi vòng lặp** nên bấm nút là có tác dụng trong
≤ 8 giây. Giá trị mặc định khi chưa bấm lần nào = `SENTIMENT_ENABLED` /
`SENTIMENT_METHOD` trong `.env`.

**Xem worker đang làm gì** — 2 cách nữa (ngoài trang trên):

```
# 1) Log ngay trên console chạy uvicorn (chỉ in khi CÓ tin mới hoặc CÓ lỗi)
[poller] 22 page · 322 hội thoại · 1 mới · 3 lỗi · 0.84s
[poller]   + MỚI · Bác sĩ Hội · Nguyễn Hoàn: dạ
[poller]   ✗ LỖI · Thạc sĩ Hội Chuyên Gia Tiêu Hoá: PancakeError: Trang này đã bị vô hiệu hóa
[sentiment] ⚠ TIÊU CỰC · Ths Dr. Bách Hội · Nguyễn Hồng Hải: vô trách nhiệm
```

```
# 2) Mở trên trình duyệt — xem lại được cả khi server chạy nền, không cần console
http://127.0.0.1:8000/poller
```

`/poller` trả JSON gồm: vòng chạy gần nhất của cả 2 worker (`tin_moi`,
`loi_chi_tiet`), số liệu kho (`tong` / `da_quet` / `tieu_cuc` / `cho_quet`) và
danh sách hội thoại **tiêu cực đang có trong kho**.

Truy vấn thẳng khi cần:

```sql
-- hội thoại mới vào kho gần đây
select page_name, name, snippet, first_seen_at from watcher.hoi_thoai
order by first_seen_at desc limit 20;
-- tất cả hội thoại tiêu cực
select page_name, name, snippet, sentiment_method from watcher.hoi_thoai
where sentiment = 'negative' order by updated_at desc;
```

Điều chỉnh nhịp/chi phí trong `.env`: `INBOX_POLL_INTERVAL`, `INBOX_POLL_LIMIT`,
`SENTIMENT_INTERVAL`, `SENTIMENT_BATCH` (đặt `SENTIMENT_METHOD=llm` trong
`ZPancake/server/.env` thì mỗi hội thoại mới tốn 1 lượt gọi OpenAI — canh
`SENTIMENT_BATCH` cho vừa túi).

### ZPancake dùng chung DB này (schema `watcher`)

[ZPancake/server](ZPancake/server/) (Pancake Watcher, cổng 8787) trước đây lưu
SQLite riêng, nay dùng **cùng container, cùng database `pancakebot`**, chỉ khác
schema:

```
pancakebot (database)
├── public.kich_ban / hoi_thoai_mau / trang_thai_khach   <- bot ở app/
└── watcher.customers                                     <- ZPancake
```

- 1 volume, `pg_dump` 1 lệnh ra cả hai, Adminer xem chung mà không lẫn tên bảng.
- ZPancake **mượn luôn pool** ở [app/db/client.py](app/db/client.py) và đọc
  `DATABASE_URL` từ `.env` **gốc** (`.env` riêng của nó chỉ để ghi đè khi cần),
  nên không có cấu hình nào phải khai hai lần.
- Mọi câu SQL bên đó ghi rõ `watcher.customers` (không đụng `search_path`) nên
  không ảnh hưởng gì tới truy vấn của app/.
- Postgres chưa bật thì server ZPancake **vẫn chạy**: GUI hiện đèn 🟡, endpoint
  cần DB trả 503 kèm hướng dẫn, và tự nối lại khi DB lên — không phải restart.

### Chuyển dữ liệu sẵn có sang

```powershell
# Từ Supabase cloud xuống (cần SUPABASE_URL + SUPABASE_KEY trong .env)
python -m scripts.migrate_supabase_to_postgres           # xem trước, KHÔNG ghi
python -m scripts.migrate_supabase_to_postgres --apply   # ghi thật

# Từ file .db của backend sqlite cũ (chạy 1 lần rồi xoá được cả file .db)
python -m scripts.migrate_sqlite_to_postgres --apply
```

Chi tiết đáng lưu ý về 2 script:

- Embedding được chép **nguyên vẹn**, không gọi lại OpenAI → không tốn tiền, không
  lệch vector so với nguồn.
- **Không chép `id`**: cột id ở Postgres là `generated always as identity` nên để
  DB tự cấp (3 bảng không tham chiếu id lẫn nhau).
- Chạy lại lần nữa thì **dừng** kèm cảnh báo thay vì nhân đôi dữ liệu; muốn chép đè
  thì thêm `--force` (`truncate ... restart identity` rồi chép lại).
- Không phụ thuộc `DB_BACKEND` đang đặt là gì — script tự dựng backend nó cần.

**Quay ngược về cloud**: đổi `DB_BACKEND=supabase` trong `.env`. Dữ liệu trên
Supabase vẫn còn nguyên, script chỉ **đọc** chứ không đụng vào nguồn.

> ⚠️ **DB local ≠ chạy offline.** `embed()` vẫn gọi OpenAI qua mạng ở cả hai
> backend, vì Postgres không tự sinh được vector. Muốn offline hẳn phải đổi sang
> embedding model chạy trên máy — việc riêng, kèm đổi số chiều vector
> (`EMBEDDING_DIM`, và phải tạo lại bảng vì cột là `vector(1536)` cố định).

### Đã kiểm chứng trên máy (30/07/2026)

Chạy thật, không phải suy đoán — Postgres **17.10** + pgvector **0.8.6** trong
container `pancakebot-pg`:

| Kiểm tra                           | Kết quả                                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Tự tạo schema ở lần chạy đầu | 3 bảng đúng chuẩn, 2 index**HNSW**`vector_cosine_ops`, trigger `updated_at` chạy      |
| Chép dữ liệu từ file`.db` cũ | 3 cặp hỏi–đáp sang nguyên vẹn,**không gọi lại OpenAI**                               |
| Tìm kiếm vector                   | Lấy embedding dòng id=1 làm truy vấn →`1.000000 / 0.466082 / 0.391866`, đúng thứ tự       |
| Ngưỡng lọc                       | `threshold=0.99` → còn đúng 1 dòng                                                            |
| `kich_ban`                        | insert → match (sim`1.000000`) → delete, `meta` ra đúng `dict`                             |
| `trang_thai_khach`                | upsert 2 lần cùng`(page_id, psid)` → vẫn 1 dòng, `updated_at` tự nhảy                     |
| Toàn chuỗi RAG (có OpenAI)       | `/data/thu-tin-nhan` với câu hỏi thật → embed 1536 chiều → điểm `0.511 / 0.370 / 0.283` |
| Bảng điều khiển                 | hiện`postgres` + `postgresql://postgres:***@127.0.0.1:5432/pancakebot`                          |

Điểm `0.466082` **trùng khít** con số đo được trên Supabase trước đây — cùng
pgvector, cùng công thức nên cùng kết quả.

### Vì sao Postgres local thay cho SQLite

- **Cùng một DB với bản cloud** — cùng pgvector, cùng schema, cùng SQL. Hết cảnh
  hai đường code tìm kiếm khác nhau (numpy vs `<=>`) phải đối chiếu cho khớp.
- **Tìm kiếm chạy trong DB**, có index **HNSW** thật: không phải kéo toàn bộ vector
  lên RAM tiến trình app như bản SQLite, nên **không có trần ~100k dòng** nữa.
- Đổi lên/xuống cloud chỉ là đổi `DATABASE_URL`, dữ liệu `pg_dump` mang đi được.

**Thêm backend mới**: viết 1 file trong
[app/db/backends/](app/db/backends/) cài đủ các phương thức của
[base.py](app/db/backends/base.py), khai báo 1 dòng ở `_REGISTRY` trong
[app/db/backends/\_\_init\_\_.py](app/db/backends/__init__.py). Không đụng tới
`queries.py` hay bất kỳ chỗ nào khác trong app.

## Tầng dữ liệu — file nào làm chức năng gì

### 1. Kết nối & cấu hình

| File                                                          | Chức năng                                                                                                                                                                            |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.env`                                                      | `DB_BACKEND` (`postgres`\|`supabase`); `DATABASE_URL` hoặc `SUPABASE_URL`+`SUPABASE_KEY` (**secret key** `sb_secret_...`); `RAG_TOP_K`, `RAG_MATCH_THRESHOLD` |
| [app/config.py](app/config.py)                                 | Đọc`.env` → `settings.db_backend`, `settings.database_url`, `settings.pg_pool_*`, `settings.supabase_*`, `settings.rag_*`                                               |
| [app/db/backends/\_\_init\_\_.py](app/db/backends/__init__.py) | `get_backend()` — chọn backend theo `DB_BACKEND` (cache 1 lần). Import nằm trong lambda nên chỉ nạp thư viện của backend đang dùng                                     |
| [app/db/client.py](app/db/client.py)                           | `get_pg_pool()` — pool psycopg dùng chung (`dict_row` + `autocommit`, an toàn theo thread). `get_supabase()` — client REST dùng chung                                     |

### 2. Đọc/ghi dữ liệu — [app/db/queries.py](app/db/queries.py) (file trung tâm)

Mọi nơi khác trong app **chỉ** import từ đây; file này không biết dữ liệu nằm ở đâu,
nó chỉ chuẩn hoá tham số + gọi embedding rồi đẩy xuống backend. Chữ ký các hàm giữ
nguyên như trước khi tách lớp, nên brain / flow / session / ui / ingestion không phải sửa gì.

| Nhóm                | Hàm                                                                    | Chức năng                                                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tiện ích           | `_count()`                                                            | Đếm số dòng (tuỳ chọn: chỉ dòng đã có embedding)                                                                                                                 |
|                      | `_k_and_threshold()`                                                  | Điền mặc định`rag_top_k` / `rag_match_threshold` từ settings                                                                                                      |
| `kich_ban`         | `load_scripts()`                                                      | Lấy toàn bộ kịch bản (cho bot)                                                                                                                                         |
|                      | `list_scripts()`                                                      | Danh sách cho giao diện (**không** kéo cột embedding cho nhẹ)                                                                                                   |
|                      | `insert_script()`                                                     | **Python gọi OpenAI** tạo embedding → `INSERT`                                                                                                                   |
|                      | `delete_script()`                                                     | Xoá 1 bước theo id                                                                                                                                                       |
| `hoi_thoai_mau`    | `list_qa_pairs()`                                                     | Danh sách cặp hỏi–đáp cho giao diện                                                                                                                                  |
|                      | `insert_qa()`                                                         | Embed câu hỏi →`INSERT` (text gốc lưu vào `meta.embed_text`)                                                                                                      |
|                      | `delete_qa()`                                                         | Xoá 1 cặp theo id                                                                                                                                                         |
| **Tìm kiếm** | `search_similar()`                                                    | Q&A gần nhất — postgres:`SELECT ... <=>`; supabase: RPC`match_documents`                                                                                             |
|                      | `search_similar_scripts()`                                            | Bước kịch bản gần nhất —`SELECT ... <=>` / RPC`match_kich_ban`                                                                                                   |
|                      | `debug_search()`                                                      | Tìm ở cả 2 bảng + số liệu chẩn đoán (cho tab "Thử tin nhắn")                                                                                                     |
| `trang_thai_khach` | `load_customer_state(page_id, psid)` / `upsert_customer_state(...)` | Phiên khách theo**(page_id, psid)** — ✅ đã căn đúng schema thật (`kich_ban`/`buoc_hien_tai`/`ngu_canh`/`trang_thai`), upsert `on_conflict=page_id,psid` |

### 3. Backend — [app/db/backends/](app/db/backends/)

| File                                            | Chức năng                                                                                                                                                        |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [base.py](app/db/backends/base.py)               | Hợp đồng chung: vector đi vào/ra là`list[float]`, cột JSON là `dict`, `match_*` trả list đã xếp hạng kèm `similarity`                        |
| [postgres_be.py](app/db/backends/postgres_be.py) | `_schema()` tự tạo bảng+index HNSW ở lần chạy đầu; ghi vector bằng `%s::vector`, `meta` bọc `Jsonb`; `_match()` chạy `<=>` thẳng trong SQL |
| [supabase_be.py](app/db/backends/supabase_be.py) | `_pgvector()` đổi list số → chuỗi `[a,b,c]`; `_rpc()` gọi hàm SQL, báo lỗi rõ nếu chưa tạo hàm                                                 |

### 4. File SQL

| File                                          | Chức năng                                                                                                                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [scripts/init_pg.sql](scripts/init_pg.sql)     | Schema cho Postgres local.**Không bắt buộc chạy** — app tự tạo y hệt; để đọc tham khảo hoặc tạo tay khi user app thiếu quyền `create extension` |
| [scripts/rpc_match.sql](scripts/rpc_match.sql) | Tạo 2 hàm RPC`match_documents` + `match_kich_ban`. **Chỉ** cần cho `DB_BACKEND=supabase`, chạy 1 lần trong SQL Editor                                  |

### 5. Nơi gọi tới tầng dữ liệu

| File                                                                                                       | Dùng để làm gì                                                                                                             |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| [app/data/routes.py](app/data/routes.py) · [app/data/webview.py](app/data/webview.py)                       | Giao diện`/data`: thêm/xem/xoá kịch bản & hội thoại mẫu, và tab **Thử tin nhắn** (xem RPC truy xuất ra gì) |
| [app/rag/retriever.py](app/rag/retriever.py)                                                                | Gọi`search_similar()` lấy ngữ cảnh cho bot trả lời                                                                      |
| [ingestion/load_scripts.py](ingestion/load_scripts.py) · [ingestion/run_ingest.py](ingestion/run_ingest.py) | Nạp hàng loạt từ file JSON vào 2 bảng                                                                                     |

### 6. File Supabase KHÔNG dùng

| File                                                                                | Ghi chú                                                                                                                                                                                |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [supabase/functions/embed-insert/index.ts](supabase/functions/embed-insert/index.ts) | Edge Function (để Supabase tự embed + insert). Đã cân nhắc rồi**chọn chạy ở máy mình** nên **không dùng, chưa deploy**. Giữ lại phòng khi đổi hướng |

> **Nhắc lại:** embedding **luôn** do OpenAI sinh ra — Postgres không tự tạo được.
> Khác biệt chỉ là *ai gọi OpenAI*: hiện tại là **Python ở máy bạn**.

## Cài đặt & chạy

Các bước đầy đủ nằm ở mục [🚀 Chạy dự án](#-chạy-dự-án) đầu file. Vài điểm bổ sung:

- Gói DB duy nhất cần cho backend mặc định là `psycopg[binary,pool]` (đã có trong
  `requirements.txt`) — **không** cần `pgvector` hay `numpy` phía Python.
- Muốn dùng cloud thay vì DB trên máy: đặt `DB_BACKEND=supabase`, điền
  `SUPABASE_URL` + `SUPABASE_KEY`, và chạy
  [scripts/rpc_match.sql](scripts/rpc_match.sql) một lần trong SQL Editor. Lúc đó
  không cần Docker.
- `--reload` chỉ hợp lúc phát triển (sửa code là tự khởi động lại). Chạy lâu dài
  thì bỏ `--reload` đi cho đỡ tốn RAM.

## Các endpoint

| Endpoint                                                            | Chức năng                                                                               |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `GET /`                                                           | Chuyển thẳng sang Bảng điều khiển                                                   |
| `GET /bang-dieu-khien`                                            | **Bảng điều khiển** — số liệu + cấu hình                                   |
| `GET /tin-nhan`                                                   | **Tin nhắn** — hộp thư 2 cột (list + chat)                                     |
| `POST /tin-nhan/tra-loi`                                          | Gửi tin trả lời từ màn 2 cột                                                        |
| `POST /tin-nhan/goi-y`                                            | **Gợi ý trả lời** (RAG+LLM) cho tin cuối của khách — trả JSON, KHÔNG gửi |
| `GET /tin-nhan/fragment/list`, `.../thread`                     | Fragment auto-refresh của màn Tin nhắn                                                 |
| `GET /khach-hang`                                                 | **Khách hàng** — bảng khách + tìm nhanh                                       |
| `GET /health`                                                     | Kiểm tra server sống (`{"status":"ok"}`)                                              |
| `GET /docs`                                                       | Swagger UI (liệt kê toàn bộ endpoint)                                                 |
| `GET /pancake/webview`                                            | Trang HTML danh sách Page có quyền                                                     |
| `GET /pancake/pages`                                              | Danh sách Page dạng JSON                                                                |
| `GET /pancake/pages/{id}/recent?limit=10`                         | Người nhắn tin (INBOX) mới nhất                                                      |
| `GET /pancake/pages/{id}/conversations/{conv_id}?customer_id=...` | Khung chat + ô trả lời                                                                 |
| `POST /pancake/pages/{id}/conversations/{conv_id}/reply`          | Gửi tin trả lời (qua Pancake)                                                          |
| `GET .../recent/fragment`, `.../{conv_id}/fragment`             | Fragment cho auto-refresh (JS gọi ngầm)                                                 |
| `GET /data/kich-ban`                                              | Giao diện thêm/xem/xoá**kịch bản**                                             |
| `POST /data/kich-ban`                                             | Thêm 1 bước kịch bản (tự tạo embedding)                                            |
| `POST /data/kich-ban/{id}/xoa`                                    | Xoá 1 bước kịch bản                                                                  |
| `GET /data/hoi-thoai`                                             | Giao diện thêm/xem/xoá**hội thoại mẫu**                                       |
| `POST /data/hoi-thoai`                                            | Thêm 1 cặp hỏi–đáp (tự tạo embedding)                                             |
| `POST /data/hoi-thoai/{id}/xoa`                                   | Xoá 1 cặp hỏi–đáp                                                                   |

> **Chỉ dùng phần xem Pancake?** Chỉ cần `PANCAKE_ACCESS_TOKEN` là các trang
> `/pancake/...` chạy được — chưa cần OpenAI hay DB. Não RAG + gửi liên quan mới
> cần thêm `OPENAI_API_KEY` và một nơi lưu dữ liệu (`DATABASE_URL` với
> `DB_BACKEND=postgres`, hoặc `SUPABASE_*`).

Trang danh sách người nhắn và khung chat **tự cập nhật** (auto-refresh 8–10 giây)
mà không cần F5; bấm vào một người để xem hội thoại và trả lời tay.

## 🔍 Pancake API — có full quyền page thì lấy được những gì

> Tài liệu công khai của Pancake không đọc được (trang SPA + cert `docs.pancake.vn`
> hết hạn) nên phần này **dò thật bằng token trong `.env`** qua tab
> [Thử API](http://127.0.0.1:8000/data/thu-api) — 26 lượt GET, chỉ đọc, ngày
> **2026-07-29**, trên page `613327758541266`, token role `EDIT_PROFILE`.

Base: `https://pages.fm/api/v1` · `access_token` đặt ở **query string**.

### ✅ Chạy được (200) — chỉ cần user JWT, KHÔNG cần Admin

| Endpoint                                                                | Trả về gì                                                                                                                                                                                                                                                     |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET me`                                                              | Tài khoản: email, phone, fb_id, timezone, chữ ký, affiliate_level · khối`me`: uid, session_id, token_for_business                                                                                                                                        |
| `GET pages`                                                           | Toàn bộ page chia 4 nhóm (activated / inactivated / hidden / nopermission) — hàm`list_pages()`                                                                                                                                                            |
| `GET pages/{id}`                                                      | Chi tiết 1 page:`shop_id`, platform, business, `tag_sync_group_id`, special_feature                                                                                                                                                                         |
| **`GET pages/{id}/settings`** ⭐                                | **`settings.tags` = toàn bộ thẻ kèm TÊN + MÀU** (52 thẻ) · `quick_replies` (**211 mẫu trả lời nhanh shop đang dùng thật**) · `warehouses` · `pinned_photos` (72) · `recent_photos` (80) · cấu hình chia ca round-robin |
| `GET pages/{id}/users`                                                | Nhân viên của page (35 người): id, name, fb_id,**`role_in_page`**, status_in_page                                                                                                                                                                   |
| `GET pages/{id}/statistics`                                           | `data.by_date` + `data.by_user`                                                                                                                                                                                                                              |
| `GET pages/{id}/conversations`                                        | Danh sách hội thoại +`list_page_users` — hàm `list_conversations()`                                                                                                                                                                                     |
| `GET pages/{id}/conversations/{conv_id}/messages`                     | Tin nhắn +`notes`, `post`, `read_watermarks`, **`conv_phone_numbers`**, `banned_by`, `reports_by_phone` — hàm `get_conversation()`                                                                                                        |
| `GET pages/{id}/customers/{customer_id}`                              | Chi tiết 1 khách —**phải có sẵn customer_id, KHÔNG list được**                                                                                                                                                                                   |
| `POST pages/{id}/conversations/{conv_id}/messages?action=reply_inbox` | Gửi tin trả lời — hàm`send_message()`                                                                                                                                                                                                                     |
| `POST pages/{id}/generate_page_access_token`                          | Sinh`page_access_token` cho public API — ⚠️ **cần quyền Admin**, token hiện tại không đủ                                                                                                                                                       |

### ❌ Không tồn tại (406 "Server internal error")

`user` · `shops` · `me/pages` · `pages/{id}/tags` · `pages/{id}/customers` (dạng
list) · `orders` · `products` · `insights` · `quick_messages` · `warehouses` ·
`categories` · `pos_settings` · `activities` · `conversations/{conv_id}/tags`

**Đọc mã trạng thái** (khi gửi `Accept: application/json`):

| Mã                         | Nghĩa                                    |
| --------------------------- | ----------------------------------------- |
| `406`                     | Route**không tồn tại** dạng API |
| `500`                     | Route API**có thật** nhưng lỗi  |
| `200` + `success:false` | Lỗi nghiệp vụ (vd sai token)           |

### ⭐ Lấy TÊN THẺ không cần quyền Admin

`settings.tags` trong `GET pages/{id}/settings` trả thẳng mảng đầy đủ:

```json
{"id": 171, "text": "1 Phản Hồi", "color": "#a06fdc", "lighten_color": "rgba(160,111,220,0.4)"}
{"id": 172, "text": "3 Báo Giá",  "color": "#ff4242"}
{"id": 173, "text": "Đã XN",      "color": "#0d5aff"}
```

> ⚠️ **Đính chính kết luận cũ.** Trước đây ta chốt rằng muốn có tên thẻ thì
> **phải** sinh `page_access_token` (cần Admin) rồi gọi Public API — nên mới đẻ ra
> bảng `TAG_OVERRIDES` gõ tên thẻ bằng tay trong
> [app/pancake/client.py](app/pancake/client.py) và màn Tin nhắn phải hiện
> `Thẻ #171`. **Kết luận đó SAI** — có đường vòng không cần Admin.
> `list_tags()` nên đổi sang đọc `settings.tags`, khi đó bỏ được cả
> `TAG_OVERRIDES` lẫn `PANCAKE_TAG_PAGE_IDS`. *(chưa làm)*

### Chưa dò

**Đơn hàng / sản phẩm không nằm ở API của page.** Pancake tách POS riêng;
`GET pages/{id}` có trả `shop_id` nên nhiều khả năng chúng nằm dưới
`shops/{shop_id}/...` — chưa thử.

### Giao diện web — menu bên trái

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000) là vào thẳng giao diện quản trị.
Mọi trang dùng chung một khung: **menu dọc bên trái** + thanh tiêu đề, bố cục rộng
cho màn hình máy tính (dưới 900px menu tự thu thành thanh ngang có icon).

| Mục menu                       | Đường dẫn        | Nội dung                                                                         |
| ------------------------------- | -------------------- | --------------------------------------------------------------------------------- |
| 📊**Bảng điều khiển** | `/bang-dieu-khien` | Số page, hội thoại, tin chưa đọc, kho dữ liệu bot, cấu hình đang chạy |
| 💬**Tin nhắn**           | `/tin-nhan`        | Hộp thư 2 cột: danh sách hội thoại ↔ khung chat + ô trả lời             |
| 👥**Khách hàng**        | `/khach-hang`      | Bảng khách đã nhắn (tên, FB ID, số tin, chưa đọc, lần cuối) + ô tìm |
| 🧠**Dữ liệu bot**       | `/data/kich-ban`   | 4 tab: Kịch bản · Hội thoại mẫu · Thử tin nhắn ·**Thử API**      |

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
Pancake API (pages.fm)          DB bot (Postgres máy mình HOẶC Supabase)
   tin nhắn, khách hàng            kịch bản, hội thoại mẫu, vector
        │                                    │
        ├── Bảng điều khiển ◄────────────────┤   (đọc cả 2 để hiện số liệu)
        ├── Tin nhắn                         │
        ├── Khách hàng                       │
        │                                    └── Dữ liệu bot
        └── (gửi tin trả lời)
```

Nói ngắn: **Tin nhắn + Khách hàng** chỉ nói chuyện với Pancake, **Dữ liệu bot**
chỉ nói chuyện với DB bot + OpenAI, **Bảng điều khiển** đọc cả hai.

#### 📊 Bảng điều khiển — `/bang-dieu-khien`

|                            |                                                                                                                                                                                                                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lấy dữ liệu**   | 3 khối**độc lập**: (1) Pancake — `list_pages()` + `list_conversations(limit=50)`; (2) DB bot — 4 lệnh đếm (qua `db/queries._count`, backend nào cũng chạy); (3) cấu hình — đọc `settings` từ `.env`, không gọi mạng                                                 |
| **Xử lý**          | Tin chưa đọc =**cộng dồn** `unread_count` của mọi hội thoại. Khách gần nhất = hội thoại đầu danh sách (đã sắp mới→cũ), đổi sang chữ "5 phút trước". Tên chủ token lấy bằng cách **giải mã payload JWT tại chỗ** (`token_owner()`), không gọi API |
| **Đếm kiểu nhẹ** | `_count()` dùng `select("id", count="exact").limit(1)` — Postgres trả về **con số**, không kéo dòng nào về. Cột `embedding` (1536 số/dòng) không bao giờ bị tải                                                                                                             |
| **Chịu lỗi**       | Mỗi khối`try/except` riêng: Pancake hỏng thì khối DB bot vẫn hiện bình thường, lỗi chỉ đỏ trong đúng ô của nó — không 500 trắng màn                                                                                                                                            |
| **Ghi gì?**         | **Không ghi gì cả**, thuần đọc                                                                                                                                                                                                                                                               |
| **File**             | [app/ui/routes.py](app/ui/routes.py) → `dashboard()` · [app/ui/webview.py](app/ui/webview.py) → `render_dashboard()`                                                                                                                                                                                |

#### 💬 Tin nhắn — `/tin-nhan`

|                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Cột trái**                        | `GET /pages/{id}/conversations?type=INBOX` → `_normalize_conv()` rút gọn còn tên, ảnh, tin cuối, số tin, chưa đọc → **sắp theo `updated_at` giảm dần** rồi cắt 20 dòng                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **Hộp thư GỘP** (`?page_id=ALL`) | Mục**"📥 Tất cả page (N đang BẬT)"** ở đầu ô chọn page: gọi song song mọi page**đang BẬT** (semaphore 5 luồng, 1 page hỏng không làm sập cả danh sách), trộn rồi sắp lại theo `updated_at`. Mỗi dòng hiện thêm **tên page**. Link mở hội thoại kèm `conv_page_id` = page THẬT → khung chat/gửi tin/gợi ý vẫn đúng page, cột trái giữ nguyên chế độ gộp. Có **cache SWR riêng cho bản đã gộp** (15s) + nhịp auto-refresh 15s (thay vì 10s) để mỗi nhịp không bung ra N lời gọi Pancake. ⚠️ Chế độ gộp **không lọc thẻ** (thẻ là dữ liệu riêng từng page, cùng số ID ở 2 page là 2 thẻ khác nhau) |
| **Cột phải**                        | Chỉ tải khi đã bấm chọn một hội thoại:`GET .../conversations/{conv_id}/messages` (**bắt buộc kèm `customer_id`**) → `_normalize_msg()` → sắp **cũ → mới**; so `from.id` với `page_id` để biết tin nào của shop (bong bóng xanh phải) hay của khách (xám trái)                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Nội dung tin**                     | Ưu tiên`original_message`; nếu không có thì bóc thẻ HTML nhưng **giữ xuống dòng** (`<br>`, `</div>` → `\n`). Ảnh/sticker hiện thumbnail, tệp khác hiện link                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Tự cập nhật**                    | JS gọi 2 endpoint mảnh:`/tin-nhan/fragment/list` (10s) và `/tin-nhan/fragment/thread` (8s). Nhận HTML về **so với lần trước, khác mới thay** → không nháy màn, không mất ảnh đang tải. Nhịp đầu chỉ "mồi" để so sánh. Lỗi mạng trả 502 → JS **bỏ qua nhịp đó**, giữ nguyên nội dung đang xem                                                                                                                                                                                                                                                                                                                                                              |
| **Gửi trả lời**                    | `POST /tin-nhan/tra-loi` → `send_message()` → `POST .../messages?action=reply_inbox` → redirect **303** về đúng hội thoại kèm `?sent=1` (F5 không gửi lại tin)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Ghi gì?**                          | ⚠️**Gửi tin THẬT tới khách** — chỉ khi bạn tự bấm nút Gửi. Không ghi vào DB bot                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **File**                              | [app/ui/routes.py](app/ui/routes.py) → `inbox()` · [app/pancake/client.py](app/pancake/client.py) → `list_conversations` / `get_conversation` / `send_message`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

#### 👥 Khách hàng — `/khach-hang`

|                          |                                                                                                                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lấy dữ liệu** | **Cùng một nguồn với màn Tin nhắn** — `list_conversations(limit=100)`. Mỗi hội thoại INBOX = một khách                                                                                                                                              |
| **Xử lý**        | Đổ thẳng vào bảng: tên,`fb_id`, `message_count`, `unread_count`, `updated_at` (đổi sang "2 ngày trước", di chuột hiện giờ chính xác). Nút *Nhắn tin* dựng sẵn link kèm `conv_id` + `customer_id` để bấm là mở đúng khung chat |
| **Ô tìm nhanh**  | Lọc**ngay tại trình duyệt** bằng JS trên bảng đã tải (khớp tên + FB ID) — gõ không gọi lại server, không tốn thêm 1 lượt Pancake                                                                                                            |
| **Ghi gì?**       | Không ghi. ⚠️ Danh sách khách**chưa được lưu vào DB bot** — mỗi lần mở là đọc mới từ Pancake, nên chưa có lịch sử/ghi chú theo khách                                                                                                   |
| **File**           | [app/ui/routes.py](app/ui/routes.py) → `customers()` · [app/ui/webview.py](app/ui/webview.py) → `render_customers()`                                                                                                                                               |

#### 🧠 Dữ liệu bot — `/data/...` (3 tab)

| Tab                                                           | Luồng dữ liệu                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Kịch bản**                                          | *Xem*: `list_scripts()` đọc bảng `kich_ban`, **cố ý không lấy cột `embedding`** cho nhẹ, rồi gom nhóm theo tên kịch bản. *Thêm*: nội dung → `embed()` gọi **OpenAI** → nhận vector 1536 chiều → ghi 1 dòng kèm vector dạng literal `[0.1,0.2,…]`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Hội thoại mẫu**                                    | Giống trên, ghi vào`hoi_thoai_mau`. Điểm khác: **vector hoá CÂU HỎI** (không phải câu trả lời) — vì lúc chạy thật ta so tin nhắn của khách với câu hỏi mẫu                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Thử API** ⚠️ *trang TEST, xoá khi xong dự án* | Đầu trang là**bảng tra cứu**: `PANCAKE_ACCESS_TOKEN` **hiện nguyên văn** (có nút Copy) + **danh sách toàn bộ page ID** (tên · page_id · nền tảng · công tắc) — bấm 1 `page_id` là chèn thẳng vào ô đường dẫn, khỏi đi tìm. Cố ý phơi bí mật ra màn hình cho tiện thử ở localhost; tick *"Che bớt access_token"* nếu cần chụp màn hình. **Thay cho Postman** — gọi thẳng endpoint Pancake, xem **JSON gốc** chưa qua lớp xử lý nào. Bố cục kiểu Postman: `[GET/POST][base URL][path][Gửi]` + bảng tham số key/value (thêm/xoá dòng). Hiện đủ **request đã gửi** (URL đầy đủ + từng tham số) và **response** (mã trạng thái, thời gian, dung lượng, body). Đổi được giữa **API nội bộ** (`/api/v1`, tự đính `access_token`) và **Public API** (`/api/public_api/v1`, tự truyền `page_access_token`). Có 4 **mẫu sẵn** điền nhanh. `access_token` **bị che mặc định** (tick để hiện) vì đây là trang hay bị chụp màn hình. Dùng `raw_call()` trong `pancake/client.py`: **không cache, không chuẩn hoá, không chặn theo công tắc page, không raise khi API lỗi** — lỗi HTTP vẫn hiện nguyên body để đọc. ⚠️ **POST hỏi xác nhận** vì có thể gửi tin thật tới khách |
| **Thử tin nhắn**                                      | Gõ tin giả làm khách →`embed()` → gọi **2 RPC** `match_documents` + `match_kich_ban`. Phép so sánh cosine `<=>` chạy **trong Postgres** và dùng **index HNSW** — Python chỉ gửi vector rồi nhận về kết quả đã xếp hạng sẵn (không kéo cả bảng về). Tick ô *kèm câu trả lời* hiện **2 ô để đối chiếu**: **Bước 4 — Trả lời theo toàn bộ tri thức** (`build_prompt()` để LLM **tự viết** — chỉ để đối chiếu, KHÔNG gửi khách vì có thể sửa nghĩa) và **Bước 5 — Gợi ý trả lời** (`choose_reply()` — GPT **chỉ CHỌN** 1 trong top 3 câu mẫu rồi trả **NGUYÊN VĂN** câu đã duyệt, không hợp → **NO_MATCH → không gợi ý**; đúng logic nút "Gợi ý trả lời" ở màn Tin nhắn)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

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

Có 3 cách, dùng cách nào cũng **tự tạo embedding** rồi ghi vào DB bot (Postgres local hay Supabase tuỳ `DB_BACKEND`).

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

| Tính năng                                                                                     | Trạng thái                                                                                                                                          |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Giao diện web có menu trái** (4 mục, bố cục cho máy tính)                       | ✅ đã verify (8 trang, HTML hợp lệ)                                                                                                               |
| Bảng điều khiển / Khách hàng / Tin nhắn 2 cột                                           | ✅ đã verify                                                                                                                                        |
| Xem page / người nhắn / khung chat + trả lời tay (Pancake)                                 | ✅ chạy                                                                                                                                              |
| Auto-refresh giao diện (poll fragment)                                                         | ✅ chạy —**chỉ page đang mở trên trình duyệt**                                                                                          |
| Cache danh sách page 60s (tránh Pancake chặn 429)                                            | ✅ đã verify (hết 502 khi mở dồn dập)                                                                                                           |
| Cache**SWR** `list_conversations` (chuyển trang lần sau hết khựng)                  | ✅ đã verify (trả bản cũ ngay + refresh nền, gọi đồng bộ chỉ lần đầu/ quá 10ph)                                                        |
| **Công tắc BẬT/TẮT từng page** (Bảng điều khiển → danh sách page)              | ✅ đã verify — TẮT chặn lấy+gửi tin của page đó ở MỌI nơi (guard trong`pancake/client`), lưu `page_switches.json`, mặc định BẬT |
| **Hộp thư GỘP mọi page đang BẬT** (`/tin-nhan?page_id=ALL`)                       | ✅ đã verify — gộp 20 dòng từ nhiều page, mở/gửi đúng page thật, chế độ xem 1 page không đổi                                        |
| RAG: embed, retrieve, LLM gpt-4o-mini, insert kèm embedding, distill                           | ✅ đã verify                                                                                                                                        |
| Tìm kiếm vector chạy**trong Postgres** (pgvector + index HNSW)                         | ✅ đã verify trên**Postgres local** (`SELECT ... <=>` thẳng, không cần RPC)                                                             |
| Ngưỡng lọc`match_threshold` (lạc đề → trả rỗng)                                      | ✅ đã verify (0.6 → 0 dòng với câu lạc đề)                                                                                                   |
| Giao diện tự nhập**kịch bản** &**hội thoại mẫu** (`/data`)                | ✅ đã verify (thêm/xoá/báo lỗi trùng)                                                                                                          |
| Nút**"Gợi ý trả lời"** trong khung chat (human-in-the-loop, không tự gửi)               | ✅ đã verify (test mock: happy-path, thiếu tin, lỗi LLM không 500)                                                                               |
| Bot**tự động poll + gợi ý/trả lời** hội thoại                                    | 🟡 đã chốt thiết kế,**chưa code**                                                                                                         |
| **Kho hội thoại + worker nền 24/7** (`watcher.hoi_thoai`)                            | ✅ đã verify 30/07/2026 — 22 page → 324 hội thoại, không sót khi rơi khỏi top-N                                                             |
| **Quét cảm xúc tiêu cực cho hội thoại Pancake** (dùng lại sentiment.py ZPancake) | ✅ đã verify — 325/325 dòng được quét, bắt đúng 1 hội thoại thật có "vô trách nhiệm"                                                |
| Phiên khách`trang_thai_khach` (session.py)                                                  | ✅ đã căn theo schema thật (page_id/psid/ngu_canh) — round-trip verify trên bảng thật                                                         |
| **DB Postgres + pgvector chạy local** (Docker, thay hẳn SQLite)                         | ✅ đã verify end-to-end 30/07/2026 — tự tạo schema, chép dữ liệu cũ, tìm kiếm khớp số cũ                                                |
| Kịch bản Bảng 1 (`bot/flow`)                                                               | ⏳ khung, chưa cài logic khớp                                                                                                                      |
| Tab**Thử tin nhắn** kèm câu trả lời của bot                                        | ✅ đã verify (tick ô để gọi gpt-4o-mini)                                                                                                        |
| Tab**Thử API** (Postman nội bộ — xem JSON gốc Pancake)                               | ✅ đã verify (gọi thật 200/406, che token, đổi public API)                                                                                      |
| Bản đồ endpoint Pancake (*Pancake API — lấy được những gì*)                         | ✅ đã dò thật 26 lượt GET (2026-07-29) — 11 endpoint chạy, 14 endpoint 406                                                                    |
| Đổi`list_tags()` sang đọc `settings.tags` (bỏ `TAG_OVERRIDES`)                       | 📋 chưa làm — đã tìm ra cách, xem mục đính chính ở trên                                                                                  |
| API`/api/chat` cho phần mềm ngoài + bảo mật API key                                      | 📋 chưa làm — xem mục*Kế hoạch: mở API* ở cuối                                                                                             |

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

   1. Nhúng câu hỏi → DB lấy **top 5** câu mẫu tương đồng (`hoi_thoai_mau`),
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
   dưới ngưỡng thì NO_MATCH luôn, không tốn tiền; (b) model trả **JSON** `{"chon": <số>}` (0 = không có) nên **hết lệ thuộc so chuỗi** NO_MATCH; (c) tin khách được
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
- **"Không nối được Postgres (...)"** — DB chưa bật hoặc sai địa chỉ. Chạy
  `docker compose up -d` rồi `docker compose ps` (phải `healthy`). Nếu container
  đang chạy mà vẫn lỗi/treo lâu: **`DATABASE_URL` để `localhost`** — đổi sang
  `127.0.0.1` (Docker chỉ nghe IPv4, Windows phân giải `localhost` ra `::1` trước).
- **"Postgres đang chạy nhưng KHÔNG có extension pgvector"** — dùng đúng image
  `pgvector/pgvector:pg17` trong [docker-compose.yml](docker-compose.yml), hoặc cài
  pgvector cho bản Postgres tự cài. Nếu user app không có quyền `create extension`
  thì chạy [scripts/init_pg.sql](scripts/init_pg.sql) bằng superuser.
- **`expected 1536 dimensions, not 768`** khi thêm dữ liệu — `EMBEDDING_MODEL` /
  `EMBEDDING_DIM` không khớp cột `vector(1536)`. Đặt lại về
  `text-embedding-3-small` + `1536`; đã lỡ đổi model thì phải **nhúng lại** toàn bộ
  (đổi số chiều = phải tạo lại bảng).
- **Cổng 5432 đã bị chiếm** (Postgres khác đang chạy) — sửa cổng ngoài trong
  [docker-compose.yml](docker-compose.yml) (ví dụ `"127.0.0.1:5433:5432"`) rồi đổi
  `DATABASE_URL` cho khớp.

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
- 🗑️ Thêm/xoá dữ liệu bot qua `/data/...`
- 💸 **Tiêu tiền OpenAI** của bạn bằng cách spam endpoint gọi LLM

Vì token Pancake / key OpenAI / secret DB đều nằm phía server, người lạ gọi
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

0. **DB tự bật cùng máy:** container `pancakebot-pg` để `restart: unless-stopped`
   nên tự chạy lại khi khởi động — chỉ cần bật **Docker Desktop** khi đăng nhập
   (Settings → General → *Start Docker Desktop when you sign in*). App khởi động
   trước DB cũng không sao: chỉ báo lỗi ở trang dùng DB, hết `docker compose ps`
   thấy `healthy` là chạy tiếp bình thường.
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
