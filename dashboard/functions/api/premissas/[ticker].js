import { json } from "../../_lib/http.js";
import { sel, insert, upsert } from "../../_lib/db.js";

// Porta de PREM_COLS (app.py). As 4 últimas são flags "usar padrão global" (int 0/1).
const COLS = [
  "lpa", "roe_i", "payout_i", "roe_t", "payout_t", "fade", "ke",
  "growth_mode", "g_i", "g_t", "fut_pe", "mos",
  "ke_default", "roet_default", "payoutt_default", "fade_default",
];
const FLAGS = new Set(["ke_default", "roet_default", "payoutt_default", "fade_default"]);

export async function onRequestGet(context) {
  const tk = context.params.ticker.toUpperCase();
  const cols = COLS.join(",");
  const cur = await sel(context.env, `premissa_atual?ticker=eq.${tk}&select=${cols},updated_at`);
  const hist = await sel(
    context.env,
    `premissa_hist?ticker=eq.${tk}&select=date,${cols}&order=id.desc&limit=40`
  );
  return json({ atual: cur[0] || null, historico: hist });
}

export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  const p = await context.request.json();
  const row = {};
  for (const c of COLS)
    row[c] = FLAGS.has(c) ? (p[c] == null ? 1 : p[c] ? 1 : 0) : p[c] ?? null;
  // histórico (sempre insere) + atual (upsert por ticker)
  await insert(context.env, "premissa_hist", [{ ticker: tk, date: p.date ?? null, ...row }]);
  await upsert(context.env, "premissa_atual", [{ ticker: tk, ...row, updated_at: p.date ?? null }]);
  return json({ ok: true });
}
