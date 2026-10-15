# Reconciliação de evidências monetárias e inventário externo

**Estado em 15/10/2026:** pendente de confirmação operacional. Este documento organiza a evidência necessária; não afirma que os payloads comparados sejam o mesmo arquivo e não autoriza operação em produção.

## 1. Divergência de contagens

Há duas contagens documentadas, com escopo ainda não demonstrado como equivalente:

- Uma validação anterior registrou **17 fatos** no dry-run.
- Um relato posterior listou **18 itens `porUsuario`**: 5 depósitos, 5 acordos, 3 promessas e 5 contatos.

A soma aritmética dos quatro grupos é 18, mas isso não prova que os dois números sejam contraditórios: “itens `porUsuario`” e “fatos persistidos” podem usar critérios diferentes, e os relatos podem corresponder a payloads distintos. Não escolher um número como correto sem verificar a origem.

### Procedimento de reconciliação

Executar somente em ambiente autorizado, com payload sanitizado fora do Git:

1. Selecionar cada arquivo de entrada por um identificador de execução local, sem publicar nome de cliente, valores, conteúdo do payload ou hash do arquivo.
2. Confirmar se os dois relatórios foram produzidos a partir do mesmo arquivo e da mesma versão do código. Se não for possível demonstrar isso, classificá-los como execuções distintas.
3. Para cada execução, registrar separadamente:
   - contagem de itens de origem em cada grupo (`depositos`, `acordos`, `promessas`, `contatos`);
   - contagem de registros normalizados por tipo;
   - contagem esperada e observada de fatos persistidos no banco temporário;
   - regra de inclusão/exclusão aplicada a cada grupo e qualquer deduplicação;
   - SHA do commit do código executado e resultado/identificador do relatório local.
4. Rodar `--dry-run`, auditoria e validação integrada com o mesmo arquivo e o mesmo checkout, usando SQLite temporário. Não remover nem editar linhas para fazer as contagens coincidirem.
5. Se houver diferença, registrar o delta por tipo e a regra que o explica. Se não houver explicação demonstrável, manter a divergência aberta e bloquear a promoção da evidência a “homologada”.

### Registro de reconciliação

| Execução local | Commit | Depósitos | Acordos | Promessas | Contatos | Fatos normalizados | Fatos esperados/observados | Resultado |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Validação anterior (relato) | `b9754aa744b35bfd0d9f8604034887d2c160ecbd` | Não registrado aqui | Não registrado aqui | Não registrado aqui | Não registrado aqui | Não confirmado | 17 reportados no dry-run | Evidência histórica; reexecutar só se autorizado |
| Validação posterior (relato) | Não informado | 5 | 5 | 3 | 5 | 18 itens de origem no total | Fatos persistidos não confirmados | Não comparável até confirmar payload e critério |

**Não incluir neste repositório** payloads, hashes de arquivos financeiros, dados pessoais, valores de clientes, caminhos de compartilhamentos internos, manifestos de backup ou variáveis de ambiente. O responsável pode manter a evidência detalhada em local restrito e registrar aqui apenas resultados agregados não sensíveis.

## 2. Inventário de leitores e escritores externos

A inspeção do repositório não confirma nem exclui consumidores que abram diretamente o arquivo SQLite. Preencher esta matriz com os responsáveis operacionais; “não identificado” não significa “inexistente”.

| Classe de consumidor | Verificação operacional necessária | Consumidor/dono | Evidência e data | Estado |
|---|---|---|---|---|
| Tarefas agendadas/serviços | Conferir jobs e processos que leem ou escrevem no arquivo | Pendente | Pendente | Não verificado |
| Planilhas e conectores | Consultar donos sobre ODBC, Power Query, consultas e arquivos vinculados | Pendente | Pendente | Não verificado |
| BI e painéis alternativos | Listar fontes SQLite, consultas salvas e extrações | Pendente | Pendente | Não verificado |
| Scripts e pastas compartilhadas | Buscar scripts de consulta e automações sob controle autorizado | Pendente | Pendente | Não verificado |
| Backups usados para consulta | Identificar cópias que sejam usadas como fonte de relatório | Pendente | Pendente | Não verificado |
| Usuários diretos | Consultar Cobrança, Controladoria e TI sobre acesso direto ao SQLite | Pendente | Pendente | Não verificado |
| Consumidores em outros repositórios/hosts | Consultar responsáveis pelos sistemas e hosts fora deste repo | Pendente | Pendente | Não verificado |

Para cada consumidor confirmado, registrar quais colunas `REAL` lê, frequência, dono, plano/data de migração para centavos, comunicação realizada e como verificar a compatibilidade. Não registrar credenciais nem dados financeiros.

## 3. Critérios para encerrar as pendências

- [ ] A contagem 17 versus 18 foi explicada por payload, definição de contagem ou transformação documentada.
- [ ] A execução usada como evidência foi reproduzida em checkout identificado, com arquivo sanitizado autorizado e SQLite temporário.
- [ ] O inventário externo foi preenchido até onde é possível saber, com donos e data de confirmação.
- [ ] Donos foram avisados antes de qualquer congelamento das colunas `REAL`.
- [ ] O runbook foi revisado com os responsáveis operacionais.
- [ ] O exercício de restauração foi realizado em homologação autorizada e documentado.

Até que esses critérios sejam atendidos, manter o inventário externo e a reconciliação como pendentes. Não habilitar dupla escrita/leitura em produção, não executar migração ou backfill real e não retirar colunas `REAL` com base apenas em CI verde ou nesta documentação.
