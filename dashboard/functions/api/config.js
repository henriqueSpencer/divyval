import { json } from "../_lib/http.js";
import { sel, upsert } from "../_lib/db.js";

// (chave da API, chave no banco, default) — porta de CFG_KEYS.
// `ke` é sempre o nominal efetivo (o app inteiro lê só ele). Os campos abaixo guardam como o
// usuário chegou nele: digitado direto (ke_mode=0) ou composto de IPCA + taxa real da NTN-B
// (+ prêmio de risco) na tela de Configurações (ke_mode=1).
const CFG = [
  ["ke", "ke_global", 0.14],
  ["roet", "roet_global", 0.12],
  ["payoutt", "payoutt_global", 0.6],
  ["fade", "fade_global", 10],
  ["ipca", "ipca_global", 0.045],
  ["ntnb", "ntnb_global", 0.072],
  ["premio", "premio_global", 0],
];

export async function onRequestGet(context) {
  const rows = await sel(context.env, "config?select=k,v");
  const m = Object.fromEntries(rows.map((r) => [r.k, r.v]));
  const out = {};
  for (const [k, dbk, d] of CFG) out[k] = m[dbk] ?? d;
  out.ke_mode = (m.ke_mode_global ?? 0) ? "real" : "nom"; // numérico no banco, string na API
  return json(out);
}

export async function onRequestPost(context) {
  const p = await context.request.json();
  const rows = [];
  for (const [k, dbk] of CFG)
    if (p[k] != null) rows.push({ k: dbk, v: parseFloat(p[k]) });
  if (p.ke_mode != null) rows.push({ k: "ke_mode_global", v: p.ke_mode === "real" ? 1 : 0 });
  if (rows.length) await upsert(context.env, "config", rows);
  return json({ ok: true });
}
