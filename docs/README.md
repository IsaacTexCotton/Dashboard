# Índice da documentação

## Produto e experiência do analista

- [Plano de implementação do dashboard orientado ao analista de cobrança](product/PLANO_IMPLEMENTACAO_DASHBOARD_ANALISTA_COBRANCA.md): incrementos do cockpit diário à central de ação, catálogo de métricas, critérios de aceite e gates de dados.
- [Dicionário de indicadores de cobrança](product/DICIONARIO_INDICADORES_COBRANCA.md): fórmulas implementadas, mapeamento JSON/SQLite, granularidade, limites de interpretação e decisões de negócio pendentes.

## Arquitetura e contrato

- [Contrato de dados financeiros](architecture/CONTRATO_DADOS_FINANCEIROS.md): semântica dos campos, totais aditivos e posição histórica de acordos.

## Precisão e migração monetária

- [Política de precisão monetária](monetary/POLITICA_PRECISAO_MONETARIA.md)
- [Inventário de leitores e escritores](monetary/INVENTARIO_LEITORES_ESCRITORES_MONETARIOS.md)
- [Plano de execução da migração](monetary/PLANO_EXECUCAO_MIGRACAO_MONETARIA.md)
- [Preparação da migração](monetary/PREPARACAO_MIGRACAO_MONETARIA.md)
- [Análise de compatibilidade](monetary/ANALISE_COMPATIBILIDADE_MONETARIA.md)
- [Adendo de auditoria estática de 15/10/2026](monetary/ADENDO_AUDITORIA_MIGRACAO_MONETARIA_2026-10-15.md)
- [Reconciliação de evidências e inventário de pendências](monetary/RECONCILIACAO_E_INVENTARIO_PENDENCIAS.md)

Esses documentos registram especificações e evidências em momentos distintos; datas, commits e limitações históricas devem ser interpretados como registros daquela revisão, não como prova automática do estado atual.

## Operação

- [Runbook operacional](operations/RUNBOOK_OPERACIONAL.md): uso seguro de diagnóstico, backup, homologação e recuperação.

## Demonstração

- [Demonstração estática](../web-demo/index.html): interface ilustrativa com dados sintéticos, sem conexão ao CRM ou banco.
- [Configuração da publicação pelo GitHub Pages](../README.md#ver-a-demonstração-sem-instalar-nada).

## Limites

Não há autorização para operações em produção implícita na documentação ou no CI. Testes devem usar SQLite temporário, fixtures sintéticas e nenhum segredo.
