import { json } from "../_lib/http.js";
import { sel, upsert } from "../_lib/db.js";

// (chave da API, chave no banco, default) — porta de CFG_KEYS.
const CFG = [
  ["ke", "ke_global", 0.14],
  ["roet", "roet_global", 0.12],
  ["payoutt", "payoutt_global", 0.6],
  ["fade", "fade_global", 10],
];

export async function onRequestGet(context) {
  const rows = await sel(context.env, "config?select=k,v");
  const m = Object.fromEntries(rows.map((r) => [r.k, r.v]));
  const out = {};
  for (const [k, dbk, d] of CFG) out[k] = m[dbk] ?? d;
  return json(out);
}

export async function onRequestPost(context) {
  const p = await context.request.json();
  const rows = [];
  for (const [k, dbk] of CFG)
    if (p[k] != null) rows.push({ k: dbk, v: parseFloat(p[k]) });
  if (rows.length) await upsert(context.env, "config", rows);
  return json({ ok: true });
}
