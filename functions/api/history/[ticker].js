import { json } from "../../_lib/http.js";
import { getHistory } from "../../_lib/quotes.js";

// GET /api/history/{ticker}?range=5y — série diária de fechamento p/ o gráfico.
export async function onRequestGet(context) {
  const tk = context.params.ticker.toUpperCase();
  const range = new URL(context.request.url).searchParams.get("range") || "5y";
  try {
    const series = await getHistory(tk, range, context);
    return json({ ticker: tk, series });
  } catch (e) {
    return json({ ticker: tk, series: [], erro: String(e).slice(0, 120) }, 502);
  }
}
