// FIIs — universo curado + preço (brapi bulk) + proventos (Yahoo, por ticker).
// PREVIEW (branch fii-valuation): nada aqui escreve em banco. Preço ao vivo pela brapi (mesmo
// endpoint das ações). DPU/DY real vem do Yahoo na tela de detalhe (1 chamada por ticker, cache);
// onde o Yahoo não estiver disponível (ex.: rate-limit local), o front usa a estimativa por
// DY típico do segmento (rotulada "estimado") ou o valor manual do usuário. NÃO usamos a CVM p/ FII:
// o informe anual é defasado e a estrutura de classes corrompe DPU/segmento (verificado).

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const BRAPI_LIST = "https://brapi.dev/api/quote/list?type=fund&limit=10000";

// DY típico por segmento (fallback só p/ estimar DPU quando não há dado real; sempre rotulado).
export const SEG_DY = {
  "Logística": 0.095,
  "Lajes corporativas": 0.085,
  "Shoppings": 0.09,
  "Papel (CRI)": 0.115,
  "Híbrido": 0.095,
  "Renda urbana": 0.09,
  "Fundo de fundos": 0.10,
  "Fiagro": 0.125,
  "Hospitalar": 0.09,
  "Desenvolvimento": 0.10,
};

// Universo curado de FIIs líquidos (classificação própria — a da CVM é inconfiável).
// { ticker: [nome curto, segmento] }
export const FII_UNIVERSE = {
  // Logística / galpões
  HGLG11: ["CSHG Logística", "Logística"],
  XPLG11: ["XP Log", "Logística"],
  BTLG11: ["BTG Logística", "Logística"],
  VILG11: ["Vinci Logística", "Logística"],
  BRCO11: ["Bresco Logística", "Logística"],
  GGRC11: ["GGR Covepi", "Logística"],
  LVBI11: ["VBI Logístico", "Logística"],
  PATL11: ["Pátria Logística", "Logística"],
  // Lajes corporativas / escritórios
  PVBI11: ["VBI Prime Properties", "Lajes corporativas"],
  HGRE11: ["CSHG Real Estate", "Lajes corporativas"],
  JSRE11: ["JS Real Estate", "Lajes corporativas"],
  RCRB11: ["Rio Bravo Renda Corp.", "Lajes corporativas"],
  BRCR11: ["BTG Corporate Office", "Lajes corporativas"],
  RBRP11: ["RBR Properties", "Lajes corporativas"],
  // Shoppings
  XPML11: ["XP Malls", "Shoppings"],
  VISC11: ["Vinci Shopping Centers", "Shoppings"],
  HGBS11: ["CSHG Brasil Shopping", "Shoppings"],
  MALL11: ["Malls Brasil Plural", "Shoppings"],
  HSML11: ["HSI Malls", "Shoppings"],
  // Papel / recebíveis (CRI)
  KNCR11: ["Kinea Rend. Imob. (CDI)", "Papel (CRI)"],
  KNIP11: ["Kinea Índices de Preços", "Papel (CRI)"],
  KNSC11: ["Kinea Securities", "Papel (CRI)"],
  MXRF11: ["Maxi Renda", "Papel (CRI)"],
  CPTS11: ["Capitânia Securities", "Papel (CRI)"],
  RECR11: ["REC Recebíveis", "Papel (CRI)"],
  IRDM11: ["Iridium Recebíveis", "Papel (CRI)"],
  HGCR11: ["CSHG Recebíveis", "Papel (CRI)"],
  RBRR11: ["RBR Rendimento High Grade", "Papel (CRI)"],
  VGIP11: ["Valora IPCA", "Papel (CRI)"],
  // Híbrido
  KNRI11: ["Kinea Renda Imobiliária", "Híbrido"],
  BTHF11: ["BTG Hedge Fund Imob.", "Híbrido"],
  // Renda urbana / varejo
  HGRU11: ["CSHG Renda Urbana", "Renda urbana"],
  TRXF11: ["TRX Real Estate", "Renda urbana"],
  RBVA11: ["Rio Bravo Renda Varejo", "Renda urbana"],
  // Fundo de fundos
  BCFF11: ["BTG FoF", "Fundo de fundos"],
  RBRF11: ["RBR Alpha Multiestratégia", "Fundo de fundos"],
  HFOF11: ["CSHG FoF", "Fundo de fundos"],
  KFOF11: ["Kinea FoF", "Fundo de fundos"],
  // Fiagro
  VGIA11: ["Valora Fiagro", "Fiagro"],
  RURA11: ["Itaú Fiagro", "Fiagro"],
  // Hospitalar
  NSLU11: ["Hospital Nossa Senhora Lourdes", "Hospitalar"],
};

// {ticker: preço} de todos os fundos da brapi, com cache de 15 min no edge.
export async function getFiiPrices(context) {
  let cache = null;
  const cacheKey = new Request("https://divyval.internal/fii-prices-v1");
  try {
    cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit.json();
  } catch (_) {}
  const r = await fetch(BRAPI_LIST, { headers: { "User-Agent": UA } });
  if (!r.ok) return {};
  const j = await r.json();
  const map = {};
  for (const s of j.stocks || [])
    if (s.subType === "fii" && s.close != null) map[s.stock] = Math.round(s.close * 100) / 100;
  if (cache) {
    const res = new Response(JSON.stringify(map), {
      headers: { "content-type": "application/json", "Cache-Control": "max-age=900" },
    });
    context.waitUntil(cache.put(cacheKey, res));
  }
  return map;
}

// Proventos (Yahoo chart, events=div) de UM fundo: soma 12m (dpu12m), série e preço.
// Cache de 6h. Yahoo pode dar 429 de IP de datacenter/local → devolve null (o front estima).
export async function getFiiDividends(ticker, context) {
  const sym = ticker.toUpperCase() + ".SA";
  let cache = null;
  const cacheKey = new Request("https://divyval.internal/fii-div/" + sym);
  try {
    cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit.json();
  } catch (_) {}
  let out = null;
  try {
    const u = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?range=2y&interval=1d&events=div`;
    const r = await fetch(u, { headers: { "User-Agent": UA } });
    if (r.ok) {
      const j = await r.json();
      const res = j?.chart?.result?.[0];
      const price = res?.meta?.regularMarketPrice ?? null;
      const divObj = res?.events?.dividends || {};
      const divs = Object.values(divObj)
        .map((d) => ({ date: d.date * 1000, amount: Math.round(d.amount * 1e6) / 1e6 }))
        .sort((a, b) => a.date - b.date);
      // soma dos proventos dos últimos ~12 meses
      const cutoff = Date.now() - 370 * 86400 * 1000;
      const dpu12m = divs.filter((d) => d.date >= cutoff).reduce((s, d) => s + d.amount, 0);
      out = {
        price,
        dpu12m: Math.round(dpu12m * 1e6) / 1e6,
        n12: divs.filter((d) => d.date >= cutoff).length,
        divs,
      };
    }
  } catch (_) {}
  if (cache && out && out.dpu12m > 0) {
    const body = new Response(JSON.stringify(out), {
      headers: { "content-type": "application/json", "Cache-Control": "max-age=21600" },
    });
    context.waitUntil(cache.put(cacheKey, body));
  }
  return out;
}
