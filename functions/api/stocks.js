import { json } from "../_lib/http.js";
import { buildStocks, sel, insert, del } from "../_lib/db.js";
import { getPrices, getMissingPrices } from "../_lib/quotes.js";

// GET /api/stocks — lista do screener (fundamentos + premissas + preço ao vivo).
export async function onRequestGet(context) {
  const prices = await getPrices(context).catch(() => ({}));
  const list = await buildStocks(context.env, prices);
  // Fallback Yahoo p/ ilíquidas ausentes da brapi (USIM6, CGAS3…): preenche o que o Yahoo tiver.
  const faltam = list.filter((s) => s.price == null).map((s) => s.ticker);
  if (faltam.length) {
    const yp = await getMissingPrices(faltam, context).catch(() => ({}));
    for (const s of list)
      if (s.price == null && yp[s.ticker] != null) {
        s.price = yp[s.ticker];
        s.fonte_preco = "yahoo";
      }
  }
  return json(list);
}

// POST /api/stocks — adiciona uma ação (porta de adicionar_acao).
export async function onRequestPost(context) {
  const s = await context.request.json();
  const tk = (s.ticker || "").toUpperCase();
  if (!tk || !s.nome)
    return json({ ok: false, erro: "ticker e nome obrigatórios" }, 400);
  const existe = await sel(context.env, `stocks?ticker=eq.${tk}&select=ticker`);
  if (existe.length) return json({ ok: false, erro: "ticker já cadastrado" }, 409);
  await insert(context.env, "stocks", [
    {
      ticker: tk, nome: s.nome, cd_cvm: null,
      setor: s.setor || "", subsetor: s.subsetor || "", segmento: s.segmento || "",
      perfil: s.perfil || "", tamanho: s.tamanho || "", gov: s.gov || "", ctrl: s.ctrl || "",
      modelo: s.modelo || "DDM · 2 est.",
      tags: JSON.stringify(s.tags || []),
      monitored: s.monitored ? 1 : 0,
      lpa: s.lpa ?? null, payout: s.payout ?? null, roe_i: s.roe_i ?? 0.15,
      user: 1,
    },
  ]);
  await del(context.env, "removed", `ticker=eq.${tk}`); // readicionar limpa o veto
  return json({ ok: true });
}
