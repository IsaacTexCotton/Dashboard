# Dashboard TexCotton — CAIXA FUTURO

Ferramentas Python para importar, auditar e proteger o consolidado diário do CRM em SQLite.

## Ferramentas

- `importar.py`: valida payloads e grava cada dia em transação atômica; o modo `--dry-run` valida arquivo local sem abrir banco e sem consultar API.
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

## Limites antes de produção

- `amostra_resposta.json` contém dados fictícios; aprovação local não comprova compatibilidade com todos os dados reais do CRM.
- Valores financeiros seguem SQLite `REAL`; validar precisão contábil antes de qualquer migração.
- A semântica histórica dos snapshots de acordo depende de decisão de negócio.
- Homologação com payload real sanitizado/autorizado, aprovação financeira, backup verificado e plano de rollback são pré-requisitos para produção.
