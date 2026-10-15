# Dicionário de indicadores de cobrança

**Revisão técnica:** 15/10/2026  
**Base inspecionada:** `main`, commit `de30c6b16783b65ce75d41f29d6aaa823fdf965f`  
**Finalidade:** descrever o que os arquivos versionados calculam hoje e separar isso de decisões de negócio que ainda precisam ser confirmadas.  
**Status:** catálogo técnico inicial; ainda requer validação de Cobrança/Financeiro.

Este documento não transforma a amostra JSON em contrato oficial da API. `amostra_resposta.json` e `amostra_resposta_ficticia.json` são fixtures ilustrativas, não evidência de valores reais. As fórmulas abaixo foram derivadas do importador, do agregador local e do auditor versionados nesta revisão. Onde o código não resolve a semântica de negócio, isso está declarado como pendência.

## 1. Como ler o catálogo

- **Fato de fluxo:** valor ou contagem acumulados dentro do intervalo selecionado a partir de `fatos`. A granularidade persistida é `data + usuario + tipo`; isso é um consolidado por usuário e dia, não uma linha para cada depósito, acordo, promessa ou contato individual.
- **Posição de carteira:** valores de um snapshot de referência. A captura mais recente elegível para o período é mostrada; snapshots de datas diferentes não devem ser somados.
- **Campo bruto da origem:** caminho no JSON de entrada. A existência do campo e o seu processamento pelo código não garantem que a semântica esteja homologada com o sistema de origem.
- **Zero, ausência e não aplicável:** zero é um valor numérico real; período sem dados, cobertura desconhecida ou campo que não se aplica não devem ser apresentados como zero.
- **R$ e centavos:** o painel formata valores monetários em reais. Os cálculos de apresentação passam por inteiro em centavos nos caminhos que o especificam; os campos físicos legados `REAL` permanecem preservados no banco conforme o contrato de migração.

## 2. Indicadores implementados

### 2.1 Depósitos

| Atributo | Definição observável |
|---|---|
| Nome de exibição | Depósitos registrados; valor depositado |
| Pergunta | Quantos depósitos e qual valor agregado constam no intervalo? |
| Fonte | `data.depositos.quantidadeTotal`, `data.depositos.valorTotal` e itens `data.depositos.porUsuario[]` |
| Granularidade da origem | Dia do payload + usuário do consolidado |
| Fórmula de quantidade | Soma de `porUsuario[].quantidade` para usuários presentes nos dias importados do filtro |
| Fórmula de valor | Soma de `porUsuario[].valor` para as linhas do tipo `deposito` dentro do filtro |
| Unidade | Quantidade inteira; BRL para valor |
| Classe | Fluxo agregado por período |
| Reconciliação | O auditor compara os totais `quantidadeTotal` e `valorTotal` contra as somas por usuário, com igualdade exata para dinheiro |
| Limites | Não assumir, sem confirmar a semântica da origem, que “depósito” equivale ao caixa líquido recebido de todos os canais. O campo de valor aceita sinal no código, mas o significado operacional de negativos/estornos deve ser confirmado |

Os totais agregados do JSON não são persistidos como uma segunda fonte independente do fato por usuário. O painel soma os fatos normalizados.

### 2.2 Acordos

| Métrica | Fonte no JSON | Fórmula implementada | Unidade e classe |
|---|---|---|---|
| Quantidade de acordos | `data.acordos.porUsuario[].quantidade` | Soma de `qtd` nas linhas do tipo `acordo` no período | Contagem; fluxo |
| Valor de face | `data.acordos.porUsuario[].valor` | Soma de `valor` nas linhas do tipo `acordo` no período | BRL; fluxo agregado |
| Valor pago | `data.acordos.porUsuario[].pagos` | Soma de `valor_pago` nas linhas do tipo `acordo` no período | BRL; classificação monetária associada aos acordos |
| Valor pendente | `data.acordos.porUsuario[].pendente` | Soma de `valor_aberto` nas linhas do tipo `acordo` no período | BRL; classificação monetária associada aos acordos |

O auditor concilia separadamente os totais de quantidade, valor de face, pagos e pendentes com os valores por usuário. **Ele não impõe a regra** `valor = pagos + pendente`. Embora essa igualdade ocorra em fixtures, mantê-la como regra bloqueante depende de validar exceções como renegociação, desconto, cancelamento, parcelas não vencidas, pagamento parcial e baixa pendente.

Não chamar valor de face de “dinheiro recebido”. Também não definir taxa de pagamento usando esses totais sem confirmar denominador, janela temporal e relação entre os eventos.

### 2.3 Promessas

| Métrica | Fonte no JSON | Fórmula implementada | Unidade e classe |
|---|---|---|---|
| Quantidade de promessas | `data.promessas.porUsuario[].quantidade` | Soma de `qtd` nas linhas do tipo `promessa` no período | Contagem; fluxo |
| Valor prometido | `data.promessas.porUsuario[].prometido` | Soma de `valor` nas linhas do tipo `promessa` no período | BRL; fluxo agregado |
| Valor cumprido | `data.promessas.porUsuario[].cumprido` | Soma de `valor_pago` nas linhas do tipo `promessa` no período | BRL; classificação reportada como cumprida |
| Valor em aberto | `data.promessas.porUsuario[].emAberto` | Soma de `valor_aberto` nas linhas do tipo `promessa` no período | BRL; classificação reportada como aberta |
| Valor quebrado | `data.promessas.porUsuario[].quebrado` | Soma de `valor_quebrado` nas linhas do tipo `promessa` no período | BRL; classificação reportada como quebrada |

O auditor reconcilia os totais aditivos de quantidade, prometido, cumprido, em aberto e quebrado com as somas por usuário. Isso não valida, por si só, que as classificações sejam mutuamente exclusivas ou que `prometido = cumprido + emAberto + quebrado` seja uma identidade contábil válida para todos os estados do processo.

Os campos `cumprido`, `emAberto` e `quebrado` são exibidos como valores separados; não são convertidos automaticamente em uma taxa de cumprimento. Uma taxa exigiria definir se o denominador é quantidade ou valor prometido, como tratar promessas parciais, múltiplas promessas por cliente e a janela usada para considerar um compromisso cumprido.

### 2.4 Contatos

| Métrica | Fonte no JSON | Fórmula implementada | Unidade e classe |
|---|---|---|---|
| Registros de contato | `data.contatos.porUsuario[].registrosTotais` | Soma de `qtd` das linhas do tipo `contato` no intervalo | Contagem de registros; fluxo |
| Contatos únicos por usuário | `data.contatos.porUsuario[].contatosUnicos` | O importador guarda o contador por usuário; o painel local soma esses contadores e rotula o resultado como soma de únicos por usuário | Contagem, com escopo limitado por usuário |
| Total global de contatos únicos | `data.contatos.contatosUnicosTotal` | O auditor o classifica como `NÃO ADITIVO`; não o compara à soma por usuário | Não homologado como total global deduplicado |

A soma dos únicos por usuário não equivale necessariamente a pessoas únicas globalmente. Uma mesma pessoa pode aparecer na carteira de mais de um usuário; não há chave nem regra de deduplicação global declarada neste payload. O rótulo e a nota do painel devem continuar deixando esse limite explícito.

O auditor compara `registrosTotaisTotal` com a soma de `registrosTotais`. Não trata `contatosUnicosTotal` como aditivo nem como gate de reconciliação.

### 2.5 Valores da carteira em `valoresAcordo`

Os três campos são fornecidos no objeto `data.valoresAcordo` e persistidos no registro de posição em `acordos_posicao`. Eles não são somados por usuário.

| Métrica | Campo de origem | Uso no painel | Classe e limite |
|---|---|---|---|
| Recebido no período | `data.valoresAcordo.valorRecebidoPeriodo` | Exibido a partir da captura mais recente elegível; o código e a interface preservam o nome “Recebido no período” | Campo de valor do período, carregado junto ao snapshot. Não somar o valor repetido em capturas distintas |
| A vencer | `data.valoresAcordo.valorAVencer` | Valor da captura mais recente elegível no intervalo | Posição da carteira; não é fluxo |
| Vencido | `data.valoresAcordo.valorVencido` | Valor da captura mais recente elegível no intervalo | Posição da carteira; não é fluxo |

A consulta do painel seleciona um snapshot cuja data está no filtro e ordena por `capturado_em` decrescente. Se não houver captura elegível, a posição fica indisponível; não deve ser reaproveitada uma captura fora do intervalo nem mostrada como saldo zero.

O campo `timestamp` é obrigatório para a importação e é preservado da origem para identificar o instante da captura; o código não deve substituir esse valor pelo relógio local nem inferir um fuso horário. O significado contábil de `valorRecebidoPeriodo`, bem como a relação entre ele e os fatos de depósito/acordo, deve ser confirmado com a origem para evitar dupla contagem.

## 3. Visões derivadas da aplicação

Estas visões são cálculos de interface sobre os indicadores acima, não campos adicionais da API.

| Visão | Regra observada | Condição de disponibilidade / interpretação |
|---|---|---|
| Resumo do período | Soma os fatos nas datas selecionadas; separa depósitos, acordo, promessa e contatos | O agregado inicializa os indicadores numéricos em zero e soma as linhas encontradas. Assim, um filtro sem fatos pode exibir zero no resumo enquanto o gráfico diário fica vazio; o payload de resumo, isoladamente, ainda não distingue zero real de ausência de registros. Cobertura de importações deve ser lida separadamente |
| Movimento diário | Agrupa os três fluxos monetários — depósitos, valor de face de acordos e valor prometido — por data | A posição a vencer/vencida não entra no gráfico de fluxo. Uma única data não demonstra tendência |
| Posição mais recente | Escolhe o snapshot elegível com maior `capturado_em` | Exibe recebido, a vencer e vencido a partir dessa captura; não soma snapshots |
| Comparação de períodos | Compara depósitos, valor de face de acordos e valor prometido em períodos de igual duração | Na aplicação local, exige metadados de importação disponíveis e os mesmos offsets relativos de datas importadas nos dois períodos. Não compara snapshots |
| Delta percentual | Calcula `(atual - anterior) / anterior × 100`, com uma casa decimal | Percentual indisponível quando a base anterior é zero ou negativa; delta absoluto pode continuar sendo exibido quando a comparação é válida |
| Recência/cobertura | Lê registros da tabela `importacoes` e a união dos intervalos reportados no período | Não presume cadência esperada. “Última importação registrada” não significa, por si só, “carga atrasada” |
| Ordenação por usuário (aplicação local) | Implementação atual ordena por uma soma de valores de depósitos + acordos + promessas, além do identificador como desempate | É critério técnico de ordenação, não um KPI de produtividade. As parcelas podem representar conceitos financeiros diferentes; não rotular como “melhor/pior desempenho” |

A comparação temporal disponível na aplicação local não deve ser transportada para a demonstração estática de uma única data como se existisse histórico real. O fixture estático atual contém apenas a data informada no próprio JSON e deve dizer que a comparação não está disponível.

## 4. Auditoria e cobertura de reconciliação

`auditar_resposta.py` implementa 12 verificações aditivas contra o payload, agrupadas em:

- depósitos: quantidade e valor;
- acordos: quantidade, valor, pagos e pendentes;
- promessas: quantidade, prometido, cumprido, em aberto e quebrado;
- contatos: registros totais.

Cada total é comparado com a soma da propriedade correspondente em `porUsuario`. As quantidades precisam ser inteiras; os valores monetários são comparados em centavos com igualdade exata. O relatório também identifica `contatosUnicosTotal` como `NÃO ADITIVO`, sem comparar esse total à soma por usuário.

O auditor não valida sozinho:

- a regra de negócio `valor = pagos + pendente` para todos os tipos de acordo;
- uma identidade entre prometido, cumprido, em aberto e quebrado;
- `valorRecebidoPeriodo` contra depósitos, acordos ou pagamentos;
- o saldo de carteira contra uma soma individual de títulos;
- unicidade global de contatos;
- atualidade/cadência operacional da carga;
- existência de todos os dias esperados de uma janela de relatório.

Portanto, “auditoria passou” significa que os totais aditivos implementados foram conciliados para aquele payload. Não significa que a definição contábil de cada indicador foi homologada nem que o dado é completo ou atual.

## 5. Indicadores que ainda não podem ser calculados de forma confiável

| Indicador solicitado ou tentador | Estado | Dados/regra ainda necessários |
|---|---|---|
| Taxa de cumprimento de promessas | Não homologada | Denominador (valor ou quantidade), tratamento de cumprimento parcial, data de vencimento/promessa e janela de observação |
| Conversão de contato para promessa ou pagamento | Não disponível com esse agregado | Eventos individualizados ligados por chaves, datas e regra de atribuição |
| Recuperação sobre carteira elegível | Não disponível | Base elegível definida, saldo por título/carteira, janela e regras de inclusão/exclusão |
| Aging por faixa de atraso | Não disponível | Vencimento e saldo individual por título, data-base e limites exatos das faixas |
| Meta e atingimento | Não há meta declarada no payload | Meta oficial, unidade, escopo, período e responsável |
| Previsão de recebimento | Fora do escopo atual | Histórico validado, modelo/critério, avaliação de erro e autorização para uso |
| Carteira de ação por cliente/título | Não disponível | Identificador estável, vencimento, saldo, status, histórico e próxima ação/responsável |
| Pessoas únicas globais | Não comprovado | Chave de pessoa e regra de deduplicação entre carteiras |
| “Melhor negociador” por produtividade | Não definido | Carteira atribuída, volume recebido, critérios de esforço e denominadores comparáveis |

Não derivar essas métricas só por divisões de agregados que parecem plausíveis. Uma fórmula aritmeticamente possível não demonstra uma relação causal nem a elegibilidade do denominador.

## 6. Decisões que Cobrança/Financeiro ainda precisa confirmar

O catálogo pode ser usado para uma revisão de negócio, mas não representa homologação. Além das decisões semânticas, há um ponto de UX/qualidade a tratar: o agregador local inicializa os indicadores numéricos em zero; em período sem fatos isso pode se parecer com zero movimento. Antes de usar o resumo como ferramenta operacional, a interface deve distinguir período sem registros/carga ausente de um período efetivamente conciliado com movimento zero. Registrar a decisão, responsável, data e evidência de validação fora de dados pessoais/financeiros:

- [ ] O que conta como depósito e se estornos/valores negativos são representados nesse campo.
- [ ] Significado operacional de valor de face, pago e pendente do acordo; tratamento de renegociações, descontos, cancelamentos, parcelas não vencidas, pagamento parcial e baixa pendente.
- [ ] Significado exato de promessa cumprida, em aberto e quebrada; se as categorias podem coexistir/parcializar o valor.
- [ ] Semântica, janela e instante de referência de `valorRecebidoPeriodo`; relação com depósitos e outros movimentos.
- [ ] Fuso/forma de leitura dos timestamps no processo consumidor, mantendo o texto original de origem como referência.
- [ ] Granularidade e eventual deduplicação dos contatos únicos; a contagem atual não é global.
- [ ] Política para cobertura de dias sem importação: ausência, atraso, falha de carga ou zero movimento.
- [ ] Definição aprovada e denominador antes de adicionar qualquer taxa, alerta, ranking ou meta.

Até essas decisões serem registradas, manter as notas de limitação em interface e relatórios. Não tornar relações contábeis bloqueantes, não introduzir taxas e não habilitar operação em produção com base apenas neste documento ou em CI verde.

## 7. Arquivos de referência implementados

- `amostra_resposta.json`: estrutura ilustrativa original; não é prova do contrato de produção.
- `amostra_resposta_ficticia.json`: fixture fictício com a mesma estrutura para demonstração e modo `--demo`.
- `importar.py`: normaliza a resposta em fatos agregados por usuário/tipo/dia e os valores do objeto `valoresAcordo`.
- `auditar_resposta.py`: reconcilia totais aditivos e identifica contatos únicos globais como não aditivos.
- `dashboard_app.py`: soma fatos por intervalo, escolhe snapshot e cria a comparação temporal condicional.
- `docs/architecture/CONTRATO_DADOS_FINANCEIROS.md`: contrato de dados, mapeamento monetário e estado das decisões técnicas.
- `docs/monetary/RECONCILIACAO_E_INVENTARIO_PENDENCIAS.md`: mantém abertas a diferença de contagens 17 versus 18 e a verificação de consumidores externos.

Nenhum passo deste catálogo executa importação, migração, backfill ou escrita em banco operacional.
