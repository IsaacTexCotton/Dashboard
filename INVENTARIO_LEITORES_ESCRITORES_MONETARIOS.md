# Inventário de leitores e escritores monetários — estado do repositório

Data da inspeção: 2026-10-15. Escopo: código versionado em `main`; não inclui inspeção de produção nem sistemas externos.

## Escritores identificados

| Componente | Papel observado | Representações |
|---|---|---|
| `importar.py` | Importador operacional; grava fatos e snapshots diários | caminho legado `REAL`; caminho de dupla escrita condicional pela variável `DASHBOARD_MONETARIO_DUAL_WRITE` |
| `escrita_dupla.py` | Preparação e gravação transacional do protótipo de dupla escrita | `REAL` legado e colunas semânticas `INTEGER` em centavos |
| `migrar_schema_monetario.py` | Migração aditiva do schema, não escritor de valores de negócio | adiciona colunas/estrutura; não deve ser confundido com importação/backfill |

## Leitores/diagnósticos identificados

| Componente | Papel observado | Limite conhecido |
|---|---|---|
| `diagnosticar_banco.py` | Diagnóstico SQLite somente leitura | lista/valida o contrato legado; não prova que consumidores externos leiam centavos |
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
