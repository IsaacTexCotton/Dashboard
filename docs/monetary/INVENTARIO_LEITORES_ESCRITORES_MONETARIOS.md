# Inventário de leitores e escritores monetários — estado do repositório

**Data da inspeção:** 15/10/2026. **Base estática:** `main`, antes desta atualização documental. Escopo: código versionado no repositório; não inclui inspeção de produção, hosts, pastas compartilhadas, planilhas ou sistemas externos.

Este documento distingue componentes encontrados no código de consumidores operacionais confirmados. Um caminho de código capaz de ler ou escrever não prova que esteja ativo num ambiente. Da mesma forma, a ausência de um consumidor nesta lista não prova que ele não exista fora do repositório.

## 1. Escritores e componentes mutáveis identificados

| Componente | Papel observado no código | Banco/efeito | Condição e limite |
|---|---|---|---|
| `importar.py` | Importa uma resposta JSON local ou consulta a API quando invocado nesse modo | Escritor principal de `usuarios`, `fatos`, `acordos_posicao` e `importacoes`; reprocessa o dia substituindo os fatos desse dia e registrando lote | `--arquivo` com `--dry-run` não abre banco. `--arquivo` sem `--dry-run` grava no banco configurado por `DASHBOARD_DB` ou, se ausente, `cobranca.db`. O modo API usa credenciais e é fora dos testes recomendados |
| `escrita_dupla.py` | Implementa a gravação transacional integrada pelo importador | Escreve colunas legadas `REAL`, colunas semânticas `INTEGER` em centavos e estado de linha | Só é chamada no caminho de dupla escrita; requer schema monetário compatível. Código presente não prova que esteja habilitada em qualquer ambiente |
| `backfill_monetario.py` | Lê e prepara a conversão do histórico e possui caminho de aplicação | Capaz de atualizar valores monetários históricos e marcador de fase nas tabelas `fatos` e `acordos_posicao` quando explicitamente executado para aplicar | Operação mutável e controlada; nenhuma aplicação em banco operacional foi executada nesta inspeção |
| `migrar_schema_monetario.py` | Migração aditiva, transições de fase e criação de triggers | Altera schema e estado de migração; pode atualizar marcadores de fase | Não é importação de fatos. DDL/transições só devem ocorrer após os gates documentados e em ambiente autorizado |
| `backup_sqlite.py` | Cria cópia consistente e manifesto, verifica backup | Lê origem em modo somente-leitura e cria um arquivo de backup/manifesto separado | O script é capaz de escrever arquivos de backup; existência do código não comprova backup/restauração operacional |
| `validar_integracao_local.py` | Orquestra auditoria, dry-run e duas importações para validar idempotência | Cria banco temporário descartável, executa gravações apenas nele e consulta seus contadores em leitura | Remove credenciais do CRM do ambiente filho e reporta `crm_consultas=0`; o relatório de validação pode ser gravado no caminho local escolhido via `--relatorio` |

## 2. Leitores, auditorias e consumidores de dados identificados

| Componente | Relação com os dados | Proteções/limites observados |
|---|---|---|
| `dashboard_app.py` | Dashboard local lê `usuarios`, `fatos`, `acordos_posicao` e `importacoes` do SQLite existente | O modo `--db` abre conexão URI `mode=ro` e configura `PRAGMA query_only=ON`; não executa importação, migração nem backfill. O modo `--demo` usa SQLite exclusivamente em memória. A leitura por centavos é suportada sob guardas explícitas de flags, schema, fase e conciliação |
| `diagnosticar_banco.py` | Lê schema, integridade, contagens e consistência monetária | Abre origem em modo somente-leitura; não grava dados de negócio |
| `auditar_resposta.py` | Lê um arquivo JSON e reconcilia totais aditivos com somas de `porUsuario` | Não abre SQLite nem chama CRM; `contatosUnicosTotal` é não aditivo e não é comparado à soma por usuário |
| `validar_integracao_local.py` | Consulta contagens/tipos do banco temporário depois da importação e reimportação de teste | Não consulta o banco operacional; o banco é criado sob diretório temporário e o acesso de leitura final é `mode=ro` |
| `backup_sqlite.py` | Lê a origem e valida cópia | A leitura da origem é somente-leitura; a escrita é confinada ao arquivo de backup escolhido |
| `backfill_monetario.py` | Leitura do legado para planejar/converter valores antes de atualizar | Não é leitor operacional do dashboard; sua execução em modo de aplicação é mutável e exige controle específico |
| `web-demo/index.html` | Demonstração web estática consome o fixture JSON fictício incorporado | Não consulta CRM nem abre SQLite |
| `.github/workflows/testes.yml` | Executa testes e validações dos fixtures versionados | Usa CI e bancos temporários dos testes; não comprova estado de hosts nem compatibilidade com todos os consumidores |
| `.github/workflows/publicar-demo.yml` | Publica conteúdo de `web-demo/` | Publicação estática, sem leitura do banco SQLite operacional |

## 3. Código legado arquivado

`archive/legacy-fase5-upload/` contém cópias históricas de alguns scripts e testes. Eles não aparecem como caminho ativo nos workflows atuais e não foram classificados como componentes de runtime atual. A inspeção estática não prova que cópias arquivadas nunca sejam executadas manualmente ou tenham sido copiadas para hosts externos; esse ponto só pode ser resolvido pela confirmação operacional.

## 4. Flags e estado da transição monetária

| Item | Comportamento observável no código versionado | O que permanece desconhecido |
|---|---|---|
| Dupla escrita | `importar.py` reconhece `DUPLA_ESCRITA` como chave principal (padrão `0`) e `DASHBOARD_MONETARIO_DUAL_WRITE` como fallback temporário quando a chave principal não está definida | Valores efetivos em qualquer host/ambiente; não foram inspecionados |
| Leitura por centavos no dashboard | `dashboard_app.py` suporta `LEITURA_CENTAVOS` sob guardas explícitas: configuração consistente, fase global `backfill_conciliado`, linhas conciliadas e igualdade integral entre legado e centavos | Não há evidência nesta inspeção de que seja usada em produção ou de que flags estejam ativadas |
| Schema, backfill e triggers | Código e testes sintéticos existem, com validação por fase e abortos para schema incompatível | Nenhuma migração/backfill foi executada contra banco operacional; CI não equivale a homologação |
| Compatibilidade com REAL | Colunas legadas continuam presentes e são mantidas no caminho de dupla escrita | Consumidores dependentes de colunas `REAL`, donos, frequências e planos de migração externos ainda não foram confirmados |

**Correção de estado documental:** linhas anteriores deste inventário que afirmavam que não havia leitor de centavos no dashboard, ou que `DUPLA_ESCRITA` ainda não era a chave principal do importador, não descrevem o código atual e são substituídas por esta tabela.

## 5. Consumidores externos — pendência operacional

Não foram identificados nesta inspeção estática consumidores externos confirmados. Isso não significa que não existam. Permanecem por verificar:

- tarefas agendadas, serviços e processos que abram o arquivo SQLite;
- planilhas, conexões ODBC/Power Query, consultas salvas e arquivos vinculados;
- BI, painéis alternativos, exportações e outras extrações;
- scripts avulsos, pastas compartilhadas e cópias de backups usadas como fonte de consulta;
- pessoas de Cobrança, Controladoria e TI que abram o banco diretamente;
- outros repositórios, hosts e sistemas.

A [Issue #17 — inventário de consumidores e rollback](https://github.com/IsaacTexCotton/Dashboard/issues/17) permanece **aberta e bloqueadora**. Ela exige donos, evidência/data de confirmação, comunicação da data de congelamento do `REAL`, revisão de runbook com operadores e exercício autorizado de restauração em homologação. Esse conjunto não pode ser concluído por inspeção de código sozinha.

## 6. Controles de transição

- Não ativar dupla escrita ou leitura por centavos em produção com base neste documento ou em CI verde.
- Não executar migração, backfill ou gravação contra banco operacional como parte desta inspeção.
- Manter colunas `REAL` enquanto a dependência de consumidores conhecidos não estiver resolvida e os gates não estiverem atendidos.
- Testar falhas, atomicidade e rollback em SQLite temporário; para homologação, usar canal autorizado e evidência sanitizada.
- Atualizar este inventário quando houver confirmação operacional de consumidores/donos; não preencher lacunas por suposição.
