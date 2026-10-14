# Análise de compatibilidade monetária — CAIXA FUTURO

**Status:** análise e minutas v1.1 atualizadas com propostas recebidas em 14/10/2026; assinatura formal pendente; nenhuma alteração funcional ou migração autorizada/executada.  
**Data:** 2026-10-14  
**Branch:** docs/analise-compatibilidade-monetaria  
**Base observada mais recente:** main, commit 7fbe7fa8d16a3d604381b0511d2b080d1f26d5cb.

## 1. Resumo e limites

Foram consultados POLITICA_PRECISAO_MONETARIA.md, CONTRATO_DADOS_FINANCEIROS.md, RUNBOOK_OPERACIONAL.md, importar.py, auditar_resposta.py, os seis módulos de teste e o workflow CI. As propostas v1.1 foram registradas em documentos separados como minutas pendentes de assinatura; v1.0 continua formalmente aprovada até a ratificação. O inventário dos leitores de REAL permanece incompleto porque `caixa-futuro-fase1.zip` não foi inspecionado. O CI #40 passou no commit documental anterior, mas ainda deve ser confirmado para o novo head. Nenhum banco local/de produção foi aberto; não houve consulta ao CRM nem uso de credenciais; nenhuma migração, alteração de schema ou corte de leitura foi executado.

## 2. Evidências verificadas

- A Política v1.0 formalmente aprovada estabelece INTEGER em centavos para valores monetários finais novos, aritmética inteira/decimal exata, half-up e igualdade exata. A minuta v1.1 nesta branch propõe regras de entrada por classe de campo e mantém o writer legado REAL ativo até descomissionamento formal.
- O contrato de dados registra que valorRecebidoPeriodo é fluxo do período, enquanto valorAVencer e valorVencido são posições por captura; snapshots devem permanecer no histórico e não ser somados como fluxo.
- O runbook exige diagnóstico e backup verificado antes de operações de banco, e proíbe versionar banco, backup, payload real ou dados pessoais.
- A base atual observada durante a atualização foi `main` em `7fbe7fa8d16a3d604381b0511d2b080d1f26d5cb`; esse hash identifica a base consultada, não o head documental desta branch.

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

## 3.1 Inventário verificado de testes e CI

A árvore versionada de `main` foi inspecionada em 14/10/2026. O workflow `.github/workflows/testes.yml` dispara em `push` para `main` e em `pull_request` destinado a `main`, configura Python 3.11 e executa `python -m unittest discover -s tests -v`; depois, valida a amostra versionada sem CRM por meio de `importar.py --dry-run`, `auditar_resposta.py` e `validar_integracao_local.py`.

Foram identificados **6 módulos de teste, com 65 métodos `test_*`** na revisão inspecionada:

| Arquivo | Testes | Cobertura observada |
|---|---:|---|
| `tests/test_importar.py` | 28 | Validação de payload, timestamp, negativos rejeitados, dry-run, idempotência por dia, rollback transacional e falha antes de criar DB |
| `tests/test_auditar_resposta.py` | 12 | Reconciliação de totais, divergência, métricas não aditivas, negativos rejeitados e CLI; inclui `test_respeita_tolerancia_de_centavo` |
| `tests/test_validar_integracao_local.py` | 3 | Fluxo local com amostra fictícia e bloqueio de divergência |
| `tests/test_backup_recuperacao.py` | 2 | Exercício de backup/verificação/restauração e manifesto inválido em banco de teste |
| `tests/test_backup_sqlite.py` | 12 | Criação, manifesto, SHA-256/contagens, adulteração, destino e CLI de backup |
| `tests/test_diagnosticar_banco.py` | 8 | Diagnóstico read-only, integridade estrutural e não criação/não alteração do banco |

### Lacunas relevantes para a migração

- Os testes existentes **afirmam o comportamento antigo** de tolerar divergência de R$ 0,01 na auditoria e rejeitar todos os valores negativos. Eles precisarão ser alterados conforme as regras ratificadas por campo; não basta adicionar novos testes mantendo assertions incompatíveis.
- Não foram identificados testes específicos para parsing monetário decimal exato, escala de entrada ratificada, conversão `Decimal → INTEGER`, nomes/constraints das novas colunas, backfill idempotente, dupla escrita atômica, alternância de leitura/rollback ou janela de dez dias úteis.
- Os testes de backup e recuperação usam banco isolado/de teste; **não equivalem** a um backup real verificado nem a um ensaio operacional autorizado em homologação.
- A amostra `amostra_resposta.json` é fictícia segundo o contrato. Não serve como prova do comportamento de sinais no CRM nem da equação de promessas em produção.
- A árvore contém `caixa-futuro-fase1.zip`, artefato binário que não foi inspecionado internamente nesta etapa. Por isso, não declaro fechado o inventário de todos os possíveis consumidores/leitores embutidos nele. A varredura de consumidores permanece um gate antes do corte.
- Resultado CI confirmado para a revisão documental anterior: [workflow #38](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38568801738), `success` no commit `a113a97401d067330944373dcaf3bd6933c4b428`. Isso confirma apenas os testes existentes e a amostra sanitizada/fictícia nesse commit; não prova compatibilidade monetária futura e uma nova execução deve ser confirmada para o head desta atualização.

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

As propostas complementares mais recentes resolveram o desenho técnico dos três bloqueadores principais: (1) colunas por métrica semântica, (2) `REAL congelado` com escrita de compatibilidade mantida por pelo menos 90 dias após o corte e até o descomissionamento formal, e (3) Política v1.1 com validação diferenciada para valores finais e grandezas de cálculo. Essa resolução está registrada como **minuta**, não como prova de assinatura financeira. Até a assinatura da Política v1.1/contrato e aprovação dos gates, a v1.0 permanece a política formalmente aprovada e nenhuma alteração funcional é autorizada.

| Tema | Decisão registrada | Estado/gate técnico |
|---|---|---|
| Sinais negativos | Permitidos somente em depósitos (estorno), `valorRecebidoPeriodo`, `acordos.porUsuario[].pendente` e `promessas.porUsuario[].emAberto`; alerta visível; demais valores e todas as quantidades não negativos | Validar com extração real sanitizada/autorizada e testes por campo; sem payload de CRM nesta análise |
| Entrada decimal | Proposta de Política v1.1 separa valor monetário final de grandeza de cálculo: valores finais aceitam casas excedentes só se forem zeros finais (`1.230` aceito; `1.231` rejeitado); escala interna segue contrato e *half-up* só no resultado final | A solução está registrada como minuta da Política v1.1 e no contrato; aguarda assinatura formal antes de alterar o runtime. Validar a forma original de entrada da origem antes de habilitar |
| Compatibilidade com REAL | Termo proposto passa a ser `REAL congelado`; escritor legado permanece com semântica inalterada durante a dupla escrita, no corte e por pelo menos 90 dias corridos pós-corte, até descomissionamento formal; ambos os lados na mesma transação | Desenho alinhado na minuta v1.1; depende de assinatura formal, inventário de consumidores e testes de atomicidade/rollback com dados pós-corte |
| Esquema | Nomes semânticos por métrica aprovados como proposta documental: oito colunas em `fatos` e três em `acordos_posicao`; `NULL` final significa não aplicável ao tipo e `0` significa zero; CHECK por tipo/sinal e obrigatoriedade gradual | Modelo descrito no contrato proposto v1.1; ainda exige assinatura formal e implementação/teste. Durante backfill, `NULL` em campo aplicável é estado de migração, não semântica final, e precisa de marcador de fase |
| Conversão do histórico | `Decimal(repr(valor))`, *half-up*, função única `real_para_centavos`, relatório de conversões suspeitas | `repr(float)` não recupera de forma garantida a grafia original do JSON. A conversão serve como interpretação determinística do REAL existente, com perda histórica explicitada; definir a regra exata de suspeita |
| Relações contábeis | Acordos: `valor = pagos + pendente`; promessas: `prometido = cumprido + emAberto + quebrado` | A amostra fictícia versionada não comprova a relação das promessas em dados reais. Verificar com extração autorizada antes do alerta |
| Pagamento sem baixa | Continua em pendente/em aberto; só é considerado pago/recebido após baixa confirmada; campo próprio, se existir, deve ser exibido separado e não somado a pagos | Inventariar se a origem fornece esse campo e comprovar como os totais são montados |
| ERP/Systêxtil | Valor calculado pela origem prevalece; app não apresenta cálculo próprio de juros/multa/desconto antes de validar a fórmula contra pelo menos 30 títulos sanitizados | Gate de TI/Contabilidade antes de habilitar cálculo próprio |
| Corte e rollback | Dez dias úteis de conciliação; centavos novos com tolerância zero; 100% das divergências classificadas; Controladoria aprova e Diretoria assina; restauração testada; REAL descomissionado em etapa posterior após 90 dias sem incidentes | Definir calendário/critério para “dia útil”, produzir relatórios reais, obter aprovações e ensaiar rollback em homologação |

## 10. Revisão de consistência técnica

| ID / severidade | Inconsistência ou risco | Tratamento necessário |
|---|---|---|
| TC-01 — **Bloqueador até assinatura** | A minuta v1.1 resolve a distinção: valor final rejeita dígito não zero após a segunda casa; zeros finais são aceitos; grandezas de cálculo preservam a escala contratada e arredondam *half-up* apenas no resultado final | Manter a versão 1.0 como formalmente aprovada até assinatura da v1.1; confirmar a representação aceita pela origem e não ativar regra nova antes da versão aprovada |
| TC-02 — **Bloqueador até assinatura** | A minuta usa “REAL congelado”: legado permanece gravável apenas pelo caminho de compatibilidade, na mesma transação, durante o corte e por no mínimo 90 dias depois; só para no descomissionamento aprovado | Completar o inventário de consumidores REAL; testar falha de cada lado da transação e rollback de leitura com dados pós-corte; manter a escrita legado ativa se o descomissionamento não for aprovado ao final dos 90 dias |
| TC-03 — **Bloqueador até assinatura** | O contrato v1.1 propõe oito colunas semânticas em `fatos` e três em `acordos_posicao`; CHECKs imediatos preservam compatibilidade com linhas antigas ainda não backfilled e restringem tipo/sinal | Antes de criar esquema, obter assinatura formal; implementar validadores por tipo, diagnóstico sensível à fase e triggers de obrigatoriedade apenas depois do backfill conciliado |
| TC-04 — **Alto** | Parsing exato requer validação do token bruto também para inteiros; `parse_float=Decimal` isolado não rejeita expoente e `parse_constant` padrão pode aceitar `NaN`/`Infinity` | Parser único usa `parse_int` e `parse_float` com gramática sem `e/E`, `parse_constant` rejeitante, rejeição explícita de bool e validação de strings somente se declaradas no contrato. A validação integral do payload antecede a transação do dia |
| TC-05 — **Alto** | `Decimal(repr(x))` é determinístico para a representação curta do float, mas não recupera com garantia o texto original (ex.: zeros finais ou grafia equivalente podem já ter sido perdidos) | Documentar conversão de REAL histórico como estimativa técnica auditável, não como reconstrução do payload. Não classificar o centavo convertido como mais verdadeiro que o legado sem reconciliação |
| TC-06 — **Alto** | Os sinais variam por campo; `NULL` é semântica final de não aplicabilidade, mas colunas aditivas estarão temporariamente nulas em linhas históricas antes do backfill | Usar CHECKs de coerência por tipo e de sinal que aceitem NULL durante a fase aditiva; distinguir backfill pendente por marcador de fase, exigir métricas aplicáveis no importador/diagnóstico e ativar triggers depois do backfill e conciliação |
| TC-07 — **Alto** | SQLite não vincula `Decimal` diretamente sem adaptação. A dupla escrita precisa definir como o valor exato em centavos alimenta as colunas novas e como o fluxo legado mantém compatibilidade com REAL | Manter cálculos e reconciliação no domínio Decimal/inteiro; confinar a eventual conversão para REAL ao adaptador legado explicitamente aprovado; realizar ambas as gravações na mesma transação e testar falha de cada lado |
| TC-08 — **Alto** | A relação das promessas está aprovada no documento de decisão, mas não foi comprovada pela evidência atualmente versionada. Os 10 dias úteis de alerta não definem como tratar dias sem carga, falhas nem feriados | Verificar a relação com payload autorizado; definir critério de contagem da janela e exigir carga/auditoria válida por dia antes de avançar o gate |
| TC-09 — **Alto** | A validação de 30 títulos do ERP ainda não foi produzida; arredondar *half-up* pelo app não prova que a fórmula do ERP, sua base de dias e o momento do arredondamento sejam iguais | Deixar cálculo próprio desligado; validar 30 casos reais sanitizados contra a origem e documentar divergências antes de alterar a política |
| TC-10 — **Médio** | O inventário completo de consumidores, testes e CI ainda não está demonstrado | Inspecionar todo o repositório, identificar leituras e escritas de REAL, automatizar os testes e exigir execução verde de CI no PR. Ausência de resultado observado não equivale a CI aprovado nem prova que inexiste workflow |
| TC-11 — **Médio** | A regra de “conversão suspeita” menciona “fração mínima” sem limite numérico operacional | Definir escala, algoritmo, epsilon/limite e formato do relatório em especificação versionada. Não usar tolerância para relaxar a igualdade exata dos dados novos |

### Recomendação de desenho

1. Separar três operações que não devem compartilhar semântica: **parse da origem** (validar formato e escala contratados), **conversão monetária exata** (Decimal para centavos, ou cálculo interno com arredondamento *half-up* apenas no resultado) e **conversão histórica de REAL** (diagnóstico e trilha de auditoria).
2. Manter a regra de igualdade exata para os novos valores em centavos; classificar divergências de legado como evidências de conversão ou erro, sem aplicar tolerância monetária ao dado novo.
3. Manter juros/multa/desconto calculados pelo app desabilitados até aprovação dos 30 títulos e não promover a amostra fictícia a evidência de produção.
4. Tratar TC-01, TC-02 e TC-03 como resolvidos no desenho proposto, mas manter migração de esquema, corte ou modificação do caminho de gravação bloqueados até a assinatura formal da Política v1.1/contrato e aprovação dos gates técnicos.

## 11. Gates obrigatórios antes da implementação/migração

- [ ] Assinatura formal da Política de Precisão Monetária v1.1 e do contrato que registra os desenhos propostos para TC-01 a TC-03.
- [ ] Inventário completo dos consumidores REAL e aprovação final do modelo das oito colunas semânticas em `fatos` e três em `acordos_posicao`.
- [ ] Implementação/testes dos CHECKs, diagnóstico sensível à fase e triggers pós-backfill; nenhuma coluna ou backfill antes da aprovação formal.
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
- [ ] Assinatura formal da Política v1.1 e do contrato monetário proposto; issues #3–#5 permanecem abertas até registro da ratificação.
- [x] Inventário da árvore textual, workflow CI e seis módulos de teste concluído; total de 65 métodos de teste identificados na revisão. [ ] Inventário de todos os consumidores/leitores ainda pendente, incluindo inspeção interna de `caixa-futuro-fase1.zip`.
- [x] GitHub Actions `Testes CAIXA FUTURO` — execução [#40](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38578606271) concluiu `success` no head documental anterior `53426230126fc138a0ad97ca7b81d8bb37530804`, incluindo testes automatizados existentes e amostra sem CRM; [ ] confirmar CI no head desta atualização. Testes específicos da migração ainda não foram implementados/executados.
- [ ] Backup real verificado/restauração testada: não executados.
- [ ] Payload do CRM/ERP real sanitizado: não consultado nem recebido nesta análise.
- [ ] Migração, alteração de schema, dupla escrita, corte ou descomissionamento de REAL: não executados.

A análise é documental e propositiva. Ela não autoriza acesso ao CRM, migração ou alteração de produção e não certifica compatibilidade integral.
