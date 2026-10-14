# Análise de compatibilidade monetária — CAIXA FUTURO

**Status:** análise documental inicial; migração não autorizada nem executada  
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

## 9. Pendências humanas

- [ ] Confirmar formato decimal oficial da origem, precisão e arredondamento.
- [ ] Aprovar sinal por campo e semântica de estornos, créditos, abatimentos e excesso de pagamento.
- [ ] Definir relação contábil entre valor, pagos, pendente, prometido, cumprido, emAberto e quebrado; distinguir pagamento confirmado de informado/pendente de baixa.
- [ ] Resolver formalmente legado somente leitura versus dupla escrita.
- [ ] Aprovar nomes/modelo de novas colunas.
- [ ] Aprovar estratégia de conversão REAL legado e seus limites.
- [ ] TI/Contabilidade confirmar half-up do ERP para cálculos próprios.
- [ ] Definir janela de conciliação, aprovação das divergências e corte.
- [ ] Aprovar plano de rollback e corte definitivo.

## 10. Estado desta entrega

- [x] Política, contrato, runbook, importar.py e auditar_resposta.py consultados remotamente.
- [x] Branch de documentação criada.
- [ ] Inventário de todos os consumidores, testes e workflow CI: pendente.
- [ ] Testes automatizados executados nesta sessão: pendente.
- [ ] Banco/backup verificado: não executado, fora do escopo.
- [ ] Migração, alteração de schema e corte: não executados.
- [ ] Aprovação da Controladoria: pendente.

Este documento não autoriza migração nem certifica compatibilidade completa.
