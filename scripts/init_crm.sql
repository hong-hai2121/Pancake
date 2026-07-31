-- ============================================================
-- CRM TIÊU HÓA — 60 bảng
--   56 bảng theo DANH-SACH-BANG-VA-QUAN-HE.md
--   + handovers     (FR-090/091 · màn 24-25 · API HANDOVER-001…006)
--   + audit_logs    (FR-180    · màn 77    · API AUDIT-001/002)
--   + user_sessions (A2 — docs/A2-DANG-NHAP.md mục 2.2)
--   + ref_codes     (danh mục dùng chung — màn 72 · BRD mục 14)
-- Bốn bảng cuối không có trong ERD nhưng đặc tả bắt buộc.
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
    task_id     bigint references tasks(id) on delete set null,
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
