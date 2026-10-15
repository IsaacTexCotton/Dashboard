# Análise de compatibilidade monetária — CAIXA FUTURO

**Status:** análise técnica de compatibilidade atualizada em 15/10/2026; nenhuma alteração funcional, migração de schema ou corte de leitura foi executado.
**Data:** 2026-10-14  
**Branch:** docs/analise-compatibilidade-monetaria  
**Base observada mais recente:** main, commit 92097eb5966e7446b0d632ec1ebd227a5a7520f3.

## 1. Resumo e limites

Foram consultados os documentos de política, contrato, runbook, importador, auditoria, testes e workflow CI. A política v1.1 está descrita como especificação técnica versionada neste repositório. Este documento acompanha regras e evidências técnicas, não registros administrativos. O inventário de leitores de REAL ainda precisa incluir todos os artefatos e consumidores externos. O CI citado corresponde a uma revisão específica; cada alteração deve ser conferida na execução correspondente. Nenhum banco de produção foi aberto; não houve consulta ao CRM nem alteração de schema, backfill ou corte de leitura.

## 2. Evidências verificadas

- A política monetária descreve INTEGER em centavos para novos valores monetários finais, aritmética decimal exata, *half-up* e igualdade exata. A especificação v1.1 detalha regras de entrada por classe de campo e preservação do escritor legado durante a transição.
- O contrato de dados registra que valorRecebidoPeriodo é fluxo do período, enquanto valorAVencer e valorVencido são posições por captura; snapshots devem permanecer no histórico e não ser somados como fluxo.
- O runbook exige diagnóstico e backup verificado antes de operações de banco, e proíbe versionar banco, backup, payload real ou dados pessoais.
- A base da PR documental foi observada em `main` no commit `92097eb5966e7446b0d632ec1ebd227a5a7520f3`; esse hash identifica a base da revisão, não o head documental desta branch.

Referências: [Política](POLITICA_PRECISAO_MONETARIA.md) · [Contrato](../architecture/CONTRATO_DADOS_FINANCEIROS.md) · [Runbook](../operations/RUNBOOK_OPERACIONAL.md) · [Importador](../../importar.py) · [Auditor](../../auditar_resposta.py)

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

- Os testes existentes refletem o comportamento antigo de tolerar divergência de R$ 0,01 na auditoria e rejeitar todos os valores negativos; devem ser revisados conforme as regras técnicas definidas por campo.
- Ainda faltam testes específicos para parsing monetário decimal exato, escala de entrada, conversão `Decimal → INTEGER`, constraints das novas colunas, backfill idempotente, dupla escrita atômica, alternância de leitura/rollback e janela de dez dias úteis.
- Os testes de backup e recuperação usam banco isolado/de teste; **não equivalem** a um backup real verificado nem a um ensaio operacional autorizado em homologação.
- A amostra `amostra_resposta.json` é fictícia segundo o contrato. Não serve como prova do comportamento de sinais no CRM nem da equação de promessas em produção.
- A árvore contém `caixa-futuro-fase1.zip`, artefato binário que não foi inspecionado internamente nesta etapa. Por isso, não declaro fechado o inventário de todos os possíveis consumidores/leitores embutidos nele. A varredura de consumidores permanece um gate antes do corte.
- Último resultado CI confirmado antes desta atualização textual: [workflow #42](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38581680436), `success` no head documental `82c5e3284a3e1db61c55ed77123e245639b93b27`. Isso confirma somente os testes existentes e a amostra fictícia nesse head; não prova compatibilidade monetária futura. A nova alteração documental exige confirmar a execução subsequente.

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

### Matriz de sinais v1.1 — validação da origem pendente

| Campo/métrica | Regra proposta | Validação que continua necessária |
|---|---|---|
| Depósito (`deposito_valor_centavos`) | negativos permitidos | confirmar com dados de origem sanitizados se estorno/crédito usa sinal negativo ou evento separado |
| Valor/face de acordo (`acordo_valor_centavos`) | não negativo | confirmar tratamento de crédito, cancelamento e renegociação |
| Pago/cumprido (`acordo_pago_centavos`, `promessa_cumprido_centavos`) | não negativos | confirmar se estornos são eventos separados |
| Pendente/em aberto (`acordo_pendente_centavos`, `promessa_em_aberto_centavos`) | negativos permitidos | confirmar excedente de pagamento, crédito e abatimentos |
| Quebrado (`promessa_quebrado_centavos`) | não negativo | confirmar semântica da métrica |
| Recebido no período (`recebido_periodo_centavos`) | negativos permitidos | confirmar tratamento de devoluções/estornos e se o total é bruto ou líquido |
| A vencer/vencido (`a_vencer_centavos`, `vencido_centavos`) | não negativos | confirmar representação de crédito/abatimento na carteira |

Esta matriz documenta as regras-alvo para o contrato v1.1. Não alterar o comportamento operacional até que a semântica por campo tenha evidência de origem sanitizada e testes de regressão. Não inferir regra contábil somente pelos nomes.

## 5. Arquitetura recomendada

1. **Entrada:** validar o token JSON bruto com `parse_int` e `parse_float` (ou parser equivalente), aplicando gramática decimal sem `e/E`; rejeitar `NaN`/infinito via `parse_constant`, booleanos por verificação explícita de tipo e strings não autorizadas pelo contrato. Não passar por `float` em cálculos financeiros.
2. Centralizar real_para_centavos(valor_legado), com Decimal e half-up simétrico para longe de zero, saída inteira e tratamento explícito de NULL, valores não finitos e overflow. Para REAL legado, a representação original pode já estar perdida; documentar a conversão determinística e validar com fixtures sintéticas. Não prometer recuperar precisão inexistente.
3. Criar colunas INTEGER paralelas com sufixo _centavos para montantes finais. Preços, quantidades fracionárias e taxas, se aplicáveis, usam escala _eN.
4. **Entrada decimal conforme classe do campo:** para valor monetário final, aceitar casas além da segunda somente se todos os dígitos excedentes forem zero (`1.230` aceito; `1.231` rejeitado sem arredondamento). Para grandezas de cálculo, preservar a escala `_eN` contratada com aritmética exata e aplicar *half-up* somente ao resultado monetário final. Valores oficiais de origem (boleto, extrato, custas) não devem ser recalculados.
5. Manter catálogo explícito de semântica e sinal por campo; nunca corrigir sinal silenciosamente.
6. Conciliar inteiros em centavos por igualdade exata. Relatório por campo/período deve apresentar contagem, total legado convertido, total novo e delta em centavos, separando fluxos de snapshots.
7. Migração aditiva e idempotente: conferir schema, criar apenas colunas ausentes, usar chave primária estável, registrar inválidos sem expor dados pessoais e abortar em incompatibilidade. Não sobrescrever destino divergente sem procedimento de reparo documentado e testado.

### Decisão de desenho consolidada: `REAL congelado` e dupla escrita

A regra técnica `REAL congelado` preserva o schema e a semântica legados, sem interromper a escrita. Após os gates técnicos de compatibilidade, o escritor mantém o caminho legado em `REAL` com semântica inalterada e grava as colunas novas `INTEGER`/`_centavos` na mesma transação SQLite. Falha em qualquer lado deve reverter ambos.

A escrita em `REAL` permanece ativa durante a dupla escrita, durante o corte e por pelo menos 90 dias corridos após o corte; continua depois disso até que os critérios documentados de descomissionamento sejam satisfeitos. Registrar leitores ainda dependentes de `REAL` e comprovar com dados novos que o rollback de leitura encontra os registros pós-corte.

Nenhuma alteração funcional, coluna ou backfill deve ser executado antes de inventário, testes isolados, evidência da origem, backup/restauração verificados, conciliação e rollback ensaiado.
## 6. Plano faseado executável — ainda não executado

### Fase 0 — inventário e semântica
- Mapear todos os leitores/escritores, SQL, views, gráficos, relatórios, exportações e integrações.
- Confirmar formato decimal oficial e sinais por campo.
- Confirmar no contrato os nomes semânticos por métrica, as regras de `NULL`/`CHECK` e a dupla escrita transacional; testar todas as regras em dados sintéticos e em payload sanitizado autorizado antes da implantação.
- Gate: revisão de engenharia concluída, semântica documentada por campo e casos de exceção cobertos por testes.

### Fase 1 — backup e baseline
- Identificar o caminho real por DASHBOARD_DB; não adivinhar.
- Em ambiente autorizado, controlar escritores e executar backup_sqlite.py criar e backup_sqlite.py verificar em destino exclusivo; exigir `status: OK`, `integrity_check` sem falhas e manifesto SHA-256 preservado.
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
- Manter a leitura legada até que a conciliação, CI, backup/restauração e rollback satisfaçam os critérios técnicos de corte; então gravar `REAL` e `_centavos` na mesma transação, preservando a semântica do escritor legado.
- Comparar por campo e período, reportar diferenças de 1 centavo e explicar todas as divergências.
- Manter a escrita em `REAL` durante e após o corte por pelo menos 90 dias corridos e até que os critérios documentados de descomissionamento sejam satisfeitos.
- Gate técnico: zero divergência inexplicada, semântica documentada e resultados da conciliação reproduzíveis.

### Fase 5 — corte e rollback
- Habilitar leitura _centavos primeiro em homologação, com regressão de consultas, relatórios e exportações.
- Definir janela, responsável, gatilhos de aborto e rollback; ensaiar em cópia.
- Antes do corte, reverter descartando o ambiente de teste. Após corte, voltar leitura via feature flag para legado sem apagar colunas novas; avaliar restauração de backup somente após preservar o estado atual e analisar as escritas posteriores conforme o runbook.
- Gate final: conciliação sem divergências inexplicadas, testes/CI verdes, backup e restauração verificados, runbook e responsável operacional definidos.
- Remover REAL somente em release futura separada, após a janela de estabilidade e comprovação de que todos os consumidores usam centavos.

## 7. Testes mínimos especificados

| Categoria | Casos | Esperado |
|---|---|---|
| Half-up positivo | 0,005; 0,004; 1,005; 2,675 | 1, 0, 101, 268 centavos para entradas decimais em reais |
| Half-up negativo | -0,005; -0,004 | -1 e 0 centavos; aceitar só em campos definidos na matriz |
| Importação | 3, 4 e 6 casas decimais | parsing decimal exato; arredondar uma vez no final |
| REAL legado | 1,005; 2,675; 0,1 + 0,2 | conversão determinística e diferenças explicitadas; documentar perda original |
| Somas extensas | muitos itens e frações subcentavo | sem deriva; arredondamento no nível correto |
| Rateio/parcelamento | 10.000 centavos em 3 partes | 3333 + 3333 + 3334; soma exata |
| Reconciliação | diferença 0,00 e 0,01 | igualdade passa; diferença de 1 centavo falha |
| Sinais | negativo por campo, crédito, estorno, abatimento | conforme matriz documentada, sem autorização global |
| Idempotência | repetir migração, schema parcial, destino já preenchido | sem duplicação; conflito explícito |
| Falha/atomicidade | interrupção, constraint, overflow, inválido | rollback; legado preservado |
| Integração | snapshots, fluxos, totais por usuário | sem somar snapshots como fluxos; contagens preservadas |

Estes são testes especificados, não resultados de execução. A integração GitHub usada nesta inspeção não executou a suite local.

## 8. Critérios de saída técnica e financeira

Entregar inventário final, baseline reproduzível, relatório por período/campo com totais e deltas em centavos, classificação documentada de cada divergência, decisão por campo sobre sinais e pagamentos pendentes, CI associado ao commit, backup/restauração verificados e rollback ensaiado. Critério de saída: nenhuma divergência inexplicada; igualdade exata para dados novos.

## 9. Decisões técnicas registradas e estado de validação

As decisões técnicas registradas neste documento cobrem: (1) colunas por métrica semântica, (2) `REAL congelado` com escrita de compatibilidade por pelo menos 90 dias após o corte e até satisfazer critérios de retirada, e (3) validação distinta para valores finais e grandezas de cálculo. A implementação funcional e a migração continuam condicionadas a testes, evidência de origem, inventário, backup/restauração e rollback.

| Tema | Decisão registrada | Estado/gate técnico |
|---|---|---|
| Sinais negativos | Permitidos somente em depósitos (estorno), `valorRecebidoPeriodo`, `acordos.porUsuario[].pendente` e `promessas.porUsuario[].emAberto`; alerta visível; demais valores e todas as quantidades não negativos | Validar com extração real sanitizada/autorizada e testes por campo; sem payload de CRM nesta análise |
| Entrada decimal | A especificação v1.1 separa valor monetário final de grandeza de cálculo: valores finais aceitam casas excedentes somente se forem zeros finais (`1.230` aceito; `1.231` rejeitado); escala interna segue contrato e *half-up* só no resultado final | Validar a grafia original de entrada e os casos de fronteira com testes antes de habilitar o caminho novo |
| Compatibilidade com REAL | `REAL congelado`: o writer legado mantém semântica durante dupla escrita, corte e pelo menos 90 dias corridos pós-corte, até os critérios documentados de retirada; ambas as representações na mesma transação | Inventário de consumidores completo e testes de atomicidade/rollback com dados pós-corte |
| Esquema | O modelo define oito colunas semânticas em `fatos` e três em `acordos_posicao`; `NULL` final significa não aplicável e `0` significa zero; CHECK por tipo/sinal e obrigatoriedade gradual | Implementar e testar o modelo em banco descartável; durante backfill, diferenciar NULL transitório por marcador de fase |
| Conversão do histórico | `Decimal(repr(valor))`, *half-up*, função única `real_para_centavos`, relatório de conversões suspeitas | `repr(float)` não recupera de forma garantida a grafia original do JSON. A conversão serve como interpretação determinística do REAL existente, com perda histórica explicitada; definir a regra exata de suspeita |
| Relações contábeis | Acordos: `valor = pagos + pendente`; promessas: `prometido = cumprido + emAberto + quebrado` | A amostra fictícia versionada não comprova a relação das promessas em dados reais. Verificar com extração autorizada antes do alerta |
| Pagamento sem baixa | Continua em pendente/em aberto; só é considerado pago/recebido após baixa confirmada; campo próprio, se existir, deve ser exibido separado e não somado a pagos | Inventariar se a origem fornece esse campo e comprovar como os totais são montados |
| ERP/Systêxtil | Valor calculado pela origem prevalece; app não apresenta cálculo próprio de juros/multa/desconto antes de validar a fórmula contra pelo menos 30 títulos sanitizados | Gate de TI/Contabilidade antes de habilitar cálculo próprio |
| Corte e rollback | Dez dias úteis de conciliação; centavos novos com tolerância zero; 100% das divergências classificadas; restauração testada; REAL removido apenas em etapa separada após 90 dias sem incidentes | Definir calendário de dia útil, produzir relatórios reais e ensaiar rollback em homologação |

## 10. Revisão de consistência técnica

| ID / severidade | Inconsistência ou risco | Tratamento necessário |
|---|---|---|
| TC-01 — **Bloqueador técnico** | Valor final rejeita dígito não zero após a segunda casa; zeros finais são aceitos; grandezas de cálculo preservam a escala contratada e aplicam *half-up* ao resultado final | Confirmar a representação aceita pela origem e testar a regra sem arredondar a entrada |
| TC-02 — **Bloqueador técnico** | `REAL congelado`: legado permanece gravável no caminho de compatibilidade na mesma transação durante e após o corte | Completar inventário de consumidores REAL; testar falha de cada lado e rollback com dados pós-corte |
| TC-03 — **Bloqueador técnico** | O contrato define oito colunas semânticas em `fatos` e três em `acordos_posicao`; CHECKs preservam linhas legadas durante backfill | Implementar validadores por tipo, diagnóstico por fase e triggers pós-backfill somente em banco descartável e com testes verdes |
| TC-04 — **Alto** | Parsing exato requer validação do token bruto também para inteiros; `parse_float=Decimal` isolado não rejeita expoente e `parse_constant` padrão pode aceitar `NaN`/`Infinity` | Parser único usa `parse_int` e `parse_float` com gramática sem `e/E`, `parse_constant` rejeitante, rejeição explícita de bool e validação de strings somente se declaradas no contrato. A validação integral do payload antecede a transação do dia |
| TC-05 — **Alto** | `Decimal(repr(x))` é determinístico para a representação curta do float, mas não recupera com garantia o texto original (ex.: zeros finais ou grafia equivalente podem já ter sido perdidos) | Documentar conversão de REAL histórico como estimativa técnica auditável, não como reconstrução do payload. Não classificar o centavo convertido como mais verdadeiro que o legado sem reconciliação |
| TC-06 — **Alto** | Os sinais variam por campo; `NULL` é semântica final de não aplicabilidade, mas colunas aditivas estarão temporariamente nulas em linhas históricas antes do backfill | Usar CHECKs de coerência por tipo e de sinal que aceitem NULL durante a fase aditiva; distinguir backfill pendente por marcador de fase, exigir métricas aplicáveis no importador/diagnóstico e ativar triggers depois do backfill e conciliação |
| TC-07 — **Alto** | SQLite não vincula `Decimal` diretamente sem adaptação. A dupla escrita precisa definir como valores exatos alimentam colunas novas e como o fluxo legado mantém compatibilidade | Manter cálculos no domínio Decimal/inteiro; documentar e testar o adaptador de compatibilidade REAL; comprovar atomicidade e rollback |
| TC-08 — **Alto** | A relação das promessas está descrita nos documentos, mas ainda não foi comprovada por evidência suficiente. Os 10 dias úteis não definem dias sem carga, falhas nem feriados | Verificar relação com payload sanitizado e definir contagem da janela com critérios reproduzíveis |
| TC-09 — **Alto** | A validação de 30 títulos do ERP ainda não foi produzida; arredondar *half-up* pelo app não prova que a fórmula do ERP, sua base de dias e o momento do arredondamento sejam iguais | Deixar cálculo próprio desligado; validar 30 casos reais sanitizados contra a origem e documentar divergências antes de alterar a política |
| TC-10 — **Médio** | O inventário de consumidores, testes e CI ainda não está completo | Inspecionar repositório e consumidores externos; identificar leituras/escritas de REAL; obter execução verde de CI no commit integrado; ausência de resultado observado não prova ausência de workflow |
| TC-11 — **Médio** | A regra de “conversão suspeita” menciona “fração mínima” sem limite numérico operacional | Definir escala, algoritmo, epsilon/limite e formato do relatório em especificação versionada. Não usar tolerância para relaxar a igualdade exata dos dados novos |

### Recomendação de desenho

1. Separar três operações que não devem compartilhar semântica: **parse da origem** (validar formato e escala contratados), **conversão monetária exata** (Decimal para centavos, ou cálculo interno com arredondamento *half-up* apenas no resultado) e **conversão histórica de REAL** (diagnóstico e trilha de auditoria).
2. Manter a regra de igualdade exata para os novos valores em centavos; classificar divergências de legado como evidências de conversão ou erro, sem aplicar tolerância monetária ao dado novo.
3. Manter juros/multa/desconto calculados pelo app desabilitados até validar 30 títulos sanitizados contra os valores de origem; não tratar a amostra fictícia como evidência de produção.
4. Tratar TC-01, TC-02 e TC-03 como resolvidos apenas no desenho técnico; manter migração de schema, corte ou modificação do caminho de gravação bloqueados até que os gates técnicos sejam demonstrados.

## 11. Gates obrigatórios antes da implementação/migração

- [ ] Política v1.1 e contrato versionados, consistentes e com regras de escala reproduzíveis.
- [ ] Inventário completo dos consumidores REAL e modelo das oito colunas semânticas em `fatos` e três em `acordos_posicao` documentado.
- [ ] Implementação/testes dos CHECKs, diagnóstico sensível à fase e triggers pós-backfill; nenhuma coluna ou backfill antes da validação técnica em banco descartável.
- [ ] Especificação do parser: tipos JSON/strings aceitos, rejeição de notação científica, escala, booleanos/nulos, limites e política para mais de duas casas.
- [ ] Extração real sanitizada e autorizada para validar sinais, semântica do pagamento sem baixa e equação das promessas.
- [ ] Evidência de ao menos 30 títulos sanitizados comparados com ERP/Systêxtil antes de habilitar cálculos próprios de encargos.
- [ ] Inventário completo de consumidores, testes e CI; testes automatizados verdes.
- [ ] Backup com manifesto/SHA-256 e restauração verificada em homologação, seguindo `RUNBOOK_OPERACIONAL.md`.
- [ ] Dez dias úteis de conciliação diária, divergências 100% classificadas e zero divergência inexplicada.
- [ ] Plano de rollback testado antes do corte; descomissionamento de REAL em release separada após 90 dias corridos sem incidentes e inventário de consumidores atualizado.

### Acompanhamento explícito dos bloqueadores no GitHub

- [ ] [Issue #3 — Definir regra de entrada monetária com mais de 2 casas](https://github.com/IsaacTexCotton/Dashboard/issues/3) — validar token de origem e casos de fronteira.
- [ ] [Issue #4 — Definir contrato de dupla escrita REAL/INTEGER](https://github.com/IsaacTexCotton/Dashboard/issues/4) — inventário completo e teste de atomicidade/rollback.
- [ ] [Issue #5 — Definir colunas INTEGER específicas por métrica](https://github.com/IsaacTexCotton/Dashboard/issues/5) — validar constraints por tipo/sinal em banco descartável.
 
## 12. Estado desta entrega

- [x] Política, contrato, runbook, importador, auditoria e esquema atual consultados remotamente.
- [x] Decisões recebidas comparadas com política, contrato e implementação observável.
- [x] Revisão de consistência técnica e plano de execução preparados em documentos da mesma branch.
- [ ] Política v1.1 e contrato monetário versionados; issues #3–#5 encerradas quando seus critérios técnicos reproduzíveis forem atendidos.
- [x] Inventário da árvore textual, workflow CI e seis módulos de teste concluído; total de 65 métodos de teste identificados na revisão. [ ] Inventário de todos os consumidores/leitores ainda pendente, incluindo inspeção interna de `caixa-futuro-fase1.zip`.
- [x] GitHub Actions `Testes CAIXA FUTURO` — execução [#42](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38581680436) concluiu `success` no head documental `82c5e3284a3e1db61c55ed77123e245639b93b27`, incluindo testes automatizados existentes e amostra sem CRM; a alteração deste próprio relatório exige uma execução atualizada. Testes específicos da migração ainda não foram implementados/executados.
- [ ] Backup real verificado/restauração testada: não executados.
- [ ] Payload do CRM/ERP real sanitizado: não consultado nem recebido nesta análise.
- [ ] Migração, alteração de schema, dupla escrita, corte ou descomissionamento de REAL: não executados.

A análise é documental e propositiva. Ela não autoriza acesso ao CRM, migração ou alteração de produção e não certifica compatibilidade integral.
