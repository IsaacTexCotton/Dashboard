# Fixtures fictícias de respostas por data

Esta pasta contém **14 payloads integralmente sintéticos**, um para cada dia de 1 a 14 de outubro de 2026. Os arquivos reproduzem a estrutura esperada pelo importador (success, data, grupos por usuário, totais agregados e timestamp) para testar validação, reconciliação e persistência por dia.

- Cada arquivo tem inicio e fim iguais à data no nome.
- As quantidades de linhas variam entre as datas para exercitar volumes diferentes.
- O fixture de **2026-10-13** contém exatamente 18 itens: 5 depósitos, 5 acordos, 3 promessas e 5 contatos.
- Os totais aditivos são calculados a partir de porUsuario. contatosUnicosTotal não é tratado como aditivo entre usuários.
- Os nomes e valores são fictícios; nenhum payload veio do CRM.

## Uso e segurança

Estes arquivos são **somente fixtures de teste**. Não os usar para inferir resultados reais, nem para substituir payloads autorizados do CRM. Os testes carregam o conteúdo localmente, verificam totais e exercitam a persistência apenas num SQLite em memória. Não fazem chamadas ao CRM, nem leem ou escrevem banco persistente.

A suíte automatizada descobre tests/test_fixtures_respostas_ficticias.py através do comando já usado no CI:

```bash
python -m unittest discover -s tests -v
```
