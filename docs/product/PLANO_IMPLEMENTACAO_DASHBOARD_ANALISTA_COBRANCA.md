# Plano de implementação — Dashboard orientado à decisão do analista de cobrança

**Projeto:** CAIXA FUTURO — Contas a Receber / Cobrança  
**Data-base:** 15/10/2026  
**Estado:** plano de produto e engenharia proposto; execução funcional depende das decisões e evidências indicadas abaixo.  
**Escopo desta etapa:** plano de implementação. Não habilita operações em produção, acesso ao CRM/ERP, migração monetária, backfill ou alteração do banco operacional.

## 1. Objetivo de produto

Transformar o CAIXA FUTURO de um painel que principalmente consolida totais em uma ferramenta que ajuda o analista a responder, no início do dia e durante o expediente:

1. Quanto foi recebido e movimentado no período, e como isso evoluiu?
2. Qual é a posição da carteira a vencer e vencida na última captura disponível?
3. Quais resultados mudaram, onde estão as exceções e que investigação deve vir primeiro?
4. Quais ações de cobrança precisam ser executadas agora — quando a origem fornecer dados individualizados suficientes para sustentar essa recomendação?

O critério de sucesso não é quantidade de gráficos. É reduzir o tempo para entender o resultado, encontrar desvios e chegar ao próximo trabalho concreto, sem misturar métricas, esconder falta de dados ou sugerir ações sem evidência.

## 2. Estado atual verificado e limitações

### O que já existe

- `web-demo/index.html`: demonstração estática e autônoma, com dados fictícios versionados, filtros de data, indicadores de depósitos/acordos/promessas/contatos, uma posição de acordos, barra por negociador e resumo por usuário. A amostra disponível representa uma única data, portanto não prova tendências históricas.
- `dashboard_app.py`: prévia local com API de leitura, filtros de período, resumo agregado, movimento diário, tabela por usuário e snapshot mais recente dentro do período. Pode abrir um banco existente em modo somente leitura ou operar em SQLite em memória com dados sintéticos.
- `importar.py`, `auditar_resposta.py` e `diagnosticar_banco.py`: importação validada por dia, conciliação de totais e diagnóstico de banco.
- `modelo_monetario.py`, `precisao_monetaria.py`, `escrita_dupla.py`, `migrar_schema_monetario.py` e `backfill_monetario.py`: base técnica para precisão monetária e transição gradual, coberta por testes sintéticos.
- CI executa a suíte automatizada e valida a amostra fictícia sem CRM. Isso comprova os cenários automatizados, não homologa o sistema com todos os dados reais.

### Limites de dados relevantes ao produto

O esquema de fatos descrito no contrato é agregado por data, usuário e tipo. O snapshot de acordos é uma posição capturada em determinado instante. A estrutura atual não equivale a uma fila de títulos/clientes com vencimento individual, saldo atualizado, identificador de acordo, histórico de contato e próxima ação.

Por isso, o primeiro incremento deve melhorar a leitura e a confiança das métricas agregadas existentes. Uma fila operacional caso a caso depende de confirmar quais campos individualizados estão disponíveis na origem e de formalizar seu contrato antes de alterar schema ou importador.

### Verificação obrigatória de consistência entre código e documentação

O código atual de `dashboard_app.py` contém um modo de leitura por centavos, com validações de fase e conciliação, além do modo legado de leitura. A demonstração estática do GitHub Pages, por sua vez, é exclusivamente sintética e não lê banco. Alguns documentos de migração registram que o leitor por centavos ainda não existe. Antes de implementar novas mudanças, reconciliar essa diferença documental com o código e os testes vigentes; não alterar flags de ambiente como parte dessa correção documental.

## 3. Princípios de desenho

- **Começar por decisões do analista:** cada indicador precisa responder a uma pergunta de trabalho e, idealmente, indicar como investigar o resultado.
- **Definição explícita:** nome, fórmula, unidade, fonte, granularidade, sinal, período e limitações de cada KPI registrados em um catálogo de métricas.
- **Fluxo separado de posição:** depósitos e outras movimentações por período não devem ser misturados à posição a vencer/vencida. Snapshots de instantes diferentes nunca são somados como fluxo.
- **Recência visível:** apresentar data/hora da última importação confirmada e timestamp da captura utilizada, quando esses dados estiverem disponíveis e validados.
- **Zero diferente de indisponível:** distinguir zero real, ausência de dados, campo não aplicável, falha de carga e indicador ainda não disponível.
- **Comparações justas:** evitar ranking de produtividade baseado só em valores absolutos sem considerar carteira atribuída, volume de entrada, período e semântica confirmada.
- **Sem inferência de dados:** não fabricar metas, aging, conversão, saldo por cliente ou prioridades sem as fontes e regras necessárias.
- **Privacidade e segurança por padrão:** usar fixtures sintéticas; banco existente em modo somente leitura; nenhum dado de cliente, payload real, segredo, backup ou caminho interno no Git.
- **Entrega em etapas revisáveis:** PRs pequenas, testes automatizados e CI verde antes da integração; nenhuma alteração destrutiva para melhorar a demonstração.

## 4. Escopo dividido por incrementos

## Incremento 0 — Baseline funcional e contrato de métricas

**Objetivo:** impedir que o redesign se apoie em números ambíguos.

### Trabalho

1. Comparar o comportamento real de `dashboard_app.py`, `web-demo/index.html`, README, contrato financeiro, plano monetário e testes.
2. Resolver a inconsistência documental sobre a existência do leitor local por centavos, deixando explícita a diferença entre:
   - prévia local com banco existente somente leitura;
   - prévia local sintética em SQLite na memória;
   - demonstração estática publicada com dados fictícios.
3. Criar um catálogo de indicadores com: nome exibido, pergunta respondida, fórmula, unidade, origem, período/granularidade, semântica de fluxo ou posição, regras de ausência/zero, filtros válidos e validação pendente.
4. Validar com Cobrança/Financeiro a semântica de depósitos, valor de face de acordos, pagos, pendentes, promessas, cumpridas/quebradas, contatos e posição da carteira.
5. Marcar explicitamente indicadores bloqueados por ausência de fonte ou regra de negócio.

### Critérios de aceite

- Nenhum KPI tem fórmula implícita ou duas interpretações conhecidas.
- Fluxo e snapshot estão separados.
- Contatos únicos por usuário não são apresentados como clientes únicos globais deduplicados.
- A documentação não contradiz o modo de leitura implementado.
- Nenhuma flag ou banco operacional é alterado.

## Incremento 1 — Cockpit diário de cobrança com dados atuais

**Objetivo:** fazer o analista compreender a situação em poucos segundos sem exigir dados individualizados novos.

### Experiência proposta

1. Cabeçalho com período, fonte/modo de leitura, última importação conhecida e timestamp do snapshot; se a recência não puder ser confirmada, mostrar “não disponível”, não inferir.
2. Cartões de movimento por período:
   - depósitos registrados e valor;
   - acordos: valor de face, pagos e pendentes;
   - promessas: valor prometido, cumprido, em aberto e quebrado;
   - contatos: registros e a contagem atualmente definida de únicos por usuário, com aviso de que não é uma deduplicação global.
3. Bloco distinto de posição da carteira na captura mais recente do período:
   - recebido no período, conforme semântica da origem;
   - a vencer;
   - vencido;
   - instante/data da captura.
4. Tendência diária de depósitos, acordos e promessas para períodos com múltiplos dias disponíveis.
5. Resumo por usuário com ordenação selecionável e explicação da métrica de ordenação; sem rotular resultado absoluto como “melhor desempenho”.
6. Estados explícitos de carregamento, erro, período inválido, período sem dados, snapshot ausente e dados incompletos.
7. Filtros de data inclusivos e consistentes entre todos os componentes; opção clara de período anterior equivalente somente quando houver histórico suficiente.

### Critérios de aceite

- Todas as visualizações respeitam o mesmo período e não mantêm valores antigos após erro ou filtro inválido.
- Período sem dados mostra estado vazio e zero apenas onde zero for semântica correta.
- A captura de posição mais recente é identificada e não somada a outras capturas.
- Valores monetários mantêm precisão de centavos na serialização e apresentação.
- Os indicadores sintéticos são rotulados como demonstração; não sugerem conexão com CRM.
- Testes cobrem períodos, snapshot ausente, arredondamento/apresentação, erro de leitura e equivalência entre os modos monetários quando aplicável.

## Incremento 2 — Comparação e explicação de variações

**Objetivo:** responder “o que mudou?” e permitir investigação sem alegar causalidade não comprovada.

### Trabalho

1. Comparar período selecionado com período anterior de duração equivalente, quando os dados permitirem.
2. Exibir valor atual, valor anterior, variação absoluta e percentual; percentual fica “não calculável” quando o denominador for zero/indisponível.
3. Separar mudanças de fluxo das mudanças de posição da carteira; snapshots são comparados como capturas, não acumulados.
4. Exibir séries diárias e detalhamento por usuário com a mesma base e as mesmas datas.
5. Introduzir alertas descritivos somente para regras acordadas (por exemplo, queda relativa acima de limite configurável), com indicação da fórmula e da cobertura de dados.
6. Mostrar qualidade e cobertura dos dados ao lado das conclusões: dias carregados, dias esperados quando houver calendário confiável, lacunas de importação e timestamp disponível.

### Critérios de aceite

- Comparações são reprodutíveis e testadas com bases sintéticas, inclusive denominador zero e dias faltantes.
- Alertas dizem “variação observada”, não atribuem causa sem evidência.
- Métricas não comparáveis ou sem cobertura suficiente são ocultadas ou explicitamente classificadas como indisponíveis.
- Nenhum “atingimento de meta” aparece sem meta oficial com período e proprietário definidos.

## Incremento 3 — Painel de desempenho de carteira e negociadores

**Objetivo:** avaliar desempenho sem incentivar comportamento errado ou comparações injustas.

### Pré-condições

Definir com gestão de Cobrança as métricas e seus denominadores, além de identificar carteira atribuída e volume de entrada. Os fatos agregados atuais, por si só, não permitem deduzir conversão individual de contato em pagamento ou atribuir causalmente recebimentos a um contato.

### Trabalho condicionado à validação

- Mostrar resultados absolutos por usuário (já suportados em parte) e permitir segmentar por período.
- Adicionar métricas normalizadas somente após validar denominadores e regras de atribuição, por exemplo, taxa de cumprimento de promessas ou recuperação sobre base elegível.
- Tratar carteira, faixa de atraso, tipo de cliente e volume de casos como variáveis de contexto se a origem fornecer esses campos.
- Evitar ranking simplista antes de validar diferenças de carteira e cobertura.
- Documentar limites de interpretação de cada indicador.

### Critérios de aceite

- Fórmula, denominador, janela de observação e origem de cada razão são revisados por Cobrança/Financeiro.
- Testes cobrem divisão por zero, amostras incompletas e mudança de responsável/carteira.
- Indicadores de conversão não são calculados a partir de totais sem relação identificável entre os eventos.

## Incremento 4 — Central de ação: lista de casos prioritários

**Objetivo:** permitir que o analista saia do agregado para o caso que deve tratar.

**Este incremento depende de descoberta da origem. Não assumir que os campos existem no payload atual.**

### Campos a confirmar com o responsável pela fonte

- identificador estável de cliente, título e/ou acordo;
- valor original e saldo atualizado;
- data de vencimento e dias de atraso;
- status financeiro e status de cobrança;
- promessas e acordos associados ao caso, datas de compromisso e resultado;
- último contato, próxima ação e responsável/carteira;
- regras de elegibilidade, exclusões, sigilo e permissão de acesso.

### Trabalho após confirmação

1. Versionar um contrato de dados individualizado e mapear fonte → normalização → persistência.
2. Definir como tratar alterações de identificador, duplicidades, acordos renegociados e histórico.
3. Desenhar uma lista ordenável/filtrável, com critérios visíveis (por exemplo, dias vencidos, valor elegível e compromisso vencido).
4. Permitir abrir o detalhe de um caso e mostrar a evidência por trás da prioridade.
5. Exportar somente os campos aprovados, com controle de acesso adequado ao ambiente real.
6. Manter a primeira versão como apoio à decisão; não iniciar comunicação ou cobrança automática sem um projeto separado, autorização e controles próprios.

### Critérios de aceite

- Cada caso é rastreável à fonte e tem chave estável validada.
- Toda prioridade tem regra explicável, testada e revisada pelo setor.
- A soma do detalhe reconcilia com os agregados correspondentes conforme contrato.
- Testes verificam autorização, exposição mínima de dados, duplicidade e atualizações de status.
- Se a origem não tiver granularidade suficiente, o incremento fica bloqueado; não se cria uma fila fictícia a partir de totais agregados.

## Incremento 5 — Piloto operacional, adoção e melhoria contínua

**Objetivo:** medir se o painel melhora o trabalho real antes de ampliar escopo.

### Plano

1. Validar indicadores com exemplos sintéticos e, somente por processo corporativo autorizado, com amostra sanitizada mantida fora do Git.
2. Fazer revisão guiada com 2–3 analistas e um responsável de Cobrança/Financeiro, usando tarefas reais de análise sem efetuar cobranças ou escritas pelo painel.
3. Registrar problemas de interpretação, cliques necessários, filtros mais usados, falsos alertas e indicadores sem ação clara.
4. Corrigir as fricções de maior impacto e repetir o roteiro.
5. Definir treinamento curto, responsável pelo catálogo de métricas e processo de reportar divergências.
6. Só propor integração operacional após os gates técnicos, de acesso e de dados pertinentes estarem satisfeitos.

### Métricas de sucesso do produto

Metas numéricas devem ser combinadas com a equipe depois de medir o baseline; não devem ser inventadas na implementação. Medir:

- tempo para responder perguntas padrão da reunião diária;
- tempo para localizar e explicar uma variação relevante;
- percentual de indicadores compreendidos sem ajuda;
- número de divergências entre painel e relatório de referência;
- percentual de períodos com recência/cobertura explícita;
- utilidade percebida e ações concretas derivadas pelo analista.

## 5. Catálogo inicial de indicadores

| Indicador | Disponível com os dados descritos hoje? | Regra/limite |
|---|---|---|
| Depósitos por período | Sim, agregado | Não assumir equivalência com todo o caixa recebido sem validar a semântica da origem |
| Valor de face, pago e pendente de acordos | Sim, agregado | A relação `valor = pagos + pendente` exige validação de exceções contábeis antes de ser bloqueante |
| Prometido, cumprido, em aberto e quebrado | Sim, agregado | Definir precisamente status, janela e valores antes de criar taxa de cumprimento |
| Registros de contatos e únicos por usuário | Parcial | Únicos não devem ser somados como total global deduplicado |
| Recebido no período | Sim, no snapshot disponível | Manter separado do estoque da carteira e registrar captura/fonte |
| A vencer e vencido | Sim, como posição de snapshot | Não substitui aging por faixa nem lista de títulos; snapshots de datas distintas não são somáveis |
| Tendência diária | Sim, se houver fatos em múltiplas datas | Ausência de carga não pode ser tratada automaticamente como zero movimento |
| Variação versus período anterior | Condicional | Exige histórico e cobertura comparável; percentual indisponível com denominador zero |
| Meta e atingimento | Não confirmada | Exige meta oficial, período, escopo e responsável |
| Aging (1–7, 8–30, 31–60, 60+ dias) | Não com o agregado atual | Requer vencimento e saldo por título/caso |
| Taxa de conversão contato → promessa → pagamento | Não comprovada | Requer eventos relacionados por identificadores, datas e janela atribuível |
| Lista de clientes/títulos prioritários | Não comprovada | Requer detalhe individualizado, status, vencimento/saldo e regras autorizadas |
| Previsão de recebimento | Fora do MVP | Só considerar após histórico validado, definição estatística e avaliação do risco de uso |

## 6. Sequência de PRs sugerida

Fazer uma entrega revisável por etapa, sem misturar redesign, schema e operações de migração na mesma PR.

1. **PR A — Baseline e catálogo:** corrigir inconsistências documentais de escopo/modos de leitura e registrar definições, limites e critérios de aceite.
2. **PR B — Recência e estados de dados:** adicionar metadados de última importação/captura quando verificáveis e cobrir estados vazio, incompleto e erro.
3. **PR C — Cockpit diário:** reorganizar hierarquia visual, nomes e agrupamento de fluxo versus posição; preservar filtros e acessibilidade.
4. **PR D — Comparação temporal:** período equivalente, deltas e tendências com teste de lacunas/denominador zero.
5. **PR E — Desempenho de carteira:** somente após aprovação das fórmulas, denominadores e atribuição.
6. **PR F — Contrato individualizado:** descoberta da origem e decisão sobre campos/chaves, antes de schema ou importador novos.
7. **PR G — Central de ação:** implementar a fila e o detalhe de caso somente quando o contrato e o acesso tiverem sido aprovados.
8. **PR H — Piloto e estabilização:** testes de regressão, roteiro de aceitação, feedback de usuários e métricas de sucesso do produto.

Cada PR precisa ter descrição funcional, screenshots ou roteiro de validação da interface quando aplicável, testes específicos, CI verde e declaração explícita de que fixtures são sintéticas ou evidências externas foram obtidas por processo autorizado. Não integrar PR com falha nos checks.

## 7. Gates e dependências que não podem ser ignorados

- Não ativar `DUPLA_ESCRITA` ou `LEITURA_CENTAVOS` em produção como parte da implementação da interface.
- Não executar migração, backfill, importação real ou DDL em banco operacional nesta trilha de produto.
- Manter a reconciliação 17-versus-18 em aberto até demonstrar se os números vêm do mesmo payload e critério.
- Manter a Issue #17 como gate para inventário externo, runbook e restauração operacional.
- Validar sinais, regras de acordo e cálculos com origem autorizada antes de transformar as regras em alertas bloqueantes.
- Confirmar proteção da branch e CI obrigatório antes do merge.
- A demonstração estática publicada é um protótipo visual sintético, não uma fonte de dados nem uma prova de prontidão operacional.
- Não remover funcionalidades existentes sem evidência de que podem ser substituídas sem regressão.

## 8. Decisão de escopo para o primeiro incremento

O primeiro incremento funcional recomendado é **Cockpit diário + recência/qualidade de dados + comparação simples quando houver cobertura**. Essa entrega usa as agregações existentes, melhora imediatamente a leitura do analista e não precisa fingir que possui uma lista de títulos.

A central de ação deve vir depois do mapeamento da origem individualizada. Essa separação evita construir uma interface de prioridade visualmente convincente, porém baseada em dados que o sistema não tem.

## 9. Definição de pronto para o MVP

O MVP do cockpit é considerado pronto quando:

- [ ] Catálogo de métricas revisado por Cobrança/Financeiro.
- [ ] Fluxo e posição estão visualmente e semanticamente separados.
- [ ] Período, cobertura, última importação e timestamp do snapshot são claros quando conhecidos.
- [ ] Períodos vazios, incompletos, inválidos ou com erro não apresentam métricas antigas como se fossem atuais.
- [ ] Comparação temporal só é mostrada quando há base comparável.
- [ ] Valores monetários e variações passam os testes de precisão.
- [ ] Estado sintético fica evidente na demonstração pública.
- [ ] Testes de lógica/API e de interface passam; CI verde no commit candidato.
- [ ] Usuários-alvo completam tarefas de avaliação e o feedback está registrado.
- [ ] Nenhum gate de produção foi contornado para demonstrar a interface.

**Resultado esperado:** uma interface que ajude o analista a entender o dia, perceber desvios relevantes e saber o próximo passo disponível — sem atribuir significado não validado aos dados. A evolução para cobrança por caso depende de dados individualizados e regras aprovadas, não apenas de um redesign.
