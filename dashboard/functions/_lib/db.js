// Camada de dados — fala com o Supabase via PostgREST (REST), com `fetch` puro (sem npm).
// A service_role key fica só na Function (env), nunca vai pro client — mesma postura de
// segurança do backend antigo (que conectava como role `postgres`). RLS off é OK por isso.
//
// Porta o build_stocks()/CRUD do antigo dashboard/backend/app.py.

function base(env) {
  const url = env.SUPABASE_URL;
  const key = env.SUPABASE_SERVICE_KEY || env.SUPABASE_KEY;
  if (!url || !key)
    throw new Error("Configure SUPABASE_URL e SUPABASE_SERVICE_KEY.");
  return {
    url,
    headers: {
      apikey: key,
      Authorization: "Bearer " + key,
      "content-type": "application/json",
    },
  };
}

// SELECT: `path` no estilo PostgREST, ex.: "stocks?select=*" ou "watchlist?select=ticker".
export async function sel(env, path) {
  const { url, headers } = base(env);
  const r = await fetch(`${url}/rest/v1/${path}`, { headers });
  if (!r.ok) throw new Error(`select ${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function write(env, method, path, body, prefer) {
  const { url, headers } = base(env);
  const h = { ...headers };
  if (prefer) h.Prefer = prefer;
  const r = await fetch(`${url}/rest/v1/${path}`, {
    method,
    headers: h,
    body: body != null ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status} ${await r.text()}`);
  return r;
}

// INSERT simples.
export const insert = (env, table, rows) =>
  write(env, "POST", table, rows, "return=minimal");
// UPSERT por PK (ON CONFLICT DO UPDATE).
export const upsert = (env, table, rows) =>
  write(env, "POST", table, rows, "resolution=merge-duplicates,return=minimal");
// INSERT ignorando duplicatas (ON CONFLICT DO NOTHING).
export const ignoreDup = (env, table, rows) =>
  write(env, "POST", table, rows, "resolution=ignore-duplicates,return=minimal");
// DELETE por filtro PostgREST (ex.: "ticker=eq.PETR4").
export const del = (env, table, filter) =>
  write(env, "DELETE", `${table}?${filter}`, null, "return=minimal");
// PATCH — devolve as linhas afetadas (p/ detectar 404 quando vazio).
export async function patch(env, table, filter, body) {
  const r = await write(env, "PATCH", `${table}?${filter}`, body, "return=representation");
  return r.json();
}

const nn = (v) => v !== null && v !== undefined;

// Porta de build_stocks() (app.py): fundamentos + premissa salva + defaults globais + preço.
// `prices` é o mapa {ticker: preço}. Saída no mesmo shape que o front espera em fromApi().
export async function buildStocks(env, prices) {
  const [rows, premList, wlList, cfgList] = await Promise.all([
    sel(env, "stocks?select=*"),
    sel(env, "premissa_atual?select=*"),
    sel(env, "watchlist?select=ticker"),
    sel(env, "config?select=k,v"),
  ]);
  const cur = Object.fromEntries(premList.map((p) => [p.ticker, p]));
  const wl = new Set(wlList.map((r) => r.ticker));
  const cfg = Object.fromEntries(cfgList.map((r) => [r.k, r.v]));
  const gke = cfg.ke_global ?? 0.14;
  const groet = cfg.roet_global ?? 0.12;
  const gpayoutt = cfg.payoutt_global ?? 0.6;
  const gfade = cfg.fade_global ?? 10;
  const g_t_global = groet * (1 - gpayoutt);

  return rows.map((r) => {
    const p = cur[r.ticker] || {};
    const o = {
      ticker: r.ticker, nome: r.nome, cd_cvm: r.cd_cvm,
      setor: r.setor, subsetor: r.subsetor, segmento: r.segmento,
      perfil: r.perfil, tamanho: r.tamanho, gov: r.gov, ctrl: r.ctrl,
      modelo: r.modelo,
      tags: JSON.parse(r.tags || "[]"),
      monitored: wl.size ? wl.has(r.ticker) : !!r.monitored,
      liquidez: r.liquidez,
      // iniciais (por ativo, do dado real; premissa salva sobrepõe)
      lpa: nn(p.lpa) ? p.lpa : r.lpa,
      roe_i: nn(p.roe_i) ? p.roe_i : nn(r.roe_i) ? r.roe_i : 0.15,
      payout_i: nn(p.payout_i) ? p.payout_i : r.payout,
      // terminais/Ke (global, salvo override com "padrão" desmarcado)
      ke: !(p.ke_default ?? 1) && nn(p.ke) ? p.ke : gke,
      roe_t: !(p.roet_default ?? 1) && nn(p.roe_t) ? p.roe_t : groet,
      payout_t: !(p.payoutt_default ?? 1) && nn(p.payout_t) ? p.payout_t : gpayoutt,
      fade: !(p.fade_default ?? 1) && nn(p.fade) ? p.fade : gfade,
      growth_mode: p.growth_mode || "roe",
      g_i: p.g_i ?? null,
      g_t: !(p.roet_default ?? 1) && nn(p.g_t) ? p.g_t : g_t_global,
      // knobs do modelo Regra nº1 (Town)
      fut_pe: p.fut_pe ?? null,
      mos: p.mos ?? null,
    };
    o.price = prices[r.ticker] ?? null;
    o.fonte_preco = o.price != null ? "brapi" : "indisponível";
    return o;
  });
}
