# Política de Precisão Monetária — Dashboard de Cobrança (Contas a Pagar / Financeiro)

**Status:** v1.1 ratificada pelo solicitante em 14/10/2026; registro de aprovação formal documentado abaixo.
**Versão proposta:** 1.1 — 14/10/2026
**Aprovação registrada:** o solicitante declarou formalmente assinar a Política v1.1 e as aprovações da Controladoria em 14/10/2026.
**Escopo:** Todo valor monetário calculado, armazenado, importado, exibido ou exportado pelo aplicativo de dashboard do **setor de Cobrança**, dentro da área de Contas a Pagar e Financeiro (títulos vencidos, juros, multa, descontos, boletos, pagamentos, negativação e cartório).
**Moeda base:** BRL (Real). Moedas estrangeiras seguem a seção 8.

---

## Registro de aprovação formal — 14/10/2026

O solicitante declarou explicitamente nesta conversa: “Eu assino formalmente a Política v1.1 e as aprovações da Controladoria, após isso integre”. Esta declaração é registrada como ratificação da versão 1.1 e aprovação para prosseguir com a integração técnica. O registro de GitHub desta alteração mantém trilha de auditoria. Se a governança corporativa exigir instrumento de assinatura externo, ele deve ser anexado ao processo interno; esta anotação não inventa certificado nem documento externo.

A ratificação não dispensa gates de execução: validação das regras com origem autorizada, backup/restauração verificados, conciliação, dez dias úteis de estabilidade e liberação formal do corte.

## 1. Princípios

1. **Dinheiro nunca é ponto flutuante.** Proibido usar `float`/`double`/`REAL` para valores monetários novos.
2. **Valores monetários são exatos.** Somas, comparações e agrupamentos são feitos em aritmética inteira ou decimal exata.
3. **Arredonda-se uma única vez, no final do cálculo**, nunca em etapas intermediárias.
4. **Valor de origem não é recalculado.** Valor de título, boleto, nota fiscal e extrato bancário é dado de origem: é importado como veio, não refeito pelo app.
5. **Arredondamento de exibição não altera o dado.** Formatação de tela e gráfico nunca é persistida.

---

## 2. Representação de armazenamento aprovada

**Valores monetários: `INTEGER` em centavos (menor unidade da moeda).**

| Item | Regra |
|---|---|
| Tipo da coluna | `INTEGER` (64 bits) |
| Unidade | Centavos de real. R$ 1.234,56 → `123456` |
| Nomenclatura | Sufixo obrigatório `_centavos` (ex.: `valor_titulo_centavos`) |
| Sinal | Com sinal. Créditos, estornos e abatimentos são negativos |
| Nulo | Permitido só quando "não informado" for diferente de zero; zero é `0` |
| Soma/agregação | Soma direta dos inteiros, sem arredondamento |

**Conversão para exibição:** dividir por 100 apenas na camada de apresentação, formatando em `pt-BR` (`R$ 1.234,56`).

**Justificativa:** inteiros eliminam erro binário de ponto flutuante (ex.: `0,1 + 0,2 ≠ 0,3` em `REAL`), tornam somas exatas e conciliáveis com banco/ERP ao centavo, e funcionam em qualquer banco, inclusive SQLite, que não possui `DECIMAL` exato.

### 2.1 Grandezas que não são "valor monetário final"

Preços unitários (por kg, metro, rolo), taxas e percentuais exigem mais casas que o centavo e são armazenados como **inteiro escalado**:

| Grandeza | Escala | Coluna (exemplo) | Exemplo |
|---|---|---|---|
| Preço unitário | 4 casas (×10.000) | `preco_unitario_e4` | R$ 12,3456 → `123456` |
| Quantidade | 4 casas (×10.000) | `quantidade_e4` | 1.250,5000 kg → `12505000` |
| Percentual / taxa | 4 casas (×10.000) | `taxa_percentual_e4` | 2,0000 % → `20000` |

O sufixo `_eN` indica a escala (N casas decimais). O valor final em centavos só nasce após o cálculo e o arredondamento da seção 3.

---

## 3. Regra de arredondamento

**Método aprovado: arredondamento comercial (*half-up*, meio para longe do zero), para 2 casas decimais (centavo).**

- Fração **≥ 0,5 centavo** → sobe um centavo (em módulo).
- Fração **< 0,5 centavo** → mantém.
- Aplicação simétrica para negativos: `-0,005 → -0,01`; `-0,004 → 0,00`.

**Por que *half-up* e não *half-even* (arredondamento bancário / NBR 5891):** a conciliação do contas a pagar é feita contra ERP, notas fiscais, boletos e bancos, que na prática operam com *half-up*. Adotar outro método geraria divergências de 1 centavo recorrentes e difíceis de explicar.

> **Validação pendente:** confirmar com TI/Contabilidade que o ERP e o módulo de títulos usam *half-up* no cálculo de juros, multa e descontos. Se algum deles divergir, a regra do sistema de origem prevalece para aquele cálculo, e o app apenas reproduz o valor importado.

### 3.1 Quando arredondar

| Situação | Momento do arredondamento |
|---|---|
| Quantidade × preço unitário | Uma vez, sobre o total da linha |
| Juros, multa, desconto, abatimento | Uma vez, sobre o valor final de cada encargo |
| Somas e totais (dashboard, relatórios) | **Nunca arredondar**: soma de inteiros já é exata |
| Rateio e parcelamento | Seção 5 |
| Indicadores e percentuais derivados | Somente na exibição |

### 3.2 Cálculos típicos de cobrança

Os parâmetros (taxas, base de dias, carência) **não são definidos por esta política**: vêm do contrato/condição comercial e do ERP (Systêxtil). Esta política define apenas **como calcular e arredondar**.

| Cálculo | Método aprovado |
|---|---|
| Multa por atraso | Percentual (`_e4`) × valor original do título, aplicada **uma única vez**; arredondar o encargo para centavos |
| Juros de mora | Juros **simples**, proporcional por dia (*pro rata die*): `valor × taxa_mensal_e4 × dias_de_atraso / base_de_dias`; arredondar **uma vez** no total dos juros |
| Valor atualizado | Original + multa + juros − descontos/abatimentos, tudo em centavos inteiros; sem arredondar novamente |
| Pagamento parcial | Abatimento em centavos inteiros; saldo = original atualizado − pagamentos, nunca recalculado por percentual |
| Custas de cartório | Valor de origem informado pelo cartório, importado como centavos; não é recalculado |
| Desconto / abatimento | Valor ou percentual aplicado uma vez; resultado arredondado *half-up* |

**Regras específicas:**

1. **Boleto emitido (portal B2B) é dado de origem.** O valor impresso no boleto é o valor oficial do título naquela data e **não é refeito** pelo app. O app apenas o registra e o compara com o valor que ele mesmo calcularia, sinalizando divergência.
2. **Dias de atraso** são contados como inteiro, pela data de vencimento e pela data de referência, e **não são arredondados nem fracionados**.
3. **Confirmação de pagamento tem defasagem** (em geral ~1 dia útil; no cartório pode ser maior). O dashboard distingue **"pago (confirmado)"** de **"pagamento informado/pendente de baixa"**, e os dois nunca são somados como se fossem a mesma coisa.
4. **Totais de carteira, recuperação e vencidos** são somas de centavos inteiros, sem arredondamento intermediário.

---

## 4. Valores com mais de duas casas decimais

1. **A classificação é campo a campo no contrato de dados.** Para um campo classificado como **valor monetário final**, a entrada deve ser decimal exata, sem passar por `float`. É permitida precisão textual superior a duas casas **somente quando todos os dígitos depois da segunda casa forem zero**: por exemplo, `1.230` equivale exatamente a `123` centavos e é aceito; `1.231` contém fração subcentavo e bloqueia o registro. A validação não arredonda nem corrige silenciosamente a entrada.
2. Para um **valor monetário final**, qualquer dígito não zero a partir da terceira casa decimal rejeita o registro/payload do dia com erro controlado, antes de abrir a transação de gravação. Não pode haver gravação parcial do dia.
3. Para uma **grandeza de cálculo** (por exemplo, preço unitário, taxa ou quantidade fracionária), o contrato declara a escala permitida (`_e4`, `_e6` ou outra escala expressamente aprovada). A entrada é preservada com aritmética decimal/exata; *half-up* aplica-se somente ao resultado monetário final do cálculo, nunca para mascarar entrada inválida.
4. **Validação lexical do token:** números JSON são validados a partir do token original, antes de construir `Decimal`. O formato permitido é `^-?\d+(\.\d+)?$`, sem expoente `e/E`; `NaN`, `Infinity`, `-Infinity`, booleanos e valores não finitos são rejeitados. Strings decimais só podem ser aceitas se o contrato do campo declarar explicitamente esse tipo, e devem passar pela mesma validação lexical. Campo ausente, `null` e zero mantêm semânticas distintas conforme o contrato.
5. **Sem passagem intermediária por ponto flutuante.** Em Python, `parse_int`/`parse_float` (ou parser equivalente) devem validar o token bruto; `parse_constant` deve rejeitar constantes não finitas; a normalização deve rejeitar booleanos explicitamente, pois `bool` é subtipo de `int` em Python.
6. Se a origem enviar legitimamente dígitos não zero além da segunda casa para um campo final, a implementação dessa regra deve parar e voltar à Diretoria Financeira com payload sanitizado e autorizado e evidência do contrato da origem. Não se deve arredondar o valor de origem para fazê-lo caber no contrato.
7. **No cálculo:** produtos intermediários mantêm a escala exata e só passam pelo arredondamento *half-up* no resultado final.
8. **Na saída:** valores monetários finais são exibidos e exportados com duas casas; preços unitários/taxas e outras grandezas escaladas seguem a escala do contrato.
9. **Proibido:** truncar casas, arredondar parcialmente, arredondar silenciosamente uma entrada final inválida ou comparar valores monetários novos com tolerância (`abs(a-b) < 0.01`). Valores novos em centavos são comparados por igualdade exata de inteiros.

---

## 5. Rateio e parcelamento

- A soma das partes deve ser **exatamente igual** ao total.
- Cada parte é calculada em centavos inteiros (divisão inteira); o **resto em centavos é somado à última parcela**.
- Exemplo: R$ 100,00 em 3 parcelas → `3333 + 3333 + 3334` centavos.
- A mesma regra vale para rateio entre centros de custo.

---

## 6. Exibição em gráficos e indicadores

- Eixos e rótulos: formatação `pt-BR`, com 2 casas para valores exatos.
- Valores grandes podem ser abreviados (mil, mi) **somente na visualização**, com o valor exato acessível em detalhe ou *tooltip*.
- Percentuais e indicadores de cobrança (ex.: % vencido, taxa de recuperação, valor em aging por faixa de atraso, por negociador): calculados sobre os inteiros em centavos e arredondados na exibição (1 casa por padrão). A soma visual de percentuais pode não fechar 100,0 %, o que é aceito; o dado subjacente permanece exato.

---

## 7. Colunas `REAL` existentes: congelamento e migração

**Proposta v1.1 — “REAL congelado” não significa somente leitura literal durante toda a transição.** O esquema e a semântica das colunas existentes ficam congelados: nenhuma coluna `REAL` é renomeada, convertida, recalculada ou removida antes de análise de compatibilidade, migração aprovada e etapa formal de descomissionamento. A escrita legada existente permanece ativa, inalterada quanto à semântica, apenas para manter a compatibilidade com os consumidores e permitir rollback.

Durante a transição:

1. **Colunas legadas preservadas.** Não renomear, alterar, recalcular ou remover as colunas `REAL` existentes. O fluxo monetário novo não usa `REAL` para cálculos, agregações, filtros ou comparações de negócio.
2. **Escrita de compatibilidade mantida.** O caminho legado de escrita em `REAL` permanece ativo sem mudança de semântica e isolado como adaptador de compatibilidade. A gravação das novas colunas `INTEGER` em centavos ocorre na **mesma transação SQLite**. Se qualquer lado falhar, ambas as escritas são revertidas.
3. **Duração explícita.** A escrita legada em `REAL` permanece ativa durante a dupla escrita, durante o corte e por **pelo menos 90 dias corridos depois do corte**. Ela só termina no descomissionamento formal, em etapa separada e mediante aprovação própria da Controladoria. Se o prazo de 90 dias for concluído sem a aprovação, a escrita legada continua.
4. **Novas colunas.** Acrescentar colunas monetárias `INTEGER` com sufixo `_centavos` e nomes semânticos por métrica, conforme o contrato versionado. Métricas não aplicáveis a um tipo de fato ficam `NULL`; zero é armazenado como `0`.
5. **Leitura de histórico.** Valores históricos existentes em `REAL` são convertidos apenas por uma única função (`real_para_centavos`) que aplica *half-up* sobre `Decimal(repr(valor))`. A conversão é uma interpretação técnica do valor armazenado, não uma reconstrução garantida do token JSON original. Suspeitas e diferenças ficam registradas em relatório, nunca corrigidas silenciosamente.
6. **Conciliação e corte.** A leitura passa para centavos somente após backup verificado, backfill idempotente, dez dias úteis consecutivos de conciliação válida, 100% das divergências classificadas, zero divergência inexplicada, testes automatizados verdes e aprovação da Controladoria com assinatura final da Diretoria Financeira.
7. **Rollback após o corte.** Como a escrita em `REAL` continua ativa no período pós-corte, reverter a chave de leitura para as colunas legadas preserva também os registros recebidos após o corte. O rollback primário é a reversão da leitura; a restauração de backup é secundária e deve estar ensaiada em homologação.
8. **Descomissionamento separado.** A desativação da escrita em `REAL` e eventual remoção das colunas são mudanças separadas, aprovadas pela Controladoria após pelo menos 90 dias corridos sem incidentes e após confirmar que todos os consumidores deixaram de depender de `REAL`. O prazo de 90 dias, por si só, não autoriza a remoção.

### 7.1 Conteúdo mínimo da análise de compatibilidade (pré-requisito para migrar)

- Inventário de tabelas/colunas `REAL` monetárias e quem as lê ou escreve (app, ERP, planilhas, relatórios, integrações).
- Impacto em consultas, índices, *views*, exportações e integrações externas.
- Medição de divergência: total `REAL` × total convertido, por período.
- Estratégia de convivência (colunas paralelas ou *view* de compatibilidade) e critério de corte.
- Anexo com os consumidores que ainda leem `REAL` e a data/gate em que cada consumidor passará a ler centavos.

### 7.2 Conteúdo mínimo do plano de migração

1. Backup completo verificado com manifesto e SHA-256, mais restauração testada em homologação.
2. Criação de colunas `INTEGER` específicas por métrica em paralelo; preenchimento por script idempotente usando `real_para_centavos`.
3. Escrita legada preservada e escrita de centavos adicionada dentro da mesma transação SQLite, com testes de falha nos dois sentidos.
4. Período de dez dias úteis consecutivos de conciliação válida; divergências integralmente classificadas e sem diferença inexplicada.
5. Corte de leitura aprovado pela Controladoria e assinado pela Diretoria; rollback para REAL comprovado com dados pós-corte.
6. Escrita legada mantida por pelo menos 90 dias corridos após o corte e até aprovação formal do descomissionamento.
7. Descomissionamento de REAL em release posterior e separada, com aprovação própria.

---

## 8. Moedas estrangeiras (importações de insumos)

- Cada valor em moeda estrangeira guarda: `moeda` (código ISO 4217), valor em **menor unidade da moeda** (inteiro) e `cotacao_e6` (taxa com 6 casas, inteiro escalado).
- Conversão para BRL: `valor_moeda × cotacao`, com **um único arredondamento *half-up* para centavos de BRL** no final.
- Totais consolidados do dashboard são somados em BRL (centavos). Valores em moeda original são exibidos separadamente e nunca somados entre moedas diferentes.

---

## 9. Testes obrigatórios

Toda alteração que toque valores monetários deve passar por testes automatizados cobrindo, no mínimo:

- Cálculo interno *half-up* de fronteira: `0,005 → 0,01`; `0,004 → 0,00`; `-0,005 → -0,01`.
- Entrada final: `1.23` e `1.230` aceitos como 123 centavos; `1.231` rejeitado sem arredondamento; valores com 3, 4 e 6 casas com dígitos não zero após a segunda rejeitados.
- Validação lexical: token exponencial, `NaN`, infinito, booleano, texto decimal não contratado, `null` e campo ausente tratados conforme o contrato.
- Prova de que um registro inválido bloqueia todo o payload/dia antes da transação e não grava parcialmente.
- Soma de muitos itens sem deriva de centavos.
- Rateio/parcelamento em que a soma das partes iguala o total.
- Conversão de valores legados `REAL` problemáticos (ex.: `1.005`, `2.675`, `0.1 + 0.2`), reportando conversões suspeitas.
- Sinais permitidos/proibidos por campo e tipo, incluindo zero e `NULL` de métrica não aplicável.
- Testes de esquema, backfill idempotente, dupla escrita atômica, falha de cada lado da escrita e rollback da leitura no cenário pós-corte.
- Reexecução da migração sem duplicação/alteração dos dados existentes; verificação de backup e ensaio separado de restauração em homologação.

---

## 10. Governança

- Esta política só pode ser alterada pela Diretoria Financeira, com registro de versão e data.
- Exceções exigem justificativa por escrito e validação da Controladoria.
- Revisão periódica: semestral, ou a cada mudança relevante de ERP, banco de dados ou integração.

---

## Resumo executivo — Política v1.1 ratificada em 14/10/2026

| Pergunta | Regra proposta |
|---|---|
| Regra de arredondamento | *Half-up* (comercial), 2 casas, uma única vez no resultado final |
| Valores finais com mais de 2 casas | Zeros finais são aceitos se o valor permanecer exato em centavos (`1.230`); dígito não zero após a segunda casa rejeita a entrada sem arredondamento. Grandezas de cálculo seguem escala contratada e só arredondam no resultado final |
| Armazenamento | `INTEGER` em centavos (`_centavos`); preços/quantidades/taxas em inteiro escalado (`_e4`, `_e6`) |
| Cálculos de cobrança | Multa e juros pro rata die calculados com precisão total e arredondados uma vez; valor de boleto/cartório é dado de origem e não é recalculado |
| Colunas `REAL` existentes | Sem mudança semântica; escrita legada preservada durante dupla escrita e por pelo menos 90 dias após o corte, até descomissionamento formal aprovado |
