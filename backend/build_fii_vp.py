#!/usr/bin/env python3
"""
Gera functions/_lib/fii_vp.js: VP/cota (valor patrimonial da cota) de cada FII do universo curado,
a partir do INFORME MENSAL de FII da CVM (dados.cvm.gov.br — diferente do informe ANUAL da base DuckDB).

Por que precisa disto: P/VP exige o VP/cota atual, que não vem de nenhuma API grátis (statusinvest
está atrás do Cloudflare; brapi per-ticker exige token). O informe mensal da CVM é oficial, gratuito
e traz `Valor_Patrimonial_Cotas` mês a mês.

Armadilhas (todas tratadas aqui, verificadas em set/2026):
- A CVM não tem ticker: casamos pelo ISIN, que fica FIXADO por fundo em `FII_UNIVERSE` (fii.js).
  A raiz do ISIN (BR+4 letras) NÃO é confiável sozinha (ex.: TRXF casava com outro fundo).
- Um mesmo ISIN pode aparecer em mais de um CNPJ (classes): escolhemos a linha cujo P/VP contra
  o preço real (brapi) é plausível (0,4–1,8); desempate pelo maior PL. Sem preço, maior PL.
- Usa o mês mais recente disponível para o fundo (o mês corrente costuma estar parcial).

Rodar (mensalmente, após a CVM publicar o informe):
    python3 backend/build_fii_vp.py            # na raiz do repo (dashboard/)
Depende só do CLI `duckdb` (já usado na base CVM) e da rede.
"""
import io, json, os, re, subprocess, sys, tempfile, urllib.request, zipfile, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FII_JS = os.path.join(ROOT, "functions", "_lib", "fii.js")
OUT_JS = os.path.join(ROOT, "functions", "_lib", "fii_vp.js")
CVM_BASE = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/"

def universe():
    """{ticker: isin} lido de FII_UNIVERSE em fii.js (3º campo de cada entrada)."""
    src = open(FII_JS, encoding="utf-8").read()
    body = src[src.index("FII_UNIVERSE"):]
    out = {}
    for m in re.finditer(r'^\s*([A-Z0-9]{5,6}):\s*\[\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"([A-Z0-9]{12})"', body, re.M):
        out[m.group(1)] = m.group(2)
    if not out: sys.exit("não achei ISINs em FII_UNIVERSE (esperado: [nome, segmento, ISIN])")
    return out

def prices():
    r = urllib.request.urlopen("https://brapi.dev/api/quote/list?type=fund&limit=10000", timeout=60)
    d = json.load(r)
    return {s["stock"]: s["close"] for s in d.get("stocks", []) if s.get("subType") == "fii" and s.get("close") is not None}

def download_latest(tmp):
    year = datetime.date.today().year
    for y in (year, year - 1):
        url = f"{CVM_BASE}inf_mensal_fii_{y}.zip"
        try:
            data = urllib.request.urlopen(url, timeout=120).read()
        except Exception:
            continue
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        g = os.path.join(tmp, f"inf_mensal_fii_geral_{y}.csv"); c = os.path.join(tmp, f"inf_mensal_fii_complemento_{y}.csv")
        if os.path.exists(g) and os.path.exists(c): return g, c, y
    sys.exit("não consegui baixar o informe mensal da CVM")

def duck(sql):
    r = subprocess.run(["duckdb", "-json", "-c", sql], capture_output=True, text=True)
    if r.returncode != 0: sys.exit("duckdb: " + r.stderr)
    return json.loads(r.stdout or "[]")

def main():
    uni = universe(); px = prices()
    with tempfile.TemporaryDirectory() as tmp:
        g, c, y = download_latest(tmp)
        rd = lambda p: f"read_csv('{p}',delim=';',header=true,all_varchar=true,encoding='latin-1')"
        isins = ",".join(f"'{i}'" for i in uni.values())
        rows = duck(f"""
          WITH g AS (SELECT DISTINCT CNPJ_Fundo_Classe cnpj, Codigo_ISIN isin, Nome_Fundo_Classe nome FROM {rd(g)} WHERE Codigo_ISIN IN ({isins})),
               c AS (SELECT CNPJ_Fundo_Classe cnpj, Data_Referencia dref,
                            TRY_CAST(REPLACE(Valor_Patrimonial_Cotas,',','.') AS DOUBLE) vp,
                            TRY_CAST(REPLACE(Patrimonio_Liquido,',','.') AS DOUBLE) pl
                     FROM {rd(c)} WHERE Valor_Patrimonial_Cotas IS NOT NULL)
          SELECT g.isin, g.nome, c.dref, c.vp, c.pl FROM g JOIN c USING(cnpj) WHERE c.vp>0""")
    by = {}
    for r in rows: by.setdefault(r["isin"], []).append(r)
    out, problems = {}, []
    for t, isin in uni.items():
        rs = by.get(isin)
        if not rs: problems.append(f"{t}: ISIN {isin} sem linhas no informe"); continue
        m = max(r["dref"] for r in rs); cand = [r for r in rs if r["dref"] == m]
        p = px.get(t)
        pool = [r for r in cand if p and 0.4 <= p / float(r["vp"]) <= 1.8] or cand
        row = max(pool, key=lambda r: r["pl"] or 0)
        vp = float(row["vp"]); pvp = (p / vp) if p else None
        if pvp is not None and not (0.4 <= pvp <= 1.8): problems.append(f"{t}: P/VP {pvp:.2f} implausível (VP {vp:.2f}, preço {p})")
        out[t] = {"vp": round(vp, 4), "ref": m[:7], "nome": row["nome"]}
        print(f"{t:8} VP {vp:9.2f}  P/VP {pvp if pvp else 0:5.2f}  {m[:7]}  {row['nome'][:40]}")
    js = ("// GERADO por backend/build_fii_vp.py — VP/cota (valor patrimonial) por FII, do Informe Mensal da CVM.\n"
          f"// Gerado em {datetime.date.today().isoformat()} a partir de inf_mensal_fii_{y}.zip. Não editar à mão; rode o script.\n"
          "export const FII_VP = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    open(OUT_JS, "w", encoding="utf-8").write(js)
    print(f"\n{len(out)}/{len(uni)} fundos → {os.path.relpath(OUT_JS, ROOT)}")
    if problems: print("ATENÇÃO:\n  " + "\n  ".join(problems))

if __name__ == "__main__": main()
