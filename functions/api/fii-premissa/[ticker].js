import { json } from "../../_lib/http.js";
import { upsert, insert, del } from "../../_lib/db.js";

const num = (v) => (v == null || v === "" || !isFinite(+v) ? null : +v);

// POST /api/fii-premissa/{ticker} — grava os OVERRIDES do fundo (null = volta ao padrão/auto) e um
// snapshot no histórico {date, prem, fair, price, modelo}. Body: {prem:{...}, fair, price, modelo, date}.
export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  const b = await context.request.json().catch(() => ({}));
  const p = b.prem || {};
  const modelo = p.modelo === "dy" || p.modelo === "r1" ? p.modelo : null;
  await upsert(context.env, "fii_premissa", [{
    ticker: tk, dpu: num(p.dpu), g: num(p.g), n: num(p.N), ke: num(p.ke), pvp_in: num(p.pvpIn),
    gvp: num(p.gvp), pvp: num(p.pvp), modelo, updated_at: new Date().toISOString(),
  }]);
  await insert(context.env, "fii_premissa_hist", [{
    ticker: tk, date: String(b.date || new Date().toLocaleString("pt-BR")), prem: p,
    fair: num(b.fair), price: num(b.price), modelo: b.modelo || modelo,
  }]);
  return json({ ok: true });
}

// DELETE /api/fii-premissa/{ticker} — apaga os overrides (o fundo volta 100% ao padrão/auto).
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await del(context.env, "fii_premissa", `ticker=eq.${tk}`);
  return json({ ok: true });
}
