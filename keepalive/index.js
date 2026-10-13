// Mantém o Supabase do DIVYVAL fora da PAUSA AUTOMÁTICA do free tier (7 dias sem atividade no banco).
// O app só toca o banco quando o usuário abre; uma semana sem uso já dispara o aviso de pausa.
//
// O cron chama /api/config no app em produção → a Pages Function faz um SELECT na tabela `config`
// via PostgREST → conta como atividade. De brinde, isso é um health check da cadeia inteira
// (Pages Function + Supabase): se o app quebrar, o cron passa a falhar e aparece no log.
//
// Secret necessário: APP_PASSWORD (a senha do app; o middleware aceita Basic como fallback).
const TARGET = "https://divyval.pages.dev/api/config";

async function ping(env) {
  const auth = "Basic " + btoa(":" + (env.APP_PASSWORD || ""));
  const r = await fetch(TARGET, { headers: { Authorization: auth } });
  const body = await r.text();
  const ok = r.ok && body.includes('"ke"');   // confirma que veio config de verdade, não um 401/HTML
  console.log(`keepalive ${new Date().toISOString()} status=${r.status} ok=${ok} bytes=${body.length}`);
  if (!ok) throw new Error(`keepalive falhou: status=${r.status}`);
  return { status: r.status, bytes: body.length };
}

export default {
  // gatilho do cron
  async scheduled(event, env, ctx) {
    ctx.waitUntil(ping(env));
  },
  // gatilho manual p/ conferir sem esperar o cron: ?k=<APP_PASSWORD>. Sem a chave → 404
  // (não é endpoint público; não devolve nenhum dado seu, só status).
  async fetch(request, env) {
    const k = new URL(request.url).searchParams.get("k");
    if (!k || k !== env.APP_PASSWORD) return new Response("not found", { status: 404 });
    try {
      const out = await ping(env);
      return Response.json({ ok: true, ...out });
    } catch (e) {
      return Response.json({ ok: false, error: String(e) }, { status: 502 });
    }
  },
};
