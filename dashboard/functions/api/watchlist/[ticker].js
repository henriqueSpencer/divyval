import { json } from "../../_lib/http.js";
import { ignoreDup, del } from "../../_lib/db.js";

// POST /api/watchlist/{ticker} — adiciona à watchlist.
export async function onRequestPost(context) {
  const tk = context.params.ticker.toUpperCase();
  await ignoreDup(context.env, "watchlist", [{ ticker: tk }]);
  return json({ ok: true });
}

// DELETE /api/watchlist/{ticker} — remove da watchlist.
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await del(context.env, "watchlist", `ticker=eq.${tk}`);
  return json({ ok: true });
}
