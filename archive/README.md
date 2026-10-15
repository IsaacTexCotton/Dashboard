# Arquivos históricos

Esta pasta contém artefatos de origem e versões antigas recebidas por upload. Eles foram retirados da raiz para deixar inequívoca a fonte atual do projeto.

- `legacy-fase5-upload/`: pacote da Fase 5 preservado como referência histórica. **Não use os scripts deste diretório como versão atual**; os módulos atuais estão na raiz e os documentos vigentes em `docs/`.
- `source-zips/`: ZIP de uma fase anterior, preservado sem extração na árvore principal.

Os relatórios JSON gerados pela validação local antiga foram excluídos da árvore ativa: são artefatos reproduzíveis, não fontes. O histórico Git ainda preserva o commit do upload original.

Nenhum arquivo deste diretório deve ser importado pelo CI nem usado para operar sobre CRM ou banco de produção.
