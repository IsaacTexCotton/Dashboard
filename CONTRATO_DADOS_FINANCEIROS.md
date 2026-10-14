# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** o JSON autorizado de um dia (2026-10-13) foi validado em 14/10/2026 com os scripts publicados no commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`; os blobs dos quatro scripts executados foram conferidos contra os hashes do GitHub. O arquivo não foi versionado. A auditoria terminou com 12 métricas aditivas `OK` e `contatosUnicosTotal` classificado como `NÃO ADITIVO`; o `--dry-run` aprovou 5 usuários e 17 fatos sem abrir banco; `validar_integracao_local.py` terminou `PASSED`, com zero consultas ao CRM e SQLite apenas temporário; o diagnóstico reportou 13 verificações `OK`, zero avisos e zero falhas. Reimportar o mesmo payload manteve os 17 fatos; o registro de importação passou de 1 para 2 e o snapshot com o mesmo timestamp permaneceu único.
- **Decisões e estado de implementação:** `valorRecebidoPeriodo` identifica recebimentos do período; `valorAVencer` e `valorVencido` representam posição da carteira e cada captura deve permanecer no histórico. Em 14/10/2026 foi recebida a política `POLITICA_PRECISAO_MONETARIA.md` (v1.0, aprovada pela Diretoria Financeira no documento fornecido): aritmética monetária exata, centavos em `INTEGER` para novas colunas, arredondamento *half-up*, uma única vez no resultado final, comparação por igualdade exata e congelamento de `REAL` legado até plano aprovado. **A versão revisada da política declara expressamente o escopo do dashboard do setor de Cobrança dentro da área de Contas a Pagar/Financeiro, portanto o conflito de escopo foi resolvido.** Permanecem conflitos entre a política e o runtime: o importador rejeita valores monetários negativos, e o auditor aceita tolerância de R$ 0,01, enquanto a política permite sinal para créditos/estornos/abatimentos e exige igualdade exata. A política não autoriza migração imediata das colunas `REAL` legadas. A decisão anterior de rejeitar todos os valores negativos e aceitar tolerância de R$ 0,01 conflita com a política revisada; esse conflito precisa ser resolvido em alteração de código própria, sem modificar automaticamente o banco legado. A igualdade `valor = pagos + pendente` continua condicionada à validação das exceções e ainda não é bloqueante.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

## Decisões de negócio recebidas em 14/10/2026

| Tema | Decisão registrada | Estado técnico |
|---|---|---|
| Acordos por usuário | `valor = pagos + pendente` deve ser obrigatório após validar exceções | Ainda não bloqueante. É necessário definir como identificar e tratar renegociações, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais antes de ativar o bloqueio |
| Precisão monetária | `POLITICA_PRECISAO_MONETARIA.md` v1.0 é a versão formalmente aprovada; proposta v1.1 registrada em branch documental, pendente de assinatura | A proposta v1.1 define valores finais com no máximo duas casas efetivas (zeros excedentes são aceitos), regras decimais exatas, sinais por campo, `REAL` congelado com escrita legada preservada até descomissionamento e colunas por métrica. Nenhuma regra nova é aplicada pelo runtime antes da assinatura e da integração da versão aprovada |
| Timestamp da captura | Usar e preservar exatamente o campo `timestamp` enviado no JSON da origem, como referência temporal da posição atualizada | Decidido em 14/10/2026: não substituir por relógio local nem inferir/converter fuso; campo ausente ou vazio deve bloquear a importação |
| Contatos únicos globais | Não existe chave/regra aprovada para deduplicação entre negociadores | Manter `contatosUnicosTotal` como não aditivo; não somar por usuário nem usar essa métrica como gate de reconciliação |

 
## Proposta de contrato monetário v1.1 — pendente de assinatura

Esta seção registra o contrato-alvo proposto para alinhar o esquema por métrica e a política v1.1. **Não descreve o comportamento atual do importador**, que ainda rejeita todos os valores negativos e faz parsing monetário por `float`. As mudanças não devem ser ativadas antes da assinatura formal da Política v1.1 e da aprovação do plano de migração.

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

Para tokens numéricos JSON, o parser usa validadores `parse_int` e `parse_float` que inspecionam a grafia original antes de criar `Decimal`; o formato lexical permitido é `^-?\d+(\\.\d+)?# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** o JSON autorizado de um dia (2026-10-13) foi validado em 14/10/2026 com os scripts publicados no commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`; os blobs dos quatro scripts executados foram conferidos contra os hashes do GitHub. O arquivo não foi versionado. A auditoria terminou com 12 métricas aditivas `OK` e `contatosUnicosTotal` classificado como `NÃO ADITIVO`; o `--dry-run` aprovou 5 usuários e 17 fatos sem abrir banco; `validar_integracao_local.py` terminou `PASSED`, com zero consultas ao CRM e SQLite apenas temporário; o diagnóstico reportou 13 verificações `OK`, zero avisos e zero falhas. Reimportar o mesmo payload manteve os 17 fatos; o registro de importação passou de 1 para 2 e o snapshot com o mesmo timestamp permaneceu único.
- **Decisões e estado de implementação:** `valorRecebidoPeriodo` identifica recebimentos do período; `valorAVencer` e `valorVencido` representam posição da carteira e cada captura deve permanecer no histórico. Em 14/10/2026 foi recebida a política `POLITICA_PRECISAO_MONETARIA.md` (v1.0, aprovada pela Diretoria Financeira no documento fornecido): aritmética monetária exata, centavos em `INTEGER` para novas colunas, arredondamento *half-up*, uma única vez no resultado final, comparação por igualdade exata e congelamento de `REAL` legado até plano aprovado. **A versão revisada da política declara expressamente o escopo do dashboard do setor de Cobrança dentro da área de Contas a Pagar/Financeiro, portanto o conflito de escopo foi resolvido.** Permanecem conflitos entre a política e o runtime: o importador rejeita valores monetários negativos, e o auditor aceita tolerância de R$ 0,01, enquanto a política permite sinal para créditos/estornos/abatimentos e exige igualdade exata. A política não autoriza migração imediata das colunas `REAL` legadas. A decisão anterior de rejeitar todos os valores negativos e aceitar tolerância de R$ 0,01 conflita com a política revisada; esse conflito precisa ser resolvido em alteração de código própria, sem modificar automaticamente o banco legado. A igualdade `valor = pagos + pendente` continua condicionada à validação das exceções e ainda não é bloqueante.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

## Decisões de negócio recebidas em 14/10/2026

| Tema | Decisão registrada | Estado técnico |
|---|---|---|
| Acordos por usuário | `valor = pagos + pendente` deve ser obrigatório após validar exceções | Ainda não bloqueante. É necessário definir como identificar e tratar renegociações, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais antes de ativar o bloqueio |
| Precisão monetária | `POLITICA_PRECISAO_MONETARIA.md` v1.0 é a versão formalmente aprovada; proposta v1.1 registrada em branch documental, pendente de assinatura | A proposta v1.1 define valores finais com no máximo duas casas efetivas (zeros excedentes são aceitos), regras decimais exatas, sinais por campo, `REAL` congelado com escrita legada preservada até descomissionamento e colunas por métrica. Nenhuma regra nova é aplicada pelo runtime antes da assinatura e da integração da versão aprovada |
| Timestamp da captura | Usar e preservar exatamente o campo `timestamp` enviado no JSON da origem, como referência temporal da posição atualizada | Decidido em 14/10/2026: não substituir por relógio local nem inferir/converter fuso; campo ausente ou vazio deve bloquear a importação |
| Contatos únicos globais | Não existe chave/regra aprovada para deduplicação entre negociadores | Manter `contatosUnicosTotal` como não aditivo; não somar por usuário nem usar essa métrica como gate de reconciliação |

 
, sem notação científica. `parse_constant` rejeita `NaN`, `Infinity` e `-Infinity`. A normalização rejeita booleanos explicitamente, pois em Python `bool` é subtipo de `int`. Strings decimais só podem ser aceitas se a origem/formato estiver declarado como permitido para aquele campo; nesse caso passam pela mesma regra. A normalização de todo o payload precede a transação de gravação do dia.

## Registro da política de precisão monetária recebida em 14/10/2026

A versão revisada recebida em 14/10/2026 foi registrada em [`POLITICA_PRECISAO_MONETARIA.md`](POLITICA_PRECISAO_MONETARIA.md). Além das regras de precisão e arredondamento, explicita o escopo do dashboard de Cobrança em Contas a Pagar/Financeiro e inclui regras para multa, juros simples *pro rata die*, valores de boleto e custas de cartório como dados de origem, pagamentos parciais e distinção entre pagamento confirmado e pagamento informado/pendente de baixa. A política solicita validação com TI/Contabilidade de que o ERP/módulo de títulos aplica *half-up* em juros, multas e descontos.

**Escopo confirmado:** a versão revisada da política nomeia explicitamente o dashboard do setor de Cobrança dentro de Contas a Pagar/Financeiro. A política aplica-se ao escopo funcional descrito e está versionada no repositório. Permanecem dois conflitos concretos de implementação: (1) o importador atual rejeita todo valor monetário negativo, enquanto a política permite sinal negativo para créditos, estornos e abatimentos; (2) o auditor atual aceita diferença agregada até R$ 0,01, enquanto a política proíbe tolerância monetária e determina igualdade exata de inteiros em centavos. Também falta implementar e testar a representação exata em centavos para novas gravações monetárias; isso não autoriza converter as colunas `REAL` já existentes sem análise e plano aprovados.

A aprovação do texto de política não equivale à aprovação de uma migração do banco atual. O esquema usa `REAL`; preservá-lo até análise/ plano de compatibilidade é requisito explícito da política. Nenhuma coluna existente foi convertida neste registro.

### Evidência e limite para a igualdade dos acordos

No payload sanitizado de 2026-10-13, as cinco linhas de `acordos.porUsuario` satisfazem a igualdade observada: `valor` coincide com `pagos + pendente`; os totais agregados também coincidem nessa amostra. Isso valida apenas as linhas presentes. O payload não demonstra como a tela classifica renegociações, descontos, cancelamentos, parcelas ainda não vencidas ou casos específicos de pagamentos parciais. Portanto, não generalizar a amostra para todos os cenários e não habilitar rejeição automática até que esses casos tenham regra aprovada e testes de regressão.

A política monetária revisada determina comparação por igualdade exata de inteiros e proíbe tolerância (`abs(a-b) < 0.01`). A auditoria atualmente implementada ainda aceita até R$ 0,01 e usa números em ponto flutuante; essa parte não está em conformidade com a política. A mudança deve ocorrer junto de parsing decimal exato/conversão para centavos e testes específicos, sem alterar as colunas `REAL` legadas antes do plano de migração. A regra de exceções para `valor = pagos + pendente` continua separada e precisa ser aprovada antes do bloqueio.

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

A tabela a seguir descreve o **estado atualmente observado** no importador legado, não as regras-alvo da proposta monetária v1.1. As regras de sinais, parsing, colunas por métrica e obrigatoriedade transicional constam na seção `Proposta de contrato monetário v1.1 — pendente de assinatura`, acima, e só podem ser aplicadas após ratificação formal.

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

1. **Comportamento atual, em conflito a resolver:** o importador rejeita qualquer valor monetário negativo. A política permite valores negativos para créditos, estornos e abatimentos. Antes de aceitar sinais negativos no JSON, mapear quais campos podem representar cada operação, confirmar como a origem informa esses valores e incluir testes de regressão. Não permitir negativos indiscriminadamente em todos os campos.
2. **Precisão monetária aprovada — escopo já confirmado:** a política prevê *half-up*, uma única vez no resultado final; entrada de decimais com mais de duas casas como texto; novos valores finais em `INTEGER` de centavos (`_centavos`); escalas inteiras `_eN` para grandezas intermediárias; aritmética exata e comparações monetárias por igualdade exata, sem tolerância. O runtime diverge: a auditoria aceita até R$ 0,01 e o fluxo atual usa ponto flutuante. Preparar conversão de entrada decimal exata, novas colunas paralelas e reconciliação; não converter nem remover colunas `REAL` existentes antes de inventário, análise de compatibilidade, backup íntegro, migração idempotente, dupla escrita/conciliação, aprovação da Controladoria e rollback testado.
3. **Semântica e decisão para acordos por usuário:** `valor` representa o valor de face do acordo; `pagos` e `pendente` são colunas distintas por status e somam valores de face. `pagos` pode incluir pagamentos parciais e não significa automaticamente caixa recebido no período. **Decidido em 14/10/2026:** `valor = pagos + pendente` deverá ser obrigatório após validar exceções. **Pendente para implementação bloqueante:** inventariar e aprovar o tratamento para renegociações, descontos, cancelamentos, parcelas ainda não vencidas e pagamentos parciais, e criar testes de regressão para esses cenários.
4. **Decidido conforme a definição informada:** `valorRecebidoPeriodo` é o total efetivamente recebido no intervalo; `valorAVencer` é o saldo ainda pendente cujo vencimento não chegou; `valorVencido` é o saldo pendente cujo vencimento passou. Estes dois últimos representam a posição da carteira, não valores que devam ser somados entre snapshots.
5. **Comportamento atual e histórico:** a tabela `acordos_posicao` preserva capturas com diferentes `capturado_em`; não somar snapshots de dias/horários diferentes. Os fatos do mesmo dia são substituídos quando esse dia é reimportado; isso é distinto do histórico de posições.
6. **Decidido em 14/10/2026 — timestamp da origem:** usar o campo `timestamp` do JSON como referência temporal da posição atualizada e preservar seu texto exatamente como recebido. Não substituir por relógio local, não converter horário e não inferir ou completar fuso. O campo é obrigatório; se estiver ausente, vazio ou não for texto não vazio, bloquear a importação com erro de validação controlado. Se o valor não explicitar fuso, armazená-lo como veio, sem presumir um fuso.

## Precisão monetária e histórico

O esquema atual usa SQLite `REAL`. A política revisada em `POLITICA_PRECISAO_MONETARIA.md` v1.0 tem escopo explícito de Cobrança dentro de Contas a Pagar/Financeiro e define aritmética inteira/decimal exata, `INTEGER` em centavos para novos valores monetários finais, sufixo `_centavos`, escalas inteiras `_eN` para grandezas intermediárias, *half-up* e um único arredondamento no fim do cálculo. Para cálculos de cobrança, define multa aplicada uma vez, juros simples *pro rata die*, valor atualizado formado por original + multa + juros − descontos/abatimentos, pagamento parcial deduzido em centavos inteiros, custas de cartório importadas como valor de origem e boleto emitido como valor oficial não recalculado pelo app; os parâmetros comerciais e a base de dias continuam vindo do contrato/ERP (Systêxtil). O dashboard deve distinguir pagamento confirmado de pagamento informado/pendente de baixa. Valores com mais de duas casas entram como texto decimal, nunca por `float`, e reconciliações usam igualdade exata dos inteiros, sem tolerância. A política determina congelar `REAL` legado até inventário, análise de consumidores, migração idempotente para colunas paralelas, dupla escrita/conciliação, aprovação da Controladoria, rollback testado e descomissionamento separado. Nenhuma coluna foi convertida neste registro. O código atual não implementa integralmente a nova precisão nem os cálculos de cobrança especificados.

Fatos diários (`fatos`) e snapshots (`acordos_posicao`) são conjuntos diferentes. Conforme definição recebida, `valorRecebidoPeriodo` representa o fluxo recebido no intervalo; `valorAVencer` e `valorVencido` são a posição da carteira na captura, classificada pela data de vencimento. Cada snapshot deve ser preservado como fotografia daquele instante, não como movimentação e não deve ser somado aos snapshots de outros instantes.

## Pendências para fechamento integral e produção

- Validar e documentar os casos de exceção à regra `valor = pagos + pendente`; só depois ativar o bloqueio e incluir testes para cada exceção aprovada.
- Resolver o conflito entre a rejeição atual de valores negativos e a política que permite sinais para créditos, estornos e abatimentos; mapear os campos JSON afetados e testar cada caso.
- Remover a tolerância monetária de R$ 0,01 em favor de comparação exata somente junto da adoção de parsing decimal exato e comparação em centavos inteiros, com testes de fronteira.
- Confirmar com TI/Contabilidade que o ERP/Systêxtil usa *half-up* para juros, multas e descontos. Os parâmetros comerciais e a base de dias vêm da condição comercial/ERP e não são definidos pela política.
- Projetar novas colunas `INTEGER` em centavos e transição a partir dos `REAL` legados conforme inventário, análise de compatibilidade, backup íntegro, migração idempotente, dupla escrita/conciliação, aprovação da Controladoria e rollback testado. Não migrar esquema neste momento.
- O timestamp de referência vem do campo `timestamp` do JSON. Preservar seu valor original; ausência ou vazio bloqueia a importação. Não gerar horário local nem inferir/converter fuso.
- Manter contatos únicos globais como não aditivos até existir chave e regra aprovada de deduplicação.
- Executar exercício operacional de backup/recuperação em banco de homologação autorizado, mantendo origem e backup preservados; testes automatizados isolados não substituem a aprovação operacional.
- Proteger `main` exigindo a verificação do workflow antes de integrar futuras alterações.
- Manter a evidência do payload sanitizado fora do Git e repetir comandos se o contrato ou os scripts mudarem. Não consultar o CRM para gerar evidências.

A validação automatizada deste payload sanitizado está concluída. A igualdade dos acordos e a precisão monetária foram decididas em princípio, mas seus requisitos ainda não estão todos prontos para bloqueio/alteração de esquema; as pendências acima continuam sendo gates antes de produção.
