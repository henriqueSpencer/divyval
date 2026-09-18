// FIIs — universo curado + preço (brapi bulk) + proventos (Yahoo) + VP/cota (CVM Informe Mensal).
// PREVIEW (branch fii-valuation): nada aqui escreve em banco.
// - Preço ao vivo: brapi (mesmo endpoint das ações).
// - DPU/DY real: Yahoo (events=div, soma 12m) — buscado EM LOTE p/ todo o universo em /api/fiis
//   (cache 6h por ticker), então screener e detalhe usam o MESMO número. Sem Yahoo, estimativa por
//   DY típico do segmento (rotulada "estimado").
// - VP/cota (p/ P/VP): Informe MENSAL de FII da CVM via backend/build_fii_vp.py → fii_vp.js
//   (oficial, mês a mês; o informe ANUAL da base DuckDB não serve — classes corrompem DPU/segmento).
import { FII_VP } from "./fii_vp.js";
export { FII_VP };

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
  HGLG11: ["Pátria Log (ex-CSHG Logística)", "Logística", "BRHGLGCTF004"],
  XPLG11: ["XP Log", "Logística", "BRXPLGCTF002"],
  BTLG11: ["BTG Logística", "Logística", "BRBTLGCTF000"],
  VILG11: ["Vinci Logística", "Logística", "BRVILGCTF001"],
  BRCO11: ["Bresco Logística", "Logística", "BRBRCOCTF007"],
  GGRC11: ["Zagros Renda Imobiliária (ex-GGR)", "Logística", "BRGGRCCTF002"],
  LVBI11: ["VBI Logístico", "Logística", "BRLVBICTF002"],
  // Lajes corporativas / escritórios
  PVBI11: ["VBI Prime Properties", "Lajes corporativas", "BRPVBICTF003"],
  HGRE11: ["Pátria Escritórios (ex-CSHG RE)", "Lajes corporativas", "BRHGRECTF006"],
  JSRE11: ["JS Real Estate", "Lajes corporativas", "BRJSRECTF007"],
  RCRB11: ["Rio Bravo Renda Corp.", "Lajes corporativas", "BRRCRBCTF000"],
  BRCR11: ["BC Fund (BTG Corporate Office)", "Lajes corporativas", "BRBRCRCTF000"],
  RBRP11: ["Pátria Properties (ex-RBR)", "Lajes corporativas", "BRRBRPCTF002"],
  // Shoppings
  XPML11: ["XP Malls", "Shoppings", "BRXPMLCTF000"],
  VISC11: ["Vinci Shopping Centers", "Shoppings", "BRVISCCTF005"],
  HGBS11: ["Hedge Brasil Shopping", "Shoppings", "BRHGBSCTF000"],
  HSML11: ["HSI Malls", "Shoppings", "BRHSMLCTF007"],
  // Papel / recebíveis (CRI)
  KNCR11: ["Kinea Rend. Imob. (CDI)", "Papel (CRI)", "BRKNCRCTF000"],
  KNIP11: ["Kinea Índices de Preços", "Papel (CRI)", "BRKNIPCTF001"],
  KNSC11: ["Kinea Securities", "Papel (CRI)", "BRKNSCCTF008"],
  MXRF11: ["Maxi Renda", "Papel (CRI)", "BRMXRFCTF008"],
  CPTS11: ["Capitânia Securities", "Papel (CRI)", "BRCPTSCTF004"],
  RECR11: ["REC Recebíveis", "Papel (CRI)", "BRRECRCTF004"],
  HGCR11: ["Pátria Recebíveis (ex-CSHG)", "Papel (CRI)", "BRHGCRCTF000"],
  RBRR11: ["RBR Rendimento High Grade", "Papel (CRI)", "BRRBRRCTF008"],
  VGIP11: ["Valora IPCA", "Papel (CRI)", "BRVGIPCTF002"],
  // Híbrido
  KNRI11: ["Kinea Renda Imobiliária", "Híbrido", "BRKNRICTF007"],
  BTHF11: ["BTG Hedge Fund Imob.", "Híbrido", "BR0EI9CTF007"],
  // Renda urbana / varejo
  HGRU11: ["Pátria Renda Urbana (ex-CSHG)", "Renda urbana", "BRHGRUCTF002"],
  TRXF11: ["TRX Real Estate", "Renda urbana", "BRTRXFCTF003"],
  RBVA11: ["Rio Bravo Renda Varejo", "Renda urbana", "BRRBVACTF006"],
  // Fundo de fundos
  HFOF11: ["CSHG FoF", "Fundo de fundos", "BRHFOFCTF002"],
  KFOF11: ["Kinea FoF", "Fundo de fundos", "BRKFOFCTF006"],
  // Fiagro
  // Hospitalar
  NSLU11: ["Hospital Nossa Senhora Lourdes", "Hospitalar", "BRNSLUCTF008"],
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

// DPU 12m de vários fundos, em lotes de 6 (rate-limit do Yahoo), reaproveitando o cache por ticker.
// Devolve {ticker: {dpu12m, n12}} só p/ os que responderam.
export async function getAllFiiDividends(tickers, context) {
  const out = {};
  for (let i = 0; i < tickers.length; i += 6) {
    await Promise.all(
      tickers.slice(i, i + 6).map(async (t) => {
        try {
          const d = await getFiiDividends(t, context);
          if (d && d.dpu12m > 0) out[t] = { dpu12m: d.dpu12m, n12: d.n12 };
        } catch (_) {}
      })
    );
  }
  return out;
}
