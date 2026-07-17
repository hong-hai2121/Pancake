# FB Sales Bot

Bot bán hàng trên Facebook Messenger: nhận tin nhắn qua webhook, đi theo kịch bản
bán hàng (Bảng 1), và khi cần thì dùng RAG + LLM để trả lời tự nhiên.

## Kiến trúc

fb-sales-bot/
├── .env                    # khóa API + chuỗi kết nối Supabase (KHÔNG commit lên git)
├── .env.example            # mẫu liệt kê các biến cần khai báo
├── requirements.txt
├── README.md
│
├── app/
│   ├── main.py             # khởi động server, đăng ký route webhook
│   ├── config.py           # đọc .env, cấu hình chung
│   │
│   ├── webhook/
│   │   ├── routes.py       # nhận GET (verify) + POST (tin nhắn) từ Facebook
│   │   └── handler.py      # điều phối: nhận tin → gọi bot → gửi trả lời
│   │
│   ├── messenger/
│   │   └── send_api.py     # gửi câu trả lời qua Facebook Send API
│   │
│   ├── bot/
│   │   ├── brain.py        # "não": quyết định trả lời gì (điều phối tổng)
│   │   ├── flow.py         # xử lý kịch bản Bảng 1 + đi tới bước tiếp
│   │   ├── session.py      # quản lý phiên: đọc/reset trang_thai_khach, mở phiên mới
│   │   └── prompt.py       # ghép system prompt + persona + ngữ cảnh
│   │
│   ├── rag/
│   │   ├── embedding.py    # vector hóa câu (gọi API embedding)
│   │   ├── retriever.py    # tìm top-k trong kich_ban / hoi_thoai_mau
│   │   └── llm.py          # gọi LLM (Gemini/OpenAI) sinh câu trả lời
│   │
│   └── db/
│       ├── client.py       # kết nối Supabase/Postgres
│       └── queries.py      # đọc/ghi 3 bảng
│
├── ingestion/              # phần chạy OFFLINE, tách hẳn khỏi webhook
│   ├── load_scripts.py     # nạp kịch bản sẵn vào bảng kich_ban
│   ├── distill.py          # chưng cất chat cũ → cặp hỏi–đáp (gọi LLM)
│   └── run_ingest.py       # cron: lấy chat đã chốt → distill → lưu + tạo embedding
│
└── scripts/
    └── init_db.sql         # tạo 3 bảng + bật extension pgvector

```
Facebook ──POST──> webhook/routes ──> webhook/handler ──> bot/brain
                                                            │
                          ┌─────────────────────────────────┤
                          ▼                                  ▼
                    bot/flow (kịch bản)              rag/retriever ──> rag/llm
                          │                                  │
                          ▼                                  ▼
                    bot/session ◄──────── db/queries ──────► rag/embedding
                                              │
                                              ▼
                                     Supabase / Postgres (pgvector)
```

- **app/** — mã chạy realtime cho webhook.
- **ingestion/** — chạy offline: nạp kịch bản, chưng cất chat cũ thành cặp hỏi–đáp, tạo embedding.
- **scripts/init_db.sql** — tạo 3 bảng + bật extension `pgvector`.

### 3 bảng chính

| Bảng                | Vai trò                                                 |
| -------------------- | -------------------------------------------------------- |
| `kich_ban`         | Kịch bản bán hàng có sẵn (Bảng 1)                 |
| `hoi_thoai_mau`    | Cặp hỏi–đáp chưng cất từ chat cũ, dùng cho RAG |
| `trang_thai_khach` | Phiên hội thoại của từng khách                     |

## Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt

copy .env.example .env        # rồi điền khóa API + chuỗi Supabase
```

## Khởi tạo database

Chạy `scripts/init_db.sql` trên Supabase (SQL Editor) hoặc:

```bash
psql "$DATABASE_URL" -f scripts/init_db.sql
```

## Chạy server

```bash
uvicorn app.main:app --reload --port 8000
```

Webhook endpoint: `GET/POST /webhook`. Dùng ngrok (hoặc domain thật) để Facebook
gọi tới được, rồi khai báo URL + `FB_VERIFY_TOKEN` trong Meta for Developers.

## Chạy ingestion (offline)

```bash
python -m ingestion.load_scripts     # nạp kịch bản vào bảng kich_ban
python -m ingestion.run_ingest       # chưng cất chat đã chốt -> hoi_thoai_mau + embedding
```
