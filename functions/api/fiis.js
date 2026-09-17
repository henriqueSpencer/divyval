import { json } from "../_lib/http.js";
import { getFiiPrices, FII_UNIVERSE, SEG_DY } from "../_lib/fii.js";

// GET /api/fiis — screener de FIIs: universo curado + preço ao vivo (brapi) + DPU/DY ESTIMADO
// pelo DY típico do segmento (rótulo "estimado"). O DPU/DY REAL vem do Yahoo na tela de detalhe
// (/api/fii/{ticker}); aqui NÃO chamamos o Yahoo (evita 40 requests/rate-limit por carga).
export async function onRequestGet(context) {
  const prices = await getFiiPrices(context);
  const fiis = [];
  for (const [ticker, [name, segment]] of Object.entries(FII_UNIVERSE)) {
    const price = prices[ticker] ?? null;
    const segDy = SEG_DY[segment] ?? 0.09;
    // estimativa consistente com o preço ao vivo (rotulada no front como "estimado")
    const dpuEst = price != null ? Math.round(price * segDy * 1e4) / 1e4 : null;
    fiis.push({
      ticker,
      name,
      segment,
      price,
      dpu_est: dpuEst, // DPU anual estimado (preço × DY típico do segmento)
      seg_dy: segDy, // DY típico usado na estimativa
    });
  }
  return json({ fiis, count: fiis.length });
}
