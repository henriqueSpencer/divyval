import { json } from "../_lib/http.js";
import { getAllFiiDividends, FII_UNIVERSE } from "../_lib/fii.js";

// GET /api/fii-dpu?t=A,B,C — DPU 12m real (Yahoo) p/ até 24 tickers, em lotes de 8, cache 6h por ticker.
// Chamado progressivamente pelo front p/ preencher o screener sem estourar o tempo de uma request.
export async function onRequestGet(context) {
  const q = new URL(context.request.url).searchParams.get("t") || "";
  const tickers = q.split(",").map((t) => t.trim().toUpperCase()).filter((t) => FII_UNIVERSE[t]).slice(0, 24);
  const divs = await getAllFiiDividends(tickers, context);
  return json({ dpu: divs });
}
