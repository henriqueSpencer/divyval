#!/usr/bin/env python3
"""
build_base.py — ETL das DFPs (Demonstrações Financeiras Padronizadas) da CVM.

Lê os CSVs brutos de "Dados CVM -Acões -Anuais" (ISO-8859-1, separador ';'),
converte cada tipo de demonstração para Parquet particionado por ano (compressão
zstd) e cria as views consultáveis em cvm.duckdb.

Idempotente: pode ser reexecutado sempre que você baixar um ano novo da CVM.
Uso:  cvm_base/.venv/bin/python cvm_base/build_base.py
"""
import duckdb
import glob
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
RAW = os.path.join(ROOT, "Dados CVM -Acões -Anuais")
PARQUET = os.path.join(BASE, "parquet")
DBFILE = os.path.join(BASE, "cvm.duckdb")
CLEAN_DIR = os.path.join(BASE, ".clean_cache")

# opções comuns de leitura dos CSVs da CVM (encoding é injetado em tempo de execução)
def opts(encoding):
    return (f"delim=';', header=true, encoding='{encoding}', union_by_name=true, "
            f"all_varchar=true, null_padding=true")

# Demonstrações financeiras (têm CD_CONTA / ORDEM_EXERC / VL_CONTA e versões con+ind).
# token = trecho do nome do arquivo; extra = coluna adicional (só DMPL tem COLUNA_DF).
FIN = [
    ("bpa",    "BPA",    None),
    ("bpp",    "BPP",    None),
    ("dre",    "DRE",    None),
    ("dfc_md", "DFC_MD", None),
    ("dfc_mi", "DFC_MI", None),
    ("dmpl",   "DMPL",   "COLUNA_DF"),
    ("dva",    "DVA",    None),
    ("dra",    "DRA",    None),
]


def q(files):
    """Lista de arquivos -> literal de array SQL do DuckDB."""
    return "[" + ",".join("'" + f.replace("'", "''") + "'" for f in files) + "]"


def find(token, side=None):
    """Encontra CSVs de um tipo em todas as pastas de ano (com ou sem sufixo de ano)."""
    pat = f"*_{token}_{side}*.csv" if side else f"*_{token}*.csv"
    return sorted(glob.glob(os.path.join(RAW, "dfp_cia_aberta_*", pat)))


def find_cadastro():
    """Arquivo-cadastro anual: dfp_cia_aberta.csv (2010) e dfp_cia_aberta_YYYY.csv."""
    a = glob.glob(os.path.join(RAW, "dfp_cia_aberta_*", "dfp_cia_aberta.csv"))
    b = glob.glob(os.path.join(RAW, "dfp_cia_aberta_*", "dfp_cia_aberta_[0-9][0-9][0-9][0-9].csv"))
    return sorted(a + b)


def sanitize(path):
    """Reescreve um CSV latin-1 como UTF-8 removendo bytes de controle C0 (ex.: 0x07 BEL,
    que aparecem no texto do parecer de 2018) que o decoder estrito do DuckDB rejeita.
    Devolve o caminho do arquivo higienizado em cache."""
    out = os.path.join(CLEAN_DIR, path.replace(os.sep, "__"))
    os.makedirs(CLEAN_DIR, exist_ok=True)
    txt = open(path, "rb").read().decode("latin-1")
    txt = "".join(c for c in txt if c >= " " or c in "\t\n\r")
    with open(out, "w", encoding="utf-8") as f:
        f.write(txt)
    return out


def select_sql(groups, encoding):
    """Monta o SELECT que une os grupos (side, arquivos). side=None => sem coluna tipo_dem."""
    parts = []
    for side, files in groups:
        tag = f"'{side}' AS tipo_dem, " if side else ""
        parts.append(
            f"SELECT *, {tag}CAST(DT_REFER[1:4] AS INTEGER) AS ano "
            f"FROM read_csv({q(files)}, {opts(encoding)})"
        )
    return " UNION ALL BY NAME ".join(parts)


def write_parquet(con, name, groups):
    """Grava o Parquet particionado por ano. Tenta latin-1 (rápido); se o DuckDB rejeitar
    algum arquivo por bytes de controle, higieniza tudo para UTF-8 e repete."""
    out = os.path.join(PARQUET, name)
    for attempt, enc, gs in (("latin-1", "latin-1", groups),
                             ("utf-8-limpo", "utf-8", None)):
        if gs is None:  # fallback: higieniza todos os arquivos dos grupos
            gs = [(side, [sanitize(f) for f in files]) for side, files in groups]
        try:
            shutil.rmtree(out, ignore_errors=True)
            con.execute(
                f"COPY ({select_sql(gs, enc)}) TO '{out}' "
                f"(FORMAT parquet, PARTITION_BY (ano), OVERWRITE_OR_IGNORE true, COMPRESSION zstd)"
            )
            n = con.execute(f"SELECT count(*) FROM read_parquet('{out}/**/*.parquet')").fetchone()[0]
            note = "" if attempt == "latin-1" else "  (higienizado)"
            print(f"  ✓ {name:<20} {n:>12,} linhas{note}")
            return n
        except duckdb.InvalidInputException as e:
            if "encoded" in str(e) and attempt == "latin-1":
                continue  # tenta o caminho higienizado
            raise
    raise RuntimeError(f"Falha ao gravar {name}")


def main():
    os.makedirs(PARQUET, exist_ok=True)
    con = duckdb.connect(DBFILE)
    con.execute("PRAGMA threads=4")

    print(f"Fonte: {RAW}")
    print(f"Saída: {PARQUET}\n")

    # ---- 1. Demonstrações financeiras (con + ind) ----
    print("Demonstrações financeiras (con+ind):")
    for name, token, _extra in FIN:
        groups = [(side, find(token, side)) for side in ("con", "ind")]
        groups = [(s, fs) for s, fs in groups if fs]
        if not groups:
            print(f"  ⚠ {name}: nenhum arquivo encontrado, pulando")
            continue
        write_parquet(con, name, groups)

    # ---- 2. Tipos de arquivo único (sem con/ind) ----
    print("\nOutros:")
    for name, files in [
        ("parecer", find("parecer")),
        ("composicao_capital", find("composicao_capital")),
        ("cadastro", find_cadastro()),
    ]:
        if not files:
            print(f"  ⚠ {name}: nenhum arquivo encontrado, pulando")
            continue
        write_parquet(con, name, [(None, files)])

    # ---- 3. Views ----
    print("\nCriando views em cvm.duckdb ...")
    build_views(con)
    con.close()
    shutil.rmtree(CLEAN_DIR, ignore_errors=True)  # descarta cache de higienização
    print("\nConcluído. Base em:", DBFILE)


def build_views(con):
    def pq(name):
        return os.path.join(PARQUET, name, "**", "*.parquet").replace("'", "''")

    # mapeamento coluna-fonte -> alias/expr desejado nas views limpas das demonstrações.
    # Alguns tipos não têm todas (ex.: BPA/BPP são foto pontual, sem DT_INI_EXERC).
    FIN_COLS = [
        ("CNPJ_CIA", "CNPJ_CIA AS cnpj"),
        ("CD_CVM", "CD_CVM AS cd_cvm"),
        ("DENOM_CIA", "DENOM_CIA AS empresa"),
        ("ano", "ano"),
        ("tipo_dem", "tipo_dem"),
        ("ORDEM_EXERC", "ORDEM_EXERC AS ordem_exerc"),
        ("DT_REFER", "DT_REFER AS dt_refer"),
        ("DT_INI_EXERC", "DT_INI_EXERC AS dt_ini"),
        ("DT_FIM_EXERC", "DT_FIM_EXERC AS dt_fim"),
        ("COLUNA_DF", "COLUNA_DF AS coluna_df"),
        ("CD_CONTA", "CD_CONTA AS cd_conta"),
        ("DS_CONTA", "DS_CONTA AS ds_conta"),
        ("VL_CONTA", "TRY_CAST(VL_CONTA AS DOUBLE) AS vl_conta"),
        ("ESCALA_MOEDA", "ESCALA_MOEDA AS escala"),
        ("MOEDA", "MOEDA AS moeda"),
        ("ST_CONTA_FIXA", "ST_CONTA_FIXA AS conta_fixa"),
        ("GRUPO_DFP", "GRUPO_DFP AS grupo"),
        ("VERSAO", "TRY_CAST(VERSAO AS INTEGER) AS versao"),
    ]

    def columns(src):
        return {c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}

    # views raw (SELECT * sobre o parquet) + views limpas (última VERSAO, colunas tidy)
    for name, _token, extra in FIN:
        src = f"read_parquet('{pq(name)}', hive_partitioning=true)"
        con.execute(f"CREATE OR REPLACE VIEW {name}_raw AS SELECT * FROM {src}")
        have = columns(src)
        sel = ", ".join(expr for col, expr in FIN_COLS if col in have)
        coluna_part = "COLUNA_DF, " if extra and "COLUNA_DF" in have else ""
        con.execute(f"""
            CREATE OR REPLACE VIEW {name} AS
            SELECT {sel}
            FROM {src}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY CNPJ_CIA, DT_REFER, tipo_dem, ORDEM_EXERC, {coluna_part} CD_CONTA
                ORDER BY TRY_CAST(VERSAO AS INTEGER) DESC) = 1
        """)

    # cadastro (metadados do documento) + empresas (dimensão de lookup)
    con.execute(f"""
        CREATE OR REPLACE VIEW cadastro AS
        SELECT CNPJ_CIA AS cnpj, CD_CVM AS cd_cvm, DENOM_CIA AS empresa, ano,
               DT_REFER AS dt_refer, CATEG_DOC AS categ_doc, ID_DOC AS id_doc,
               DT_RECEB AS dt_receb, LINK_DOC AS link_doc,
               TRY_CAST(VERSAO AS INTEGER) AS versao
        FROM read_parquet('{pq("cadastro")}', hive_partitioning=true)
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY CNPJ_CIA, DT_REFER ORDER BY TRY_CAST(VERSAO AS INTEGER) DESC) = 1
    """)
    con.execute("""
        CREATE OR REPLACE VIEW empresas AS
        SELECT cd_cvm, cnpj, arg_max(empresa, ano) AS empresa,
               MIN(ano) AS primeiro_ano, MAX(ano) AS ultimo_ano
        FROM cadastro GROUP BY cd_cvm, cnpj
    """)

    # composição do capital (nº de ações ON/PN e tesouraria)
    con.execute(f"""
        CREATE OR REPLACE VIEW composicao_capital AS
        SELECT CNPJ_CIA AS cnpj, DENOM_CIA AS empresa, ano, DT_REFER AS dt_refer,
               TRY_CAST(QT_ACAO_ORDIN_CAP_INTEGR AS DOUBLE) AS acoes_on,
               TRY_CAST(QT_ACAO_PREF_CAP_INTEGR  AS DOUBLE) AS acoes_pn,
               TRY_CAST(QT_ACAO_TOTAL_CAP_INTEGR AS DOUBLE) AS acoes_total,
               TRY_CAST(QT_ACAO_ORDIN_TESOURO AS DOUBLE) AS tesouro_on,
               TRY_CAST(QT_ACAO_PREF_TESOURO  AS DOUBLE) AS tesouro_pn,
               TRY_CAST(QT_ACAO_TOTAL_TESOURO AS DOUBLE) AS tesouro_total,
               TRY_CAST(VERSAO AS INTEGER) AS versao
        FROM read_parquet('{pq("composicao_capital")}', hive_partitioning=true)
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY CNPJ_CIA, DT_REFER ORDER BY TRY_CAST(VERSAO AS INTEGER) DESC) = 1
    """)

    # parecer do auditor (texto)
    con.execute(f"""
        CREATE OR REPLACE VIEW parecer AS
        SELECT CNPJ_CIA AS cnpj, DENOM_CIA AS empresa, ano, DT_REFER AS dt_refer,
               TP_RELAT_AUD AS tipo_relatorio, TP_PARECER_DECL AS tipo_parecer,
               NUM_ITEM_PARECER_DECL AS num_item, TXT_PARECER_DECL AS texto,
               TRY_CAST(VERSAO AS INTEGER) AS versao
        FROM read_parquet('{pq("parecer")}', hive_partitioning=true)
    """)


if __name__ == "__main__":
    main()
