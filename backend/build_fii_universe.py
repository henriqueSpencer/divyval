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
- Segmento: a CVM diz "Multicategoria/Outros" p/ a maioria (inútil). Classificamos pela COMPOSIÇÃO DA
  CARTEIRA (arquivo ativo_passivo: CRI/LCI/LIG = papel; cotas de FII = fundo de fundos; Direitos sobre
  imóveis = tijolo, com venda/construção/terrenos = desenvolvimento), refinando o tipo de tijolo pelo
  Segmento_Atuacao quando específico ou por palavras do nome. FII_CURATED sobrepõe tudo.
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

def classify(name, seg_cvm, comp):
    """Segmento pelo balanço (comp = shares sobre Total_Investido) + refino por segmento/nome."""
    n = (name or "").upper()
    if re.search(r"FIAGRO|\bAGRO\b|AGRONEG|\bRURAL\b|TERRAS", n): return "Fiagro"
    tijolo_sub = SEG_MAP.get(seg_cvm)
    if tijolo_sub in ("Papel (CRI)", "Híbrido"): tijolo_sub = None      # só subtipos de tijolo
    def by_name():
        if re.search(r"LOG[IÍ]ST|\bLOG\b|GALP", n): return "Logística"
        if re.search(r"SHOPPING|MALL", n): return "Shoppings"
        if re.search(r"OFFICE|ESCRIT|CORPORATE|CORPORATIV|LAJES|TORRE|PRIME PROP|EDIF", n): return "Lajes corporativas"
        if re.search(r"RENDA URBANA|VAREJO|RETAIL|SUPERMERC", n): return "Renda urbana"
        if re.search(r"HOSPITAL|HEALTH|SA[UÚ]DE|CL[IÍ]NIC", n): return "Hospitalar"
        if re.search(r"HOTEL|HOSPITALIDADE", n): return "Hotel"
        if re.search(r"RESIDENC|HABITA|MORADIA", n): return "Residencial"
        if re.search(r"EDUCA|UNIVERS|ESCOLA", n): return "Educacional"
        if re.search(r"AG[EÊ]NCIA|BANC[OÁ]", n): return "Agências bancárias"
        if re.search(r"DESENVOLV|INCORPORA", n): return "Desenvolvimento"
        if re.search(r"\bFOF\b|FUNDO DE FUNDOS|FUNDOS DE INVESTIMENTO IMOB", n): return "Fundo de fundos"
        if re.search(r"HEDGE|MULTIESTRAT|MULTI ?ESTRAT|MULTICARTEIRA", n): return "Híbrido"
        if re.search(r"\bCRI\b|RECEB[IÍ]VEIS|CR[EÉ]DITO|HIGH GRADE|HIGH YIELD|SECURITIES|RENDIMENTOS IMOB|\bYIELD\b|\bDEBT\b", n): return "Papel (CRI)"
        return None
    TIJOLO = {"Logística", "Shoppings", "Lajes corporativas", "Renda urbana", "Hospitalar", "Hotel", "Residencial", "Educacional", "Agências bancárias"}
    nm = by_name()
    if nm in TIJOLO: return nm     # nome explícito de tijolo vence (muitos detêm imóveis via FIIs subsidiários → composição diria "FoF")
    if comp:
        papel, fof, tijolo, dev = comp["papel"], comp["fof"], comp["tijolo"], comp["dev"]
        if papel >= 0.5: return "Papel (CRI)"
        if fof >= 0.5: return "Fundo de fundos"
        if dev >= 0.4: return "Desenvolvimento"
        if tijolo >= 0.5: return tijolo_sub or nm or "Tijolo"
        if sum(x >= 0.25 for x in (papel, fof, tijolo)) >= 2: return "Híbrido"
    return tijolo_sub or nm or "—"

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
        a = os.path.join(tmp, f"inf_mensal_fii_ativo_passivo_{y}.csv")
        rd = lambda p: f"read_csv('{p}',delim=';',header=true,all_varchar=true,encoding='latin-1')"
        num = lambda col: f"COALESCE(TRY_CAST(REPLACE({col},',','.') AS DOUBLE),0)"
        comp_rows = duck(f"""
          SELECT * FROM (SELECT CNPJ_Fundo_Classe cnpj, Data_Referencia dref,
              {num('Total_Investido')} tot,
              {num('CRI')}+{num('CRI_CRA')}+{num('Letras_Hipotecarias')}+{num('LCI')}+{num('LCI_LCA')}+{num('LIG')} papel,
              {num('FII')} fof,
              {num('Direitos_Bens_Imoveis')}+{num('Acoes_Sociedades_Atividades_FII')}+{num('Cotas_Sociedades_Atividades_FII')} tijolo,
              {num('Imoveis_Venda_Acabados')}+{num('Imoveis_Venda_Construcao')}+{num('Terrenos')}+{num('FIP')} dev,
              ROW_NUMBER() OVER (PARTITION BY CNPJ_Fundo_Classe ORDER BY Data_Referencia DESC) rn
            FROM {rd(a)}) WHERE rn=1 AND tot>0""") if os.path.exists(a) else []
        COMP = {r["cnpj"]: {k: float(r[k]) / float(r["tot"]) for k in ("papel", "fof", "tijolo", "dev")} for r in comp_rows}
        rows = duck(f"""
          WITH g AS (SELECT DISTINCT CNPJ_Fundo_Classe cnpj, Codigo_ISIN isin, Nome_Fundo_Classe nome, Segmento_Atuacao seg FROM {rd(g)} WHERE Codigo_ISIN LIKE 'BR%'),
               c AS (SELECT CNPJ_Fundo_Classe cnpj, Data_Referencia dref, TRY_CAST(REPLACE(Valor_Patrimonial_Cotas,',','.') AS DOUBLE) vp,
                            TRY_CAST(REPLACE(Patrimonio_Liquido,',','.') AS DOUBLE) pl FROM {rd(c)} WHERE Valor_Patrimonial_Cotas IS NOT NULL)
          SELECT g.isin, g.cnpj, g.nome, g.seg, c.dref, c.vp, c.pl FROM g JOIN c USING(cnpj) WHERE c.vp>0""")
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
            if row: isin = row["isin"]; name = clean_name(row["nome"]); seg = classify(row["nome"], row["seg"], COMP.get(row["cnpj"]))
            else:
                # sem VP plausível: se a raiz casa com UM ÚNICO fundo na CVM, a identidade é inequívoca →
                # usa nome/segmento dele (o VP continua de fora, pois não passou na plausibilidade)
                uniq = {r["isin"]: r for r in byroot.get(t[:4], [])}
                if len(uniq) == 1:
                    r0 = next(iter(uniq.values())); name = clean_name(r0["nome"]); seg = classify(r0["nome"], r0["seg"], COMP.get(r0["cnpj"]))
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
