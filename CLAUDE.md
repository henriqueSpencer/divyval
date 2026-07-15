# Investimentos — instruções para o Claude

Este diretório contém dados da CVM para análise fundamentalista/valuation de ações da B3.

## Regra principal
**NUNCA leia os CSVs brutos** em `Dados CVM -Acões -Anuais/` (são ~3,8 GB, ISO-8859-1, e
estouram o contexto). Toda consulta a dados financeiros deve passar pela base DuckDB:

```bash
duckdb "/Users/henriquespencer/Documents/Investimentos/cvm_base/cvm.duckdb" "<SQL>"
```

Traga apenas o resultado agregado da query — não faça dump de tabelas inteiras.

## O que existe
- `Dados CVM -Acões -Anuais/` — CSVs brutos, DFP de ações (2010–2026). **Fonte, não mexer.**
- `Dados CVM FII Anuais/` — CSVs brutos, Informe Anual de FIIs (2016–2025). **Fonte, não mexer.**
- `cvm_base/cvm.duckdb` — base consultável (views SQL de ações **e** FIIs). **Use esta.**
- `cvm_base/parquet/` (ações) e `cvm_base/parquet_fii/` (FIIs) — dados colunares por ano.
- `cvm_base/build_base.py` — ETL de **ações**. `cvm_base/build_fii.py` — ETL de **FIIs**.
  Rode ao baixar um ano novo: `cvm_base/.venv/bin/python cvm_base/build_base.py` (e `build_fii.py`).
- `cvm_base/DICIONARIO.md` (ações) e `cvm_base/DICIONARIO_FII.md` (FIIs) — **leia antes de montar
  queries**: views, colunas e plano de contas.

## Views principais
**Ações** (já filtradas para a última `VERSAO`): `dre`, `bpa`, `bpp`, `dfc_mi`, `dfc_md`,
`dmpl`, `dva`, `dra`. Apoio: `empresas` (lookup nome↔`cd_cvm`↔`cnpj`), `cadastro`,
`composicao_capital`, `parecer`.
**FIIs** (prefixo `fii_`, última `Versao` por fundo/data): `fii_geral` (identificação, ISIN,
segmento), `fii_complemento` (rentabilidade, dividendos, PL), `fii_distribuicao_cotistas`,
`fii_ativo_valor_contabil`, `fii_ativo_adquirido`, `fii_ativo_transacao`, `fii_processo`, etc.
Versões `*_raw` expõem o Parquet cru.

## Consulta por TICKER (de-para) — o jeito preferido
A base tem uma tabela **`tickers`** (ticker B3 → `cd_cvm`), gerada por `cvm_base/build_tickers.py`.
Quando o usuário passar um ticker (ex.: `PETR4`), **faça JOIN com `tickers`** em vez de adivinhar:
```bash
duckdb cvm_base/cvm.duckdb "SELECT t.ticker, d.ano, d.vl_conta/1000 AS lucro_milhoes
  FROM dre d JOIN tickers t USING(cd_cvm)
  WHERE t.ticker='PETR4' AND d.cd_conta='3.11' AND d.ordem_exerc='ÚLTIMO' AND d.tipo_dem='con'
  ORDER BY d.ano DESC"
```
Cobre ~60 ações líquidas. Se um ticker não estiver lá, adicione uma linha em `MAPA` no
`build_tickers.py` (padrão de nome + setor) e rode o script — ele resolve o `cd_cvm` na base.
Lembre: preço/cotação **não** vem daqui (é yfinance, no dashboard).

## Convenções que SEMPRE importam nas queries
- Identifique a empresa por **`cd_cvm`** (estável) ou pelo `ticker` via tabela `tickers`.
  Sem ticker no mapa? Busque em `empresas`:
  `duckdb .../cvm.duckdb "SELECT cd_cvm, empresa FROM empresas WHERE empresa ILIKE '%petrobras%'"`
- Filtre **`tipo_dem='con'`** (consolidado) para valuation, salvo quando quiser a controladora.
- Filtre **`ordem_exerc='ÚLTIMO'`** para série histórica sem duplicar (cada arquivo traz o ano
  corrente e o anterior).
- Atenção à **`escala`** (`'MIL'` ⇒ multiplique `vl_conta` por 1.000).
- Bancos/seguradoras usam **plano de contas diferente** — confira `ds_conta`, não presuma o `cd_conta`.

## Convenções das views FII
- Fundo identificado por **`CNPJ_Fundo_Classe`** (não há ticker na CVM; mas `fii_geral` tem
  `Codigo_ISIN`, útil para mapear ticker depois). Descubra o CNPJ por nome em `fii_geral`.
- Colunas mantêm o nome original da CVM (ex.: `Nome_Fundo_Classe`); DuckDB é case-insensitive.
- Tabelas 1:N (ativos, processos) já vêm filtradas para a última versão de cada informe.

## Dashboard (DIVYVAL) — `dashboard/`
Frontend em `dashboard/index.html` (SPA, HTML/CSS/JS à mão) + backend FastAPI em
`dashboard/backend/app.py` que serve os dados reais via **Yahoo Finance** (yfinance) e o próprio
frontend. Classificação curada em `dashboard/backend/stocks_meta.json`.
- **Persistência:** PostgreSQL no **Supabase** — **não há mais fallback SQLite**. O app **exige**
  a env var `DATABASE_URL` (connection string do *pooler de transação*, porta **6543**); sem ela não
  sobe. Usa `psycopg` 3; a camada `_Conn/_Cur/_Row` traduz placeholders `?`→`%s`. `init_db()` cria e
  semeia as tabelas no boot (379 ações do `universe.json`, `ON CONFLICT DO UPDATE`).
- **Rodar local:** exporte a `DATABASE_URL` antes —
  `cd dashboard/backend && DATABASE_URL='<pooler-6543>' ../../cvm_base/.venv/bin/python app.py`
  → http://127.0.0.1:8000/. O `cvm_base/.venv` já tem `psycopg`. A connection string (com senha) **não
  fica no repo** (é público); peça ao usuário ou pegue via MCP do Supabase.
- **Deploy:** no ar em **https://divyval.onrender.com** (Render free web service, **auto-deploy no push
  pra `main`**; repo **público** `henriqueSpencer/divyval`). Env vars no Render: `DATABASE_URL`,
  `APP_PASSWORD` (Basic Auth — só a senha é validada, o usuário é ignorado), `PYTHON_VERSION`.
  Free "dorme" após ~15 min sem uso (cold start).
- **Supabase via MCP:** o projeto Supabase `divyval` é consultável/administrável pelo MCP nesta máquina
  (`list_tables`/`execute_sql`/`apply_migration`). Dados do usuário (premissas, watchlist, config globais)
  vivem em `premissa_atual`/`premissa_hist`/`watchlist`/`config` — o `init_db` **não** os re-semeia,
  só `stocks` (do `universe.json`) e a `config` com `DO NOTHING`.
- Endpoints: `/api/stocks` (screener), `/api/history/{ticker}?range=5y` (fechamento diário p/ o gráfico).
  Cache em memória (cotações 15min, histórico 30min).
- **Universo completo (~378 ações da B3):** `build_universe.py` gera `universe.json` cruzando
  `b3_tickers.csv` (lista da brapi) → `cd_cvm` (match por nome) → fundamentos da CVM.
  **LPA = conta 3.99.01 "Lucro Básico por Ação · ON" reportada (auditada)** — NÃO usar
  `composicao_capital.acoes_total` (escala inconsistente entre empresas). Preço vem do Yahoo ao vivo.
  `stocks_meta.json` sobrepõe só perfil/governança/tags das ~12 principais.
- **Classificação B3 (Setor › Subsetor › Segmento):** vem do **statusinvest** (endpoint
  `advancedsearchresultpaginated`, campos `sectorname/subsectorname/segmentname`) — é a taxonomia
  oficial de 3 níveis. Limpar artefatos de pontuação (`clean_b3`). NÃO usar `SETOR_ATIV` da CVM
  (taxonomia diferente). Controle vem do cadastro CVM (`CONTROLE_ACIONARIO`); Tamanho do market cap;
  LPA da CVM (3.99.01) com fallback do statusinvest. Ainda faltam Perfil (subjetivo) e Governança
  (segmento de listagem Novo Mercado) para o universo — só nos 12 curados.
- Preços da B3 usam sufixo `.SA`; símbolos que diferem no Yahoo vão ajustados no meta (ex.: Copel = CPLE3).
- O frontend cai nos dados de exemplo embutidos se o backend estiver fora.

## Limitação importante
A CVM **não fornece ticker (ex.: PETR4/HGLG11) nem cotação/preço**. Múltiplos de mercado
(P/L, P/VP, DY, EV/EBITDA) precisam de preços de fonte externa (ex.: Yahoo Finance) — etapa
dedicada ainda não integrada. Helpers de valuation prontos também são etapa futura.
