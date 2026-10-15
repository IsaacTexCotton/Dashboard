# CAIXA FUTURO — Runbook operacional

## Propósito e limites

Este roteiro protege o SQLite antes de testes ou reprocessamentos. Os comandos abaixo não executam sozinhos uma migração. Use somente payload sanitizado obtido por canal autorizado e siga as regras de acesso da empresa; confirme o caminho do banco e o escopo da operação antes de qualquer etapa mutável.

## 1. Preparação

1. Confirme qual caminho a aplicação utiliza e quais processos escrevem nele (`DASHBOARD_DB`). Não adivinhe o caminho.
2. Confira o espaço livre e escolha uma pasta de backup com acesso restrito. Não versione banco, backup, manifesto ou payload real no Git.
3. Crie a pasta de backup, se ausente, e execute o diagnóstico inicial:

```bash
mkdir -p backups
python diagnosticar_banco.py ./cobranca.db --json
```

Se o diagnóstico retornar `FAIL`, pare e investigue. Examine e registre os `WARN`; não prossiga enquanto seu impacto não estiver compreendido.

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
- [ ] Totais aditivos reconciliados; cada divergência foi classificada, explicada e registrada com evidência.
- [ ] Datas, campos obrigatórios, nulos e valores extremos revisados.
- [ ] Responsável financeiro aprovou o significado das métricas e snapshots, e os casos de renegociação, descontos, cancelamentos, parcelas não vencidas e pagamentos parciais foram avaliados para a regra `valor = pagos + pendente`.
- [ ] A política e o contrato estão versionados e consistentes com as regras implementadas; o escopo identifica o dashboard de Cobrança em Contas a Pagar/Financeiro.
- [ ] TI/Contabilidade confirmou se o ERP e o módulo de títulos usam *half-up* para juros, multas e descontos.
- [ ] Antes de alterar regras monetárias, foram resolvidos os conflitos de sinal por campo e implementados testes para arredondamento fronteiriço, somas sem deriva, importação com 3/4/6 casas decimais, valores legados `REAL` problemáticos e igualdade de rateio/parcelamento.
- [ ] Parsing decimal sem `float`, armazenamento de novos valores em centavos e comparação exata foram implementados e testados; a tolerância monetária não é usada como substituto de conversão exata.
- [ ] Implementação de cobrança respeita as regras da política: juros simples `pro rata die`, multa aplicada uma vez, boleto/custas importados como valor de origem, pagamento confirmado separado de pagamento informado/pendente de baixa.
- [ ] Qualquer migração de `REAL` possui inventário de leitores/escritores, análise de compatibilidade, backup/restauração verificados, colunas paralelas, script idempotente, dupla escrita/conciliação e rollback testado.
- [ ] O campo `timestamp` do JSON é preservado exatamente como recebido; ausência/vazio bloqueia a importação, sem fallback para relógio local nem inferência/conversão de fuso.
- [ ] `main` exige o workflow de CI como verificação obrigatória.
- [ ] Backup recente criado e verificado, com manifesto íntegro.
- [ ] Banco de homologação diagnosticado após importação e reimportação.
- [ ] Plano de rollback e janela de manutenção acordados.
- [ ] Código e testes revisados no repositório autorizado.

Se qualquer critério não for atendido, não promova a rotina para produção.

### Gate específico para a transição REAL/INTEGER (contrato em revisão)

Estado de referência: Issues [#4](https://github.com/IsaacTexCotton/Dashboard/issues/4), [#5](https://github.com/IsaacTexCotton/Dashboard/issues/5) e [#17](https://github.com/IsaacTexCotton/Dashboard/issues/17). Este trecho documenta pré-requisitos técnicos e operacionais; não autoriza ativar flags, executar migração ou alterar dados.

- [ ] Issue #5: nomes semânticos, sinais, `monetario_fase`, nulabilidade e regra de entrada decimal definidos e cobertos por verificação técnica.
- [ ] Issue #4: contrato revisado tecnicamente; o diagnóstico de igualdade REAL→centavos e a configuração de leitura/dupla escrita passaram por revisão e testes. A comparação exata e a trava das flags têm testes sintéticos; a prévia local `dashboard_app.py` possui leitura por centavos com bloqueio fail-closed, mas a presença desse código não demonstra uso operacional, habilitação de flags ou corte de leitura em produção.
- [ ] Issue #17 concluída: consumidores externos registrados, donos avisados, runbook revisado com os operadores e exercício de restauração em homologação autorizado documentado.
- [ ] Testes de reimportação dupla revisados/integrados; CI verde no HEAD exato da versão candidata.
- [ ] Backup criado e verificado antes de qualquer ensaio mutável em homologação.

**Atenção às chaves:** o código versionado reconhece `DUPLA_ESCRITA` como chave principal (padrão `0`) e `DASHBOARD_MONETARIO_DUAL_WRITE` como fallback temporário quando a chave principal não foi definida. `LEITURA_CENTAVOS` tem padrão `0` e exige explicitamente `DUPLA_ESCRITA=1`; sem isso, a configuração é inválida. A prévia `dashboard_app.py` recusa iniciar em centavos a menos que a fase global esteja `backfill_conciliado`, todas as linhas monetárias estejam `conciliado` e a reconciliação REAL→centavos seja integral. O código não foi validado contra as variáveis reais do host. Não ative qualquer chave em produção.

Quando a leitura por centavos estiver autorizada operacionalmente, o rollback primário definido é desligar `LEITURA_CENTAVOS`, retornando a leitura ao `REAL` preservado; restaurar o backup verificado é a alternativa secundária. A escrita `REAL` permanece durante a dupla escrita e por pelo menos 90 dias corridos após o corte de leitura. Se um consumidor desconhecido for descoberto, reinicie a contagem dos 90 dias. Nenhuma retirada de `REAL` é autorizada por este runbook enquanto os gates estiverem abertos.

## 5. Recuperação: princípios seguros

Não há restauração automática nesta ferramenta: substituir um banco usado pela aplicação pode perder escritas recentes ou deixar conexões ativas.

1. Pare os processos que escrevem no banco e confirme que não existem conexões ativas.
2. Identifique backup e manifesto; execute `backup_sqlite.py verificar <backup>` e exija `status: OK`.
3. Preserve o banco atual para investigação, incluindo `-wal` e `-shm` se existirem. Não descarte o arquivo que falhou.
4. Copie o backup verificado para um arquivo temporário no mesmo volume do destino e rode `diagnosticar_banco.py` nele.
5. Faça a troca somente após concluir os critérios técnicos, na janela de manutenção registrada, preservando o banco anterior e o responsável pela execução.
6. Reabra a aplicação, valide leituras críticas e registre operador, horário, backup, SHA-256, critérios verificados e resultado.

Não renomeie ou restaure arquivos enquanto a aplicação estiver escrevendo. Se houver dúvida, interrompa e preserve os artefatos para análise.

## 6. Proteção da informação

- Nunca coloque `CRM_TOKEN`, `CRM_COOKIE`, dados de clientes, payload real ou backups em relatórios compartilhados ou no Git.
- Armazene backups e manifestos com acesso restrito e política de retenção definida.
- SHA-256 detecta mudanças em relação ao manifesto, mas não é assinatura digital: quem pode substituir ambos pode falsificar a comparação. Proteja os dois artefatos juntos.
