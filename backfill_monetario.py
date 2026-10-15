"""Backfill histórico idempotente para revisão isolada; não executa sozinho.

O modo padrão é simulação sem escrita. A aplicação exige aplicar=True e roda
numa transação SQLite. Nunca sobrescreve valores _centavos já preenchidos e
divergentes, nunca atualiza colunas REAL e não marca a conciliação como concluída.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from migrar_schema_monetario import (
    ErroMigracaoMonetaria,
    TABELA_ESTADO,
    validar_schema_monetario,
)
from precisao_monetaria import ErroMonetario, real_legado_para_centavos

_CHAVES = {
    "fatos": ("data", "usuario", "tipo"),
    "acordos_posicao": ("capturado_em",),
}
_FATO_COLUNAS = (
    "deposito_valor_centavos",
    "acordo_valor_centavos",
    "acordo_pago_centavos",
    "acordo_pendente_centavos",
    "promessa_prometido_centavos",
    "promessa_cumprido_centavos",
    "promessa_em_aberto_centavos",
    "promessa_quebrado_centavos",
)
_POSICAO_COLUNAS = (
    "recebido_periodo_centavos",
    "a_vencer_centavos",
    "vencido_centavos",
)
_MAPA_FATOS = {
    "deposito": (("valor", "deposito_valor_centavos", True),),
    "acordo": (
        ("valor", "acordo_valor_centavos", False),
        ("valor_pago", "acordo_pago_centavos", False),
        ("valor_aberto", "acordo_pendente_centavos", True),
    ),
    "promessa": (
        ("valor", "promessa_prometido_centavos", False),
        ("valor_pago", "promessa_cumprido_centavos", False),
        ("valor_aberto", "promessa_em_aberto_centavos", True),
        ("valor_quebrado", "promessa_quebrado_centavos", False),
    ),
    "contato": (),
}
_MAPA_POSICAO = (
    ("recebido_periodo", "recebido_periodo_centavos", True),
    ("a_vencer", "a_vencer_centavos", False),
    ("vencido", "vencido_centavos", False),
)


class ErroBackfillMonetario(RuntimeError):
    """O histórico ou o schema não corresponde ao plano de backfill."""


@dataclass(frozen=True)
class Atualizacao:
    tabela: str
    chave: tuple[Any, ...]
    valores: tuple[tuple[str, int], ...]


def _fase(con: sqlite3.Connection) -> str:
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (TABELA_ESTADO,),
    ).fetchone()
    if not existe:
        raise ErroBackfillMonetario("schema monetário não foi preparado")
    linha = con.execute(
        f"SELECT versao,fase FROM {TABELA_ESTADO} WHERE id=1"
    ).fetchone()
    if not linha or linha[0] != 1:
        raise ErroBackfillMonetario("marcador de migração ausente ou incompatível")
    if linha[1] not in ("schema_adicionado", "backfill_em_andamento"):
        raise ErroBackfillMonetario(
            f"backfill não permitido na fase {linha[1]!r}"
        )
    return str(linha[1])


def _verificar_schema(con: sqlite3.Connection) -> None:
    try:
        validar_schema_monetario(con)
    except ErroMigracaoMonetaria as exc:
        raise ErroBackfillMonetario(str(exc)) from exc
    for tabela, colunas_requeridas in (
        ("fatos", set(_CHAVES["fatos"]) | {
            "valor", "valor_pago", "valor_aberto", "valor_quebrado"
        } | set(_FATO_COLUNAS)),
        ("acordos_posicao", set(_CHAVES["acordos_posicao"]) | {
            "recebido_periodo", "a_vencer", "vencido"
        } | set(_POSICAO_COLUNAS)),
    ):
        existe = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
        ).fetchone()
        if not existe:
            raise ErroBackfillMonetario(f"tabela obrigatória ausente: {tabela}")
        cols = {
            str(row[1]): str(row[2]).upper()
            for row in con.execute(f"PRAGMA table_info({tabela})").fetchall()
        }
        faltantes = colunas_requeridas - set(cols)
        if faltantes:
            raise ErroBackfillMonetario(
                f"{tabela}: colunas ausentes: {sorted(faltantes)}"
            )
        for coluna in (_FATO_COLUNAS if tabela == "fatos" else _POSICAO_COLUNAS):
            if cols[coluna] != "INTEGER":
                raise ErroBackfillMonetario(f"{tabela}.{coluna}: tipo precisa ser INTEGER")


def _planejar_fato(linha: sqlite3.Row | tuple[Any, ...]) -> tuple[Atualizacao | None, int, int]:
    # Ordenação de SELECT declarada abaixo, sem usar nomes dinâmicos da origem.
    (data, usuario, tipo, valor, valor_pago, valor_aberto, valor_quebrado, *atuais) = linha
    if tipo not in _MAPA_FATOS:
        raise ErroBackfillMonetario(f"tipo histórico desconhecido: {tipo!r}")
    esperados: dict[str, int | None] = {coluna: None for coluna in _FATO_COLUNAS}
    pendencias = 0
    mapeamento = _MAPA_FATOS[tipo]
    fonte = {
        "valor": valor,
        "valor_pago": valor_pago,
        "valor_aberto": valor_aberto,
        "valor_quebrado": valor_quebrado,
    }
    for origem, destino, negativos_permitidos in mapeamento:
        bruto = fonte[origem]
        if bruto is None:
            pendencias += 1
            continue
        try:
            esperados[destino] = real_legado_para_centavos(
                bruto,
                campo=f"fatos[{data},{usuario},{tipo}].{origem}",
                negativos_permitidos=negativos_permitidos,
            )
        except ErroMonetario as exc:
            raise ErroBackfillMonetario(str(exc)) from exc

    alteracoes: list[tuple[str, int]] = []
    ja_corretas = 0
    for coluna, atual in zip(_FATO_COLUNAS, atuais):
        esperado = esperados[coluna]
        if atual is not None and (isinstance(atual, bool) or not isinstance(atual, int)):
            raise ErroBackfillMonetario(
                f"fatos[{data},{usuario},{tipo}].{coluna}: destino preenchido não é INTEGER"
            )
        if atual is None:
            if esperado is not None:
                alteracoes.append((coluna, esperado))
        elif esperado is None or atual != esperado:
            raise ErroBackfillMonetario(
                f"conflito: fatos[{data},{usuario},{tipo}].{coluna}="
                f"{atual}, esperado {esperado}; não sobrescrevendo"
            )
        else:
            ja_corretas += 1
    chave = (data, usuario, tipo)
    atualizacao = Atualizacao("fatos", chave, tuple(alteracoes)) if alteracoes else None
    return atualizacao, len(alteracoes), pendencias


def _planejar_posicao(linha: sqlite3.Row | tuple[Any, ...]) -> tuple[Atualizacao | None, int, int]:
    (capturado_em, recebido, a_vencer, vencido, *atuais) = linha
    fontes = (recebido, a_vencer, vencido)
    esperados: list[int | None] = []
    pendencias = 0
    for bruto, (origem, destino, negativos_permitidos) in zip(fontes, _MAPA_POSICAO):
        if bruto is None:
            esperados.append(None)
            pendencias += 1
            continue
        try:
            esperados.append(real_legado_para_centavos(
                bruto,
                campo=f"acordos_posicao[{capturado_em}].{origem}",
                negativos_permitidos=negativos_permitidos,
            ))
        except ErroMonetario as exc:
            raise ErroBackfillMonetario(str(exc)) from exc

    alteracoes: list[tuple[str, int]] = []
    ja_corretas = 0
    for coluna, atual, esperado in zip(_POSICAO_COLUNAS, atuais, esperados):
        if atual is not None and (isinstance(atual, bool) or not isinstance(atual, int)):
            raise ErroBackfillMonetario(
                f"acordos_posicao[{capturado_em}].{coluna}: destino não é INTEGER"
            )
        if atual is None:
            if esperado is not None:
                alteracoes.append((coluna, esperado))
        elif esperado is None or atual != esperado:
            raise ErroBackfillMonetario(
                f"conflito: acordos_posicao[{capturado_em}].{coluna}="
                f"{atual}, esperado {esperado}; não sobrescrevendo"
            )
        else:
            ja_corretas += 1
    atualizacao = Atualizacao(
        "acordos_posicao", (capturado_em,), tuple(alteracoes)
    ) if alteracoes else None
    return atualizacao, len(alteracoes), pendencias


def backfill_monetario(
    con: sqlite3.Connection,
    *,
    aplicar: bool = False,
) -> dict[str, Any]:
    """Planeja por padrão; aplicar=True executa todos os updates em transação.

    Não altera colunas REAL, não inventa zero para NULL e não marca a
    conciliação como concluída. Conflito em qualquer linha aborta todo o lote.
    """
    if not isinstance(con, sqlite3.Connection):
        raise ErroBackfillMonetario("conexão SQLite inválida")
    if con.in_transaction:
        raise ErroBackfillMonetario("backfill exige conexão fora de transação")
    if not isinstance(aplicar, bool):
        raise ErroBackfillMonetario("aplicar precisa ser booleano")
    abriu_transacao = False
    try:
        if aplicar:
            # Trava os escritores antes de validar o schema, ler o REAL e
            # preparar o plano: valores não podem mudar entre leitura e UPDATE.
            con.execute("BEGIN IMMEDIATE")
            abriu_transacao = True
        _verificar_schema(con)
        fase = _fase(con)
        # Uma única consulta por tabela com projeção fixa facilita auditar
        # exatamente quais colunas participam da conversão histórica.
        fatos = con.execute(
            "SELECT data,usuario,tipo,valor,valor_pago,valor_aberto,valor_quebrado,"
            + ",".join(_FATO_COLUNAS)
            + " FROM fatos ORDER BY data,usuario,tipo"
        ).fetchall()
        posicoes = con.execute(
            "SELECT capturado_em,recebido_periodo,a_vencer,vencido,"
            + ",".join(_POSICAO_COLUNAS)
            + " FROM acordos_posicao ORDER BY capturado_em"
        ).fetchall()

        plano: list[Atualizacao] = []
        colunas_alteradas = 0
        campos_pendentes = 0
        for linha in fatos:
            atualizacao, alterados, _status = _planejar_fato(linha)
            if atualizacao:
                plano.append(atualizacao)
                colunas_alteradas += alterados
        for linha in posicoes:
            atualizacao, alterados, pendentes = _planejar_posicao(linha)
            if atualizacao:
                plano.append(atualizacao)
                colunas_alteradas += alterados
            campos_pendentes += pendentes
        # NULL em fatos aplicáveis é pendência apenas quando a origem histórica
        # também não contém valor; o campo atual NULL e origem numérica viraria
        # atualização no plano, logo não entra nesta contagem.
        for linha in fatos:
            tipo = linha[2]
            mapeamento = _MAPA_FATOS[tipo]
            fonte = {
                "valor": linha[3],
                "valor_pago": linha[4],
                "valor_aberto": linha[5],
                "valor_quebrado": linha[6],
            }
            campos_pendentes += sum(1 for origem, _destino, _neg in mapeamento
                                    if fonte[origem] is None)

        if aplicar:
            if fase == "schema_adicionado":
                con.execute(
                    f"UPDATE {TABELA_ESTADO} SET fase='backfill_em_andamento',"
                    "atualizado_em=CURRENT_TIMESTAMP WHERE id=1"
                )
            for atualizacao in plano:
                tabela = atualizacao.tabela
                assignments = ",".join(f"{coluna}=?" for coluna, _ in atualizacao.valores)
                where = " AND ".join(f"{chave}=?" for chave in _CHAVES[tabela])
                sql = f"UPDATE {tabela} SET {assignments} WHERE {where}"
                parametros = tuple(valor for _coluna, valor in atualizacao.valores) + atualizacao.chave
                cur = con.execute(sql, parametros)
                if cur.rowcount != 1:
                    raise ErroBackfillMonetario(
                        f"chave histórica mudou durante backfill: {tabela}{atualizacao.chave!r}"
                    )
            con.commit()
            abriu_transacao = False

        return {
            "modo": "aplicado" if aplicar else "simulacao",
            "fase_antes": fase,
            "fase_depois": "backfill_em_andamento" if aplicar else fase,
            "linhas_fatos": len(fatos),
            "snapshots_posicao": len(posicoes),
            "updates_previstos": len(plano),
            "colunas_a_preencher": colunas_alteradas,
            "campos_pendentes_origem_null": campos_pendentes,
            "colunas_real_alteradas": 0,
            "conciliacao_concluida": False,
        }
    except BaseException:
        if abriu_transacao and con.in_transaction:
            con.rollback()
        raise


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys
    from datetime import datetime, timezone
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Backfill monetário histórico; modo simulação por padrão"
    )
    parser.add_argument("banco", help="caminho para SQLite existente; nunca cria banco")
    parser.add_argument("--aplicar", action="store_true", help="aplica o backfill em transação")
    parser.add_argument(
        "--diretorio-backup",
        help="diretório existente para backup e manifesto obrigatórios em modo --aplicar",
    )
    args = parser.parse_args(argv)
    banco = Path(args.banco).expanduser().resolve()
    if not banco.is_file():
        print(json.dumps({"status": "ERROR", "error": f"Banco não encontrado: {banco}"}))
        return 2
    if args.aplicar and (not args.diretorio_backup or not Path(args.diretorio_backup).is_dir()):
        print(json.dumps({
            "status": "ERROR",
            "error": "--aplicar exige --diretorio-backup apontando para diretório existente",
        }))
        return 2

    backup_info: dict[str, Any] | None = None
    try:
        if args.aplicar:
            import backup_sqlite

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            destino = Path(args.diretorio_backup).resolve() / (
                f"{banco.stem}-pre-backfill-{stamp}{banco.suffix or '.sqlite3'}"
            )
            manifesto = backup_sqlite.criar_backup(banco, destino)
            verificado = backup_sqlite.verificar_backup(destino)
            if verificado.get("status") != "OK":
                raise ErroBackfillMonetario(
                    "backup não passou na verificação: " + json.dumps(verificado)
                )
            if manifesto.get("source_file") != banco.name:
                raise ErroBackfillMonetario("manifesto do backup não corresponde ao banco de origem")
            backup_info = {
                "arquivo": str(destino),
                "sha256": verificado.get("backup_sha256"),
                "status": verificado.get("status"),
            }

        if args.aplicar:
            con = sqlite3.connect(str(banco), timeout=30)
        else:
            con = sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True)
        try:
            resultado = backfill_monetario(con, aplicar=args.aplicar)
        finally:
            con.close()
        print(json.dumps({
            "status": "OK",
            "banco": str(banco),
            "backup": backup_info,
            "resultado": resultado,
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, sqlite3.Error, ErroBackfillMonetario, ErroMigracaoMonetaria) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
