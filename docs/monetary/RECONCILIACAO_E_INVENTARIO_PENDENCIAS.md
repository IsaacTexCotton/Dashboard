# Reconciliação de evidências monetárias e inventário externo

**Estado em 15/10/2026:** a definição de contagem do código foi confirmada estaticamente e coberta por teste sintético; a divergência histórica 17 versus 18 continua sem reconciliação operacional porque a identidade dos payloads/execuções não está demonstrada. O inventário de componentes do repositório foi ampliado, mas o inventário externo e a confirmação operacional permanecem pendentes.

Este documento não autoriza operação em produção. Payloads de negócio, valores, hashes de arquivos financeiros, logs completos, caminhos internos e variáveis de ambiente não devem ser versionados.

## 1. Divergência de contagens

Há duas evidências históricas com escopo ainda não demonstrado como equivalente:

- Uma validação de payload sanitizado registrou **17 fatos** no dry-run, vinculada no contrato de dados ao commit `b9754aa744b35bfd0d9f8604034887d2c160ecbd`.
- Um relato posterior listou **18 itens `porUsuario`**: 5 depósitos, 5 acordos, 3 promessas e 5 contatos. O SHA do código e a identidade do payload dessa segunda execução não foram registrados.

### Definição observável de “fato” no código atual

A inspeção de `importar.py`, `auditar_resposta.py`, `validar_integracao_local.py` e `tests/test_importar.py` estabeleceu a seguinte regra:

1. `normalizar()` percorre cada item das listas `depositos.porUsuario`, `acordos.porUsuario`, `promessas.porUsuario` e `contatos.porUsuario` e acrescenta uma tupla de fato por item. Não existe deduplicação cruzada entre tipos; o mesmo usuário pode produzir fatos de tipos diferentes. Usuário duplicado dentro de um mesmo grupo é rejeitado pela validação.
2. `gravar()` apaga os fatos do dia a reprocessar e insere todas as tuplas normalizadas. Retorna `len(fatos)` e grava essa mesma contagem em `importacoes.linhas`.
3. O caminho `--dry-run` calcula `len(fatos)` e imprime também as linhas previstas por tipo, sem abrir/criar banco.
4. `validar_integracao_local.py` consulta em SQLite temporário a contagem real das linhas por tipo e no total.
5. A auditoria financeira soma métricas aditivas, mas não é por si só uma auditoria de quantidade de linhas. `contatosUnicosTotal` permanece não aditivo.

**Conclusão da regra de contagem:** para um mesmo payload aceito por essa versão do código, 5 + 5 + 3 + 5 itens `porUsuario` devem produzir **18 fatos normalizados** e 18 linhas na gravação temporária. Não é correto explicar uma diferença de um registro simplesmente afirmando que “itens por usuário” e “fatos” têm definições diferentes nesse caminho de código.

O commit histórico `b9754aa...` alterou o tratamento de exceções da CLI e um teste; seu diff não altera a regra de normalização/contagem. Isso, porém, **não prova** que a execução de 17 fatos e o relato de 18 itens tenham utilizado o mesmo arquivo, o mesmo checkout completo, ou que o relato posterior tenha contado o resultado do importador. A divergência permanece aberta até que esses elementos sejam confirmados em ambiente autorizado.

Os fixtures versionados atuais não resolvem a divergência histórica: o teste de `amostra_resposta.json` verifica 5 linhas de origem e 5 fatos; a amostra fictícia foi criada para demonstração e possui a mesma estrutura do fixture original, não os grupos 5/5/3/5 do relato.

### Procedimento de reconciliação

Executar somente em ambiente autorizado, com payload sanitizado fora do Git:

1. Identificar localmente cada execução, sem publicar nome de cliente, valores, conteúdo do payload, hash do arquivo ou caminho interno.
2. Confirmar se os dois relatórios usaram exatamente o mesmo payload. Se a identidade não puder ser demonstrada, classificar os relatos como execuções distintas, sem tentar fazê-los coincidir.
3. Executar no mesmo checkout e payload: auditoria, `--dry-run` e validação integrada em SQLite temporário. Para cada execução, registrar em local restrito:
   - contagem `porUsuario` de cada grupo;
   - quantidade normalizada por tipo e quantidade total;
   - total esperado e observado em SQLite temporário;
   - SHA do commit, saída final dos comandos e regra que explique eventual delta.
4. Não apagar, deduplicar ou editar linhas para fazer a contagem coincidir. Se o mesmo payload aceito produzir 17 fatos quando as quatro listas somam 18, investigar a divergência como falha real e manter a promoção bloqueada.
5. No registro versionado, publicar apenas totais agregados não sensíveis e o status da investigação.

### Registro de reconciliação

| Execução local | Commit reportado | Depósitos | Acordos | Promessas | Contatos | Fatos normalizados | Resultado |
|---|---|---:|---:|---:|---:|---:|---|
| Validação anterior | `b9754aa744b35bfd0d9f8604034887d2c160ecbd` | Não registrado | Não registrado | Não registrado | Não registrado | 17 reportados | Evidência histórica; entrada exata não versionada |
| Validação posterior (relato) | Não informado | 5 | 5 | 3 | 5 | Não confirmado | 18 itens de origem; precisa comprovar saída correspondente |
| Teste sintético reproduzível adicionado nesta etapa | Commit desta alteração (ver PR vinculada) | 5 | 5 | 3 | 5 | 18 normalizados e gravados em SQLite em memória | Valida a regra do código; não identifica o payload histórico |

## 2. Inventário de leitores/escritores

O mapa estático dos componentes atuais está em [`INVENTARIO_LEITORES_ESCRITORES_MONETARIOS.md`](INVENTARIO_LEITORES_ESCRITORES_MONETARIOS.md). Foram identificados os escritores e leitores presentes no código versionado, incluindo o dashboard local somente-leitura e as ferramentas de migração/backfill explicitamente invocadas.

Essa inspeção **não confirma nem exclui** consumidores fora do repositório: agendadores, planilhas, Power Query/ODBC, BI, scripts em compartilhamentos, backups usados para consulta, hosts diferentes e pessoas que abrem SQLite diretamente. A [Issue #17](https://github.com/IsaacTexCotton/Dashboard/issues/17) segue aberta porque exige confirmação operacional por responsáveis, notificação, revisão do runbook e ensaio de restauração autorizado.

## 3. Critérios para encerrar as pendências

- [ ] A contagem 17 versus 18 foi ligada a payloads/execuções específicos e reconciliada, ou os relatos foram comprovadamente classificados como execuções distintas.
- [ ] Se aplicável, a execução com payload sanitizado autorizado foi reproduzida em checkout identificado, com audit, dry-run e SQLite temporário.
- [x] O código versionado e a regra atual de mapeamento `porUsuario` → fato foram inspecionados e há teste sintético que comprova a contagem 18 no banco temporário.
- [x] O inventário estático dos leitores/escritores do repositório foi atualizado.
- [ ] O inventário externo foi confirmado “até onde é possível saber” com donos e data, conforme Issue #17.
- [ ] Donos foram avisados antes de qualquer congelamento das colunas `REAL`.
- [ ] O runbook foi revisado com os responsáveis operacionais.
- [ ] O exercício de restauração foi realizado em homologação autorizada e documentado.

Até que os itens operacionais sejam atendidos, manter a reconciliação histórica e o inventário externo como pendentes. Não habilitar dupla escrita/leitura em produção, não executar migração ou backfill real e não retirar colunas `REAL` com base apenas em CI verde ou em teste sintético.
