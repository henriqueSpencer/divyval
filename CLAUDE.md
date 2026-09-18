# DIVYVAL — dashboard de valuation (instruções para o Claude)

SPA de screener/valuation de ações da B3. Frontend em `index.html` (HTML/CSS/JS à mão, sem
build). O backend virou **Cloudflare Pages Functions** (edge serverless, JS) em `functions/` —
substituíram o antigo FastAPI. Servem as rotas `/api/*`; o próprio Pages serve os estáticos.
Classificação curada em `backend/stocks_meta.json`.

> **Esta pasta É a raiz do repositório git** (remote `henriqueSpencer/divyval`); o Cloudflare Pages
> serve a partir da raiz. A base CVM/DuckDB e o `CLAUDE.md` da raiz **não estão neste repo** — ficam
> em `~/Documents/Investimentos` (fora do git). Ao consultar dados da CVM lá: **nunca leia os CSVs
> brutos** — use `cvm_base/cvm.duckdb`. O **FastAPI legado** (`backend/app.py`) fica no repo como
> referência mas **não é mais deployado**.

## FIIs — valuation (EM PROD desde set/2026)
Feature **integrada ao `index.html`** (mesclada da branch `fii-valuation` em 18/set/2026): a navegação continua com os 4 itens (Monitoradas · Carteira · Screener ·
Config) e cada tela ganhou um **toggle "Ações | FIIs"** (`assetToggleHtml`, classe `.asset-toggle`) no
topo. Rotas: `#/screener/fiis`, `#/monitoradas/fiis`, `#/carteira/fiis`, `#/fii/{ticker}` (as rotas de
ações ficaram como estavam). Views próprias: `#view-fiis` (screener/monitoradas, `renderFiiView`),
`#view-fii-detail` (`openFii`/`drawFiiDetail`), `#view-fii-carteira` (`renderFiiCart`); `show()` conhece
as três. `fiis.html` virou só um **redirect** p/ `/#/screener/fiis`. Todo o código FII tem prefixo
`fii`/`FII_` (estado `FIIS`/`FDIV`/`FII_PREM`/`FII_WATCH`/`FII_CART`/`FII_CFG`, rascunho `FDRAFT`,
`curFii`, `fiiScope`) e ids próprios no DOM (`fiiChartWrap`, `fiiHeroGauge`, `fii-impl-*`, `fpv_*`,
gráfico com `fiiSvg`/`fiiHit`/…) para **não colidir** com o detalhe das ações (que fica no DOM oculto).
Reusa do index: `$`, `dec`, `brl`, `brl0`, `pctv`, `globalCfg`, `show`, `setActiveNav`, `closePop` e todo o
CSS (hero/verdict/medidor `.hg-*`, `.mode-toggle`, `.field`/slider, `.impl-row`, `.step`/`.formula`/`.proj`,
`.chart-wrap`/`.periods`); CSS específico de FII (`.ftbl`, `.fstat`, `.srcpill`, `.dvchart`, `.segbar`,
`.fmos`, `.fest`, `.fpos/.fneg`) fica num bloco próprio no `<style>`. `/api/fiis` carrega **sob demanda**
(`ensureFiis`, na 1ª tela de FII), não no boot das ações.
- **Config compartilhada** (pedido do usuário): `fiiG()` lê **Ke = `globalCfg.ke`** e **horizonte
  (anos até a venda) = `globalCfg.fade`** — mudar na Config global recalcula FIIs (`rerenderFiiViews`,
  chamada no `saveConfig`). O card **"Premissas de FIIs"** na Config (`renderFiiConfig`/`saveFiiConfig`)
  guarda só o específico: modelo padrão, g do DPU, cresc. do VP/cota, P/VP de saída — em
  **localStorage `fii.cfg.v1`** (preview; ao aprovar, viram chaves k/v na tabela `config`, sem schema).
- **Dados**: **universo = todos os FIIs com cotação na brapi** (~328), gerado por
  **`backend/build_fii_universe.py` → `functions/_lib/fii_data.js`** (`FII_UNIVERSE` + `FII_VP`; rodar
  mensalmente). `FII_CURATED` em `_lib/fii.js` (34 líquidos com nome/segmento curados e **ISIN fixado**)
  sobrepõe o gerado. **VP/cota (p/ P/VP)** vem do **Informe MENSAL de FII da CVM** (`Valor_Patrimonial_
  Cotas`, oficial, mês a mês; o informe ANUAL da base DuckDB não serve). Casamento ticker↔fundo: ISIN
  fixado ou candidatos por raiz `BR+4 letras` → escolhe a linha do mês mais recente com **P/VP plausível
  (0,4–1,8) contra o preço real**, desempate por maior PL (resolve classes múltiplas, ex. XPML 110 vs
  22.548, e colisão de raiz, ex. TRXF). Set/2026: 269/328 com VP; os demais entram sem P/VP (modelo sai
  pelo DY exigido). Segmento: curado nos 34; nos outros é **classificado pela composição da carteira**
  (arquivo `ativo_passivo` do informe mensal: CRI/LCI/LIG ⇒ Papel; cotas de FII ⇒ Fundo de fundos;
  direitos sobre imóveis ⇒ tijolo, com venda/construção/terrenos ⇒ Desenvolvimento; mistura ⇒ Híbrido),
  refinando o tipo de tijolo pelo `Segmento_Atuacao` quando específico ou por palavras do nome (`classify()`
  no script; **nome explícito de tijolo vence a composição**, pois muitos detêm imóveis via FIIs
  subsidiários). Resultado set/2026: só 38/328 ficam `—` (sem identidade na CVM); o `Segmento_Atuacao`
  cru era "Multicategoria/Outros" p/ 207. **DPU/DY real** vem do **Yahoo** (events=div,
  soma 12m, cache 6h por ticker): `/api/fiis` responde rápido (DPU **só do cache**, `cacheOnly`) e o front
  completa **progressivamente** via **`/api/fii-dpu?t=…`** (lotes de 24, 8 em paralelo; monitoradas e
  carteira primeiro; ~35 s p/ cobrir tudo a frio, depois cache). Screener e detalhe usam o **mesmo cache**
  → mesmos números (antes o screener usava estimativa e o detalhe o real → "mudava" ao abrir, ex. TRXF).
  Sem DPU real, estimativa por DY típico do segmento (`dpu_src:"estimado"`, pill). **P/VP de entrada** no
  detalhe é **automático** (preço ÷ VP/cota CVM, pill `CVM aaaa-mm`); digitar sobrescreve (pill `manual`),
  apagar volta. Histórico do gráfico: `/api/history/{ticker}`.
- **Persistência de FII = Supabase, igual às ações** (migrado do localStorage em 18/set/2026, antes de ir
  a prod): tabelas **`fii_premissa`** (ticker PK; só overrides — null = padrão/auto), **`fii_premissa_hist`**
  (snapshots de "Salvar": `date, prem jsonb, fair, price, modelo`; 20 por fundo na leitura),
  **`fii_watchlist`**, **`fii_carteira`** (quantidade, preco_medio) — todas com RLS ligado sem políticas.
  Padrões de FII (`fii_g/fii_gvp/fii_pvp/fii_modelo`, este 0=r1/1=dy) são chaves k/v na **`config`**,
  expostas por `api/config.js` junto com o resto (`saveConfig` faz spread pra preservá-las). Endpoints:
  `GET /api/fii-state` (tudo numa chamada: prem/watch/cart/hist, carregado com o universo em `ensureFiis`),
  `POST|DELETE /api/fii-premissa/{tk}` (POST grava overrides + snapshot), `POST|DELETE /api/fii-watchlist/{tk}`,
  `POST|DELETE /api/fii-carteira/{tk}`. Front é otimista (atualiza e depois chama a API; toast se falhar).
- **Dois modelos** (seletor no detalhe; `fiiPrem().modelo`, default do card FII): **`r1` Regra nº1 · FII**
  (`fiiValueAt`) = VP dos proventos + saída no ano N (por P/VP se houver P/VP de entrada, senão por DY
  exigido); **`dy` DY-alvo · perpetuidade** (`gordonMonthly`), exige Ke>g. **Proventos MENSAIS**
  (`divPVmonthly`): 12N parcelas = DPU_mês crescendo `g`, descontadas ao **Ke mensal** `(1+ke)^(1/12)−1`
  (soma fechada, conferida vs. loop mês a mês; ~3% acima do anual). A premissa **DPU é mensal**
  (`dpuM`; o cálculo usa `dpu=dpuM×12`). **TIR implícita** por bissecção com o mesmo fluxo mensal.
  Implicações mostram **DY corrente** (12×DPU_mês÷preço, soma) e **DY efetivo reinvestido**
  ((1+DY_mês)¹²−1) — leituras distintas, ambas corretas. Passo 2 do passo a passo é **mês a mês** (1º ano
  detalhado + resto agregado, coluna do fator de desconto). Math conferida: r1 15/15, mensal 10/10,
  dy 7/7; integração 16/16 (shim de DOM: ações intactas + rotas FII).
- **Backend read-only** (sem banco): `functions/_lib/fii.js`, `functions/api/fiis.js`, `functions/api/fii/[ticker].js`.
  Yahoo dá 429 de curl direto local, mas **funciona via Function** (confirmado local e no edge).
- **Premissas ligadas à Config no detalhe do FII** (checkbox **"padrão (x)"**, igual às ações;
  `FII_LINKED` = ke, N, g, gvp, pvp): marcado = sem override (segue Config, slider travado `.locked`);
  desmarcar cria override = global e destrava; remarcar apaga (`FDRAFT[k]=null`). DPU e P/VP de
  entrada não têm global. **Histórico de premissas** (`FII_HIST`, localStorage `fii.hist.v1`, 20 por
  fundo): cada "Salvar" grava `{date, prem, fair, price, modelo}`; card no detalhe com **Aplicar**
  (vira rascunho; chaves ausentes voltam ao padrão). **Sem margem-input nem preço-teto** em FII
  (removidos junto com o das ações); `msafe` segue como leitura calculada.

## Arquitetura (Cloudflare Pages + Functions)
```
./                            ← raiz do repo = Pages "root directory"
  index.html, ddm.html        ← estáticos (servidos grátis, ilimitado)
  login.html                  ← tela de senha (única rota pública além de /api/login e ícones)
  wrangler.toml               ← config do Pages (buildless)
  functions/                  ← rotas /api/* (edge)
    _middleware.js            ← auth (cookie de sessão assinado; Basic como fallback) + no-cache no HTML
    _lib/http.js              ← helper de resposta JSON
    _lib/session.js           ← token HMAC do cookie `dv_session` (emitir/verificar/renovar)
    api/login.js, api/logout.js ← POST: cria / apaga o cookie de sessão (login.html é a tela)
    _lib/db.js                ← PostgREST (Supabase) via fetch + buildStocks() (porta do app.py)
    _lib/quotes.js            ← preços (brapi list) + histórico (Yahoo chart), com cache de edge
    _lib/macro.js             ← Selic + IPCA-12m do Banco Central (SGS), cache de edge 12h
    api/stocks.js             ← GET screener / POST add
    api/macro.js              ← GET Selic/IPCA-12m (BCB)
    api/stocks/[ticker].js    ← PATCH editar / DELETE remover
    api/history/[ticker].js   ← GET série do gráfico
    api/config.js             ← GET/POST padrões globais
    api/premissas/[ticker].js ← GET / POST (hist + upsert atual)
    api/watchlist.js          ← GET;  api/watchlist/[ticker].js ← POST/DELETE
    api/carteira.js           ← GET;  api/carteira/[ticker].js ← POST(upsert qtd+PM)/DELETE
    _lib/fii.js, _lib/fii_data.js ← FIIs: curadoria+ISIN, universo gerado (brapi∩CVM) e VP/cota
    api/fiis.js, api/fii/[ticker].js, api/fii-dpu.js ← screener FII, detalhe, DPU em lote (Yahoo)
    api/fii-state.js, api/fii-premissa|fii-watchlist|fii-carteira/[ticker].js ← estado do usuário (FII)
  backend/build_fii_universe.py ← gera _lib/fii_data.js (rodar mensalmente)
  backend/                    ← FastAPI legado (NÃO deployado)
```
As Functions são **buildless** (`fetch` puro, zero npm). A lógica de merge/CRUD é porta direta do
`backend/app.py` — se precisar entender uma regra, o Python é a referência canônica.

## Rodar local
```bash
npx wrangler pages dev .   # na raiz do repo → http://localhost:8788/
```
Segredos locais em `dashboard/.dev.vars` (gitignored): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
(**precisa ser a service key** `sb_secret_…`, porque o **RLS está ligado** — a anon/publishable é
bloqueada), `APP_PASSWORD` (vazio = app aberto no dev).
Atenção: aponta pro Supabase de **produção**.

## Persistência
PostgreSQL no **Supabase**, acessado via **PostgREST REST** (`fetch`, sem driver) em `_lib/db.js`.
A chave (`SUPABASE_SERVICE_KEY` = **service key** `sb_secret_…`, que **ignora o RLS**) fica **só na
Function** (env), nunca no client. **RLS está LIGADO** em todas as tabelas, **sem políticas** →
anon/publishable ficam totalmente bloqueadas; só a service key (server-side) acessa. (Ligado em
jul/2026 após o advisor do Supabase; o `sb_secret` deve ir como `apikey`+`Bearer`, ambos funcionam.)
Não há mais `init_db`/seed no boot: a base já está semeada
(379 ações); re-semear é tarefa **offline** (`build_universe.py` + seed script), só ao baixar um ano
novo da CVM. O projeto Supabase `divyval` é administrável pelo **MCP** (`list_tables` /
`execute_sql` / `apply_migration`).

Dados do usuário vivem em `premissa_atual` / `premissa_hist` / `watchlist` / `carteira` / `config`
(ações) e `fii_premissa` / `fii_premissa_hist` / `fii_watchlist` / `fii_carteira` (FIIs; ver seção FIIs).
A tabela **`carteira`** (`ticker` PK, `quantidade`, `preco_medio`, `updated_at`; RLS ligado) guarda as
posições do usuário — uma linha por ativo, upsert por ticker.
`buildStocks()` (`_lib/db.js`) monta o screener: fundamentos de `stocks` + override da premissa
salva + defaults globais (Ke/ROE_t/payout_t/fade da `config`) + preço ao vivo. **Preserva o que o
usuário edita** (`modelo`, classificação, `tags`) porque nada é re-semeado em runtime.

## Preços e histórico
- **Preço (screener):** `brapi.dev/api/quote/list` — **1 request, sem token, ~todas as ações da B3**
  (campo `close`), com CORS. Cache de **15 min** no edge (`caches.default`). Sem cron, sem KV.
- **Fallback de preço (ilíquidas):** a brapi cobre ~360/379 — ~19 classes ilíquidas (HBTS5, CGAS3,
  USIM6, CEGR3, COCE3, BRSR5…) ficam de fora. `getMissingPrices` (`_lib/quotes.js`, chamada em
  `api/stocks.js`) busca essas no **Yahoo chart** (per-ticker, em lotes de 6, cache 15 min) → hoje
  **379/379 com cotação** (o Yahoo do edge da CF não é bloqueado; confirmado). O que o Yahoo também
  não tiver fica `indisponível` (nunca inventa valor).
- **Histórico (gráfico):** Yahoo chart `v8/finance/chart/{TICKER}.SA` per-ticker, sob demanda,
  cache de **30 min**. Se o Yahoo falhar (ex.: bloqueio de IP), o front mostra série vazia com `erro`
  — degradação graciosa, não quebra a página.

## Deploy
No ar em **https://divyval.pages.dev** (Cloudflare Pages, free, **~zero cold start**; senha `divyval2026`).
Projeto `divyval`, account `b7345f757a0fc365da5dcdea7a033db5` (`wrangler` já logado como
`henriquespencer11@gmail.com`). Deploy é **manual, direct-upload** (NÃO tem git-integration ainda →
push no GitHub **não** redeploya sozinho):
```bash
npx wrangler pages deploy . --project-name=divyval --branch=main --commit-dirty=true   # na raiz do repo
```
> **Trocar um secret exige redeploy** pra a Function pegar (um deploy que correu antes do secret
> propagar já serviu dado errado). Secrets: `wrangler pages secret put NOME --project-name=divyval`.

Secrets do projeto: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (**service key `sb_secret_…`**),
`APP_PASSWORD` (senha única do app). `_middleware.js` protege tudo (inclusive o HTML) e mantém
`Cache-Control: no-cache` no HTML.

## Autenticação (sessão em cookie, set/2026)
Antes era **HTTP Basic Auth** puro: o browser guardava a senha só na memória da aba e descartava
quando queria (fechar o app no celular, reiniciar o Safari, PWA na tela inicial) → 401 +
`WWW-Authenticate` → diálogo nativo de novo. Era isso que parecia "ficar pedindo para relogar".
Agora (`_lib/session.js` + `_middleware.js`):
- **`/login.html`** (senha) → `POST /api/login` → cookie **`dv_session`** = `v1.<exp_ms>.<HMAC>`,
  **HttpOnly, SameSite=Lax, Secure (só em https), Max-Age 180 dias**. A chave HMAC deriva de
  `APP_PASSWORD` (SHA-256) — **trocar a senha invalida todas as sessões** (é a forma de "deslogar
  todo mundo"). Nenhum secret novo.
- **Renovação deslizante:** o middleware reemite o cookie em qualquer request quando faltam menos
  de 90 dias — quem usa o app nunca cai. Comparações são em tempo constante (`safeEqual`).
- **Sem credencial:** `/api/*` → **401 JSON sem `WWW-Authenticate`** (o browser não abre o diálogo
  nativo); páginas → **303 p/ `/login`**; `/login` já logado → 303 p/ `/`. Rotas públicas: `/login` **e**
  `/login.html` (o Pages faz 308 de `.html` → clean URL em prod; sem as duas dava loop), `/api/login`, favicons.
- **`Authorization: Basic`** segue aceito (curl/scripts). `APP_PASSWORD` vazio = app aberto (dev).
- No front (`index.html`), um wrapper de `window.fetch` manda pro login se qualquer `/api/*` devolver
  401 (sessão limpa/expirada); `POST /api/logout` limpa o cookie (botão "Sair" no card **Sessão** da
  aba Config). Não há Supabase Auth nem token em localStorage: é uso pessoal com senha única, e o
  cookie HttpOnly no servidor (Pages Function) é mais simples e mais seguro que token no client.
- Testar local com senha: `npx wrangler pages dev . --binding APP_PASSWORD=teste`.
> Migrado do **Render** (que dormia → cold start) em jul/2026; o Render segue dormindo (inofensivo,
> desligar exige painel/API do Render). `render.yaml` e `backend/` ficam no repo como legado.

## Modelos de valuation (escolhíveis por ação — campo `stocks.modelo`)
Todo o cálculo é no **frontend** (`index.html`), despachado por `fairResult(s)`:
- `DDM · 2 est.` (`computeDDM`) — dividendos descontados ao Ke, fade de ROE/payout + perpetuidade
  de Gordon (o padrão).
- `Owner Earnings DCF` (`computeOE`) — método do Buffett: lucro do dono (≈LPA) a VP por N anos +
  perpetuidade.
- `Regra nº1 · Town` (`computeR1`) — LPA×(P/L futuro) descontado ao retorno **+ dividendos
  recebidos** (payout); saída = preço justo (sticker). **A margem de segurança como INPUT foi removida
  (set/2026, pedido do usuário)** — não há mais slider `mos` nem "preço-teto de compra" (era só
  `sticker×(1−mos)`, trivial de fazer de cabeça e mais um campo pra preencher). `computeR1` ainda
  aceita `mos` (passado sempre `0`); a coluna `mos` da `premissa_atual` fica no banco, ignorada.
  Tem os **mesmos dois modos de crescimento do DDM** (jul/2026): *Via ROE* (`g = ROE × (1 − payout)`,
  slider `r1-roe`) ou *Crescimento direto* (`r1-g`) — toggle `#r1GrowthToggle`, campos `.roe-only`/
  `.g-only` dentro de `#r1PremCard` (`applyR1Mode`, chamada por `applyMode`). O g efetivo sai de
  **`r1G(s)`** (usado por `fairResult`, `irrParams` e `histResult`) — `oeG(s)` segue servindo só ao OE.
  O crescimento é **constante** (é o método do Town, sem fade); o passo a passo mostra de onde veio
  o g (`#r1-f-gform`) e "Implicações" traz a linha "Crescimento do LPA".
  > **`growth_mode` é premissa da ação, compartilhada** entre DDM e R1 (como Ke e horizonte): o
  > toggle de um reflete no outro e ambos gravam a mesma coluna. Não há schema novo — o R1 passou a
  > salvar `roe_i` junto. Universo semeado vem com `growth_mode='g'`, então as 72 ações em R1 hoje
  > não mudaram de preço justo (conferido: 0 diferenças nas 379).
- `Sem valuation` — ações com prejuízo crônico: sem preço justo/margem (`fair` null). Cuidado:
  `brl` trata null/NaN como `—`; há guarda na célula de justo dos filhos no screener.

**Ke (= retorno exigido) e horizonte (= anos de fade) são compartilhados** entre os modelos: usam o
padrão global (Configurações) via checkbox "padrão". Premissas por ação em `premissa_atual` /
`premissa_hist`; o R1 acrescentou a coluna **`fut_pe`** (P/L futuro) — e `mos`, hoje **sem uso**;
payout→`payout_i`, retorno→`ke`, horizonte→`fade`. Screener e histórico recalculam por modelo.

**Ke global — dois modos de entrada** (Configurações, jul/2026): *Nominal* (slider, como antes) ou
*IPCA + NTN-B*, que compõe **Ke = (1+IPCA)×(1+taxa real do título)×(1+prêmio de risco) − 1** (Fisher;
o prêmio é opcional, default 0). O nominal equivalente aparece no próprio campo. **O resto do app
segue lendo só `globalCfg.ke`** — o modo apenas registra como o número foi obtido; as chaves
`ipca_global`/`ntnb_global`/`premio_global`/`ke_mode_global` (0/1) vivem na tabela `config` e são
expostas por `api/config.js` (`ke_mode` vai como string `"nom"`/`"real"` na API). Motivo de usar o
nominal: LPA e dividendos projetados nos modelos são nominais.

**Referência de mercado do BCB (set/2026) — no modo IPCA + NTN-B.** Uma Function `/api/macro`
(`_lib/macro.js`) busca no **Banco Central (API do SGS, `api.bcb.gov.br`, grátis, sem token)** a
**Selic meta** (série 432) e o **IPCA acumulado 12 meses** (série 13522), as duas em paralelo,
tolerando uma falhar, com **cache de 12h no edge**. Devolve `{selic, ipca12m, selic_data, ipca_data,
fonte:"BCB"}` (valores em % — ex.: `selic:14`, `ipca12m:4.22`). Degrada gracioso: BCB fora ⇒ nulos.
No front (`index.html`): `loadMacro()` cacheia 1 dia no **localStorage** (chave `divyval.macro.v1`,
por `macroDay()` UTC; offline cai no último conhecido) e o bloco `#cfgKeReal` ganhou a **strip
"Referência de mercado · BCB"** (`#mktRef`: Selic + IPCA-12m + mês de ref.) e um **toggle auto ⇄
manual no campo IPCA** (`#ipcaAuto`, `ipcaAutoOn()`/`applyIpcaAuto()`; flag em `divyval.ipcaAuto.v1`,
**default auto**). Em *auto* o IPCA acompanha o BCB (preenche `#cfgIpca` e salva se mudou — o
set é programático, **não** dispara `input`); **digitar** no campo vira manual sozinho; clicar
"auto" religa e repõe o BCB. Nada de schema novo — o valor continua indo pra `ipca_global`; a
Selic é só **referência** (não entra em cálculo). A UI só aparece no modo IPCA + NTN-B.

**Upside × Margem de segurança (jul/2026) — duas colunas, duas bases.** A distância preço↔justo
aparece nas duas leituras, com nomes agora distintos:
- **`Upside`** (coluna `margin`, `marginOf`) = `(justo − preço)/preço` — "quanto pode subir".
  É a coluna histórica (só o **rótulo** mudou de "Margem" para "Upside"; a chave `margin` segue a
  mesma, então filtros/ordenação/colunas ocultas salvos no localStorage não quebram). Mantém o
  **mini medidor** (`.mos-bar`) — é a assinatura visual.
- **`Margem seg.`** (coluna `msafe`, `mosOf`/`mosFromFair`) = `(justo − preço)/justo` — definição
  clássica de Graham, **teto de +100%**. Número puro, sem barra. `justo ≤ 0` ⇒ `—`. É uma
  **leitura calculada** (não pede input) — foi mantida quando o slider de margem saiu.
- Relação: `MS = upside/(1+upside)`. Ordenar por uma dá a mesma ordem da outra (transformação
  monotônica) — o que muda é a **leitura** (upside +260% = comprar a 28% do valor).
- No detalhe as duas linhas convivem em "Implicações" (`impl-margin`/`impl-msafe` e equivalentes
  em OE/R1) e o selo do hero passou a dizer "de upside".
- Cabeçalhos têm `title` (campo `hint` em `COLUMNS`) explicando cada fórmula.

**TIR implícita (jul/2026) — o mesmo modelo rodado ao contrário.** Em vez de descontar ao Ke e
comparar com o preço, resolve **`valor(r) = preço de mercado`**; esse `r` é o retorno anual embutido
no preço de hoje. Como `valor(r)` é monotonicamente decrescente (todo fluxo é dividido por
`(1+r)^ano`), a raiz sai por **bissecção** (`solveIRR`, 64 passos) — vale para os 3 modelos
(`irrDDM`/`irrOE`/`irrR1`, despachados por `irrOf(s)` a partir do modelo salvo da ação).
- **Piso da busca:** no DDM/OE é o crescimento perpétuo `g∞` (abaixo dele Gordon não converge) —
  se nem aí o modelo alcança o preço, a TIR é **indefinida** (`—`, nunca um número inventado).
  No R1 não há perpetuidade: o piso é −90%, então ação cara demais devolve **TIR negativa**.
  Teto `IRR_HI = 200%` (satura). Sem preço, LPA≤0 ou `Sem valuation` ⇒ `null`.
- **É aditivo:** não altera preço justo nem margem — só relê os mesmos `compute*` com outro desconto.
  (Não há mais margem-input no R1; a TIR usa o sticker direto.)
- **Onde aparece:** coluna **TIR** no screener (ordenável/filtrável; verde/vermelho vs. o **Ke
  efetivo da ação** — `oeD(s)` = o dela se salvo, senão o global; o mesmo Ke que gerou o justo) +
  stat "TIR mediana"; no detalhe, linha no hero (`updateHeroTir`), linha em "Implicações"
  (`setTirRow`) e o **passo a passo da conta** (`tirStepHtml` → `#ddm-tirBox`/`#oe-tirBox`/
  `#r1-tirBox`): ponto de partida ao Ke, tabela de sensibilidade com a linha da raiz destacada
  (`.proj tr.hit`), prêmio em p.p. e o equivalente **real** (deflacionado pelo IPCA da config).
  No detalhe a TIR usa as premissas **ao vivo** dos sliders; no screener, as salvas.
- **Memo:** `irrOf` cacheia em `s.__irr` com chave (`irrKey`) que cobre preço, modelo, todas as
  premissas e os padrões globais — o screener remapeia a lista a cada tecla do filtro
  (≈5,6 ms frio → 0,4 ms quente nas 379 ações).
- Por que somar à margem: a margem % depende do Ke arbitrado e da duração dos fluxos; a TIR põe
  todas as ações na mesma unidade (retorno a.a.), comparável entre si e contra a NTN-B.

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

## Carteira (aba `#/carteira`, ago/2026)
Aba de acompanhamento da carteira do usuário. **Reusa os MESMOS cálculos do screener** (`fairResult`,
`marginOf`, `mosOf`, `irrOf`, `oeD`) — nada é recalculado por fora; o front (`renderCarteira` em
`index.html`) só junta `PORTFOLIO` (posições do Supabase) com os objetos de ação já carregados.
Pesos e concentração vêm do **valor de mercado** (`qtd × preço ao vivo`). Convenções dos agregados:
- **Patrimônio** = Σ qtd×preço; **Resultado** = patrimônio − custo (custo = Σ qtd×PM).
- **DY / renda projetada:** `DPA = LPA × payout` (MESMA base do "dividendo de partida" do DDM/R1;
  `payoutEff`→`dpaOf`/`dyOf`). Renda anual = Σ DPA×qtd; DY carteira = renda ÷ patrimônio.
- **Margem seg. / Upside agregados:** nível de carteira, não média de %: `(Σqᵢjustoᵢ − Σqᵢpreçoᵢ)`
  sobre `Σqᵢjustoᵢ` (margem, base justo) ou `Σqᵢpreçoᵢ` (upside) — só sobre posições com justo válido.
- **TIR ponderada:** média das `irrOf` **ponderada pelo valor** da posição (renormalizada nas com TIR
  definida); benchmark = **Ke efetivo ponderado** (Σ `oeD`×valor). É média ponderada, não uma TIR
  agregada resolvida do zero — rotulada como tal.
- **HHI** = Σ peso² (0..1; exibido ×10.000); **nº efetivo de ações** = 1/Σpeso² (faixas 1500/2500).
  A caixinha "Concentração" tem um **ⓘ** (`.cart-statinfo` → popover `.cart-statpop`, toggle no click
  handler do `#cartBody`) que explica a fórmula com os **números reais** (HHI, maior posição). Padrão
  reaproveitável via `data-statpop` (dá p/ pôr o mesmo ⓘ nas outras caixinhas).
- **Visualização da concentração:** barras por ação (`.cart-bar-fill` **precisa de `display:block`** —
  span inline ignora `width`) + **rosca por setor B3 em SVG** (`donutSvg`: um `<path>` por fatia, arcos
  ∝ `wRel` p/ fechar 360°; grupo único vira `<circle>` anel). **Drill-down clicável** Setor→Subsetor→
  Segmento: as fatias e a legenda levam `data-drill-setor`/`data-drill-sub`; breadcrumb (`data-drill-to`)
  volta. Estado em `secDrill`/`secData`; `renderSectorCard()` redesenha só o card (`#cartSecCard`) sem
  re-render geral. `.cart-donut-mid` é `pointer-events:none` p/ não bloquear o clique nas fatias. A
  legenda mostra **% (peso na carteira) e valor em R$** (`wRel` só desenha a rosca; o número é o peso real).
- **Aporte inteligente** = HEURÍSTICA (`suggestAporte`, rotulada "não é recomendação"): só sugere o
  que está **abaixo do preço justo E sub-alocado** (peso < alvo igualitário), p/ o aporte de fato
  reduzir concentração; aloca ∝ score (0,65 desconto + 0,35 sub-alocação), floor em cotas inteiras.
- Todos os agregados protegem divisão por 0; posições sem cotação/justo ficam fora dos respectivos
  totais (nunca inventam valor) e são sinalizadas. Verificado: as funções reais batem 1:1 com
  recálculo independente sobre dados ao vivo (12/12 checks).

## Endpoints e outros detalhes
- `/api/stocks` (screener), `/api/history/{ticker}?range=5y` (fechamento diário p/ o gráfico),
  `/api/config`, `/api/premissas/{ticker}`, `/api/watchlist[/{ticker}]`, `/api/carteira[/{ticker}]`
  (GET lista; POST upsert `{quantidade, preco_medio}`; DELETE), `/api/stocks/{ticker}`
  (PATCH/DELETE), `/api/macro` (Selic + IPCA-12m do BCB), FIIs: `/api/fiis`, `/api/fii/{ticker}`,
  `/api/fii-dpu?t=…`, `/api/fii-state`, `/api/fii-premissa|fii-watchlist|fii-carteira/{ticker}`.
  Cache no edge (preços 15 min, histórico 30 min, macro 12h, proventos de FII 6h).
- O gráfico de preços tem **seleção por clique-e-arrasto** (mostra a variação % entre dois pontos).
- O frontend cai nos dados de exemplo embutidos se as Functions estiverem fora. O `bootstrap`
  faz só um retry curto (não há mais cold start pra cobrir).

## Identidade visual ("Mesa de análise", jul/2026)
Re-skin sóbrio de nota de research (não é o SaaS azul/Inter genérico antigo). Tudo via CSS
variables no `<style>`, temas claro/escuro:
- **Paleta:** fundo porcelana `#f1f0ec`; `--accent` índigo-tinta `#2c3e6e`; par semântico
  **`--good` pinho `#1b6b4c` / `--bad` argila `#a8432f`**; **`--worth` latão** `#9a7b34` = "valor
  intrínseco" (usado no preço justo do hero e nos ticks do medidor).
- **Fontes:** **Space Grotesk** (títulos/tickers/rótulos/`.disp`), **IBM Plex Mono** (`.num`/`.mono`
  — todos os números), **Inter** (corpo/tabelas). Carregadas via Google Fonts no `<link>`.
- **Assinatura — Medidor de Margem de Segurança:** mostra preço↔justo. Grande no hero
  (`#heroGauge`, função `updateHeroGauge`, chamada em `renderDDM`/`setVerdict`/`renderNA`); mini na
  coluna Margem do screener (`marginCell`/`.mos-bar` — tick de latão central, fill pinho/argila).
  É **aditivo** (ilustra números já calculados; não altera valuation). O passo a passo do
  DDM/OE/R1 e todas as explicações ficam intactos — mudou só a "roupa" (fonte/cor).

## Mobile (camada responsiva, ago/2026)
Layout mobile todo em CSS (media queries), sem JS de layout. **Dois breakpoints** mexem no shell:
`@media (max-width:860px)` (tablet: sidebar vira topbar sticky + grids do detalhe/config viram 1 coluna)
e `@media (max-width:720px)` (celular). No celular:
- **Screener/Monitoradas viram cards** (`renderScreenerCards` → `.scr-cards`; a tabela some) + barra de
  controles `.scr-mtools` (busca `#scrSearch`, ordenação `#scrSortSel`, botão de filtros → bottom-sheet
  `#filterSheet`).
- **Navegação = barra inferior** (`.sidebar` vira `position:fixed;bottom:0;z-index:40`, `.nav` em linha
  com `flex:1` por item — a aba Carteira entra automática). `.main` reserva `padding-bottom` p/ a barra.
- **GOTCHA da barra fixa:** em telas longas (screener, 379 cards) a barra `position:fixed` pode
  **piscar/sumir no scroll** (repaint no Android / momentum no iOS). Fix atual: `transform:translateZ(0)`
  (camada de composição própria) **sem `will-change`** (que no iOS faz o oposto e some com o elemento).
  ⚠️ **NÃO** trocar por "shell de scroll interno" (`body{overflow:hidden}` + `.main` rolando + `100dvh`):
  foi tentado e **escondeu a barra** (o `100dvh` empurrou o rodapé pra baixo da área visível, sem scroll
  pra alcançar). `position:fixed;bottom:0` é o que garante a barra sempre visível.

## Git
Conta **henriqueSpencer** (`gh auth switch --user henriqueSpencer`), autor
`Henrique Spencer <henriquespencer11@gmail.com>`. Commits/PRs **sem nenhuma menção a IA/Claude/
Anthropic** (nada de `Co-Authored-By` nem "Generated with"). **Deploy é MANUAL** (`wrangler pages deploy`,
ver seção Deploy) — **push no `main` NÃO redeploya sozinho** (sem git-integration).
