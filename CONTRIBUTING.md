# Contribuindo

## Fluxo de alteração

1. Abra uma branch com nome orientado à intenção, por exemplo `fix/validacao-payload`, `docs/atualizar-runbook` ou `chore/reorganizar-repositorio`.
2. Mantenha o diff focado. Não misture refatoração ampla, mudança de regra financeira e alteração de documentação sem necessidade.
3. Abra um pull request para `main`, descreva comportamento afetado, riscos, testes executados e eventuais pendências.
4. Aguarde o workflow `Testes CAIXA FUTURO` e confira o diff final antes do merge.

## Validação local

Python 3.10 ou superior:

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
python validar_integracao_local.py amostra_resposta.json
```

Os comandos devem ser executados a partir da raiz. O `--dry-run` precisa receber um arquivo local e não deve abrir nem criar banco.

## Proteções obrigatórias

- Use somente fixtures sintéticas e bancos em memória/temporários nos testes automatizados.
- Não execute importação, migração, backfill nem scripts de alteração em banco real durante uma alteração de código.
- Não habilite flags operacionais nem altere variáveis do ambiente de produção.
- Nunca comite tokens, cookies, `.env`, payloads reais, bancos, backups ou manifestos de backup.
- Preserve o comportamento fail-closed: configuração incompleta, schema incompatível ou divergência monetária deve bloquear o modo solicitado.
- Não declare produção validada com base em CI ou dados sintéticos.

## Estrutura e documentação

- Scripts ativos ficam na raiz por compatibilidade com os pontos de entrada e testes atuais.
- Especificação/contrato ficam em `docs/architecture/` e `docs/monetary/`; procedimentos operacionais em `docs/operations/`.
- Pacotes antigos e arquivos ZIP de origem ficam em `archive/`, claramente marcados como históricos.
- A demonstração `web-demo/` é estática e usa somente dados fictícios. Não adicione chamadas à API/CRM nem credenciais.
- Ao alterar uma regra monetária, atualize contrato, implementação, testes sintéticos e documentação relevante no mesmo conjunto de mudanças.
