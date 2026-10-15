# Dashboard TexCotton — CAIXA FUTURO

Ferramentas Python para importar, auditar e proteger o consolidado diário do CRM em SQLite.

## Ferramentas

- `importar.py`: audita totais aditivos antes de gravar, valida payloads e grava cada dia em transação atômica; `--dry-run` audita/valida arquivo local sem abrir banco e sem consultar API.
- `auditar_resposta.py`: reconcilia totais aditivos gerais com somas por usuário a partir de JSON local.
- `diagnosticar_banco.py`: verifica estrutura e consistência do SQLite em modo somente leitura.
- `backup_sqlite.py`: cria snapshot consistente, sem sobrescrever backup existente; gera manifesto com tamanho, SHA-256, integridade e contagens de tabela.
- `validar_integracao_local.py`: executa auditoria, dry-run, importação dupla e diagnóstico num SQLite temporário.
- `RUNBOOK_OPERACIONAL.md`: critérios de homologação, backup e recuperação.

## Requisitos

Python 3.10 ou superior; não há dependências externas para executar ferramentas e testes.

## Validar localmente

Na raiz do repositório:

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
python validar_integracao_local.py amostra_resposta.json
```

Os testes usam apenas uma amostra ilustrativa e bancos temporários; não consultam o CRM. O workflow do GitHub Actions executa a suíte e as três validações de arquivo local a cada push em `main` e pull request para `main`.

## Diagnóstico e backup

```bash
python diagnosticar_banco.py ./cobranca.db --json
mkdir -p backups
python backup_sqlite.py criar ./cobranca.db --destino ./backups/cobranca-antes.sqlite3
python backup_sqlite.py verificar ./backups/cobranca-antes.sqlite3
```

O diagnóstico é somente-leitura e exige um banco existente. A pasta de backup deve existir, e os arquivos de backup/manifesta são criados sem sobrescrever arquivos existentes. Consulte o runbook antes de operar sobre banco real.

## Configuração da API

Para importação via API, configure `CRM_URL` e pelo menos uma credencial (`CRM_TOKEN` ou `CRM_COOKIE`) por variáveis de ambiente. `DASHBOARD_DB` define o caminho do SQLite; o padrão é `cobranca.db`. Não grave segredos no código ou no repositório.


## Diretriz de implementação monetária

O projeto não inclui uma etapa de ratificação administrativa/formal como requisito de desenvolvimento. O trabalho segue os contratos técnicos versionados, as regras de negócio fornecidas e critérios verificáveis de código, testes e operação. Não reintroduzir essa ratificação como gate em README, código, issues ou runbook.

A transição de `REAL` para `INTEGER` em centavos é incremental; a existência de testes ou de uma especificação não significa que o corte esteja habilitado. Não executar migração, backfill nem importação real como parte dos testes automatizados.

### Flags monetárias

- `DUPLA_ESCRITA` controla a gravação paralela e tem padrão `0`.
- `LEITURA_CENTAVOS` tem padrão `0`. Se for definida como `1`, o importador recusa a operação até existir um leitor de centavos realmente integrado; ele não pode ignorar a flag e continuar lendo `REAL` silenciosamente.
- `DASHBOARD_MONETARIO_DUAL_WRITE` é aceito apenas como fallback de compatibilidade temporária quando `DUPLA_ESCRITA` não foi definido.
- Ambas as flags aceitam somente `0` ou `1`. `LEITURA_CENTAVOS=1` sem `DUPLA_ESCRITA=1` é configuração inválida.
- A escrita dupla exige um banco já existente com o esquema monetário validado. A configuração por si só não cria esquema e não autoriza operações em produção.


### Fase monetária por linha

- A migração aditiva adiciona as 11 colunas de métricas em centavos e `monetario_fase` em `fatos` e `acordos_posicao`; as linhas existentes recebem `legado`.
- O escritor duplo grava `monetario_fase='dual'` na mesma transação que grava as duas representações.
- A fase `conciliado` é atribuída às linhas somente quando a verificação integral de igualdade REAL→centavos passa e a fase global avança para `backfill_conciliado`.
- A migração instala guardas de fase idempotentes: depois de `backfill_conciliado`, novas linhas não podem cair no padrão `legado` e linhas existentes não podem voltar a essa fase.
- `diagnosticar_banco.py --json` é somente-leitura: NULL em métrica aplicável na fase `legado` é pendência (`WARN`); ausência ou divergência em linhas `dual`/`conciliado` é falha (`FAIL`).
- `auditar_resposta.py` soma e compara dinheiro em centavos inteiros, sem tolerância de R$ 0,01; tokens monetários precisam ser `int`/`Decimal` exatos, com precisão além de duas casas aceita somente quando os dígitos excedentes são zero.
- Testes de migração/backfill usam bancos sintéticos. Nenhuma migração, backfill ou importação em banco real foi executada, e nenhum corte foi habilitado.

## Limites antes de produção

- `amostra_resposta.json` contém dados fictícios; teste local não comprova compatibilidade com todos os dados reais do CRM.
- As colunas legadas `REAL` permanecem preservadas; o caminho `INTEGER` em centavos continua sujeito à implementação e verificação faseadas.
- A semântica histórica dos snapshots de acordo depende de decisão de negócio.
- Homologação com payload real obtido por canal autorizado, validação das regras financeiras, backup/restauração verificados e plano de rollback ensaiado são critérios técnicos antes de produção.
