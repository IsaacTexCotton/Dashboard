# Política de Precisão Monetária — Dashboard de Cobrança (Contas a Pagar / Financeiro)

**Status:** Aprovada (versão 1.0)
**Aprovador:** Diretoria Financeira
**Escopo:** Todo valor monetário calculado, armazenado, importado, exibido ou exportado pelo aplicativo de dashboard do **setor de Cobrança**, dentro da área de Contas a Pagar e Financeiro (títulos vencidos, juros, multa, descontos, boletos, pagamentos, negativação e cartório).
**Moeda base:** BRL (Real). Moedas estrangeiras seguem a seção 8.

---

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

1. **Na entrada (importação ERP/planilha/API):** valor com mais de 2 casas é lido como texto decimal (nunca via `float`), convertido para inteiro escalado e, se for valor monetário final, arredondado por *half-up* para centavos. O valor bruto original pode ser guardado em coluna de auditoria (`_e4`) quando for relevante.
2. **No cálculo:** usar aritmética inteira escalada ou biblioteca decimal exata; produtos intermediários mantêm todas as casas e só passam pelo arredondamento no resultado final.
3. **Na saída:** valores monetários exibidos e exportados sempre com **2 casas**; preços unitários e taxas com até 4 casas, conforme a grandeza.
4. **Proibido:** truncar casas (cortar sem arredondar), arredondar parcial a cada etapa, ou comparar valores monetários com tolerância (`abs(a-b) < 0.01`). A comparação é por igualdade exata dos inteiros.

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

**Decisão:** nenhuma coluna `REAL` existente será alterada, convertida ou removida sem **análise de compatibilidade e plano de migração aprovados**.

Até lá:

1. **Colunas legadas permanecem como estão** e são tratadas como somente leitura para o novo código.
2. **Novas colunas monetárias** nascem em `INTEGER` (centavos), conforme a seção 2.
3. **Leitura de legado:** todo valor vindo de coluna `REAL` passa por uma única função de conversão (`real_para_centavos`), que aplica *half-up* sobre o valor com proteção contra erro binário (ex.: `1.005` armazenado como `1.00499999…`). Nenhum outro ponto do código converte `REAL` por conta própria.
4. **Auditoria de divergência:** o dashboard deve permitir comparar total legado (`REAL`) × total convertido (`INTEGER`) para identificar diferenças de centavos.

### 7.1 Conteúdo mínimo da análise de compatibilidade (pré-requisito para migrar)

- Inventário de tabelas/colunas `REAL` monetárias e quem as lê ou escreve (app, ERP, planilhas, relatórios, integrações).
- Impacto em consultas, índices, *views*, exportações e integrações externas.
- Medição de divergência: total `REAL` × total convertido, por período.
- Estratégia de convivência (colunas paralelas ou *view* de compatibilidade) e critério de corte.

### 7.2 Conteúdo mínimo do plano de migração

1. Backup completo e verificado.
2. Criação das colunas `INTEGER` em paralelo; **preenchimento por script idempotente** usando `real_para_centavos`.
3. Período de **dupla escrita e conciliação** (legado × novo) com relatório de divergências.
4. Corte de leitura para as novas colunas após conciliação aprovada pela Controladoria.
5. Plano de *rollback* documentado e testado.
6. Descomissionamento das colunas `REAL` apenas em etapa posterior e separada, com aprovação própria.

---

## 8. Moedas estrangeiras (importações de insumos)

- Cada valor em moeda estrangeira guarda: `moeda` (código ISO 4217), valor em **menor unidade da moeda** (inteiro) e `cotacao_e6` (taxa com 6 casas, inteiro escalado).
- Conversão para BRL: `valor_moeda × cotacao`, com **um único arredondamento *half-up* para centavos de BRL** no final.
- Totais consolidados do dashboard são somados em BRL (centavos). Valores em moeda original são exibidos separadamente e nunca somados entre moedas diferentes.

---

## 9. Testes obrigatórios

Toda alteração que toque valores monetários deve passar por testes automatizados cobrindo, no mínimo:

- Arredondamento de fronteira: `0,005 → 0,01`; `0,004 → 0,00`; `-0,005 → -0,01`.
- Soma de muitos itens sem deriva de centavos.
- Rateio/parcelamento em que a soma das partes iguala o total.
- Conversão de valores legados `REAL` problemáticos (ex.: `1.005`, `2.675`, `0.1 + 0.2`).
- Importação de valores com 3, 4 e 6 casas decimais.

---

## 10. Governança

- Esta política só pode ser alterada pela Diretoria Financeira, com registro de versão e data.
- Exceções exigem justificativa por escrito e validação da Controladoria.
- Revisão periódica: semestral, ou a cada mudança relevante de ERP, banco de dados ou integração.

---

## Resumo executivo

| Pergunta | Decisão aprovada |
|---|---|
| Regra de arredondamento | *Half-up* (comercial), 2 casas, uma única vez no resultado final |
| Valores com mais de 2 casas | Lidos como texto, mantidos em inteiro escalado no cálculo, arredondados só no final; nunca truncar |
| Armazenamento | `INTEGER` em centavos (`_centavos`); preços/quantidades/taxas em inteiro escalado (`_e4`, `_e6`) |
| Cálculos de cobrança | Multa e juros pro rata die calculados com precisão total e arredondados uma vez; valor de boleto/cartório é dado de origem e não é recalculado |
| Colunas `REAL` existentes | Congeladas; só mudam após análise de compatibilidade e plano de migração aprovados |
