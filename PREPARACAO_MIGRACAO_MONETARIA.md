# Preparação da migração monetária — auditoria e runbook

**Data da revisão:** 14/10/2026  
**Repositório:** `IsaacTexCotton/Dashboard`  
**Branch desta preparação:** `ops/preparacao-migracao-monetaria`  
**Base:** merge da PR #9, `88d20f9e2c5e608518d7fd949095763f4e454665`  
**Escopo:** somente código, testes e documentação. Nenhum banco/CRM de produção foi acessado ou modificado.

## 1. Resumo executivo e evidências

| Item | Estado observado | Evidência / limite |
|---|---|---|
| PR #9 | Integrada | [PR #9](https://github.com/IsaacTexCotton/Dashboard/pull/9), merge `88d20f9e2c5e608518d7fd949095763f4e454665` |
| Implementação monetária | Presente na `main` | Parser estrito, mapeamento semântico, migração aditiva, backfill e escrita dupla opt-in |
| Flag da escrita dupla | Desativada por padrão | `importar.py` consulta `DASHBOARD_MONETARIO_DUAL_WRITE` com padrão `0`; esta preparação não altera a variável |
| PR #11 | Fechada sem merge | [PR #11](https://github.com/IsaacTexCotton/Dashboard/pull/11), HEAD `38408ae752b8825bfc85601530480788bb27b721` |
| Branch da PR #11 | Preservada | `feat/integracao-monetaria-v11`; não foi excluída |
| CI da PR #9 | Sucesso no HEAD da PR | [Run #38601252854](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38601252854), HEAD `761fbc3c37728b9718367d8b6c0618b2d23cfc4d`, 142 testes reportados |
| CI do commit exato da `main` | **Não comprovado pelo conector consultado** | A consulta de status para `88d20f9e2c5e608518d7fd949095763f4e454665` retornou uma lista vazia; a consulta de workflow disponível filtra execuções disparadas por PR e não permite concluir que não houve workflow de push. Não atribuir ao merge o sucesso do HEAD da PR |
| Amostra ERP/Systêxtil real sanitizada | Não disponível nesta revisão | Foi adicionada uma fixture de 36 casos sintéticos identificados no arquivo; ela não é evidência de validação de origem real |
| Produção | Intocada nesta etapa | Sem acesso a DB/CRM, DDL, backfill aplicado, cutover ou alteração de valores financeiros |

### Classificação das afirmações

- **Fato verificado:** resposta atual da API do GitHub para PRs, refs, arquivos e status disponível no conector.
- **Teste existente:** caso presente em `tests/`; seu sucesso nesta preparação só será afirmado se o CI da branch/PR o confirmar.
- **Teste sintético:** cenário gerado sem origem empresarial real.
- **Pendente:** evidência que não pôde ser obtida com os acessos/ferramentas disponíveis ou atividade que está fora do escopo sem produção.

## 2. Tratamento da PR #11 e preservação de contribuições

A PR #11 foi comparada com a `main` atual. A comparação de refs registrou 36 commits à frente da base comum e um commit de diferença no outro sentido; a PR listava 17 arquivos modificados. A comparação individual de conteúdo remoto encontrou 14 arquivos idênticos à `main` e diferenças em três arquivos:

1. **`importar.py`:** a versão antiga deixa de converter algumas exceções `ErroMonetario` em `ErroValidacao` nos preparadores da escrita dupla. A versão da `main` já contém esses tratamentos. Portar a versão antiga poderia regredir a superfície de erro do importador.
2. **`tests/test_importar.py`:** a PR antiga adicionava `depositos.valor` à lista de sinais proibidos. Isso contradiz a regra atual que permite sinal negativo no valor de depósito; não foi portado. A expectativa de erro para subcentavos foi especificada de forma mais precisa como `importar.ErroValidacao`, e essa melhoria de teste foi portada para esta branch.
3. **`tests/test_auditar_resposta.py`:** a PR antiga exigia divergência para um agregado negativo cuja soma por usuário também diverge. Essa assertiva foi avaliada, mas não portada: para os grupos acordos/promessas presentes na fixture, os valores negativos podem resultar em soma exatamente igual e o status correto é `OK`. Foi mantida a asserção flexível que verifica que a regra de sinal não levanta erro. A invocação que passa tolerância de R$ 0,01 não foi copiada, pois a política atual exige reconciliação monetária exata.

Os módulos monetários, o backfill, a escrita dupla, a migração e seus testes correspondentes já têm conteúdo idêntico ao da `main` no HEAD comparado. Nenhuma contribuição funcional exclusiva necessária foi identificada. A PR #11 está fechada sem merge, e a branch foi preservada como trilha de auditoria; **não excluir a branch até terminar a revisão humana do histórico, caso o proprietário queira mantê-la por mais tempo**.

## 3. Auditoria técnica da integração

### 3.1 Parser e normalização

- `precisao_monetaria.py` mantém inteiros como `int` e decimais JSON como `Decimal` por meio de `loads_json_estrito`. O parser lexical rejeita notação científica, constantes não finitas e JSON malformado.
- `valor_final_centavos` converte valores finais para inteiro escalado em duas casas sem arredondar entrada. Zeros finais extras são aceitos; dígitos não zero além da segunda casa são rejeitados. A faixa é compatível com INTEGER assinado de 64 bits.
- `grandeza_para_escala` trata grandezas como preço/taxa/quantidade com escala declarada. `resultado_calculado_para_centavos` aplica `ROUND_HALF_UP` ao resultado calculado, não à entrada monetária de origem.
- `modelo_monetario.py` separa as 8 métricas de `fatos` e as 3 métricas de `acordos_posicao`.
- O caminho legado do importador ainda converte valores a `float` e grava colunas SQLite `REAL`; isso é compatibilidade existente, não prova de que os `REAL` foram desativados. A migração paralela só se destina a ativação controlada.

### 3.2 Migração, backfill e escrita dupla

- `migrar_schema_monetario.py` implementa DDL aditiva, valida colunas/checks e mantém um marcador de fase. A integração de importação não deve ser tratada como gatilho implícito para aplicar DDL.
- `backfill_monetario.py` planeja sem escrita por padrão (`aplicar=False`/CLI sem `--aplicar`). A simulação abre banco existente em modo somente leitura, calcula updates previstos e não muda colunas `REAL` nem marca reconciliação concluída.
- A aplicação do backfill é uma operação separada, explicitamente opt-in e transacional. A CLI exige `--diretorio-backup` existente e cria/verifica backup antes de aplicar; **não foi chamada com `--aplicar` nesta etapa**.
- `escrita_dupla.py` deriva as duas representações da mesma entrada validada e grava `REAL`, centavos, usuários e log dentro da transação do dia. Os testes existentes exercitam falha simulada em cada representação e rollback.
- O default `DASHBOARD_MONETARIO_DUAL_WRITE=0` deve permanecer. Esta branch não altera o default ou variável de ambiente.
- O helper de conversão de histórico usa `Decimal(repr(float))` e `half-up` como interpretação determinística do valor já armazenado em `REAL`. Isso não recupera o token decimal original do ERP. Qualquer divergência entre o número histórico interpretado e a regra de origem precisa ser diagnosticada, nunca corrigida em silêncio.

## 4. Inventário conhecido de consumidores/caminhos de `REAL`

Este inventário cobre os arquivos que puderam ser inspecionados individualmente no repositório remoto. A ferramenta de busca de código disponível não retornou correspondências indexadas para pesquisas por `valor_pago`, `valor_aberto`, `acordos_posicao`, `sqlite3.connect` ou `DASHBOARD_DB`. Portanto, **não é correto afirmar que este inventário já é exaustivo para todos os dashboards, relatórios, consultas externas ou integrações**. O comando de busca de checkout completo mais abaixo fecha essa lacuna.

| Arquivo / função | Relação com `REAL` | Estratégia de transição |
|---|---|---|
| `importar.py` — `SCHEMA`, `_numero`/`_campo_numero`, `normalizar`, `gravar`, `_abrir_banco` | Cria/usa `fatos.valor`, `valor_pago`, `valor_aberto`, `valor_quebrado` e `acordos_posicao.recebido_periodo`, `a_vencer`, `vencido` como `REAL`. O caminho legado escreve esses campos. | Manter semântica legada durante transição. Ativação paralela apenas após inventário de consumidores, schema verificado e ensaio separado; flag fica em `0`. |
| `escrita_dupla.py` — `preparar_fato_duplo`, `preparar_posicao_dupla`, `gravar_dia_duplo` | Escritor para as colunas legadas `REAL` e respectivas colunas `INTEGER` em centavos, atomicamente. | Usar somente no ensaio com SQLite descartável. Não ativar em produção neste trabalho. |
| `backfill_monetario.py` — `backfill_monetario`, `_planejar_fato`, `_planejar_posicao` | Leitor dos `REAL` históricos para planejar valores em centavos; pode aplicar updates quando explicitamente solicitado. | Executar sem `--aplicar` para relatório reproduzível. Uma eventual aplicação exige etapa operacional separada, backup verificado e análise de divergências. |
| `migrar_schema_monetario.py` — `migrar_schema_monetario`, `validar_schema_monetario` | Inspeciona schema legado e acrescenta colunas semânticas; não é consumidor de relatório financeiro. | Executar somente em DB sintético/descartável nesta preparação. DDL real continua fora do escopo. |
| `auditar_resposta.py` — `auditar` | Valida totais recebidos no JSON e soma por usuário; não consulta o DB `REAL` diretamente. Os valores são normalizados para comparação exata. | Continuar como gate pré-gravação para o payload. Não confundir com reconciliação de backfill histórico. |
| `diagnosticar_banco.py` — `diagnosticar` | Abre SQLite em modo somente leitura; confere existência, tipo e finitude de colunas legadas, integridade e referências. | Preservar diagnóstico de compatibilidade durante a transição e adicionar verificações paralelas de schema/contagens onde necessário. |
| `backup_sqlite.py` — `criar_backup`, `verificar_backup` | Copia o arquivo SQLite de forma consistente e verifica hash, integridade e contagens; não interpreta regra monetária. | Usar antes de qualquer operação potencialmente mutável e testar restauração em arquivo separado. |
| `validar_integracao_local.py` | Exercita importação, auditoria e diagnóstico contra SQLite temporário; não chama o CRM e não deve apontar para DB persistente. | Manter teste local/CI; a fixture atual é ilustrativa, não amostra ERP real. |
| Relatórios, dashboards, SQL externo, exportadores e outros clientes não listados | **Não confirmados como ausentes.** A leitura recursiva completa do código não pôde ser executada via conector; consumidores externos também não podem ser inferidos a partir do código acessível. | Executar a busca abaixo num checkout completo e documentar cada ocorrência com arquivo/função, leitura/escrita, proprietário funcional conhecido e teste de compatibilidade antes de planejar corte. |

Busca reproduzível num checkout completo (não altera dados):

```bash
git grep -nE 'valor_pago|valor_aberto|valor_quebrado|recebido_periodo|a_vencer|vencido|deposito_valor_centavos|acordo_.*centavos|promessa_.*centavos|sqlite3\.connect|DASHBOARD_DB|SELECT.*valor|INSERT.*fatos|UPDATE.*fatos' -- '*.py' '*.sql' '*.js' '*.ts' '*.html' '*.yml' '*.yaml'
```

Registre ocorrências em código de aplicação separadamente de documentação e testes. Faça a mesma busca em repositórios clientes, consultas salvas e ferramentas externas que não estão versionadas neste repositório; a ausência de ocorrência local não prova ausência de consumidor externo.

## 5. Contrato de dados monetários

Todos os valores abaixo são inteiros assinados de 64 bits em **centavos de BRL**. Para valores finais recebidos, a entrada deve ser exata até centavos; `1.230` equivale a 123 centavos, enquanto `1.231` deve ser rejeitado, sem arredondamento. `half-up` é aplicado uma vez somente ao resultado de cálculo. Não há tolerância de um centavo para declarar igualdade monetária.

### 5.1 Oito métricas semânticas de `fatos`

| Coluna alvo | Tipo de fato / origem | Sinal permitido | Se não aplicável |
|---|---|---|---|
| `deposito_valor_centavos` | `deposito.valor` / legado `fatos.valor` | Negativo permitido | `NULL` |
| `acordo_valor_centavos` | `acordo.valor` / legado `fatos.valor` | `>= 0` | `NULL` |
| `acordo_pago_centavos` | `acordo.pagos` / legado `fatos.valor_pago` | `>= 0` | `NULL` |
| `acordo_pendente_centavos` | `acordo.pendente` / legado `fatos.valor_aberto` | Negativo permitido | `NULL` |
| `promessa_prometido_centavos` | `promessa.prometido` / legado `fatos.valor` | `>= 0` | `NULL` |
| `promessa_cumprido_centavos` | `promessa.cumprido` / legado `fatos.valor_pago` | `>= 0` | `NULL` |
| `promessa_em_aberto_centavos` | `promessa.emAberto` / legado `fatos.valor_aberto` | Negativo permitido | `NULL` |
| `promessa_quebrado_centavos` | `promessa.quebrado` / legado `fatos.valor_quebrado` | `>= 0` | `NULL` |

Para `tipo='contato'`, nenhuma das oito métricas monetárias é aplicável; os alvos devem ser `NULL`. Campos do legado que tenham valor zero por default não tornam a métrica semanticamente aplicável.

### 5.2 Três métricas de `acordos_posicao`

| Coluna alvo | Origem/legado | Sinal permitido |
|---|---|---|
| `recebido_periodo_centavos` | `valoresAcordo.valorRecebidoPeriodo` / `recebido_periodo` | Negativo permitido |
| `a_vencer_centavos` | `valoresAcordo.valorAVencer` / `a_vencer` | `>= 0` |
| `vencido_centavos` | `valoresAcordo.valorVencido` / `vencido` | `>= 0` |

### 5.3 `NULL`, zero, eventos e escalas

- **Zero (`0`)** significa que a métrica aplicável foi informada/calculada e seu valor é zero.
- **`NULL`** significa que a métrica não se aplica àquele tipo de fato ou que a origem não informou o dado; o backfill não converte `NULL` em zero. Uma origem `NULL` para métrica aplicável requer diagnóstico e permanece pendência.
- Tipos de evento de `fatos`: `deposito`, `acordo`, `promessa`, `contato`. Tipos desconhecidos devem interromper o lote, sem gravação parcial.
- Valores monetários finais têm escala 2. Preços unitários, quantidades fracionárias, taxas e percentuais usam a escala declarada no contrato, como `_e4`, sem arredondamento ao converter a entrada.
- Limites de intervalo, tokens não finitos, booleanos e notação científica são validações negativas obrigatórias. Os sinais acima provêm de `modelo_monetario.py` e `migrar_schema_monetario.py`; sua validade com fórmulas/semântica do ERP real continua dependente da amostra sanitizada de origem.
- Nenhum registro deve ser marcado conciliado apenas porque o conversor produziu um inteiro. Conciliação exige comparar os centavos esperados, registrar divergências e preservar sua evidência.

## 6. Validação representativa de 30+ registros

O repositório não fornece, nesta etapa, 30 títulos/eventos reais ERP/Systêxtil autorizados e sanitizados. Para não fabricar evidência de origem, foi adicionada `tests/fixtures/amostra_monetaria_erp_systextil_sintetica.json`, marcada `SINTETICO_NAO_REAL`, com **36 casos** de depósitos, acordos, promessas, snapshots e grandezas de cálculo.

Os cenários incluem zero versus `NULL`, sinal permitido/proibido, zeros finais, subcentavos rejeitados, limites int64, escala e4 e `half-up` em resultados calculados. O teste `tests/test_preparacao_migracao_monetaria.py` consome tokens decimais por `loads_json_estrito` e verifica resultado/erro esperado. Isso é cobertura contratual sintética, não validação de dado real, regra de negócio do ERP ou fórmula Systêxtil.

Para fechar a lacuna real, coletar ao menos 30 registros representativos de origem sob acesso autorizado, remover identificadores pessoais e segredos, preservar tipos e tokens numéricos relevantes, registrar sistema/campo/regra/caso e comparar cada resultado em centavos com o resultado oficial do ERP. Se a origem carregar frações subcentavo em campo final ou discordar do sinal/método de arredondamento definido, bloquear o cenário e abrir decisão técnica com evidência; não ajustar o dado silenciosamente.

## 7. Backup, restauração e verificação de integridade

### Procedimento implementado

`backup_sqlite.py` usa a API online backup do SQLite, recusa sobrescrever destino/manifesto e registra tamanho, SHA-256, `PRAGMA integrity_check`, `user_version` e contagens por tabela. A verificação valida hash, tamanho, contagens e integridade. Nesta branch, `tests/test_preparacao_migracao_monetaria.py` cria uma base sintética descartável com 36 linhas, cria backup, verifica o manifesto, restaura para um **terceiro arquivo** e compara linhas/contagens mais `integrity_check`. O teste não acessa qualquer caminho de produção.

Comandos do runbook para um banco de homologação isolado existente:

```bash
mkdir -p /tmp/migracao-monetaria/backups
python backup_sqlite.py criar /tmp/migracao-monetaria/homologacao.sqlite3 \
  --destino /tmp/migracao-monetaria/backups/pre-migracao.sqlite3
python backup_sqlite.py verificar /tmp/migracao-monetaria/backups/pre-migracao.sqlite3
```

Restauração de ensaio deve apontar para novo arquivo, não substituir a origem:

```bash
python - <<'PY'
import sqlite3
origem = sqlite3.connect("/tmp/migracao-monetaria/backups/pre-migracao.sqlite3")
destino = sqlite3.connect("/tmp/migracao-monetaria/restaurado.sqlite3")
try:
    origem.backup(destino)
    assert destino.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    print("integrity_check=ok")
finally:
    destino.close()
    origem.close()
PY
```

A verificação do manifesto é feita sobre o backup original antes da restauração. Para validar a cópia restaurada, use `PRAGMA integrity_check`, contagens por tabela e comparação de conteúdo com a origem/backup. Não interprete hash do arquivo restaurado como igual ao hash do backup em todo cenário de cópia lógica. O teste automatizado compara as linhas restauradas com as linhas da origem e verifica a integridade.

Para operação futura em ambiente real, gerar backup novo com acesso restrito, guardar arquivo e manifesto juntos, conferir o resultado `OK`, testar a restauração em arquivo separado e registrar o hash e as contagens antes de iniciar qualquer etapa mutável. Backup validado não é autorização para migrar.

## 8. Backfill em modo simulação

A simulação deve usar banco descartável já preparado com o schema legado e as colunas aditivas:

```bash
python backfill_monetario.py /tmp/migracao-monetaria/homologacao-migrada.sqlite3
```

Sem `--aplicar`, a CLI exige que o arquivo já exista, abre SQLite em modo somente leitura e retorna JSON com `modo=simulacao`, número de linhas de `fatos`, snapshots, `updates_previstos`, `colunas_a_preencher`, campos pendentes, `colunas_real_alteradas=0` e `conciliacao_concluida=false`. Guardar a saída com identificação do SHA do código, hash/contagens da base sintética e comando usado.

O relatório de simulação deve ser repetível sobre a mesma imagem de banco. Divergências de destinos já preenchidos, valores históricos não finitos, sinais proibidos, tipo desconhecido e overflow são erros para diagnóstico; o conversor não deve sobrescrever um valor em centavos já preenchido e divergente. A simulação não é reconciliação financeira nem substitui os 30 registros reais.

**Proibido nesta etapa:** executar `migrar_schema_monetario.py` contra DB real, usar CLI com `--aplicar`, alterar o banco de produção, ativar triggers em produção ou fazer cutover.

## 9. Dupla escrita, falha e rollback

Cobertura já presente em `tests/test_escrita_dupla.py` inclui:

- `test_grava_legado_e_centavos_no_mesmo_lote`: confere valores legados e centavos na mesma gravação;
- `test_falha_em_centavos_reverte_o_dia_inteiro`: trigger de falha na escrita em centavos, sem preservar gravação parcial do dia;
- `test_falha_no_writer_legado_reverte_tambem_centavos`: falha no writer legado reverte a transação;
- `test_rollback_pos_corte_encontra_registro_novo_nas_colunas_real`: confirma que uma linha escrita em modo duplo segue legível nos campos `REAL` legados;
- `test_autocommit_tambem_usa_transacao_explicita`: testa a fronteira transacional com autocommit.

Os testes usam banco SQLite em memória. São testes de mecanismo, não ensaio de volume ou operação de produção. A escrita dupla deve produzir `REAL`, centavos e log dentro de uma transação; qualquer falha deve reverter todos os efeitos do lote. Para rollback futuro de leitura, manter os `REAL` legados sem renomear/remover e conferir que as linhas criadas depois do corte permanecem disponíveis nas colunas legadas. Não fazer rollback por restauração cega de backup antigo sobre dados recentes; isso apagaria gravações posteriores. O rollback da aplicação deve voltar a ler os campos legados do banco atual, preservando todas as linhas gravadas durante o período duplo.

A flag continua em `DASHBOARD_MONETARIO_DUAL_WRITE=0`. Os testes isolados chamam explicitamente o gravador para validar o mecanismo, não habilitam a feature flag nem afetam bancos persistentes.

## 10. Observabilidade, reconciliação e condições de interrupção

Durante qualquer ensaio futuro, registrar por execução, sem dados pessoais:

- SHA do código, versão do schema/fase, origem do dataset (sintético ou sanitizado), quantidade de linhas de `fatos` e `acordos_posicao`;
- valores previstos: `updates_previstos`, `colunas_a_preencher`, `campos_pendentes_origem_null`, `colunas_real_alteradas` e `conciliacao_concluida`;
- contagens de métricas aplicáveis ausentes, `NULL` em métricas não aplicáveis, zero legítimo, valor negativo permitido, sinal proibido, não finito, overflow e conflito entre centavos já gravados e conversão esperada;
- número de divergências por tabela/campo e uma amostra com chaves técnicas pseudonimizadas; preservar os dados de origem fora de logs compartilhados;
- falhas da transação, rollback executado, hash/resultado do backup e `PRAGMA integrity_check` antes/depois.

Reconciliação: para cada campo histórico, comparar `centavos_existentes` com o inteiro produzido pela regra de conversão explicitamente definida para `REAL` legado. Para dado novo de origem, comparar os inteiros em centavos obtidos de JSON estrito com os centavos esperados pela origem, por igualdade exata. Não usar `abs(a-b) < 0.01`, não comparar por tolerância de um centavo e não usar conversão float de exibição como evidência.

**Interromper sem avançar fase** se houver: backup ausente ou verificação diferente de `OK`; erro de integridade; teste falho; schema/constraint incompatível; tipo de evento desconhecido; valor final subcentavo; token decimal inválido/não finito; sinal não permitido; overflow int64; conflito de destino previamente preenchido; discrepância nas contagens; falha de escrita sem rollback integral; ou divergência monetária ainda não explicada. Não marcar registros conciliados automaticamente.

## 11. Testes e validações a executar/acompanhar

O workflow `.github/workflows/testes.yml` configura Python 3.11, executa `python -m unittest discover -s tests -v` e valida `amostra_resposta.json` com importação em `--dry-run`, auditoria e `validar_integracao_local.py`.

Para reproduzir o conjunto inteiro localmente:

```bash
python -m unittest discover -s tests -v
python -m unittest tests/test_preparacao_migracao_monetaria.py -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
python validar_integracao_local.py amostra_resposta.json
```

Use a primeira forma de execução da suíte como referência principal; conforme o ambiente Python, o comando direcionado ao módulo de teste pode precisar da forma `python -m unittest discover -s tests -p 'test_preparacao_migracao_monetaria.py' -v`.

A consulta efetuada para o status do commit exato da `main` não retornou checks identificáveis pelo conector. O sucesso de #38601252854 está associado a `761fbc3c...`, não ao commit de merge `88d20f9e...`. Esta distinção deve ser mantida. O CI disparado pela PR desta preparação é a evidência para as alterações de testes/documentação e para a suíte do código-base incorporado; não reescrever retroativamente o status do merge como se fosse o resultado do HEAD da PR.

## 12. Escopo, riscos remanescentes e decisão

### Concluído no escopo desta branch

- [x] Comparar PR #11 com a `main` e revisar as diferenças de conteúdo identificadas.
- [x] Manter PR #11 fechada sem merge e preservar a branch antiga.
- [x] Documentar o contrato das 11 métricas e a distinção `NULL`/zero.
- [x] Adicionar 36 fixtures explicitamente sintéticas e testes de conversão estrita.
- [x] Adicionar teste de backup, verificação e restauração lógica em SQLite descartável.
- [x] Fortalecer a expectativa do teste de subcentavos com o tipo de erro público (`ErroValidacao`), sem alterar o runtime.
- [x] Documentar o inventário de consumidores conhecido, a lacuna de exaustividade e a busca reproduzível.
- [x] Documentar comandos operacionais; nenhum comando de alteração foi apontado para DB/CRM de produção.

### Pendências reais antes de considerar migração operacional pronta

- [ ] Obter CI recente com evidência inequívoca do commit exato `88d20f9e2c5e608518d7fd949095763f4e454665`, ou registrar o CI de PR desta branch como validação da árvore de código-base e manter explicitamente a lacuna de status do merge.
- [ ] Completar o inventário via `git grep` no checkout completo e nos repositórios/consultas consumidores não versionados.
- [ ] Validar ao menos 30 registros ERP/Systêxtil reais, autorizados e sanitizados. Fixtures sintéticas não eliminam essa pendência.
- [ ] Executar e guardar o resultado do backfill em simulação sobre uma cópia sintética completa representativa, com contagens e divergências reproduzíveis.
- [ ] Preservar evidência do teste isolado de backup/restauração e do CI desta branch.
- [ ] Elaborar uma janela de execução futura e uma comparação de reconciliação com a origem antes de qualquer ação de escrita; isso não é autorização automática.

**Decisão desta preparação:** **pronto com ressalvas para revisão técnica/operacional documental**, somente se o CI desta PR passar. Não está pronto para backfill aplicado, migração real, ativação da dupla escrita ou cutover. A limitação do CI exato da `main`, a busca completa de consumidores e a ausência de amostra real permanecem explícitas; nenhuma dessas lacunas foi convertida em resultado presumido.
