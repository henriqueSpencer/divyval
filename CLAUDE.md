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

## Arquitetura (Cloudflare Pages + Functions)
```
./                            ← raiz do repo = Pages "root directory"
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
    api/carteira.js           ← GET;  api/carteira/[ticker].js ← POST(upsert qtd+PM)/DELETE
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

Dados do usuário vivem em `premissa_atual` / `premissa_hist` / `watchlist` / `carteira` / `config`.
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
`APP_PASSWORD` (Basic Auth — só a senha é validada, o usuário é ignorado). `_middleware.js` protege
tudo (inclusive o HTML) e mantém `Cache-Control: no-cache` no HTML.
> Migrado do **Render** (que dormia → cold start) em jul/2026; o Render segue dormindo (inofensivo,
> desligar exige painel/API do Render). `render.yaml` e `backend/` ficam no repo como legado.

## Modelos de valuation (escolhíveis por ação — campo `stocks.modelo`)
Todo o cálculo é no **frontend** (`index.html`), despachado por `fairResult(s)`:
- `DDM · 2 est.` (`computeDDM`) — dividendos descontados ao Ke, fade de ROE/payout + perpetuidade
  de Gordon (o padrão).
- `Owner Earnings DCF` (`computeOE`) — método do Buffett: lucro do dono (≈LPA) a VP por N anos +
  perpetuidade.
- `Regra nº1 · Town` (`computeR1`) — LPA×(P/L futuro) descontado ao retorno **+ dividendos
  recebidos** (payout); saída = preço justo (sticker) e **preço-teto de compra** (sticker×(1−margem)).
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
`premissa_hist`; o R1 acrescentou as colunas **`fut_pe`** (P/L futuro) e **`mos`** (margem);
payout→`payout_i`, retorno→`ke`, horizonte→`fade`. Screener e histórico recalculam por modelo.

**Ke global — dois modos de entrada** (Configurações, jul/2026): *Nominal* (slider, como antes) ou
*IPCA + NTN-B*, que compõe **Ke = (1+IPCA)×(1+taxa real do título)×(1+prêmio de risco) − 1** (Fisher;
o prêmio é opcional, default 0). O nominal equivalente aparece no próprio campo. **O resto do app
segue lendo só `globalCfg.ke`** — o modo apenas registra como o número foi obtido; as chaves
`ipca_global`/`ntnb_global`/`premio_global`/`ke_mode_global` (0/1) vivem na tabela `config` e são
expostas por `api/config.js` (`ke_mode` vai como string `"nom"`/`"real"` na API). Motivo de usar o
nominal: LPA e dividendos projetados nos modelos são nominais.

**Upside × Margem de segurança (jul/2026) — duas colunas, duas bases.** A distância preço↔justo
aparece nas duas leituras, com nomes agora distintos:
- **`Upside`** (coluna `margin`, `marginOf`) = `(justo − preço)/preço` — "quanto pode subir".
  É a coluna histórica (só o **rótulo** mudou de "Margem" para "Upside"; a chave `margin` segue a
  mesma, então filtros/ordenação/colunas ocultas salvos no localStorage não quebram). Mantém o
  **mini medidor** (`.mos-bar`) — é a assinatura visual.
- **`Margem seg.`** (coluna `msafe`, `mosOf`/`mosFromFair`) = `(justo − preço)/justo` — definição
  clássica de Graham, **teto de +100%**; é a mesma base que o R1 usa no preço-teto
  (`sticker×(1−mos)`). Número puro, sem barra. `justo ≤ 0` ⇒ `—`.
- Relação: `MS = upside/(1+upside)`. Ordenar por uma dá a mesma ordem da outra (transformação
  monotônica) — o que muda é a **leitura** (upside +260% = comprar a 28% do valor).
- No detalhe as duas linhas convivem em "Implicações" (`impl-margin`/`impl-msafe` e equivalentes
  em OE/R1) e o selo do hero passou a dizer "de upside". No R1, `r1-impl-msafe-lbl` distingue a
  margem **atual** (no preço de hoje) da **exigida** (slider, que define o teto).
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
  A margem do R1 (`mos`) não entra na TIR (é proteção aplicada depois, não retorno).
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
  (PATCH/DELETE). Cache no edge (preços 15 min, histórico 30 min).
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
