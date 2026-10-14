# Plano de execução — Migração monetária para centavos inteiros

**Projeto:** Dashboard de Cobrança (CAIXA FUTURO), Contas a Pagar / Financeiro  
**Data:** 14/10/2026  
**Estado:** plano proposto; dependente de ratificação/assinatura e de gates técnicos.  
**Branch de documentação:** `docs/analise-compatibilidade-monetaria`  
**Regra de segurança:** nenhuma alteração de schema, migração, dupla escrita ou corte de produção está autorizada por este documento.

## 1. Objetivo e resultado esperado

Migrar valores monetários de `REAL` para `INTEGER` em centavos, com parsing decimal exato, conciliação sem tolerância nos dados novos e rollback por chave de configuração, mantendo a compatibilidade do dashboard durante a transição. O plano preserva as colunas legadas até um descomissionamento aprovado em etapa separada.

A execução deve ocorrer em branch de implementação própria e PRs revisáveis. Esta PR é documental e não deve misturar mudança de regras operacionais com código da migração.

## 2. Bloqueios de desenho que precedem código

| ID | Decisão necessária | Proposta técnica para avaliação | Gate |
|---|---|---|---|
| G-01 | Política v1.0 §4 permite entrada com mais de duas casas e arredondamento final; a decisão complementar manda bloquear valor monetário final com mais de duas casas | Ratificar a regra estrita para valores finais importados e publicar revisão/versionamento da política; diferenciar isso de cálculos internos que mantêm precisão e arredondam só no resultado | Diretoria Financeira |
| G-02 | “REAL somente leitura” versus continuidade da escrita legado já existente | Redigir como “não introduzir/alterar uma nova via de escrita em REAL; manter temporariamente o caminho legado existente para compatibilidade; gravar centavos em paralelo na mesma transação”. Isso implica que REAL não é literalmente somente leitura até o corte | Diretoria + TI |
| G-03 | Modelo com coluna específica por métrica versus nome = coluna legada + `_centavos`; `fatos.valor` é polimórfica por `tipo` | Aprovar um mapa explícito de colunas semânticas antes da migração. Candidatos: `deposito_valor_centavos`, `acordo_valor_centavos`, `acordo_pago_centavos`, `acordo_pendente_centavos`, `promessa_prometido_centavos`, `promessa_cumprido_centavos`, `promessa_em_aberto_centavos`, `promessa_quebrado_centavos`; posição: `recebido_periodo_centavos`, `a_vencer_centavos`, `vencido_centavos`. A proposta foge do sufixo puro em `fatos.valor`, por isso exige ratificação do contrato de schema | Diretoria Financeira + TI |
| G-04 | Regra operacional de conversão suspeita do REAL legado menciona “fração mínima” sem limite formal | Definir a fórmula e o limite exato do diagnóstico, com exemplos reproduzíveis; manter esse diagnóstico separado das regras de aceitação de dados novos | TI + Controladoria |
| G-05 | Negativos em origem não comprovados para todos os campos listados e relação das promessas ainda não validada em dado real | Autorizar extração sanitizada e registrar evidência por campo/cenário; sem inferência a partir da amostra fictícia | TI + Controladoria |
| G-06 | Fórmulas ERP/Systêxtil não validadas | Obter ao menos 30 títulos reais sanitizados e reproduzir ao centavo antes de habilitar qualquer cálculo próprio de encargo | Contabilidade + TI |

**Nenhum código de migração deve começar enquanto G-01 a G-04 não tiverem resolução registrada.** Trabalho de inventário e preparação de testes isolados pode avançar sem alterar a produção.

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
- Usar `parse_float` com validação do token bruto antes de criar `Decimal`, rejeitando `e/E` se a notação científica for proibida. Validar strings decimais separadamente; rejeitar booleanos, NaN, infinito e texto inválido.
- Aplicar a regra de escala ratificada a valores monetários finais. Bloquear registro inválido de modo controlado, sem arredondamento silencioso. Reservar *half-up* para os cálculos internos/legados que o contrato autorizar.
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
- Criar migração versionada e idempotente, que somente adiciona colunas aprovadas `INTEGER`; não renomear, reescrever ou remover colunas legadas `REAL`.
- Preservar `NULL` quando significar “não informado”; não converter ausência para zero sem regra aprovada.
- Backfill do histórico a partir do REAL com `real_para_centavos`; marcar cada conversão suspeita e manter chave/valor original para auditoria.
- Adicionar `CHECK` de sinal conforme o modelo final; se sinal depende de `tipo`, explicitar a condição em vez de usar validação genérica.
- Reexecutar a migração e comprovar que não duplica nem altera valores previamente migrados.

**Saída:** mesma contagem de registros e mesmas chaves; nenhuma alteração destrutiva; relatório de backfill integral e idempotência comprovada.

### Fase 6 — Dupla escrita transacional e conciliação técnica

**Tarefas**
- Modificar o escritor somente após decisão formal de G-02. Gravar colunas legadas pelo caminho compatível aprovado e novas colunas em centavos dentro da **mesma transação**.
- Calcular as colunas novas diretamente a partir do Decimal validado, não convertendo REAL de volta a centavos para dados novos.
- Não usar REAL em cálculos, filtros monetários ou comparações no fluxo novo; se a compatibilidade exigir valor REAL, confinar o cast ao adaptador legado e documentá-lo.
- Forçar falhas de cada escrita e provar rollback integral da transação; testar retry/idempotência e reprocessamento de um dia.
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
- CI aprovado e testes automatizados verdes.
- Backup, manifesto e hash verificados; restauração em homologação ensaiada.
- 10 dias úteis concluídos; zero divergência inexplicada nos novos centavos.
- Regras de sinais, parser, identidades contábeis e 30 títulos do ERP validados conforme aplicável.
- Aprovação da Controladoria e assinatura final da Diretoria Financeira.

**Tarefas**
- Alternar leitura para centavos com chave/configuração reversível.
- Fazer smoke tests de dashboards, totais, filtros, exportações e auditoria.
- Monitorar alertas e comparativos após corte; registrar responsável e procedimento de acionamento.
- Em divergência inexplicada, falha de integridade ou decisão da Controladoria, reverter leitura às colunas legadas imediatamente; restaurar backup somente se necessário e conforme plano ensaiado.

**Saída:** corte registrado, métricas de saúde acompanhadas e rollback disponível/testado.

### Fase 9 — Descomissionamento separado

Só iniciar depois de 90 dias corridos de operação sem incidente após o corte, com aprovação própria da Controladoria. Verificar todos os consumidores e retenção/auditoria antes de remover qualquer dependência de REAL. Nenhuma remoção ou renomeação faz parte das fases anteriores.

## 4. Matriz mínima de testes

| Grupo | Casos obrigatórios | Resultado esperado |
|---|---|---|
| Parsing | JSON number, string decimal, inteiro, nulo, ausente, booleano, texto inválido, vírgula decimal, `NaN`, infinito e token com `e/E` | Formatos previstos aceitos; formato não contratual rejeitado com erro controlado |
| Escala de entrada | Valores finais com 0, 1, 2, 3, 4 e 6 casas, incluindo zeros finais como `1.230` | De acordo com a regra formal ratificada; não arredondar silenciosamente valor final com escala inválida |
| Arredondamento interno | `0.005`, `0.004`, `-0.005`, `1.005`, `2.675`, `0.1 + 0.2`, `0.29`, `1e-7` | *Half-up* correto somente nos caminhos de cálculo/conversão onde ele é permitido; notação científica de entrada tratada conforme contrato |
| Sinal por campo | Negativo, positivo e zero para cada campo aprovado; negativo para todos os campos proibidos; contagens negativas | Regras aplicadas campo+tipo, alertas emitidos e entradas indevidas rejeitadas |
| Aritmética | Soma longa sem deriva; igualdade exata com diferença de 1 centavo; rateio de 10.000 centavos em 3.333 + 3.333 + 3.334 | Soma exata; divergência de 1 centavo identificada; rateio preserva total |
| Identidade contábil | Acordo pago total/parcial, pendente, crédito; promessa cumprida/em aberto/quebrada; cancelamento, desconto, renegociação e baixa pendente | Igualdades corretas ou exceção classificada; não contar pago antes de baixa |
| Histórico REAL | `1.005`, `2.675`, `0.1 + 0.2`, nulo, valor negativo autorizado, valor com representação longa | Conversão determinística *half-up* e suspeitas listadas sem reescrita silenciosa do histórico |
| Banco/transaction | Migração repetida, colunas já existentes, falha na gravação nova, falha na escrita legada, rollback, interrupção e retry | Migração idempotente; nenhuma transação parcial; registros/chaves preservados |
| Regras temporais | fluxo `recebido_periodo`, snapshots `a_vencer`/`vencido`, timestamp original, dia sem carga | Fluxo e posição não confundidos; timestamp preservado; janela de alerta segue calendário formal |
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
- Matriz completa de leitores e escritores.
- Payload sanitizado e autorizado / resultados de 30 títulos mantidos fora do Git, mais relatório com hashes e resultados não sensíveis.
- Resultados de testes unitários/integrados e CI.
- Manifesto do backup, SHA-256 e relatório de restauração, mantendo artefatos sensíveis em armazenamento restrito.
- Relatórios diários dos dez dias úteis, divergências classificadas e aprovações.
- Procedimento e evidência de rollback em homologação.

## 8. Estado atual

Este plano foi preparado a partir da análise documental e das decisões recebidas em 14/10/2026. O GitHub Actions `Testes CAIXA FUTURO` — execução [#38](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38568801738) no head documental `a113a97401d067330944373dcaf3bd6933c4b428` — concluiu com sucesso nos testes automatizados existentes e na validação da amostra sem CRM. Isso não valida uma migração que ainda não foi implementada: testes específicos de centavos/schema/dupla escrita/rollback permanecem pendentes. Não foram executados backup, migração, alteração de schema, dupla escrita, acesso ao CRM/ERP ou corte de produção nesta etapa.


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

Workflow `.github/workflows/testes.yml`: Python 3.11, `unittest discover`, dry-run de importação da amostra, auditoria da amostra e validação de integração local. A última execução confirmada é [#38](https://github.com/IsaacTexCotton/Dashboard/actions/runs/38568801738), `success`, no commit documental `a113a97401d067330944373dcaf3bd6933c4b428`; uma execução nova precisa confirmar o head desta atualização.

**Atenção:** os testes atuais de auditoria/importação codificam as regras antigas (aceitar diferença de um centavo em contexto de auditoria e rejeitar todo negativo). Devem ser revisados de acordo com as decisões ratificadas. Não há evidência de testes de centavos, backfill, dupla escrita, constraints do schema monetário ou rollback de leitura; esses testes precisam existir antes do corte. A amostra é fictícia e os testes automatizados de backup usam bancos temporários; nenhum dos dois comprova segurança operacional em banco real.

A árvore também contém `caixa-futuro-fase1.zip`, cujo conteúdo não foi inspecionado. Fechar o inventário de consumidores exige verificar esse artefato ou documentar formalmente que ele está fora do escopo operacional.
