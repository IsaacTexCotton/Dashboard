# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** o JSON autorizado de um dia (2026-10-13) foi validado em 14/10/2026 com os scripts publicados no commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`; os blobs dos quatro scripts executados foram conferidos contra os hashes do GitHub. O arquivo não foi versionado. A auditoria terminou com 12 métricas aditivas `OK` e `contatosUnicosTotal` classificado como `NÃO ADITIVO`; o `--dry-run` aprovou 5 usuários e 17 fatos sem abrir banco; `validar_integracao_local.py` terminou `PASSED`, com zero consultas ao CRM e SQLite apenas temporário; o diagnóstico reportou 13 verificações `OK`, zero avisos e zero falhas. Reimportar o mesmo payload manteve os 17 fatos; o registro de importação passou de 1 para 2 e o snapshot com o mesmo timestamp permaneceu único.
- **Decisões e estado de implementação:** `valorRecebidoPeriodo` identifica recebimentos do período; `valorAVencer` e `valorVencido` são posições por captura e cada captura permanece no histórico. A política versionada descreve aritmética exata, centavos em `INTEGER` para novas colunas, arredondamento *half-up* uma única vez no resultado final, comparação por igualdade exata e preservação das colunas `REAL` legadas até existir uma transição técnica segura. Este documento descreve o contrato de dados e o estado técnico verificável. A auditoria monetária já compara valores em centavos inteiros; o esquema aditivo, o backfill, a dupla escrita e o diagnóstico de fase têm implementação e testes em SQLite sintético. As colunas monetárias legadas `REAL` permanecem preservadas. A leitura por centavos do dashboard não está integrada, portanto não houve corte nem operação em banco real.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

## Decisões de negócio recebidas em 14/10/2026

| Tema | Decisão registrada | Estado técnico |
|---|---|---|
| Acordos por usuário | `valor = pagos + pendente` deve ser obrigatório após validar exceções | Ainda não bloqueante. É necessário definir como identificar e tratar renegociações, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais antes de ativar o bloqueio |
| Precisão monetária | Especificação v1.1 documentada em `POLITICA_PRECISAO_MONETARIA.md` | Parsing exato, classificação por campo, sinais e colunas semânticas descritos como alvo; DDL/backfill/cutover continuam dependentes dos gates técnicos de backup, conciliação e homologação |
| Timestamp da captura | Usar e preservar exatamente o campo `timestamp` enviado no JSON da origem, como referência temporal da posição atualizada | Decidido em 14/10/2026: não substituir por relógio local nem inferir/converter fuso; campo ausente ou vazio deve bloquear a importação |
| Contatos únicos globais | Não existe chave/regra de deduplicação documentada para negociadores | Manter `contatosUnicosTotal` como não aditivo; não somar por usuário nem usar essa métrica como gate de reconciliação |

 
## Contrato monetário v1.1 — especificação técnica de destino

Esta seção registra o contrato-alvo para alinhar o esquema por métrica e a política v1.1. **Não descreve o comportamento anterior do importador**, que rejeitava todos os valores negativos e fazia parsing monetário por `float`. A especificação v1.1 define o comportamento esperado; a execução depende dos gates técnicos de validação de origem, testes, backup/restauração, conciliação e rollback.

### Classificação campo a campo

Todos os valores monetários do payload de cobrança atualmente descritos nesta tabela são classificados como **valores monetários finais**, não como grandezas intermediárias de cálculo. A entrada deve preservar o token decimal original e ser convertida diretamente para centavos sem passar por `float`. Um valor com mais de duas casas textuais é aceito apenas quando todos os dígitos após a segunda casa são zero: `1.230 → 123` centavos; `1.231` é rejeitado sem arredondamento. No payload observado, os valores são números JSON; aceitar strings monetárias só depois de confirmar e declarar esse formato para o campo no contrato de origem.

| Campo lógico | Caminho JSON | Coluna-alvo INTEGER | Negativo permitido | Semântica do negativo |
|---|---|---|---|---|
| Depósito | `data.depositos.porUsuario[].valor` | `fatos.deposito_valor_centavos` | Sim | Estorno de depósito |
| Valor de face do acordo | `data.acordos.porUsuario[].valor` | `fatos.acordo_valor_centavos` | Não | Não usar face negativa para cancelar/descontar |
| Acordo pago | `data.acordos.porUsuario[].pagos` | `fatos.acordo_pago_centavos` | Não | Estorno por reclassificação, não pagamento negativo |
| Acordo pendente | `data.acordos.porUsuario[].pendente` | `fatos.acordo_pendente_centavos` | Sim | Crédito do cliente/pagamento a maior |
| Promessa de face | `data.promessas.porUsuario[].prometido` | `fatos.promessa_prometido_centavos` | Não | Cancelamento por status, não face negativa |
| Promessa cumprida | `data.promessas.porUsuario[].cumprido` | `fatos.promessa_cumprido_centavos` | Não | Estorno por reclassificação |
| Promessa em aberto | `data.promessas.porUsuario[].emAberto` | `fatos.promessa_em_aberto_centavos` | Sim | Crédito do cliente/pagamento a maior |
| Promessa quebrada | `data.promessas.porUsuario[].quebrado` | `fatos.promessa_quebrado_centavos` | Não | Valor de classificação não negativo |
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | `acordos_posicao.recebido_periodo_centavos` | Sim | Recebimento líquido após estornos |
| Posição a vencer | `data.valoresAcordo.valorAVencer` | `acordos_posicao.a_vencer_centavos` | Não | Posição de carteira não negativa |
| Posição vencida | `data.valoresAcordo.valorVencido` | `acordos_posicao.vencido_centavos` | Não | Posição de carteira não negativa |

Quantidades e contagens continuam inteiras, exatas e não negativas; não aceitam booleanos nem frações. No conjunto dos dados atualmente descritos não há taxa/preço unitário financeiro no payload de cobrança; se uma futura integração incluir grandeza intermediária, sua classificação e escala `_eN` deverão ser declaradas explicitamente antes da implementação.

### Esquema-alvo de `fatos`

O nome de cada coluna monetária é derivado da **métrica semântica** mais o sufixo `_centavos`, não do nome físico legado reutilizado. As oito colunas-alvo são:

- `deposito_valor_centavos`
- `acordo_valor_centavos`
- `acordo_pago_centavos`
- `acordo_pendente_centavos`
- `promessa_prometido_centavos`
- `promessa_cumprido_centavos`
- `promessa_em_aberto_centavos`
- `promessa_quebrado_centavos`

Em `acordos_posicao`, as colunas-alvo são `recebido_periodo_centavos`, `a_vencer_centavos` e `vencido_centavos`.

### Regras de NULL, CHECK e obrigatoriedade gradual

**Semântica final:** em `fatos`, `NULL` significa que a métrica não se aplica ao `tipo` da linha; `0` significa valor zero aplicável. Uma linha `contato` não utiliza nenhuma das oito métricas monetárias. Em `acordos_posicao`, as três métricas são aplicáveis ao snapshot; `NULL` só pode existir temporariamente enquanto o legado aguarda backfill, nunca como estado final de um snapshot homologado.

1. **CHECK imediato por coerência de tipo:** para cada coluna de métrica em `fatos`, aplicar uma condição equivalente a `CHECK (coluna IS NULL OR tipo = 'tipo_aplicavel')`. Assim, uma coluna não pode receber valor em tipo incorreto, mas valores `NULL` de linhas legadas ainda não preenchidas não invalidam a migração aditiva. As oito colunas devem ter condição própria; para `contato`, todas permanecem nulas.
2. **CHECK de sinal:** `deposito_valor_centavos`, `acordo_pendente_centavos` e `promessa_em_aberto_centavos` aceitam inteiros com sinal. As outras cinco colunas de `fatos` exigem `NULL` ou valor `>= 0`. Em `acordos_posicao`, `recebido_periodo_centavos` aceita sinal; `a_vencer_centavos` e `vencido_centavos` exigem `NULL` ou valor `>= 0`. As expressões precisam ser explícitas, porque um `CHECK` SQLite cujo resultado é `NULL` não falha automaticamente.
3. **Obrigatoriedade na aplicação:** após habilitar a escrita de centavos, o importador exige que toda métrica aplicável esteja presente; zero é válido e `NULL` não substitui zero. O payload completo é normalizado/validado antes de abrir a transação do dia, de modo que um único campo inválido bloqueia o dia sem gravação parcial.
4. **Diagnóstico com consciência da fase:** `diagnosticar_banco.py` distingue o backfill pendente de violações nos dados novos. Enquanto o marcador da migração indicar backfill incompleto, ausência de centavos em linhas históricas elegíveis é reportada como pendência; linhas novas escritas depois da ativação da dupla escrita que não tenham métricas aplicáveis preenchidas são falha. Após o backfill, conciliação e avanço do marcador de fase, ausência de centavos numa métrica aplicável é falha de integridade.
5. **Obrigatoriedade por trigger somente após backfill:** triggers que exigem métricas não nulas dentro de cada tipo só são criados depois que o backfill estiver concluído e conciliado. A migração aditiva inicial não pode bloquear os registros históricos ainda não convertidos.
6. **Idempotência e preservação:** colunas são adicionadas por migração versionada e idempotente. Colunas `REAL` legadas não são renomeadas, reescritas, nem removidas nesta fase. A conversão suspeita do histórico é relatada, não corrigida silenciosamente.

### Token decimal e validação antes da transação

Para tokens numéricos JSON, o parser usa validadores `parse_int` e `parse_float` que inspecionam a grafia original antes de criar `Decimal`; a gramática decimal lexical exige sinal `-` opcional, um ou mais dígitos, e opcionalmente um ponto seguido de um ou mais dígitos, sem notação científica `e/E`. `parse_constant` rejeita `NaN`, `Infinity` e `-Infinity`. A normalização rejeita booleanos explicitamente, pois em Python `bool` é subtipo de `int`. Strings decimais só podem ser aceitas se a origem/formato estiver declarado como permitido para aquele campo; nesse caso passam pela mesma regra. A normalização de todo o payload precede a transação de gravação do dia.


## Registro da política de precisão monetária recebida em 14/10/2026

A versão revisada recebida em 14/10/2026 foi registrada em [`POLITICA_PRECISAO_MONETARIA.md`](POLITICA_PRECISAO_MONETARIA.md). Além das regras de precisão e arredondamento, explicita o escopo do dashboard de Cobrança em Contas a Pagar/Financeiro e inclui regras para multa, juros simples *pro rata die*, valores de boleto e custas de cartório como dados de origem, pagamentos parciais e distinção entre pagamento confirmado e pagamento informado/pendente de baixa. A política solicita validação com TI/Contabilidade de que o ERP/módulo de títulos aplica *half-up* em juros, multas e descontos.

**Escopo documentado:** a política descreve o dashboard do setor de Cobrança dentro de Contas a Pagar/Financeiro. O importador aceita sinal negativo somente nos campos mapeados como permitidos — depósito, pendente de acordo, em aberto de promessa e recebido no período —; os demais campos monetários recusam negativos. Os sinais permanecem provisórios até validação por extração sanitizada e autorizada da origem. O auditor já usa igualdade exata em centavos, e o esquema aditivo/dupla escrita/backfill têm testes em bancos SQLite descartáveis. Nenhuma coluna `REAL` histórica foi convertida em banco real neste registro.

O registro da especificação não é execução de migração. O esquema atual usa `REAL`; preservá-lo até inventário, análise de compatibilidade, migração idempotente, backup/restauração, conciliação e rollback testado é requisito técnico. Nenhuma coluna existente foi convertida neste registro.

### Evidência e limite para a igualdade dos acordos

No payload sanitizado de 2026-10-13, as cinco linhas observadas de `acordos.porUsuario` satisfazem a igualdade `valor = pagos + pendente`; os totais agregados também coincidem nessa amostra. Isso valida apenas as linhas presentes. O payload não demonstra como a tela classifica renegociações, descontos, cancelamentos, parcelas ainda não vencidas ou pagamentos parciais. Não generalizar a amostra; definir e testar os cenários de exceção antes de torná-los bloqueantes.

A política monetária define comparação por igualdade exata em centavos e não permite tolerância de R$ 0,01. O auditor atual converte cada total e valor por usuário em centavos inteiros, calcula soma/diferença em inteiros e rejeita valores que exijam arredondamento na entrada. Testes cobrem igualdade, divergência de um centavo, precisão excedente com dígitos não zero e rejeição de `float`. A regra `valor = pagos + pendente` ainda não é imposta: depende da classificação dos cenários de renegociação, desconto, cancelamento, parcela não vencida, pagamento parcial e baixa pendente.

## Resultado da validação controlada do payload sanitizado (14/10/2026)

Os comandos abaixo foram executados contra o arquivo sanitizado fornecido, fora do repositório, sem consultar o CRM. O ambiente removeu as variáveis `CRM_URL`, `CRM_TOKEN` e `CRM_COOKIE`; o fluxo integrado reportou `crm_consultas: 0` e `banco_persistente: false`.

| Execução | Resultado observado |
|---|---|
| `python auditar_resposta.py resposta_sanitizada.json` | Código 0; 12 checks aditivos `OK`; `contatosUnicosTotal` tratado como `NÃO ADITIVO` |
| `python importar.py --arquivo resposta_sanitizada.json --dry-run` | Código 0; validação de 5 usuários e 17 fatos; nenhum banco aberto ou alterado |
| `python validar_integracao_local.py resposta_sanitizada.json` | `PASSED`; importação e reimportação em SQLite temporário; 17 fatos e 1 dia mantidos; log de importação incrementado; nenhum acesso ao CRM |
| Diagnóstico dentro da integração | 13 checks `OK`, 0 avisos e 0 falhas |

Também foram executadas regressões com cópias temporárias derivadas do payload, removidas ao final. O registro de 14/10/2026 descreve o runtime daquele momento (incluindo a antiga tolerância de R$ 0,01); não representa o comportamento atual após a auditoria por centavos inteiros. O JSON original não foi modificado.

Esta evidência fecha a pendência de executar os scripts do projeto sobre **este payload sanitizado específico**. Não prova, isoladamente, o contrato integral da API de produção, não substitui as decisões contábeis ainda abertas e não autoriza implantação. O exercício de restauração registrado na suíte automatizada usa bancos temporários e não substitui a preparação operacional exigida pelo runbook.

## Contrato observado e persistência

Todas as propriedades abaixo são observadas na amostra fictícia e implementadas pelo importador. Isso não comprova que a API real sempre as envia.

A tabela a seguir descreve o **estado atualmente observado** no importador legado, não as regras-alvo da especificação monetária v1.1. A ativação de schema/backfill continua sujeita aos gates técnicos e operacionais do plano.

| Campo lógico | Caminho JSON | Tipo/obrigatoriedade atual | Validação atual | Destino SQLite |
|---|---|---|---|---|
| Dia inicial | `data.inicio` | string, obrigatório | data ISO canônica; deve ser o dia importado | `fatos.data`, `acordos_posicao.data`, `importacoes.inicio` |
| Dia final | `data.fim` | string, obrigatório | data ISO canônica; deve ser igual ao dia importado | `importacoes.fim` |
| Sucesso | `success` | boolean true, obrigatório | exige identidade `True` | não persistido |
| Depósitos: quantidade | `data.depositos.porUsuario[].quantidade` | inteiro >= 0, obrigatório por usuário | rejeita bool, fração e negativo | `fatos.qtd`, tipo `deposito` |
| Depósitos: valor | `data.depositos.porUsuario[].valor` | valor monetário final, obrigatório por usuário | rejeita bool, texto e não finitos; aceita negativo no campo mapeado como estorno e rejeita fração subcentavo | `fatos.valor`, tipo `deposito` |
| Depósitos: totais agregados | `data.depositos.quantidadeTotal`, `valorTotal` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; valores monetários convertidos em centavos inteiros e comparados por igualdade exata | não persistidos separadamente |
| Acordos: quantidade | `data.acordos.porUsuario[].quantidade` | inteiro >= 0, obrigatório | mesmas regras de quantidade | `fatos.qtd`, tipo `acordo` |
| Acordos: valor | `data.acordos.porUsuario[].valor` | valor monetário final não negativo, obrigatório | rejeita bool, não finitos, negativos e fração subcentavo | `fatos.valor`, tipo `acordo` |
| Acordos: pagos | `data.acordos.porUsuario[].pagos` | valor monetário final não negativo, obrigatório | rejeita bool, não finitos, negativos e fração subcentavo | `fatos.valor_pago`, tipo `acordo` |
| Acordos: pendente | `data.acordos.porUsuario[].pendente` | valor monetário final, obrigatório | aceita negativo no campo mapeado como crédito; rejeita bool, não finitos e fração subcentavo | `fatos.valor_aberto`, tipo `acordo` |
| Acordos: totais agregados | `quantidadeTotal`, `valorTotal`, `pagosTotal`, `pendenteTotal` em `data.acordos` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; valores monetários convertidos em centavos inteiros e comparados por igualdade exata | não persistidos separadamente |
| Promessas: quantidade | `data.promessas.porUsuario[].quantidade` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `promessa` |
| Promessas: prometido | `data.promessas.porUsuario[].prometido` | valor monetário final não negativo, obrigatório | rejeita bool, não finitos, negativos e fração subcentavo | `fatos.valor`, tipo `promessa` |
| Promessas: cumprido | `data.promessas.porUsuario[].cumprido` | valor monetário final não negativo, obrigatório | rejeita bool, não finitos, negativos e fração subcentavo | `fatos.valor_pago`, tipo `promessa` |
| Promessas: em aberto | `data.promessas.porUsuario[].emAberto` | valor monetário final, obrigatório | aceita negativo no campo mapeado como crédito; rejeita bool, não finitos e fração subcentavo | `fatos.valor_aberto`, tipo `promessa` |
| Promessas: quebrado | `data.promessas.porUsuario[].quebrado` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_quebrado`, tipo `promessa` |
| Promessas: totais agregados | `quantidadeTotal`, `prometidoTotal`, `cumpridoTotal`, `emAbertoTotal`, `quebradoTotal` em `data.promessas` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; valores monetários convertidos em centavos inteiros e comparados por igualdade exata | não persistidos separadamente |
| Contatos: registros totais | `data.contatos.porUsuario[].registrosTotais` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `contato` |
| Contatos: contatos únicos por usuário | `data.contatos.porUsuario[].contatosUnicos` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd_unicos`, tipo `contato` |
| Contatos: registros agregados | `data.contatos.registrosTotaisTotal` | opcional para importador; auditado quando presente | reconciliação inteira exata | não persistido separadamente |
| Contatos únicos agregados | `data.contatos.contatosUnicosTotal` | observado na amostra; não aditivo | auditor exibe como não aditivo, sem reconciliação | não persistido separadamente |
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | valor monetário final, obrigatório | aceita sinal negativo para líquido de estornos; sem total por usuário para reconciliar | `acordos_posicao.recebido_periodo` |
| Valores a vencer | `data.valoresAcordo.valorAVencer` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.a_vencer` |
| Valores vencidos | `data.valoresAcordo.valorVencido` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.vencido` |
| Timestamp da resposta | `timestamp` | texto não vazio, obrigatório e fornecido pela origem | preserva exatamente a string original; rejeita ausente/vazio; não converte nem infere fuso | `acordos_posicao.capturado_em` |

O usuário é identificado por `usuario` (texto não vazio) e o nome é opcional (`nome`, texto ou null). Um mesmo identificador com nomes não vazios conflitantes dentro do payload bloqueia a normalização. Usuários repetidos dentro do mesmo grupo bloqueiam; um usuário pode aparecer em grupos diferentes. A tabela `usuarios` é atualizada pelo identificador global.

## Auditoria e severidade

Desde a proteção da Fase 6, os caminhos de gravação por arquivo e API e o modo `--dry-run` executam a auditoria antes de gravar a resposta. Qualquer check `DIVERGÊNCIA` ou `PENDENTE` bloqueia a execução com código 1; erros de estrutura/tipo continuam sendo erros de validação (código 2). A resposta da API é auditada antes de abrir/criar o SQLite na primeira data. Em uma faixa de vários dias, cada dia continua sendo transacionado separadamente: dias anteriores já gravados não são revertidos se um dia posterior falhar.

- `auditar_resposta.py` compara totais agregados disponíveis contra soma por usuário. Campos agregados ausentes viram `PENDENTE` e resultam em código 1; qualquer divergência em centavos ou contagem resulta em código 1. A auditoria soma e compara inteiros em centavos, sem tolerância; tokens monetários `float` e dígitos não zero após a segunda casa são rejeitados. Estrutura/JSON inválidos resultam em código 2.
- A importação local valida estrutura e campos obrigatórios, mas não reconcilia por si só todos os totais agregados. A rotina integrada bloqueia a importação se a auditoria não retorna código 0.
- Grupos `porUsuario` vazios são aceitos se a lista existir. Totais agregados ausentes na resposta ainda podem impedir a homologação integrada pela auditoria.
- O auditor não reconcilia `valorRecebidoPeriodo`, `valorAVencer` ou `valorVencido` com fatos por usuário; não há base comprovada para tal igualdade. Os campos `acordos.valorTotal`, `pagosTotal` e `pendenteTotal` continuam auditados individualmente contra as somas por usuário. A decisão de tornar `valor = pagos + pendente` obrigatório por usuário foi recebida em 14/10/2026, condicionada à validação dos casos de exceção; o código ainda não impõe essa relação. A tela indica valores de face classificados por status, não necessariamente caixa recebido.
- Os números de contato único por negociador não podem ser somados como clientes únicos globais sem chave de pessoa e regra de deduplicação definida.

## Questões que exigem decisão financeira

1. **Sinais por campo, ainda provisórios:** o importador permite negativos apenas em depósito, pendente de acordo, em aberto de promessa e recebido no período. Os demais campos rejeitam negativos. A semântica exata desses sinais precisa ser confrontada com extração sanitizada e autorizada da origem; não ampliar a lista de campos negativos sem evidência.
2. **Precisão monetária — implementação parcial já testada:** o parser estrito preserva `Decimal`/`int`, o auditor concilia em centavos inteiros, o esquema alvo é aditivo/idempotente e a dupla escrita/backfill têm testes sintéticos. O schema `REAL` legado segue intacto. A leitura do dashboard por centavos ainda não está integrada; corte, migração e backfill em banco real permanecem fora do que foi executado.
3. **Semântica e decisão para acordos por usuário:** `valor` representa o valor de face do acordo; `pagos` e `pendente` são colunas distintas por status e somam valores de face. `pagos` pode incluir pagamentos parciais e não significa automaticamente caixa recebido no período. **Regra funcional documentada em 14/10/2026:** `valor = pagos + pendente` deverá ser obrigatório após validar exceções. **Pendente para implementação bloqueante:** definir o tratamento para renegociações, descontos, cancelamentos, parcelas ainda não vencidas e pagamentos parciais, e criar testes de regressão para esses cenários.
4. **Decidido conforme a definição informada:** `valorRecebidoPeriodo` é o total efetivamente recebido no intervalo; `valorAVencer` é o saldo ainda pendente cujo vencimento não chegou; `valorVencido` é o saldo pendente cujo vencimento passou. Estes dois últimos representam a posição da carteira, não valores que devam ser somados entre snapshots.
5. **Comportamento atual e histórico:** a tabela `acordos_posicao` preserva capturas com diferentes `capturado_em`; não somar snapshots de dias/horários diferentes. Os fatos do mesmo dia são substituídos quando esse dia é reimportado; isso é distinto do histórico de posições.
6. **Decidido em 14/10/2026 — timestamp da origem:** usar o campo `timestamp` do JSON como referência temporal da posição atualizada e preservar seu texto exatamente como recebido. Não substituir por relógio local, não converter horário e não inferir ou completar fuso. O campo é obrigatório; se estiver ausente, vazio ou não for texto não vazio, bloquear a importação com erro de validação controlado. Se o valor não explicitar fuso, armazená-lo como veio, sem presumir um fuso.

## Precisão monetária e histórico

O esquema legado usa SQLite `REAL`; o esquema aditivo em paralelo e a conversão em centavos estão implementados e testados em bancos descartáveis, mas não foram aplicados a um banco real. A especificação `POLITICA_PRECISAO_MONETARIA.md` define `INTEGER` em centavos para valores monetários finais, sufixo `_centavos`, escalas `_eN` para grandezas intermediárias e *half-up* uma única vez no fim do cálculo. Para cobranças, a política contempla multa aplicada uma vez, juros simples *pro rata die*, boleto/custas como dados de origem e distinção entre pagamento confirmado e informado/pendente de baixa. O dashboard ainda não tem leitor integrado de centavos; não houve corte nem alteração de colunas `REAL` históricas.

Fatos diários (`fatos`) e snapshots (`acordos_posicao`) são conjuntos diferentes. Conforme definição recebida, `valorRecebidoPeriodo` representa o fluxo recebido no intervalo; `valorAVencer` e `valorVencido` são a posição da carteira na captura, classificada pela data de vencimento. Cada snapshot deve ser preservado como fotografia daquele instante, não como movimentação e não deve ser somado aos snapshots de outros instantes.

## Pendências para fechamento integral e produção

- Validar e documentar os casos de exceção à regra `valor = pagos + pendente`; só depois ativar o bloqueio e incluir testes para cada exceção identificada.
- Validar com extração sanitizada e autorizada os sinais provisórios por campo; confirmar se depósito, pendente de acordo, em aberto de promessa e recebido do período correspondem às semânticas de estorno/crédito previstas.
- A conciliação de totais monetários já usa igualdade exata em centavos inteiros; a relação `valor = pagos + pendente` por acordo e suas exceções contábeis continuam pendentes de casos de origem e testes específicos.
- Confirmar com TI/Contabilidade que o ERP/Systêxtil usa *half-up* para juros, multas e descontos. Os parâmetros comerciais e a base de dias vêm da condição comercial/ERP e não são definidos pela política.
- O esquema aditivo, a dupla escrita, o backfill e o diagnóstico por fase têm implementação e testes em SQLite sintético. Continuam pendentes: identificar todos os leitores reais, executar ensaio autorizado de backup/restauração em homologação, integrar um leitor por centavos ao dashboard e validar rollback de leitura com dados pós-corte.
- O timestamp de referência vem do campo `timestamp` do JSON. Preservar seu valor original; ausência ou vazio bloqueia a importação. Não gerar horário local nem inferir/converter fuso.
- Manter contatos únicos globais como não aditivos até existir chave e regra de deduplicação definida.
- Executar exercício operacional de backup/recuperação em ambiente de homologação autorizado, mantendo origem e backup preservados; testes automatizados isolados não substituem o ensaio operacional.
- Proteger `main` exigindo a verificação do workflow antes de integrar futuras alterações.
- Manter a evidência do payload sanitizado fora do Git e repetir comandos se o contrato ou os scripts mudarem. Não consultar o CRM para gerar evidências.

A validação automatizada do payload sanitizado corresponde ao cenário e à versão executados naquela data. A auditoria de totais e o caminho aditivo REAL/INTEGER estão implementados/testados com fixtures sintéticas. A regra `valor = pagos + pendente` permanece sem bloqueio até que os cenários de exceção sejam definidos; a leitura por centavos e os ensaios operacionais continuam pendentes.


---

## Adendo da Issue #5 — esquema por métrica (especificação técnica proposta)

**Status:** especificação proposta; não autoriza DDL, migração, backfill ou ativação operacional. As regras de sinal abaixo permanecem provisórias até validação com extração do CRM sanitizada e autorizada. Este adendo prevalece sobre formulações antigas incompatíveis com a nomenclatura semântica.

### Contrato das colunas em centavos

Todas as colunas abaixo são `INTEGER`, representam centavos de real (BRL), sem escala adicional, e mantêm as colunas históricas `REAL` inalteradas.

| Tabela | Coluna-alvo | Origem JSON | Tipo aplicável | Nulabilidade | Sinal |
|---|---|---|---|---|---|
| `fatos` | `deposito_valor_centavos` | `depositos.porUsuario[].valor` | `deposito` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | Negativo permitido (estorno) |
| `fatos` | `acordo_valor_centavos` | `acordos.porUsuario[].valor` | `acordo` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | `>= 0` |
| `fatos` | `acordo_pago_centavos` | `acordos.porUsuario[].pagos` | `acordo` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | `>= 0` |
| `fatos` | `acordo_pendente_centavos` | `acordos.porUsuario[].pendente` | `acordo` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | Negativo permitido (crédito) |
| `fatos` | `promessa_prometido_centavos` | `promessas.porUsuario[].prometido` | `promessa` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | `>= 0` |
| `fatos` | `promessa_cumprido_centavos` | `promessas.porUsuario[].cumprido` | `promessa` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | `>= 0` |
| `fatos` | `promessa_em_aberto_centavos` | `promessas.porUsuario[].emAberto` | `promessa` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | Negativo permitido (crédito) |
| `fatos` | `promessa_quebrado_centavos` | `promessas.porUsuario[].quebrado` | `promessa` | `NULL` se não aplicável; em `legado`, também pode indicar backfill pendente | `>= 0` |
| `acordos_posicao` | `recebido_periodo_centavos` | `valoresAcordo.valorRecebidoPeriodo` | Todos os snapshots | Só pode ser `NULL` transitoriamente na fase `legado`, enquanto aguarda backfill | Negativo permitido (líquido de estornos) |
| `acordos_posicao` | `a_vencer_centavos` | `valoresAcordo.valorAVencer` | Todos os snapshots | Só pode ser `NULL` transitoriamente na fase `legado`, enquanto aguarda backfill | `>= 0` |
| `acordos_posicao` | `vencido_centavos` | `valoresAcordo.valorVencido` | Todos os snapshots | Só pode ser `NULL` transitoriamente na fase `legado`, enquanto aguarda backfill | `>= 0` |

### Fase, NULL e zero

A coluna proposta `monetario_fase` é `TEXT` com `CHECK` restrito a `legado`, `dual` e `conciliado`; o padrão aditivo é `legado`. Registros históricos devem receber esse padrão. Em `fatos`, `NULL` numa métrica não aplicável é permanente e legítimo; `0` significa zero monetário real. Para `tipo = 'contato'`, as oito métricas monetárias devem ser sempre `NULL`. Em `acordos_posicao`, as três métricas se aplicam a todo snapshot; `NULL` só é tolerado como pendência transitória de linha `legado`.

Para linhas `dual` ou `conciliado`, toda métrica aplicável deve estar preenchida. Durante a transição, o importador é responsável pela obrigatoriedade de novas gravações e o diagnóstico separa pendência histórica `legado` de erro nas fases `dual`/`conciliado`. Triggers de obrigatoriedade só devem ser instalados/exercitados depois que o backfill estiver conciliado e aprovado.

### Restrições propostas

Cada coluna recebe `CHECK (col IS NULL OR typeof(col) = 'integer')`. As métricas não negativas recebem também `CHECK (col IS NULL OR col >= 0)`. Nas oito colunas de `fatos`, acrescenta-se a condição de aplicabilidade `CHECK (col IS NULL OR tipo = 'tipo_aplicavel')`. Essas constraints não impõem `valor = pagos + pendente` nem a relação equivalente das promessas; essas relações pertencem ao gate de reconciliação faseado definido em outra seção.

A afinidade `INTEGER` do SQLite pode converter o texto numérico `'123'` em inteiro antes de avaliar `typeof(col)`. Portanto, o CHECK não prova o tipo lexical do token JSON original. O parser precisa validar o token antes da coerção; o protótipo documentado na Issue #5 demonstra esse limite.

### Limite de implementação

Esta seção define o contrato-alvo por métrica. O código versionado já implementa, com testes em SQLite descartável, a migração aditiva das 11 colunas de centavos e dos marcadores de fase por linha, a escrita de fase `dual` no caminho de dupla escrita e o diagnóstico de igualdade exata REAL→centavos. Esses testes não executam nem autorizam migração/backfill em banco real ou ativação de flags. O leitor de centavos ainda não está integrado ao dashboard neste repositório; `LEITURA_CENTAVOS=1` é recusada até existir tal leitor. Os gates operacionais da Issue #17 permanecem separados.
