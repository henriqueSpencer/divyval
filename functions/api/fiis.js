import { json } from "../_lib/http.js";
import { getFiiPrices, getAllFiiDividends, FII_UNIVERSE, FII_VP, SEG_DY } from "../_lib/fii.js";

// GET /api/fiis — screener de FIIs: universo curado + preço ao vivo (brapi) + DPU 12m REAL (Yahoo, em
// lote, cache 6h) + VP/cota (CVM mensal). O detalhe (/api/fii/{tk}) usa as MESMAS fontes → mesmos números.
// Sem Yahoo p/ um fundo, cai no DPU estimado (DY típico do segmento), sinalizado em `dpu_src`.
export async function onRequestGet(context) {
  const tickers = Object.keys(FII_UNIVERSE);
  const [prices, divs] = await Promise.all([getFiiPrices(context), getAllFiiDividends(tickers, context)]);
  const fiis = tickers.map((ticker) => {
    const [name, segment] = FII_UNIVERSE[ticker];
    const price = prices[ticker] ?? null;
    const segDy = SEG_DY[segment] ?? 0.09;
    const real = divs[ticker];
    const vp = FII_VP[ticker];
    return {
      ticker, name, segment, price,
      dpu12m: real ? real.dpu12m : (price != null ? Math.round(price * segDy * 1e4) / 1e4 : null),
      dpu_src: real ? "yahoo" : "estimado",
      n12: real ? real.n12 : null,
      seg_dy: segDy,
      vp_cota: vp ? vp.vp : null,     // valor patrimonial da cota (CVM)
      vp_ref: vp ? vp.ref : null,     // mês de referência do informe (aaaa-mm)
    };
  });
  return json({ fiis, count: fiis.length });
}
