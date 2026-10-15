# Plano de execução — Migração monetária para centavos inteiros

**Projeto:** Dashboard de Cobrança (CAIXA FUTURO), Contas a Pagar / Financeiro  
**Data:** 14/10/2026  
**Estado:** plano técnico por fases, atualizado em 15/10/2026; avanço orientado por critérios verificáveis.
**Branch de documentação:** `docs/analise-compatibilidade-monetaria`  
**Regra de segurança:** nenhuma alteração de schema, migração, dupla escrita ou corte de produção está autorizada por este documento.

## 1. Objetivo e resultado esperado

Migrar valores monetários de `REAL` para `INTEGER` em centavos, com parsing decimal exato, conciliação sem tolerância nos dados novos e rollback por chave de configuração, mantendo a compatibilidade do dashboard durante a transição. As colunas legadas permanecem durante a transição e só são retiradas em release separada após satisfazer critérios técnicos documentados.

A execução deve ocorrer em branch de implementação própria e PRs revisáveis. Esta PR é documental e não deve misturar mudança de regras operacionais com código da migração.

## 2. Bloqueios de desenho que precedem código

| ID | Decisão necessária | Proposta técnica para avaliação | Gate |
|---|---|---|---|
| G-01 | Regra de escala da entrada monetária | Valor final aceita casas excedentes apenas quando os dígitos após a 2ª casa são zeros (`1.230` aceito; `1.231` rejeitado); grandezas de cálculo preservam escala contratada e arredondam *half-up* no resultado; cada campo é classificado no contrato | Contrato versionado, exemplos de fronteira reproduzíveis, payload sanitizado e testes da gramática de entrada |
| G-02 | Continuidade da escrita em REAL | Preservar a semântica legada durante dupla escrita, corte e por ao menos 90 dias corridos pós-corte; centavos e REAL na mesma transação SQLite | Inventário de leitores, teste de atomicidade e rollback pós-corte com dados novos em SQLite descartável |
| G-03 | Esquema por métrica e regras NULL/CHECK | O contrato define oito colunas em `fatos` e três em `acordos_posicao`; CHECK por tipo/sinal; obrigatoriedade gradual após backfill conciliado | DDL aditiva e idempotente verificada em banco descartável; testes de CHECK, NULL, zero e fases; restauração de backup ensaiada |
| G-04 | Regra de conversão suspeita do REAL legado | Definir fórmula e limite reproduzível, separado das regras de entrada nova | Especificação do algoritmo, exemplos e resultados determinísticos nos testes |
| G-05 | Sinais na origem e relação das promessas | Validar os sinais por campo e a identidade das promessas com amostra sanitizada obtida por canal corporativo autorizado | Evidência por campo/cenário e testes de regressão; não inferir regras a partir da amostra fictícia |
| G-06 | Fórmulas ERP/Systêxtil não validadas | Obter ao menos 30 títulos reais sanitizados e reproduzir ao centavo antes de habilitar qualquer cálculo próprio de encargo | Contabilidade + TI |

**A especificação monetária v1.1 está documentada em versão controlada.** DDL, backfill, escrita dupla em produção e corte continuam bloqueados até que os gates técnicos sejam demonstrados: backup/restauração verificados, CI verde, evidência da origem, conciliação, rollback ensaiado e janela operacional registrada.

## 3. Fases, tarefas e critérios de saída

### Fase 0 — Governança e contrato

**Tarefas**
- Consolidar e versionar decisões de negócio, sem ambiguidades críticas de implementação.
- Resolver G-01 a G-04 e versionar a Política de Precisão Monetária/contrato de dados.
- Fixar contrato de entrada: número JSON ou string decimal, sinal, escala, notação científica, nulo/ausente, separador decimal, limites de magnitude e tratamento de mais de duas casas.
- Fixar nome e tipo de cada nova coluna, nulabilidade, condições de `CHECK` e chave de reconciliação.

**Saída:** documentos versionados, regras consistentes e ambiguidades críticas resolvidas por critérios verificáveis.

### Fase 1 — Inventário de leituras, escritas e baseline

**Tarefas**
- Localizar todas as leituras e gravações das colunas `REAL`, não só `importar.py`: dashboards, relatórios, exportações, APIs, queries, scripts e tarefas operacionais.
- Identificar testes existentes e workflows de CI; registrar comandos e resultados reais.
- Confirmar o caminho do DB via configuração operacional (ex.: `DASHBOARD_DB`), processos escritores, esquema, `user_version`, contagens e integridade, sem presumir arquivo/caminho.
- Rodar importação/auditoria em arquivo sanitizado autorizado; capturar baseline por dia, usuário, tipo e métrica.
- Solicitar e guardar fora do Git a evidência autorizada de payloads de origem; não consultar CRM por iniciativa deste plano.

**Saída:** matriz leitor/escritor/consumidor, baseline reconciliado e inventário de testes/CI revisado.

### Fase 2 — Backup e recuperação operacional

**Tarefas**
- Seguir `RUNBOOK_OPERACIONAL.md`: diagnóstico inicial, investigação de qualquer `FAIL` e avaliação de `WARN`.
- Criar backup com `backup_sqlite.py criar`, manifesto e SHA-256; executar `backup_sqlite.py verificar`.
- Restaurar o backup numa cópia de homologação isolada e verificar integridade, `user_version`, contagens e funcionamento de leitura do dashboard.
- Registrar dono, local restrito, hashes, contagens e resultado do exercício. Não versionar banco, backup, manifesto nem payload real.

**Saída:** backup verificado e restauração comprovada em homologação. Backup verificado sem teste de restauração não satisfaz o gate de corte.

### Fase 3 — Parsing e domínio monetário exato, sem persistência

**Estado do código (15/10/2026):** parser JSON estrito, conversão de valor final para centavos, conversão determinística do REAL histórico, matriz de sinais por campo e testes de precisão estão implementados. No fluxo exato de dupla escrita/auditoria, a validação preserva `Decimal`/`int`; o `float` permanece restrito ao adaptador de compatibilidade REAL. Os sinais ainda precisam ser verificados com extração da origem sanitizada e autorizada.

**Tarefas**
- Implementar módulo comum de parsing/conversão, reutilizado por importador e auditoria; evitar dois parsers divergentes.
- Validar a grafia do token JSON antes de criar `Decimal`, usando `parse_int` e `parse_float` com uma gramática que rejeita `e/E` e `parse_constant` que rejeita `NaN`/`Infinity`. Rejeitar booleanos explicitamente; strings só são aceitas se o contrato as declarar permitidas para o campo.
- Para valores monetários finais, aceitar casas além de duas apenas quando os dígitos excedentes são zeros (`1.230` → 123 centavos); rejeitar (`1.231`) sem arredondamento. Em grandezas de cálculo com escala contratada, preservar decimal exato e aplicar *half-up* apenas no resultado final. Validar o payload inteiro antes da transação diária.
- Converter `Decimal` para centavos com aritmética decimal exata, limites de inteiro de 64 bits e política explícita para nulo versus zero.
- Centralizar a matriz de sinal por campo e tipo; emitir alerta visível de crédito/estorno para negativos permitidos.
- Implementar `real_para_centavos` apenas para histórico, via `Decimal(repr(valor))` e *half-up*, com relatório de suspeitas cujo algoritmo/limite esteja documentado. Não tratar o texto original como recuperável.

**Saída:** testes unitários verdes; importação e banco permanecem sem alteração.

### Fase 4 — Auditoria exata e semântica contábil

**Estado do código (15/10/2026):** a soma e a comparação dos totais monetários são calculadas em centavos inteiros com tolerância zero, com testes de diferença de um centavo e de precisão inválida. A igualdade `valor = pagos + pendente` e a regra equivalente das promessas não são bloqueantes, pois as exceções contábeis ainda não foram classificadas e testadas.

**Tarefas**
- [x] Implementado: auditoria monetária compara inteiros em centavos com igualdade exata; quantidades/contagens permanecem inteiras e exatas.
- Implementar checks separados para somas agregadas de origem versus usuários, identidade de acordos e identidade de promessas. Não somar `contatosUnicosTotal` entre usuários.
- Tratar `valorRecebidoPeriodo` como fluxo do período e `valorAVencer`/`valorVencido` como posição por captura: nunca somar snapshots de capturas diferentes como fluxo.
- Confirmar a regra das promessas e as exceções contábeis com payload real sanitizado, com foco em desconto, renegociação, cancelamento, pagamento parcial e pagamento informado sem baixa.
- Gerar relatório que distingue divergência de origem, falha de regra, conversão histórica suspeita e dado ausente.

**Saída:** todas as divergências de testes são explicáveis; regras contábeis foram comprovadas ou os casos pendentes permanecem explicitamente não bloqueantes.

### Fase 5 — Migração de esquema aditiva e backfill idempotente

**Estado do código (15/10/2026):** migração aditiva/idempotente, 11 colunas de métricas em centavos e dois marcadores `monetario_fase` por linha estão implementados; a fase global e os guardas de fase são validados, e o backfill/diagnóstico têm testes sintéticos. Isso não significa que o script foi aplicado a um banco real. Um relatório operacional completo de conversões históricas suspeitas e a execução autorizada em homologação permanecem pendentes.

**Pré-condições:** Fases 0–4 atendidas; backup e restauração verificados; revisão técnica concluída; CI verde.

**Tarefas**
- Criar migração versionada e idempotente para as colunas semânticas definidas no contrato:
- Preservar `NULL` quando significar “não informado”; não converter ausência para zero sem regra explícita e testada.
- Backfill do histórico a partir do REAL com `real_para_centavos`; marcar cada conversão suspeita e manter chave/valor original para auditoria.
- Adicionar CHECKs imediatos: cada métrica de `fatos` só pode ser não nula para o `tipo` aplicável; CHECKs de sinal permitem negativos apenas em `deposito_valor_centavos`, `acordo_pendente_centavos`, `promessa_em_aberto_centavos` e `recebido_periodo_centavos`. NULL é aceito durante backfill; para `fatos`, o estado final NULL significa não aplicável e zero significa zero real.
- Fazer `diagnosticar_banco.py` sensível à fase: NULL em métrica aplicável de linha histórica é pendência enquanto backfill estiver incompleto; métrica ausente em nova gravação após ativar dupla escrita é falha; depois do backfill conciliado, ausência em métrica aplicável deve falhar. Instalar triggers de obrigatoriedade somente após backfill e conciliação completos.
- Reexecutar a migração e comprovar que não duplica nem altera valores previamente migrados.

**Saída:** mesma contagem de registros e mesmas chaves; nenhuma alteração destrutiva; relatório de backfill integral e idempotência comprovada.

### Fase 6 — Dupla escrita transacional e conciliação técnica

**Estado do código (15/10/2026):** escrita dupla do mesmo `Decimal` em REAL compatível e centavos na mesma transação, gravação da fase `dual`, reimportação/idempotência, atomicidade em arquivo e leitor concorrente têm cobertura sintética. O diagnóstico compara cada par exatamente. O leitor do dashboard por centavos ainda não existe no repositório; a flag `LEITURA_CENTAVOS=1` é recusada, logo não houve corte nem teste de rollback de leitura pós-corte.

**Tarefas**
- Modificar o escritor somente após os testes isolados de G-02 demonstrarem atomicidade, idempotência e rollback.
- Calcular as colunas novas diretamente a partir do Decimal validado, não convertendo REAL de volta a centavos para dados novos.
- Não usar REAL em cálculos, filtros monetários ou comparações no fluxo novo; se a compatibilidade exigir valor REAL, confinar o cast ao adaptador legado e documentá-lo.
- Forçar falhas em cada lado (REAL e centavos) e provar rollback integral da transação; testar retry/idempotência, reprocessamento de um dia e rollback da leitura após o corte usando dados novos do período pós-corte.
- Emitir relatório diário por chave/métrica que classifique todas as diferenças como conversão histórica suspeita ou erro a corrigir.

**Saída:** atomicidade, idempotência e reconciliação técnica demonstradas em homologação; nenhuma divergência sem classificação.

### Fase 7 — Alerta contábil por dez dias úteis

**Tarefas**
- Ativar primeiro o modo de alerta; não bloquear por identidades contábeis até completar dez dias úteis consecutivos com carga válida e análise diária.
- Definir operacionalmente o calendário de dia útil, falha de carga, dia sem payload e reinício/pausa da contagem antes de ativar a janela.
- Verificar todos os casos de exceção da decisão de negócio. Falhas e dias sem evidência não devem ser contados automaticamente como observação válida.
- Arquivar relatório diário e classificação registrada de cada divergência.

**Saída:** 10 dias úteis válidos, resultados documentados e 100% das divergências classificadas/corrigidas antes de habilitar bloqueio.

### Fase 8 — Corte de leitura e rollback

**Pré-condições obrigatórias**
- Política monetária v1.1 e contrato de dados versionados e tecnicamente consistentes.
- CI verde no head a integrar e testes específicos de parsing, schema, backfill, dupla escrita, diagnóstico e rollback verdes.
- Backup, manifesto e SHA-256 verificados; restauração em homologação ensaiada.
- Dez dias úteis consecutivos de conciliação válida; zero divergência inexplicada e 100% das divergências classificadas.
- Regras de sinais validadas com evidência de origem; regras contábeis e 30 títulos do ERP validados conforme aplicável.
- Inventário anexo lista os consumidores que ainda leem REAL e o gate/data planejada para cada um migrar leitura para centavos.
- Relatórios de conciliação revisados e critérios técnicos de corte satisfeitos; responsável operacional e janela de mudança registrados.

**Estado atual:** esta fase não pode iniciar enquanto não houver leitor de centavos integrado ao dashboard e todos os gates operacionais tiverem evidência. O importador recusa `LEITURA_CENTAVOS=1` em vez de fingir que o corte ocorreu.

**Tarefas**
- Alternar leitura para centavos com chave/configuração reversível.
- Fazer smoke tests de dashboards, totais, filtros, exportações e auditoria.
- **Manter a escrita legada REAL ativa** durante e depois do corte; a chave de leitura não altera nem interrompe a gravação de compatibilidade.
- Monitorar alertas e comparativos após o corte; registrar responsável e procedimento de acionamento.
- Testar o rollback com dados criados/importados **depois do corte**: confirmar que as novas linhas foram escritas em REAL e INTEGER na mesma transação e que a reversão da leitura para REAL exibe esses mesmos dados.
- Em divergência inexplicada ou falha de integridade, reverter leitura às colunas legadas imediatamente; restaurar backup somente se necessário e conforme plano ensaiado.

**Saída:** corte registrado, escrita legada ainda ativa, métricas de saúde acompanhadas e rollback demonstrado com dados pós-corte.

### Fase 9 — Descomissionamento separado

A escrita legada em REAL permanece ativa durante os 90 dias corridos posteriores ao corte e além desse período até que os critérios documentados de descomissionamento sejam satisfeitos. Registrar inventário de consumidores que ainda leem REAL e evidência de migração de cada leitor. Não remover colunas automaticamente pelo decurso do prazo.

## 4. Matriz mínima de testes

| Grupo | Casos obrigatórios | Resultado esperado |
|---|---|---|
| Parsing | JSON number/integer, string somente se contratada, nulo, ausente, booleano, texto inválido, vírgula decimal, `NaN`, infinito, token com `e/E` | Formatos previstos aceitos; formatos não contratuais rejeitados com erro controlado antes da transação |
| Escala de entrada | Valores finais `1.23`, `1.230`, `1.231` e entradas com 3/4/6 casas | `1.23` e `1.230` aceitos; qualquer dígito não zero além da 2ª casa (ex.: `1.231`) rejeita sem arredondamento; classes de cálculo seguem escala `_eN` contratada |
| Arredondamento interno | `0.005`, `0.004`, `-0.005`, `1.005`, `2.675`, `0.1 + 0.2`, `0.29`, `1e-7` | *Half-up* correto somente nos caminhos de cálculo/conversão onde ele é permitido; notação científica de entrada tratada conforme contrato |
| Sinal por campo | Negativo, positivo e zero para cada campo definido; negativo para todos os campos proibidos; contagens negativas | Regras aplicadas campo+tipo, alertas emitidos e entradas indevidas rejeitadas |
| Aritmética | Soma longa sem deriva; igualdade exata com diferença de 1 centavo; rateio de 10.000 centavos em 3.333 + 3.333 + 3.334 | Soma exata; divergência de 1 centavo identificada; rateio preserva total |
| Identidade contábil | Acordo pago total/parcial, pendente, crédito; promessa cumprida/em aberto/quebrada; cancelamento, desconto, renegociação e baixa pendente | Igualdades corretas ou exceção classificada; não contar pago antes de baixa |
| Histórico REAL | `1.005`, `2.675`, `0.1 + 0.2`, nulo, valor negativo autorizado, valor com representação longa | Conversão determinística *half-up* e suspeitas listadas sem reescrita silenciosa do histórico |
| Banco/transaction | Migração repetida, colunas já existentes, falha na gravação nova, falha na escrita legada, rollback, interrupção e retry | Migração idempotente; nenhuma transação parcial; registros/chaves preservados |
| Regras temporais | fluxo `recebido_periodo`, snapshots `a_vencer`/`vencido`, timestamp original, dia sem carga, contagem dos 10 dias úteis | Fluxo e posição não confundidos; timestamp preservado; janela de alerta segue calendário definido e dias sem carga não contam automaticamente |
| CHECK/obrigatoriedade faseada | NULL legado antes de backfill, zero, coluna não aplicável ao tipo, sinal, marker de fase, triggers pós-backfill | Linhas históricas incompletas não bloqueiam a migração aditiva; dados novos inválidos falham; após backfill conciliado, ausência em métrica aplicável falha |
| Rollback após corte | Importar um registro novo depois do corte, forçar mudança de chave de leitura, confirmar retorno a REAL | O registro pós-corte permanece visível ao voltar a REAL; a escrita legada não foi encerrada antes do descomissionamento |
| Integração | CLI do importador, auditoria, dashboard, relatórios, exportações, workflow CI | Compatibilidade comprovada por testes de regressão e CI verde |

## 5. Critérios de conciliação e saída

- **Dados novos:** igualdade exata em centavos; tolerância zero.
- **Legado REAL versus INTEGER:** 100% das diferenças classificadas como conversão histórica suspeita, com registro e valor identificados, ou erro corrigido. Nenhuma divergência inexplicada.
- **Janela:** dez dias úteis consecutivos de dupla escrita e conciliação diária, sob critério de calendário definido antes de iniciar.
- **Registro operacional:** manter histórico da execução, responsável, janela, evidências e resultado técnico do corte.
- **Backup:** manifesto e SHA-256 conferidos e restauração ensaiada em homologação.
- **Retirada de REAL:** release separada após 90 dias corridos sem incidentes, inventário completo e comprovação de que todos os consumidores migraram para centavos.

## 6. Rollback

1. Acionar rollback diante de divergência inexplicada ou falha de integridade.
2. Reverter imediatamente a chave de leitura para as colunas legadas; confirmar smoke tests e registrar horário, responsável, motivo e alcance.
3. Se o banco estiver comprometido, restaurar backup verificado conforme exercício ensaiado; validar integridade, contagens, `user_version` e funcionamento.
4. Não apagar colunas novas nem remodelar schema durante resposta emergencial; preservar logs, relatórios e evidências para análise.

## 7. Evidências a anexar ao PR de implementação

- Versão da política/contrato e histórico das decisões técnicas.
- Matriz completa de leitores e escritores, incluindo anexo por consumidor que informa dependência atual de REAL e data/gate planejado para mudar a leitura.
- Payload sanitizado e autorizado / resultados de 30 títulos mantidos fora do Git, mais relatório com hashes e resultados não sensíveis.
- Resultados de testes unitários/integrados e CI.
- Manifesto do backup, SHA-256 e relatório de restauração, mantendo artefatos sensíveis em armazenamento restrito.
- Relatórios diários dos dez dias úteis e classificação documentada das divergências.
- Procedimento e evidência de rollback em homologação.

## 8. Estado atual

As decisões de desenho técnico registradas neste plano são: nomes semânticos por métrica, `REAL congelado` com escrita legada mantida ao menos 90 dias pós-corte e distinção entre valores finais e grandezas de cálculo. Nenhum backfill, corte ou alteração de banco real será executado sem evidência dos gates técnicos, configuração do ambiente confirmada, backup/restauração verificados e janela operacional registrada.

**Atualização de estado (15/10/2026):** o conjunto atual inclui testes específicos de parsing/precisão, mapeamento por métrica, esquema aditivo, backfill, flags, dupla escrita, reimportação, atomicidade, diagnóstico por fase e preservação de valores `REAL`. O CI executa a suíte completa e valida a amostra fictícia sem CRM. Verificar o status do workflow no HEAD candidato, não usar o antigo run #42 como evidência atual. Nenhum backup/restauração operacional em homologação, migração/backfill real, acesso ao CRM/ERP ou corte de leitura foi executado nesta implementação.


### Bloqueadores rastreados no GitHub

- [Issue #3 — Definir regra de entrada monetária com mais de 2 casas](https://github.com/IsaacTexCotton/Dashboard/issues/3)
- [Issue #4 — Definir contrato de dupla escrita REAL/INTEGER](https://github.com/IsaacTexCotton/Dashboard/issues/4)
- [Issue #5 — Definir colunas INTEGER específicas por métrica](https://github.com/IsaacTexCotton/Dashboard/issues/5)

Os três itens precisam ter definição técnica versionada, testes reproduzíveis e critérios de aceite documentados antes da PR funcional de migração.

## 9. Inventário de testes/CI confirmado (15/10/2026)

A árvore de `main` contém 15 módulos de teste Python e 189 métodos `test_*`. O workflow `.github/workflows/testes.yml` executa `unittest discover -s tests` em Python 3.11 e as validações locais da amostra fictícia sem CRM.

A execução [#38754594110](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38754594110) passou com 189 testes no HEAD da PR #32 (`9d4ad634d987ba6ac96bc31a2217c77fb47c4560)), antes de a alteração ser integrada à `main`. Esse HEAD continha a mesma árvore de código/testes que foi integrada pelo commit `ecb3c2f7381a000ef157669a66a51fe74e217677`; a execução é evidência do candidato testado, não um check separado emitido sobre o SHA de merge.

| Arquivo | Testes | Cobertura principal |
|---|---:|---|
| `tests/test_auditar_resposta.py` | 17 | Conciliação de totais em centavos inteiros, divergência de 1 centavo, precisão excedente e rejeição de `float` |
| `tests/test_backfill_monetario.py` | 8 | Simulação, idempotência, rollback por conflito e transição de fase |
| `tests/test_backup_recuperacao.py` | 2 | Recuperação em SQLite descartável; não substitui ensaio operacional |
| `tests/test_backup_sqlite.py` | 12 | Manifesto, hash, verificação, corrupção e preservação de registros |
| `tests/test_diagnosticar_banco.py` | 12 | Diagnóstico somente-leitura, coerência REAL/centavos e fase |
| `tests/test_escrita_dupla.py` | 13 | Escrita atômica REAL/INTEGER, falhas, interrupção em arquivo e leitor concorrente |
| `tests/test_flags_monetarias.py` | 9 | Defaults, precedência/compatibilidade, validação das flags e leitura ainda não implementada |
| `tests/test_importar.py` | 41 | Parser estrito, normalização, transação, timestamp, reimportação e validação |
| `tests/test_issue4_reimportacao_escrita_dupla.py` | 1 | Reimportação substitui fatos nas duas representações e mantém snapshots por timestamp |
| `tests/test_migrar_schema_monetario.py` | 17 | DDL aditivo/idempotente, checksum de REAL, fases, guardas e rollback |
| `tests/test_modelo_monetario.py` | 12 | Mapeamento semântico, aplicabilidade, sinais e NULL versus zero |
| `tests/test_precisao_monetaria.py` | 32 | Decimal exato, token JSON, centavos, sinais, escala e limites |
| `tests/test_preparacao_migracao_monetaria.py` | 3 | Fixtures sintéticas, backfill simulado e backup/restauração em banco descartável |
| `tests/test_prototipo_issue5_schema_monetario.py` | 7 | CHECKs, afinidade SQLite, aplicabilidade e protótipo de esquema |
| `tests/test_validar_integracao_local.py` | 3 | Fluxo de integração local com amostra fictícia, sem CRM |

**Interpretação do resultado:** CI verde confirma somente os cenários cobertos pelas fixtures/testes. Não comprova semântica final dos sinais da origem, inventário completo de consumidores externos, restauração operacional em homologação, migração/backfill em banco real nem cutover de leitura.

A árvore também contém `caixa-futuro-fase1.zip`, mas a listagem do pacote feita em 15/10/2026 não mostrou UI/relatórios de leitura por centavos. Não conectar a flag de leitura a um consumidor hipotético: o leitor de centavos do dashboard ainda precisa ser identificado/integrado; por isso `LEITURA_CENTAVOS=1` continua sendo recusada.
