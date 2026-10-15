# Inventário de leitores e escritores monetários — estado do repositório

Data da inspeção: 2026-10-15. Escopo: código versionado em `main`; não inclui inspeção de produção nem sistemas externos.

## Escritores identificados

| Componente | Papel observado | Representações |
|---|---|---|
| `importar.py` | Importador operacional; grava fatos e snapshots diários | caminho legado `REAL`; dupla escrita condicional por `DUPLA_ESCRITA`, com fallback temporário de `DASHBOARD_MONETARIO_DUAL_WRITE` |
| `escrita_dupla.py` | Escrita transacional de fatos/snapshots nas duas representações | `REAL` legado, colunas semânticas `INTEGER` em centavos e fase `dual` por linha |
| `migrar_schema_monetario.py` | Migração aditiva do schema, não escritor de valores de negócio | adiciona colunas/estrutura; não deve ser confundido com importação/backfill |

## Leitores/diagnósticos identificados

| Componente | Papel observado | Limite conhecido |
|---|---|---|
| `diagnosticar_banco.py` | Diagnóstico SQLite somente leitura | compara REAL→centavos por igualdade exata em linhas `dual`/`conciliado`; reporta pendências históricas `legado`; não prova que consumidores externos leiam centavos |
| `validar_integracao_local.py` | Executa fluxo de validação em banco temporário | amostra fictícia, sem CRM nem produção |
| Aplicação/dashboard | Não foi possível identificar com segurança todos os consumidores de leitura por nomes de arquivo óbvios na raiz | exige busca adicional por consultas dinâmicas, dashboards e consumidores externos |

## Consumidores externos e lacunas

O repositório não é evidência suficiente para declarar completo o inventário de consumidores externos, tarefas agendadas, cópias locais ou ferramentas que leem diretamente o SQLite. Não foi acessado o ambiente de produção nem interrogados seus processos. Portanto, o critério de inventário externo permanece **pendente** até que o responsável operacional confirme os consumidores conhecidos.

## Controles para a transição

- A variável `DASHBOARD_MONETARIO_DUAL_WRITE` tem padrão `0` no código; esta inspeção não verifica seu valor em qualquer ambiente.
- Não ativar dupla escrita nem executar migração/backfill como parte desta etapa.
- Manter as colunas `REAL` enquanto houver consumidores que dependam delas.
- Testar rollback em SQLite temporário e exigir CI verde antes de integrar alterações.
- Um teste local/sintético não equivale a homologação com payload real nem validação de produção.


## Adendo de controle — contrato REAL/INTEGER revisado em 15/10/2026

Este adendo registra a diferença entre o comportamento observado no código versionado e o contrato-alvo proposto nas Issues #4 e #5. Não é autorização para ativar flags, executar DDL, backfill ou alterar dados reais.

| Item | Estado observado no código/CI | Estado-alvo ou pendência |
|---|---|---|
| Flag de dupla escrita | `importar.py` lê `DASHBOARD_MONETARIO_DUAL_WRITE`, com padrão `0` | O contrato revisado define `DUPLA_ESCRITA`; a chave-alvo ainda precisa ser implementada/validada |
| Flag de leitura por centavos | `LEITURA_CENTAVOS` é reconhecida pelo importador, mas o leitor de centavos não existe neste repositório | A flag `LEITURA_CENTAVOS=1` é recusada com erro explícito; não há leitura legado silenciosa |
| Diagnóstico de coerência | O diagnóstico compara REAL convertido e centavos por linha | Testes sintéticos cobrem igualdade exata, divergência e pendência `legado` |
| Testes de atomicidade | Há testes sintéticos em memória e, após PR #19, em arquivo temporário com interrupção de processo e leitor concorrente | Continuar sem tratar CI como homologação de produção |
| Reimportação em dupla escrita | PR #20 integrada à `main` com CI verde | Teste sintético substitui fatos em ambas as representações e preserva snapshots por `capturado_em` |
| Consumidores externos | Não verificados por este inventário estático | Issue #17 exige inventário operacional com donos, comunicação, runbook e ensaio de restauração |

## Gate explícito de produção

Não definir variáveis de ambiente para ativar dupla escrita ou leitura por centavos em produção com base neste documento. O valor real das configurações do host não foi inspecionado. O código versionado reconhece `DUPLA_ESCRITA` como chave principal e `DASHBOARD_MONETARIO_DUAL_WRITE` como fallback temporário; isso não significa que qualquer valor do ambiente tenha sido verificado. `LEITURA_CENTAVOS=1` é recusada enquanto não existir um leitor integrado.

O inventário externo permanece **pendente**: a inspeção de código não confirma planilhas, conexões ODBC/Power Query, tarefas agendadas, cópias consultadas por terceiros nem usuários que abrem o SQLite diretamente.
