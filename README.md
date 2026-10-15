# CAIXA FUTURO — Dashboard TexCotton

Ferramentas para importar, auditar e visualizar o consolidado diário de cobrança a partir de payloads do CRM, com armazenamento SQLite e transição monetária controlada.

## Ver a demonstração sem instalar nada

A demonstração estática e interativa fica em [`web-demo/index.html`](web-demo/index.html). Ela usa exclusivamente dados fictícios em JavaScript local; não consulta o CRM, não abre banco de dados e não grava informações.

Para disponibilizá-la por um endereço público, configure uma única vez **Settings → Pages → Build and deployment → Source: GitHub Actions**. O workflow `Publicar demonstração estática` publicará o conteúdo de `web-demo/` nas alterações da `main`. A URL esperada para este repositório é `https://isaactexcotton.github.io/Dashboard/`; ela só ficará ativa depois que o Pages for habilitado e a publicação terminar.

Essa demonstração serve para visualizar a interface, não é uma aplicação conectada ao CRM nem prova de funcionamento em produção.

## Componentes atuais

| Arquivo | Responsabilidade |
|---|---|
| `dashboard_app.py` | Prévia web local; demo sintética em SQLite em memória ou banco existente em modo somente leitura. |
| `importar.py` | Validação do payload e importação por dia em transação SQLite. |
| `auditar_resposta.py` | Reconciliação dos totais aditivos do JSON antes da gravação. |
| `diagnosticar_banco.py` | Diagnóstico do banco, somente leitura. |
| `backup_sqlite.py` | Backup SQLite consistente e manifesto verificável, sem sobrescrita. |
| `backfill_monetario.py` | Planejamento e aplicação explicitamente opt-in do backfill monetário. |
| `escrita_dupla.py` | Gravação atômica de métricas legadas e métricas em centavos. |
| `migrar_schema_monetario.py` | Migração aditiva e verificações de fase/schema. |
| `modelo_monetario.py`, `precisao_monetaria.py` | Contrato de colunas monetárias e conversão decimal exata. |

Os scripts permanecem na raiz por compatibilidade com os imports, testes e comandos existentes. Uma mudança para pacote `src/` será feita somente junto com a atualização e validação de todos os pontos de entrada.

## Documentação

- [Índice da documentação](docs/README.md)
- [Contrato de dados financeiros](docs/architecture/CONTRATO_DADOS_FINANCEIROS.md)
- [Política de precisão monetária](docs/monetary/POLITICA_PRECISAO_MONETARIA.md)
- [Inventário de leitores e escritores monetários](docs/monetary/INVENTARIO_LEITORES_ESCRITORES_MONETARIOS.md)
- [Plano de execução da migração](docs/monetary/PLANO_EXECUCAO_MIGRACAO_MONETARIA.md)
- [Runbook operacional](docs/operations/RUNBOOK_OPERACIONAL.md)
- [Como contribuir e validar alterações](CONTRIBUTING.md)

**Ratificação administrativa/formal não é etapa nem gate deste projeto.** O avanço é determinado por critérios técnicos verificáveis, revisão, testes e evidência operacional.

## Requisitos e execução local

- Python 3.10 ou superior para os scripts e a aplicação local.
- Os scripts utilizam a biblioteca padrão; não há dependências externas de runtime.

Execute na raiz do repositório. A demonstração abaixo usa dados sintéticos e banco SQLite exclusivamente em memória:

```bash
python dashboard_app.py --demo
```

Abra `http://127.0.0.1:8765`. Para inspecionar um banco SQLite existente sem alterá-lo, use `python dashboard_app.py --db caminho/para/cobranca.db`; o arquivo precisa existir e é aberto em modo somente leitura.

## Testes e validações

```bash
python -m unittest discover -s tests -v
python importar.py --arquivo amostra_resposta.json --dry-run
python auditar_resposta.py amostra_resposta.json
python validar_integracao_local.py amostra_resposta.json
```

O CI executa a suíte e as validações do JSON ilustrativo. Os testes usam fixtures e bancos temporários; não chamam o CRM nem comprovam compatibilidade com dados reais.

## Segurança e transição monetária

- Não versionar credenciais, cookies, tokens, payloads de clientes, bancos SQLite reais, backups ou manifestos.
- `DUPLA_ESCRITA` controla a gravação paralela (padrão `0`). A chave legada `DASHBOARD_MONETARIO_DUAL_WRITE` é apenas fallback quando a chave principal não está definida.
- `LEITURA_CENTAVOS` tem padrão `0`; `LEITURA_CENTAVOS=1` exige `DUPLA_ESCRITA=1`. A aplicação também exige fase global conciliada, linhas conciliadas e igualdade integral entre os valores legados e centavos; caso contrário, recusa iniciar nesse modo.
- A existência do código e de testes sintéticos não significa que migração, backfill, dupla escrita ou leitura por centavos estejam habilitados em produção.
- Não executar migração, backfill ou importação contra produção como parte dos testes. Consulte o [runbook operacional](docs/operations/RUNBOOK_OPERACIONAL.md) antes de qualquer operação mutável.

## Organização do repositório

```text
.github/workflows/       CI e publicação da demonstração estática
archive/                 pacote legado e ZIPs históricos, não executáveis como fonte atual
docs/                    contrato, precisão monetária, análises e runbook
tests/                   testes e fixtures sintéticas
web-demo/                prévia estática, independente de Python/CRM/banco
*.py                     scripts atuais e módulos monetários
```

Veja também o [histórico de reorganização e limites do pacote legado](archive/README.md).
