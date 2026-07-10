#!/usr/bin/env python3
"""
build_tickers.py — cria o "de-para" ticker B3 -> cd_cvm dentro de cvm.duckdb.

A CVM não fornece ticker (PETR4) nem preço; só CNPJ/CD_CVM/nome. Este script resolve o
cd_cvm de cada ticker A PARTIR DO NOME na própria base (nunca digitamos cd_cvm à mão, para
não errar), grava a tabela `tickers` em cvm.duckdb e exporta dashboard/backend/tickers.csv.

Depois disso dá para consultar por ticker, ex.:
  duckdb cvm_base/cvm.duckdb "SELECT ano, vl_conta FROM dre JOIN tickers USING(cd_cvm)
    WHERE ticker='PETR4' AND cd_conta='3.11' AND ordem_exerc='ÚLTIMO' AND tipo_dem='con'"

Uso:  cvm_base/.venv/bin/python cvm_base/build_tickers.py
Extensão: adicione linhas em MAPA (ticker -> (padrão de nome, setor)). Vários tickers podem
apontar para o mesmo cd_cvm (ON/PN/UNIT).
"""
import csv
import os
import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DBFILE = os.path.join(BASE, "cvm.duckdb")
CSV_OUT = os.path.join(ROOT, "dashboard", "backend", "tickers.csv")

# ticker -> (padrão ILIKE do nome na CVM, setor). Padrão deve casar a EMPRESA LISTADA
# (holding), evitando subsidiárias (ex.: usar a controladora, não "CEMIG GERACAO").
MAPA = {
    "PETR4": ("PETROLEO BRASILEIRO%PETROBRAS", "Petróleo e Gás"),
    "PETR3": ("PETROLEO BRASILEIRO%PETROBRAS", "Petróleo e Gás"),
    "VALE3": ("VALE S.A.", "Materiais Básicos"),
    "ITUB4": ("ITAU UNIBANCO HOLDING", "Financeiro"),
    "BBDC4": ("BCO BRADESCO S.A.", "Financeiro"),
    "BBAS3": ("BCO BRASIL S.A.", "Financeiro"),
    "SANB11": ("BCO SANTANDER (BRASIL)", "Financeiro"),
    "ABEV3": ("AMBEV S.A.", "Consumo não Cíclico"),
    "WEGE3": ("WEG S.A.", "Bens Industriais"),
    "TAEE11": ("TRANSMISSORA ALIAN", "Utilidade Pública"),
    "EGIE3": ("ENGIE BRASIL ENERGIA", "Utilidade Pública"),
    "CPLE6": ("CIA PARANAENSE DE ENERGIA%COPEL", "Utilidade Pública"),
    "CMIG4": ("CIA ENERGETICA DE MINAS GERAIS%CEMIG", "Utilidade Pública"),
    "ELET3": ("ELETROBRAS", "Utilidade Pública"),
    "EQTL3": ("EQUATORIAL", "Utilidade Pública"),
    "CPFE3": ("CPFL ENERGIA", "Utilidade Pública"),
    "NEOE3": ("NEOENERGIA", "Utilidade Pública"),
    "ALUP11": ("ALUPAR INVESTIMENTO", "Utilidade Pública"),
    "SBSP3": ("CIA SANEAMENTO BASICO EST%SAO PAULO", "Utilidade Pública"),
    "SAPR11": ("CIA SANEAMENTO DO PARANA%SANEPAR", "Utilidade Pública"),
    "CSMG3": ("COPASA", "Utilidade Pública"),
    "BBSE3": ("BB SEGURIDADE", "Financeiro"),
    "PSSA3": ("PORTO SEGURO S.A.", "Financeiro"),
    "B3SA3": ("B3 S.A", "Financeiro"),
    "ITSA4": ("ITAUSA S.A", "Financeiro"),
    "KLBN11": ("KLABIN S.A.", "Materiais Básicos"),
    "SUZB3": ("SUZANO S.A.", "Materiais Básicos"),
    "GGBR4": ("GERDAU S.A.", "Materiais Básicos"),
    "GOAU4": ("METALURGICA GERDAU", "Materiais Básicos"),
    "CSNA3": ("CIA SIDERURGICA NACIONAL", "Materiais Básicos"),
    "USIM5": ("USINAS SID%MINAS GERAIS%USIMINAS", "Materiais Básicos"),
    "UNIP6": ("UNIPAR CARBOCLORO", "Materiais Básicos"),
    "VIVT3": ("TELEFONICA BRASIL", "Comunicações"),
    "RENT3": ("LOCALIZA RENT A CAR", "Consumo Cíclico"),
    "TIMS3": ("TIM S.A.", "Comunicações"),
    "LREN3": ("LOJAS RENNER", "Consumo Cíclico"),
    "RADL3": ("RAIA DROGASIL", "Consumo não Cíclico"),
    "MGLU3": ("MAGAZINE LUIZA", "Consumo Cíclico"),
    "JBSS3": ("JBS S.A.", "Consumo não Cíclico"),
    "BRFS3": ("BRF S.A.", "Consumo não Cíclico"),
    "MRFG3": ("MARFRIG", "Consumo não Cíclico"),
    "BEEF3": ("MINERVA S.A.", "Consumo não Cíclico"),
    "SLCE3": ("SLC AGRICOLA", "Consumo não Cíclico"),
    "SMTO3": ("SAO MARTINHO", "Consumo não Cíclico"),
    "ABCB4": ("BCO ABC BRASIL", "Financeiro"),
    "RAIL3": ("RUMO S.A.", "Bens Industriais"),
    "EMBR3": ("EMBRAER", "Bens Industriais"),
    "POMO4": ("MARCOPOLO", "Bens Industriais"),
    "TOTS3": ("TOTVS", "Tecnologia"),
    "HYPE3": ("HYPERA", "Saúde"),
    "FLRY3": ("FLEURY", "Saúde"),
    "PRIO3": ("PETRO RIO", "Petróleo e Gás"),
    "VBBR3": ("VIBRA ENERGIA", "Petróleo e Gás"),
    "UGPA3": ("ULTRAPAR", "Petróleo e Gás"),
    "CSAN3": ("COSAN S.A.", "Petróleo e Gás"),
    "PCAR3": ("CIA BRASILEIRA DE DISTRIBUICAO", "Consumo não Cíclico"),
    "ASAI3": ("SENDAS DISTRIBUIDORA", "Consumo não Cíclico"),
    "CYRE3": ("CYRELA BRAZIL REALTY", "Consumo Cíclico"),
    "MRVE3": ("MRV ENGENHARIA", "Consumo Cíclico"),
    "DXCO3": ("DEXCO", "Materiais Básicos"),
    "GRND3": ("GRENDENE", "Consumo Cíclico"),
    "KEPL3": ("KEPLER WEBER", "Bens Industriais"),
}
# remove entradas-placeholder inválidas
MAPA = {t: v for t, v in MAPA.items() if v[0]}


def resolve(con, pattern):
    """Escolhe o melhor cd_cvm para um padrão de nome: empresa mais recente e, no empate,
    nome mais curto (a controladora listada costuma ter o nome mais canônico).
    Match acento-insensível (strip_accents) e sempre envolto em %...%."""
    rows = con.execute(
        "SELECT cd_cvm, empresa, ultimo_ano FROM empresas "
        "WHERE strip_accents(empresa) ILIKE strip_accents(?) "
        "ORDER BY ultimo_ano DESC, length(empresa) ASC",
        [f"%{pattern}%"],
    ).fetchall()
    return rows


def main():
    con = duckdb.connect(DBFILE)
    resolved, problemas = [], []
    for ticker, (pattern, setor) in sorted(MAPA.items()):
        cands = resolve(con, pattern)
        if not cands:
            problemas.append((ticker, pattern, "NENHUM match"))
            continue
        cd_cvm, empresa, _ = cands[0]
        resolved.append((ticker, cd_cvm, empresa, setor))
        if len(cands) > 1:  # registra ambiguidade para conferência
            outros = "; ".join(f"{c[0]}={c[1]}" for c in cands[1:3])
            problemas.append((ticker, empresa, f"ambíguo (usei {cd_cvm}); outros: {outros}"))

    # grava tabela tickers na base (fonte única para consultas e dashboard)
    con.execute("DROP TABLE IF EXISTS tickers")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, cd_cvm VARCHAR, nome VARCHAR, setor VARCHAR)")
    con.executemany("INSERT INTO tickers VALUES (?,?,?,?)", resolved)
    con.close()

    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "cd_cvm", "nome", "setor"])
        w.writerows(resolved)

    print(f"✓ {len(resolved)} tickers resolvidos e gravados em tabela `tickers` + {CSV_OUT}\n")
    for t, cd, emp, _ in resolved:
        print(f"  {t:<8} {cd}  {emp}")
    if problemas:
        print("\n⚠ Conferir:")
        for p in problemas:
            print("  ", " | ".join(str(x) for x in p))


if __name__ == "__main__":
    main()
