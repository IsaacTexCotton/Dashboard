# CAIXA FUTURO — Runbook operacional (homologação e recuperação)

## Propósito e limites

Este roteiro protege o SQLite antes de testes ou reprocessamentos. Ele não autoriza, por si só, consultar o CRM, importar para produção, alterar o esquema ou recuperar o banco de produção. Antes de qualquer operação real, obtenha um payload sanitizado/autorizado, liberação para escrita no repositório e aprovação do responsável pelo processo financeiro.

## 1. Preparação

1. Confirme qual caminho é o banco efetivamente usado pela aplicação e qual processo pode escrever nele (`DASHBOARD_DB`). Não adivinhe o caminho.
2. Confira espaço livre e escolha uma pasta de backup com acesso restrito. Não comite banco, backup, manifesto ou payload real no Git.
3. Crie a pasta de backup se ela ainda não existir. O comando abaixo deliberadamente não cria diretórios nem sobrescreve arquivos.

```bash
mkdir -p backups
python diagnosticar_banco.py ./cobranca.db --json
```

Se o diagnóstico retornar `FAIL`, pare e investigue antes de qualquer reprocessamento. Examine `WARN` em vez de tratá-lo como aprovação.

## 2. Criar e verificar backup

Use um nome novo para cada execução. O arquivo e o manifesto são criados de forma exclusiva; se qualquer um já existir, a ferramenta se recusa a sobrescrever.

```bash
python backup_sqlite.py criar ./cobranca.db \
  --destino ./backups/cobranca-pre-homologacao-AAAA-MM-DD.sqlite3

python backup_sqlite.py verificar \
  ./backups/cobranca-pre-homologacao-AAAA-MM-DD.sqlite3
```

Só prossiga se o comando de verificação terminar com código de saída `0` e `status: OK`. Preserve lado a lado o arquivo `.sqlite3` e o arquivo `.sqlite3.manifest.json`. O manifesto inclui tamanho, SHA-256, `PRAGMA integrity_check`, `user_version` e contagem por tabela.

A criação usa a API de backup do SQLite, que obtém um snapshot consistente mesmo quando o arquivo usa WAL. Não copie apenas o arquivo `.db` com um comando de sistema enquanto houver escritores ativos.

## 3. Homologar sem CRM de produção

1. Trabalhe numa pasta/cópia de teste e use somente uma resposta JSON sanitizada/autorizada.
2. Execute os testes automatizados:

```bash
python -m unittest discover -s tests -v
```

3. Valide a resposta e os totais aditivos:

```bash
python importar.py --arquivo resposta_sanitizada.json --dry-run
python auditar_resposta.py resposta_sanitizada.json
python validar_integracao_local.py resposta_sanitizada.json --relatorio relatorio_homologacao.json
```

4. Confirme que o relatório integrado retorna `PASSED`, que a auditoria financeira não tem divergências bloqueantes e que nenhuma informação pessoal permaneceu no payload/relatório.
5. Faça o teste de persistência apenas com `DASHBOARD_DB` apontado para um banco de homologação descartável. Não use `--arquivo` sem `--dry-run` enquanto `DASHBOARD_DB` ainda apontar para o banco real: `--arquivo` grava.

O teste local cobre o contrato representado pelo JSON fornecido, não comprova sozinho a semântica contábil nem compatibilidade com todos os casos do CRM.

## 4. Critérios mínimos antes de operar em produção

- [ ] Resposta do CRM real sanitizada e autorizada, com seu período identificado.
- [ ] Totais aditivos reconciliados; qualquer divergência explicada e aprovada.
- [ ] Campos obrigatórios, datas, nulos e valores extremos revistos.
- [ ] Responsável financeiro aprovou o significado das métricas, os snapshots de acordo e o tratamento de renegociação/cancelamento/pagamento parcial.
- [ ] Política de precisão monetária aprovada; nenhuma migração de `REAL` feita implicitamente.
- [ ] Backup recém-criado e verificado, com manifesto íntegro.
- [ ] Banco de homologação diagnosticado após importação e reimportação.
- [ ] Plano de rollback e janela de manutenção acordados.
- [ ] Código publicado com revisão do diff e testes executados no repositório autorizado.

Se qualquer critério não for atendido, não promova a execução para produção.

## 5. Recuperação — princípios seguros

Não existe restauração automática neste pacote porque trocar um banco usado por uma aplicação pode perder escritas recentes ou deixar processos com conexões abertas.

1. Interrompa todos os processos que escrevem no banco e confirme que não existem conexões ativas.
2. Identifique o backup e seu manifesto; rode `backup_sqlite.py verificar <backup>` e exija `status: OK`.
3. Preserve o estado atual para investigação, junto de arquivos laterais SQLite se existirem (`-wal` e `-shm`); não descarte o banco que falhou.
4. Copie o backup verificado para um arquivo temporário **no mesmo volume** do destino, rode `diagnosticar_banco.py` nesse arquivo e examine todos os `WARN`/`FAIL`.
5. Somente com autorização do responsável, faça a troca durante a janela de manutenção, mantendo o banco anterior preservado. Reabra a aplicação e valide leituras críticas antes de retomar a escrita.
6. Registre quem aprovou, horário, backup utilizado, SHA-256, diagnósticos e resultado.

Não renomeie/restaure arquivos enquanto a aplicação estiver gravando. Em caso de dúvida, interrompa a recuperação e preserve os artefatos para análise.

## 6. Proteção de informação

- Nunca inclua `CRM_TOKEN`, `CRM_COOKIE`, dados de clientes, payload real ou backups no relatório compartilhado ou no Git.
- Guarde backups e manifestos em armazenamento com acesso restrito e política de retenção definida.
- O SHA-256 detecta mudanças acidentais em relação ao manifesto, mas não é assinatura digital: quem consegue substituir ambos pode falsificar a comparação. Proteja o arquivo e seu manifesto juntos.
