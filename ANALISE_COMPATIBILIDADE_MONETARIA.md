# Análise de compatibilidade monetária — CAIXA FUTURO

**Status:** análise documental atualizada com decisões recebidas em 14/10/2026; pendente de ratificação/assinatura formal e de verificações técnicas; migração não autorizada nem executada  
**Data:** 2026-10-14  
**Branch:** docs/analise-compatibilidade-monetaria  
**Base observada:** main, commit 80791885a5b906d3e14d71091932eabe53a203da.

## 1. Resumo e limites

Foram consultados POLITICA_PRECISAO_MONETARIA.md, CONTRATO_DADOS_FINANCEIROS.md, RUNBOOK_OPERACIONAL.md, importar.py e auditar_resposta.py no GitHub. O inventário abaixo registra evidência observada e pendências separadamente. Não foi aberto banco local ou de produção, não houve consulta ao CRM nem uso de credenciais, não houve migração, alteração de schema ou corte de leitura. O inventário de todos os consumidores da interface e o estado do CI ainda precisam ser completados; não se afirma que testes ou backup tenham sido executados nesta sessão.

## 2. Evidências verificadas

- A política v1.0 aprova INTEGER em centavos com sufixo _centavos para valores monetários finais novos, aritmética inteira/decimal exata, half-up, igualdade exata e preservação das colunas REAL legadas até análise e plano aprovados.
- O contrato de dados registra que valorRecebidoPeriodo é fluxo do período, enquanto valorAVencer e valorVencido são posições por captura; snapshots devem permanecer no histórico e não ser somados como fluxo.
- O runbook exige diagnóstico e backup verificado antes de operações de banco, e proíbe versionar banco, backup, payload real ou dados pessoais.
- O commit mais recente observado em main durante a consulta foi 80791885a5b906d3e14d71091932eabe53a203da. Isso é a base observada, não o commit desta entrega.

Referências: [Política](POLITICA_PRECISAO_MONETARIA.md) · [Contrato](CONTRATO_DADOS_FINANCEIROS.md) · [Runbook](RUNBOOK_OPERACIONAL.md) · [Importador](importar.py) · [Auditor](auditar_resposta.py)

## 3. Inventário do fluxo monetário

### Entrada e validação — importar.py

- _numero(valor, campo) retorna float, aceita int/float JSON (rejeita bool), executa float(valor), valida finitude e rejeita valores menores que zero.
- _campo_numero exige o campo e delega a _numero.
- normalizar mapeia os campos JSON para fatos e snapshot de posição. json.load é usado sem parse_float=Decimal; números decimais JSON chegam como float.
- gravar normaliza antes de escrever e, em transação SQLite, atualiza usuarios, apaga e reinsere fatos do dia, substitui acordos_posicao e acrescenta importacoes.
- _auditoria_financeira_ok chama auditar_resposta.auditar e bloqueia checks DIVERGÊNCIA/PENDENTE.

### Campos e colunas no schema SCHEMA de importar.py

| Origem / semântica | Mapeamento atual | Coluna SQLite | Regra observada | Destino candidato |
|---|---|---|---|---|
| depositos.porUsuario[].valor | valor de depósito | fatos.valor, tipo deposito | float; não negativo | valor_centavos |
| acordos.porUsuario[].valor | valor de acordo | fatos.valor, tipo acordo | float; não negativo | valor_centavos |
| acordos.porUsuario[].pagos | pagos de acordo | fatos.valor_pago | float; não negativo | valor_pago_centavos |
| acordos.porUsuario[].pendente | pendente de acordo | fatos.valor_aberto | float; não negativo | valor_aberto_centavos |
| promessas.porUsuario[].prometido | valor prometido | fatos.valor, tipo promessa | float; não negativo | valor_centavos |
| promessas.porUsuario[].cumprido | valor cumprido | fatos.valor_pago | float; não negativo | valor_pago_centavos |
| promessas.porUsuario[].emAberto | valor em aberto | fatos.valor_aberto | float; não negativo | valor_aberto_centavos |
| promessas.porUsuario[].quebrado | valor quebrado | fatos.valor_quebrado | float; não negativo | valor_quebrado_centavos |
| valoresAcordo.valorRecebidoPeriodo | fluxo recebido no período | acordos_posicao.recebido_periodo REAL | float; não negativo | recebido_periodo_centavos |
| valoresAcordo.valorAVencer | posição a vencer por captura | acordos_posicao.a_vencer REAL | float; não negativo | a_vencer_centavos |
| valoresAcordo.valorVencido | posição vencida por captura | acordos_posicao.vencido REAL | float; não negativo | vencido_centavos |

O schema observado declara fatos(data, usuario, tipo, qtd, qtd_unicos, valor REAL, valor_pago REAL, valor_aberto REAL, valor_quebrado REAL, importado_em), chave primária (data, usuario, tipo) e índice ix_fatos_data. Declara acordos_posicao(capturado_em TEXT PRIMARY KEY, data TEXT, recebido_periodo REAL, a_vencer REAL, vencido REAL), importacoes com metadados de execução e usuarios com identificador/nome.

Os campos valor, valor_pago e valor_aberto são polimórficos: o significado depende de fatos.tipo. Os nomes de destino são candidatos, não decisão de esquema. Antes de alterar schema, decidir entre colunas paralelas polimórficas e colunas específicas por métrica/tipo; não renomear nem reaproveitar silenciosamente colunas existentes.

### Auditoria — auditar_resposta.py

- REGRAS cobre totais de depósitos, acordos, pagos, pendentes, promessas (prometido, cumprido, emAberto, quebrado) e registros de contato.
- _decimal usa Decimal(str(valor)), mas se o valor veio como float, a grafia decimal original pode já ter sido perdida.
- _decimal rejeita valores negativos.
- auditar(resp, tolerancia=Decimal("0.01")) aceita diferença monetária absoluta de até R$ 0,01 inclusive. Quantidades são comparadas exatamente.
- contatosUnicosTotal é tratado como não aditivo.
- A tolerância afeta a aceitação do importador porque _auditoria_financeira_ok bloqueia apenas DIVERGÊNCIA/PENDENTE.

### Consumidores a confirmar

A inspeção acima não prova que todos os leitores e escritores foram localizados. Antes de migração, pesquisar referências SQL/Python a fatos.valor, valor_pago, valor_aberto, valor_quebrado e acordos_posicao, além de SUM, views, interface, gráficos, relatórios, exportações, integrações e scripts de manutenção. O inventário de testes e o estado do workflow CI também permanecem pendentes.

## 4. Conflitos e riscos

### Fatos observados
1. importar._numero converte para float e rejeita todos os valores monetários negativos.
2. auditar_resposta._decimal também rejeita negativos.
3. auditar_resposta.auditar usa tolerância padrão de R$ 0,01.
4. O schema do importador usa REAL nas colunas monetárias.
5. O parsing não preserva o token decimal JSON como texto ou Decimal.
6. A semântica documentada distingue fluxo recebido de snapshots de carteira.

### Conclusões técnicas
- Decimal(str(float)) não restaura com certeza a representação decimal original.
- Tolerância de R$ 0,01 pode mascarar uma divergência real de um centavo e viola igualdade exata em centavos.
- Colunas REAL devem permanecer inalteradas; usar colunas paralelas e conciliação.
- Valores de face, pagamentos confirmados, pendentes de baixa, créditos e abatimentos têm semânticas diferentes. Não liberar negativos globalmente nem presumir que pagos e pendente cobrem todos os cenários contábeis.

### Matriz provisória de sinais — requer confirmação por campo

| Campo | Regra provisória | Pendência |
|---|---|---|
| Depósito | manter não negativo por ora | confirmar se estornos são eventos separados ou valores negativos |
| Valor/face de acordo | manter não negativo por ora | confirmar tratamento de crédito, cancelamento e renegociação |
| Pagos/cumpridos | manter não negativo por ora | confirmar se estornos são eventos separados |
| Pendente/em aberto | manter não negativo por ora | confirmar se excesso de pagamento pode gerar saldo negativo |
| Quebrado | manter não negativo por ora | confirmar semântica da métrica |
| Recebido no período | manter não negativo por ora | confirmar se total é bruto/líquido de devoluções |
| A vencer/vencido | manter não negativo por ora | confirmar representação de crédito/abatimento na carteira |

A política permite negativos somente quando a semântica do campo os autoriza. Até decisão documentada, manter o comportamento atual em produção; não inferir regra contábil a partir dos nomes.

## 5. Arquitetura recomendada

1. Entrada: parsear decimais do JSON com parse_float=Decimal ou preservar os tokens numéricos; validar finitude e tipos, sem float em cálculos financeiros.
2. Centralizar real_para_centavos(valor_legado), com Decimal e half-up simétrico para longe de zero, saída inteira e tratamento explícito de NULL, valores não finitos e overflow. Para REAL legado, a representação original pode já estar perdida; documentar a conversão determinística e validar com fixtures sintéticas. Não prometer recuperar precisão inexistente.
3. Criar colunas INTEGER paralelas com sufixo _centavos para montantes finais. Preços, quantidades fracionárias e taxas, se aplicáveis, usam escala _eN.
4. Valores de entrada com mais de duas casas devem ser tratados como texto decimal e arredondados uma única vez no resultado final. Valores oficiais de origem (boleto, extrato, custas) não devem ser recalculados.
5. Manter catálogo explícito de semântica e sinal por campo; nunca corrigir sinal silenciosamente.
6. Conciliar inteiros em centavos por igualdade exata. Relatório por campo/período deve apresentar contagem, total legado convertido, total novo e delta em centavos, separando fluxos de snapshots.
7. Migração aditiva e idempotente: conferir schema, criar apenas colunas ausentes, usar chave primária estável, registrar inválidos sem expor dados pessoais e abortar em incompatibilidade. Não sobrescrever destino divergente sem modo de reparo aprovado.

### Ambiguidade crítica: legado somente leitura versus dupla escrita

A política exige que colunas REAL existentes sejam somente leitura para o novo código e também menciona período de dupla escrita. Isso é incompatível se dupla escrita significar atualizar as colunas REAL. Recomendação para decisão humana: legado estritamente somente leitura; novos escritores gravam somente _centavos; conciliação lê ambos sem mutar legado. Se consumidores antigos exigirem REAL atualizado, bloquear até exceção formal ou camada de compatibilidade aprovada. Não implementar exceção unilateralmente.

## 6. Plano faseado executável — ainda não executado

### Fase 0 — inventário e semântica
- Mapear todos os leitores/escritores, SQL, views, gráficos, relatórios, exportações e integrações.
- Confirmar formato decimal oficial e sinais por campo.
- Resolver nomes e modelo das colunas novas e a ambiguidade da dupla escrita.
- Gate: revisão de engenharia e semântica aprovada pela área financeira.

### Fase 1 — backup e baseline
- Identificar o caminho real por DASHBOARD_DB; não adivinhar.
- Em ambiente autorizado, controlar escritores e executar backup_sqlite.py criar e backup_sqlite.py verificar em destino exclusivo; exigir status OK, integrity_check aprovado e manifesto SHA-256 protegido.
- Registrar contagens, user_version e totais por campo/período fora do Git.
- Executar diagnosticar_banco.py e guardar relatório restrito.
- Gate: backup verificado e baseline reproduzível. Nenhum backup foi criado nesta análise.

### Fase 2 — utilitários e testes isolados
- Implementar parsing decimal exato, real_para_centavos, formatação e rateio em módulo isolado.
- Testar NULL, -0.0, NaN/Infinity, overflow e valores fora do domínio.
- Gate: suite passa e algoritmo revisado.

### Fase 3 — schema paralelo e backfill idempotente
- Usar banco descartável/fixture sintética; adicionar colunas INTEGER _centavos sem modificar REAL.
- Script verifica schema, cria somente colunas ausentes, usa chave estável e relata dados inválidos.
- Repetição deve manter resultados idênticos, sem duplicação ou reconversão. Valores destino já divergentes devem gerar conflito explícito.
- Gate: contagens preservadas e legado inalterado.

### Fase 4 — leitura paralela e conciliação
- Manter leitura de legado até aprovação do corte; não gravar no legado.
- Comparar por campo e período, reportar diferenças de 1 centavo e explicar todas as divergências.
- Dupla escrita no REAL só pode ocorrer mediante exceção formal à política.
- Gate Controladoria: zero divergência inexplicada, semântica confirmada e aprovação escrita.

### Fase 5 — corte e rollback
- Habilitar leitura _centavos primeiro em homologação, com regressão de consultas, relatórios e exportações.
- Definir janela, responsável, gatilhos de aborto e rollback; ensaiar em cópia.
- Antes do corte, reverter descartando ambiente de teste. Após corte, voltar leitura via feature flag para legado sem apagar colunas novas; restaurar backup somente com aprovação e análise das escritas posteriores.
- Gate final: conciliação aprovada, testes/CI verdes, backup verificado, runbook e responsáveis definidos.
- Remover REAL somente em etapa futura separada e aprovada.

## 7. Testes mínimos especificados

| Categoria | Casos | Esperado |
|---|---|---|
| Half-up positivo | 0,005; 0,004; 1,005; 2,675 | 1, 0, 101, 268 centavos para entradas decimais em reais |
| Half-up negativo | -0,005; -0,004 | -1 e 0 centavos; aceitar só em campos aprovados |
| Importação | 3, 4 e 6 casas decimais | parsing decimal exato; arredondar uma vez no final |
| REAL legado | 1,005; 2,675; 0,1 + 0,2 | conversão determinística e diferenças explicitadas; documentar perda original |
| Somas extensas | muitos itens e frações subcentavo | sem deriva; arredondamento no nível correto |
| Rateio/parcelamento | 10.000 centavos em 3 partes | 3333 + 3333 + 3334; soma exata |
| Reconciliação | diferença 0,00 e 0,01 | igualdade passa; diferença de 1 centavo falha |
| Sinais | negativo por campo, crédito, estorno, abatimento | conforme matriz aprovada, sem autorização global |
| Idempotência | repetir migração, schema parcial, destino já preenchido | sem duplicação; conflito explícito |
| Falha/atomicidade | interrupção, constraint, overflow, inválido | rollback; legado preservado |
| Integração | snapshots, fluxos, totais por usuário | sem somar snapshots como fluxos; contagens preservadas |

Estes são testes especificados, não resultados de execução. A integração GitHub usada nesta inspeção não executou a suite local.

## 8. Critérios de aprovação da Controladoria

Entregar inventário final, baseline reproduzível, relatório por período/campo com totais e diferenças em centavos, justificativa aprovada para cada divergência, decisão sobre sinais e pagamentos pendentes, testes e CI ligados ao commit, backup verificado e rollback ensaiado. Gate: nenhuma divergência inexplicada; não substituir igualdade exata por tolerância informal.

## 9. Decisões recebidas e estado de ratificação

O arquivo **`DECISOES_PENDENCIAS_MIGRACAO.md`**, recebido em 14/10/2026, registra as decisões de negócio abaixo. O próprio cabeçalho informa que estão **para ratificação e assinatura**; portanto, devem ser tratadas como regras propostas para implementação, sujeitas ao gate formal, e não como evidência de assinatura já concluída.

| Tema | Decisão registrada | Estado/gate técnico |
|---|---|---|
| Sinais negativos | Permitidos somente em depósitos (estorno), `valorRecebidoPeriodo`, `acordos.porUsuario[].pendente` e `promessas.porUsuario[].emAberto`; alerta visível; demais valores e todas as quantidades não negativos | Validar com extração real sanitizada/autorizada e testes por campo; sem payload de CRM nesta análise |
| Entrada decimal | Duas casas para valor monetário final; sem passagem por `float`; mais de duas casas bloqueia o registro; rejeitar notação científica, NaN, infinito e texto inválido | **Conflita com a seção 4 da Política v1.0**, que prevê valores com mais casas em entrada e arredondamento ao final. Ratificar e versionar a política antes de codificar |
| Compatibilidade com REAL | Manter as colunas legadas; novas colunas `INTEGER` em centavos; escrita na mesma transação | “REAL somente leitura” conflita com a necessidade registrada de manter a gravação pelo caminho legado existente durante a transição; corrigir o texto da decisão antes da implementação |
| Esquema | Colunas específicas por métrica, sufixo `_centavos`, `CHECK` para sinal onde aplicável | A regra “nome da coluna legada + sufixo” não resolve `fatos.valor`, cujo significado depende de `tipo`. Aprovar nomes/modelo explícitos para depósitos, acordos e promessas |
| Conversão do histórico | `Decimal(repr(valor))`, *half-up*, função única `real_para_centavos`, relatório de conversões suspeitas | `repr(float)` não recupera de forma garantida a grafia original do JSON. A conversão serve como interpretação determinística do REAL existente, com perda histórica explicitada; definir a regra exata de suspeita |
| Relações contábeis | Acordos: `valor = pagos + pendente`; promessas: `prometido = cumprido + emAberto + quebrado` | A amostra fictícia versionada não comprova a relação das promessas em dados reais. Verificar com extração autorizada antes do alerta |
| Pagamento sem baixa | Continua em pendente/em aberto; só é considerado pago/recebido após baixa confirmada; campo próprio, se existir, deve ser exibido separado e não somado a pagos | Inventariar se a origem fornece esse campo e comprovar como os totais são montados |
| ERP/Systêxtil | Valor calculado pela origem prevalece; app não apresenta cálculo próprio de juros/multa/desconto antes de validar a fórmula contra pelo menos 30 títulos sanitizados | Gate de TI/Contabilidade antes de habilitar cálculo próprio |
| Corte e rollback | Dez dias úteis de conciliação; centavos novos com tolerância zero; 100% das divergências classificadas; Controladoria aprova e Diretoria assina; restauração testada; REAL descomissionado em etapa posterior após 90 dias sem incidentes | Definir calendário/critério para “dia útil”, produzir relatórios reais, obter aprovações e ensaiar rollback em homologação |

## 10. Revisão de consistência técnica

| ID / severidade | Inconsistência ou risco | Tratamento necessário |
|---|---|---|
| TC-01 — **Bloqueador** | Política monetária v1.0 permite tratar entradas com mais de duas casas como decimal exato e arredondar o resultado final; a decisão complementar manda bloquear valores finais com mais de duas casas | Diretoria Financeira deve ratificar a regra prevalente e publicar revisão versionada da política. Não usar o documento complementar para alterar silenciosamente uma política aprovada |
| TC-02 — **Bloqueador** | “REAL somente leitura” não é compatível, literalmente, com “a gravação em REAL continua pelo caminho existente”, enquanto se mantém o dashboard legado | Especificar que não haverá **novo caminho de escrita** para REAL, mas que o escritor legado permanecerá ativo e inalterado até o corte; se essa não for a intenção, redesenhar a transição. Testar rollback por chave de leitura |
| TC-03 — **Bloqueador** | “Colunas específicas por métrica” conflita com adicionar apenas o sufixo à coluna física legada `fatos.valor`, reutilizada para depósito, acordo e promessa | Aprovar o modelo antes de criar colunas. Recomendação para decisão: preservar as métricas distintas com nomes semanticamente explícitos; para `fatos.valor`, não presumir que um único `valor_centavos` atende ao requisito sem ratificação. Rever também como `CHECK` expressa regras condicionadas por `tipo` |
| TC-04 — **Alto** | `json.load(parse_float=Decimal)` preserva precisão numérica decimal, mas não rejeita automaticamente toda notação científica; `parse_float` recebe o token numérico e pode validá-lo antes de construir o Decimal | Usar parser comum para importador e auditoria; inspecionar o token bruto para rejeitar `e/E`, aceitar apenas formatos contratuais e validar separadamente strings decimais, booleanos, nulos e limites |
| TC-05 — **Alto** | `Decimal(repr(x))` é determinístico para a representação curta do float, mas não recupera com garantia o texto original (ex.: zeros finais ou grafia equivalente podem já ter sido perdidos) | Documentar conversão de REAL histórico como estimativa técnica auditável, não como reconstrução do payload. Não classificar o centavo convertido como mais verdadeiro que o legado sem reconciliação |
| TC-06 — **Alto** | Os sinais permitidos variam conforme o campo e, em `fatos`, também conforme `tipo`; uma regra genérica de “não negativo” ou um `CHECK` apenas por coluna pode aceitar/rejeitar casos errados | Criar matriz de validação centralizada campo+tipo, restrições `CHECK` compatíveis com o desenho escolhido e testes para negativos permitidos/proibidos, zero, nulo e fronteiras |
| TC-07 — **Alto** | SQLite não vincula `Decimal` diretamente sem adaptação. A dupla escrita precisa definir como o valor exato em centavos alimenta as colunas novas e como o fluxo legado mantém compatibilidade com REAL | Manter cálculos e reconciliação no domínio Decimal/inteiro; confinar a eventual conversão para REAL ao adaptador legado explicitamente aprovado; realizar ambas as gravações na mesma transação e testar falha de cada lado |
| TC-08 — **Alto** | A relação das promessas está aprovada no documento de decisão, mas não foi comprovada pela evidência atualmente versionada. Os 10 dias úteis de alerta não definem como tratar dias sem carga, falhas nem feriados | Verificar a relação com payload autorizado; definir critério de contagem da janela e exigir carga/auditoria válida por dia antes de avançar o gate |
| TC-09 — **Alto** | A validação de 30 títulos do ERP ainda não foi produzida; arredondar *half-up* pelo app não prova que a fórmula do ERP, sua base de dias e o momento do arredondamento sejam iguais | Deixar cálculo próprio desligado; validar 30 casos reais sanitizados contra a origem e documentar divergências antes de alterar a política |
| TC-10 — **Médio** | O inventário completo de consumidores, testes e CI ainda não está demonstrado | Inspecionar todo o repositório, identificar leituras e escritas de REAL, automatizar os testes e exigir execução verde de CI no PR. Ausência de resultado observado não equivale a CI aprovado nem prova que inexiste workflow |
| TC-11 — **Médio** | A regra de “conversão suspeita” menciona “fração mínima” sem limite numérico operacional | Definir escala, algoritmo, epsilon/limite e formato do relatório em especificação versionada. Não usar tolerância para relaxar a igualdade exata dos dados novos |

### Recomendação de desenho

1. Separar três operações que não devem compartilhar semântica: **parse da origem** (validar formato e escala contratados), **conversão monetária exata** (Decimal para centavos, ou cálculo interno com arredondamento *half-up* apenas no resultado) e **conversão histórica de REAL** (diagnóstico e trilha de auditoria).
2. Manter a regra de igualdade exata para os novos valores em centavos; classificar divergências de legado como evidências de conversão ou erro, sem aplicar tolerância monetária ao dado novo.
3. Manter juros/multa/desconto calculados pelo app desabilitados até aprovação dos 30 títulos e não promover a amostra fictícia a evidência de produção.
4. Não fazer migração de esquema, corte ou modificação de caminho de gravação enquanto TC-01, TC-02 e TC-03 não forem resolvidos formalmente.

## 11. Gates obrigatórios antes da implementação/migração

- [ ] Ratificação e assinatura das decisões de negócio; atualização versionada da Política de Precisão Monetária para resolver TC-01.
- [ ] Decisão escrita sobre a continuidade da escrita legada em REAL durante a dupla escrita (TC-02).
- [ ] Modelo e nomes finais de colunas por métrica, incluindo o caso de `fatos.valor` (TC-03).
- [ ] Especificação do parser: tipos JSON/strings aceitos, rejeição de notação científica, escala, booleanos/nulos, limites e política para mais de duas casas.
- [ ] Extração real sanitizada e autorizada para validar sinais, semântica do pagamento sem baixa e equação das promessas.
- [ ] Evidência de ao menos 30 títulos sanitizados comparados com ERP/Systêxtil antes de habilitar cálculos próprios de encargos.
- [ ] Inventário completo de consumidores, testes e CI; testes automatizados verdes.
- [ ] Backup com manifesto/SHA-256 e restauração verificada em homologação, seguindo `RUNBOOK_OPERACIONAL.md`.
- [ ] Dez dias úteis de conciliação diária, divergências 100% classificadas, zero divergência inexplicada, aprovação da Controladoria e assinatura da Diretoria.
- [ ] Plano de rollback testado antes do corte; descomissionamento de REAL tratado em release separada após 90 dias corridos sem incidentes e aprovação própria.

### Acompanhamento explícito dos bloqueadores no GitHub

- [ ] [Issue #3 — Ratificar regra de entrada com mais de 2 casas](https://github.com/IsaacTexCotton/Dashboard/issues/3) — decisão da Diretoria Financeira e revisão versionada da política.
- [ ] [Issue #4 — Definir contrato de dupla escrita REAL/INTEGER](https://github.com/IsaacTexCotton/Dashboard/issues/4) — redação formal aprovada por TI/Controladoria/Diretoria.
- [ ] [Issue #5 — Definir colunas INTEGER específicas por métrica](https://github.com/IsaacTexCotton/Dashboard/issues/5) — aprovação do modelo por métrica e das constraints.
 
## 12. Estado desta entrega

- [x] Política, contrato, runbook, importador, auditoria e esquema atual consultados remotamente.
- [x] Decisões recebidas comparadas com política, contrato e implementação observável.
- [x] Revisão de consistência técnica e plano de execução preparados em documentos da mesma branch.
- [ ] Ratificação/assinatura formal das decisões e das resoluções dos bloqueadores.
- [ ] Inventário completo dos consumidores, testes e workflows CI: pendente.
- [x] GitHub Actions `Testes CAIXA FUTURO` — execução [#38](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38568801738) concluiu `success` no head documental `a113a97401d067330944373dcaf3bd6933c4b428`, incluindo os testes automatizados existentes e validação da amostra sem CRM; testes específicos da migração ainda não foram implementados/executados.
- [ ] Backup real verificado/restauração testada: não executados.
- [ ] Payload do CRM/ERP real sanitizado: não consultado nem recebido nesta análise.
- [ ] Migração, alteração de schema, dupla escrita, corte ou descomissionamento de REAL: não executados.

A análise é documental e propositiva. Ela não autoriza acesso ao CRM, migração ou alteração de produção e não certifica compatibilidade integral.
