import { json } from "../../_lib/http.js";
import { upsert, del } from "../../_lib/db.js";

// POST /api/carteira/{ticker} — cria/atualiza uma posição {quantidade, preco_medio}.
// Upsert por PK (ticker): reenviar sobrescreve a quantidade e o preço médio.
export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  const body = await context.request.json().catch(() => ({}));
  const quantidade = Number(body.quantidade);
  const preco_medio = Number(body.preco_medio);
  if (!isFinite(quantidade) || !isFinite(preco_medio) || quantidade <= 0 || preco_medio < 0)
    return json({ error: "quantidade > 0 e preco_medio >= 0 são obrigatórios" }, 400);
  await upsert(context.env, "carteira", [
    { ticker: tk, quantidade, preco_medio, updated_at: new Date().toISOString() },
  ]);
  return json({ ok: true });
}

// DELETE /api/carteira/{ticker} — remove a posição da carteira.
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await del(context.env, "carteira", `ticker=eq.${tk}`);
  return json({ ok: true });
}
