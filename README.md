# Dashboard TexCotton — CAIXA FUTURO

Projeto local para importar e auditar o consolidado diário do CRM, com persistência SQLite.

## Ferramentas

- `importar.py`: importa o consolidado diário, valida estrutura e campos antes de gravar e substitui cada dia dentro de uma transação SQLite.
- `auditar_resposta.py`: reconcilia totais gerais com somas por usuário a partir de um JSON local.
- `diagnosticar_banco.py`: verifica estrutura e consistência de um banco SQLite em modo somente leitura.
- `backup_sqlite.py`: cria e verifica cópias de segurança com manifesto e SHA-256.
- `validar_integracao_local.py`: executa validação integrada local.

## Validar localmente

Requer Python 3.10 ou superior. Na raiz do repositório:

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
```

Para validar uma cópia de banco existente:

```bash
python diagnosticar_banco.py ./cobranca.db --json
python backup_sqlite.py criar ./cobranca.db --destino ./backups/cobranca.sqlite3
python backup_sqlite.py verificar ./backups/cobranca.sqlite3
```

O modo `--dry-run` exige `--arquivo`; não chama o CRM e não abre ou altera banco de dados.

## Configuração da consulta ao CRM

Para importação via API, configure variáveis de ambiente `CRM_URL` e ao menos uma credencial (`CRM_TOKEN` ou `CRM_COOKIE`). O banco é escolhido por `DASHBOARD_DB` (padrão: `cobranca.db`). Não grave credenciais no código nem em arquivos versionados.

## Limites importantes

- `amostra_resposta.json` contém dados fictícios de teste, não evidência de consistência com dados reais.
- Valores financeiros ainda usam SQLite `REAL`; validar precisão contábil antes de uso em produção.
- Snapshots de posição de acordos exigem definição de negócio para interpretação histórica.
- A validação local não substitui homologação com uma resposta real, autorizada e sanitizada.
- Não execute importação ou restauração sobre produção sem backup validado e procedimento de recuperação testado.
