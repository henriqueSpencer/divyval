// Cotações e histórico. Preço: brapi.dev/api/quote/list (1 request, sem token, ~todas as ações
// da B3, campo `close`). Histórico do gráfico: Yahoo chart per-ticker, sob demanda.

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const BRAPI_LIST = "https://brapi.dev/api/quote/list?limit=10000";

// Mapa {ticker: preço} de toda a B3, com cache de 15 min no edge (caches.default).
export async function getPrices(context) {
  let cache = null;
  const cacheKey = new Request("https://divyval.internal/prices-v1");
  try {
    cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit.json();
  } catch (_) {
    /* Cache API pode não existir no dev local — segue sem cache */
  }
  const r = await fetch(BRAPI_LIST, { headers: { "User-Agent": UA } });
  if (!r.ok) return {};
  const j = await r.json();
  const map = {};
  for (const s of j.stocks || [])
    if (s.close != null) map[s.stock] = Math.round(s.close * 100) / 100;
  if (cache) {
    const res = new Response(JSON.stringify(map), {
      headers: { "content-type": "application/json", "Cache-Control": "max-age=900" },
    });
    context.waitUntil(cache.put(cacheKey, res));
  }
  return map;
}

// Série diária de fechamento p/ o gráfico. Cache de 30 min por (ticker,range).
export async function getHistory(ticker, range, context) {
  const sym = ticker.toUpperCase() + ".SA";
  let cache = null;
  const cacheKey = new Request(`https://divyval.internal/hist/${sym}/${range}`);
  try {
    cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return (await hit.json()).series;
  } catch (_) {}
  const u = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?range=${range}&interval=1d`;
  const r = await fetch(u, { headers: { "User-Agent": UA } });
  if (!r.ok) throw new Error("yahoo " + r.status);
  const j = await r.json();
  const res = j?.chart?.result?.[0];
  const ts = res?.timestamp || [];
  const cl = res?.indicators?.quote?.[0]?.close || [];
  const series = [];
  for (let i = 0; i < ts.length; i++)
    if (cl[i] != null) series.push([ts[i] * 1000, Math.round(cl[i] * 100) / 100]);
  if (cache && series.length) {
    const body = new Response(JSON.stringify({ series }), {
      headers: { "content-type": "application/json", "Cache-Control": "max-age=1800" },
    });
    context.waitUntil(cache.put(cacheKey, body));
  }
  return series;
}
