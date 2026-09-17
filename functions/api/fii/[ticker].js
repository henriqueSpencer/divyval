import { json } from "../../_lib/http.js";
import { getFiiDividends, getFiiPrices, FII_UNIVERSE, SEG_DY } from "../../_lib/fii.js";

// GET /api/fii/{ticker} — detalhe de um FII: DPU 12m REAL + série de proventos (Yahoo) + preço.
// Se o Yahoo não responder (429 local etc.), devolve dpu real null e uma estimativa por segmento,
// sempre sinalizando a origem (`source`: "yahoo" | "estimado").
export async function onRequestGet(context) {
  const ticker = (context.params.ticker || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const meta = FII_UNIVERSE[ticker];
  const [prices, div] = await Promise.all([
    getFiiPrices(context),
    getFiiDividends(ticker, context),
  ]);
  const price = div?.price ?? prices[ticker] ?? null;
  const segment = meta ? meta[1] : null;
  const segDy = SEG_DY[segment] ?? 0.09;

  let dpu12m = null,
    source = "estimado";
  if (div && div.dpu12m > 0) {
    dpu12m = div.dpu12m;
    source = "yahoo";
  } else if (price != null) {
    dpu12m = Math.round(price * segDy * 1e4) / 1e4; // estimativa consistente com o preço
  }

  return json({
    ticker,
    name: meta ? meta[0] : ticker,
    segment,
    price,
    dpu12m,
    source,
    seg_dy: segDy,
    n12: div?.n12 ?? null,
    divs: div?.divs ?? [], // [{date(ms), amount}]
  });
}
