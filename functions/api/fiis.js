import { json } from "../_lib/http.js";
import { getFiiPrices, getAllFiiDividends, FII_UNIVERSE, FII_VP, SEG_DY } from "../_lib/fii.js";

// GET /api/fiis — screener de FIIs: universo completo (brapi ∩ CVM, gerado em fii_data.js) + preço ao vivo
// (brapi) + VP/cota (CVM mensal) + DPU 12m real SÓ do que já está em cache (responde rápido com ~330 fundos).
// O DPU dos demais o front busca progressivamente em /api/fii-dpu (mesmo cache → mesmos números no detalhe).
// Sem DPU real, vai o estimado (DY típico do segmento), sinalizado em `dpu_src`.
export async function onRequestGet(context) {
  const tickers = Object.keys(FII_UNIVERSE);
  const [prices, divs] = await Promise.all([getFiiPrices(context), getAllFiiDividends(tickers, context, true)]);
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
      vp_cota: vp ? vp.vp : null,
      vp_ref: vp ? vp.ref : null,
    };
  }).filter((f) => f.price != null);   // sem cotação não entra no screener
  return json({ fiis, count: fiis.length });
}
