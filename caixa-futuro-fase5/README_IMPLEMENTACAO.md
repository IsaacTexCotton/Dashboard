# CAIXA FUTURO — Fase 5: backup verificável e prontidão operacional

Este pacote consolida as fases anteriores e adiciona criação/verificação de backup SQLite consistente e um runbook operacional para homologação e recuperação. É uma entrega local; não está publicada no GitHub.

## Conteúdo

- `importar.py`: validação do payload e gravação transacional por dia.
- `auditar_resposta.py`: reconciliação de totais aditivos.
- `diagnosticar_banco.py`: diagnóstico somente-leitura do SQLite.
- `validar_integracao_local.py`: fluxo de qualidade de ponta a ponta usando um JSON local e banco temporário.
- `backup_sqlite.py`: cria snapshot SQLite via API de backup, sem sobrescrever artefatos; gera manifesto com hash/tamanho/integridade/contagens e oferece verificação posterior.
- `RUNBOOK_OPERACIONAL.md`: passos de backup, homologação, critérios de entrada em produção e princípios de recuperação.
- `tests/`: testes unitários e integrados.
- `amostra_resposta.json`: dados ilustrativos/fictícios, não carteira real.
- `relatorio_validacao_local_fase5.json`: resultado da última validação executada sobre a amostra fictícia.

## Requisitos

Python 3.10 ou superior. O backup exige um SQLite existente e uma pasta de destino já criada. Não acessa CRM nem exige credenciais.

## Validar tudo localmente

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
python validar_integracao_local.py amostra_resposta.json --relatorio relatorio_validacao_local_fase5.json
```

## Criar e conferir um backup

```bash
mkdir -p backups
python backup_sqlite.py criar ./cobranca.db --destino ./backups/cobranca-antes.db
python backup_sqlite.py verificar ./backups/cobranca-antes.db
```

A ferramenta também cria `cobranca-antes.db.manifest.json`. Ela se recusa a sobrescrever o banco de backup ou o manifesto. A verificação compara nome, tamanho, SHA-256, integridade SQLite e contagens de linhas por tabela com o manifesto. Um manifesto não é assinatura digital; proteja ambos os artefatos com controles de acesso.

## Resultado desta execução

Em 13/10/2026, os **44 testes automatizados passaram** no ambiente local. A validação integrada com a amostra fictícia retornou `PASSED`: 5 fatos, sem duplicação após reimportação, 13 verificações de banco sem `WARN`/`FAIL`, `crm_consultas: 0` e `banco_persistente: false`. Também foram executados testes de criação/verificação de backup, não sobrescrita e detecção de alterações no manifesto/arquivo. Isso demonstra os caminhos cobertos pela suíte, não prova um restore de produção nem valida dados reais do CRM.

## Segurança e limites

- Nenhuma chamada nova ao CRM é feita pelos testes ou pela ferramenta de backup.
- Nenhum banco persistente de produção foi aberto ou alterado durante a validação desta fase.
- O backup é um snapshot técnico; não substitui a revisão de acessos, criptografia em repouso, retenção, e testes de restauração sob procedimento aprovado.
- Valores monetários continuam como SQLite `REAL`; esta fase não introduz migração de escala ou semântica contábil.
- A amostra é sintética; sucesso local não comprova compatibilidade com payload real.
- Antes de produção, ainda exigimos payload real sanitizado/autorizado, decisão de negócio sobre snapshots/precisão, backup verificado e rollback aprovado.
- A tentativa de escrita na integração GitHub continua bloqueada pelo erro `HTTP 403`; esta fase não foi commitada no `main`.

Consulte `RUNBOOK_OPERACIONAL.md` antes de executar comandos contra banco de dados real.
