# Plano de execução — Migração monetária para centavos inteiros

**Projeto:** Dashboard de Cobrança (CAIXA FUTURO), Contas a Pagar / Financeiro  
**Data:** 14/10/2026  
**Estado:** Política v1.1 ratificada pelo solicitante em 14/10/2026; plano técnico em execução por etapas, com gates operacionais ainda obrigatórios.  
**Branch de documentação:** `docs/analise-compatibilidade-monetaria`  
**Regra de segurança:** nenhuma alteração de schema, migração, dupla escrita ou corte de produção está autorizada por este documento.

## 1. Objetivo e resultado esperado

Migrar valores monetários de `REAL` para `INTEGER` em centavos, com parsing decimal exato, conciliação sem tolerância nos dados novos e rollback por chave de configuração, mantendo a compatibilidade do dashboard durante a transição. O plano preserva as colunas legadas até um descomissionamento aprovado em etapa separada.

A execução deve ocorrer em branch de implementação própria e PRs revisáveis. Esta PR é documental e não deve misturar mudança de regras operacionais com código da migração.

## 2. Bloqueios de desenho que precedem código

| ID | Decisão necessária | Proposta técnica para avaliação | Gate |
|---|---|---|---|
| G-01 | Regra de escala da entrada monetária | Minuta v1.1: valor final aceita casas excedentes apenas quando os dígitos após a 2ª casa são todos zero (`1.230` aceito; `1.231` rejeitado); grandezas de cálculo preservam escala contratada e arredondam *half-up* no resultado. Contrato deve classificar cada campo | Diretoria Financeira: assinatura formal da v1.1 ainda bloqueia mudança funcional |
| G-02 | Continuidade da escrita em REAL | Minuta v1.1 troca o termo para `REAL congelado`: caminho legado mantém semântica inalterada durante dupla escrita, corte e por pelo menos 90 dias corridos pós-corte, até descomissionamento formal; centavos e REAL participam da mesma transação SQLite | TI/Controladoria/Diretoria: assinar política/contrato; validar leitores e rollback com dados pós-corte |
| G-03 | Esquema por métrica e regras NULL/CHECK | Minuta do contrato define as oito colunas semânticas em `fatos`, três em `acordos_posicao`; CHECK de aplicabilidade por tipo e sinal; importador/diagnóstico exigem dados novos; triggers de obrigatoriedade só após backfill conciliado | Assinatura/aprovação formal precede criação de qualquer coluna/backfill |
| G-04 | Regra operacional de conversão suspeita do REAL legado menciona “fração mínima” sem limite formal | Definir a fórmula e o limite exato do diagnóstico, com exemplos reproduzíveis; manter esse diagnóstico separado das regras de aceitação de dados novos | TI + Controladoria |
| G-05 | Negativos em origem não comprovados para todos os campos listados e relação das promessas ainda não validada em dado real | Autorizar extração sanitizada e registrar evidência por campo/cenário; sem inferência a partir da amostra fictícia | TI + Controladoria |
| G-06 | Fórmulas ERP/Systêxtil não validadas | Obter ao menos 30 títulos reais sanitizados e reproduzir ao centavo antes de habilitar qualquer cálculo próprio de encargo | Contabilidade + TI |

**A ratificação da Política v1.1 foi declarada em 14/10/2026.** A integração de código pode avançar em PR isolada e sob feature flag. DDL, backfill, ativação de dupla escrita em produção e cutover continuam bloqueados até os respectivos gates técnicos (backup/restauração verificados, revisão, evidência de origem, conciliação e aprovações documentadas).

## 3. Fases, tarefas e critérios de saída

### Fase 0 — Governança e contrato

**Tarefas**
- Ratificar e assinar as decisões de negócio.
- Resolver G-01 a G-04 e versionar a Política de Precisão Monetária/contrato de dados.
- Fixar contrato de entrada: número JSON ou string decimal, sinal, escala, notação científica, nulo/ausente, separador decimal, limites de magnitude e tratamento de mais de duas casas.
- Fixar nome e tipo de cada nova coluna, nulabilidade, condições de `CHECK` e chave de reconciliação.

**Saída:** documentos versionados e aprovados; sem ambiguidades críticas de implementação.

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

**Tarefas**
- Implementar módulo comum de parsing/conversão, reutilizado por importador e auditoria; evitar dois parsers divergentes.
- Validar a grafia do token JSON antes de criar `Decimal`, usando `parse_int` e `parse_float` com uma gramática que rejeita `e/E` e `parse_constant` que rejeita `NaN`/`Infinity`. Rejeitar booleanos explicitamente; strings só são aceitas se o contrato as declarar permitidas para o campo.
- Para valores monetários finais, aceitar casas além de duas apenas quando os dígitos excedentes são zeros (`1.230` → 123 centavos); rejeitar (`1.231`) sem arredondamento. Em grandezas de cálculo com escala contratada, preservar decimal exato e aplicar *half-up* apenas no resultado final. Validar o payload inteiro antes da transação diária.
- Converter `Decimal` para centavos com aritmética decimal exata, limites de inteiro de 64 bits e política explícita para nulo versus zero.
- Centralizar a matriz de sinal por campo e tipo; emitir alerta visível de crédito/estorno para negativos permitidos.
- Implementar `real_para_centavos` apenas para histórico, via `Decimal(repr(valor))` e *half-up*, com relatório de suspeitas cujo algoritmo/limite já esteja formalizado. Não tratar o texto original como recuperável.

**Saída:** testes unitários verdes; importação e banco permanecem sem alteração.

### Fase 4 — Auditoria exata e semântica contábil

**Tarefas**
- Eliminar tolerância monetária de R$ 0,01 na auditoria nova; comparar inteiros em centavos com igualdade exata. Quantidades/contagens permanecem inteiras e exatas.
- Implementar checks separados para somas agregadas de origem versus usuários, identidade de acordos e identidade de promessas. Não somar `contatosUnicosTotal` entre usuários.
- Tratar `valorRecebidoPeriodo` como fluxo do período e `valorAVencer`/`valorVencido` como posição por captura: nunca somar snapshots de capturas diferentes como fluxo.
- Confirmar a regra das promessas e as exceções contábeis com payload real sanitizado, com foco em desconto, renegociação, cancelamento, pagamento parcial e pagamento informado sem baixa.
- Gerar relatório que distingue divergência de origem, falha de regra, conversão histórica suspeita e dado ausente.

**Saída:** todas as divergências de testes são explicáveis; regras contábeis foram comprovadas ou os casos pendentes permanecem explicitamente não bloqueantes.

### Fase 5 — Migração de esquema aditiva e backfill idempotente

**Pré-condições:** Fases 0–4 aceitas; backup verificado; revisão de código aprovada.

**Tarefas**
- Criar migração versionada e idempotente para as colunas semânticas aprovadas: `deposito_valor_centavos`, `acordo_valor_centavos`, `acordo_pago_centavos`, `acordo_pendente_centavos`, `promessa_prometido_centavos`, `promessa_cumprido_centavos`, `promessa_em_aberto_centavos`, `promessa_quebrado_centavos`, `recebido_periodo_centavos`, `a_vencer_centavos` e `vencido_centavos`. Não renomear, reescrever ou remover colunas legadas `REAL`.
- Preservar `NULL` quando significar “não informado”; não converter ausência para zero sem regra aprovada.
- Backfill do histórico a partir do REAL com `real_para_centavos`; marcar cada conversão suspeita e manter chave/valor original para auditoria.
- Adicionar CHECKs imediatos: cada métrica de `fatos` só pode ser não nula para o `tipo` aplicável; CHECKs de sinal permitem negativos apenas em `deposito_valor_centavos`, `acordo_pendente_centavos`, `promessa_em_aberto_centavos` e `recebido_periodo_centavos`. NULL é aceito durante backfill; para `fatos`, o estado final NULL significa não aplicável e zero significa zero real.
- Fazer `diagnosticar_banco.py` sensível à fase: NULL em métrica aplicável de linha histórica é pendência enquanto backfill estiver incompleto; métrica ausente em nova gravação após ativar dupla escrita é falha; depois do backfill conciliado, ausência em métrica aplicável deve falhar. Instalar triggers de obrigatoriedade somente após backfill e conciliação completos.
- Reexecutar a migração e comprovar que não duplica nem altera valores previamente migrados.

**Saída:** mesma contagem de registros e mesmas chaves; nenhuma alteração destrutiva; relatório de backfill integral e idempotência comprovada.

### Fase 6 — Dupla escrita transacional e conciliação técnica

**Tarefas**
- Modificar o escritor somente após assinatura/aprovação de G-02. Manter a gravação legada em REAL com semântica inalterada e gravar as colunas em centavos na **mesma transação**. A escrita em REAL continua durante a dupla escrita, no corte e por pelo menos 90 dias corridos pós-corte; só para com descomissionamento formal aprovado.
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
- Arquivar relatório diário e classificação assinada de cada divergência.

**Saída:** 10 dias úteis válidos, resultados documentados e 100% das divergências classificadas/corrigidas antes de habilitar bloqueio.

### Fase 8 — Corte de leitura e rollback

**Pré-condições obrigatórias**
- Política monetária v1.1 e contrato de dados formalmente assinados/ratificados.
- CI aprovado no head a integrar e testes específicos de parsing, schema, backfill, dupla escrita, diagnóstico e rollback verdes.
- Backup, manifesto e SHA-256 verificados; restauração em homologação ensaiada.
- Dez dias úteis consecutivos de conciliação válida; zero divergência inexplicada e 100% das divergências classificadas.
- Regras de sinais validadas com evidência de origem; regras contábeis e 30 títulos do ERP validados conforme aplicável.
- Inventário anexo lista os consumidores que ainda leem REAL e o gate/data planejada para cada um migrar leitura para centavos.
- Aprovação da Controladoria e assinatura final da Diretoria Financeira.

**Tarefas**
- Alternar leitura para centavos com chave/configuração reversível.
- Fazer smoke tests de dashboards, totais, filtros, exportações e auditoria.
- **Manter a escrita legada REAL ativa** durante e depois do corte; a chave de leitura não altera nem interrompe a gravação de compatibilidade.
- Monitorar alertas e comparativos após o corte; registrar responsável e procedimento de acionamento.
- Testar o rollback com dados criados/importados **depois do corte**: confirmar que as novas linhas foram escritas em REAL e INTEGER na mesma transação e que a reversão da leitura para REAL exibe esses mesmos dados.
- Em divergência inexplicada, falha de integridade ou decisão da Controladoria, reverter leitura às colunas legadas imediatamente; restaurar backup somente se necessário e conforme plano ensaiado.

**Saída:** corte registrado, escrita legada ainda ativa, métricas de saúde acompanhadas e rollback demonstrado com dados pós-corte.

### Fase 9 — Descomissionamento separado

A escrita legada em REAL permanece ativa durante os 90 dias corridos posteriores ao corte e continua ativa depois desse prazo enquanto a aprovação formal de descomissionamento não ocorrer. Somente iniciar após pelo menos 90 dias corridos de operação sem incidente, com aprovação própria da Controladoria. Anexar inventário de consumidores que ainda leem REAL e a data/gate em que cada um deixou de ler. Verificar retenção/auditoria antes de remover qualquer dependência; não remover colunas automaticamente pelo decurso do prazo.

## 4. Matriz mínima de testes

| Grupo | Casos obrigatórios | Resultado esperado |
|---|---|---|
| Parsing | JSON number/integer, string somente se contratada, nulo, ausente, booleano, texto inválido, vírgula decimal, `NaN`, infinito, token com `e/E` | Formatos previstos aceitos; formatos não contratuais rejeitados com erro controlado antes da transação |
| Escala de entrada | Valores finais `1.23`, `1.230`, `1.231` e entradas com 3/4/6 casas | `1.23` e `1.230` aceitos; qualquer dígito não zero além da 2ª casa (ex.: `1.231`) rejeita sem arredondamento; classes de cálculo seguem escala `_eN` contratada |
| Arredondamento interno | `0.005`, `0.004`, `-0.005`, `1.005`, `2.675`, `0.1 + 0.2`, `0.29`, `1e-7` | *Half-up* correto somente nos caminhos de cálculo/conversão onde ele é permitido; notação científica de entrada tratada conforme contrato |
| Sinal por campo | Negativo, positivo e zero para cada campo aprovado; negativo para todos os campos proibidos; contagens negativas | Regras aplicadas campo+tipo, alertas emitidos e entradas indevidas rejeitadas |
| Aritmética | Soma longa sem deriva; igualdade exata com diferença de 1 centavo; rateio de 10.000 centavos em 3.333 + 3.333 + 3.334 | Soma exata; divergência de 1 centavo identificada; rateio preserva total |
| Identidade contábil | Acordo pago total/parcial, pendente, crédito; promessa cumprida/em aberto/quebrada; cancelamento, desconto, renegociação e baixa pendente | Igualdades corretas ou exceção classificada; não contar pago antes de baixa |
| Histórico REAL | `1.005`, `2.675`, `0.1 + 0.2`, nulo, valor negativo autorizado, valor com representação longa | Conversão determinística *half-up* e suspeitas listadas sem reescrita silenciosa do histórico |
| Banco/transaction | Migração repetida, colunas já existentes, falha na gravação nova, falha na escrita legada, rollback, interrupção e retry | Migração idempotente; nenhuma transação parcial; registros/chaves preservados |
| Regras temporais | fluxo `recebido_periodo`, snapshots `a_vencer`/`vencido`, timestamp original, dia sem carga, contagem dos 10 dias úteis | Fluxo e posição não confundidos; timestamp preservado; janela de alerta segue calendário formal e dias sem carga não contam automaticamente |
| CHECK/obrigatoriedade faseada | NULL legado antes de backfill, zero, coluna não aplicável ao tipo, sinal, marker de fase, triggers pós-backfill | Linhas históricas incompletas não bloqueiam a migração aditiva; dados novos inválidos falham; após backfill conciliado, ausência em métrica aplicável falha |
| Rollback após corte | Importar um registro novo depois do corte, forçar mudança de chave de leitura, confirmar retorno a REAL | O registro pós-corte permanece visível ao voltar a REAL; a escrita legada não foi encerrada antes do descomissionamento |
| Integração | CLI do importador, auditoria, dashboard, relatórios, exportações, workflow CI | Compatibilidade comprovada por testes de regressão e CI verde |

## 5. Critérios de conciliação e aprovação

- **Dados novos:** igualdade exata em centavos; tolerância zero.
- **Legado REAL versus INTEGER:** 100% das diferenças classificadas como conversão histórica suspeita, com registro e valor identificados, ou erro corrigido. Nenhuma divergência inexplicada.
- **Janela:** dez dias úteis consecutivos de dupla escrita e conciliação diária, sob critério de calendário definido antes de iniciar.
- **Governança:** Controladoria aprova; Diretoria Financeira assina o corte.
- **Backup:** manifesto e SHA-256 conferidos e restauração ensaiada em homologação.
- **Retirada de REAL:** release separada após 90 dias corridos sem incidentes e aprovação própria.

## 6. Rollback

1. Acionar rollback diante de divergência inexplicada, falha de integridade ou decisão da Controladoria.
2. Reverter imediatamente a chave de leitura para as colunas legadas; confirmar smoke tests e registrar horário, responsável, motivo e alcance.
3. Se o banco estiver comprometido, restaurar backup verificado conforme exercício ensaiado; validar integridade, contagens, `user_version` e funcionamento.
4. Não apagar colunas novas nem remodelar schema durante resposta emergencial; preservar logs, relatórios e evidências para análise.

## 7. Evidências a anexar ao PR de implementação

- Decisões ratificadas e versão da política/contrato.
- Matriz completa de leitores e escritores, incluindo anexo por consumidor que informa dependência atual de REAL e data/gate planejado para mudar a leitura.
- Payload sanitizado e autorizado / resultados de 30 títulos mantidos fora do Git, mais relatório com hashes e resultados não sensíveis.
- Resultados de testes unitários/integrados e CI.
- Manifesto do backup, SHA-256 e relatório de restauração, mantendo artefatos sensíveis em armazenamento restrito.
- Relatórios diários dos dez dias úteis, divergências classificadas e aprovações.
- Procedimento e evidência de rollback em homologação.

## 8. Estado atual

As decisões de desenho dos três bloqueadores foram ratificadas pelo solicitante em 14/10/2026: nome semântico por métrica, `REAL congelado` com escrita legada mantida ao menos 90 dias pós-corte e até descomissionamento formal, e distinção entre valores finais e grandezas de cálculo. A integração de código segue em branch/PR controlada. Nenhum backfill, corte ou alteração de banco real será executado até a aprovação dos gates operacionais e a verificação de backup/restauração.

Este plano foi preparado a partir da análise documental e das decisões recebidas em 14/10/2026. O GitHub Actions `Testes CAIXA FUTURO` — execução [#42](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38581680436) no head documental `82c5e3284a3e1db61c55ed77123e245639b93b27` — concluiu com sucesso nos testes automatizados existentes e na validação da amostra sem CRM. Isso não valida uma migração que ainda não foi implementada: testes específicos de centavos/schema/dupla escrita/rollback permanecem pendentes. Não foram executados backup, migração, alteração de schema, dupla escrita, acesso ao CRM/ERP ou corte de produção nesta etapa.


### Bloqueadores rastreados no GitHub

- [Issue #3 — Ratificar regra de entrada com mais de 2 casas](https://github.com/IsaacTexCotton/Dashboard/issues/3)
- [Issue #4 — Definir contrato de dupla escrita REAL/INTEGER](https://github.com/IsaacTexCotton/Dashboard/issues/4)
- [Issue #5 — Definir colunas INTEGER específicas por métrica](https://github.com/IsaacTexCotton/Dashboard/issues/5)

Os três itens precisam ser decididos e fechados com evidência/aprovação antes da PR funcional de migração.

## 9. Inventário de testes/CI confirmado

A árvore de `main` inspecionada em 14/10/2026 lista seis módulos de teste e 65 métodos `test_*`:

| Arquivo | Número de testes | Implicação para o plano |
|---|---:|---|
| `tests/test_importar.py` | 28 | Aproveitar as regressões existentes de timestamp, transação, reimportação/idempotência, dry-run e validação; rever expectativas de sinal |
| `tests/test_auditar_resposta.py` | 12 | Atualizar `test_respeita_tolerancia_de_centavo`: tolerância de R$ 0,01 não está conforme a política de igualdade exata para os novos centavos |
| `tests/test_validar_integracao_local.py` | 3 | Preservar o fluxo local com amostra sem CRM, adicionando fixtures para as novas semânticas quando aprovadas |
| `tests/test_backup_recuperacao.py` | 2 | Cobertura automatizada em DB temporário; não substitui restauração operacional em homologação |
| `tests/test_backup_sqlite.py` | 12 | Reutilizar testes de manifesto, hash, corrupção e preservação de registros |
| `tests/test_diagnosticar_banco.py` | 8 | Preservar garantias de diagnóstico read-only/não destrutivo |

Workflow `.github/workflows/testes.yml`: Python 3.11, `unittest discover`, dry-run de importação da amostra, auditoria da amostra e validação de integração local. A última execução confirmada antes desta edição é [#42](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38581680436), `success`, no head documental `82c5e3284a3e1db61c55ed77123e245639b93b27`; uma nova execução precisa confirmar o head desta atualização.

**Atenção:** os testes atuais de auditoria/importação codificam as regras antigas (aceitar diferença de um centavo em contexto de auditoria e rejeitar todo negativo). Devem ser revisados de acordo com as decisões ratificadas. Não há evidência de testes de centavos, backfill, dupla escrita, constraints do schema monetário ou rollback de leitura; esses testes precisam existir antes do corte. A amostra é fictícia e os testes automatizados de backup usam bancos temporários; nenhum dos dois comprova segurança operacional em banco real.

A árvore também contém `caixa-futuro-fase1.zip`, cujo conteúdo não foi inspecionado. Fechar o inventário de consumidores exige verificar esse artefato ou documentar formalmente que ele está fora do escopo operacional.
