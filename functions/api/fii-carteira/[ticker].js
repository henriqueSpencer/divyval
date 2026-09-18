import { json } from "../../_lib/http.js";
import { upsert, del } from "../../_lib/db.js";

// POST /api/fii-carteira/{ticker} — cria/atualiza a posição {quantidade, preco_medio} (upsert por ticker).
export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  const body = await context.request.json().catch(() => ({}));
  const quantidade = Number(body.quantidade), preco_medio = Number(body.preco_medio);
  if (!isFinite(quantidade) || !isFinite(preco_medio) || quantidade <= 0 || preco_medio < 0)
    return json({ error: "quantidade > 0 e preco_medio >= 0 são obrigatórios" }, 400);
  await upsert(context.env, "fii_carteira", [{ ticker: tk, quantidade, preco_medio, updated_at: new Date().toISOString() }]);
  return json({ ok: true });
}
// DELETE /api/fii-carteira/{ticker} — remove a posição.
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await del(context.env, "fii_carteira", `ticker=eq.${tk}`);
  return json({ ok: true });
}
