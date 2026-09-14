// Indicadores macro do Banco Central (API do SGS). Grátis, sem token, CORS aberto.
// Selic meta (% a.a.) = série 432; IPCA acumulado 12 meses (%) = série 13522.
// Referência de mercado no Ke (modo IPCA + NTN-B) e régua ao lado da TIR.

const SGS = (serie) =>
  `https://api.bcb.gov.br/dados/serie/bcdata.sgs.${serie}/dados/ultimos/1?formato=json`;

const SERIES = { selic: 432, ipca12m: 13522 };

// "16/09/2026" -> "09/2026" (mês de referência, curto)
function mesRef(br) {
  const m = /^\d{2}\/(\d{2}\/\d{4})$/.exec(br || "");
  return m ? m[1] : br || "";
}

async function fetchSerie(serie) {
  const r = await fetch(SGS(serie), { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error("bcb " + r.status);
  const j = await r.json();
  const row = Array.isArray(j) ? j[j.length - 1] : null;
  if (!row) throw new Error("bcb vazio");
  const v = parseFloat(String(row.valor).replace(",", "."));
  if (!isFinite(v)) throw new Error("bcb nan");
  return { valor: v, data: row.data };
}

// { selic, ipca12m, selic_data, ipca_data, fonte } — cache de 12h no edge (caches.default).
// Busca as duas séries em paralelo e tolera uma falhar (a outra ainda vale).
export async function getMacro(context) {
  let cache = null;
  const cacheKey = new Request("https://divyval.internal/macro-v1");
  try {
    cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit.json();
  } catch (_) {
    /* Cache API pode não existir no dev local — segue sem cache */
  }
  const [selic, ipca] = await Promise.all([
    fetchSerie(SERIES.selic).catch(() => null),
    fetchSerie(SERIES.ipca12m).catch(() => null),
  ]);
  const out = {
    selic: selic ? selic.valor : null,
    ipca12m: ipca ? ipca.valor : null,
    selic_data: selic ? selic.data : null, // dd/mm/aaaa da meta vigente
    ipca_data: ipca ? mesRef(ipca.data) : null, // mm/aaaa de referência
    fonte: "BCB",
  };
  // só cacheia se veio ao menos um valor (não congela uma falha total por 12h)
  if (cache && (out.selic != null || out.ipca12m != null)) {
    const res = new Response(JSON.stringify(out), {
      headers: { "content-type": "application/json", "Cache-Control": "max-age=43200" },
    });
    context.waitUntil(cache.put(cacheKey, res));
  }
  return out;
}
