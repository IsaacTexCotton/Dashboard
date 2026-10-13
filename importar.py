#!/usr/bin/env python3
"""Importa o consolidado diário do CRM (por negociador) para SQLite.

Uso:
  python importar.py --desde 2026-01-01        # carga inicial, dia a dia
  python importar.py                           # rotina diária: últimos 7 dias
  python importar.py --dia 2026-10-12          # reprocessa um dia
  python importar.py --arquivo resposta.json   # usa uma resposta salva (teste/fallback)

Variáveis de ambiente (nunca no código):
  CRM_URL     endereço do endpoint (recebe ?inicio=AAAA-MM-DD&fim=AAAA-MM-DD)
  CRM_TOKEN   token (enviado como Bearer)   -- ou --
  CRM_COOKIE  cookie de sessão, se o CRM autenticar por cookie
  DASHBOARD_DB  caminho do banco (padrão: cobranca.db)
"""
import argparse, json, os, sqlite3, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

DB = os.environ.get("DASHBOARD_DB", "cobranca.db")
JANELA_PADRAO = 7  # reimporta os últimos dias: promessas/acordos mudam de status depois

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, nome TEXT);
CREATE TABLE IF NOT EXISTS fatos (
  data TEXT NOT NULL,
  usuario TEXT NOT NULL,
  tipo TEXT NOT NULL,                  -- deposito | acordo | promessa | contato
  qtd INTEGER NOT NULL DEFAULT 0,      -- contato: registros totais
  qtd_unicos INTEGER NOT NULL DEFAULT 0, -- contato: clientes únicos
  valor REAL NOT NULL DEFAULT 0,       -- depósito / acordo (face) / prometido
  valor_pago REAL NOT NULL DEFAULT 0,  -- acordo: pagos / promessa: cumprido
  valor_aberto REAL NOT NULL DEFAULT 0,-- acordo: pendente / promessa: em aberto
  valor_quebrado REAL NOT NULL DEFAULT 0,
  importado_em TEXT NOT NULL,
  PRIMARY KEY (data, usuario, tipo)
);
CREATE INDEX IF NOT EXISTS ix_fatos_data ON fatos(data);
-- Posição da carteira de acordos no momento da captura (não é histórico retroativo)
CREATE TABLE IF NOT EXISTS acordos_posicao (
  capturado_em TEXT PRIMARY KEY, data TEXT,
  recebido_periodo REAL, a_vencer REAL, vencido REAL
);
CREATE TABLE IF NOT EXISTS importacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, origem TEXT,
  inicio TEXT, fim TEXT, linhas INTEGER
);
"""

def f(v): return float(v or 0)
def i(v): return int(v or 0)

def normalizar(resp, dia):
    """Resposta do CRM -> (usuarios, fatos, posicao). Único ponto acoplado ao formato do CRM."""
    if not resp.get("success"):
        raise RuntimeError(f"CRM respondeu success=false: {str(resp)[:200]}")
    d = resp["data"]
    usuarios, fatos = {}, []
    def u(x): usuarios[x["usuario"]] = x.get("nome")

    for x in d.get("depositos", {}).get("porUsuario", []):
        u(x); fatos.append((dia, x["usuario"], "deposito", i(x["quantidade"]), 0, f(x["valor"]), 0, 0, 0))
    for x in d.get("acordos", {}).get("porUsuario", []):
        u(x); fatos.append((dia, x["usuario"], "acordo", i(x["quantidade"]), 0, f(x["valor"]),
                            f(x.get("pagos")), f(x.get("pendente")), 0))
    for x in d.get("promessas", {}).get("porUsuario", []):
        u(x); fatos.append((dia, x["usuario"], "promessa", i(x["quantidade"]), 0, f(x["prometido"]),
                            f(x.get("cumprido")), f(x.get("emAberto")), f(x.get("quebrado"))))
    for x in d.get("contatos", {}).get("porUsuario", []):
        u(x); fatos.append((dia, x["usuario"], "contato", i(x["registrosTotais"]), i(x["contatosUnicos"]), 0, 0, 0, 0))

    v = d.get("valoresAcordo") or {}
    pos = (resp.get("timestamp") or datetime.now().isoformat(), dia,
           f(v.get("valorRecebidoPeriodo")), f(v.get("valorAVencer")), f(v.get("valorVencido")))
    return usuarios, fatos, pos

def buscar(dia):
    url = os.environ.get("CRM_URL")
    if not url: sys.exit("Defina CRM_URL (e CRM_TOKEN ou CRM_COOKIE), ou use --arquivo.")
    q = urllib.parse.urlencode({"inicio": dia, "fim": dia})
    hdr = {"Accept": "application/json"}
    if os.environ.get("CRM_TOKEN"): hdr["Authorization"] = f"Bearer {os.environ['CRM_TOKEN']}"
    if os.environ.get("CRM_COOKIE"): hdr["Cookie"] = os.environ["CRM_COOKIE"]
    req = urllib.request.Request(f"{url}{'&' if '?' in url else '?'}{q}", headers=hdr)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def gravar(con, dia, resp, origem):
    usuarios, fatos, pos = normalizar(resp, dia)
    agora = datetime.now().isoformat(timespec="seconds")
    for k, n in usuarios.items():
        con.execute("INSERT INTO usuarios VALUES (?,?) ON CONFLICT(usuario) DO UPDATE SET nome=excluded.nome", (k, n))
    # troca o dia inteiro: se um negociador deixou de ter registro, a linha antiga some
    con.execute("DELETE FROM fatos WHERE data=?", (dia,))
    con.executemany("INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)", [(*r, agora) for r in fatos])
    con.execute("INSERT OR REPLACE INTO acordos_posicao VALUES (?,?,?,?,?)", pos)
    con.execute("INSERT INTO importacoes(quando,origem,inicio,fim,linhas) VALUES (?,?,?,?,?)",
                (agora, origem, dia, dia, len(fatos)))
    con.commit()
    return len(fatos)

def dias(inicio, fim):
    d = date.fromisoformat(inicio)
    while d <= date.fromisoformat(fim):
        yield d.isoformat(); d += timedelta(days=1)

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--desde"); a.add_argument("--dia"); a.add_argument("--arquivo")
    a = a.parse_args()
    con = sqlite3.connect(DB); con.executescript(SCHEMA)
    if a.arquivo:
        with open(a.arquivo, encoding="utf-8-sig") as fh: resp = json.load(fh)
        dia_ref = resp["data"]["inicio"]
        print(f"{gravar(con, dia_ref, resp, 'arquivo')} linhas ({dia_ref}) em {DB}"); return
    hoje = date.today()
    if a.dia: ini = fim = a.dia
    elif a.desde: ini, fim = a.desde, hoje.isoformat()
    else: ini, fim = (hoje - timedelta(days=JANELA_PADRAO - 1)).isoformat(), hoje.isoformat()
    total = 0
    for dia in dias(ini, fim):
        total += gravar(con, dia, buscar(dia), "api")
        print(f"  {dia} ok"); time.sleep(0.3)  # gentil com o CRM
    print(f"{total} linhas gravadas em {DB}")

if __name__ == "__main__":
    main()
