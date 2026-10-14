# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** o JSON autorizado de um dia (2026-10-13) foi validado em 14/10/2026 com os scripts publicados no commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`; os blobs dos quatro scripts executados foram conferidos contra os hashes do GitHub. O arquivo não foi versionado. A auditoria terminou com 12 métricas aditivas `OK` e `contatosUnicosTotal` classificado como `NÃO ADITIVO`; o `--dry-run` aprovou 5 usuários e 17 fatos sem abrir banco; `validar_integracao_local.py` terminou `PASSED`, com zero consultas ao CRM e SQLite apenas temporário; o diagnóstico reportou 13 verificações `OK`, zero avisos e zero falhas. Reimportar o mesmo payload manteve os 17 fatos; o registro de importação passou de 1 para 2 e o snapshot com o mesmo timestamp permaneceu único.
- **Decisões informadas para a homologação:** valores monetários negativos devem bloquear a importação; a tolerância de reconciliação monetária de R$ 0,01 é aceita; `valorRecebidoPeriodo` identifica recebimentos dentro do período; `valorAVencer` e `valorVencido` representam posição da carteira conforme vencimento; cada captura da posição deve permanecer como registro histórico. A regra `valor do acordo = pago + pendente` ainda não foi confirmada.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

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
| Depósitos: totais agregados | `data.depositos.quantidadeTotal`, `valorTotal` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | quantidade deve reconciliar exatamente; dinheiro com tolerância padrão R$ 0,01 | não persistidos separadamente |
| Acordos: quantidade | `data.acordos.porUsuario[].quantidade` | inteiro >= 0, obrigatório | mesmas regras de quantidade | `fatos.qtd`, tipo `acordo` |
| Acordos: valor | `data.acordos.porUsuario[].valor` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor`, tipo `acordo` |
| Acordos: pagos | `data.acordos.porUsuario[].pagos` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_pago`, tipo `acordo` |
| Acordos: pendente | `data.acordos.porUsuario[].pendente` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_aberto`, tipo `acordo` |
| Acordos: totais agregados | `quantidadeTotal`, `valorTotal`, `pagosTotal`, `pendenteTotal` em `data.acordos` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; monetários com tolerância R$ 0,01 | não persistidos separadamente |
| Promessas: quantidade | `data.promessas.porUsuario[].quantidade` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `promessa` |
| Promessas: prometido | `data.promessas.porUsuario[].prometido` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor`, tipo `promessa` |
| Promessas: cumprido | `data.promessas.porUsuario[].cumprido` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_pago`, tipo `promessa` |
| Promessas: em aberto | `data.promessas.porUsuario[].emAberto` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_aberto`, tipo `promessa` |
| Promessas: quebrado | `data.promessas.porUsuario[].quebrado` | número finito não negativo, obrigatório | valores negativos são rejeitados | `fatos.valor_quebrado`, tipo `promessa` |
| Promessas: totais agregados | `quantidadeTotal`, `prometidoTotal`, `cumpridoTotal`, `emAbertoTotal`, `quebradoTotal` em `data.promessas` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; monetários com tolerância R$ 0,01 | não persistidos separadamente |
| Contatos: registros totais | `data.contatos.porUsuario[].registrosTotais` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `contato` |
| Contatos: contatos únicos por usuário | `data.contatos.porUsuario[].contatosUnicos` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd_unicos`, tipo `contato` |
| Contatos: registros agregados | `data.contatos.registrosTotaisTotal` | opcional para importador; auditado quando presente | reconciliação inteira exata | não persistido separadamente |
| Contatos únicos agregados | `data.contatos.contatosUnicosTotal` | observado na amostra; não aditivo | auditor exibe como não aditivo, sem reconciliação | não persistido separadamente |
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | número finito não negativo, obrigatório | sem total por usuário para reconciliar | `acordos_posicao.recebido_periodo` |
| Valores a vencer | `data.valoresAcordo.valorAVencer` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.a_vencer` |
| Valores vencidos | `data.valoresAcordo.valorVencido` | número finito não negativo, obrigatório | rejeita negativos | `acordos_posicao.vencido` |
| Timestamp da resposta | `timestamp` | texto não vazio; se ausente, gerado localmente | não valida formato temporal | `acordos_posicao.capturado_em` |

O usuário é identificado por `usuario` (texto não vazio) e o nome é opcional (`nome`, texto ou null). Um mesmo identificador com nomes não vazios conflitantes dentro do payload bloqueia a normalização. Usuários repetidos dentro do mesmo grupo bloqueiam; um usuário pode aparecer em grupos diferentes. A tabela `usuarios` é atualizada pelo identificador global.

## Auditoria e severidade

Desde a proteção da Fase 6, os caminhos de gravação por arquivo e API e o modo `--dry-run` executam a auditoria antes de gravar ou aprovar a resposta. Qualquer check `DIVERGÊNCIA` ou `PENDENTE` bloqueia a execução com código 1; erros de estrutura/tipo continuam sendo erros de validação (código 2). A resposta da API é auditada antes de abrir/criar o SQLite na primeira data. Em uma faixa de vários dias, cada dia continua sendo transacionado separadamente: dias anteriores já gravados não são revertidos se um dia posterior falhar.

- `auditar_resposta.py` compara totais agregados disponíveis contra soma por usuário. Campos agregados ausentes viram `PENDENTE` e resultam em código 1; divergência monetária acima de R$ 0,01 ou divergência inteira resulta em código 1. Estrutura/JSON inválidos resultam em código 2.
- A importação local valida estrutura e campos obrigatórios, mas não reconcilia por si só todos os totais agregados. A rotina integrada bloqueia a importação se a auditoria não retorna código 0.
- Grupos `porUsuario` vazios são aceitos se a lista existir. Totais agregados ausentes na resposta ainda podem impedir a homologação integrada pela auditoria.
- O auditor não reconcilia `valorRecebidoPeriodo`, `valorAVencer` ou `valorVencido` com fatos por usuário; não há base comprovada para tal igualdade. Da mesma forma, os campos `acordos.valorTotal`, `pagosTotal` e `pendenteTotal` são auditados individualmente contra as somas por usuário, mas o sistema ainda não impõe a relação entre os três totais. A tela indica somas de valor de face por status, não necessariamente caixa recebido.
- Os números de contato único por negociador não podem ser somados como clientes únicos globais sem chave de pessoa e regra de deduplicação aprovada.

## Questões que exigem decisão financeira

1. **Decidido:** qualquer campo monetário negativo bloqueia a validação/importação. Estornos e ajustes, se representados negativamente pelo CRM, precisam ser tratados fora desta regra ou ter formato aprovado explicitamente; o importador não os aceitará como valores monetários negativos.
2. **Decidido provisoriamente para reconciliação:** tolerância monetária de R$ 0,01. Diferenças superiores a um centavo bloqueiam; quantidades inteiras precisam coincidir exatamente. O esquema SQLite continua usando `REAL`, então a política de precisão para persistência/migração permanece pendente.
3. **Semântica observada na tela de acordos por usuário:** `valor` representa o valor de face do acordo; `pagos` e `pendente` são colunas separadas que classificam parcelas por status e somam seus valores de face. A descrição da tela informa que `pagos` inclui pagamentos parciais e que `pendente` se refere às vencidas. Portanto, `pagos` não deve ser interpretado automaticamente como dinheiro efetivamente recebido. **Ainda pendente:** confirmar se `valor = pagos + pendente` é uma igualdade obrigatória e se essas duas categorias cobrem todas as parcelas em casos de renegociação, descontos, cancelamentos ou parcelas ainda não vencidas.
4. **Decidido conforme a definição informada:** `valorRecebidoPeriodo` é o total efetivamente recebido no intervalo; `valorAVencer` é o saldo ainda pendente cujo vencimento não chegou; `valorVencido` é o saldo pendente cujo vencimento passou. Estes dois últimos representam a posição da carteira, não valores que devam ser somados entre snapshots.
5. **Comportamento atual e histórico:** a tabela `acordos_posicao` preserva capturas com diferentes `capturado_em`; não somar snapshots de dias/horários diferentes. Os fatos do mesmo dia são substituídos quando esse dia é reimportado; isso é distinto do histórico de posições.
6. Aprovar o formato e a semântica de `timestamp`; quando ausente, o importador inventa um horário local de captura, que não representa o horário da resposta do CRM.

## Precisão monetária e histórico

O esquema atual usa SQLite `REAL` (ponto flutuante binário), sujeito a pequenas diferenças de representação. Não migrar automaticamente: antes, comparar todos os valores existentes em centavos, definir política para valores com mais de duas casas e preparar migração com backup, verificação de contagens e reconciliação antes/depois. Recomendação provisória: usar `Decimal` na camada de validação/cálculo e persistir centavos inteiros somente após aprovação e plano de migração compatível; até lá, converter de strings decimais quando possível, explicitar tolerância e evitar igualdade exata entre floats.

Fatos diários (`fatos`) e snapshots (`acordos_posicao`) são conjuntos diferentes. Conforme definição recebida, `valorRecebidoPeriodo` representa o fluxo recebido no intervalo; `valorAVencer` e `valorVencido` são a posição da carteira na captura, classificada pela data de vencimento. Cada snapshot deve ser preservado como fotografia daquele instante, não como movimentação e não deve ser somado aos snapshots de outros instantes.

## Pendências para fechamento integral e produção

- Aprovar ou rejeitar formalmente a regra `valor do acordo = pago + pendente`, incluindo renegociações, descontos, cancelamentos e pagamentos parciais.
- Definir como validar contatos únicos globalmente, sem somar contagens por negociador sem regra de deduplicação.
- Confirmar precisão/arredondamento e aprovar eventual migração do SQLite `REAL`, com análise de compatibilidade e backup.
- Executar o exercício operacional de backup/recuperação em banco de homologação autorizado, mantendo o banco de origem e o backup preservados; os testes automatizados isolados não substituem essa aprovação operacional.
- Manter a evidência do payload sanitizado fora do Git e repetir os comandos quando houver mudança relevante no contrato ou nos scripts. Não consultar o CRM para gerar evidência de homologação.

A validação automatizada deste payload sanitizado está concluída; as pendências acima continuam sendo gates antes de produção.
