# CAIXA FUTURO — Runbook operacional

## Propósito e limites

Este roteiro protege o SQLite antes de testes ou reprocessamentos. Não autoriza, por si só, consulta ao CRM, importação para produção, alteração do esquema ou restauração de banco de produção. Antes de qualquer operação real, obtenha um payload sanitizado/autorizado e aprovação do responsável financeiro.

## 1. Preparação

1. Confirme qual caminho a aplicação utiliza e quais processos escrevem nele (`DASHBOARD_DB`). Não adivinhe o caminho.
2. Confira o espaço livre e escolha uma pasta de backup com acesso restrito. Não versione banco, backup, manifesto ou payload real no Git.
3. Crie a pasta de backup, se ausente, e execute o diagnóstico inicial:

```bash
mkdir -p backups
python diagnosticar_banco.py ./cobranca.db --json
```

Se o diagnóstico retornar `FAIL`, pare e investigue. Examine também os `WARN`; eles não significam aprovação automática.

## 2. Criar e verificar o backup

Use nomes novos a cada execução. O arquivo e o manifesto são criados de forma exclusiva; a ferramenta recusa sobrescrever qualquer um.

```bash
python backup_sqlite.py criar ./cobranca.db --destino ./backups/cobranca-pre-homologacao-AAAA-MM-DD.sqlite3
python backup_sqlite.py verificar ./backups/cobranca-pre-homologacao-AAAA-MM-DD.sqlite3
```

Prossiga apenas se o segundo comando terminar com código `0` e `status: OK`. Preserve juntos o arquivo e o respectivo `.manifest.json`. O manifesto registra tamanho, SHA-256, `integrity_check`, `user_version` e contagens por tabela.

A criação usa a API online backup do SQLite, que produz um snapshot consistente mesmo com WAL. Evite copiar apenas o arquivo `.db` enquanto houver escritores ativos.

## 3. Homologar sem CRM

Use uma resposta JSON sanitizada e autorizada; nenhum dos passos abaixo chama o CRM:

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo resposta_sanitizada.json --dry-run
python auditar_resposta.py resposta_sanitizada.json
python validar_integracao_local.py resposta_sanitizada.json --relatorio relatorio_homologacao.json
```

Confirme que os testes passam, a auditoria não aponta divergências bloqueantes e o relatório integrado retorna `PASSED`. Revise o payload e o relatório para garantir que não contêm dados pessoais desnecessários.

Atenção: `--arquivo` sem `--dry-run` grava no SQLite definido por `DASHBOARD_DB`. Use um banco descartável de homologação e confira o caminho antes de executar.

O sucesso local comprova apenas os cenários cobertos pelo JSON e pelos testes. Não demonstra sozinho a semântica contábil ou a compatibilidade com todos os payloads do CRM.

## 4. Critérios antes de produção

- [ ] Resposta real sanitizada e autorizada, com período identificado.
- [ ] Totais aditivos reconciliados; divergências explicadas e aprovadas.
- [ ] Datas, campos obrigatórios, nulos e valores extremos revisados.
- [ ] Responsável financeiro aprovou o significado das métricas e snapshots, e os casos de renegociação, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais foram avaliados para a regra `valor = pagos + pendente`.
- [ ] A política aprovada está versionada em `POLITICA_PRECISAO_MONETARIA.md`; sua aplicabilidade ao CAIXA FUTURO foi confirmada apesar do escopo do texto declarar Contas a Pagar.
- [ ] TI/Contabilidade confirmou se o ERP e o módulo de títulos usam *half-up* para juros, multas e descontos.
- [ ] Antes de alterar regras monetárias, foram resolvidos os conflitos de escopo/sinais, e há testes para arredondamento fronteiriço, somas sem deriva, importação com 3/4/6 casas decimais, valores legados `REAL` problemáticos e igualdade de rateio/parcelamento.
- [ ] Comparação por igualdade exata em centavos e tratamento de entrada decimal foram implementados e testados somente após a confirmação de escopo.
- [ ] Qualquer migração de `REAL` possui inventário de leitores/escritores, análise de compatibilidade, backup verificado, colunas paralelas, script idempotente, dupla escrita/conciliação, aprovação de corte e rollback testado.
- [ ] O campo `timestamp` do JSON é preservado exatamente como recebido; ausência/vazio bloqueia a importação, sem fallback para relógio local nem inferência/conversão de fuso.
- [ ] `main` exige o workflow de CI como verificação obrigatória.
- [ ] Backup recente criado e verificado, com manifesto íntegro.
- [ ] Banco de homologação diagnosticado após importação e reimportação.
- [ ] Plano de rollback e janela de manutenção acordados.
- [ ] Código e testes revisados no repositório autorizado.

Se qualquer critério não for atendido, não promova a rotina para produção.

## 5. Recuperação: princípios seguros

Não há restauração automática nesta ferramenta: substituir um banco usado pela aplicação pode perder escritas recentes ou deixar conexões ativas.

1. Pare os processos que escrevem no banco e confirme que não existem conexões ativas.
2. Identifique backup e manifesto; execute `backup_sqlite.py verificar <backup>` e exija `status: OK`.
3. Preserve o banco atual para investigação, incluindo `-wal` e `-shm` se existirem. Não descarte o arquivo que falhou.
4. Copie o backup verificado para um arquivo temporário no mesmo volume do destino e rode `diagnosticar_banco.py` nele.
5. Só com aprovação do responsável, faça a troca durante uma janela de manutenção, mantendo o banco anterior preservado.
6. Reabra a aplicação, valide leituras críticas e registre aprovador, horário, backup, SHA-256 e resultado.

Não renomeie ou restaure arquivos enquanto a aplicação estiver escrevendo. Se houver dúvida, interrompa e preserve os artefatos para análise.

## 6. Proteção da informação

- Nunca coloque `CRM_TOKEN`, `CRM_COOKIE`, dados de clientes, payload real ou backups em relatórios compartilhados ou no Git.
- Armazene backups e manifestos com acesso restrito e política de retenção definida.
- SHA-256 detecta mudanças em relação ao manifesto, mas não é assinatura digital: quem pode substituir ambos pode falsificar a comparação. Proteja os dois artefatos juntos.
