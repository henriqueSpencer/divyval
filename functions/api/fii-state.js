import { json } from "../_lib/http.js";
import { sel } from "../_lib/db.js";

// GET /api/fii-state — estado do usuário p/ FIIs numa chamada só (carregado ao entrar na 1ª tela de FII):
// { prem:{ticker:{dpu,g,N,ke,pvpIn,gvp,pvp,modelo}}, watch:[tickers], cart:{ticker:{qtd,pm}}, hist:{ticker:[...]} }
// Só overrides são gravados (null = segue o padrão/auto), então a resposta vem enxuta.
export async function onRequestGet(context) {
  const env = context.env;
  const [prem, watch, cart, hist] = await Promise.all([
    sel(env, "fii_premissa?select=ticker,dpu,g,n,ke,pvp_in,gvp,pvp,modelo"),
    sel(env, "fii_watchlist?select=ticker"),
    sel(env, "fii_carteira?select=ticker,quantidade,preco_medio"),
    sel(env, "fii_premissa_hist?select=ticker,date,prem,fair,price,modelo&order=id.desc&limit=2000"),
  ]);
  const P = {};
  for (const r of prem) {
    const o = {};
    if (r.dpu != null) o.dpu = +r.dpu;
    if (r.g != null) o.g = +r.g;
    if (r.n != null) o.N = +r.n;
    if (r.ke != null) o.ke = +r.ke;
    if (r.pvp_in != null) o.pvpIn = +r.pvp_in;
    if (r.gvp != null) o.gvp = +r.gvp;
    if (r.pvp != null) o.pvp = +r.pvp;
    if (r.modelo) o.modelo = r.modelo;
    if (Object.keys(o).length) P[r.ticker] = o;
  }
  const H = {};
  for (const h of hist) {
    (H[h.ticker] ||= []);
    if (H[h.ticker].length < 20)
      H[h.ticker].push({ date: h.date, prem: h.prem || {}, fair: h.fair == null ? null : +h.fair, price: h.price == null ? null : +h.price, modelo: h.modelo });
  }
  const C = {};
  for (const r of cart) C[r.ticker] = { qtd: +r.quantidade, pm: +r.preco_medio };
  return json({ prem: P, watch: watch.map((w) => w.ticker), cart: C, hist: H });
}
