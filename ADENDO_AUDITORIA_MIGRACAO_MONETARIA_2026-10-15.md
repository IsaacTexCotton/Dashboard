# Adendo de auditoria estática — migração monetária

**Data da revisão:** 15/10/2026  
**Base analisada:** `main`, commit `acbb308ee732df54d819da4fc53cf39c4dc4119d`  
**Natureza:** registro documental de inspeção estática e de resultados locais reportados pelo operador. Não altera o comportamento da aplicação nem autoriza operações em produção.

## 1. Evidência do CI da base

A execução `Testes CAIXA FUTURO` **#38610782121** terminou em `success` no evento de `push` da `main`, no mesmo SHA `acbb308ee732df54d819da4fc53cf39c4dc4119d`.

Isso confirma que o workflow configurado passou nessa revisão da `main`. Não significa que o JSON sanitizado local tenha sido executado no CI, nem valida o backfill ou uma migração em banco real.

Evidência: https://github.com/IsaacTexCotton/Dashboard/actions/runs/38610782121

## 2. Comparação estática: pacote de Fase 1 e importador atual

A listagem local reportada para `caixa-futuro-fase1.zip` contém `README_IMPLEMENTACAO.md`, `tests/test_importar.py`, `amostra_resposta.json`, `importar.py` e `.gitignore`. Não foram listados arquivos de interface, gráficos ou relatórios nesse pacote. Isso não prova que não existam consumidores externos ou noutros repositórios.

A comparação estática entre o `importar.py` do pacote e o `importar.py` atual mostrou:

- O importador atual importa as funções de preparação/gravação de `escrita_dupla.py` e a validação de schema de `migrar_schema_monetario.py`.
- O código atual contém o seletor `DASHBOARD_MONETARIO_DUAL_WRITE`, cujo padrão no código é `0`. Esse padrão não comprova o valor configurado no ambiente de produção.
- O caminho legado e o `SCHEMA` ainda contêm colunas monetárias SQLite declaradas como `REAL`. A presença das funções de escrita dupla não demonstra que elas estejam habilitadas em produção.
- O caminho de escrita dupla requer schema já migrado/validado; não deve ser ativado antes dos gates técnicos e operacionais.

A inspeção foi estática; nenhum importador foi executado contra CRM ou banco persistente.

## 3. Pré-validação local de JSON reportada pelo operador

O operador informou que um arquivo sanitizado, mantido fora do repositório, passou por uma ferramenta HTML local com os seguintes resultados não sensíveis:

- Estrutura JSON válida e período diário compatível.
- Pseudônimos conhecidos sem problemas reportados.
- Doze verificações de totais aditivos marcadas como `OK`.
- `contatosUnicosTotal` classificado como `NÃO ADITIVO`, pois uma pessoa pode aparecer em mais de uma carteira.
- Nenhuma falha de precisão ou de estrutura foi reportada pelo pré-validador.

**Classificação da evidência:** pré-validação local reportada pelo operador, não execução independente desta revisão, não dry-run oficial Python e não teste de CI com esse arquivo. O JSON e seus valores financeiros não foram anexados ao repositório.

### Diferença de contagens a reconciliar

O relatório local mais recente informado lista 5 registros em depósitos, 5 em acordos, 3 em promessas e 5 em contatos. Isso totaliza 18 itens `porUsuario` entre os quatro grupos. Um registro anterior em `CONTRATO_DADOS_FINANCEIROS.md` menciona 17 fatos para outra validação. Antes de consolidar evidência de homologação, identificar se os registros se referem a payloads diferentes ou a critérios de contagem distintos. Não afirmar que são o mesmo payload sem comparar identidade/hash em ambiente autorizado; não inserir o hash do arquivo financeiro neste repositório.

## 4. Inventário conhecido e lacunas

| Componente | Relação com dados monetários | Situação |
|---|---|---|
| `importar.py` | Valida o JSON e grava os registros; conserva o caminho legado `REAL` | Escritor conhecido |
| `escrita_dupla.py` | Grava colunas legadas e campos inteiros em centavos na mesma transação | Código presente; ativação de produção não comprovada |
| `migrar_schema_monetario.py` | Adiciona/valida o schema de destino | Operação real não autorizada por este adendo |
| `backfill_monetario.py` | Lê valores históricos e prepara valores em centavos | Backfill real não executado |
| `diagnosticar_banco.py` | Lê o SQLite para diagnóstico | Caminho do banco operacional não identificado nesta revisão |
| `backup_sqlite.py` | Faz/verifica backup SQLite | Backup/restauração operacional não comprovados nesta revisão |
| `caixa-futuro-fase1.zip` | Pacote legado listado com README, importador, teste e amostra | Nenhuma UI/relatório foi identificada no conteúdo listado |
| Consumidores fora do repositório | BI, relatórios, consultas salvas, exportações, jobs ou integrações externas | **Não verificados; inventário continua não exaustivo** |

## 5. Critérios de acompanhamento do projeto

O repositório acompanha a especificação técnica, os testes e as evidências de execução. O estado de cada fase deve ser descrito por critérios objetivos observados, sem inferir execução a partir de texto documental ou de CI verde.

## 6. Próximos gates — ainda obrigatórios

1. Reconciliar a diferença de contagem entre as evidências dos payloads, sem compartilhar ou versionar dados financeiros.
2. Completar a matriz de leitores/escritores, incluindo consumidores fora do pacote/repositório.
3. Confirmar configuração do processo operacional e caminho do banco com seu responsável; variáveis da sessão local não provam configuração em produção.
4. Em ambiente autorizado com Python, executar dry-run oficial e validação integrada para a amostra sanitizada aprovada, mantendo o arquivo fora do Git.
5. Antes de qualquer operação em banco real: concluir backup/restauração, inventário e conciliação, CI, plano de rollback e janela operacional; confirmar que a operação está dentro das permissões e procedimentos da organização.

**Estado final desta revisão:** inventário estático parcialmente ampliado; nenhuma operação de produção realizada; DDL, backfill, escrita dupla, mudança de leitura e remoção de colunas `REAL` não foram executados.
