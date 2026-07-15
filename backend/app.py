#!/usr/bin/env python3
"""
Backend do DIVYVAL — serve o dashboard e os dados reais das ações via Yahoo Finance.

Fontes:
- Yahoo Finance (yfinance): preço atual, histórico diário de fechamento, dividendos, LPA (EPS)
  e payout quando disponíveis. Tickers da B3 usam sufixo ".SA".
- stocks_meta.json: classificação curada (perfil, tamanho, governança, controle, segmento,
  situação) que não vem do Yahoo.

Endpoints:
  GET /api/stocks                       -> lista para o screener (com preço + fundamentos)
  GET /api/history/{ticker}?range=5y    -> série diária de fechamento para o gráfico
  GET /api/health                       -> status
  /                                     -> serve o frontend (dashboard/index.html)

Rodar:  cvm_base/.venv/bin/uvicorn app:app --app-dir dashboard/backend --port 8000
   (ou) cd dashboard/backend && ../../cvm_base/.venv/bin/python app.py
"""
import base64
import json
import os
import secrets
import threading
import time

import psycopg
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.dirname(HERE)
META = json.load(open(os.path.join(HERE, "stocks_meta.json"), encoding="utf-8"))
UNIVERSE = json.load(open(os.path.join(HERE, "universe.json"), encoding="utf-8"))
META_BY_TICKER = {m["ticker"]: m for m in META}

# Persistência: PostgreSQL (Supabase na nuvem). A conexão vem inteira de DATABASE_URL
# — use a connection string do POOLER do Supabase (porta 6543) tanto em produção
# quanto no dev local. Sem a env var o app não sobe (não há mais fallback SQLite).
DATABASE_URL = os.environ.get("DATABASE_URL")
# Senha compartilhada (Basic Auth). Sem a env var, o app fica aberto (dev local).
APP_PASSWORD = os.environ.get("APP_PASSWORD")

app = FastAPI(title="DIVYVAL")


@app.middleware("http")
async def _auth(request: Request, call_next):
    """Protege tudo com uma senha simples quando APP_PASSWORD está definida."""
    if APP_PASSWORD:
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(hdr[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(pw, APP_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Autenticação necessária", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="DIVYVAL"'})
    return await call_next(request)

_price_cache = {"data": None, "ts": 0}
_hist_cache = {}          # (ticker, range) -> {"data":..., "ts":...}
PRICE_TTL = 900           # 15 min
HIST_TTL = 1800           # 30 min

STOCK_COLS = ["ticker", "nome", "cd_cvm", "setor", "subsetor", "segmento", "perfil", "tamanho",
              "gov", "ctrl", "modelo", "tags", "monitored", "lpa", "payout", "liquidez",
              "g1", "ke", "gp"]


class _Row:
    """Linha que aceita índice por posição (r[0]) e por nome (r['col']), além de
    dict(r) — dá às tuplas do psycopg o mesmo contrato de acesso que o app espera."""
    __slots__ = ("_c", "_v")

    def __init__(self, cols, vals):
        self._c = cols
        self._v = tuple(vals)

    def __getitem__(self, k):
        return self._v[k] if isinstance(k, int) else self._v[self._c.index(k)]

    def keys(self):
        return list(self._c)

    def __iter__(self):
        return iter(self._v)

    def __len__(self):
        return len(self._v)


class _Cur:
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        r = self._cur.fetchone()
        return _Row(self._cols, r) if r is not None else None

    def fetchall(self):
        return [_Row(self._cols, r) for r in self._cur.fetchall()]


class _Conn:
    """Conexão fina sobre psycopg (PostgreSQL). Mantém o mesmo contrato que o app já usa
    (execute/fetchone/fetchall/commit) e traduz os placeholders `?` (estilo SQLite) para
    `%s` (estilo psycopg), para não precisar reescrever as queries."""

    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL não definida — configure a connection string do Postgres.")
        # prepare_threshold=None desativa prepared statements, exigência do pooler
        # (pgBouncer em modo transaction) do Supabase.
        self.raw = psycopg.connect(DATABASE_URL, prepare_threshold=None)

    def execute(self, sql, params=()):
        return _Cur(self.raw.execute(sql.replace("?", "%s"), params))

    def executescript(self, script):
        for stmt in filter(str.strip, script.split(";")):
            self.raw.execute(stmt)
        return self

    def commit(self):
        self.raw.commit()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                pass
        self.close()


def db():
    return _Conn()


def init_db():
    """Cria as tabelas e (re)semeia os fundamentos do universe.json + curadoria do meta.
    As premissas do usuário ficam em tabelas próprias e NÃO são tocadas ao re-semear."""
    with db() as c:
        c.executescript("""
          CREATE TABLE IF NOT EXISTS stocks(
            ticker TEXT PRIMARY KEY, nome TEXT, cd_cvm TEXT, setor TEXT, subsetor TEXT, segmento TEXT,
            perfil TEXT, tamanho TEXT, gov TEXT, ctrl TEXT, modelo TEXT, tags TEXT, monitored INTEGER,
            lpa REAL, payout REAL, liquidez REAL, roe_i REAL, g1 REAL, ke REAL, gp REAL, "user" INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS premissa_atual(
            ticker TEXT PRIMARY KEY, lpa REAL, payout REAL, g1 REAL, ke REAL, gp REAL, updated_at TEXT);
          CREATE TABLE IF NOT EXISTS premissa_hist(
            id BIGSERIAL PRIMARY KEY, ticker TEXT, date TEXT,
            lpa REAL, payout REAL, g1 REAL, ke REAL, gp REAL);
          CREATE TABLE IF NOT EXISTS watchlist(ticker TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS removed(ticker TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY, v REAL);
        """)
        # migrações (colunas do novo modelo ROE-fade). ADD COLUMN IF NOT EXISTS é idempotente.
        migr = ["ALTER TABLE stocks ADD COLUMN IF NOT EXISTS liquidez REAL",
                "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS roe_i REAL"]
        for tb in ("premissa_atual", "premissa_hist"):
            for col in ("ke_default INTEGER DEFAULT 1", "gp_default INTEGER DEFAULT 1",
                        "roe_i REAL", "payout_i REAL", "roe_t REAL", "payout_t REAL", "fade REAL",
                        "roet_default INTEGER DEFAULT 1", "payoutt_default INTEGER DEFAULT 1",
                        "fade_default INTEGER DEFAULT 1",
                        "growth_mode TEXT DEFAULT 'roe'", "g_i REAL", "g_t REAL"):
                migr.append(f"ALTER TABLE {tb} ADD COLUMN IF NOT EXISTS {col}")
        for sql in migr:
            c.execute(sql)
        for k, v in (("ke_global", 0.14), ("roet_global", 0.12), ("payoutt_global", 0.60), ("fade_global", 10)):
            c.execute("INSERT INTO config(k,v) VALUES(?,?) ON CONFLICT DO NOTHING", (k, v))
        removed = {r["ticker"] for r in c.execute("SELECT ticker FROM removed").fetchall()}
        seed_cols = ["ticker", "nome", "cd_cvm", "setor", "subsetor", "segmento", "perfil", "tamanho",
                     "gov", "ctrl", "modelo", "tags", "monitored", "lpa", "payout", "liquidez",
                     "roe_i", "g1", "ke", "gp"]
        seed_ph = ",".join("?" * len(seed_cols))
        seed_upd = ",".join(f"{col}=excluded.{col}" for col in seed_cols[1:])
        seed_sql = (f'INSERT INTO stocks({",".join(seed_cols)},"user") VALUES({seed_ph},0) '
                    f'ON CONFLICT(ticker) DO UPDATE SET {seed_upd},"user"=excluded."user"')
        for u in UNIVERSE:  # base do universo (não sobrescreve ações adicionadas pelo usuário)
            if u["ticker"] in removed:   # ação apagada pelo usuário -> não re-semeia
                continue
            monit = 1 if u.get("monitored") else 0
            c.execute(
                seed_sql,
                (u["ticker"], u["nome"], u.get("cd_cvm"), u["setor"], u["subsetor"], u["segmento"],
                 u.get("perfil") or "", u["tamanho"], u.get("gov") or "", u["ctrl"], u["modelo"],
                 json.dumps(u.get("tags") or [], ensure_ascii=False), monit,
                 u.get("lpa"), u.get("payout"), u.get("liquidez"), u.get("roe_i", 0.15),
                 u["g1"], u["ke"], u["gp"]))
        c.commit()


def fetch_prices(tickers):
    """Cotação atual de muitos tickers via Yahoo, em lotes (um download por lote)."""
    prices = {}
    sa = [t + ".SA" for t in tickers]
    for i in range(0, len(sa), 60):
        chunk = sa[i:i + 60]
        try:
            df = yf.download(chunk, period="5d", interval="1d", progress=False,
                             group_by="ticker", threads=True)
            for t in chunk:
                try:
                    s = (df[t]["Close"] if len(chunk) > 1 else df["Close"]).dropna()
                    if len(s):
                        prices[t[:-3]] = round(float(s.iloc[-1]), 2)
                except Exception:
                    pass
        except Exception as e:
            print("lote de preço falhou:", str(e)[:80])
    return prices


_fetching = {"on": False}


def _refresh_prices(tickers):
    try:
        _price_cache["data"] = fetch_prices(tickers)
        _price_cache["ts"] = time.time()
    finally:
        _fetching["on"] = False


def get_prices(tickers):
    """NÃO bloqueia: devolve o que estiver em cache e atualiza em segundo plano se vencido."""
    now = time.time()
    stale = _price_cache["data"] is None or now - _price_cache["ts"] > PRICE_TTL
    if stale and not _fetching["on"]:
        _fetching["on"] = True
        threading.Thread(target=_refresh_prices, args=(tickers,), daemon=True).start()
    return _price_cache["data"] or {}


def build_stocks():
    """Monta a lista do banco (fundamentos + premissas salvas do usuário) + preço ao vivo."""
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM stocks").fetchall()]
        cur = {r["ticker"]: dict(r) for r in c.execute("SELECT * FROM premissa_atual").fetchall()}
        wl = {r["ticker"] for r in c.execute("SELECT ticker FROM watchlist").fetchall()}
        cfg = {row["k"]: row["v"] for row in c.execute("SELECT k,v FROM config").fetchall()}
    gke = cfg.get("ke_global", 0.14)
    groet, gpayoutt, gfade = cfg.get("roet_global", 0.12), cfg.get("payoutt_global", 0.60), cfg.get("fade_global", 10)
    prices = get_prices([r["ticker"] for r in rows])
    out = []
    for r in rows:
        r["tags"] = json.loads(r["tags"] or "[]")
        r["monitored"] = (r["ticker"] in wl) if wl else bool(r["monitored"])
        p = cur.get(r["ticker"]) or {}
        # iniciais (por ativo, do dado real; premissa salva sobrepõe)
        r["lpa"] = p["lpa"] if p.get("lpa") is not None else r.get("lpa")
        r["roe_i"] = p["roe_i"] if p.get("roe_i") is not None else (r.get("roe_i") if r.get("roe_i") is not None else 0.15)
        r["payout_i"] = p["payout_i"] if p.get("payout_i") is not None else r.get("payout")
        # terminais/Ke (global, salvo se o ativo tem override com o "padrão" desmarcado)
        r["ke"] = p["ke"] if (not p.get("ke_default", 1) and p.get("ke") is not None) else gke
        r["roe_t"] = p["roe_t"] if (not p.get("roet_default", 1) and p.get("roe_t") is not None) else groet
        r["payout_t"] = p["payout_t"] if (not p.get("payoutt_default", 1) and p.get("payout_t") is not None) else gpayoutt
        r["fade"] = p["fade"] if (not p.get("fade_default", 1) and p.get("fade") is not None) else gfade
        # modo de crescimento: 'roe' (deriva g) ou 'g' (crescimento digitado direto)
        r["growth_mode"] = p.get("growth_mode") or "roe"
        r["g_i"] = p.get("g_i")
        g_t_global = groet * (1 - gpayoutt)   # g terminal padrão = ROE_t global × (1 − payout_t global)
        r["g_t"] = p["g_t"] if (not p.get("roet_default", 1) and p.get("g_t") is not None) else g_t_global
        for k in ("g1", "gp", "payout"):
            r.pop(k, None)
        r["price"] = prices.get(r["ticker"])
        r["fonte_preco"] = "yahoo" if r["price"] else "indisponível"
        r.pop("user", None)
        out.append(r)
    return out


@app.get("/api/stocks")
def api_stocks(refresh: int = 0):
    if refresh:
        _price_cache["ts"] = 0
    return build_stocks()


CFG_KEYS = (("ke", "ke_global", 0.14), ("roet", "roet_global", 0.12),
            ("payoutt", "payoutt_global", 0.60), ("fade", "fade_global", 10))


@app.get("/api/config")
def get_config():
    with db() as c:
        r = {row["k"]: row["v"] for row in c.execute("SELECT k,v FROM config").fetchall()}
    return {k: r.get(dbk, dflt) for k, dbk, dflt in CFG_KEYS}


@app.post("/api/config")
async def set_config(req: Request):
    p = await req.json()
    with db() as c:
        for k, dbk, _ in CFG_KEYS:
            if p.get(k) is not None:
                c.execute("INSERT INTO config(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                          [dbk, float(p[k])])
        c.commit()
    return {"ok": True}


PREM_COLS = ["lpa", "roe_i", "payout_i", "roe_t", "payout_t", "fade", "ke",
             "growth_mode", "g_i", "g_t",
             "ke_default", "roet_default", "payoutt_default", "fade_default"]


@app.get("/api/premissas/{ticker}")
def get_premissas(ticker: str):
    cols = ",".join(PREM_COLS)
    with db() as c:
        cur = c.execute(f"SELECT {cols},updated_at FROM premissa_atual WHERE ticker=?",
                        [ticker.upper()]).fetchone()
        hist = c.execute(f"SELECT date,{cols} FROM premissa_hist WHERE ticker=? ORDER BY id DESC LIMIT 40",
                         [ticker.upper()]).fetchall()
    return {"atual": dict(cur) if cur else None, "historico": [dict(h) for h in hist]}


@app.post("/api/premissas/{ticker}")
async def salvar_premissas(ticker: str, req: Request):
    p = await req.json()
    tk = ticker.upper()
    flags = ("ke_default", "roet_default", "payoutt_default", "fade_default")
    v = [p.get(k) for k in PREM_COLS[:-len(flags)]] + [int(bool(p.get(k, 1))) for k in flags]
    cols = ",".join(PREM_COLS)
    ph = ",".join("?" * len(PREM_COLS))
    upd = ",".join(f"{k}=excluded.{k}" for k in PREM_COLS)
    with db() as c:
        c.execute(f"INSERT INTO premissa_hist(ticker,date,{cols}) VALUES(?,?,{ph})", [tk, p.get("date"), *v])
        c.execute(f"INSERT INTO premissa_atual(ticker,{cols},updated_at) VALUES(?,{ph},?) "
                  f"ON CONFLICT(ticker) DO UPDATE SET {upd},updated_at=excluded.updated_at",
                  [tk, *v, p.get("date")])
        c.commit()
    return {"ok": True}


@app.get("/api/watchlist")
def get_watchlist():
    with db() as c:
        return [r["ticker"] for r in c.execute("SELECT ticker FROM watchlist ORDER BY ticker").fetchall()]


@app.post("/api/watchlist/{ticker}")
def add_watchlist(ticker: str):
    with db() as c:
        c.execute("INSERT INTO watchlist(ticker) VALUES(?) ON CONFLICT DO NOTHING", [ticker.upper()])
        c.commit()
    return {"ok": True}


@app.delete("/api/watchlist/{ticker}")
def del_watchlist(ticker: str):
    with db() as c:
        c.execute("DELETE FROM watchlist WHERE ticker=?", [ticker.upper()])
        c.commit()
    return {"ok": True}


@app.post("/api/stocks")
async def adicionar_acao(req: Request):
    s = await req.json()
    tk = (s.get("ticker") or "").upper()
    if not tk or not s.get("nome"):
        return JSONResponse({"ok": False, "erro": "ticker e nome obrigatórios"}, status_code=400)
    with db() as c:
        if c.execute("SELECT 1 FROM stocks WHERE ticker=?", [tk]).fetchone():
            return JSONResponse({"ok": False, "erro": "ticker já cadastrado"}, status_code=409)
        c.execute(
            "INSERT INTO stocks(ticker,nome,cd_cvm,setor,subsetor,segmento,perfil,tamanho,gov,ctrl,"
            'modelo,tags,monitored,lpa,payout,roe_i,"user") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
            (tk, s.get("nome"), None, s.get("setor", ""), s.get("subsetor", ""), s.get("segmento", ""),
             s.get("perfil", ""), s.get("tamanho", ""), s.get("gov", ""), s.get("ctrl", ""),
             s.get("modelo", "DDM · 2 est."), json.dumps(s.get("tags", []), ensure_ascii=False),
             1 if s.get("monitored") else 0, s.get("lpa"), s.get("payout"), s.get("roe_i", 0.15)))
        c.execute("DELETE FROM removed WHERE ticker=?", [tk])   # readicionar limpa o veto
        c.commit()
    return {"ok": True}


EDIT_FIELDS = ("nome", "setor", "subsetor", "segmento", "perfil", "tamanho", "gov", "ctrl", "modelo", "tags")


@app.patch("/api/stocks/{ticker}")
async def editar_acao(ticker: str, req: Request):
    """Atualiza só a classificação/identidade da ação (premissas ficam em /api/premissas)."""
    s = await req.json()
    tk = ticker.upper()
    sets, vals = [], []
    for f in EDIT_FIELDS:
        if f in s:
            sets.append(f"{f}=?")
            vals.append(json.dumps(s[f] or [], ensure_ascii=False) if f == "tags" else (s[f] or ""))
    if not sets:
        return JSONResponse({"ok": False, "erro": "nada para atualizar"}, status_code=400)
    vals.append(tk)
    with db() as c:
        n = c.execute(f"UPDATE stocks SET {','.join(sets)} WHERE ticker=?", vals).rowcount
        c.commit()
    if not n:
        return JSONResponse({"ok": False, "erro": "ticker não encontrado"}, status_code=404)
    return {"ok": True}


@app.delete("/api/stocks/{ticker}")
def remover_acao(ticker: str):
    """Apaga a ação por completo (base + watchlist + premissas) e veta o re-semear do universo."""
    tk = ticker.upper()
    with db() as c:
        c.execute("INSERT INTO removed(ticker) VALUES(?) ON CONFLICT DO NOTHING", [tk])
        c.execute("DELETE FROM stocks WHERE ticker=?", [tk])
        c.execute("DELETE FROM watchlist WHERE ticker=?", [tk])
        c.execute("DELETE FROM premissa_atual WHERE ticker=?", [tk])
        c.execute("DELETE FROM premissa_hist WHERE ticker=?", [tk])
        c.commit()
    return {"ok": True}


@app.get("/api/history/{ticker}")
def api_history(ticker: str, range: str = "5y"):
    key = (ticker.upper(), range)
    now = time.time()
    c = _hist_cache.get(key)
    if c and now - c["ts"] < HIST_TTL:
        return {"ticker": ticker, "series": c["data"]}
    try:
        h = yf.Ticker(ticker.upper() + ".SA").history(period=range, interval="1d")
        series = [[int(ts.timestamp() * 1000), round(float(c), 2)] for ts, c in h["Close"].dropna().items()]
    except Exception as e:
        return JSONResponse({"ticker": ticker, "series": [], "erro": str(e)[:120]}, status_code=502)
    _hist_cache[key] = {"data": series, "ts": now}
    return {"ticker": ticker, "series": series}


@app.get("/api/health")
def health():
    with db() as c:
        n = c.execute("SELECT count(*) FROM stocks").fetchone()[0]
    return {"ok": True, "tickers": n, "cache": _price_cache["data"] is not None}


init_db()   # cria/semeia o banco no start
get_prices([u["ticker"] for u in UNIVERSE])   # aquece o cache de preços em segundo plano

# frontend (precisa vir DEPOIS das rotas /api)
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
