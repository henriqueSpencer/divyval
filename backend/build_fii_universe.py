#!/usr/bin/env python3
"""
Gera functions/_lib/fii_data.js — o UNIVERSO de FIIs do DIVYVAL + VP/cota (valor patrimonial) por fundo:
  universo = todos os FIIs com cotação na brapi (~330)  ∩  Informe MENSAL de FII da CVM (VP/cota, nome, segmento)

Fontes:
- brapi.dev/api/quote/list?type=fund (subType "fii", campo close) → quais tickers existem + preço p/ plausibilidade.
- dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/ (zip do ano) → Valor_Patrimonial_Cotas mês a mês, nome e
  Segmento_Atuacao (oficial). Diferente do informe ANUAL da base DuckDB, que não serve p/ isto.

Como casa ticker ↔ fundo (a CVM não tem ticker):
- FII_CURATED em fii.js pode fixar o ISIN (e nome/segmento curados) — usado quando existe.
- senão, candidatos = fundos cujo ISIN começa com "BR" + 4 letras do ticker (BRHGLG…); pode haver
  vários (classes/CNPJs ou colisão de raiz, ex. TRXF) → escolhe a linha do mês mais recente cujo
  P/VP contra o preço real é plausível (0,4–1,8); desempate pelo maior PL. Sem candidato plausível
  → fundo entra SEM VP (P/VP "—"; o modelo sai pelo DY exigido).

Rodar mensalmente (após a CVM publicar o informe):  python3 backend/build_fii_universe.py   (na raiz do repo)
Depende só do CLI `duckdb` e da rede.
"""
import io, json, os, re, subprocess, sys, tempfile, urllib.request, zipfile, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FII_JS = os.path.join(ROOT, "functions", "_lib", "fii.js")
OUT_JS = os.path.join(ROOT, "functions", "_lib", "fii_data.js")
CVM_BASE = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/"

# Segmento_Atuacao da CVM → rótulo do app (Multicategoria/Outros são inúteis → "—")
SEG_MAP = {"Logística": "Logística", "Escritórios": "Lajes corporativas", "Lajes Corporativas": "Lajes corporativas",
           "Shoppings": "Shoppings", "Residencial": "Residencial", "Hospital": "Hospitalar", "Hotel": "Hotel",
           "Varejo": "Renda urbana", "Educacional": "Educacional", "Híbrido": "Híbrido", "Títulos e Val. Mob.": "Papel (CRI)"}

def curated():
    """{ticker: (nome, segmento, isin)} de FII_CURATED em fii.js."""
    src = open(FII_JS, encoding="utf-8").read()
    body = src[src.index("FII_CURATED"):]
    body = body[:body.index("};")]
    out = {}
    for m in re.finditer(r'^\s*([A-Z0-9]{5,6}):\s*\[\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([A-Z0-9]{12})"', body, re.M):
        out[m.group(1)] = (m.group(2), m.group(3), m.group(4))
    return out

def brapi():
    d = json.load(urllib.request.urlopen("https://brapi.dev/api/quote/list?type=fund&limit=10000", timeout=60))
    return {s["stock"]: s["close"] for s in d.get("stocks", []) if s.get("subType") == "fii" and s.get("close")}

def download_latest(tmp):
    y0 = datetime.date.today().year
    for y in (y0, y0 - 1):
        try: data = urllib.request.urlopen(f"{CVM_BASE}inf_mensal_fii_{y}.zip", timeout=120).read()
        except Exception: continue
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        g = os.path.join(tmp, f"inf_mensal_fii_geral_{y}.csv"); c = os.path.join(tmp, f"inf_mensal_fii_complemento_{y}.csv")
        if os.path.exists(g) and os.path.exists(c): return g, c, y
    sys.exit("não consegui baixar o informe mensal da CVM")

def duck(sql):
    r = subprocess.run(["duckdb", "-json", "-c", sql], capture_output=True, text=True)
    if r.returncode != 0: sys.exit("duckdb: " + r.stderr)
    return json.loads(r.stdout or "[]")

STRIP = [r"FUNDO DE INVESTIMENTO IMOBILI[ÁA]RIO", r"FUNDO DE INVEST(IMENTO)?\.? IMOB(ILI[ÁA]RIO)?\.?", r"FDO DE INVEST IMOBILI[ÁA]RIO",
         r"RESPONSABILIDADE LIMITADA", r"RESP\.? LIMITADA", r"\bRESP\b\.?", r"\bFII\b", r"\bF\.?I\.?I\.?\b", r"\bRL\b", r"\bLTDA\b", r"\bFI\b"]
def clean_name(n):
    s = n.upper()
    for p in STRIP: s = re.sub(p, " ", s)
    s = re.sub(r"[\-–—]+\s*$", "", re.sub(r"\s+", " ", s)).strip(" -–—.")
    small = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "II", "III", "IV"}
    words = [w if w in {"II", "III", "IV", "XP", "BTG", "CSHG", "HSI", "JS", "RBR", "VBI", "BC", "REC", "CRI", "TRX", "HNS"} else (w.lower() if w in small else w.capitalize()) for w in s.split()]
    return " ".join(words)[:48] or n[:48]

def main():
    cur = curated(); px = brapi()
    with tempfile.TemporaryDirectory() as tmp:
        g, c, y = download_latest(tmp)
        rd = lambda p: f"read_csv('{p}',delim=';',header=true,all_varchar=true,encoding='latin-1')"
        rows = duck(f"""
          WITH g AS (SELECT DISTINCT CNPJ_Fundo_Classe cnpj, Codigo_ISIN isin, Nome_Fundo_Classe nome, Segmento_Atuacao seg FROM {rd(g)} WHERE Codigo_ISIN LIKE 'BR%'),
               c AS (SELECT CNPJ_Fundo_Classe cnpj, Data_Referencia dref, TRY_CAST(REPLACE(Valor_Patrimonial_Cotas,',','.') AS DOUBLE) vp,
                            TRY_CAST(REPLACE(Patrimonio_Liquido,',','.') AS DOUBLE) pl FROM {rd(c)} WHERE Valor_Patrimonial_Cotas IS NOT NULL)
          SELECT g.isin, g.nome, g.seg, c.dref, c.vp, c.pl FROM g JOIN c USING(cnpj) WHERE c.vp>0""")
    byisin, byroot = {}, {}
    for r in rows:
        byisin.setdefault(r["isin"], []).append(r); byroot.setdefault(r["isin"][2:6], []).append(r)
    def pick(cands, p):
        if not cands: return None
        m = max(r["dref"] for r in cands); cand = [r for r in cands if r["dref"] == m]
        ok = [r for r in cand if p and 0.4 <= p / float(r["vp"]) <= 1.8]
        if not ok: return None
        return max(ok, key=lambda r: r["pl"] or 0)
    uni, vpmap, n_vp = {}, {}, 0
    for t in sorted(px):
        p = px[t]; name = seg = isin = None; row = None
        if t in cur:
            name, seg, isin = cur[t]; row = pick(byisin.get(isin, []), p) or (max(byisin[isin], key=lambda r: r["dref"]) if byisin.get(isin) else None)
        else:
            row = pick(byroot.get(t[:4], []), p)
            if row: isin = row["isin"]; name = clean_name(row["nome"]); seg = SEG_MAP.get(row["seg"], "—")
            else: name = t; seg = "—"
        uni[t] = [name, seg, isin]
        if row and (p is None or 0.4 <= p / float(row["vp"]) <= 1.8):
            vpmap[t] = {"vp": round(float(row["vp"]), 4), "ref": row["dref"][:7]}; n_vp += 1
    js = ("// GERADO por backend/build_fii_universe.py — universo de FIIs (brapi ∩ CVM) + VP/cota (Informe Mensal CVM).\n"
          f"// Gerado em {datetime.date.today().isoformat()} (inf_mensal_fii_{y}.zip). Não editar à mão; rode o script.\n"
          "export const FII_UNIVERSE = " + json.dumps(uni, ensure_ascii=False, indent=0) + ";\n"
          "export const FII_VP = " + json.dumps(vpmap, ensure_ascii=False, indent=0) + ";\n")
    open(OUT_JS, "w", encoding="utf-8").write(js)
    segs = {}
    for v in uni.values(): segs[v[1]] = segs.get(v[1], 0) + 1
    print(f"{len(uni)} fundos (brapi) | {n_vp} com VP/cota plausível | curados: {len(cur)} → {os.path.relpath(OUT_JS, ROOT)}")
    print("segmentos:", dict(sorted(segs.items(), key=lambda x: -x[1])))

if __name__ == "__main__": main()
