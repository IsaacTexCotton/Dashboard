# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** o JSON autorizado de um dia (2026-10-13) foi validado em 14/10/2026 com os scripts publicados no commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`; os blobs dos quatro scripts executados foram conferidos contra os hashes do GitHub. O arquivo não foi versionado. A auditoria terminou com 12 métricas aditivas `OK` e `contatosUnicosTotal` classificado como `NÃO ADITIVO`; o `--dry-run` aprovou 5 usuários e 17 fatos sem abrir banco; `validar_integracao_local.py` terminou `PASSED`, com zero consultas ao CRM e SQLite apenas temporário; o diagnóstico reportou 13 verificações `OK`, zero avisos e zero falhas. Reimportar o mesmo payload manteve os 17 fatos; o registro de importação passou de 1 para 2 e o snapshot com o mesmo timestamp permaneceu único.
- **Decisões e estado de implementação:** `valorRecebidoPeriodo` identifica recebimentos do período; `valorAVencer` e `valorVencido` representam posição da carteira e cada captura deve permanecer no histórico. Em 14/10/2026 foi recebida a política `POLITICA_PRECISAO_MONETARIA.md` (v1.0, aprovada pela Diretoria Financeira no documento fornecido): aritmética monetária exata, centavos em `INTEGER` para novas colunas, arredondamento *half-up*, uma única vez no resultado final, comparação por igualdade exata e congelamento de `REAL` legado até plano aprovado. **A política declara escopo de Contas a Pagar, enquanto este contrato descreve o CAIXA FUTURO com métricas de acordos/cobrança; a aplicabilidade ao projeto precisa ser confirmada antes de alterar o comportamento.** O runtime atual ainda rejeita valores negativos e aceita tolerância de R$ 0,01 na auditoria, portanto esses comportamentos estão em conflito com partes da política fornecida. A decisão anterior sobre valores negativos e tolerância não deve ser considerada conciliada com a política até resolver esse conflito de escopo. A igualdade `valor = pagos + pendente` continua condicionada à validação das exceções e ainda não é bloqueante.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

## Decisões de negócio recebidas em 14/10/2026

| Tema | Decisão registrada | Estado técnico |
|---|---|---|
| Acordos por usuário | `valor = pagos + pendente` deve ser obrigatório após validar exceções | Ainda não bloqueante. É necessário definir como identificar e tratar renegociações, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais antes de ativar o bloqueio |
| Precisão monetária | Política `POLITICA_PRECISAO_MONETARIA.md` v1.0 fornecida como aprovada pela Diretoria Financeira | Parâmetros estão transcritos; falta confirmar a aplicabilidade do escopo (o documento diz Contas a Pagar) ao CAIXA FUTURO e resolver conflitos com validação atual. Sem migração até inventário, compatibilidade e plano aprovados |
| Timestamp da captura | Usar e preservar exatamente o campo `timestamp` enviado no JSON da origem, como referência temporal da posição atualizada | Decidido em 14/10/2026: não substituir por relógio local nem inferir/converter fuso; campo ausente ou vazio deve bloquear a importação |
| Contatos únicos globais | Não existe chave/regra aprovada para deduplicação entre negociadores | Manter `contatosUnicosTotal` como não aditivo; não somar por usuário nem usar essa métrica como gate de reconciliação |

 
## Registro da política de precisão monetária recebida em 14/10/2026

O documento fornecido foi versionado sem alteração substantiva em [`POLITICA_PRECISAO_MONETARIA.md`](POLITICA_PRECISAO_MONETARIA.md). Ele estabelece: armazenamento de novos valores monetários finais como inteiros em centavos com sufixo `_centavos`; preços unitários, quantidades e taxas como inteiros escalados (`_eN`); método *half-up* (meio para longe do zero); uma única etapa de arredondamento ao final do cálculo; entrada de valores com mais de duas casas como texto decimal, nunca via `float`; comparação monetária por igualdade exata em centavos; e proibição de alterar colunas legadas `REAL` antes de análise de compatibilidade e plano de migração aprovado. O documento ainda solicita confirmação de que ERP/módulo de títulos usa *half-up* para juros, multas e descontos.

**Alerta de escopo e conflito:** o título e o escopo do documento recebido referem-se a um dashboard de **Contas a Pagar**. Este contrato do CAIXA FUTURO descreve dados de acordos, pagamentos e cobrança. Até que a Diretoria Financeira/Controladoria confirme por escrito que a política abrange este projeto, ela fica registrada como documento fornecido, mas não se deve inferir autorização para alterar a lógica de runtime. Há dois conflitos concretos que precisam ser resolvidos se a política se aplicar: (1) o importador atual rejeita todo valor monetário negativo, enquanto a política permite sinal negativo para créditos, estornos e abatimentos; (2) o auditor atual aceita diferença agregada até R$ 0,01, enquanto a política proíbe tolerância monetária e determina igualdade exata de inteiros em centavos.

A aprovação do texto de política não equivale à aprovação de uma migração do banco atual. O esquema usa `REAL`; preservá-lo até análise/ plano de compatibilidade é requisito explícito da política. Nenhuma coluna existente foi convertida neste registro.

### Evidência e limite para a igualdade dos acordos

No payload sanitizado de 2026-10-13, as cinco linhas de `acordos.porUsuario` satisfazem a igualdade observada: `valor` coincide com `pagos + pendente`; os totais agregados também coincidem nessa amostra. Isso valida apenas as linhas presentes. O payload não demonstra como a tela classifica renegociações, descontos, cancelamentos, parcelas ainda não vencidas ou casos específicos de pagamentos parciais. Portanto, não generalizar a amostra para todos os cenários e não habilitar rejeição automática até que esses casos tenham regra aprovada e testes de regressão.

A política monetária fornecida determina comparação por igualdade exata de inteiros e proíbe tolerância (`abs(a-b) < 0.01`). A auditoria atualmente implementada ainda aceita até R$ 0,01 e usa números em ponto flutuante; não declarar essa parte homologada pela política. Após confirmação de escopo, a mudança deve ocorrer junto de parsing decimal exato/conversão para centavos e testes específicos. A regra de exceções para `valor = pagos + pendente` continua separada e precisa ser aprovada antes do bloqueio.

## Resultado da validação controlada do payload sanitizado (14/10/2026)

Os comandos abaixo foram executados contra o arquivo sanitizado fornecido, fora do repositório, sem consultar o CRM. O ambiente removeu as variáveis `CRM_URL`, `CRM_TOKEN` e `CRM_COOKIE`; o fluxo integrado reportou `crm_consultas: 0` e `banco_persistente: false`.

| Execução | Resultado observado |
|---|---|
| `python auditar_resposta.py resposta_sanitizada.json` | Código 0; 12 checks aditivos `OK`; `contatosUnicosTotal` tratado como `NÃO ADITIVO` |
| `python importar.py --arquivo resposta_sanitizada.json --dry-run` | Código 0; validação de 5 usuários e 17 fatos; nenhum banco aberto ou alterado |
| `python validar_integracao_local.py resposta_sanitizada.json` | `PASSED`; importação e reimportação em SQLite temporário; 17 fatos e 1 dia mantidos; log de importação incrementado; nenhum acesso ao CRM |
| Diagnóstico dentro da integração | 13 checks `OK`, 0 avisos e 0 falhas |

Também foram executadas regressões com cópias temporárias derivadas do payload, removidas ao final: diferença monetária de R$ 0,01 aprovada; diferença de R$ 0,02 bloqueada; `valorVencido` negativo rejeitado pela importação com código 2, mensagem controlada e sem criação de banco. O JSON original não foi modificado.

Esta evidência fecha a pendência de executar os scripts do projeto sobre **este payload sanitizado específico**. Não prova, isoladamente, o contrato integral da API de produção, não substitui as decisões contábeis ainda abertas e não autoriza implantação. O exercício de restauração registrado na suíte automatizada usa bancos temporários e não substitui a preparação operacional exigida pelo runbook.

## Contrato observado e persistência

Todas as propriedades abaixo são observadas na amostra fictícia e implementadas pelo importador. Isso não comprova que a API real sempre as envia.

| Campo lógico | Caminho JSON | Tipo/obrigatoriedade atual | Validação atual | Destino SQLite |
|---|---|---|---|---|
| Dia inicial | `data.inicio` | string, obrigatório | data ISO canônica; deve ser o dia importado | `fatos.data`, `acordos_posicao.data`, `importacoes.inicio` |
| Dia final | `data.fim` | string, obrigatório | data ISO canônica; deve ser igual ao dia importado | `importacoes.fim` |
| Sucesso | `success` | boolean true, obrigatório | exige identidade `True` | não persistido |
| Depósitos: quantidade | `data.depositos.porUsuario[].quantidade` | inteiro >= 0, obrigatório por usuário | rejeita bool, fração e negativo | `fatos.qtd`, tipo `deposito` |
| Depósitos: valor | `data.depositos.porUsuario[].valor` | número finito não negativo, obrigatório por usuário | rejeita bool, texto, não finito e negativo | `fatos.valor`, tipo `deposito` |
| Depósitos: totais agregados | `data.depositos.quantidadeTotal`, `valorTotal` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | estado atual: quantidade exata; monetários com tolerância R$ 0,01 — conflito com a política fornecida se ela se aplicar | não persistidos separadamente |
| Acordos: quantidade | `data.acordos.porUsuario[].quantidade` | inteiro >= 0, obrigatório | mesmas regras de quantidade | `fatos.qtd`, tipo `acordo` |
| Acordos: valor | `data.acordos.porUsuario[].valor` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor`, tipo `acordo` |
| Acordos: pagos | `data.acordos.porUsuario[].pagos` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_pago`, tipo `acordo` |
| Acordos: pendente | `data.acordos.porUsuario[].pendente` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_aberto`, tipo `acordo` |
| Acordos: totais agregados | `quantidadeTotal`, `valorTotal`, `pagosTotal`, `pendenteTotal` em `data.acordos` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | estado atual: contagem exata; monetários com tolerância R$ 0,01 — conflito com a política fornecida se ela se aplicar | não persistidos separadamente |
| Promessas: quantidade | `data.promessas.porUsuario[].quantidade` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `promessa` |
| Promessas: prometido | `data.promessas.porUsuario[].prometido` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor`, tipo `promessa` |
| Promessas: cumprido | `data.promessas.porUsuario[].cumprido` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_pago`, tipo `promessa` |
| Promessas: em aberto | `data.promessas.porUsuario[].emAberto` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_aberto`, tipo `promessa` |
| Promessas: quebrado | `data.promessas.porUsuario[].quebrado` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_quebrado`, tipo `promessa` |
| Promessas: totais agregados | `quantidadeTotal`, `prometidoTotal`, `cumpridoTotal`, `emAbertoTotal`, `quebradoTotal` em `data.promessas` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | estado atual: contagem exata; monetários com tolerância R$ 0,01 — conflito com a política fornecida se ela se aplicar | não persistidos separadamente |
| Contatos: registros totais | `data.contatos.porUsuario[].registrosTotais` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `contato` |
| Contatos: contatos únicos por usuário | `data.contatos.porUsuario[].contatosUnicos` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd_unicos`, tipo `contato` |
| Contatos: registros agregados | `data.contatos.registrosTotaisTotal` | opcional para importador; auditado quando presente | reconciliação inteira exata | não persistido separadamente |
| Contatos únicos agregados | `data.contatos.contatosUnicosTotal` | observado na amostra; não aditivo | auditor exibe como não aditivo, sem reconciliação | não persistido separadamente |
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | número finito não negativo, obrigatório | sem total por usuário para reconciliar | `acordos_posicao.recebido_periodo` |
| Valores a vencer | `data.valoresAcordo.valorAVencer` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.a_vencer` |
| Valores vencidos | `data.valoresAcordo.valorVencido` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.vencido` |
| Timestamp da resposta | `timestamp` | texto não vazio, obrigatório e fornecido pela origem | preserva exatamente a string original; rejeita ausente/vazio; não converte nem infere fuso | `acordos_posicao.capturado_em` |

O usuário é identificado por `usuario` (texto não vazio) e o nome é opcional (`nome`, texto ou null). Um mesmo identificador com nomes não vazios conflitantes dentro do payload bloqueia a normalização. Usuários repetidos dentro do mesmo grupo bloqueiam; um usuário pode aparecer em grupos diferentes. A tabela `usuarios` é atualizada pelo identificador global.

## Auditoria e severidade

Desde a proteção da Fase 6, os caminhos de gravação por arquivo e API e o modo `--dry-run` executam a auditoria antes de gravar ou aprovar a resposta. Qualquer check `DIVERGÊNCIA` ou `PENDENTE` bloqueia a execução com código 1; erros de estrutura/tipo continuam sendo erros de validação (código 2). A resposta da API é auditada antes de abrir/criar o SQLite na primeira data. Em uma faixa de vários dias, cada dia continua sendo transacionado separadamente: dias anteriores já gravados não são revertidos se um dia posterior falhar.

- `auditar_resposta.py` compara totais agregados disponíveis contra soma por usuário. Campos agregados ausentes viram `PENDENTE` e resultam em código 1; estado atual: divergência monetária acima de R$ 0,01 ou divergência inteira resulta em código 1. A tolerância financeira diverge da política fornecida, que exige igualdade exata de inteiros; corrigir somente após confirmar escopo e preparar parsing exato em centavos. Estrutura/JSON inválidos resultam em código 2.
- A importação local valida estrutura e campos obrigatórios, mas não reconcilia por si só todos os totais agregados. A rotina integrada bloqueia a importação se a auditoria não retorna código 0.
- Grupos `porUsuario` vazios são aceitos se a lista existir. Totais agregados ausentes na resposta ainda podem impedir a homologação integrada pela auditoria.
- O auditor não reconcilia `valorRecebidoPeriodo`, `valorAVencer` ou `valorVencido` com fatos por usuário; não há base comprovada para tal igualdade. Os campos `acordos.valorTotal`, `pagosTotal` e `pendenteTotal` continuam auditados individualmente contra as somas por usuário. A decisão de tornar `valor = pagos + pendente` obrigatório por usuário foi recebida em 14/10/2026, condicionada à validação dos casos de exceção; o código ainda não impõe essa relação. A tela indica valores de face classificados por status, não necessariamente caixa recebido.
- Os números de contato único por negociador não podem ser somados como clientes únicos globais sem chave de pessoa e regra de deduplicação aprovada.

## Questões que exigem decisão financeira

1. **Comportamento atual, em conflito a resolver:** o importador rejeita qualquer valor monetário negativo. A política fornecida permite valores negativos para créditos, estornos e abatimentos. Não alterar silenciosamente essa validação enquanto não for confirmada a aplicabilidade da política ao CAIXA FUTURO e especificada a semântica de cada campo do JSON.
2. **Precisão aprovada no documento fornecido:** *half-up*, uma única vez no final do cálculo; leitura de valores com mais de duas casas como texto decimal; novos valores monetários finais em `INTEGER` de centavos, nomes terminados em `_centavos`; cálculos exatos e comparações por igualdade exata, sem tolerância. **Conflito atual:** o auditor aceita diferença de R$ 0,01 e os valores são lidos/armazenados como números `REAL`/ponto flutuante. Confirmar por escrito que a política cujo escopo está descrito como Contas a Pagar também se aplica a este projeto; depois elaborar plano de parsing/conversão e de coexistência/migração. O esquema SQLite atual usa `REAL`; não converter nem remover colunas existentes sem análise de compatibilidade, backup íntegro, plano idempotente, dupla escrita/conciliação e rollback aprovados.
3. **Semântica e decisão para acordos por usuário:** `valor` representa o valor de face do acordo; `pagos` e `pendente` são colunas distintas por status e somam valores de face. `pagos` pode incluir pagamentos parciais e não significa automaticamente caixa recebido no período. **Decidido em 14/10/2026:** `valor = pagos + pendente` deverá ser obrigatório após validar exceções. **Pendente para implementação bloqueante:** inventariar e aprovar o tratamento para renegociações, descontos, cancelamentos, parcelas ainda não vencidas e pagamentos parciais, e criar testes de regressão para esses cenários.
4. **Decidido conforme a definição informada:** `valorRecebidoPeriodo` é o total efetivamente recebido no intervalo; `valorAVencer` é o saldo ainda pendente cujo vencimento não chegou; `valorVencido` é o saldo pendente cujo vencimento passou. Estes dois últimos representam a posição da carteira, não valores que devam ser somados entre snapshots.
5. **Comportamento atual e histórico:** a tabela `acordos_posicao` preserva capturas com diferentes `capturado_em`; não somar snapshots de dias/horários diferentes. Os fatos do mesmo dia são substituídos quando esse dia é reimportado; isso é distinto do histórico de posições.
6. **Decidido em 14/10/2026 — timestamp da origem:** usar o campo `timestamp` do JSON como referência temporal da posição atualizada e preservar seu texto exatamente como recebido. Não substituir por relógio local, não converter horário e não inferir ou completar fuso. O campo é obrigatório; se estiver ausente, vazio ou não for texto não vazio, bloquear a importação com erro de validação controlado. Se o valor não explicitar fuso, armazená-lo como veio, sem presumir um fuso.

## Precisão monetária e histórico

O esquema atual usa SQLite `REAL`. A política fornecida em `POLITICA_PRECISAO_MONETARIA.md` v1.0 define aritmética inteira/decimal exata, `INTEGER` em centavos para novos valores monetários finais, sufixo `_centavos`, escalas inteiras `_eN` para grandezas de precisão maior, *half-up* e um único arredondamento no fim do cálculo. Valores com mais de duas casas devem entrar como texto decimal, nunca por `float`, e reconciliações monetárias devem usar igualdade exata dos inteiros, sem tolerância. A política determina congelar colunas `REAL` legadas até conclusão de inventário de consumidores/escritores, medição de divergências, análise de consultas/índices/views/exportações, desenho de convivência, backup verificado, novas colunas paralelas preenchidas por migração idempotente via `real_para_centavos`, dupla escrita e conciliação, aprovação da Controladoria para corte, rollback testado e descomissionamento separado. Nenhuma coluna foi convertida neste registro. Como o escopo do documento recebido diz Contas a Pagar, enquanto o contrato descreve dados de cobrança/acordos, a aplicabilidade deve ser formalmente confirmada antes de transformar esses requisitos em alterações de runtime.

Fatos diários (`fatos`) e snapshots (`acordos_posicao`) são conjuntos diferentes. Conforme definição recebida, `valorRecebidoPeriodo` representa o fluxo recebido no intervalo; `valorAVencer` e `valorVencido` são a posição da carteira na captura, classificada pela data de vencimento. Cada snapshot deve ser preservado como fotografia daquele instante, não como movimentação e não deve ser somado aos snapshots de outros instantes.

## Pendências para fechamento integral e produção

- Validar e documentar os casos de exceção à regra `valor = pagos + pendente`; só depois ativar o bloqueio e incluir testes para cada exceção aprovada.
- Confirmar por escrito que a política em `POLITICA_PRECISAO_MONETARIA.md` (cujo escopo formal declara Contas a Pagar) se aplica também ao CAIXA FUTURO; validar com TI/Contabilidade o uso de *half-up* pelo ERP para juros, multas e descontos.
- Após essa confirmação, projetar parsing decimal sem `float`, novas colunas `INTEGER` em centavos, comparações exatas e transição a partir dos `REAL` legados conforme análise de compatibilidade, backup íntegro, migração idempotente, dupla escrita/conciliação, aprovação da Controladoria e rollback testado. Não migrar esquema neste momento.
- O timestamp de referência vem do campo `timestamp` do JSON. Preservar seu valor original; ausência ou vazio bloqueia a importação. Não gerar horário local nem inferir/converter fuso.
- Manter contatos únicos globais como não aditivos até existir chave e regra aprovada de deduplicação.
- Executar exercício operacional de backup/recuperação em banco de homologação autorizado, mantendo origem e backup preservados; testes automatizados isolados não substituem a aprovação operacional.
- Proteger `main` exigindo a verificação do workflow antes de integrar futuras alterações.
- Manter a evidência do payload sanitizado fora do Git e repetir comandos se o contrato ou os scripts mudarem. Não consultar o CRM para gerar evidências.

A validação automatizada deste payload sanitizado está concluída. A igualdade dos acordos e a precisão monetária foram decididas em princípio, mas seus requisitos ainda não estão todos prontos para bloqueio/alteração de esquema; as pendências acima continuam sendo gates antes de produção.
