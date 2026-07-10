# Dicionário de dados — Base CVM DFP (Ações)

Base construída a partir das **Demonstrações Financeiras Padronizadas (DFP)** anuais que a
CVM publica em <https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/>.
Fonte bruta: `Dados CVM -Acões -Anuais/` (preservada). Base consultável: `cvm_base/cvm.duckdb`
(+ `cvm_base/parquet/`). Reprocessar com `build_base.py` sempre que baixar um ano novo.

## Como consultar
```bash
duckdb cvm_base/cvm.duckdb "SELECT ano, vl_conta FROM dre WHERE cd_cvm='001023' AND cd_conta='3.11' AND ordem_exerc='ÚLTIMO' AND tipo_dem='con' ORDER BY ano"
```

## Views disponíveis
As views **limpas** já mantêm só a versão mais recente de cada documento (`VERSAO`) e têm
colunas em minúsculas. As views `*_raw` expõem o Parquet cru (SELECT *), úteis para depurar.

| View | Conteúdo |
|------|----------|
| `dre` | Demonstração do Resultado (receita, custos, lucro) |
| `bpa` | Balanço Patrimonial **Ativo** |
| `bpp` | Balanço Patrimonial **Passivo** (inclui Patrimônio Líquido) |
| `dfc_mi` | Fluxo de Caixa — Método **Indireto** |
| `dfc_md` | Fluxo de Caixa — Método **Direto** |
| `dmpl` | Mutações do Patrimônio Líquido (tem coluna extra `coluna_df`) |
| `dva` | Demonstração do Valor Adicionado |
| `dra` | Demonstração do Resultado Abrangente |
| `cadastro` | Metadados do documento (categoria, data de recebimento, link CVM) |
| `empresas` | Dimensão de lookup: `cd_cvm`, `cnpj`, `empresa`, faixa de anos |
| `composicao_capital` | Nº de ações ON/PN e em tesouraria (a partir de 2011) |
| `parecer` | Texto do parecer do auditor |

## Colunas das demonstrações financeiras (`dre`, `bpa`, `bpp`, `dfc_*`, `dmpl`, `dva`, `dra`)
| Coluna | Descrição |
|--------|-----------|
| `cnpj`, `cd_cvm`, `empresa` | Identificação da companhia. **`cd_cvm` é o identificador estável** (o CNPJ e o nome podem mudar) |
| `ano` | Ano de referência (partição do Parquet) |
| `tipo_dem` | `'con'` = consolidado (grupo) · `'ind'` = individual (controladora). **Para valuation use `con`** quando existir |
| `ordem_exerc` | `'ÚLTIMO'` = ano de referência · `'PENÚLTIMO'` = ano anterior (cada arquivo traz os dois). **Filtre `ordem_exerc='ÚLTIMO'`** para a série sem sobreposição |
| `dt_ini`, `dt_fim`, `dt_refer` | Datas do exercício e de referência |
| `cd_conta`, `ds_conta` | Código e descrição da conta (ver plano de contas abaixo) |
| `vl_conta` | **Valor** (DOUBLE). Atenção à `escala` |
| `escala` | `'MIL'` (multiplique por 1.000) ou `'UNIDADE'` |
| `moeda` | Normalmente `REAL` |
| `conta_fixa` | `'S'` = conta padronizada/fixa do plano CVM · `'N'` = detalhamento da empresa |
| `coluna_df` | (só `dmpl`) qual coluna do PL: Capital Social, Reservas, Lucros Acumulados, etc. |

## Plano de contas — códigos mais úteis (empresas NÃO-financeiras)
> ⚠️ **Bancos e seguradoras usam outro plano** (ex.: no Banco do Brasil `3.01` = "Receitas de
> Intermediação Financeira"). Sempre confira `ds_conta`. Contas hierárquicas: `3`, depois
> `3.01`, `3.01.01`… (quanto mais níveis, mais detalhe). `conta_fixa='S'` filtra as padronizadas.

**DRE (`dre`)**
| cd_conta | conta |
|----------|-------|
| `3.01` | Receita de Venda de Bens/Serviços (receita líquida) |
| `3.02` | Custo dos Bens/Serviços Vendidos |
| `3.03` | Resultado Bruto |
| `3.04` | Despesas/Receitas Operacionais |
| `3.05` | Resultado antes do Financeiro e Tributos (**EBIT**) |
| `3.06` | Resultado Financeiro |
| `3.07` | Resultado antes dos Tributos |
| `3.08` | IR e CSLL |
| `3.09` | Lucro Líquido das Operações Continuadas |
| `3.11` | **Lucro/Prejuízo do período** (resultado líquido) |

> 📌 **O código do lucro líquido MUDA por setor e por época.** Em não-financeiras é `3.11`.
> Em **bancos**, o lucro consolidado está em `3.09` (ex.: Banco do Brasil até ~2019) e passou
> a `3.11` em anos recentes. Regra segura: filtre por texto —
> `ds_conta ILIKE '%lucro%líquido%período%'` — em vez de fixar o `cd_conta`.

**Balanço Ativo (`bpa`)**
| cd_conta | conta |
|----------|-------|
| `1` | Ativo Total |
| `1.01` | Ativo Circulante |
| `1.01.01` | Caixa e Equivalentes de Caixa |
| `1.02` | Ativo Não Circulante |

**Balanço Passivo (`bpp`)**
| cd_conta | conta |
|----------|-------|
| `2` | Passivo Total (= Ativo Total) |
| `2.01` | Passivo Circulante |
| `2.02` | Passivo Não Circulante |
| `2.03` | **Patrimônio Líquido** (Consolidado) |

**Fluxo de Caixa Indireto (`dfc_mi`)**
| cd_conta | conta |
|----------|-------|
| `6.01` | Caixa das Atividades Operacionais |
| `6.02` | Caixa das Atividades de Investimento |
| `6.03` | Caixa das Atividades de Financiamento |

## Receitas para valuation (exemplos)
- **Série histórica de lucro líquido** (consolidado): `dre` + `cd_conta='3.11'` + `ordem_exerc='ÚLTIMO'`.
- **ROE**: lucro (`dre 3.11`) ÷ Patrimônio Líquido (`bpp 2.03`), mesmo `cd_cvm`/`ano`/`tipo_dem`.
- **Margem líquida**: `dre 3.11` ÷ `dre 3.01`.
- **Nº de ações** para LPA/valor patrimonial por ação: `composicao_capital`.

## Limitações
- **Sem ticker (ex.: PETR4) e sem preço/cotação** — os dados da CVM só trazem `cnpj`/`cd_cvm`/`empresa`.
  Múltiplos de mercado (P/L, P/VP, EV/EBITDA) exigem integrar preços de mercado à parte (etapa futura).
- Ano de 2026 é parcial (fechamento em andamento na CVM).
- Poucas empresas **mudam o exercício social** e reportam 2 datas (`dt_refer`) no mesmo `ano`.
  Se precisar de exatamente uma linha por ano, desempate pela mais recente:
  `QUALIFY row_number() OVER (PARTITION BY cd_cvm, ano, tipo_dem, ordem_exerc, cd_conta ORDER BY dt_refer DESC)=1`.
- FIIs ainda não incluídos (pasta `Dados CVM FII Anuais`, etapa futura).
