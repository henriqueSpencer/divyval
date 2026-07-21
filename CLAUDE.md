# DIVYVAL — dashboard de valuation (instruções para o Claude)

SPA de screener/valuation de ações da B3. Frontend em `index.html` (HTML/CSS/JS à mão, sem
build). O backend virou **Cloudflare Pages Functions** (edge serverless, JS) em `functions/` —
substituíram o antigo FastAPI. Servem as rotas `/api/*`; o próprio Pages serve os estáticos.
Classificação curada em `backend/stocks_meta.json`.

> O repositório git é a pasta-mãe `~/Documents/Investimentos` (remote `henriqueSpencer/divyval`);
> o Cloudflare Pages usa **root directory `dashboard`**. O `CLAUDE.md` da raiz (base CVM/DuckDB)
> continua valendo: **nunca leia os CSVs brutos da CVM** — consulte `cvm_base/cvm.duckdb`.
> O **FastAPI legado** (`backend/app.py`) fica no repo como referência mas **não é mais deployado**.

## Arquitetura (Cloudflare Pages + Functions)
```
dashboard/                    ← Pages "root directory"
  index.html, ddm.html        ← estáticos (servidos grátis, ilimitado)
  wrangler.toml               ← config do Pages (buildless)
  functions/                  ← rotas /api/* (edge)
    _middleware.js            ← Basic Auth (APP_PASSWORD) + Cache-Control no-cache no HTML
    _lib/http.js              ← helper de resposta JSON
    _lib/db.js                ← PostgREST (Supabase) via fetch + buildStocks() (porta do app.py)
    _lib/quotes.js            ← preços (brapi list) + histórico (Yahoo chart), com cache de edge
    api/stocks.js             ← GET screener / POST add
    api/stocks/[ticker].js    ← PATCH editar / DELETE remover
    api/history/[ticker].js   ← GET série do gráfico
    api/config.js             ← GET/POST padrões globais
    api/premissas/[ticker].js ← GET / POST (hist + upsert atual)
    api/watchlist.js          ← GET;  api/watchlist/[ticker].js ← POST/DELETE
  backend/                    ← FastAPI legado (NÃO deployado)
```
As Functions são **buildless** (`fetch` puro, zero npm). A lógica de merge/CRUD é porta direta do
`backend/app.py` — se precisar entender uma regra, o Python é a referência canônica.

## Rodar local
```bash
cd dashboard && npx wrangler pages dev .   # → http://localhost:8788/
```
Segredos locais em `dashboard/.dev.vars` (gitignored): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
(no dev pode ser a **anon** key — RLS off), `APP_PASSWORD` (vazio = app aberto no dev).
Atenção: aponta pro Supabase de **produção**.

## Persistência
PostgreSQL no **Supabase**, acessado via **PostgREST REST** (`fetch`, sem driver) em `_lib/db.js`.
A chave (`SUPABASE_SERVICE_KEY`) fica **só na Function** (env), nunca no client — por isso RLS off
segue seguro (a anon key não é exposta). Não há mais `init_db`/seed no boot: a base já está semeada
(379 ações); re-semear é tarefa **offline** (`build_universe.py` + seed script), só ao baixar um ano
novo da CVM. O projeto Supabase `divyval` é administrável pelo **MCP** (`list_tables` /
`execute_sql` / `apply_migration`).

Dados do usuário vivem em `premissa_atual` / `premissa_hist` / `watchlist` / `config`.
`buildStocks()` (`_lib/db.js`) monta o screener: fundamentos de `stocks` + override da premissa
salva + defaults globais (Ke/ROE_t/payout_t/fade da `config`) + preço ao vivo. **Preserva o que o
usuário edita** (`modelo`, classificação, `tags`) porque nada é re-semeado em runtime.

## Preços e histórico
- **Preço (screener):** `brapi.dev/api/quote/list` — **1 request, sem token, ~todas as ações da B3**
  (campo `close`), com CORS. Cobre ~362/379 (17 ilíquidos ficam sem preço — o front trata como
  `indisponível`). Cache de **15 min** no edge (`caches.default`). Sem cron, sem KV.
- **Histórico (gráfico):** Yahoo chart `v8/finance/chart/{TICKER}.SA` per-ticker, sob demanda,
  cache de **30 min**. Se o Yahoo falhar (ex.: bloqueio de IP), o front mostra série vazia com `erro`
  — degradação graciosa, não quebra a página.

## Deploy
**Cloudflare Pages** (free, **~zero cold start**), **auto-deploy no push pra `main`**, repo público
`henriqueSpencer/divyval`, **root directory `dashboard`**, sem build command. Env vars no painel do
Pages: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (a **service_role** em prod), `APP_PASSWORD`
(Basic Auth — só a senha é validada, o usuário é ignorado). `_middleware.js` protege tudo (inclusive
o HTML) e mantém `Cache-Control: no-cache` no HTML pra não servir JS/estado velhos após um deploy.
> Migrado do **Render** (que dormia após ~15 min → cold start) em jul/2026. O `render.yaml` e o
> `backend/` ficam no repo mas o serviço do Render pode ser desligado após validar o Pages.

## Modelos de valuation (escolhíveis por ação — campo `stocks.modelo`)
Todo o cálculo é no **frontend** (`index.html`), despachado por `fairResult(s)`:
- `DDM · 2 est.` (`computeDDM`) — dividendos descontados ao Ke, fade de ROE/payout + perpetuidade
  de Gordon (o padrão).
- `Owner Earnings DCF` (`computeOE`) — método do Buffett: lucro do dono (≈LPA) a VP por N anos +
  perpetuidade.
- `Regra nº1 · Town` (`computeR1`) — LPA×(P/L futuro) descontado ao retorno **+ dividendos
  recebidos** (payout); saída = preço justo (sticker) e **preço-teto de compra** (sticker×(1−margem)).
- `Sem valuation` — ações com prejuízo crônico: sem preço justo/margem (`fair` null). Cuidado:
  `brl` trata null/NaN como `—`; há guarda na célula de justo dos filhos no screener.

**Ke (= retorno exigido) e horizonte (= anos de fade) são compartilhados** entre os modelos: usam o
padrão global (Configurações) via checkbox "padrão". Premissas por ação em `premissa_atual` /
`premissa_hist`; o R1 acrescentou as colunas **`fut_pe`** (P/L futuro) e **`mos`** (margem);
payout→`payout_i`, retorno→`ke`, horizonte→`fade`. Screener e histórico recalculam por modelo.

**O modelo é escolhido por pré-visualização:** o seletor no detalhe só troca a visualização
(`previewModel`); o modelo só grava na ação (`stocks.modelo`, via `commitModel`→PATCH) ao clicar em
**"Salvar premissas"**. Trocar o seletor não altera screener/Monitoradas até salvar.

## Universo de ações
`backend/build_universe.py` gera `universe.json` (~378 ações) cruzando `b3_tickers.csv` (lista da
brapi) → `cd_cvm` (match por nome) → fundamentos da CVM.
- **LPA = conta 3.99.01 "Lucro Básico por Ação · ON" reportada (auditada)** — NÃO usar
  `composicao_capital.acoes_total` (escala inconsistente entre empresas). Preço vem do Yahoo ao vivo.
- `stocks_meta.json` sobrepõe só perfil/governança/tags das ~12 principais.
- **Classificação B3 (Setor › Subsetor › Segmento)** vem do **statusinvest** (endpoint
  `advancedsearchresultpaginated`, campos `sectorname/subsectorname/segmentname`) — taxonomia oficial
  de 3 níveis; limpar artefatos de pontuação (`clean_b3`). NÃO usar `SETOR_ATIV` da CVM (taxonomia
  diferente). Controle vem do cadastro CVM (`CONTROLE_ACIONARIO`); Tamanho do market cap.
- Faltam Perfil (subjetivo) e Governança (segmento de listagem) para o universo — só nos 12 curados.
- Preços da B3 usam sufixo `.SA`; símbolos que diferem no Yahoo vão ajustados no meta (ex.: Copel =
  CPLE3).

## Endpoints e outros detalhes
- `/api/stocks` (screener), `/api/history/{ticker}?range=5y` (fechamento diário p/ o gráfico),
  `/api/config`, `/api/premissas/{ticker}`, `/api/watchlist[/{ticker}]`, `/api/stocks/{ticker}`
  (PATCH/DELETE). Cache no edge (preços 15 min, histórico 30 min).
- O gráfico de preços tem **seleção por clique-e-arrasto** (mostra a variação % entre dois pontos).
- O frontend cai nos dados de exemplo embutidos se as Functions estiverem fora. O `bootstrap`
  faz só um retry curto (não há mais cold start pra cobrir).

## Git
Conta **henriqueSpencer** (`gh auth switch --user henriqueSpencer`), autor
`Henrique Spencer <henriquespencer11@gmail.com>`. Commits/PRs **sem nenhuma menção a IA/Claude/
Anthropic** (nada de `Co-Authored-By` nem "Generated with"). Push em `main` = deploy.
