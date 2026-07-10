#!/usr/bin/env python3
"""
build_fii.py — ETL do Informe Anual de FIIs da CVM.

Estrutura totalmente diferente das DFPs de ações: são ~13 tabelas do "Informe Anual FII"
(geral, complemento, ativos, distribuição de cotistas, prestadores, processos...), cada uma
com colunas próprias e chave comum (CNPJ_Fundo_Classe, Data_Referencia, Versao).

Lê "Dados CVM FII Anuais", grava Parquet particionado por ano em cvm_base/parquet_fii/ e
cria as views `fii_<tabela>` na MESMA base cvm_base/cvm.duckdb.

Idempotente. Uso:  cvm_base/.venv/bin/python cvm_base/build_fii.py
"""
import duckdb
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_base import q, opts, sanitize, CLEAN_DIR  # reusa helpers do ETL de ações

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
RAW = os.path.join(ROOT, "Dados CVM FII Anuais")
PARQUET = os.path.join(BASE, "parquet_fii")
DBFILE = os.path.join(BASE, "cvm.duckdb")

PREFIX = "inf_anual_fii_"
# ano derivado do nome do arquivo (inequívoco; Data_Referencia varia de dia/mês)
ANO = r"CAST(regexp_extract(filename, '_(\d{4})\.csv$', 1) AS INTEGER) AS ano"
# chave de dedup: mantém todas as linhas da última Versao por (fundo, data de referência)
KEY = ("CNPJ_Fundo_Classe", "Data_Referencia", "Versao")


def discover_tables():
    """Descobre os tipos de tabela a partir dos nomes de arquivo, em todos os anos."""
    tabs = set()
    for f in glob.glob(os.path.join(RAW, f"{PREFIX}*", f"{PREFIX}*_[0-9][0-9][0-9][0-9].csv")):
        base = os.path.basename(f)[len(PREFIX):-len("_YYYY.csv")]
        tabs.add(base)
    return sorted(tabs)


def files_for(table):
    return sorted(glob.glob(os.path.join(RAW, f"{PREFIX}*", f"{PREFIX}{table}_[0-9][0-9][0-9][0-9].csv")))


def write_parquet(con, table, files):
    out = os.path.join(PARQUET, table)
    for attempt, enc, fs in (("latin-1", "latin-1", files), ("utf-8-limpo", "utf-8", None)):
        if fs is None:
            fs = [sanitize(f) for f in files]
        select = (f"SELECT * EXCLUDE (filename), {ANO} "
                  f"FROM read_csv({q(fs)}, {opts(enc)}, filename=true)")
        try:
            shutil.rmtree(out, ignore_errors=True)
            con.execute(
                f"COPY ({select}) TO '{out}' "
                f"(FORMAT parquet, PARTITION_BY (ano), OVERWRITE_OR_IGNORE true, COMPRESSION zstd)"
            )
            n = con.execute(f"SELECT count(*) FROM read_parquet('{out}/**/*.parquet')").fetchone()[0]
            note = "" if attempt == "latin-1" else "  (higienizado)"
            print(f"  ✓ fii_{table:<28} {n:>10,} linhas{note}")
            return
        except duckdb.InvalidInputException as e:
            if "encoded" in str(e) and attempt == "latin-1":
                continue
            raise
    raise RuntimeError(f"Falha ao gravar fii_{table}")


def build_view(con, table):
    src = f"read_parquet('{os.path.join(PARQUET, table, '**', '*.parquet')}', hive_partitioning=true)"
    con.execute(f"CREATE OR REPLACE VIEW fii_{table}_raw AS SELECT * FROM {src}")
    have = {c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}
    if set(KEY) <= have:  # dedup: última Versao por (fundo, data_referencia)
        con.execute(f"""
            CREATE OR REPLACE VIEW fii_{table} AS
            SELECT * FROM {src}
            QUALIFY TRY_CAST(Versao AS INTEGER)
                    = MAX(TRY_CAST(Versao AS INTEGER)) OVER (
                        PARTITION BY CNPJ_Fundo_Classe, Data_Referencia)
        """)
    else:  # sem chave completa: expõe cru (só com ano)
        con.execute(f"CREATE OR REPLACE VIEW fii_{table} AS SELECT * FROM {src}")


def main():
    os.makedirs(PARQUET, exist_ok=True)
    con = duckdb.connect(DBFILE)
    con.execute("PRAGMA threads=4")
    print(f"Fonte: {RAW}\nSaída: {PARQUET}\n")

    tables = discover_tables()
    print(f"Tabelas do Informe Anual FII ({len(tables)}):")
    for t in tables:
        fs = files_for(t)
        if not fs:
            print(f"  ⚠ {t}: sem arquivos, pulando")
            continue
        write_parquet(con, t, fs)

    print("\nCriando views fii_* em cvm.duckdb ...")
    for t in tables:
        if files_for(t):
            build_view(con, t)

    con.close()
    shutil.rmtree(CLEAN_DIR, ignore_errors=True)
    print("\nConcluído. Views 'fii_*' adicionadas em:", DBFILE)


if __name__ == "__main__":
    main()
