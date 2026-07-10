#!/usr/bin/env python3
"""
build_universe.py — cadastra TODAS as ações da B3 no screener, com fundamentos reais da CVM.

- Mapeia cada ticker (b3_tickers.csv, nomes oficiais da brapi) -> cd_cvm da base CVM por nome.
- Calcula da base CVM (auditada): LPA = lucro líquido consolidado (último ano) ÷ nº de ações;
  payout ≈ dividendos+JCP pagos ÷ lucro; patrimônio líquido (p/ P/VP futuro).
- NÃO busca preço aqui (preço é ao vivo no backend). Gera universe.json.

Uso: cd dashboard/backend && ../../cvm_base/.venv/bin/python build_universe.py
"""
import csv, json, os, re, unicodedata, urllib.request
import duckdb

CAD_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
BRAPI_LIST = "https://brapi.dev/api/quote/list?type=stock"
SI_URL = ("https://statusinvest.com.br/category/advancedsearchresultpaginated"
          "?search=%7B%7D&orderColumn=&isAsc=&page=0&take=1000&CategoryType=1")


import base64
B3_DETAIL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetDetail/"


def clean_b3(s):
    """Normaliza nomes da B3 vindos do statusinvest (troca artefatos de '.' por ',')."""
    if not s:
        return ""
    s = s.strip().replace("Financeiro e Outros", "Financeiro")
    s = s.replace("..", ", ").replace(" . ", ", ").replace(". ", ", ")
    s = re.sub(r"\s+", " ", s).strip().strip(",").strip()
    return s


def map_gov(m):
    """market da B3 -> rótulo de governança."""
    m = (m or "").upper()
    if "NOVO MERCADO" in m: return "Novo Mercado"
    if "MAIS N" in m: return "Bovespa Mais N2"
    if "NIVEL 2" in m or "NÍVEL 2" in m: return "Nível 2"
    if "NIVEL 1" in m or "NÍVEL 1" in m: return "Nível 1"
    if "MAIS" in m: return "Bovespa Mais"
    return "Tradicional" if m else ""


def fetch_gov(cvms):
    """Governança (segmento de listagem) por cd_cvm, via B3 GetDetail (campo `market`)."""
    out = {}
    for cvm in cvms:
        try:
            p = base64.b64encode(json.dumps({"codeCVM": str(int(cvm)), "language": "pt-br"}).encode()).decode()
            req = urllib.request.Request(B3_DETAIL + p, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=15).read())
            if isinstance(d, str):
                d = json.loads(d)
            out[cvm] = map_gov(d.get("market"))
        except Exception:
            pass
    return out


def _n(v):
    return v if isinstance(v, (int, float)) else None


def derive_perfil(setor, s):
    """Perfil a partir de indicadores reais (não é achismo): commodity->Cíclica, DY alto->Dividendos, etc."""
    dy, pl, pvp = _n(s.get("dy")), _n(s.get("p_l")), _n(s.get("p_vp"))
    cagr, roe = _n(s.get("receitas_cagr5")), _n(s.get("roe"))
    if setor in ("Materiais Básicos", "Petróleo, Gás e Biocombustíveis"):
        return "Cíclica"
    if dy and dy >= 6:
        return "Dividendos"
    if cagr and cagr >= 12 and roe and roe >= 12:
        return "Crescimento"
    if pl and 0 < pl <= 9 and pvp and 0 < pvp <= 1.2:
        return "Valor"
    if setor in ("Utilidade Pública", "Consumo não Cíclico", "Saúde"):
        return "Defensiva"
    if cagr and cagr >= 8:
        return "Crescimento"
    return "Valor"


def derive_tags(s):
    """Situação (tags) a partir de indicadores reais."""
    dy, pl, pvp, roe = _n(s.get("dy")), _n(s.get("p_l")), _n(s.get("p_vp")), _n(s.get("roe"))
    dle, lpa, mc = _n(s.get("dividaliquidaebit")), _n(s.get("lpa")), _n(s.get("valormercado"))
    t = []
    if lpa is not None and lpa < 0: t.append("Prejuízo")
    if dy and dy >= 8: t.append("Alta DY")
    if pl and 0 < pl <= 8 and pvp and 0 < pvp <= 1: t.append("Barata")
    elif (pl and pl >= 25) or (pvp and pvp >= 4): t.append("Cara")
    if roe and roe >= 15 and (dle is None or dle <= 2): t.append("Qualidade")
    if dle and dle >= 3.5: t.append("Alavancada")
    if mc and mc >= 5e10 and "Prejuízo" not in t: t.append("Blue chip")
    return t[:3]


def clean_setor(s):
    s = (s or "").strip()
    s = re.sub(r"^Emp\. Adm\. Part\. - ", "", s)
    return "" if s == "Sem Setor Principal" else s


def map_controle(c):
    c = (c or "").upper()
    if "ESTATAL" in c: return "Estatal"
    if "ESTRANGEIRO" in c: return "Estrangeiro"
    if "PRIVADO" in c: return "Privada nacional"
    return ""


def size_from_mcap(mc):
    if not mc: return ""
    b = mc / 1e9
    return "Large cap" if b >= 10 else "Mid cap" if b >= 2 else "Small cap"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB = os.path.join(ROOT, "cvm_base", "cvm.duckdb")
TICKERS = os.path.join(HERE, "b3_tickers.csv")
OUT = os.path.join(HERE, "universe.json")

STOP = {"SA", "S", "A", "DO", "DA", "DE", "E", "DOS", "DAS", "CIA", "COMPANHIA"}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"EM RECUPERACAO JUDICIAL", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s):
    return frozenset(w for w in norm(s).split() if w not in STOP and len(w) > 1)


def main():
    con = duckdb.connect(DB, read_only=True)

    # dimensão empresas (prefere a entidade com dados mais recentes)
    emp = con.execute("SELECT cd_cvm, empresa, cnpj, ultimo_ano FROM empresas").fetchall()
    by_norm, by_tokens = {}, []
    for cd, nome, cnpj, uano in emp:
        key = norm(nome)
        if key not in by_norm or uano > by_norm[key][1]:
            by_norm[key] = (cd, uano)
        by_tokens.append((tokens(nome), cd, uano))

    def resolve(nome):
        k = norm(nome)
        if k in by_norm:
            return by_norm[k][0], "exato"
        tk = tokens(nome)
        best, bestsc = None, 0.0
        for tt, cd, uano in by_tokens:
            if not tt or not tk:
                continue
            j = len(tk & tt) / len(tk | tt)
            if j > bestsc or (j == bestsc and best and uano > best[1]):
                best, bestsc = (cd, uano), j
        if best and bestsc >= 0.72:
            return best[0], f"token {bestsc:.2f}"
        return None, "SEM MATCH"

    # fundamentos por cd_cvm (base CVM, consolidado, último exercício)
    # LPA = Lucro Básico por Ação REPORTADO pela empresa (conta 3.99.01.xx, preferindo ON).
    # É o dado auditado direto — não depende do nº de ações (campo inconsistente na CVM).
    eps = {r[0]: r[1] for r in con.execute("""
        SELECT cd_cvm, vl_conta FROM dre
        WHERE tipo_dem='con' AND ordem_exerc='ÚLTIMO' AND cd_conta LIKE '3.99.01.%'
          AND strip_accents(ds_conta) IN ('ON','PN','PNA','PNB') AND vl_conta<>0
        QUALIFY row_number() OVER (PARTITION BY cd_cvm
                 ORDER BY ano DESC,(strip_accents(ds_conta)='ON') DESC, abs(vl_conta) DESC)=1
    """).fetchall()}
    # lucro líquido total (p/ payout, que independe de nº de ações)
    ni = {r[0]: (r[1], r[2]) for r in con.execute("""
        SELECT cd_cvm, vl_conta, escala FROM dre
        WHERE tipo_dem='con' AND ordem_exerc='ÚLTIMO' AND cd_conta IN ('3.11','3.09')
        QUALIFY row_number() OVER (PARTITION BY cd_cvm ORDER BY ano DESC,(cd_conta='3.11') DESC)=1
    """).fetchall()}
    div = {r[0]: r[1] for r in con.execute("""
        SELECT cd_cvm, arg_max(v, ano) FROM (
          SELECT cd_cvm, ano, sum(abs(vl_conta)) v FROM dfc_mi
          WHERE tipo_dem='con' AND ordem_exerc='ÚLTIMO'
            AND (strip_accents(ds_conta) ILIKE '%dividendo%' OR strip_accents(ds_conta) ILIKE '%juros sobre capital%')
          GROUP BY cd_cvm, ano) GROUP BY cd_cvm
    """).fetchall()}

    def reais(pair):
        if not pair or pair[0] is None:
            return None
        v, esc = pair
        return v * 1000 if esc == "MIL" else v

    # classificação oficial: Setor + Controle (cadastro CVM, por cd_cvm); Tamanho (market cap brapi)
    cad_setor, cad_ctrl, mcap = {}, {}, {}
    try:
        raw = urllib.request.urlopen(CAD_URL, timeout=40).read().decode("latin-1")
        for r in csv.DictReader(raw.splitlines(), delimiter=";"):
            cd = (r.get("CD_CVM") or "").zfill(6)
            cad_setor[cd] = clean_setor(r.get("SETOR_ATIV"))
            cad_ctrl[cd] = map_controle(r.get("CONTROLE_ACIONARIO"))
        print(f"cadastro CVM: {len(cad_setor)} empresas com setor/controle")
    except Exception as e:
        print("cadastro CVM falhou:", str(e)[:80])
    try:
        js = json.loads(urllib.request.urlopen(BRAPI_LIST, timeout=30).read())
        mcap = {s["stock"]: s.get("market_cap") for s in js["stocks"]}
        print(f"brapi: {sum(1 for v in mcap.values() if v)} com market cap")
    except Exception as e:
        print("brapi falhou:", str(e)[:80])
    # classificação oficial B3 de 3 níveis (Setor › Subsetor › Segmento) via statusinvest
    si = {}
    try:
        req = urllib.request.Request(SI_URL, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh)", "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"})
        sij = json.loads(urllib.request.urlopen(req, timeout=40).read())
        si = {x["ticker"]: x for x in sij["list"]}
        print(f"statusinvest: {len(si)} ações com classificação B3")
    except Exception as e:
        print("statusinvest falhou:", str(e)[:80])

    universe, matched, nomatch, no_lpa = [], 0, [], 0
    with open(TICKERS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        tk, nome = r["ticker"], r["empresa"]
        cd, how = resolve(nome)
        s = si.get(tk)
        lpa = payout = None
        if cd:
            matched += 1
            lpa = eps.get(cd)                        # LPA auditado da CVM (primário)
            if lpa is not None and abs(lpa) > 100:   # EPS absurdo (grupamento/distressed) -> descarta
                lpa = None
            netinc = reais(ni.get(cd))
            d = div.get(cd)
            if d and netinc and netinc > 0:
                payout = round(min(1.5, max(0.0, d * 1000 / netinc)), 3)
        if lpa is None and s and s.get("lpa") and abs(s["lpa"]) <= 100:   # fallback statusinvest
            lpa = round(s["lpa"], 2)
        if not cd:
            nomatch.append(tk)
        if lpa is None:
            no_lpa += 1
        # classificação: só B3 oficial (statusinvest) — sem misturar taxonomia da CVM
        setor = clean_b3(s.get("sectorname")) if s else ""
        tamanho = size_from_mcap((s.get("valormercado") if s else None) or mcap.get(tk))
        universe.append({
            "ticker": tk, "nome": nome, "cd_cvm": cd,
            "setor": setor,
            "subsetor": clean_b3(s.get("subsectorname")) if s else "",
            "segmento": clean_b3(s.get("segmentname")) if s else "",
            "perfil": derive_perfil(setor, s) if s else "",
            "tamanho": tamanho, "gov": "", "ctrl": cad_ctrl.get(cd or "", ""),
            "modelo": "DDM · 2 est.", "tags": derive_tags(s) if s else [], "monitored": False,
            "lpa": round(lpa, 2) if lpa is not None else None,
            "payout": payout if payout is not None else 0.45,
            "roe_i": round(s["roe"] / 100, 4) if s and isinstance(s.get("roe"), (int, float)) and s["roe"] > 0 else 0.15,
            "liquidez": round(s["liquidezmediadiaria"]) if s and s.get("liquidezmediadiaria") else None,
            "g1": 0.06, "ke": 0.14, "gp": 0.04,
        })

    # governança (segmento de listagem B3) por cd_cvm — passada de rede (~2 min)
    cvms = sorted({u["cd_cvm"] for u in universe if u["cd_cvm"]})
    print(f"buscando governança na B3 para {len(cvms)} empresas...")
    gov = fetch_gov(cvms)
    for u in universe:
        u["gov"] = gov.get(u["cd_cvm"], "")
    print(f"governança preenchida: {sum(1 for u in universe if u['gov'])}/{len(universe)}")

    json.dump(universe, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"tickers: {len(universe)} | mapeados p/ CVM: {matched} | com LPA calculado: {len(universe)-no_lpa}")
    print(f"sem match CVM: {len(nomatch)}  (ex.: {nomatch[:8]})")
    print("\nVALIDAÇÃO (LPA calculado da CVM):")
    idx = {u["ticker"]: u for u in universe}
    for t in ["PETR4", "VALE3", "ITUB4", "BBAS3", "WEGE3", "ABEV3", "TAEE11", "MGLU3"]:
        u = idx.get(t)
        if u:
            print(f"  {t:7} LPA={u['lpa']}  payout={u['payout']}  cd_cvm={u['cd_cvm']}")
    print("\nSalvo:", OUT)


if __name__ == "__main__":
    main()
