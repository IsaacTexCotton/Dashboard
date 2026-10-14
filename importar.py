#!/usr/bin/env python3
"""Importa o consolidado diário do CRM para SQLite, com validação antes de gravar.

Uso:
  python importar.py --arquivo amostra_resposta.json --dry-run
  python importar.py --arquivo resposta.json
  python importar.py --dia 2026-10-12
  python importar.py
  python importar.py --desde 2026-01-01

Variáveis de ambiente: CRM_URL, CRM_TOKEN ou CRM_COOKIE e DASHBOARD_DB.
--dry-run exige --arquivo, não abre banco e nunca consulta a API.
Cada dia é gravado em uma transação SQLite.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

DB = os.environ.get("DASHBOARD_DB", "cobranca.db")
JANELA_PADRAO = 7
TIPOS = ("deposito", "acordo", "promessa", "contato")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, nome TEXT);
CREATE TABLE IF NOT EXISTS fatos (
  data TEXT NOT NULL, usuario TEXT NOT NULL, tipo TEXT NOT NULL,
  qtd INTEGER NOT NULL DEFAULT 0, qtd_unicos INTEGER NOT NULL DEFAULT 0,
  valor REAL NOT NULL DEFAULT 0, valor_pago REAL NOT NULL DEFAULT 0,
  valor_aberto REAL NOT NULL DEFAULT 0, valor_quebrado REAL NOT NULL DEFAULT 0,
  importado_em TEXT NOT NULL, PRIMARY KEY (data, usuario, tipo)
);
CREATE INDEX IF NOT EXISTS ix_fatos_data ON fatos(data);
CREATE TABLE IF NOT EXISTS acordos_posicao (
  capturado_em TEXT PRIMARY KEY, data TEXT,
  recebido_periodo REAL, a_vencer REAL, vencido REAL
);
CREATE TABLE IF NOT EXISTS importacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, origem TEXT,
  inicio TEXT, fim TEXT, linhas INTEGER
);
"""


class ErroValidacao(ValueError):
    """Resposta incompatível ou insegura para importar."""


def _dia_iso(valor: Any, campo: str = "data") -> str:
    if not isinstance(valor, str):
        raise ErroValidacao(f"{campo}: esperado texto no formato AAAA-MM-DD")
    try:
        convertido = date.fromisoformat(valor)
    except ValueError as exc:
        raise ErroValidacao(f"{campo}: data inválida {valor!r}") from exc
    if convertido.isoformat() != valor:
        raise ErroValidacao(f"{campo}: use exatamente o formato AAAA-MM-DD")
    return valor


def _objeto(valor: Any, campo: str) -> dict:
    if not isinstance(valor, dict):
        raise ErroValidacao(f"{campo}: esperado objeto JSON")
    return valor


def _numero(valor: Any, campo: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroValidacao(f"{campo}: esperado número JSON finito")
    try:
        numero = float(valor)
    except (OverflowError, ValueError) as exc:
        raise ErroValidacao(f"{campo}: número fora do intervalo suportado") from exc
    if not math.isfinite(numero):
        raise ErroValidacao(f"{campo}: número não finito")
    if numero < 0:
        raise ErroValidacao(f"{campo}: valor monetário negativo não permitido")
    return numero


def _inteiro(valor: Any, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroValidacao(f"{campo}: esperado inteiro JSON")
    if valor < 0:
        raise ErroValidacao(f"{campo}: quantidade negativa não permitida")
    return valor


def _campo_numero(item: dict, campo: str, contexto: str) -> float:
    if campo not in item:
        raise ErroValidacao(f"{contexto}: campo obrigatório ausente: {campo}")
    return _numero(item[campo], f"{contexto}.{campo}")


def _campo_inteiro(item: dict, campo: str, contexto: str) -> int:
    if campo not in item:
        raise ErroValidacao(f"{contexto}: campo obrigatório ausente: {campo}")
    return _inteiro(item[campo], f"{contexto}.{campo}")


def normalizar(resp: Any, dia: str):
    """Valida e normaliza a resposta antes de qualquer escrita no SQLite."""
    dia = _dia_iso(dia, "dia de importação")
    resp = _objeto(resp, "resposta")
    if resp.get("success") is not True:
        raise ErroValidacao("CRM/arquivo não confirmou success=true")
    d = _objeto(resp.get("data"), "data")
    inicio = _dia_iso(d.get("inicio"), "data.inicio")
    fim = _dia_iso(d.get("fim"), "data.fim")
    if inicio != dia or fim != dia:
        raise ErroValidacao(f"período divergente: esperado {dia}–{dia}, recebido {inicio}–{fim}")

    usuarios: dict[str, str | None] = {}
    fatos: list[tuple] = []

    def ler_grupo(nome: str) -> list:
        grupo = _objeto(d.get(nome), f"data.{nome}")
        linhas = grupo.get("porUsuario")
        if not isinstance(linhas, list):
            raise ErroValidacao(f"data.{nome}.porUsuario: esperado lista")
        return linhas

    def registrar_usuario(item: dict, contexto: str) -> str:
        usuario = item.get("usuario")
        if not isinstance(usuario, str) or not usuario.strip():
            raise ErroValidacao(f"{contexto}.usuario: identificador vazio ou inválido")
        nome = item.get("nome")
        if nome is not None and not isinstance(nome, str):
            raise ErroValidacao(f"{contexto}.nome: esperado texto ou null")
        if usuario in usuarios and nome and usuarios[usuario] and nome != usuarios[usuario]:
            raise ErroValidacao(f"nomes conflitantes para o usuário {usuario!r}")
        if usuario not in usuarios or (not usuarios[usuario] and nome):
            usuarios[usuario] = nome
        return usuario

    def percorrer(nome: str):
        vistos: set[str] = set()
        for indice, bruto in enumerate(ler_grupo(nome)):
            contexto = f"data.{nome}.porUsuario[{indice}]"
            item = _objeto(bruto, contexto)
            usuario = registrar_usuario(item, contexto)
            if usuario in vistos:
                raise ErroValidacao(f"{contexto}: usuário duplicado no grupo {nome}")
            vistos.add(usuario)
            yield contexto, usuario, item

    for ctx, usuario, x in percorrer("depositos"):
        fatos.append((dia, usuario, "deposito", _campo_inteiro(x, "quantidade", ctx), 0,
                      _campo_numero(x, "valor", ctx), 0, 0, 0))
    for ctx, usuario, x in percorrer("acordos"):
        fatos.append((dia, usuario, "acordo", _campo_inteiro(x, "quantidade", ctx), 0,
                      _campo_numero(x, "valor", ctx), _campo_numero(x, "pagos", ctx),
                      _campo_numero(x, "pendente", ctx), 0))
    for ctx, usuario, x in percorrer("promessas"):
        fatos.append((dia, usuario, "promessa", _campo_inteiro(x, "quantidade", ctx), 0,
                      _campo_numero(x, "prometido", ctx), _campo_numero(x, "cumprido", ctx),
                      _campo_numero(x, "emAberto", ctx), _campo_numero(x, "quebrado", ctx)))
    for ctx, usuario, x in percorrer("contatos"):
        fatos.append((dia, usuario, "contato", _campo_inteiro(x, "registrosTotais", ctx),
                      _campo_inteiro(x, "contatosUnicos", ctx), 0, 0, 0, 0))

    valores = _objeto(d.get("valoresAcordo"), "data.valoresAcordo")
    totais = (
        _campo_numero(valores, "valorRecebidoPeriodo", "data.valoresAcordo"),
        _campo_numero(valores, "valorAVencer", "data.valoresAcordo"),
        _campo_numero(valores, "valorVencido", "data.valoresAcordo"),
    )
    timestamp = resp.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ErroValidacao("timestamp: campo obrigatório da origem; esperado texto não vazio")
    return usuarios, fatos, (timestamp, dia, *totais)


def _url_do_dia(url_base: str, dia: str) -> str:
    partes = urllib.parse.urlsplit(url_base)
    parametros = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
    filtrados = [(k, v) for k, v in parametros if k not in ("inicio", "fim")]
    filtrados.extend((("inicio", dia), ("fim", dia)))
    return urllib.parse.urlunsplit((partes.scheme, partes.netloc, partes.path,
                                    urllib.parse.urlencode(filtrados), partes.fragment))


def buscar(dia: str):
    url = os.environ.get("CRM_URL")
    if not url:
        raise RuntimeError("Defina CRM_URL ou use --arquivo resposta.json.")
    token, cookie = os.environ.get("CRM_TOKEN"), os.environ.get("CRM_COOKIE")
    if not token and not cookie:
        raise RuntimeError("Defina CRM_TOKEN ou CRM_COOKIE para autenticar a consulta.")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(_url_do_dia(url, dia), headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"CRM retornou HTTP {exc.code} para o dia {dia}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de comunicação com CRM no dia {dia}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CRM retornou JSON inválido para o dia {dia}") from exc


def gravar(con: sqlite3.Connection, dia: str, resp: Any, origem: str) -> int:
    usuarios, fatos, posicao = normalizar(resp, dia)
    agora = datetime.now().isoformat(timespec="seconds")
    with con:
        for usuario, nome in usuarios.items():
            con.execute(
                "INSERT INTO usuarios(usuario,nome) VALUES (?,?) "
                "ON CONFLICT(usuario) DO UPDATE SET nome=excluded.nome",
                (usuario, nome),
            )
        con.execute("DELETE FROM fatos WHERE data=?", (dia,))
        con.executemany(
            "INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(*linha, agora) for linha in fatos],
        )
        con.execute("INSERT OR REPLACE INTO acordos_posicao VALUES (?,?,?,?,?)", posicao)
        con.execute(
            "INSERT INTO importacoes(quando,origem,inicio,fim,linhas) VALUES (?,?,?,?,?)",
            (agora, origem, dia, dia, len(fatos)),
        )
    return len(fatos)


def dias(inicio: str, fim: str):
    inicio, fim = _dia_iso(inicio, "data inicial"), _dia_iso(fim, "data final")
    if inicio > fim:
        raise ErroValidacao("data inicial posterior à data final")
    atual = date.fromisoformat(inicio)
    while atual <= date.fromisoformat(fim):
        yield atual.isoformat()
        atual += timedelta(days=1)


def _carregar_arquivo(caminho: str):
    try:
        with open(caminho, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Arquivo JSON inválido: {caminho}, linha {exc.lineno}") from exc


def _auditoria_financeira_ok(resp: Any) -> bool:
    """Bloqueia gravação quando totais aditivos estão ausentes ou divergem."""
    # Import local para evitar ciclo de importação: o auditor reutiliza normalizar().
    from auditar_resposta import auditar

    checks = auditar(resp)
    bloqueios = [check for check in checks if check.status in ("DIVERGÊNCIA", "PENDENTE")]
    for check in bloqueios:
        print(
            f"Auditoria bloqueante: {check.grupo}.{check.metrica}: {check.status}; "
            f"total={check.total_api}; soma={check.soma_usuarios}; "
            f"diferença={check.diferenca}",
            file=sys.stderr,
        )
    if bloqueios:
        print(
            f"Importação bloqueada pela auditoria financeira: {len(bloqueios)} "
            "verificação(ões) pendente(s) ou divergente(s).",
            file=sys.stderr,
        )
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importação controlada do consolidado diário do CRM")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--desde", help="data inicial inclusiva, até hoje")
    grupo.add_argument("--dia", help="reprocessa um único dia")
    parser.add_argument("--arquivo", help="usa uma resposta JSON local; não consulta API")
    parser.add_argument("--dry-run", action="store_true",
                        help="valida --arquivo sem abrir ou gravar no banco")
    args = parser.parse_args(argv)
    if args.dry_run and not args.arquivo:
        parser.error("--dry-run exige --arquivo; nenhuma consulta de API será feita")
    if args.arquivo and (args.desde or args.dia):
        parser.error("--arquivo não pode ser combinado com --desde ou --dia")

    if args.arquivo:
        resp = _carregar_arquivo(args.arquivo)
        if not isinstance(resp, dict) or not isinstance(resp.get("data"), dict):
            raise ErroValidacao("arquivo: estrutura data ausente ou inválida")
        if not _auditoria_financeira_ok(resp):
            return 1
        dia_ref = _dia_iso(resp["data"].get("inicio"), "data.inicio")
        if args.dry_run:
            usuarios, fatos, _ = normalizar(resp, dia_ref)
            contagens = {tipo: sum(1 for linha in fatos if linha[2] == tipo) for tipo in TIPOS}
            print(f"VALIDAÇÃO OK — dia {dia_ref}; {len(usuarios)} usuários; {len(fatos)} fatos")
            print("Linhas previstas: " + ", ".join(f"{tipo}={contagens[tipo]}" for tipo in TIPOS))
            print("DRY-RUN: nenhum banco foi aberto ou alterado; nenhuma chamada ao CRM foi feita.")
            return 0
        con = sqlite3.connect(DB)
        try:
            con.executescript(SCHEMA)
            total = gravar(con, dia_ref, resp, "arquivo")
        finally:
            con.close()
        print(f"{total} linhas gravadas ({dia_ref}) em {DB}")
        return 0

    hoje = date.today()
    if args.dia:
        inicio = fim = _dia_iso(args.dia, "--dia")
    elif args.desde:
        inicio, fim = _dia_iso(args.desde, "--desde"), hoje.isoformat()
        if inicio > fim:
            raise ErroValidacao("--desde não pode ser posterior a hoje")
    else:
        inicio, fim = (hoje - timedelta(days=JANELA_PADRAO - 1)).isoformat(), hoje.isoformat()
    if not os.environ.get("CRM_URL"):
        raise RuntimeError("Defina CRM_URL ou use --arquivo resposta.json.")
    if not os.environ.get("CRM_TOKEN") and not os.environ.get("CRM_COOKIE"):
        raise RuntimeError("Defina CRM_TOKEN ou CRM_COOKIE para autenticar a consulta.")

    total = 0
    con: sqlite3.Connection | None = None
    try:
        for dia in dias(inicio, fim):
            resposta = buscar(dia)
            if not _auditoria_financeira_ok(resposta):
                return 1
            # Só cria/abre o banco depois que a primeira resposta foi auditada.
            if con is None:
                con = sqlite3.connect(DB)
                con.executescript(SCHEMA)
            total += gravar(con, dia, resposta, "api")
            print(f"  {dia} ok")
            time.sleep(0.3)
    finally:
        if con is not None:
            con.close()
    print(f"{total} linhas gravadas em {DB}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        # auditar_resposta também importa este módulo como "importar"; ambas
        # as instâncias de ErroValidacao herdam ValueError, mesmo se este arquivo
        # estiver sendo executado como __main__.
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(2)
