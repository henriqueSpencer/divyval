import { json } from "../../_lib/http.js";
import { ignoreDup, del } from "../../_lib/db.js";

// POST /api/fii-watchlist/{ticker} — monitora; DELETE — deixa de monitorar.
export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  await ignoreDup(context.env, "fii_watchlist", [{ ticker: tk }]);
  return json({ ok: true });
}
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await del(context.env, "fii_watchlist", `ticker=eq.${tk}`);
  return json({ ok: true });
}
