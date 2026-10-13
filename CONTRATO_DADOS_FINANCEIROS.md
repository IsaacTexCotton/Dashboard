# CAIXA FUTURO — Contrato de dados e homologação financeira

## Estado da evidência

- **Amostra observada:** `amostra_resposta.json`, versionada no repositório. É explicitamente fictícia; demonstra somente a forma ilustrativa abaixo.
- **Payload sanitizado fornecido:** foi recebido um JSON de um único dia (2026-10-13). Uma auditoria aritmética independente conciliou as 12 métricas aditivas; o arquivo não foi versionado. Os scripts do repositório ainda não foram executados diretamente contra essa cópia neste ambiente, pois o clone falhou por indisponibilidade de DNS. Portanto, a validação automatizada dessa instância permanece **PENDENTE** até execução em ambiente controlado com o código publicado.
- **Regra contábil aprovada:** nenhuma aprovação formal foi apresentada. Não inferir equivalência entre métricas distintas.
- **Escopo:** contrato implementado por `importar.normalizar`, esquema SQLite atual e reconciliações implementadas em `auditar_resposta.py`. Este documento não afirma que os nomes são um contrato oficial do CRM.

## Contrato observado e persistência

Todas as propriedades abaixo são observadas na amostra fictícia e implementadas pelo importador. Isso não comprova que a API real sempre as envia.

| Campo lógico | Caminho JSON | Tipo/obrigatoriedade atual | Validação atual | Destino SQLite |
|---|---|---|---|---|
| Dia inicial | `data.inicio` | string, obrigatório | data ISO canônica; deve ser o dia importado | `fatos.data`, `acordos_posicao.data`, `importacoes.inicio` |
| Dia final | `data.fim` | string, obrigatório | data ISO canônica; deve ser igual ao dia importado | `importacoes.fim` |
| Sucesso | `success` | boolean true, obrigatório | exige identidade `True` | não persistido |
| Depósitos: quantidade | `data.depositos.porUsuario[].quantidade` | inteiro >= 0, obrigatório por usuário | rejeita bool, fração e negativo | `fatos.qtd`, tipo `deposito` |
| Depósitos: valor | `data.depositos.porUsuario[].valor` | número finito, obrigatório por usuário | rejeita bool, texto e não finito; negativos ainda não são rejeitados | `fatos.valor`, tipo `deposito` |
| Depósitos: totais agregados | `data.depositos.quantidadeTotal`, `valorTotal` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | quantidade deve reconciliar exatamente; dinheiro com tolerância padrão R$ 0,01 | não persistidos separadamente |
| Acordos: quantidade | `data.acordos.porUsuario[].quantidade` | inteiro >= 0, obrigatório | mesmas regras de quantidade | `fatos.qtd`, tipo `acordo` |
| Acordos: valor | `data.acordos.porUsuario[].valor` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor`, tipo `acordo` |
| Acordos: pagos | `data.acordos.porUsuario[].pagos` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor_pago`, tipo `acordo` |
| Acordos: pendente | `data.acordos.porUsuario[].pendente` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor_aberto`, tipo `acordo` |
| Acordos: totais agregados | `quantidadeTotal`, `valorTotal`, `pagosTotal`, `pendenteTotal` em `data.acordos` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; monetários com tolerância R$ 0,01 | não persistidos separadamente |
| Promessas: quantidade | `data.promessas.porUsuario[].quantidade` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `promessa` |
| Promessas: prometido | `data.promessas.porUsuario[].prometido` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor`, tipo `promessa` |
| Promessas: cumprido | `data.promessas.porUsuario[].cumprido` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor_pago`, tipo `promessa` |
| Promessas: em aberto | `data.promessas.porUsuario[].emAberto` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor_aberto`, tipo `promessa` |
| Promessas: quebrado | `data.promessas.porUsuario[].quebrado` | número finito, obrigatório | negativo não é bloqueado atualmente | `fatos.valor_quebrado`, tipo `promessa` |
| Promessas: totais agregados | `quantidadeTotal`, `prometidoTotal`, `cumpridoTotal`, `emAbertoTotal`, `quebradoTotal` em `data.promessas` | opcionais na normalização; ausentes geram PENDENTE no auditor e bloqueiam importação | contagem exata; monetários com tolerância R$ 0,01 | não persistidos separadamente |
| Contatos: registros totais | `data.contatos.porUsuario[].registrosTotais` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd`, tipo `contato` |
| Contatos: contatos únicos por usuário | `data.contatos.porUsuario[].contatosUnicos` | inteiro >= 0, obrigatório | inteiro não negativo | `fatos.qtd_unicos`, tipo `contato` |
| Contatos: registros agregados | `data.contatos.registrosTotaisTotal` | opcional para importador; auditado quando presente | reconciliação inteira exata | não persistido separadamente |
| Contatos únicos agregados | `data.contatos.contatosUnicosTotal` | observado na amostra; não aditivo | auditor exibe como não aditivo, sem reconciliação | não persistido separadamente |
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | número finito, obrigatório | não negativo ainda não exigido; sem total por usuário para reconciliar | `acordos_posicao.recebido_periodo` |
| Valores a vencer | `data.valoresAcordo.valorAVencer` | número finito, obrigatório | não negativo ainda não exigido | `acordos_posicao.a_vencer` |
| Valores vencidos | `data.valoresAcordo.valorVencido` | número finito, obrigatório | não negativo ainda não exigido | `acordos_posicao.vencido` |
| Timestamp da resposta | `timestamp` | texto não vazio; se ausente, gerado localmente | não valida formato temporal | `acordos_posicao.capturado_em` |

O usuário é identificado por `usuario` (texto não vazio) e o nome é opcional (`nome`, texto ou null). Um mesmo identificador com nomes não vazios conflitantes dentro do payload bloqueia a normalização. Usuários repetidos dentro do mesmo grupo bloqueiam; um usuário pode aparecer em grupos diferentes. A tabela `usuarios` é atualizada pelo identificador global.

## Auditoria e severidade

Desde a proteção da Fase 6, os caminhos de gravação por arquivo e API e o modo `--dry-run` executam a auditoria antes de gravar ou aprovar a resposta. Qualquer check `DIVERGÊNCIA` ou `PENDENTE` bloqueia a execução com código 1; erros de estrutura/tipo continuam sendo erros de validação (código 2). A resposta da API é auditada antes de abrir/criar o SQLite na primeira data. Em uma faixa de vários dias, cada dia continua sendo transacionado separadamente: dias anteriores já gravados não são revertidos se um dia posterior falhar.

- `auditar_resposta.py` compara totais agregados disponíveis contra soma por usuário. Campos agregados ausentes viram `PENDENTE` e resultam em código 1; divergência monetária acima de R$ 0,01 ou divergência inteira resulta em código 1. Estrutura/JSON inválidos resultam em código 2.
- A importação local valida estrutura e campos obrigatórios, mas não reconcilia por si só todos os totais agregados. A rotina integrada bloqueia a importação se a auditoria não retorna código 0.
- Grupos `porUsuario` vazios são aceitos se a lista existir. Totais agregados ausentes na resposta ainda podem impedir a homologação integrada pela auditoria.
- O auditor não reconcilia `valorRecebidoPeriodo`, `valorAVencer` ou `valorVencido` com fatos por usuário; não há base comprovada para tal igualdade.
- Os números de contato único por negociador não podem ser somados como clientes únicos globais sem chave de pessoa e regra de deduplicação aprovada.

## Questões que exigem decisão financeira

1. Confirmar se valores negativos são válidos (estornos, ajustes, cancelamentos) ou devem bloquear importação. O importador atualmente aceita números negativos finitos nos campos monetários; não mudar essa regra sem decisão de negócio.
2. Definir moeda, arredondamento e tolerância por campo; a tolerância atual de R$ 0,01 é aplicada pelo auditor a totais monetários aditivos.
3. Definir se `valorTotal`, `pagos` e `pendente` têm relação contábil obrigatória, incluindo pagamentos parciais, renegociações e cancelamentos.
4. Definir o significado temporal de `valoresAcordo`: recebido no período é fluxo do período; a vencer/vencido parecem posição, mas isso não foi comprovado pela API/negócio.
5. Definir se reimportar o mesmo dia deve substituir o snapshot ou preservar múltiplas capturas. Atualmente fatos do dia são substituídos, enquanto snapshots usam `capturado_em` como chave e podem manter várias capturas.
6. Aprovar o formato e a semântica de `timestamp`; quando ausente, o importador inventa um horário local de captura, que não representa o horário da resposta do CRM.

## Precisão monetária e histórico

O esquema atual usa SQLite `REAL` (ponto flutuante binário), sujeito a pequenas diferenças de representação. Não migrar automaticamente: antes, comparar todos os valores existentes em centavos, definir política para valores com mais de duas casas e preparar migração com backup, verificação de contagens e reconciliação antes/depois. Recomendação provisória: usar `Decimal` na camada de validação/cálculo e persistir centavos inteiros somente após aprovação e plano de migração compatível; até lá, converter de strings decimais quando possível, explicitar tolerância e evitar igualdade exata entre floats.

Fatos diários (`fatos`) e snapshots (`acordos_posicao`) são conjuntos diferentes. Um fato diário representa métricas associadas ao dia importado; um snapshot registra valores de posição na captura. Sem especificação do CRM, não se deve tratar snapshots como histórico de movimentações, nem somá-los entre dias.

## Evidência necessária para fechar homologação

- JSON real sanitizado e autorizado, preservando estrutura, tipos, campos opcionais e relações entre totais e linhas; remover nomes/identificadores pessoais ou substituí-los consistentemente por pseudônimos.
- Identificação do período e da origem da resposta, sem tokens, cookies, cabeçalhos de autenticação ou dados pessoais desnecessários.
- Aprovação do responsável financeiro para semântica, tolerância, valores negativos, contatos únicos, snapshots e política de precisão.
- Execução local auditada com o JSON fornecido; não consultar o CRM para obter a evidência.
