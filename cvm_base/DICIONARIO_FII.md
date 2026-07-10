# Dicionário de dados — Base CVM FII (Informe Anual)

Base a partir do **Informe Anual de FIIs** que a CVM publica em
<https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/>.
Fonte bruta: `Dados CVM FII Anuais/` (preservada). Views na mesma `cvm_base/cvm.duckdb`
(prefixo `fii_`), Parquet em `cvm_base/parquet_fii/`. Reprocessar: `build_fii.py`.

Cobertura atual: **1.336 fundos, 2016–2025**.

## Como consultar
```bash
# achar o CNPJ do fundo pelo nome
duckdb cvm_base/cvm.duckdb "SELECT DISTINCT CNPJ_Fundo_Classe, Nome_Fundo_Classe FROM fii_geral WHERE Nome_Fundo_Classe ILIKE '%kinea%'"
# carteira de imóveis/ativos de um fundo num ano
duckdb cvm_base/cvm.duckdb "SELECT Nome_Ativo, Valor FROM fii_ativo_valor_contabil WHERE CNPJ_Fundo_Classe='...' AND ano=2024"
```

## Estrutura
Cada tabela do informe é uma view `fii_<tabela>`, **já filtrada para a última `Versao`** de
cada informe (par `CNPJ_Fundo_Classe` + `Data_Referencia`). As `fii_<tabela>_raw` expõem o cru.
Colunas mantêm o **nome original da CVM** (DuckDB é case-insensitive, então `nome_fundo_classe`
funciona). O `ano` (partição) vem do nome do arquivo.

### Chaves comuns a quase todas as tabelas
| Coluna | Descrição |
|--------|-----------|
| `CNPJ_Fundo_Classe` | **Identificador do fundo** (não há ticker na CVM) |
| `Data_Referencia` | Data-base do informe (dia/mês variam; use `ano` para filtrar por ano) |
| `Versao` | Versão do informe; as views já mantêm só a mais recente |
| `ano` | Ano de referência (partição) |

## Views (tabelas do informe)
| View | Conteúdo | Cardinalidade |
|------|----------|---------------|
| `fii_geral` | Identificação: nome, `Codigo_ISIN`, `Segmento_Atuacao`, `Tipo_Gestao`, público-alvo, administrador, nº de cotas emitidas | 1 por fundo/ano |
| `fii_complemento` | Gestor/custodiante/auditor, **resultado do exercício**, políticas, `Valor_Pago_Ano_Referencia`, `Percentual_Patrimonio_*` | 1 por fundo/ano |
| `fii_distribuicao_cotistas` | Distribuição de cotistas por faixa (nº de cotistas, % PF/PJ) | 1 por fundo/ano |
| `fii_ativo_valor_contabil` | **Carteira**: `Nome_Ativo`, `Valor` (contábil), `Valor_Justo` (flag S/N), % valorização | N por fundo/ano |
| `fii_ativo_adquirido` | Ativos adquiridos no exercício | N por fundo/ano |
| `fii_ativo_transacao` | Transações com ativos (compras/vendas) | N por fundo/ano |
| `fii_diretor_responsavel` | Diretor responsável pelo fundo | 1+ por fundo/ano |
| `fii_experiencia_profissional` | Experiência profissional dos responsáveis | N |
| `fii_prestador_servico` | Prestadores de serviço | N |
| `fii_processo` | Processos judiciais/administrativos | N |
| `fii_processo_semelhante` | Processos semelhantes | N |
| `fii_representante_cotista` | Representante de cotistas | N |
| `fii_representante_cotista_fundo` | Representante de cotistas (fundo) | N |

## Observações
- `fii_ativo_valor_contabil.Valor_Justo` é um **flag** (`S`/`N`), não um valor monetário; o valor
  está em `Valor` (texto — use `TRY_CAST(Valor AS DOUBLE)`).
- Números vêm como texto (leitura `all_varchar`); converta com `TRY_CAST(... AS DOUBLE)` nas contas.
- `Codigo_ISIN` (em `fii_geral`) é o gancho para mapear o **ticker de bolsa** (ex.: HGLG11) numa
  etapa futura de integração de preços.
- Sem cotação/preço na CVM — múltiplos como **DY, P/VP** exigem preço de fonte externa.
