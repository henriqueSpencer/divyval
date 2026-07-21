import { json } from "../_lib/http.js";
import { sel } from "../_lib/db.js";

// GET /api/watchlist — lista de tickers monitorados.
export async function onRequestGet(context) {
  const rows = await sel(context.env, "watchlist?select=ticker&order=ticker.asc");
  return json(rows.map((r) => r.ticker));
}
