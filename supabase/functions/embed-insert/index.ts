// Supabase Edge Function: nhận TEXT -> tự gọi OpenAI tạo embedding -> ghi vào DB.
//
// Nhờ hàm này, phía Python (hoặc bất kỳ client nào) KHÔNG cần gọi OpenAI khi
// nhập dữ liệu nữa — chỉ gửi nội dung, Supabase lo phần embedding + insert.
// Chạy ĐỒNG BỘ: trả về ngay dòng đã ghi (kèm embedding), tìm kiếm được luôn.
//
// Deploy:
//   npx supabase secrets set OPENAI_API_KEY=sk-proj-...
//   npx supabase functions deploy embed-insert
//
// Body JSON:
//   { "loai": "hoi_thoai_mau", "cau_hoi": "...", "cau_tra_loi": "...", "nguon": "..." }
//   { "loai": "kich_ban", "noi_dung": "...", "ten_kich_ban": "...", "buoc": 1,
//     "dieu_kien": "...", "buoc_tiep": 2 }

import { createClient } from "jsr:@supabase/supabase-js@2";

const EMBEDDING_MODEL = "text-embedding-3-small";
const EMBEDDING_DIM = 1536; // phải khớp cột vector(1536) trong DB

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Gọi OpenAI lấy vector cho 1 đoạn text. */
async function embed(text: string): Promise<number[]> {
  const key = Deno.env.get("OPENAI_API_KEY");
  if (!key) throw new Error("Chưa đặt secret OPENAI_API_KEY cho Edge Function");

  const resp = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: EMBEDDING_MODEL,
      input: text.replace(/\n/g, " ").trim(),
      dimensions: EMBEDDING_DIM,
    }),
  });

  if (!resp.ok) {
    throw new Error(`OpenAI lỗi ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const data = await resp.json();
  return data.data[0].embedding as number[];
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "Chỉ nhận POST" }, 405);

  try {
    const body = await req.json();
    const loai = body.loai ?? "hoi_thoai_mau";

    // Dùng service role key (Supabase tự cấp cho Edge Function) để ghi bảng.
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    if (loai === "kich_ban") {
      const noiDung = (body.noi_dung ?? "").trim();
      if (!noiDung) return json({ error: "Thiếu noi_dung" }, 400);
      if (!body.ten_kich_ban) return json({ error: "Thiếu ten_kich_ban" }, 400);
      if (body.buoc === undefined || body.buoc === null) {
        return json({ error: "Thiếu buoc" }, 400);
      }

      const embedding = await embed(noiDung); // <- embed chính nội dung bước
      const { data, error } = await supabase
        .from("kich_ban")
        .insert({
          ten_kich_ban: body.ten_kich_ban,
          buoc: body.buoc,
          noi_dung: noiDung,
          dieu_kien: body.dieu_kien ?? null,
          buoc_tiep: body.buoc_tiep ?? null,
          embedding,                    // supabase-js tự chuyển mảng -> vector
          meta: body.meta ?? {},
        })
        .select("id,ten_kich_ban,buoc,noi_dung")
        .single();

      if (error) return json({ error: error.message }, 400);
      return json({ ok: true, row: data, embedded: noiDung, dim: EMBEDDING_DIM });
    }

    // Mặc định: hoi_thoai_mau
    const cauHoi = (body.cau_hoi ?? "").trim();
    const cauTraLoi = (body.cau_tra_loi ?? "").trim();
    if (!cauHoi) return json({ error: "Thiếu cau_hoi" }, 400);
    if (!cauTraLoi) return json({ error: "Thiếu cau_tra_loi" }, 400);

    // Embed CÂU HỎI để khớp với tin nhắn khách gửi tới.
    const embedText = (body.embed_text ?? cauHoi).trim();
    const embedding = await embed(embedText);

    const { data, error } = await supabase
      .from("hoi_thoai_mau")
      .insert({
        cau_hoi: cauHoi,
        cau_tra_loi: cauTraLoi,
        nguon: body.nguon ?? null,
        embedding,
        meta: { ...(body.meta ?? {}), embed_text: embedText },
      })
      .select("id,cau_hoi,cau_tra_loi,nguon")
      .single();

    if (error) return json({ error: error.message }, 400);
    return json({ ok: true, row: data, embedded: embedText, dim: EMBEDDING_DIM });
  } catch (e) {
    return json({ error: String(e instanceof Error ? e.message : e) }, 500);
  }
});
