-- ============================================================
-- CRM TIÊU HÓA — 70 bảng
--   56 bảng theo DANH-SACH-BANG-VA-QUAN-HE.md
--   + handovers     (FR-090/091 · màn 24-25 · API HANDOVER-001…006)
--   + audit_logs    (FR-180    · màn 77    · API AUDIT-001/002)
--   + user_sessions (A2 — docs/A2-DANG-NHAP.md mục 2.2)
--   + ref_codes     (danh mục dùng chung — màn 72 · BRD mục 14)
--   + 5 bảng B5   : examinations · current_medications · previous_treatments ·
--                   clinical_escalations · treatment_recommendations (B6)
--   + order_status_mappings (B7 — ánh xạ mã POS, màn 23)
--   + 4 bảng mục 4: integration_accounts · sync_logs · sync_errors · staff_mappings
-- Các bảng sau 56 không có trong ERD nhưng đặc tả bắt buộc.
--
-- Chạy (idempotent, chạy lại nhiều lần không sao):
--   docker exec -i pancakebot-pg psql -U postgres -d pancakebot < scripts/init_crm.sql
--   psql "postgresql://postgres:postgres@127.0.0.1:5432/pancakebot" -f scripts/init_crm.sql
--
-- Toàn bộ nằm trong schema RIÊNG `crm`. Bản đồ schema của DB pancakebot:
--   public.*   -> bot RAG   (kich_ban, hoi_thoai_mau, trang_thai_khach)
--   watcher.*  -> watcher   (customers, hoi_thoai, canh_bao_tieu_cuc)
--   crm.*      -> 56 bảng dưới đây
-- Script này KHÔNG đụng gì ngoài schema crm (hàm/trigger cũng nằm trong crm).
--
-- ⚠️ CÓ 2 BẢNG TÊN `customers`: crm.customers (hồ sơ khách) và watcher.customers
-- (hàng đợi hội thoại). Query LUÔN ghi rõ schema, hoặc đặt search_path:
--     set search_path = crm, public;               -- trong phiên psql
--     options='-c search_path=crm,public'          -- trong chuỗi kết nối
--
-- QUY ƯỚC (theo tài liệu):
--   * PK: bigint generated always as identity
--   * created_at ở mọi bảng; updated_at ở bảng có sửa (trigger tự cập nhật)
--   * thời gian: timestamptz · tiền: numeric(14,2)
--   * trạng thái: text + CHECK, KHÔNG dùng ENUM gốc của Postgres
--
-- NHÓM A — đã chốt:
--   1. customers.primary_phone KHÔNG duy nhất, chỉ đánh index
--   2. ĐÃ thêm customer_treatments.order_id  (đơn hàng → liệu trình)
--   3. ĐÃ thêm users.password_hash + users.last_login_at (nullable, SSO vẫn dùng được)
--   4. 3 quan hệ đa hình giữ nguyên dạng (type, id), CHECK trên cột type, không FK
--
-- NHÓM B — đã chốt danh mục, tất cả đều là CHECK có ĐẶT TÊN nên sửa 1 dòng:
--       alter table X drop constraint ck_X_Y;
--       alter table X add  constraint ck_X_Y check (Y in (...));
--   teams.department · customer_identities.platform · pipelines.type
--   lead_reasons.category · treatment_templates.level · care_plan_steps.step_code
--   thang điểm triệu chứng 0–10 (customer_symptoms + symptom_assessments)
--   + các cột `status`/`platform` còn bỏ trống, theo đúng quy ước "trạng thái phải có CHECK"
--
-- NHÓM C — 2 cột ERD đọc không rõ, nay đã TRA RA từ đặc tả (hết đoán):
--   knowledge_documents.ai_permission = cột "Quyền AI"     — FR-140 + màn 47
--   scenario_steps.risk_level         = "Gán mức rủi ro"   — màn 50
--   scenario_steps.ai_permission      = "Gán quyền AI"     — màn 50 (bổ sung cùng lúc)
--   funnel_events.value               → chốt là TIỀN (VND) — vẫn là suy đoán
--
-- NHÓM D — CHƯA ĐỘNG (partition theo tháng, chính sách lưu ghi âm) — xem cuối file.
-- ============================================================

begin;

create schema if not exists crm;

-- Mọi `create table` không ghi schema ở dưới sẽ rơi vào crm.
-- public đứng sau để vẫn thấy extension vector và các kiểu dùng chung.
set local search_path = crm, public;

-- Hàm riêng của crm — CỐ Ý không dùng chung public.set_updated_at() của bot,
-- để script này không bao giờ ghi đè object của bot.
create or replace function crm.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;


-- ============================================================
-- MODULE 1 — TỔ CHỨC & PHÂN QUYỀN
-- ============================================================

create table if not exists pages (
    id               bigint generated always as identity primary key,
    external_page_id text not null,
    name             text not null,
    platform         text not null
                     check (platform in ('facebook','zalo','tiktok','website')),
    status           text not null default 'active'
                     check (status in ('active','paused','disconnected')),
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    unique (platform, external_page_id)
);
comment on table pages is 'Fanpage / kênh chat kết nối vào CRM';

create table if not exists permissions (
    id         bigint generated always as identity primary key,
    code       text not null unique,
    name       text not null,
    created_at timestamptz not null default now()
);
comment on column permissions.code is 'Dạng customer.view, order.approve';

create table if not exists roles (
    id          bigint generated always as identity primary key,
    name        text not null unique,
    description text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table if not exists role_permissions (
    role_id       bigint not null references roles(id)       on delete cascade,
    permission_id bigint not null references permissions(id) on delete cascade,
    created_at    timestamptz not null default now(),
    primary key (role_id, permission_id)
);

-- teams tạo TRƯỚC users (users.team_id trỏ về đây); manager_id gắn FK ở cuối
-- module vì hai bảng phụ thuộc vòng.
create table if not exists teams (
    id         bigint generated always as identity primary key,
    name       text not null unique,
    department text,
    manager_id bigint,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_teams_department check (department is null or department in
        ('sale','cskh','marketing','chuyen_mon','kho_van','admin'))
);
comment on column teams.department is
    'sale=bán hàng · cskh=chăm sóc khách · marketing · chuyen_mon=chuyên môn/y tế · kho_van=kho vận · admin=vận hành';

create table if not exists users (
    id                 bigint generated always as identity primary key,
    name               text not null,
    email              text not null unique,
    username           text unique,
    phone              text,
    status             text not null default 'active'
                       check (status in ('active','inactive','suspended')),
    team_id            bigint references teams(id) on delete set null,
    role_id            bigint references roles(id) on delete set null,
    password_hash      text,
    failed_login_count int not null default 0,
    locked_until       timestamptz,
    last_login_at      timestamptz,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
-- DB đã tạo từ bản cũ: bổ sung cột TRƯỚC khi comment (bảng mới thì 3 lệnh bỏ qua).
alter table users add column if not exists username           text unique;
alter table users add column if not exists failed_login_count int not null default 0;
alter table users add column if not exists locked_until       timestamptz;

comment on column users.password_hash is
    'Thêm ngoài ERD: để trống nếu đăng nhập bằng SSO';
comment on column users.username is
    'A2: tên đăng nhập ngắn (vd sale01) — AUTH-001. Đăng nhập được bằng username HOẶC email';
comment on column users.failed_login_count is
    'A2: số lần sai liên tiếp; đăng nhập đúng thì về 0 (FR-001 khoá tạm)';
comment on column users.locked_until is
    'A2: sai quá số lần → khoá tới thời điểm này; hết giờ tự mở, không cần cron';

-- ------------------------------------------------------------
-- user_sessions — phiên đăng nhập (A2, docs/A2-DANG-NHAP.md mục 2.2)
-- Thêm ngoài ERD: vừa là chỗ thu hồi refresh token khi logout, vừa là
-- "lịch sử đăng nhập + thiết bị" mà màn 1 yêu cầu.
-- Chỉ ghi thêm/thu hồi, không sửa nội dung → không có updated_at.
-- ------------------------------------------------------------
create table if not exists user_sessions (
    id                 bigint generated always as identity primary key,
    user_id            bigint not null references users(id) on delete cascade,
    refresh_token_hash text not null unique,
    ip_address         inet,
    user_agent         text,
    expires_at         timestamptz not null,
    revoked_at         timestamptz,
    last_used_at       timestamptz,
    created_at         timestamptz not null default now()
);
create index if not exists idx_user_sessions_user on user_sessions(user_id);
comment on column user_sessions.refresh_token_hash is
    'SHA-256 của refresh token — DB không giữ token thật, lộ DB cũng không dùng lại được';
comment on column user_sessions.revoked_at is
    'NULL = còn hiệu lực; logout/đổi mật khẩu thì đặt giá trị';

do $$
begin
    if not exists (select 1 from pg_constraint
                   where conname = 'fk_teams_manager'
                     and connamespace = 'crm'::regnamespace) then
        alter table crm.teams
            add constraint fk_teams_manager
            foreign key (manager_id) references crm.users(id) on delete set null;
    end if;
end $$;

create index if not exists idx_users_team on users (team_id);
create index if not exists idx_users_role on users (role_id);
create index if not exists idx_teams_manager on teams (manager_id);


-- ============================================================
-- MODULE 2 — KHÁCH HÀNG & TƯƠNG TÁC
-- ============================================================

create table if not exists customers (
    id             bigint generated always as identity primary key,
    customer_code  text unique,
    full_name      text not null,
    primary_phone  text,
    gender         text check (gender in ('male','female','other')),
    birth_date     date,
    province       text,
    source         text,
    status         text not null default 'new',
    merged_into_id bigint references customers(id) on delete set null,
    deleted_at     timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
-- DB tạo từ bản cũ: bổ sung cột + nới CHECK (B1)
alter table customers add column if not exists source         text;
alter table customers add column if not exists merged_into_id bigint references customers(id) on delete set null;
alter table customers add column if not exists deleted_at     timestamptz;
alter table customers drop constraint if exists customers_status_check;
alter table customers drop constraint if exists ck_customers_status;
alter table customers add constraint ck_customers_status
    check (status in ('new','consulting','customer','treating',
                      'completed','churned','blocked','merged'));

comment on column customers.primary_phone is
    'CỐ Ý không đặt UNIQUE: người nhà dùng chung số. LUÔN lưu dạng đã chuẩn hoá '
    '(0xxxxxxxxx — app/services/phone.py); chỉ đánh index để tra cứu';
comment on column customers.source is 'B1/FR-020: nguồn khách (pancake/facebook/zalo/tay...)';
comment on column customers.merged_into_id is
    'B1/FR-022: hồ sơ phụ sau gộp trỏ về hồ sơ chính, status = merged, KHÔNG xoá';
comment on column customers.deleted_at is 'B1/CUSTOMER-005: xoá mềm — đặc tả cấm xoá cứng';

create index if not exists idx_customers_phone  on customers (primary_phone);
create index if not exists idx_customers_status on customers (status);
create index if not exists idx_customers_song
    on customers (created_at desc) where deleted_at is null and status <> 'merged';

create table if not exists customer_identities (
    id                   bigint generated always as identity primary key,
    customer_id          bigint not null references customers(id) on delete cascade,
    platform             text,
    external_customer_id text,
    psid                 text,
    page_id              bigint references pages(id) on delete set null,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    constraint ck_customer_identities_platform check (platform is null or platform in
        ('facebook','zalo','tiktok','website'))
);
comment on column customer_identities.psid is 'ID phạm vi trang, chỉ duy nhất trong 1 page';
comment on column customer_identities.platform is 'Dùng chung danh mục với pages.platform';

create unique index if not exists uq_customer_identities_page_psid
    on customer_identities (page_id, psid) where psid is not null;
-- B1/FR-022: "External ID không được trùng sau hợp nhất" — chặn từ gốc luôn
create unique index if not exists uq_customer_identities_external
    on customer_identities (platform, external_customer_id)
    where external_customer_id is not null;
create index if not exists idx_customer_identities_customer
    on customer_identities (customer_id);

create table if not exists conversations (
    id                       bigint generated always as identity primary key,
    customer_id              bigint references customers(id) on delete set null,
    page_id                  bigint references pages(id) on delete set null,
    external_conversation_id text,
    status                   text not null default 'open'
                             check (status in ('open','pending','closed','spam')),
    last_message_at          timestamptz,
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now(),
    unique (page_id, external_conversation_id)
);
comment on column conversations.customer_id is
    'Cho phép rỗng: chat về trước khi kịp định danh khách';

create index if not exists idx_conversations_customer on conversations (customer_id);
create index if not exists idx_conversations_last_msg on conversations (last_message_at desc);

create table if not exists messages (
    id                  bigint generated always as identity primary key,
    conversation_id     bigint not null references conversations(id) on delete cascade,
    external_message_id text,
    sender_type         text not null
                        check (sender_type in ('customer','agent','bot','system')),
    sender_user_id      bigint references users(id) on delete set null,
    content             text,
    sent_at             timestamptz not null,
    created_at          timestamptz not null default now()
);
comment on table messages is
    'Bảng phình nhanh nhất. Sau 1-2 năm cân nhắc partition by range (sent_at)';

create index if not exists idx_messages_conversation on messages (conversation_id, sent_at desc);
create index if not exists idx_messages_sender_user  on messages (sender_user_id);

create table if not exists calls (
    id              bigint generated always as identity primary key,
    customer_id     bigint references customers(id) on delete set null,
    user_id         bigint references users(id)     on delete set null,
    external_call_id text unique,
    direction       text check (direction in ('inbound','outbound')),
    started_at      timestamptz not null,
    duration_sec    integer check (duration_sec >= 0),
    status          text check (status in ('answered','missed','busy','failed','voicemail')),
    recording_url   text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists idx_calls_customer on calls (customer_id, started_at desc);
create index if not exists idx_calls_user     on calls (user_id, started_at desc);

create table if not exists call_transcripts (
    id         bigint generated always as identity primary key,
    call_id    bigint not null references calls(id) on delete cascade,
    speaker    text check (speaker in ('agent','customer','unknown')),
    content    text,
    start_sec  numeric(10,2),
    end_sec    numeric(10,2),
    confidence numeric(4,3) check (confidence between 0 and 1),
    created_at timestamptz not null default now(),
    constraint ck_call_transcripts_range check (end_sec is null or start_sec is null or end_sec >= start_sec)
);

create index if not exists idx_call_transcripts_call on call_transcripts (call_id, start_sec);

create table if not exists call_evaluations (
    id            bigint generated always as identity primary key,
    call_id       bigint not null references calls(id) on delete cascade,
    score_total   numeric(6,2),
    risk_level    text check (risk_level in ('low','medium','high','critical')),
    summary       text,
    review_status text not null default 'pending'
                  check (review_status in ('pending','reviewed','disputed','closed')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
comment on column call_evaluations.risk_level is
    'Rủi ro tuân thủ: tư vấn viên hứa công dụng vượt hồ sơ. Đối chiếu product_versions.prohibited_claims';

create index if not exists idx_call_evaluations_call on call_evaluations (call_id);

create table if not exists tags (
    id         bigint generated always as identity primary key,
    name       text not null,
    type       text,
    created_at timestamptz not null default now(),
    unique (type, name)
);

create table if not exists customer_tags (
    customer_id bigint not null references customers(id) on delete cascade,
    tag_id      bigint not null references tags(id)      on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (customer_id, tag_id)
);

create table if not exists customer_assignments (
    id              bigint generated always as identity primary key,
    customer_id     bigint not null references customers(id) on delete cascade,
    user_id         bigint not null references users(id),
    assignment_type text not null,
    start_at        timestamptz not null default now(),
    end_at          timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
comment on column customer_assignments.assignment_type is 'sale / cskh / chuyên môn';
comment on column customer_assignments.end_at is 'Rỗng = đang phụ trách';

-- Mỗi khách, mỗi loại vai trò chỉ 1 người đang phụ trách tại một thời điểm
create unique index if not exists uq_customer_assignments_active
    on customer_assignments (customer_id, assignment_type) where end_at is null;
create index if not exists idx_customer_assignments_user on customer_assignments (user_id);


-- ============================================================
-- MODULE 3 — SALE & TƯ VẤN
-- ============================================================

create table if not exists pipelines (
    id         bigint generated always as identity primary key,
    name       text not null unique,
    type       text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_pipelines_type check (type is null or type in
        ('new_sale','upsell','reactivation'))
);
comment on column pipelines.type is
    'new_sale=bán mới · upsell=nâng liệu trình · reactivation=đánh thức khách cũ';

create table if not exists pipeline_stages (
    id          bigint generated always as identity primary key,
    pipeline_id bigint not null references pipelines(id) on delete cascade,
    code        text not null,
    name        text not null,
    sort_order  integer not null default 0,
    is_closed   boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (pipeline_id, code)
);
comment on column pipeline_stages.is_closed is 'true = giai đoạn kết thúc (thắng hoặc thua)';

create table if not exists lead_reasons (
    id         bigint generated always as identity primary key,
    code       text not null unique,
    name       text not null,
    category   text,
    created_at timestamptz not null default now(),
    constraint ck_lead_reasons_category check (category is null or category in
        ('price','trust','timing','competitor','health','other'))
);
comment on column lead_reasons.category is
    'price=giá · trust=niềm tin · timing=thời điểm · competitor=đối thủ · health=sức khỏe · other=khác';

create table if not exists leads (
    id               bigint generated always as identity primary key,
    customer_id      bigint not null references customers(id) on delete cascade,
    pipeline_id      bigint not null references pipelines(id),
    stage_id         bigint not null references pipeline_stages(id),
    owner_id         bigint references users(id) on delete set null,
    source           text,
    priority         text not null default 'normal'
                     check (priority in ('low','normal','high','urgent')),
    temperature      text,
    next_action_at   timestamptz,
    stage_entered_at timestamptz not null default now(),
    first_contact_at timestamptz,
    sla_due_at       timestamptz,
    closed_at        timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    constraint ck_leads_temperature check (temperature is null or temperature in
        ('nong','am','lanh'))
);
-- DB tạo từ bản cũ: bổ sung cột (bảng mới thì các lệnh dưới bỏ qua) — B3
alter table leads add column if not exists temperature      text;
alter table leads add column if not exists stage_entered_at timestamptz not null default now();
alter table leads add column if not exists first_contact_at timestamptz;
alter table leads add column if not exists sla_due_at       timestamptz;
alter table leads add column if not exists closed_at        timestamptz;
-- DB cũ thiếu CHECK inline ở trên (thêm 31/07/2026) — drop+add cho chạy lại được
alter table leads drop constraint if exists ck_leads_temperature;
alter table leads add constraint ck_leads_temperature
    check (temperature is null or temperature in ('nong','am','lanh'));

comment on column leads.temperature is
    'B3: lead score nóng/ấm/lạnh (BRD mục 7) — lọc màn 8/12, API LEAD-009 /leads/hot';
comment on column leads.stage_entered_at is
    'B3: thời điểm vào giai đoạn hiện tại — Kanban hiển thị "số ngày ở trạng thái"';
comment on column leads.first_contact_at is
    'B3: tương tác đầu tiên (FR-042 — SLA 15 phút); rỗng + quá sla_due_at = lead quá hạn';
comment on column leads.sla_due_at is
    'B3: hạn phải nhận/phản hồi (FR-030 "tạo thời hạn phản hồi", FR-042 SLA 5 phút)';
comment on column leads.closed_at is 'B3: thời điểm vào giai đoạn kết thúc (is_closed)';

create index if not exists idx_leads_customer    on leads (customer_id);
create index if not exists idx_leads_owner       on leads (owner_id);
create index if not exists idx_leads_stage       on leads (stage_id);
create index if not exists idx_leads_next_action on leads (next_action_at);
create index if not exists idx_leads_sla         on leads (sla_due_at)
    where closed_at is null and first_contact_at is null;
create index if not exists idx_leads_queue       on leads (created_at)
    where owner_id is null and closed_at is null;

-- stage_id phải thuộc đúng pipeline_id — FK thường không làm được, dùng trigger
-- Ghi rõ crm.pipeline_stages: hàm trigger chạy theo search_path của CONNECTION
-- gọi nó — app nối bằng search_path mặc định (public) là không thấy bảng.
create or replace function crm.check_lead_stage_pipeline()
returns trigger as $$
declare
    v_pipeline_id bigint;
begin
    select pipeline_id into v_pipeline_id from crm.pipeline_stages where id = new.stage_id;
    if v_pipeline_id is distinct from new.pipeline_id then
        raise exception 'stage_id % không thuộc pipeline_id %', new.stage_id, new.pipeline_id;
    end if;
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_leads_stage_pipeline on crm.leads;
create trigger trg_leads_stage_pipeline
    before insert or update of stage_id, pipeline_id on crm.leads
    for each row execute function crm.check_lead_stage_pipeline();

create table if not exists lead_stage_history (
    id            bigint generated always as identity primary key,
    lead_id       bigint not null references leads(id) on delete cascade,
    from_stage_id bigint references pipeline_stages(id),
    to_stage_id   bigint not null references pipeline_stages(id),
    changed_by    bigint references users(id) on delete set null,
    changed_at    timestamptz not null default now(),
    reason        text,
    note          text,
    created_at    timestamptz not null default now()
);
alter table lead_stage_history add column if not exists note text;  -- B3, FR-041
comment on column lead_stage_history.from_stage_id is 'Rỗng khi lead mới tạo';
comment on column lead_stage_history.note is 'FR-041: ghi chú thêm, tách khỏi lý do';

create index if not exists idx_lead_stage_history_lead on lead_stage_history (lead_id, changed_at desc);

create table if not exists lead_lost_reasons (
    id             bigint generated always as identity primary key,
    lead_id        bigint not null references leads(id) on delete cascade,
    lost_reason_id bigint not null references lead_reasons(id),
    note           text,
    evidence_type  text check (evidence_type in ('message','call','note')),
    evidence_id    bigint,
    created_at     timestamptz not null default now()
);
comment on column lead_lost_reasons.evidence_id is
    'QUAN HỆ ĐA HÌNH: trỏ messages hoặc calls tùy evidence_type — không có FK, phần mềm tự kiểm';

create index if not exists idx_lead_lost_reasons_lead on lead_lost_reasons (lead_id);

create table if not exists consultation_sessions (
    id           bigint generated always as identity primary key,
    customer_id  bigint not null references customers(id) on delete cascade,
    lead_id      bigint references leads(id) on delete set null,
    user_id      bigint references users(id) on delete set null,
    channel      text check (channel in ('chat','call','zalo','direct')),
    started_at   timestamptz,
    completed_at timestamptz,
    risk_level   text check (risk_level in ('low','medium','high','critical')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on column consultation_sessions.channel is 'direct = tư vấn trực tiếp';

create index if not exists idx_consultation_sessions_customer on consultation_sessions (customer_id);
create index if not exists idx_consultation_sessions_lead     on consultation_sessions (lead_id);

create table if not exists consultation_answers (
    id            bigint generated always as identity primary key,
    session_id    bigint not null references consultation_sessions(id) on delete cascade,
    question_code text not null,
    answer_text   text,
    answer_value  numeric(12,4),
    captured_at   timestamptz,
    created_at    timestamptz not null default now()
);
comment on column consultation_answers.answer_value is 'Bản số hóa để tính điểm / so sánh';

create index if not exists idx_consultation_answers_session on consultation_answers (session_id);

create table if not exists symptoms (
    id         bigint generated always as identity primary key,
    code       text not null unique,
    name       text not null,
    group_name text,
    created_at timestamptz not null default now()
);
comment on column symptoms.group_name is 'dạ dày / đại tràng / tiêu hóa chung';

create table if not exists customer_symptoms (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    symptom_id  bigint not null references symptoms(id),
    severity    integer,
    frequency   text check (frequency in ('rare','sometimes','often','daily','constant')),
    started_at  timestamptz,
    is_primary  boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint ck_customer_symptoms_severity check (severity is null or severity between 0 and 10),
    unique (customer_id, symptom_id)
);
comment on column customer_symptoms.severity is
    'Thang 0-10 (0 = không có, 10 = nặng nhất). Đổi thang thì drop constraint ck_customer_symptoms_severity';
comment on column customer_symptoms.frequency is
    'rare=hiếm, sometimes=thỉnh thoảng, often=thường, daily=hằng ngày, constant=liên tục';

create table if not exists safety_screenings (
    id              bigint generated always as identity primary key,
    customer_id     bigint not null references customers(id) on delete cascade,
    screening_type  text not null,
    value           text,
    risk_level      text check (risk_level in ('low','medium','high','critical')),
    requires_review boolean not null default false,
    created_at      timestamptz not null default now()
);
comment on table safety_screenings is
    'Chốt chặn an toàn (sụt cân, đi ngoài ra máu, nuốt nghẹn, thai kỳ, thuốc chống đông...). '
    'PHẢI kiểm tra trước khi tạo customer_treatments';

create index if not exists idx_safety_screenings_customer on safety_screenings (customer_id, created_at desc);

-- ------------------------------------------------------------
-- B5 — Hồ sơ tư vấn + sàng lọc an toàn (FR-050…053)
-- ------------------------------------------------------------

-- FR-050: phiếu triệu chứng cần thêm thời điểm xuất hiện / liên quan bữa ăn /
-- ghi chú (ghi chú CHỈ bổ sung, không thay dữ liệu cấu trúc — service chặn)
alter table customer_symptoms add column if not exists occurs_when   text;
alter table customer_symptoms add column if not exists meal_relation text
    check (meal_relation in ('truoc_an','sau_an','khi_doi','khong_lien_quan'));
alter table customer_symptoms add column if not exists note          text;

-- FR-053: cờ an toàn trên hồ sơ khách — red = cảnh báo đỏ, CHẶN đề xuất liệu
-- trình (B6 phải gọi consult_service.kiem_duoc_de_xuat trước khi đề xuất)
alter table customers add column if not exists safety_flag text
    check (safety_flag in ('red','yellow'));

-- FR-051: kết quả khám khách cung cấp (nội soi, HP, siêu âm...)
create table if not exists examinations (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    exam_type   text not null check (exam_type in ('noi_soi','hp','sieu_am',
                                                   'xet_nghiem','khac')),
    exam_date   date,
    facility    text,
    conclusion  text,
    file_url    text,
    created_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now()
);
create index if not exists idx_examinations_customer
    on examinations (customer_id, exam_date desc);

-- FR-052: thuốc/sản phẩm ĐANG dùng (nhân viên không tự khuyên dừng/đổi thuốc;
-- có phản ứng bất thường -> service tự mở ca chuyển chuyên môn)
create table if not exists current_medications (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    name        text not null,
    dosage      text,
    duration    text,
    is_active   boolean not null default true,
    effect      text,
    reaction    text,
    created_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists idx_current_medications_customer
    on current_medications (customer_id);

-- FR-052: điều trị/sản phẩm đã dùng TRƯỚC ĐÂY
create table if not exists previous_treatments (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    name        text not null,
    duration    text,
    result      text,
    note        text,
    created_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now()
);
create index if not exists idx_previous_treatments_customer
    on previous_treatments (customer_id);

-- FR-053 + SAFETY-003…005: ca chuyển chuyên môn (đi kèm 1 task duyet_chuyen_mon
-- của B4 để nằm trong "việc hôm nay" của người chuyên môn)
create table if not exists clinical_escalations (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    source      text not null default 'manual'
                check (source in ('safety_check','medication_risk','manual')),
    reason      text not null,
    risk_level  text check (risk_level in ('low','medium','high','critical')),
    status      text not null default 'pending'
                check (status in ('pending','resolved')),
    -- FK sang tasks gắn SAU (MODULE 6) — bảng tasks tạo ở dưới, khai inline
    -- ở đây là vỡ khi nạp DB mới tinh
    task_id     bigint,
    created_by  bigint references users(id) on delete set null,
    assigned_to bigint references users(id) on delete set null,
    resolution  text,
    resolved_by bigint references users(id) on delete set null,
    resolved_at timestamptz,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists idx_clinical_escalations_status
    on clinical_escalations (status, created_at desc);
create index if not exists idx_clinical_escalations_customer
    on clinical_escalations (customer_id);

-- FR-053: gỡ cảnh báo phải có dấu vết — screening được "xoá" bằng cleared_at
-- (người chuyên môn resolve), KHÔNG delete dòng
alter table safety_screenings add column if not exists cleared_at timestamptz;
alter table safety_screenings add column if not exists cleared_by bigint
    references users(id) on delete set null;


-- ============================================================
-- MODULE 4 — SẢN PHẨM, LIỆU TRÌNH & ĐƠN HÀNG
-- ============================================================

create table if not exists products (
    id                 bigint generated always as identity primary key,
    product_code       text unique,
    name               text not null,
    product_type       text,
    price              numeric(14,2) check (price >= 0),
    package            text,
    units_per_package  integer check (units_per_package > 0),
    status             text not null default 'active'
                       check (status in ('active','inactive','discontinued')),
    approval_status    text not null default 'draft'
                       check (approval_status in ('draft','pending','approved','rejected')),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
comment on column products.approval_status is
    'Trạng thái duyệt nội dung công bố. CHỈ sản phẩm approved mới được đưa vào tư vấn';

create table if not exists product_versions (
    id                bigint generated always as identity primary key,
    product_id        bigint not null references products(id) on delete cascade,
    version_no        integer not null,
    usage_text        text,
    approved_claims   jsonb not null default '[]'::jsonb,
    prohibited_claims jsonb not null default '[]'::jsonb,
    effective_from    timestamptz not null default now(),
    effective_to      timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (product_id, version_no)
);
comment on table product_versions is
    'Chỗ dựa pháp lý. Chấm call_evaluations phải đối chiếu phiên bản CÓ HIỆU LỰC TẠI THỜI ĐIỂM GỌI, không phải bản mới nhất';

create index if not exists idx_product_versions_effective
    on product_versions (product_id, effective_from desc);

create table if not exists treatment_templates (
    id            bigint generated always as identity primary key,
    template_code text not null,
    name          text not null,
    problem_group text,
    level         text,
    base_price    numeric(14,2) check (base_price >= 0),
    duration_days integer check (duration_days > 0),
    status        text not null default 'draft'
                  check (status in ('draft','active','archived')),
    version_no    integer not null default 1,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (template_code, version_no),
    constraint ck_treatment_templates_level check (level is null or level in
        ('mild','moderate','severe'))
);
comment on column treatment_templates.level is
    'mild=nhẹ · moderate=trung bình · severe=nặng';

create table if not exists treatment_template_items (
    id          bigint generated always as identity primary key,
    template_id bigint not null references treatment_templates(id) on delete cascade,
    product_id  bigint not null references products(id),
    quantity    numeric(12,2) not null check (quantity > 0),
    dose_text   text,
    sort_order  integer not null default 0,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists idx_treatment_template_items_template
    on treatment_template_items (template_id, sort_order);

create table if not exists treatment_rules (
    id             bigint generated always as identity primary key,
    template_id    bigint not null references treatment_templates(id) on delete cascade,
    rule_type      text not null,
    condition_json jsonb not null default '{}'::jsonb,
    action_json    jsonb not null default '{}'::jsonb,
    priority       integer not null default 0,
    status         text not null default 'active'
                   check (status in ('active','inactive')),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
comment on table treatment_rules is
    'Chống chỉ định, tăng/giảm liều theo triệu chứng, loại trừ khi có cờ đỏ';
comment on column treatment_rules.priority is 'Số lớn chạy trước';

create index if not exists idx_treatment_rules_template
    on treatment_rules (template_id, priority desc);

-- ------------------------------------------------------------
-- B6 — versioning giá + phiên bản đề xuất liệu trình (FR-060/062)
-- ------------------------------------------------------------

-- FR-060 "thay đổi giá tạo phiên bản mới": snapshot giá nằm cùng bảng phiên
-- bản nội dung — đơn cũ giữ giá cũ vì order_items chốt giá lúc lên đơn
alter table product_versions add column if not exists price numeric(14,2)
    check (price is null or price >= 0);

-- FR-062 "lưu phiên bản đề xuất": Sale chọn phương án từ rule engine -> lưu;
-- có cảnh báo thì phải chuyên môn duyệt (TREATMENT-011) mới tạo được liệu trình
create table if not exists treatment_recommendations (
    id             bigint generated always as identity primary key,
    customer_id    bigint not null references customers(id) on delete cascade,
    template_id    bigint not null references treatment_templates(id),
    recommended_by bigint references users(id) on delete set null,
    status         text not null default 'proposed'
                   check (status in ('proposed','pending_approval','approved','rejected')),
    needs_approval boolean not null default false,
    reasons        jsonb not null default '[]'::jsonb,
    warnings       jsonb not null default '[]'::jsonb,
    missing_info   jsonb not null default '[]'::jsonb,
    note           text,
    approved_by    bigint references users(id) on delete set null,
    approved_at    timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists idx_treatment_recommendations_customer
    on treatment_recommendations (customer_id, created_at desc);

create table if not exists orders (
    id               bigint generated always as identity primary key,
    customer_id      bigint not null references customers(id),
    external_order_id text unique,
    order_type       text check (order_type in ('new','repurchase','upsell','exchange')),
    sale_owner_id    bigint references users(id) on delete set null,
    cskh_owner_id    bigint references users(id) on delete set null,
    status           text not null default 'draft'
                     check (status in ('draft','confirmed','packing','shipping',
                                       'delivered','returned','cancelled')),
    total_amount     numeric(14,2) not null default 0 check (total_amount >= 0),
    delivered_at     timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
comment on column orders.delivered_at is
    'MỐC KHỞI TÍNH liệu trình và lịch CSKH — có index riêng';

create index if not exists idx_orders_customer     on orders (customer_id, created_at desc);
create index if not exists idx_orders_delivered_at on orders (delivered_at);
create index if not exists idx_orders_sale_owner   on orders (sale_owner_id);
create index if not exists idx_orders_cskh_owner   on orders (cskh_owner_id);

create table if not exists order_items (
    id                   bigint generated always as identity primary key,
    order_id             bigint not null references orders(id) on delete cascade,
    product_id           bigint not null references products(id),
    treatment_template_id bigint references treatment_templates(id),
    quantity             numeric(12,2) not null check (quantity > 0),
    unit_price           numeric(14,2) not null check (unit_price >= 0),
    line_total           numeric(14,2),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);
comment on column order_items.unit_price is
    'Giá TẠI THỜI ĐIỂM BÁN — không tra ngược products.price';

create index if not exists idx_order_items_order    on order_items (order_id);
create index if not exists idx_order_items_product  on order_items (product_id);
create index if not exists idx_order_items_template on order_items (treatment_template_id);

create table if not exists order_status_history (
    id          bigint generated always as identity primary key,
    order_id    bigint not null references orders(id) on delete cascade,
    from_status text,
    to_status   text,
    changed_at  timestamptz not null default now(),
    changed_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_order_status_history_order
    on order_status_history (order_id, changed_at desc);

create table if not exists customer_treatments (
    id                bigint generated always as identity primary key,
    customer_id       bigint not null references customers(id) on delete cascade,
    template_id       bigint references treatment_templates(id),
    order_id          bigint references orders(id) on delete set null,
    approved_by       bigint references users(id) on delete set null,
    start_date        date,
    expected_end_date date,
    status            text not null default 'planned'
                      check (status in ('planned','active','paused','completed','stopped')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
comment on column customer_treatments.order_id is
    'THÊM ngoài ERD: truy được đơn hàng nào sinh ra liệu trình (tính doanh thu theo liệu trình)';

create index if not exists idx_customer_treatments_customer on customer_treatments (customer_id);
create index if not exists idx_customer_treatments_order    on customer_treatments (order_id);
create index if not exists idx_customer_treatments_end_date on customer_treatments (expected_end_date);

create table if not exists customer_treatment_items (
    id                    bigint generated always as identity primary key,
    customer_treatment_id bigint not null references customer_treatments(id) on delete cascade,
    product_id            bigint not null references products(id),
    quantity              numeric(12,2) not null check (quantity > 0),
    dose_text             text,
    actual_start_date     date,
    actual_end_date       date,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index if not exists idx_customer_treatment_items_parent
    on customer_treatment_items (customer_treatment_id);


-- ------------------------------------------------------------
-- handovers — phiếu bàn giao Sale sang CSKH
-- KHÔNG có trong ERD 56 bảng, thêm theo FR-090/091, màn 24-25 và
-- nhóm API HANDOVER-001…006 (thuộc MVP).
-- ------------------------------------------------------------
create table if not exists handovers (
    id                    bigint generated always as identity primary key,
    customer_id           bigint not null references customers(id) on delete cascade,
    order_id              bigint references orders(id) on delete set null,
    customer_treatment_id bigint references customer_treatments(id) on delete set null,
    -- FK gắn sau khi care_plans được tạo (Module 5) — xem fk_handovers_care_plan
    care_plan_id          bigint,
    sale_user_id          bigint references users(id) on delete set null,
    cskh_user_id          bigint references users(id) on delete set null,
    status                text not null default 'pending'
                          check (status in ('pending','assigned','accepted','returned','completed')),
    -- FR-091: hồ sơ thiếu thì đánh dấu chưa hoàn tất, CSKH trả lại Sale bổ sung
    is_complete           boolean not null default false,
    missing_fields        jsonb not null default '[]'::jsonb,
    returned_reason       text,
    -- Nội dung phiếu bàn giao (màn 25)
    customer_condition    text,   -- Tình trạng khách
    main_symptoms         text,   -- Triệu chứng chính
    treatment_summary     text,   -- Liệu trình
    dose_text             text,   -- Cách dùng
    current_medications   text,   -- Thuốc đang dùng
    comorbidities         text,   -- Bệnh nền
    notes                 text,   -- Lưu ý
    concerns              text,   -- Băn khoăn
    sale_discussed        text,   -- Điều Sale đã trao đổi
    promises_made         text,   -- Cam kết đã nói
    cskh_watch_points     text,   -- Vấn đề CSKH cần theo dõi
    expected_start_date   date,   -- Ngày dự kiến bắt đầu
    accepted_at           timestamptz,
    returned_at           timestamptz,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);
comment on table handovers is
    'Sinh tự động khi đơn giao thành công (FR-090). Ngày giao thành công KHÔNG lưu ở đây, '
    'lấy từ orders.delivered_at để tránh lệch số liệu';
comment on column handovers.promises_made is
    'Cam kết Sale đã nói với khách — đối chiếu với product_versions.prohibited_claims khi rà tuân thủ';

-- Một đơn chỉ sinh một phiếu bàn giao: chặn automation chạy hai lần tạo trùng
create unique index if not exists uq_handovers_order
    on handovers (order_id) where order_id is not null;
create index if not exists idx_handovers_customer on handovers (customer_id);
create index if not exists idx_handovers_cskh     on handovers (cskh_user_id, status);
create index if not exists idx_handovers_pending  on handovers (status) where status = 'pending';


-- ============================================================
-- MODULE 5 — CSKH, CÔNG VIỆC & MUA LẠI
-- ============================================================

create table if not exists care_plans (
    id                    bigint generated always as identity primary key,
    customer_id           bigint not null references customers(id) on delete cascade,
    customer_treatment_id bigint references customer_treatments(id) on delete set null,
    owner_id              bigint references users(id) on delete set null,
    status                text not null default 'active'
                          check (status in ('active','paused','completed','cancelled')),
    started_at            timestamptz,
    ended_at              timestamptz,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index if not exists idx_care_plans_customer  on care_plans (customer_id);
create index if not exists idx_care_plans_treatment on care_plans (customer_treatment_id);
create index if not exists idx_care_plans_owner     on care_plans (owner_id);

-- handovers (Module 4) khai báo trước care_plans nên không gắn FK inline được.
do $$
begin
    if not exists (select 1 from pg_constraint
                   where conname = 'fk_handovers_care_plan'
                     and connamespace = 'crm'::regnamespace) then
        alter table crm.handovers
            add constraint fk_handovers_care_plan
            foreign key (care_plan_id) references crm.care_plans(id) on delete set null;
    end if;
end $$;
create index if not exists idx_handovers_care_plan on handovers (care_plan_id);

create table if not exists care_plan_steps (
    id           bigint generated always as identity primary key,
    care_plan_id bigint not null references care_plans(id) on delete cascade,
    step_code    text,
    planned_at   timestamptz,
    completed_at timestamptz,
    status       text not null default 'pending'
                 check (status in ('pending','due','done','skipped','failed')),
    result_code  text,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    constraint ck_care_plan_steps_step_code check (step_code is null or step_code in
        ('CS01',   -- Xác nhận đơn          — ngay khi Sale lên đơn
         'CS02',   -- Nhận hàng & onboarding — sau 3-5 ngày gửi / giao thành công
         'CS03',   -- Xác nhận bắt đầu dùng  — sau 2 ngày từ khi nhận (lấy actual_start_date)
         'CS04',   -- Đánh giá sớm           — NGÀY 4 dùng
         'CS05',   -- Kiểm tra tuân thủ      — NGÀY 10 dùng
         'CS06',   -- Đánh giá đáp ứng       — NGÀY 15 dùng (so điểm trước/sau)
         'CS07',   -- Chuẩn bị mua lại       — NGÀY 20 dùng (tạo cơ hội mua lại)
         'CS08',   -- Chốt liệu trình tiếp   — NGÀY 25 dùng
         'CS09',   -- Cứu cơ hội             — NGÀY 28 nếu chưa mua
         'CS10',   -- Chăm LT2               — sau giao liệu trình 2
         'CS11',   -- Chăm LT3 & duy trì     — sau giao liệu trình 3
         'khac'))  -- lối thoát cho mốc phát sinh
);
comment on column care_plan_steps.step_code is
    'Quy trình chuẩn 11 bước CS01-CS11 theo BRD mục 14.3. Mốc ngày 4/10/15/20/25/28 tính từ '
    'ngày BẮT ĐẦU DÙNG THẬT (actual_start_date lấy ở CS03), KHÔNG phải ngày giao hàng. '
    'Tên + kích hoạt + dữ liệu bắt buộc từng bước: xem crm.ref_codes nhóm care_step. '
    'Dùng ''khac'' cho mốc phát sinh thay vì phá CHECK';

create index if not exists idx_care_plan_steps_plan   on care_plan_steps (care_plan_id);
create index if not exists idx_care_plan_steps_due    on care_plan_steps (planned_at) where status in ('pending','due');

create table if not exists care_interactions (
    id                bigint generated always as identity primary key,
    care_plan_step_id bigint references care_plan_steps(id) on delete set null,
    customer_id       bigint not null references customers(id) on delete cascade,
    user_id           bigint references users(id) on delete set null,
    channel           text check (channel in ('call','chat','zalo','sms','direct')),
    contacted         boolean,
    summary           text,
    next_action_at    timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists idx_care_interactions_customer on care_interactions (customer_id, created_at desc);
create index if not exists idx_care_interactions_step     on care_interactions (care_plan_step_id);

create table if not exists symptom_assessments (
    id                  bigint generated always as identity primary key,
    care_interaction_id bigint not null references care_interactions(id) on delete cascade,
    symptom_id          bigint not null references symptoms(id),
    before_score        numeric(6,2),
    current_score       numeric(6,2),
    change_score        numeric(6,2) generated always as (before_score - current_score) stored,
    created_at          timestamptz not null default now(),
    constraint ck_symptom_assessments_scale check (
        (before_score  is null or before_score  between 0 and 10) and
        (current_score is null or current_score between 0 and 10))
);
comment on column symptom_assessments.change_score is
    'Cột tính tự động = before_score - current_score; DƯƠNG = cải thiện (khoảng -10..10)';
comment on constraint ck_symptom_assessments_scale on symptom_assessments is
    'Thang 0-10, khớp customer_symptoms.severity. Đổi thang thì drop cả 2 constraint ck_*_scale / ck_*_severity';

create index if not exists idx_symptom_assessments_interaction
    on symptom_assessments (care_interaction_id);
create index if not exists idx_symptom_assessments_symptom
    on symptom_assessments (symptom_id);

create table if not exists tasks (
    id           bigint generated always as identity primary key,
    customer_id  bigint references customers(id) on delete cascade,
    assigned_to  bigint references users(id) on delete set null,
    task_type    text not null,
    due_at       timestamptz,
    priority     text not null default 'normal'
                 check (priority in ('low','normal','high','urgent')),
    status       text not null default 'open'
                 check (status in ('open','in_progress','done','cancelled','overdue')),
    related_type text check (related_type in ('lead','order','care_plan_step',
                                              'customer_treatment','repurchase_opportunity')),
    related_id   bigint,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on column tasks.related_id is
    'QUAN HỆ ĐA HÌNH theo related_type — không đặt được FK, phần mềm tự kiểm';

-- B4 (mục 19 BRD): tiêu đề + kết quả bắt buộc khi đóng + ai tạo + dấu leo thang
alter table tasks add column if not exists title        text;
alter table tasks add column if not exists result       text;
alter table tasks add column if not exists created_by   bigint references users(id) on delete set null;
alter table tasks add column if not exists completed_at timestamptz;
alter table tasks add column if not exists escalated_at timestamptz;
comment on column tasks.result is
    'Mục 19 BRD: KHÔNG đóng việc nếu thiếu kết quả — service chặn, cột này giữ bằng chứng';
comment on column tasks.escalated_at is
    'Worker quét việc quá hạn đánh dấu + ghi audit (báo quản lý theo SLA); dời lịch thì xoá dấu';

create index if not exists idx_tasks_assigned on tasks (assigned_to, status, due_at);
create index if not exists idx_tasks_customer on tasks (customer_id);
create index if not exists idx_tasks_related  on tasks (related_type, related_id);

-- FK task_id của clinical_escalations (MODULE 3 — B5) gắn ở đây vì tasks tạo
-- sau nó; drop trước cho chạy lại được
alter table clinical_escalations drop constraint if exists fk_clinical_escalations_task;
alter table clinical_escalations add constraint fk_clinical_escalations_task
    foreign key (task_id) references tasks(id) on delete set null;

create table if not exists repurchase_opportunities (
    id                   bigint generated always as identity primary key,
    customer_id          bigint not null references customers(id) on delete cascade,
    current_treatment_id bigint references customer_treatments(id) on delete set null,
    next_template_id     bigint references treatment_templates(id),
    owner_id             bigint references users(id) on delete set null,
    expected_close_date  date,
    expected_value       numeric(14,2) check (expected_value >= 0),
    stage                text not null default 'identified'
                         check (stage in ('identified','contacted','negotiating',
                                          'won','lost','postponed')),
    lost_reason_id       bigint references lead_reasons(id),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);
comment on table repurchase_opportunities is
    'Sinh tự động bằng job quét customer_treatments sắp đến expected_end_date';

create index if not exists idx_repurchase_customer  on repurchase_opportunities (customer_id);
create index if not exists idx_repurchase_owner     on repurchase_opportunities (owner_id, stage);
create index if not exists idx_repurchase_treatment on repurchase_opportunities (current_treatment_id);

create table if not exists reactivation_campaigns (
    id                bigint generated always as identity primary key,
    name              text not null,
    segment_rule_json jsonb not null default '{}'::jsonb,
    start_at          timestamptz,
    end_at            timestamptz,
    status            text not null default 'draft'
                      check (status in ('draft','running','paused','finished')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create table if not exists reactivation_members (
    id          bigint generated always as identity primary key,
    campaign_id bigint not null references reactivation_campaigns(id) on delete cascade,
    customer_id bigint not null references customers(id) on delete cascade,
    assigned_to bigint references users(id) on delete set null,
    status      text not null default 'pending'
                check (status in ('pending','contacted','responded','converted',
                                  'refused','unreachable')),
    result      text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (campaign_id, customer_id)
);

create index if not exists idx_reactivation_members_customer on reactivation_members (customer_id);


-- ============================================================
-- MODULE 6 — KHO KIẾN THỨC, AI & MARKETING
-- ============================================================

create table if not exists knowledge_documents (
    id                bigint generated always as identity primary key,
    title             text not null,
    category          text,
    topic             text,
    source            text,
    keywords          text[] not null default '{}',
    applicable_to     text,
    contraindication  text,
    risk_level        text,
    status            text not null default 'draft',
    ai_permission     text not null default 'internal',
    approved_by       bigint references users(id) on delete set null,
    effective_from    timestamptz,
    effective_to      timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    constraint ck_knowledge_documents_status check (status in
        ('draft','pending','approved','archived')),
    constraint ck_knowledge_documents_ai_permission check (ai_permission in
        ('none','internal','send_customer')),
    constraint ck_knowledge_documents_risk check (risk_level is null or risk_level in
        ('low','medium','high','critical'))
);
comment on column knowledge_documents.topic is 'Chủ đề — cột của màn 47';
comment on column knowledge_documents.source is 'Nguồn trích dẫn — FR-140, màn 48';
comment on column knowledge_documents.keywords is
    'Từ khóa (màn 48). Mảng text, tra bằng toán tử @> với index GIN bên dưới';
comment on column knowledge_documents.applicable_to is 'Đối tượng áp dụng — màn 48';
comment on column knowledge_documents.contraindication is 'Trường hợp không dùng — màn 48';
comment on column knowledge_documents.risk_level is 'Mức rủi ro — màn 48';

create index if not exists idx_knowledge_documents_keywords
    on knowledge_documents using gin (keywords);
create index if not exists idx_knowledge_documents_effective
    on knowledge_documents (status, effective_from desc);
comment on column knowledge_documents.ai_permission is
    'Cột "Quyền AI" — chốt theo FR-140 (danh sách dữ liệu) và màn 47 (cột cuối bảng). '
    'none=AI không được dùng · internal=AI dùng để soạn cho nhân viên, không gửi thẳng khách · '
    'send_customer=được phép gửi cho khách. Ăn khớp FR-142 (nhân viên duyệt trước khi gửi).';

create table if not exists knowledge_versions (
    id                   bigint generated always as identity primary key,
    document_id          bigint not null references knowledge_documents(id) on delete cascade,
    version_no           integer not null,
    content              text,
    content_for_customer text,
    created_by           bigint references users(id) on delete set null,
    approved_at          timestamptz,
    created_at           timestamptz not null default now(),
    unique (document_id, version_no)
);
comment on column knowledge_versions.content is 'Nội dung NỘI BỘ — màn 48';
comment on column knowledge_versions.content_for_customer is
    'Nội dung ĐƯỢC PHÉP GỬI KHÁCH — màn 48. Chỉ dùng khi '
    'knowledge_documents.ai_permission = ''send_customer''';

create table if not exists consultation_scenarios (
    id            bigint generated always as identity primary key,
    name          text not null,
    problem_group text,
    version_no    integer not null default 1,
    status        text not null default 'draft',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint ck_consultation_scenarios_status check (status in
        ('draft','active','archived'))
);

create table if not exists scenario_rules (
    id             bigint generated always as identity primary key,
    scenario_id    bigint not null references consultation_scenarios(id) on delete cascade,
    condition_json jsonb not null default '{}'::jsonb,
    action_json    jsonb not null default '{}'::jsonb,
    priority       integer not null default 0,
    status         text not null default 'active',
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    constraint ck_scenario_rules_status check (status in ('active','inactive'))
);
comment on column scenario_rules.priority is 'Số lớn chạy trước (giống treatment_rules)';

create index if not exists idx_scenario_rules_scenario
    on scenario_rules (scenario_id, priority desc);

create table if not exists scenario_steps (
    id               bigint generated always as identity primary key,
    scenario_id      bigint not null references consultation_scenarios(id) on delete cascade,
    step_code        text,
    step_type        text,
    question_text    text,
    customer_message text,
    required         boolean not null default false,
    next_step_code   text,
    risk_level       text,
    ai_permission    text not null default 'internal',
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    unique (scenario_id, step_code),
    constraint ck_scenario_steps_type check (step_type is null or step_type in
        ('question','message','action','branch','block','end')),
    constraint ck_scenario_steps_risk check (risk_level is null or risk_level in
        ('low','medium','high','critical')),
    constraint ck_scenario_steps_ai_permission check (ai_permission in
        ('none','internal','send_customer'))
);
comment on column scenario_steps.risk_level is
    'Cột "Gán mức rủi ro" của màn 50 (Trình thiết kế cây kịch bản). Dùng chung thang với '
    'consultation_sessions / call_evaluations / safety_screenings / ai_recommendations';
comment on column scenario_steps.ai_permission is
    'Cột "Gán quyền AI" của màn 50. Cùng danh mục với knowledge_documents.ai_permission';
comment on column scenario_steps.step_type is
    'question=hỏi khách · message=đọc mẫu câu · action=thao tác · branch=rẽ nhánh theo scenario_rules · '
    'block=chặn bước (màn 50 "Chặn bước") · end=kết thúc';
comment on column scenario_steps.question_text is 'Câu hỏi cho tư vấn viên';
comment on column scenario_steps.customer_message is 'Mẫu câu nói với khách';

create table if not exists ad_campaigns (
    id                  bigint generated always as identity primary key,
    external_campaign_id text not null,
    name                text not null,
    platform            text not null,
    status              text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (platform, external_campaign_id),
    constraint ck_ad_campaigns_platform check (platform in
        ('facebook','google','tiktok','zalo')),
    constraint ck_ad_campaigns_status check (status is null or status in
        ('active','paused','archived','deleted'))
);
comment on constraint ck_ad_campaigns_status on ad_campaigns is
    'Theo trạng thái chuẩn của Meta/Google/TikTok Ads';

create table if not exists ad_sets (
    id              bigint generated always as identity primary key,
    campaign_id     bigint not null references ad_campaigns(id) on delete cascade,
    external_adset_id text unique,
    name            text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists idx_ad_sets_campaign on ad_sets (campaign_id);

create table if not exists ads (
    id            bigint generated always as identity primary key,
    ad_set_id     bigint not null references ad_sets(id) on delete cascade,
    external_ad_id text unique,
    name          text,
    creative_id   text,
    status        text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint ck_ads_status check (status is null or status in
        ('active','paused','archived','deleted'))
);

create index if not exists idx_ads_ad_set on ads (ad_set_id);

create table if not exists lead_attributions (
    id            bigint generated always as identity primary key,
    customer_id   bigint references customers(id) on delete cascade,
    lead_id       bigint references leads(id) on delete cascade,
    campaign_id   bigint references ad_campaigns(id) on delete set null,
    ad_set_id     bigint references ad_sets(id) on delete set null,
    ad_id         bigint references ads(id) on delete set null,
    touch_type    text check (touch_type in ('first','last','assisted')),
    attributed_at timestamptz,
    created_at    timestamptz not null default now()
);
comment on table lead_attributions is
    'Một lead có nhiều bản ghi quy nguồn (chạm đầu / cuối / hỗ trợ) — tính được cả hai mô hình quy nguồn';

create index if not exists idx_lead_attributions_lead     on lead_attributions (lead_id);
create index if not exists idx_lead_attributions_customer on lead_attributions (customer_id);
create index if not exists idx_lead_attributions_campaign on lead_attributions (campaign_id);

create table if not exists funnel_events (
    id          bigint generated always as identity primary key,
    customer_id bigint references customers(id) on delete cascade,
    lead_id     bigint references leads(id) on delete set null,
    order_id    bigint references orders(id) on delete set null,
    event_type  text not null,
    event_at    timestamptz not null default now(),
    value       numeric(14,2),
    created_at  timestamptz not null default now()
);
comment on table funnel_events is 'Bảng nhật ký, phình nhanh';
comment on column funnel_events.value is
    'ĐOÁN: chốt là TIỀN (VND) — giá trị quy cho sự kiện phễu, để cộng doanh thu theo nguồn. '
    'Sự kiện không có tiền thì để rỗng';

create index if not exists idx_funnel_events_customer on funnel_events (customer_id, event_at desc);
create index if not exists idx_funnel_events_type     on funnel_events (event_type, event_at desc);

create table if not exists ai_recommendations (
    id                  bigint generated always as identity primary key,
    customer_id         bigint references customers(id) on delete cascade,
    session_id          bigint references consultation_sessions(id) on delete set null,
    recommendation_type text,
    content             text,
    source_refs         jsonb not null default '[]'::jsonb,
    risk_level          text check (risk_level in ('low','medium','high','critical')),
    accepted_by         bigint references users(id) on delete set null,
    created_at          timestamptz not null default now()
);
comment on column ai_recommendations.source_refs is
    'QUAN HỆ ĐA HÌNH: nguồn trích dẫn, nên trỏ về knowledge_versions.id — không FK';
comment on column ai_recommendations.accepted_by is
    'NGƯỜI THẬT đã duyệt gợi ý của máy trước khi nói với khách';

create index if not exists idx_ai_recommendations_customer on ai_recommendations (customer_id, created_at desc);
create index if not exists idx_ai_recommendations_session  on ai_recommendations (session_id);


-- ============================================================
-- MODULE 7 — NHẬT KÝ (ngoài ERD 56 bảng)
-- ============================================================

-- ------------------------------------------------------------
-- audit_logs — FR-180, màn 77, API AUDIT-001/002 (thuộc MVP)
-- Chỉ GHI THÊM, không sửa không xoá → cố ý KHÔNG có updated_at và không có trigger.
-- ------------------------------------------------------------
create table if not exists audit_logs (
    id          bigint generated always as identity primary key,
    user_id     bigint references users(id) on delete set null,
    action      text not null,
    object_type text not null,
    object_id   bigint,
    old_value   jsonb,
    new_value   jsonb,
    reason      text,
    ip_address  inet,
    user_agent  text,
    created_at  timestamptz not null default now()
);
comment on table audit_logs is
    'Bảng chỉ ghi thêm. Mọi API có ghi dữ liệu đều phải chèn 1 dòng (yêu cầu kỹ thuật, API mục XXXVI). '
    'Phình nhanh — ứng viên partition theo tháng cùng nhóm với messages/funnel_events';
comment on column audit_logs.user_id is 'Rỗng = hành động của hệ thống (worker, automation)';
comment on column audit_logs.object_type is 'Tên bảng hoặc loại đối tượng bị tác động';
comment on column audit_logs.object_id is 'QUAN HỆ ĐA HÌNH theo object_type — không đặt được FK';
comment on column audit_logs.user_agent is 'Phần "thiết bị" của màn 77, đi kèm ip_address';

create index if not exists idx_audit_logs_object
    on audit_logs (object_type, object_id, created_at desc);
create index if not exists idx_audit_logs_user
    on audit_logs (user_id, created_at desc);
create index if not exists idx_audit_logs_created
    on audit_logs (created_at desc);


-- ------------------------------------------------------------
-- ref_codes — danh mục dùng chung (màn 72), thêm ngoài ERD gốc.
-- Chứa các bộ mã BRD định nghĩa nhưng không có bảng riêng:
--   cskh_state  C01-C09  · care_step CS01-CS11 · care_result RS01-RS12
--   automation  AU01-AU13 (tham chiếu, chưa phải máy luật)
--   adherence_level / diet_compliance / adverse_event / bowel_status /
--   repurchase_readiness / contact_result / next_action  (BRD bảng 19)
-- Nạp dữ liệu bằng scripts/seed_danh_muc.py (idempotent).
-- ------------------------------------------------------------
create table if not exists ref_codes (
    id          bigint generated always as identity primary key,
    group_code  text not null,
    code        text not null,
    name        text not null,
    description text,
    extra       jsonb not null default '{}'::jsonb,
    sort_order  integer not null default 0,
    status      text not null default 'active'
                check (status in ('active','inactive')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (group_code, code)
);
comment on table ref_codes is
    'Danh mục dùng chung (màn 72). Cột nghiệp vụ kiểu text (vd care_plan_steps.result_code) '
    'tra giá trị hợp lệ ở đây thay vì khoá cứng bằng CHECK — sửa danh mục không phải ALTER';
comment on column ref_codes.extra is
    'Chi tiết theo nhóm: care_step giữ {kich_hoat, muc_tieu, kenh, du_lieu_bat_buoc, ngoai_le}; '
    'automation giữ {khi, thi, uu_tien}; cskh_state giữ {dieu_kien_vao, dieu_kien_ra}';

create index if not exists idx_ref_codes_group on ref_codes (group_code, sort_order);


-- ------------------------------------------------------------
-- Bổ sung B7 — Đơn hàng (FR-080…082, màn 21-23)
-- 1) orders.status nâng 7 -> 11 trạng thái chuẩn (thêm pending /
--    awaiting_shipment / collected / returning) để phủ đủ vòng đời
--    17 mã của Pancake POS mà không mất thông tin quan trọng.
-- 2) Cột pos_* nhận diện + lưu vết đơn đồng bộ từ Pancake POS
--    (Open API pos.pages.fm/api/v1 — dò 01/08, xem scripts/do_pos_api.py).
-- 3) order_status_mappings: ánh xạ mã POS -> trạng thái CRM, admin sửa
--    được ở màn 23 (ORDER-010) — seed 17 mã, on conflict DO NOTHING để
--    KHÔNG đè chỉnh sửa của admin khi chạy lại file này.
-- ------------------------------------------------------------
alter table orders drop constraint if exists orders_status_check;
alter table orders drop constraint if exists ck_orders_status;
alter table orders add constraint ck_orders_status check (status in
    ('draft','pending','confirmed','packing','awaiting_shipment','shipping',
     'delivered','collected','returning','returned','cancelled'));

alter table orders add column if not exists source text not null default 'crm'
    check (source in ('crm','pancake_pos'));
alter table orders add column if not exists note                text;
alter table orders add column if not exists pos_shop_id         bigint;
alter table orders add column if not exists pos_order_id        bigint;
alter table orders add column if not exists pos_status          integer;
alter table orders add column if not exists pos_conversation_id text;
alter table orders add column if not exists pos_page_id         text;
alter table orders add column if not exists pos_inserted_at     timestamptz;
alter table orders add column if not exists pos_updated_at      timestamptz;
alter table orders add column if not exists pos_raw             jsonb;

comment on column orders.source is
    'crm = tạo tay trong CRM; pancake_pos = đồng bộ từ Pancake POS (B7)';
comment on column orders.pos_status is
    'Mã trạng thái GỐC của POS (0…20) ở lần đồng bộ cuối — orders.status là bản ĐÃ ánh xạ';
comment on column orders.pos_raw is
    'Nguyên văn đơn POS lần đồng bộ cuối — giống watcher giữ raw hội thoại: '
    'sau này cần trường nào (vận đơn, phí ship, UTM...) moi ra được, khỏi gọi lại API';

create unique index if not exists uq_orders_pos
    on orders (pos_shop_id, pos_order_id)
    where pos_shop_id is not null and pos_order_id is not null;
create index if not exists idx_orders_status on orders (status);

-- Lý do đổi trạng thái: 'pos_sync' = máy đồng bộ đổi; còn lại người ghi
alter table order_status_history add column if not exists reason text;

create table if not exists order_status_mappings (
    id                  bigint generated always as identity primary key,
    pancake_status      integer not null unique,
    pancake_status_name text not null default '',
    crm_status          text not null check (crm_status in
        ('draft','pending','confirmed','packing','awaiting_shipment','shipping',
         'delivered','collected','returning','returned','cancelled')),
    note                text,
    updated_by          bigint references users(id) on delete set null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
comment on table order_status_mappings is
    'Ánh xạ mã trạng thái Pancake POS -> 11 trạng thái CRM (FR-081, màn 23). '
    'Đồng bộ đọc bảng này MỖI LẦN chạy — admin sửa là lượt sau ăn ngay';

insert into order_status_mappings (pancake_status, pancake_status_name, crm_status) values
    ( 0, 'Mới',            'draft'),
    (17, 'Chờ xác nhận',   'pending'),
    (11, 'Chờ hàng',       'confirmed'),
    (20, 'Đã đặt hàng',    'confirmed'),
    ( 1, 'Đã xác nhận',    'confirmed'),
    (12, 'Chờ in',         'packing'),
    (13, 'Đã in',          'packing'),
    ( 8, 'Đang đóng hàng', 'packing'),
    ( 9, 'Chờ chuyển hàng','awaiting_shipment'),
    ( 2, 'Đã gửi hàng',    'shipping'),
    ( 3, 'Đã nhận',        'delivered'),
    (16, 'Đã thu tiền',    'collected'),
    ( 4, 'Đang hoàn',      'returning'),
    (15, 'Hoàn một phần',  'returning'),
    ( 5, 'Đã hoàn',        'returned'),
    ( 6, 'Đã hủy',         'cancelled'),
    ( 7, 'Đã xóa',         'cancelled')
on conflict (pancake_status) do nothing;


-- ------------------------------------------------------------
-- Bổ sung MỤC 4 BRD — TÍCH HỢP PANCAKE & NGUỒN QUẢNG CÁO
--   "Đồng bộ khách, hội thoại, đơn hàng và nguồn quảng cáo về CRM mà
--    không làm mất dữ liệu hoặc tạo trùng."
--   4 bảng mới: integration_accounts · sync_logs · sync_errors · staff_mappings
--   + cột lưu vết đồng bộ (source / external_updated_at / synced_at) theo đúng
--     câu "Lưu external_id, source, page_id, updated_at_external, synced_at"
--   + nới cây quảng cáo để nhận ad_id Pancake trả về khi CHƯA có cây campaign
--     (Facebook Ads API là việc của C-MVP5 — lấp campaign/adset sau, không chặn)
-- ------------------------------------------------------------

-- Kết nối: MỘT dòng cho mỗi tài khoản/kênh nối vào (nhiều tài khoản Pancake +
-- nhiều shop POS đều nằm chung bảng này, phân biệt bằng provider).
-- ⚠️ KHÔNG lưu token thật ở DB — token nằm trong .env; ở đây chỉ giữ bản CHE
-- (token_hint) + tình trạng để cảnh báo "token lỗi/hết hạn" theo luật mục 4.
create table if not exists integration_accounts (
    id               bigint generated always as identity primary key,
    provider         text not null check (provider in ('pancake_pages','pancake_pos')),
    name             text not null,
    external_id      text not null default '',
    status           text not null default 'active'
                     check (status in ('active','paused','error','disconnected')),
    token_status     text not null default 'unknown'
                     check (token_status in ('unknown','ok','invalid','missing')),
    token_hint       text,
    token_checked_at timestamptz,
    last_ok_at       timestamptz,
    last_error       text,
    last_error_at    timestamptz,
    config           jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    unique (provider, external_id)
);
comment on table integration_accounts is
    'Kết nối ngoài (mục 4): pancake_pages = tài khoản pages.fm (chat), '
    'pancake_pos = shop POS (đơn). external_id = shop_id với POS, rỗng với pages.fm';
comment on column integration_accounts.token_hint is
    'Token ĐÃ CHE (4 ký tự cuối) chỉ để đối chiếu — token thật luôn ở .env';
comment on column integration_accounts.token_status is
    'Luật mục 4 "Token lỗi/hết hạn phải cảnh báo": invalid/missing -> màn Tích hợp báo đỏ';

-- Page: gắn về tài khoản, bật/tắt đồng bộ từng page, giữ lỗi gần nhất
alter table pages add column if not exists account_id bigint
    references integration_accounts(id) on delete set null;
alter table pages add column if not exists sync_enabled   boolean not null default true;
alter table pages add column if not exists last_synced_at timestamptz;
alter table pages add column if not exists last_error     text;
alter table pages add column if not exists last_error_at  timestamptz;
alter table pages add column if not exists external_shop_id text;
comment on column pages.sync_enabled is
    'Tắt = poller vẫn chạy cho bot nhưng KHÔNG đổ page này vào CRM (mục 4, màn Tích hợp)';
comment on column pages.external_shop_id is 'Shop POS chứa page này — dùng để ánh xạ đơn về đúng page';

-- Nhật ký đồng bộ (màn "Nhật ký đồng bộ"): mỗi LƯỢT chạy một dòng
create table if not exists sync_logs (
    id            bigint generated always as identity primary key,
    provider      text not null check (provider in ('pancake_pages','pancake_pos')),
    -- 'message' là giá trị message_sync.py ghi thật từ lâu nhưng file này chưa
    -- bao giờ liệt kê -> DB dựng mới sẽ chặn nhật ký đồng bộ tin nhắn (vá 04/08).
    entity        text not null
                  check (entity in ('conversation','message','order','customer',
                                    'tag','page','staff')),
    scope         text,
    run_type      text not null default 'poll'
                  check (run_type in ('poll','manual','backfill','webhook','retry')),
    status        text not null default 'running'
                  check (status in ('running','success','partial','failed')),
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    duration_ms   integer,
    created_count integer not null default 0,
    updated_count integer not null default 0,
    skipped_count integer not null default 0,
    error_count   integer not null default 0,
    message       text,
    created_at    timestamptz not null default now()
);
comment on table sync_logs is
    'Mỗi lượt đồng bộ 1 dòng (mục 4: "đồng bộ bù, retry queue và sync log"). '
    'Bảng nhật ký, phình theo nhịp worker — dọn định kỳ bằng integration_service.don_log_cu';
comment on column sync_logs.scope is 'Page ngoài (pancake_pages) hoặc shop_id (pancake_pos); rỗng = toàn bộ';

create index if not exists idx_sync_logs_moi on sync_logs (started_at desc);
create index if not exists idx_sync_logs_provider on sync_logs (provider, started_at desc);

-- Hàng đợi lỗi (màn "Danh sách lỗi") — GIỮ NGUYÊN VĂN bản ghi để chạy lại được
create table if not exists sync_errors (
    id            bigint generated always as identity primary key,
    provider      text not null check (provider in ('pancake_pages','pancake_pos')),
    -- 'message' là giá trị message_sync.py ghi thật từ lâu nhưng file này chưa
    -- bao giờ liệt kê -> DB dựng mới sẽ chặn nhật ký đồng bộ tin nhắn (vá 04/08).
    entity        text not null
                  check (entity in ('conversation','message','order','customer',
                                    'tag','page','staff')),
    external_id   text not null,
    scope         text,
    payload       jsonb not null default '{}'::jsonb,
    error_type    text,
    error_message text not null default '',
    retry_count   integer not null default 0,
    next_retry_at timestamptz not null default now(),
    last_tried_at timestamptz,
    status        text not null default 'pending'
                  check (status in ('pending','resolved','given_up')),
    sync_log_id   bigint references sync_logs(id) on delete set null,
    resolved_at   timestamptz,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
comment on table sync_errors is
    'Retry queue mục 4: dòng nào đồng bộ hỏng thì nằm đây kèm payload gốc, '
    'worker thử lại theo backoff; quá số lần thì given_up để người xử lý tay';
comment on column sync_errors.payload is
    'Nguyên văn bản ghi từ Pancake — chạy lại KHÔNG cần gọi lại API (dữ liệu cũ gọi lại cũng không còn)';

-- Mỗi (nguồn, thực thể, id ngoài) chỉ 1 dòng ĐANG CHỜ — thử lại hỏng tiếp thì
-- cộng retry_count vào chính dòng đó, không sinh hàng nghìn dòng trùng.
create unique index if not exists uq_sync_errors_dang_cho
    on sync_errors (provider, entity, external_id) where status = 'pending';
create index if not exists idx_sync_errors_hang_doi
    on sync_errors (next_retry_at) where status = 'pending';

-- Ánh xạ nhân viên Pancake -> nhân viên CRM (màn "Ánh xạ Page/nhân viên/trạng thái đơn")
create table if not exists staff_mappings (
    id                bigint generated always as identity primary key,
    provider          text not null check (provider in ('pancake_pages','pancake_pos')),
    external_staff_id text not null,
    external_name     text,
    user_id           bigint references users(id) on delete set null,
    role_hint         text,
    last_seen_at      timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (provider, external_staff_id)
);
comment on table staff_mappings is
    'Nhân viên xử lý bên Pancake (assignee_ids / assigning_seller_id / assigning_care_id) '
    'ứng với ai trong CRM. Chưa ánh xạ thì user_id rỗng — vẫn ghi lại để Admin gán sau';
comment on column staff_mappings.role_hint is 'seller / care / marketer / inbox — biết id này đến từ vai nào bên Pancake';

-- Hồ sơ nhân viên lấy từ DANH SÁCH của POS (GET /shops/{id}/users), khác với các
-- dòng chỉ nhặt được id trần trong đơn. Cùng một bảng vì `external_staff_id` là
-- uuid TOÀN CỤC của Pancake (đã đối chiếu: 21/21 id thấy trong đơn đều nằm trong
-- danh sách) — tách bảng thứ hai là đẻ ra hai nguồn sự thật cho cùng con người.
-- KHÔNG có cột nào cho `api_key`: mỗi dòng POS trả về mang api_key riêng của
-- người đó, cố ý không lưu và không log (cùng luật với token ở màn Cài đặt).
alter table staff_mappings add column if not exists shop_id     text;
alter table staff_mappings add column if not exists email       text;
alter table staff_mappings add column if not exists phone       text;
alter table staff_mappings add column if not exists department  text;
alter table staff_mappings add column if not exists fb_id       text;
alter table staff_mappings add column if not exists avatar_url  text;
alter table staff_mappings add column if not exists raw         jsonb;
alter table staff_mappings add column if not exists synced_at   timestamptz;
comment on column staff_mappings.shop_id is 'Shop POS thấy người này lần cuối (api_key POS cấp theo từng shop)';
comment on column staff_mappings.department is 'Tên phòng ban bên POS (SALE OCP · CSKH NT · ADS…) — thứ người đọc hiểu được, khác `role` của POS là bitmask số';
comment on column staff_mappings.raw is 'Nguyên văn 1 dòng POS, ĐÃ LỌC BỎ api_key/note_api_key';
comment on column staff_mappings.synced_at is 'Lần cuối lấy từ DANH SÁCH POS. Rỗng = mới chỉ nhặt được id trong đơn, chưa có hồ sơ';
-- Ghép nhanh theo email/SĐT khi máy gợi ý cặp POS ↔ CRM.
create index if not exists idx_staff_mappings_email on staff_mappings (lower(email))
    where email is not null;

-- Mẻ "lấy danh sách nhân viên" cũng ghi nhật ký như mọi mẻ đồng bộ khác -> nới
-- CHECK cho 'staff'. Nhân thể vá 'message': message_sync.py ghi giá trị đó từ
-- lâu mà danh sách trên chưa có, nên DB nào dựng đúng file này là gãy chỗ đó.
-- Nới cả sync_errors cho khỏi lệch, dù hàng đợi lỗi chưa nhận việc staff.
alter table sync_logs   drop constraint if exists sync_logs_entity_check;
alter table sync_logs   add  constraint sync_logs_entity_check
    check (entity in ('conversation','message','order','customer','tag','page','staff'));
alter table sync_errors drop constraint if exists sync_errors_entity_check;
alter table sync_errors add  constraint sync_errors_entity_check
    check (entity in ('conversation','message','order','customer','tag','page','staff'));

-- Lưu vết đồng bộ trên chính dữ liệu (mục 4: external_id, source, page_id,
-- updated_at_external, synced_at). external_id + page_id đã có sẵn từ B1/B2.
alter table conversations add column if not exists source               text;
alter table conversations add column if not exists external_updated_at  timestamptz;
alter table conversations add column if not exists synced_at            timestamptz;
alter table conversations add column if not exists assignee_external_id text;
alter table conversations add column if not exists assignee_user_id     bigint
    references users(id) on delete set null;
alter table conversations add column if not exists external_tags jsonb not null default '[]'::jsonb;
alter table conversations add column if not exists message_count integer;
alter table conversations add column if not exists unread_count  integer;
alter table conversations add column if not exists snippet       text;
-- Đợt 2 — LOẠI hội thoại. Bình luận và tin nhắn riêng khác nhau ở hai điểm chí
-- mạng: bình luận thường không kéo được nội dung tin, và cửa gửi tin của Meta
-- cũng khác. Không phân biệt được thì lead bình luận lọt vào bảng việc Sale mà
-- nhân viên mở ra chẳng có gì để tư vấn.
alter table conversations add column if not exists kind text not null
    default 'inbox';
do $$ begin
    alter table conversations add constraint conversations_kind_check
        check (kind in ('inbox','comment','phone','khac'));
exception when duplicate_object then null; end $$;
comment on column conversations.kind is
    'inbox | comment | phone | khac — dịch từ trường `type` của Pancake. Bảng '
    'việc Sale lọc theo cột này (Cài đặt → Nguồn lead vào bảng việc)';
create index if not exists idx_conversations_kind
    on conversations (customer_id, kind);
comment on column conversations.external_updated_at is
    'updated_at BÊN PANCAKE ở lần đồng bộ cuối — so mốc này để biết có gì mới, '
    'KHÔNG so updated_at của CRM (trigger tự đổi mỗi lần ghi)';
comment on column conversations.synced_at is 'Lần cuối dòng này được đồng bộ về (mục 4)';
comment on column conversations.external_tags is 'ID thẻ Pancake nguyên bản; bản dịch ra tên nằm ở crm.tags/customer_tags';

alter table customers           add column if not exists synced_at timestamptz;
alter table customer_identities add column if not exists synced_at timestamptz;
alter table orders              add column if not exists synced_at timestamptz;

-- Quảng cáo: Pancake CHỈ trả ad_id + post_id (không có cây campaign/adset), nên
-- ad_set_id phải cho rỗng — nếu không thì mọi ad_id thật đều không lưu nổi.
-- C-MVP5 kéo Facebook Ads API về sẽ lấp campaign/adset cho các dòng này.
alter table ads alter column ad_set_id drop not null;
alter table ads add column if not exists post_id  text;
alter table ads add column if not exists platform text;
alter table ads add column if not exists first_seen_at timestamptz;
comment on column ads.ad_set_id is
    'Rỗng = mới biết ad_id (từ đơn Pancake POS), chưa biết nó thuộc adset/campaign nào';

alter table lead_attributions add column if not exists source         text;
alter table lead_attributions add column if not exists external_ad_id text;
alter table lead_attributions add column if not exists post_id        text;
alter table lead_attributions add column if not exists utm  jsonb not null default '{}'::jsonb;
comment on column lead_attributions.source is 'pancake_pos / pancake_pages / ads_api (C-MVP5)';
comment on column lead_attributions.utm is 'p_utm_* của đơn POS: {source, medium, campaign, content, term, id}';

-- first_touch / last_touch: mỗi khách đúng 1 dòng mỗi loại chạm (mục 4).
-- Chạm hỗ trợ ('assisted') không bị ràng buộc này — cần bao nhiêu dòng cũng được.
create unique index if not exists uq_lead_attributions_cham
    on lead_attributions (customer_id, touch_type)
    where customer_id is not null and touch_type in ('first','last');


-- ------------------------------------------------------------
-- Bổ sung MỤC 4 (phần NGUỒN QUẢNG CÁO) — cây quảng cáo thật + chi phí
--   Nguồn: Pancake POS **Ads Manager** (pos.pages.fm/api/v1/shops/{id}/ads_manager/*)
--   — dò 01/08: ad_accounts · campaigns_v2 · ad_sets_v2 · ads_v2, mỗi dòng kèm
--   `insights` (spend, impressions, clicks, reach, cpc, cpm, ctr, frequency).
--   Nhờ vậy KHÔNG cần Facebook Ads API riêng vẫn có chi phí để tính ROAS.
--
--   ⚠️ Chỉ ads của TÀI KHOẢN QUẢNG CÁO đã nối vào POS mới có chi phí. Ad nào
--   thấy trên đơn (orders.pos_raw.ad_id) mà chưa nối tài khoản thì vẫn được lưu
--   (biết doanh thu, chưa biết chi phí) — màn báo cáo hiện "—" ở cột chi phí.
-- ------------------------------------------------------------
alter table ad_campaigns add column if not exists external_account_id text;
alter table ad_campaigns add column if not exists account_name        text;
alter table ad_campaigns add column if not exists objective           text;
alter table ad_campaigns add column if not exists effective_status    text;
alter table ad_campaigns add column if not exists daily_budget        numeric(14,2);
alter table ad_campaigns add column if not exists lifetime_budget     numeric(14,2);
alter table ad_campaigns add column if not exists start_time          timestamptz;
alter table ad_campaigns add column if not exists end_time            timestamptz;
alter table ad_campaigns add column if not exists currency            text;
alter table ad_campaigns add column if not exists synced_at           timestamptz;
-- POS trả trạng thái Facebook (ACTIVE/PAUSED/ARCHIVED/DELETED, có cả
-- CAMPAIGN_PAUSED, IN_PROCESS…) — CHECK cũ 4 giá trị chặn mất; hạ về chuẩn hoá
-- trong code (ads_sync._trang_thai) rồi giữ CHECK cho giá trị đã chuẩn.
alter table ad_campaigns drop constraint if exists ck_ad_campaigns_status;
alter table ad_campaigns add constraint ck_ad_campaigns_status
    check (status is null or status in ('active','paused','archived','deleted','other'));

alter table ad_sets add column if not exists status            text;
alter table ad_sets add column if not exists effective_status  text;
alter table ad_sets add column if not exists optimization_goal text;
alter table ad_sets add column if not exists destination_type  text;
alter table ad_sets add column if not exists daily_budget      numeric(14,2);
alter table ad_sets add column if not exists lifetime_budget   numeric(14,2);
alter table ad_sets add column if not exists start_time        timestamptz;
alter table ad_sets add column if not exists end_time          timestamptz;
alter table ad_sets add column if not exists targeting         jsonb;
alter table ad_sets add column if not exists synced_at         timestamptz;
alter table ad_sets drop constraint if exists ck_ad_sets_status;
alter table ad_sets add constraint ck_ad_sets_status
    check (status is null or status in ('active','paused','archived','deleted','other'));
-- Adset có thể biết trước ad (đồng bộ từ ads_v2) — cho phép chưa gắn campaign,
-- lượt đồng bộ cây sau sẽ lấp. Cùng lý do với ads.ad_set_id ở trên.
alter table ad_sets alter column campaign_id drop not null;

alter table ads add column if not exists external_account_id text;
alter table ads add column if not exists creative_name       text;
alter table ads add column if not exists object_story_id     text;
alter table ads add column if not exists effective_status    text;
alter table ads add column if not exists created_time        timestamptz;
alter table ads add column if not exists synced_at           timestamptz;
alter table ads drop constraint if exists ck_ads_status;
alter table ads add constraint ck_ads_status
    check (status is null or status in ('active','paused','archived','deleted','other'));
comment on column ads.object_story_id is
    'Bài viết gốc của creative (dạng <page_id>_<post_id>) — nối được về post_id trên đơn POS';

-- Chi phí + chỉ số THEO NGÀY. Vì sao theo ngày: API trả số ĐÃ TỔNG HỢP theo
-- khoảng thời gian truyền vào, nên muốn phục vụ mọi cửa sổ (7/30/60/90 ngày của
-- ADS-010) thì phải lưu hạt mịn nhất rồi tự cộng. Đồng bộ 1 lời gọi/ngày/cấp.
create table if not exists ad_metrics_daily (
    id          bigint generated always as identity primary key,
    entity_type text not null check (entity_type in ('campaign','ad_set','ad')),
    entity_id   bigint not null,
    external_id text not null,
    ngay        date not null,
    spend       numeric(14,2) not null default 0,
    impressions bigint not null default 0,
    clicks      bigint not null default 0,
    reach       bigint not null default 0,
    cpc         numeric(14,2),
    cpm         numeric(14,2),
    ctr         numeric(10,4),
    frequency   numeric(10,4),
    currency    text,
    source      text not null default 'pancake_pos',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (entity_type, entity_id, ngay)
);
comment on table ad_metrics_daily is
    'Chi phí/chỉ số quảng cáo theo NGÀY (Pancake POS Ads Manager). Quan hệ đa hình '
    '(entity_type, entity_id) theo đúng quy ước NHÓM A mục 4 của file này — không FK. '
    'Cộng theo cửa sổ để ra chi phí 7/30/60/90 ngày; ROAS = doanh thu quy nguồn / chi phí';

create index if not exists idx_ad_metrics_ngay on ad_metrics_daily (ngay desc);
create index if not exists idx_ad_metrics_entity
    on ad_metrics_daily (entity_type, entity_id, ngay desc);

-- ------------------------------------------------------------
-- CÀI ĐẶT HỆ THỐNG chỉnh được trên web (màn 78 · SYSTEM-001/002)
--   Chỉ lưu phần NGƯỜI ĐÃ ĐỔI. Mô tả/kiểu/khoảng hợp lệ/giá trị mặc định nằm
--   trong CODE (app/core/runtime_config.py `MUC`) — thêm một cài đặt mới là
--   thêm một dòng Python, KHÔNG phải chạy migration.
--   Chưa có dòng nào ở đây = dùng đúng giá trị trong .env như trước giờ.
-- ------------------------------------------------------------
create table if not exists app_settings (
    code       text primary key,
    value      text not null,
    updated_by bigint references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
comment on table app_settings is
    'Công tắc + nhịp chạy đổi được trên web, worker đọc lại mỗi vòng nên KHÔNG phải '
    'khởi động lại server. Thiếu dòng nào thì lấy mặc định từ .env';


-- Nhật ký/hàng đợi lỗi nhận thêm loại 'ad' (đồng bộ cây + chi phí quảng cáo)
-- và 'message' (FR-012 — đồng bộ nội dung tin nhắn về crm.messages)
--
-- ⚠️ ĐÂY LÀ LẦN SỬA CUỐI của CHECK này trong file — nó GHI ĐÈ lệnh ở mục 4
-- (dòng ~1701). Danh sách dưới phải là HỢP của cả hai chỗ, thiếu giá trị nào là
-- DB đang chạy có dòng đó sẽ làm cả script rollback. Lần trước rơi mất 'staff'
-- và mọi máy đã đồng bộ nhân viên đều không nạp lại được schema.
alter table sync_logs   drop constraint if exists sync_logs_entity_check;
alter table sync_logs   add constraint sync_logs_entity_check
    check (entity in ('conversation','message','order','customer','tag','page',
                      'staff','ad'));
alter table sync_errors drop constraint if exists sync_errors_entity_check;
alter table sync_errors add constraint sync_errors_entity_check
    check (entity in ('conversation','message','order','customer','tag','page',
                      'staff','ad'));


-- ------------------------------------------------------------
-- FR-012 (CONV-001…006) — nội dung tin nhắn đầy đủ về crm.messages
--   Khối nâng-cấp-DB-cũ: bảng messages/conversations tạo ở MODULE trên,
--   các cột dưới đây bồi thêm cho DB đã chạy trước bản này.
-- ------------------------------------------------------------
-- Tin nhắn giữ NGUYÊN VĂN từ Pancake: người gửi bản gốc (id + tên hiển thị),
-- loại tin, file/ảnh/video đính kèm. KHÔNG bao giờ update content (luật FR-012
-- "không chỉnh sửa nội dung gốc" — on conflict do nothing ở tầng repo).
alter table messages add column if not exists sender_external_id text;
alter table messages add column if not exists sender_name        text;
alter table messages add column if not exists msg_type           text;
alter table messages add column if not exists attachments        jsonb;
comment on column messages.sender_external_id is
    'from.id bên Pancake — khách là PSID, page trả lời thì trùng page_id';
comment on column messages.attachments is
    'Danh sách file/ảnh/video [{type,url}] — url là link Pancake, không tải về';

-- Idempotent theo (hội thoại, id tin bên Pancake): đồng bộ lại không nhân đôi.
-- Partial index vì tin hệ thống/tay có thể không mang external id.
create unique index if not exists uq_messages_conv_external
    on messages (conversation_id, external_message_id)
    where external_message_id is not null;

-- Mốc lần cuối kéo TIN NHẮN (khác synced_at = lần cuối chạm HỘI THOẠI):
-- worker chỉ kéo hội thoại có external_updated_at mới hơn mốc này.
alter table conversations add column if not exists messages_synced_at timestamptz;
create index if not exists idx_conversations_msg_stale
    on conversations (external_updated_at desc)
    where external_conversation_id is not null;


-- ------------------------------------------------------------
-- TRUNG TÂM THÔNG BÁO (màn 3 · NOTIFY-001…004)
--   11 loại theo danh sách màn hình. Thông báo KHÔNG tự sinh trong service
--   nghiệp vụ mà do worker `notifications` QUÉT DB định kỳ rồi đẩy vào đây —
--   nhờ vậy thêm/bớt loại thông báo không phải sửa luật B1…B8.
--   `dedupe_key` chặn trùng: quét lại 5 phút/lần vẫn chỉ một dòng cho mỗi
--   (người nhận, sự việc). Đã đọc rồi thì KHÔNG sinh lại (xem repo.day).
-- ------------------------------------------------------------
create table if not exists notifications (
    id           bigint generated always as identity primary key,
    user_id      bigint not null references users(id) on delete cascade,
    type         text not null,
    title        text not null,
    body         text,
    link         text,
    priority     text not null default 'normal'
                 check (priority in ('low','normal','high','urgent')),
    related_type text,
    related_id   bigint,
    dedupe_key   text not null,
    read_at      timestamptz,
    created_at   timestamptz not null default now()
);
comment on column notifications.dedupe_key is
    'Khoá chống trùng do nguồn quét đặt, vd "viec_qua_han:123" — worker chạy lại không đẻ dòng mới';
comment on column notifications.link is
    'Đường dẫn mở thẳng màn liên quan (bấm vào dòng thông báo là tới nơi)';

create unique index if not exists uq_notifications_dedupe
    on notifications (user_id, dedupe_key);
create index if not exists idx_notifications_user_moi
    on notifications (user_id, created_at desc);
create index if not exists idx_notifications_chua_doc
    on notifications (user_id) where read_at is null;

-- NOTIFY-004: mỗi người tự tắt loại mình không muốn nhận. Thiếu dòng = BẬT
-- (mặc định nhận hết) — bảng chỉ giữ phần người đã đổi, giống app_settings.
create table if not exists notification_settings (
    user_id    bigint not null references users(id) on delete cascade,
    type       text not null,
    enabled    boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, type)
);


-- ============================================================
-- B9 — CHĂM SÓC 11 BƯỚC (FR-100…110 · CARE/ASSESSMENT/NORESPONSE)
--   * care_plans: ngày bắt đầu THẬT (mốc 4/10/15/20/25 tính từ đây — FR-102),
--     trạng thái pipeline CSKH C01-C09 (màn 27), chu kỳ liệu trình 1/2/3
--   * care_plan_steps: phiếu chăm dạng jsonb (trường bắt buộc + bộ giá trị
--     nằm ở ref_codes nhóm care_step / 7 bộ giá trị — bảng 18-19 BRD)
--   * customers: cờ "yêu cầu ngừng liên hệ" (NORESPONSE-004, AU11)
--   * 2 bảng mới: chuỗi không phản hồi (FR-110) — DB 74→76 bảng
-- ============================================================
alter table care_plans add column if not exists actual_start_date date;
alter table care_plans add column if not exists cskh_state text not null default 'C01';
alter table care_plans add column if not exists cycle_no   integer not null default 1
    check (cycle_no between 1 and 9);
comment on column care_plans.actual_start_date is
    'FR-102: ngày BẮT ĐẦU DÙNG THẬT (CS03 ghi) — mốc CS04-08 tính từ đây, '
    'KHÔNG phải ngày giao. Chưa có = chưa sinh mốc đánh giá';
comment on column care_plans.cskh_state is
    'Pipeline CSKH C01-C09 (ref_codes nhóm cskh_state, BRD bảng 17) — màn 27. '
    'Không đặt CHECK cứng: danh mục nằm ở ref_codes, service tự kiểm';
comment on column care_plans.cycle_no is
    'Chu kỳ liệu trình: 1 = LT đầu, 2/3 = mua lại (CS10/CS11 — FR-109)';
create index if not exists idx_care_plans_state on care_plans (cskh_state)
    where status = 'active';

alter table care_plan_steps add column if not exists data jsonb not null default '{}'::jsonb;
alter table care_plan_steps add column if not exists note text;
alter table care_plan_steps add column if not exists completed_by bigint
    references users(id) on delete set null;
comment on column care_plan_steps.data is
    'Phiếu chăm của mốc (FR-103…108): trường bắt buộc theo ref_codes '
    'care_step.attrs.du_lieu_bat_buoc, giá trị chuẩn theo 7 bộ giá trị (bảng 19)';
-- Mỗi kế hoạch mỗi mã mốc chỉ 1 dòng (CS10/CS11 chu kỳ sau nằm ở plan mới);
-- mốc phát sinh dùng step_code='khac' nên được phép lặp
create unique index if not exists uq_care_plan_steps_ma
    on care_plan_steps (care_plan_id, step_code) where step_code <> 'khac';

alter table customers add column if not exists do_not_contact boolean not null default false;
alter table customers add column if not exists do_not_contact_at timestamptz;
alter table customers add column if not exists do_not_contact_reason text;
comment on column customers.do_not_contact is
    'FR-110/NORESPONSE-004 + AU11: khách yêu cầu NGỪNG liên hệ — mọi automation '
    'chăm sóc/bám đuổi phải bỏ qua khách này; chỉ mở lại khi có đồng ý mới (C09)';

-- FR-110 — chuỗi không phản hồi chuẩn: nhắn 1 → gọi 1 → nhắn 2 → gọi 2
-- → tạm mất liên lạc (C08) → đưa vào tái kích hoạt (B10)
create table if not exists no_response_sequences (
    id                bigint generated always as identity primary key,
    customer_id       bigint not null references customers(id) on delete cascade,
    care_plan_step_id bigint references care_plan_steps(id) on delete set null,
    status            text not null default 'active'
                      check (status in ('active','closed')),
    outcome           text check (outcome is null or outcome in
                      ('responded','lost_contact','do_not_contact')),
    started_by        bigint references users(id) on delete set null,
    close_reason      text,
    closed_by         bigint references users(id) on delete set null,
    closed_at         timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
comment on table no_response_sequences is
    'FR-110: mỗi lần khách im lặng mở 1 chuỗi; 4 lần chạm đủ mà im → '
    'lost_contact + care_plans.cskh_state=C08; khách lên tiếng → responded';
-- 1 khách chỉ 1 chuỗi ĐANG CHẠY (mở chuỗi mới khi cái cũ chưa đóng là lỗi luật)
create unique index if not exists uq_no_response_dang_chay
    on no_response_sequences (customer_id) where status = 'active';

create table if not exists no_response_attempts (
    id           bigint generated always as identity primary key,
    sequence_id  bigint not null references no_response_sequences(id) on delete cascade,
    attempt_no   integer not null check (attempt_no between 1 and 4),
    channel      text not null check (channel in ('message','call')),
    result       text,
    note         text,
    attempted_by bigint references users(id) on delete set null,
    attempted_at timestamptz not null default now(),
    created_at   timestamptz not null default now(),
    unique (sequence_id, attempt_no)
);
comment on column no_response_attempts.attempt_no is
    'Thứ tự chuẩn FR-110: 1=nhắn · 2=gọi · 3=nhắn · 4=gọi — service ép đúng kênh';
comment on column no_response_attempts.result is
    'Bộ giá trị contact_result (ref_codes): Kết nối/Không nghe/Sai số/Hẹn lại/Từ chối';


-- ============================================================
-- B10 — MUA LẠI & KHÁCH NGỦ (FR-120…123 · REPURCHASE-001…010)
--   Bảng repurchase_opportunities + reactivation_* có sẵn từ đầu; ở đây chỉ
--   thêm cột phiếu FR-121. 9 trạng thái màn 40 (chưa/sắp/đến hạn/quá hạn…)
--   KHÔNG lưu cột riêng — suy từ stage + expected_close_date lúc đọc
--   (service `trang_thai_hien_thi`), khỏi cần worker chạy đêm đổi trạng thái.
-- ============================================================
alter table repurchase_opportunities add column if not exists readiness text;
alter table repurchase_opportunities add column if not exists lost_note text;
alter table repurchase_opportunities add column if not exists stage_moved_at timestamptz;
comment on column repurchase_opportunities.readiness is
    'FR-121 mức sẵn sàng — bộ giá trị repurchase_readiness trong ref_codes '
    '(Sẵn sàng/Cân nhắc/Chưa sẵn sàng/Từ chối)';
comment on column repurchase_opportunities.lost_note is
    'FR-122/REPURCHASE-006: lý do CHUẨN nằm ở lost_reason_id (lead_reasons '
    '9 mã BRD); cột này giữ diễn giải thêm + bằng chứng chat/call';
comment on column repurchase_opportunities.stage_moved_at is
    'Mốc vào stage hiện tại — màn 40 hiện "ở trạng thái bao lâu"';


-- ============================================================
-- C1 — HẠNG THẺ & VOUCHER (port từ mẫu Kallet: hang-the.php · voucher.php)
--
--   Mẫu PHP để hạng thẻ ở cột `customers.hang_the` + tổng chi tiêu ở
--   `customers.tong_chi_tieu`. Ta giữ NGUYÊN nếp đó (denormalise 2 cột) vì:
--     * màn Khách hàng lọc theo hạng, đếm theo hạng — tính lại mỗi lần đọc
--       thì mọi truy vấn phải quét cả bảng orders;
--     * "chỉ NÂNG hạng, không ai bị tụt" là luật CÓ TRẠNG THÁI — phải nhớ hạng
--       cũ mới biết có được đổi hay không, suy từ đơn hàng là mất luật này.
--   Nguồn số vẫn là orders (đơn `delivered`); dịch vụ card_service tính lại.
-- ============================================================
alter table customers add column if not exists card_rank text;
alter table customers add column if not exists total_spent numeric(14,2) not null default 0;
alter table customers add column if not exists last_delivered_at timestamptz;
comment on column customers.card_rank is
    'Mã hạng thẻ hiện tại (crm.card_ranks.code). NULL = chưa xếp hạng. '
    'CHỈ NÂNG — xem services/card_service.tinh_lai_hang';
comment on column customers.total_spent is
    'Tổng tiền đơn đã giao thành công. Cột đệm, tính lại từ orders';
comment on column customers.last_delivered_at is
    'Ngày nhận hàng gần nhất — nền cho luật "180 ngày không mua thì giảm '
    'quyền lợi ngầm 1 bậc" (hạng HIỂN THỊ giữ nguyên)';
create index if not exists idx_customers_card_rank on customers (card_rank);

create table if not exists card_ranks (
    id         bigint generated always as identity primary key,
    code       text not null unique,
    name       text not null,
    emoji      text not null default '',
    min_spent  numeric(14,2),
    max_spent  numeric(14,2),
    sort_order int not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
comment on table card_ranks is
    'Bậc thang hạng thẻ. min_spent NULL = CHƯA ĐIỀN (màn Cài đặt tô cam "chưa '
    'điền", KHÔNG hiểu là 0) — hạng chưa có ngưỡng thì không xếp ai vào.';
comment on column card_ranks.sort_order is
    'Cao hơn = hạng to hơn. Luật "chỉ nâng" so bằng cột này, không so tiền';

create table if not exists card_rank_benefits (
    id            bigint generated always as identity primary key,
    rank_code     text not null references card_ranks(code) on delete cascade,
    benefit_key   text not null,
    benefit_value text not null default '',
    sort_order    int not null default 0,
    created_at    timestamptz not null default now()
);
create index if not exists idx_card_rank_benefits on card_rank_benefits (rank_code);

create table if not exists vouchers (
    id            bigint generated always as identity primary key,
    customer_id   bigint not null references customers(id) on delete cascade,
    code          text not null default '',
    amount        numeric(14,2) not null default 0 check (amount >= 0),
    granted_by_kind text not null default 'nguoi'
                    check (granted_by_kind in ('may','nguoi')),
    granted_by    bigint references users(id) on delete set null,
    order_from_id bigint references orders(id) on delete set null,
    granted_on    date not null default current_date,
    expires_on    date not null,
    status        text not null default 'con_han'
                  check (status in ('chua_bao_ma','con_han','da_dung',
                                    'het_han_khong_dung','da_tra_lai')),
    order_used_id bigint references orders(id) on delete set null,
    pos_discount  numeric(14,2),
    note          text not null default '',
    updated_by    bigint references users(id) on delete set null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
comment on column vouchers.code is
    'Trống = CHƯA BÁO MÃ cho khách (status chua_bao_ma) — đây là VIỆC CẦN LÀM, '
    'không phải lỗi dữ liệu';
comment on column vouchers.granted_by_kind is
    'may = automation tặng · nguoi = nhân viên tặng. Màn Voucher tách hẳn 2 cột '
    'tiền vì thưởng chăm sóc chỉ tính phần NGƯỜI tặng';
comment on column vouchers.pos_discount is
    'Số tiền POS thực giảm khi đơn dùng voucher. Lệch mệnh giá → màn Voucher '
    'gắn dấu ❓ để soi lại, KHÔNG tự sửa';
create index if not exists idx_vouchers_customer on vouchers (customer_id);
create index if not exists idx_vouchers_code     on vouchers (code);
create index if not exists idx_vouchers_expires  on vouchers (expires_on);
-- Luật C7 "còn voucher hiệu lực thì tắt mọi mốc chăm chuẩn" tra bằng index này
create index if not exists idx_vouchers_con_han
    on vouchers (customer_id, expires_on) where status in ('con_han','chua_bao_ma');


-- ============================================================
-- C2 — LƯƠNG · THƯỞNG · ĐỐI SOÁT
--      (port từ mẫu Kallet: luong.php · luong-thuong.php · doi-soat.php)
--
-- Mẫu gắn bậc lương vào `positions`; bên ta vai trò (crm.roles) đóng đúng vai
-- đó nên bậc treo theo `role_id`, khỏi đẻ thêm một cây chức danh thứ hai.
--
-- BA LUẬT DỄ BỊ "SỬA CHO ĐÚNG" RỒI HỎNG — mẫu ghi rõ, chép lại đây:
--   1. Thưởng chăm sóc CHỒNG LÊN hoa hồng (cộng thêm, không thay thế). Người
--      dựng hay tưởng đang tính hai lần rồi bỏ đi một khoản.
--   2. Thưởng nóng có HAI KIỂU CHẠY SONG SONG và CỘNG DỒN: theo doanh thu
--      NGÀY và theo giá trị TỪNG ĐƠN. Không phải chọn một.
--   3. Đơn hoàn/huỷ SAU khi đã chốt lương thì KHÔNG sửa kỳ cũ — ghi một dòng
--      payroll_adjustments âm vào KỲ SAU (payrolls.frozen chặn sửa ngược).
-- ============================================================

-- Lương cứng: cấu hình theo VAI TRÒ, cho phép đè theo TỪNG NGƯỜI (thực tế
-- lương cứng hay lệch nhau trong cùng vai trò). NULL ở users = lấy của role.
alter table roles add column if not exists base_salary numeric(14,2) not null default 0;
alter table users add column if not exists base_salary numeric(14,2);
comment on column users.base_salary is
    'Lương cứng RIÊNG của người này. NULL = dùng roles.base_salary';

-- Ba trục phân loại đơn của mẫu (C5): lần mua · công sức · quảng cáo.
-- "Lần mua" đã có sẵn ở orders.order_type nên chỉ thêm 2 trục còn lại.
alter table orders add column if not exists effort_axis text
    check (effort_axis in ('cham_soc','tu_nhien'));
alter table orders add column if not exists ads_attributed boolean not null default false;
alter table orders add column if not exists payroll_period text;
alter table orders add column if not exists classified_manually boolean not null default false;
alter table orders add column if not exists classify_reason text;
alter table orders add column if not exists classified_by bigint references users(id) on delete set null;
alter table orders add column if not exists classified_at timestamptz;
comment on column orders.effort_axis is
    'Trục CÔNG SỨC (C5): cham_soc = đơn có công chăm sóc → xét thưởng chăm; '
    'tu_nhien = khách tự mua. NULL = máy chưa phân loại';
comment on column orders.ads_attributed is
    'Trục QUẢNG CÁO — quy theo last-touch (crm.lead_attributions). Đọc SONG '
    'SONG với doanh thu chứ KHÔNG cộng vào, tránh đếm tiền hai lần';
comment on column orders.payroll_period is
    'Kỳ lương của đơn, dạng YYYY-MM. Ghi CỨNG lúc đơn giao thành công để đơn '
    'không tự nhảy kỳ khi ngày giao bị sửa về sau';
comment on column orders.classified_manually is
    'Người đã sửa phân loại → máy THÔI tự đổi đơn này (giữ dấu vết ai/khi nào/'
    'vì sao ở 3 cột classify_*)';
create index if not exists idx_orders_ky_luong
    on orders (payroll_period, sale_owner_id) where payroll_period is not null;
create index if not exists idx_orders_cham_soc
    on orders (effort_axis) where effort_axis = 'cham_soc';

create table if not exists commission_tiers (
    id          bigint generated always as identity primary key,
    role_id     bigint not null references roles(id) on delete cascade,
    min_revenue numeric(14,2) not null,
    kind        text not null default 'phan_tram'
                check (kind in ('phan_tram','tien')),
    value       numeric(14,2) not null,
    sort_order  int not null default 0,
    created_at  timestamptz not null default now()
);
comment on table commission_tiers is
    'Bậc hoa hồng theo doanh thu kỳ. Áp bậc CAO NHẤT mà doanh thu chạm tới '
    '(không cộng dồn các bậc) — xem services/payroll_service.hoa_hong';
create index if not exists idx_commission_tiers_role on commission_tiers (role_id);

create table if not exists care_bonus_tiers (
    id          bigint generated always as identity primary key,
    role_id     bigint not null references roles(id) on delete cascade,
    min_revenue numeric(14,2) not null,
    kind        text not null default 'phan_tram'
                check (kind in ('phan_tram','tien')),
    value       numeric(14,2) not null,
    sort_order  int not null default 0,
    created_at  timestamptz not null default now()
);
comment on table care_bonus_tiers is
    'Bậc thưởng chăm sóc, xét theo giá trị TỪNG ĐƠN (không phải doanh thu kỳ). '
    'LUẬT 1: khoản này CỘNG THÊM vào hoa hồng, không thay thế';
create index if not exists idx_care_bonus_tiers_role on care_bonus_tiers (role_id);

create table if not exists hot_bonus_tiers (
    id          bigint generated always as identity primary key,
    role_id     bigint not null references roles(id) on delete cascade,
    basis       text not null check (basis in ('doanh_thu_ngay','gia_tri_don')),
    threshold   numeric(14,2) not null,
    kind        text not null default 'tien' check (kind in ('phan_tram','tien')),
    value       numeric(14,2) not null,
    sort_order  int not null default 0,
    created_at  timestamptz not null default now()
);
comment on column hot_bonus_tiers.basis is
    'LUẬT 2 — hai kiểu CHẠY SONG SONG và CỘNG DỒN: doanh_thu_ngay (tổng bán '
    'trong một ngày) và gia_tri_don (từng đơn lẻ). Không phải chọn một';
create index if not exists idx_hot_bonus_tiers_role on hot_bonus_tiers (role_id);

create table if not exists care_bonus_reviews (
    order_id    bigint primary key references orders(id) on delete cascade,
    status      text not null check (status in ('duyet','tu_choi')),
    amount      numeric(14,2) not null default 0,
    reason      text not null default '',
    reviewed_by bigint references users(id) on delete set null,
    reviewed_at timestamptz not null default now()
);
comment on table care_bonus_reviews is
    'Duyệt/bác thưởng chăm sóc từng đơn (màn Đối soát). `amount` là số tiền '
    'CHỐT LÚC DUYỆT — tính lại ở máy chủ, không tin số client gửi lên';
create index if not exists idx_care_bonus_reviews_tt on care_bonus_reviews (status);

create table if not exists user_goals (
    id         bigint generated always as identity primary key,
    user_id    bigint not null references users(id) on delete cascade,
    period     text not null,
    target     numeric(14,2) not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, period)
);
comment on table user_goals is
    'Mục tiêu thu nhập do CHÍNH nhân viên tự đặt (màn Thu nhập của tôi) — '
    'không phải KPI quản lý giao';

create table if not exists payrolls (
    id                bigint generated always as identity primary key,
    user_id           bigint not null references users(id) on delete cascade,
    period            text not null,
    base_salary       numeric(14,2) not null default 0,
    revenue_booked    numeric(14,2) not null default 0,
    revenue_collected numeric(14,2) not null default 0,
    commission        numeric(14,2) not null default 0,
    care_bonus        numeric(14,2) not null default 0,
    hot_bonus         numeric(14,2) not null default 0,
    adjustment        numeric(14,2) not null default 0,
    total             numeric(14,2) not null default 0,
    frozen            boolean not null default false,
    closed_at         timestamptz,
    closed_by         bigint references users(id) on delete set null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (user_id, period)
);
comment on column payrolls.revenue_booked is
    'Doanh thu LÊN ĐƠN (tổng giá trị đơn trong kỳ). Khác revenue_collected = '
    'ĐÃ THU (đơn giao thành công) — mọi con số bày ra màn phải ghi rõ là cái nào';
comment on column payrolls.frozen is
    'Đã chốt kỳ → KHOÁ. Đơn hoàn/huỷ phát sinh sau ghi vào kỳ SAU bằng một '
    'dòng payroll_adjustments âm (LUẬT 3), tuyệt đối không sửa ngược kỳ cũ';

create table if not exists payroll_adjustments (
    id         bigint generated always as identity primary key,
    user_id    bigint not null references users(id) on delete cascade,
    period     text not null,
    order_id   bigint references orders(id) on delete set null,
    amount     numeric(14,2) not null,
    reason     text not null default '',
    created_by bigint references users(id) on delete set null,
    created_at timestamptz not null default now()
);
comment on column payroll_adjustments.amount is
    'Cộng/TRỪ vào kỳ. Số ÂM = truy thu (đơn hoàn sau khi đã chốt lương kỳ trước)';
create index if not exists idx_payroll_adj on payroll_adjustments (user_id, period);
-- Mỗi đơn chỉ truy thu MỘT lần: worker chạy lại không nhân đôi khoản trừ.
create unique index if not exists uq_payroll_adj_don
    on payroll_adjustments (order_id) where order_id is not null;

create table if not exists leave_periods (
    id         bigint generated always as identity primary key,
    user_id    bigint not null references users(id) on delete cascade,
    stand_in_id bigint references users(id) on delete set null,
    from_date  date not null,
    to_date    date,
    created_by bigint references users(id) on delete set null,
    created_at timestamptz not null default now()
);
comment on table leave_periods is
    'Kỳ nghỉ của nhân viên + người trực thay. to_date NULL = nghỉ chưa hẹn ngày '
    'về (chia lead vẫn phải né người này)';
create index if not exists idx_leave_periods_user on leave_periods (user_id);


-- ============================================================
-- C3 — CHIẾN DỊCH 2 TẦNG & MẪU TIN
--      (port từ mẫu Kallet: chien-dich.php · mau-tin.php)
--
-- KHÔNG đẻ bảng `campaigns` mới: `reactivation_campaigns` + `reactivation_
-- members` (B10) đã đúng khái niệm, chỉ thiếu mấy cột của chiến dịch 2 tầng.
-- Hai bảng campaign song song là kiểu gì cũng có ngày đếm số lệch nhau.
--
-- VÌ SAO 2 TẦNG (mẫu ghi rõ, đừng gộp lại thành 1):
--   Máy gửi TẦNG 1 cho cả tệp — miễn phí, không tốn người. Chỉ khách nào
--   TRẢ LỜI mới sinh việc TẦNG 2 cho nhân viên. Gộp một tầng nghĩa là ném cả
--   tệp mấy chục nghìn khách vào bảng việc của vài người → quá tải, và nhân
--   viên bỏ luôn cả những khách thật sự quan tâm.
-- ============================================================
alter table reactivation_campaigns add column if not exists description text;
alter table reactivation_campaigns add column if not exists tier1_channel text
    not null default 'bot';
alter table reactivation_campaigns add column if not exists tier1_flow_id text;
alter table reactivation_campaigns add column if not exists template_id bigint;
alter table reactivation_campaigns add column if not exists batch_size int not null default 500;
alter table reactivation_campaigns add column if not exists batch_interval_days int not null default 7;
alter table reactivation_campaigns add column if not exists deadline date;
alter table reactivation_campaigns add column if not exists created_by bigint
    references users(id) on delete set null;
alter table reactivation_campaigns add column if not exists last_batch_at timestamptz;
comment on column reactivation_campaigns.batch_size is
    'Chia ĐỢT: mẫu chốt thử 500 ngẫu nhiên rồi mới 5.000/tuần. Bắn cả tệp một '
    'lượt là cách nhanh nhất để bị Meta khoá page';
comment on column reactivation_campaigns.tier1_flow_id is
    'Kịch bản Botcake gửi ở TẦNG 1. Rỗng = chiến dịch chỉ để gom tệp, máy '
    'không gửi gì';

alter table reactivation_members add column if not exists sent_at timestamptz;
alter table reactivation_members add column if not exists send_result text;
alter table reactivation_members add column if not exists responded_at timestamptz;
alter table reactivation_members add column if not exists task_id bigint
    references tasks(id) on delete set null;
comment on column reactivation_members.sent_at is
    'CHỈ đóng dấu khi GỬI THẬT. Chạy ở chế độ nháp (công tắc gửi tin TẮT) '
    'không được "tiêu" khách — bật gửi thật vẫn phải gửi đủ';
comment on column reactivation_members.task_id is
    'Việc TẦNG 2 sinh ra khi khách trả lời. NULL = chưa ai phải làm gì';
-- J5 — "1 khách không nằm 2 chiến dịch CÙNG LÚC". Cố ý KHÔNG unique trên
-- customer_id: chiến dịch đóng rồi thì khách phải được vào chiến dịch khác.
create unique index if not exists uq_reactivation_dang_cham
    on reactivation_members (customer_id)
    where status in ('pending','contacted','responded');
create index if not exists idx_reactivation_chua_gui
    on reactivation_members (campaign_id) where sent_at is null;

create table if not exists message_templates (
    id           bigint generated always as identity primary key,
    code         text not null unique,
    name         text not null default '',
    kind         text not null default 'tu_do'
                 check (kind in ('tu_do','meta_duyet')),
    meta_status  text not null default 'rong'
                 check (meta_status in ('gui_ngoai_cua','chi_trong_cua','rong')),
    variables    text not null default '',
    body         text not null default '',
    sent_count   int not null default 0,
    status       text not null default 'active'
                 check (status in ('active','inactive')),
    created_by   bigint references users(id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on column message_templates.kind is
    'tu_do = tin thường, CHỈ gửi được trong cửa 24h. meta_duyet = mẫu Meta đã '
    'duyệt, gửi được NGOÀI cửa. Gửi nhầm loại là bị Meta phạt page';
comment on column message_templates.variables is
    'Danh sách biến cho phép, cách nhau dấu phẩy (vd "ten_khach,ma_voucher"). '
    'Biến lạ trong body sẽ bị service chặn lúc lưu';


-- ============================================================
-- C4 — THƯ VIỆN KỊCH BẢN · KHO DATA · GIÁM SÁT (SOI TIN)
--      (port từ mẫu Kallet: kich-ban.php · kho-data.php · lich-su.php ·
--       includes/xac_minh.php)
--
-- ⚠️ HAI THỨ TÊN GIỐNG NHAU NHƯNG KHÁC HẲN — mẫu dặn "ĐỪNG GỘP":
--     📚 THƯ VIỆN kịch bản (bảng `sale_scripts` dưới đây) = kho câu chữ để
--        nhân viên CHÉP TAY. Mở màn này KHÔNG gửi gì cho ai.
--     🤖 GỬI kịch bản Botcake (message_templates + chiến dịch, C3) = máy BẮN
--        tin thật tới khách.
--   Gộp hai thứ này là có ngày ai đó bấm "xem câu mẫu" rồi tin bay tới khách.
--
-- VÒNG XÁC MINH CÔNG (soi tin):
--   * 1 CÔNG / khách / nhân viên / hành động / NGÀY — nhắn 10 tin vẫn 1 công.
--   * TIN NHẮN THẬT là bằng chứng: máy soi crm.messages thấy nhân viên nhắn
--     thì tự cộng công và đánh dấu đã xác minh.
--   * Tự khai mà quá hạn không soi thấy tin → tự BÁC, trưởng nhóm vớt tay.
--   * CỬA SỔ SOI ±1 NGÀY: nhân viên hay nhắn buổi sáng, tối mới bấm tick.
-- ============================================================
create table if not exists sale_scripts (
    id           bigint generated always as identity primary key,
    kind         text not null default 'sale' check (kind in ('sale','sau_ban')),
    situation    text not null default '',
    milestone    text,
    channel      text not null default 'nhan_tin'
                 check (channel in ('nhan_tin','goi_dien')),
    title        text not null default '',
    body         text not null default '',
    body_nodiacritic text not null default '',
    tags         text not null default '',
    use_count    int not null default 0,
    sort_order   int not null default 0,
    status       text not null default 'active'
                 check (status in ('active','inactive')),
    created_by   bigint references users(id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on table sale_scripts is
    'THƯ VIỆN câu chữ để nhân viên CHÉP TAY. Mở/tìm ở đây KHÔNG gửi gì cho '
    'khách — gửi thật là message_templates + chiến dịch (C3)';
comment on column sale_scripts.body_nodiacritic is
    'Bản BỎ DẤU của body, service tự sinh lúc lưu. Có cột này thì tìm "dau da '
    'day" ra được câu "đau dạ dày" mà không cần extension unaccent của Postgres';
comment on column sale_scripts.use_count is
    'Đếm lượt chép — dùng để soi kịch bản CHẾT (viết ra rồi không ai dùng)';
create index if not exists idx_sale_scripts_kind on sale_scripts (kind, status);
create index if not exists idx_sale_scripts_tim
    on sale_scripts using gin (to_tsvector('simple', body_nodiacritic));

create table if not exists script_suggest_rules (
    id         bigint generated always as identity primary key,
    keywords   text not null,
    script_id  bigint references sale_scripts(id) on delete cascade,
    status     text not null default 'active'
               check (status in ('active','inactive')),
    created_at timestamptz not null default now()
);
comment on table script_suggest_rules is
    'Gợi ý kịch bản theo TỪ KHOÁ trong tin khách — dò từ khoá thuần, CỐ Ý '
    'không dùng AI: gợi ý phải giải thích được "vì sao ra câu này"';

-- Nhật ký chia/thu hồi khách (mẫu: assignment_log)
create table if not exists assignment_logs (
    id           bigint generated always as identity primary key,
    customer_id  bigint not null references customers(id) on delete cascade,
    from_user_id bigint references users(id) on delete set null,
    to_user_id   bigint references users(id) on delete set null,
    action       text not null check (action in
                 ('chia','chia_deu','thu_hoi','chuyen_tay','tu_nhan',
                  'nghi_viec','chien_dich')),
    reason       text not null default '',
    by_machine   boolean not null default false,
    by_user      bigint references users(id) on delete set null,
    created_at   timestamptz not null default now()
);
comment on column assignment_logs.reason is
    'THU HỒI BẮT BUỘC có lý do (mẫu chốt) — mất khách là chuyện lớn với nhân '
    'viên, không được thu hồi im lặng';
create index if not exists idx_assignment_logs_kh on assignment_logs (customer_id);

create table if not exists recall_blocks (
    id          bigint generated always as identity primary key,
    customer_id bigint not null references customers(id) on delete cascade,
    user_id     bigint not null references users(id) on delete cascade,
    block_until date not null,
    reason      text not null default '',
    created_at  timestamptz not null default now()
);
comment on table recall_blocks is
    'Khách vừa bị thu hồi khỏi một người thì KHOÁ không chia lại cho chính '
    'người đó tới ngày block_until — tránh vòng lặp thu hồi/chia lại';
create index if not exists idx_recall_blocks on recall_blocks (customer_id, user_id);

create table if not exists export_logs (
    id         bigint generated always as identity primary key,
    user_id    bigint references users(id) on delete set null,
    scope      text not null default '',
    row_count  int not null default 0,
    filters    jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
comment on table export_logs is
    'Ai xuất dữ liệu gì, bao nhiêu dòng, lọc theo điều kiện nào. Xuất khách '
    'hàng ra Excel là hành vi cần truy vết được';

create table if not exists merge_logs (
    id                  bigint generated always as identity primary key,
    primary_customer_id bigint not null references customers(id) on delete cascade,
    merged_customer_id  bigint not null references customers(id) on delete cascade,
    snapshot            jsonb not null default '{}'::jsonb,
    undone              boolean not null default false,
    by_user             bigint references users(id) on delete set null,
    created_at          timestamptz not null default now()
);
comment on column merge_logs.snapshot is
    'Nguyên trạng hồ sơ phụ TRƯỚC khi gộp — có cái này mới TÁCH LẠI được. '
    'Gộp nhầm hai người thật mà không tách lại được là mất dữ liệu vĩnh viễn';

create table if not exists merge_ignored (
    id          bigint generated always as identity primary key,
    phone       text not null unique,
    reason      text not null default '',
    by_user     bigint references users(id) on delete set null,
    created_at  timestamptz not null default now()
);
comment on table merge_ignored is
    'Số điện thoại ĐÃ XÁC NHẬN không phải trùng (người nhà dùng chung số) — '
    'màn gộp trùng thôi hỏi lại';

-- Vòng xác minh công: thêm cột vào care_interactions (B9) thay vì bảng mới
alter table care_interactions add column if not exists action_kind text;
alter table care_interactions add column if not exists verify_source text
    not null default 'tu_khai'
    check (verify_source in ('may_tu_nhan','tu_khai','chat_ngay','may_tu_soi'));
alter table care_interactions add column if not exists verify_status text
    not null default 'tu_khai_chua_soi'
    check (verify_status in ('dang_xac_minh','da_xac_minh','tu_khai_chua_soi',
                             'bac_bo'));
alter table care_interactions add column if not exists verified_at timestamptz;
alter table care_interactions add column if not exists verified_by bigint
    references users(id) on delete set null;
alter table care_interactions add column if not exists verify_reason text;
alter table care_interactions add column if not exists action_at timestamptz;
comment on column care_interactions.action_kind is
    'nhan | goi | tang_voucher | xong — hành động được ghi công';
comment on column care_interactions.verify_source is
    'may_tu_nhan = máy chủ TỰ LÀM (gửi tin hộ/tạo voucher) → xác minh theo cấu '
    'trúc · tu_khai = người bấm nút khai, chờ soi · may_tu_soi = máy soi tin '
    'Pancake thấy nhắn thật → tự cộng';
comment on column care_interactions.action_at is
    'Mốc hành động THẬT (giờ VN). Khoá 1-công/ngày và cửa soi ±1 ngày đều tính '
    'trên cột này, KHÔNG dùng created_at (giờ ghi vào DB, có thể lệch)';
-- 1 CÔNG / khách / nhân viên / hành động / NGÀY — chặn ngay ở DB, không tin
-- vào việc client ẩn nút.
create unique index if not exists uq_care_cong_ngay
    on care_interactions (customer_id, user_id, action_kind,
                          ((action_at at time zone 'Asia/Ho_Chi_Minh')::date))
    where action_kind is not null and user_id is not null;
create index if not exists idx_care_verify on care_interactions (verify_status);


-- ============================================================
-- C5 — BỘ PHẬN SALE: THANG BÁM ĐUỔI + BẢNG VIỆC
--      (port từ mẫu Kallet: includes/sale_buoc.php · includes/board_rules.php
--       · trang-chu.php)
--
-- Ý TƯỞNG LÕI, khác hẳn pipeline 13 giai đoạn sẵn có:
--   Pipeline 13 giai đoạn = nhân viên TỰ KÉO thẻ. Thang bám đuổi = MÁY ĐỌC TIN
--   NHẮN THẬT rồi tự biết đã đi tới bước nào. Hai thứ SỐNG SONG SONG:
--     * `leads.stage_id`   — giai đoạn do người đặt (bán hàng tới đâu)
--     * `leads.sale_step`  — con trỏ do máy dò (đã nói những gì với khách)
--   Đừng gộp. Giai đoạn trả lời "khách ở đâu trong quy trình bán"; con trỏ trả
--   lời "câu tiếp theo cần nói là gì".
--
-- BỐN LUẬT CỦA THANG (mẫu đã trả giá để có, chép nguyên):
--   1. NGÀY BẬT THANG là chốt chặn quan trọng nhất. Không có nó, lượt dò đầu
--      đọc CẢ LỊCH SỬ → khách nhắn qua lại vài tháng nhảy thẳng bước cuối →
--      "hết thang" → rơi khỏi bảng việc. Cả bảng Sale trống trong một nốt nhạc.
--   2. Con trỏ CHỈ TIẾN, không bao giờ lùi.
--   3. Mỗi tin chỉ nhảy tối đa `cua_so` bước — một cụm chữ lạc không được đẩy
--      khách thẳng tới bước cuối rồi bị buông oan.
--   4. Khách đang chờ nhân viên trả lời thì con trỏ ĐỨNG YÊN — việc lúc đó là
--      ĐÁP KHÁCH, không phải đẩy bước tiếp.
-- ============================================================
create table if not exists sale_steps (
    id           bigint generated always as identity primary key,
    step_no      int not null unique,
    name         text not null default '',
    work         text not null default '',
    keywords_agent    text not null default '',
    keywords_customer text not null default '',
    status       text not null default 'active'
                 check (status in ('active','inactive')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on table sale_steps is
    'Thang bám đuổi Sale — sửa được ở màn Bảng việc, không phải sửa code';
comment on column sale_steps.keywords_agent is
    'Cụm chữ NHÂN VIÊN nói ⇒ coi như đã làm bước này. Cách nhau dấu phẩy, so '
    'khớp sau khi bỏ dấu cả hai phía. Ba từ máy tự hiểu: #anh (tin có ảnh) · '
    '#gia (tin có số tiền) · #ma (tin có mã giảm)';
comment on column sale_steps.keywords_customer is
    'Cụm chữ KHÁCH nói ⇒ NHẢY CÓC thẳng tới bước này. Khách kêu "đắt quá" lúc '
    'con trỏ mới 0 thì nhảy thẳng bước gửi mã giảm, khỏi bắt nhân viên bò qua '
    'mấy bước giữa trong khi khách đã nói toạc ra rồi. Trống = bước không nhảy '
    'cóc được';

-- Con trỏ bước + cột đặt tay, gắn trên LEAD (thực thể Sale của ta)
alter table leads add column if not exists sale_step int not null default 0;
alter table leads add column if not exists sale_step_at timestamptz;
alter table leads add column if not exists sale_step_day date;
alter table leads add column if not exists sale_step_count int not null default 0;
alter table leads add column if not exists replied_at timestamptz;
alter table leads add column if not exists board_column text;
alter table leads add column if not exists board_column_at timestamptz;
alter table leads add column if not exists board_column_by bigint
    references users(id) on delete set null;
comment on column leads.sale_step is
    'Con trỏ bước ĐÃ LÀM (0 = chưa bước nào). Việc cần làm là bước sale_step+1. '
    'CHỈ TIẾN — services/sale_service.dong_bo_con_tro lấy max()';
comment on column leads.sale_step_count is
    'Số bước đã nhích TRONG NGÀY sale_step_day — chặn trần bước/ngày để nhân '
    'viên không bắn 8 tin liền một lúc cho xong việc';
comment on column leads.replied_at is
    'Lần gần nhất khách TRẢ LỜI sau khi shop nhắn. Có dấu này = khách chịu nói '
    'chuyện ⇒ vào cột "Tiềm năng"';
comment on column leads.board_column is
    'Cột người ĐẶT TAY, đè lên cột máy suy ra. TỰ NHẢ khi khách nhắn mới sau '
    'board_column_at — "Từ chối đợt này" không được kẹt vĩnh viễn';
create index if not exists idx_leads_sale_step on leads (sale_step)
    where closed_at is null;
create index if not exists idx_leads_board_column on leads (board_column)
    where board_column is not null;


-- ============================================================
-- C7 — MÀN ĐƠN HÀNG (port `don-hang.php` của mẫu Kallet)
-- Mẫu đọc thẳng các cột này trên bảng orders; bên ta chúng NẰM TRONG
-- orders.pos_raw (nguyên văn đơn POS). Rút ra thành cột thật vì:
--   * pos_raw là jsonb bị TOAST — moi 5 khoá cho 53k đơn mỗi lần lọc/xuất là
--     đọc lại cả bảng ngoài dòng, chậm gấp mấy chục lần;
--   * ô tìm "mã đơn" và ô lọc "nhân viên POS" cần INDEX, jsonb->>'' không có.
-- Cột chỉ là BẢN SAO của pos_raw: mất thì backfill lại được (khối update dưới).
-- ============================================================
alter table orders add column if not exists pos_display_id  text;
alter table orders add column if not exists cod_amount      numeric(14,2);
alter table orders add column if not exists prepaid_amount  numeric(14,2);
alter table orders add column if not exists pos_ad_id       text;
alter table orders add column if not exists pos_seller_id   text;
alter table orders add column if not exists pos_seller_name text;
comment on column orders.pos_display_id is
    'MÃ ĐƠN NGƯỜI DÙNG THẤY bên POS (pos_raw->>''id''). KHÁC orders.pos_order_id '
    '(= system_id, khoá kỹ thuật): 1.535 đơn nhập từ hệ cũ có mã dạng chuỗi '
    '"C430270742.88" nên cột này là text, không ép số';
comment on column orders.cod_amount is
    'Tiền thu hộ khi giao (pos_raw->>''cod''). Chỉ để HIỂN THỊ/XUẤT — doanh thu '
    'vẫn tính bằng total_amount, đừng cộng hai cột này vào nhau';
comment on column orders.prepaid_amount is 'Khách trả trước (pos_raw->>''prepaid'')';
comment on column orders.pos_seller_name is
    'Tên nhân viên POS phụ trách đơn (pos_raw->''assigning_seller''->>''name''). '
    'KHÔNG PHẢI users.id bên ta — POS dùng UUID riêng, chưa có bảng nối. Màn Đơn '
    'hàng vì thế có HAI ô lọc nhân viên: CRM (sale_owner_id) và POS (cột này)';

-- Backfill: chỉ chạm đơn CHƯA rút (chạy lại file này bao nhiêu lần cũng được).
-- Ép số qua regexp vì POS trả tiền dạng chuỗi; gặp chuỗi lạ thì để NULL chứ
-- KHÔNG cho câu update vỡ giữa chừng.
update orders
   set pos_display_id  = pos_raw->>'id',
       cod_amount      = case when pos_raw->>'cod' ~ '^-?[0-9]+(\.[0-9]+)?$'
                              then (pos_raw->>'cod')::numeric end,
       prepaid_amount  = case when pos_raw->>'prepaid' ~ '^-?[0-9]+(\.[0-9]+)?$'
                              then (pos_raw->>'prepaid')::numeric end,
       pos_ad_id       = nullif(pos_raw->>'ad_id', ''),
       pos_seller_id   = nullif(pos_raw->'assigning_seller'->>'id', ''),
       pos_seller_name = nullif(pos_raw->'assigning_seller'->>'name', '')
 where pos_raw is not null and pos_display_id is null;

create index if not exists idx_orders_pos_display on orders (pos_display_id);
create index if not exists idx_orders_pos_seller  on orders (pos_seller_name);
-- Bảng đơn mặc định sắp theo NGÀY ĐẶT: đơn POS lấy pos_inserted_at, đơn CRM
-- lấy created_at — index theo đúng biểu thức đó mới ăn được.
create index if not exists idx_orders_ngay_dat
    on orders ((coalesce(pos_inserted_at, created_at)) desc);


-- ============================================================
-- C6 — QUY TRÌNH CSKH BA GIAI ĐOẠN + BẢNG VIỆC CSKH
--      (port từ mẫu Kallet: includes/cskh_quy_trinh.php bản chốt 02/08/2026
--       + nửa CSKH của includes/board_rules.php)
--
-- ĐỪNG NHẦM với màn "Chăm sóc C01-C09" (B9, bảng care_plans): cái đó là liệu
-- trình của MỘT đơn (onboarding, phiếu chăm ngày 4/10/15/20/25) và kết thúc
-- khi hết liệu trình. Phần này là VÒNG ĐỜI KHÁCH sau khi nhận hàng, chạy mãi
-- tới khi khách rời bảng:
--
--   GĐ1 · ngày 0 → trước mốc đầu   cảm ơn → khách im thì gọi → tặng voucher
--   GĐ2 · voucher còn hạn          nhắc 15 · 7 · 3 · 0 ngày TRƯỚC hết hạn
--   GĐ3 · từ D45, mỗi 15 ngày      mốc XEN KẼ có khuyến mãi → bám đuổi 3 ngày
--
-- Mọi con số đọc từ Cài đặt (nhóm "cskh"), KHÔNG chốt cứng trong bảng: thang
-- mốc dưới đây là bản MATERIALIZE của cấu hình, sinh lại bằng
-- scripts/seed_cskh.py hoặc nút "Dựng lại thang" ở màn Bảng việc CSKH.
-- ============================================================
create table if not exists care_milestones (
    id           bigint generated always as identity primary key,
    code         text not null unique,
    dept         text not null default 'cskh' check (dept in ('cskh', 'sale')),
    offset_days  int  not null,
    window_from  int  not null default 0,
    window_to    int  not null default 0,
    board_column text not null default '',
    promo        boolean not null default false,
    sender       text not null default 'nguoi' check (sender in ('nguoi', 'may')),
    active       boolean not null default true,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
comment on table care_milestones is
    'Thang mốc chăm — SINH TỪ 3 con số ở Cài đặt (mốc đầu · khoảng cách · ngày '
    'buông), không chép tay. Sửa cửa sổ ở đây là bảng việc đổi ngay';
comment on column care_milestones.window_from is
    'Cửa sổ mốc MỞ ở ngày này (kể từ ngày nhận hàng). Hai mốc liền nhau KHÔNG '
    'được chồng lấn, nếu không một khách đứng hai mốc cùng lúc';
comment on column care_milestones.board_column is
    'moc_45 · moc_60 … · moc_out = mốc BUÔNG (ngoài vòng chăm, chỉ đánh dấu '
    'khách rời bảng — đừng gắn nhãn "chưa chăm" cho nó)';
comment on column care_milestones.promo is
    'Mốc XEN KẼ có chương trình khuyến mãi → bám đuổi 3 ngày (gửi ưu đãi + gọi '
    'push) thay vì chăm thường';
comment on column care_milestones.sender is
    'nguoi = nhân viên làm · may = automation gửi. Mặc định NGƯỜI: máy chỉ lo '
    'cảm ơn + tặng voucher';

-- Đợt 1 (khối 1D): nhãn 📌 riêng cho từng mốc.
-- Trước đây mọi mốc trong cùng một cột đọc CHUNG một câu việc, nên ba mốc
-- 60·90·120 cùng gom vào cột "Đến kỳ mua lại" hiện y hệt nhau — nhân viên
-- không biết khách đang ở nấc nào. Có nhãn riêng thì mốc nào nói câu nấy;
-- để TRỐNG thì rơi về câu chung của cột (khai ở 1G/1H).
alter table care_milestones add column if not exists label text not null default '';
comment on column care_milestones.label is
    'Nhãn ngắn 📌 của MỐC, đè lên câu việc chung của cột. Trống = dùng câu cột';
create index if not exists idx_care_milestones_dept
    on care_milestones (dept, offset_days) where active;

-- Đợt khuyến mãi NHẬP TAY mỗi đợt (không lấy tự động từ Chiến dịch/Flash sale).
-- Không có đợt nào đang chạy thì mốc khuyến mãi tạm chăm như mốc thường —
-- KHÔNG bịa nội dung ưu đãi ra gửi khách.
create table if not exists cskh_promos (
    id         bigint generated always as identity primary key,
    name       text not null default '',
    content    text not null default '',
    start_on   date,
    end_on     date,
    active     boolean not null default false,
    created_by bigint references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
comment on table cskh_promos is
    'Đợt khuyến mãi cho mốc CSKH có cờ promo. Nhập tay từng đợt — mốc lấy nội '
    'dung từ đợt ĐANG CHẠY hôm nay';
create index if not exists idx_cskh_promos_chay
    on cskh_promos (start_on, end_on) where active;

-- Kết quả cuộc gọi GĐ1. Thiếu cột này thì máy không biết đẩy khách sang "tặng
-- voucher" (nghe máy) hay để lại chờ (không nghe).
-- 🔑 Nới care_interactions (B9) thay vì đẻ bảng care_actions như mẫu: cùng khái
--    niệm "một lần chạm khách", hai bảng là hai nguồn đá nhau lúc đếm công.
alter table care_interactions add column if not exists call_result text
    check (call_result is null
           or call_result in ('nghe', 'khong_nghe', 'hen_goi_lai'));
comment on column care_interactions.call_result is
    'C6/GĐ1: nghe = gọi được (đủ điều kiện tặng voucher) · khong_nghe · '
    'hen_goi_lai. Mỗi khách chỉ gọi 1 LẦN trong một đợt bám đuổi';

-- Cột người ĐẶT TAY trên bảng việc CSKH (đè lên cột máy suy ra).
-- TỰ NHẢ khi khách nhắn mới sau cskh_column_at — "Từ chối đợt này" không được
-- kẹt vĩnh viễn (xem cskh_repo.nha_cot_da_cu).
alter table customers add column if not exists cskh_column text;
alter table customers add column if not exists cskh_column_at timestamptz;
alter table customers add column if not exists cskh_column_by bigint
    references users(id) on delete set null;
create index if not exists idx_customers_cskh_column on customers (cskh_column)
    where cskh_column is not null;


-- ============================================================
-- ĐỢT 2 · MẪU CÂU NHẬN DIỆN (mẫu Kallet: bảng `phrase_patterns`)
-- ============================================================
-- Bốn danh sách mẫu câu mà máy dùng để ĐỌC tin nhân viên gõ. Trước Đợt 2 chúng
-- ghi cứng trong `services/tieng_viet.py`; ghi cứng thì mỗi lần shop nói kiểu
-- khác một chút là phải sửa mã và triển khai lại — trong khi đây đúng là thứ
-- người vận hành phải tự sửa được.
--
-- Hằng trong mã KHÔNG bị xoá đi: chúng thành bộ NỀN luôn có hiệu lực, bảng này
-- chỉ THÊM vào. Nhờ vậy bảng rỗng (chưa seed, hoặc admin lỡ xoá sạch) thì bộ dò
-- vẫn chạy đúng như trước, không im lặng ngừng nhận diện.
create table if not exists phrase_patterns (
    id          bigint generated always as identity primary key,
    kind        text not null check (kind in ('goi','chan','voucher','viet_tat')),
    pattern     text not null,
    replacement text,
    status      text not null default 'active'
                check (status in ('active','inactive')),
    created_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now()
);
comment on table phrase_patterns is
    'Mẫu câu admin khai thêm cho bộ nhận diện (Cài đặt → Kịch bản nhận diện). '
    'goi = tính là ĐÃ GỌI · chan = chạy TRƯỚC goi để loại câu "lát em gọi" · '
    'voucher = từ báo mã giảm · viet_tat = bung tắt thành chữ đầy đủ';
comment on column phrase_patterns.replacement is
    'Chỉ dùng cho kind=viet_tat: chữ đầy đủ. Ba loại kia để NULL';
-- Trùng mẫu trong CÙNG một loại là vô nghĩa (dò hai lần một thứ) — chặn ở DB
-- thay vì tin vào giao diện, vì còn cả đường API/seed ghi vào bảng này.
create unique index if not exists idx_phrase_patterns_unique
    on phrase_patterns (kind, lower(pattern));
create index if not exists idx_phrase_patterns_kind
    on phrase_patterns (kind, status);

-- ============================================================
-- ĐỢT 3 · LUỒNG TỰ ĐỘNG — KHUNG, CHƯA GỬI (mẫu Kallet: auto_flows)
-- ============================================================
-- 🔴 ĐỌC TRƯỚC KHI SỬA: bộ bảng này mới là KHUNG để khai và SOI luật. Engine
-- (`services/auto_flow.py`) CỐ Ý không có một lời gọi API gửi tin nào — muốn
-- gửi thật phải viết thêm mã mới, không phải gạt một công tắc. Ngoài ra còn
-- khoá cứng riêng `AUTO_FLOW_HARD_LOCK` trong .env chặn ở `cong_tac_gui_tin`.
create table if not exists auto_flows (
    id          bigint generated always as identity primary key,
    name        text not null default '',
    -- 3 kiểu kích hoạt: su_kien (POS/Pancake báo) · lech_ngay (N ngày kể từ
    -- một mốc neo) · truong_doi (một trường của khách đổi sang giá trị nào đó)
    kind        text not null default 'lech_ngay'
                check (kind in ('su_kien','lech_ngay','truong_doi')),
    status      text not null default 'inactive'
                check (status in ('active','inactive')),
    su_kien     text,
    so_ngay     integer,
    lech        integer not null default 0,
    moc_neo     text,
    truong      text,
    truong_gia_tri text,
    khop        text not null default 'all' check (khop in ('all','any')),
    dieu_kien   jsonb not null default '[]'::jsonb,
    -- Nội dung sẽ gửi. Để đây từ bây giờ để màn hình khai được đủ ý định, dù
    -- chưa đường nào đọc tới nó: khai luật mà không nói gửi gì thì lượt chạy
    -- khô chẳng kiểm chứng được điều gì có ý nghĩa.
    template_id bigint references message_templates(id) on delete set null,
    script_id   bigint references sale_scripts(id) on delete set null,
    gio_quet    integer,
    tao_viec    boolean not null default false,
    lan_chay_cuoi timestamptz,
    created_by  bigint references users(id) on delete set null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
comment on table auto_flows is
    'KHUNG luồng tự động (Đợt 3). Khai + soi luật được; GỬI thì CHƯA — engine '
    'không có mã gọi API, và còn khoá cứng AUTO_FLOW_HARD_LOCK chặn ở cửa gửi';
comment on column auto_flows.status is
    'active = luật được tính khi chạy khô. KHÔNG có nghĩa là được gửi tin';
comment on column auto_flows.dieu_kien is
    'Danh sách điều kiện lọc: [{"ma","phep","gia_tri"}] — catalog ở '
    'services/auto_flow.DIEU_KIEN';
comment on column auto_flows.tao_viec is
    'Sinh một việc cho nhân viên thay vì gửi tin. Đây là đường AN TOÀN: người '
    'vẫn là người bấm gửi, máy chỉ nhắc';
create index if not exists idx_auto_flows_chay on auto_flows (status, kind);

-- Nhật ký từng lượt CHẠY KHÔ. Có bảng này thì "luật của tôi trúng ai" trả lời
-- được bằng dữ liệu chứ không phải bằng niềm tin — và khi nào bật gửi thật thì
-- đã có sẵn chỗ đối chiếu trước/sau.
create table if not exists auto_flow_runs (
    id           bigint generated always as identity primary key,
    auto_flow_id bigint not null references auto_flows(id) on delete cascade,
    -- 'kho' là giá trị DUY NHẤT hiện có. 'that' để sẵn cho ngày bật gửi thật;
    -- CHECK giữ cả hai để lúc đó không phải migrate, nhưng không mã nào ghi
    -- 'that' cả — xem `auto_flow.chay_kho()`.
    che_do       text not null default 'kho' check (che_do in ('kho','that')),
    so_trung     integer not null default 0,
    so_bo_qua    integer not null default 0,
    chi_tiet     jsonb not null default '[]'::jsonb,
    boi          bigint references users(id) on delete set null,
    created_at   timestamptz not null default now()
);
comment on table auto_flow_runs is
    'Nhật ký lượt chạy KHÔ của luồng tự động: luật trúng bao nhiêu khách và vì '
    'sao. Không tin nào được gửi trong bất kỳ lượt nào ghi ở đây';
comment on column auto_flow_runs.chi_tiet is
    'Mẫu vài chục khách đầu kèm lý do trúng — đủ để soi luật, không lưu cả tệp';
create index if not exists idx_auto_flow_runs on auto_flow_runs
    (auto_flow_id, created_at desc);

-- Luồng đã sinh VIỆC cho khách nào. Bảng nay là thứ giữ cho worker chạy được
-- nhiều lượt một ngày mà không đẻ ra một núi việc trùng: khoá duy nhất theo
-- (luồng, khách, NGÀY) nên chạy 10 lượt trong ngày vẫn đúng 1 việc.
create table if not exists auto_flow_tasks (
    id           bigint generated always as identity primary key,
    auto_flow_id bigint not null references auto_flows(id) on delete cascade,
    customer_id  bigint not null references customers(id) on delete cascade,
    task_id      bigint references tasks(id) on delete set null,
    ngay         date not null default (now() at time zone 'Asia/Ho_Chi_Minh')::date,
    created_at   timestamptz not null default now()
);
comment on table auto_flow_tasks is
    'Luong tu dong da sinh viec cho ai. Dung de CHONG TRUNG, va de tra loi '
    '"viec nay o dau ra" khi nhan vien hoi';
comment on column auto_flow_tasks.ngay is
    'Ngay theo GIO VN (UTC+7), khong phai UTC — worker chay luc 01:00 VN van '
    'phai tinh la hom nay chu khong phai hom qua';
create unique index if not exists idx_auto_flow_tasks_ngay
    on auto_flow_tasks (auto_flow_id, customer_id, ngay);
create index if not exists idx_auto_flow_tasks_kh
    on auto_flow_tasks (customer_id, created_at desc);

-- Việc do luồng tự động sinh trỏ ngược về `auto_flows` để thẻ việc trả lời được
-- câu "việc này ở đâu ra". CHECK cũ chưa biết giá trị đó nên phải nới ra — nới
-- bằng cách DROP rồi ADD lại ĐỦ danh sách (không thêm CHECK thứ hai: hai ràng
-- buộc trên cùng một cột thì phải thoả CẢ HAI, và cái cũ sẽ chặn giá trị mới).
alter table tasks drop constraint if exists tasks_related_type_check;
alter table tasks add  constraint tasks_related_type_check
    check (related_type in ('lead','order','care_plan_step',
                            'customer_treatment','repurchase_opportunity',
                            'auto_flows'));

-- ============================================================
-- TRIGGER updated_at cho mọi bảng CÓ CỘT updated_at trong schema crm
-- (lọc theo nspname='crm' nên không bao giờ chạm bảng của bot/watcher)
-- ============================================================
do $$
declare
    t text;
begin
    for t in
        select c.relname
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid
        where n.nspname = 'crm'
          and c.relkind = 'r'
          and a.attname = 'updated_at'
          and not a.attisdropped
    loop
        execute format('drop trigger if exists trg_%I_updated on crm.%I', t, t);
        execute format(
            'create trigger trg_%I_updated before update on crm.%I '
            'for each row execute function crm.set_updated_at()', t, t);
    end loop;
end $$;

commit;

-- ============================================================
-- CÁC CỘT CỐ Ý ĐỂ TEXT TỰ DO (danh mục mở, KHÔNG đặt CHECK)
--   products.product_type · tags.type · tasks.task_type
--   safety_screenings.screening_type · treatment_rules.rule_type
--   funnel_events.event_type · ai_recommendations.recommendation_type
--   care_plan_steps.result_code · symptoms.group_name · leads.source
-- Đây là các bộ mã sẽ nở ra theo vận hành, khoá cứng bằng CHECK chỉ tổ vướng.
--
-- NHÓM D — CHƯA ĐỘNG, quyết định sau khi có dữ liệu thật:
--   * partition theo tháng cho messages / funnel_events / call_transcripts
--     (làm được về sau, nhưng phải dừng ghi một lúc để chuyển bảng)
--   * chính sách lưu trữ ghi âm + bóc băng: thời hạn xoá calls.recording_url
--   * ai được xem call_transcripts — dữ liệu nhạy cảm, hiện CHƯA có phân quyền
--     ở tầng DB (không bật row level security), phần mềm phải tự chặn
-- ============================================================
