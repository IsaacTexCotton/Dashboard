"""Migração aditiva isolada para as colunas monetárias semânticas.

Este módulo não é chamado pela aplicação. Os testes usam SQLite descartável.
Não execute contra dados reais sem assinatura formal da Política v1.1/contrato,
backup/restauração verificados, revisão e aprovação dos gates de migração.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

FASES_VALIDAS = ("schema_adicionado", "backfill_em_andamento", "backfill_conciliado")
TABELA_ESTADO = "estado_migracao_monetaria"


@dataclass(frozen=True)
class ColunaAlvo:
    tabela: str
    nome: str
    check: str


_COLUNAS: tuple[ColunaAlvo, ...] = (
    ColunaAlvo("fatos", "deposito_valor_centavos",
               "deposito_valor_centavos IS NULL OR (typeof(deposito_valor_centavos)='integer' AND tipo='deposito')"),
    ColunaAlvo("fatos", "acordo_valor_centavos",
               "acordo_valor_centavos IS NULL OR (typeof(acordo_valor_centavos)='integer' AND acordo_valor_centavos>=0 AND tipo='acordo')"),
    ColunaAlvo("fatos", "acordo_pago_centavos",
               "acordo_pago_centavos IS NULL OR (typeof(acordo_pago_centavos)='integer' AND acordo_pago_centavos>=0 AND tipo='acordo')"),
    ColunaAlvo("fatos", "acordo_pendente_centavos",
               "acordo_pendente_centavos IS NULL OR (typeof(acordo_pendente_centavos)='integer' AND tipo='acordo')"),
    ColunaAlvo("fatos", "promessa_prometido_centavos",
               "promessa_prometido_centavos IS NULL OR (typeof(promessa_prometido_centavos)='integer' AND promessa_prometido_centavos>=0 AND tipo='promessa')"),
    ColunaAlvo("fatos", "promessa_cumprido_centavos",
               "promessa_cumprido_centavos IS NULL OR (typeof(promessa_cumprido_centavos)='integer' AND promessa_cumprido_centavos>=0 AND tipo='promessa')"),
    ColunaAlvo("fatos", "promessa_em_aberto_centavos",
               "promessa_em_aberto_centavos IS NULL OR (typeof(promessa_em_aberto_centavos)='integer' AND tipo='promessa')"),
    ColunaAlvo("fatos", "promessa_quebrado_centavos",
               "promessa_quebrado_centavos IS NULL OR (typeof(promessa_quebrado_centavos)='integer' AND promessa_quebrado_centavos>=0 AND tipo='promessa')"),
    ColunaAlvo("acordos_posicao", "recebido_periodo_centavos",
               "recebido_periodo_centavos IS NULL OR typeof(recebido_periodo_centavos)='integer'"),
    ColunaAlvo("acordos_posicao", "a_vencer_centavos",
               "a_vencer_centavos IS NULL OR (typeof(a_vencer_centavos)='integer' AND a_vencer_centavos>=0)"),
    ColunaAlvo("acordos_posicao", "vencido_centavos",
               "vencido_centavos IS NULL OR (typeof(vencido_centavos)='integer' AND vencido_centavos>=0)"),
)

_COLUNAS_LEGADAS_OBRIGATORIAS = {
    "fatos": {
        "data", "usuario", "tipo", "qtd", "qtd_unicos", "valor",
        "valor_pago", "valor_aberto", "valor_quebrado", "importado_em",
    },
    "acordos_posicao": {
        "capturado_em", "data", "recebido_periodo", "a_vencer", "vencido",
    },
}


class ErroMigracaoMonetaria(RuntimeError):
    """Schema não compatível com o contrato de migração proposto."""


def _tabelas(con: sqlite3.Connection) -> dict[str, str]:
    return {
        str(nome): str(sql or "")
        for nome, sql in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _colunas_tabela(con: sqlite3.Connection, tabela: str) -> dict[str, str]:
    # Os identificadores de tabela vêm apenas da lista de nomes internos.
    if tabela not in {"fatos", "acordos_posicao"}:
        raise ErroMigracaoMonetaria(f"tabela fora da allowlist: {tabela}")
    return {
        str(row[1]): str(row[2]).upper()
        for row in con.execute(f"PRAGMA table_info({tabela})").fetchall()
    }


def _normalizar_sql(sql: str) -> str:
    return re.sub(r"\s+", "", sql.lower().replace('"', "").replace("`", "").replace("[", "").replace("]", ""))


def _tem_check_esperado(sql_tabela: str, coluna: ColunaAlvo) -> bool:
    sql = _normalizar_sql(sql_tabela)
    check = _normalizar_sql(coluna.check)
    # SQLite pode acrescentar parênteses externos durante o ALTER; verifica os
    # elementos semânticos determinantes da expressão, não apenas o nome.
    partes = [
        f"{coluna.nome}isnullor",
        f"typeof({coluna.nome})='integer'",
    ]
    if "tipo='" in coluna.check:
        partes.append("tipo='" + coluna.check.split("tipo='", 1)[1].split("'", 1)[0] + "'")
    if ">=" in coluna.check:
        partes.append(f"{coluna.nome}>=0")
    return all(_normalizar_sql(p) in sql for p in partes) and check in sql


def _validar_estado(con: sqlite3.Connection, tabelas: dict[str, str]) -> str | None:
    if TABELA_ESTADO not in tabelas:
        return None
    colunas = {
        str(row[1]): str(row[2]).upper()
        for row in con.execute(f"PRAGMA table_info({TABELA_ESTADO})").fetchall()
    }
    if colunas != {"id": "INTEGER", "versao": "INTEGER", "fase": "TEXT", "atualizado_em": "TEXT"}:
        raise ErroMigracaoMonetaria("tabela de estado existe com schema incompatível")
    rows = con.execute(
        f"SELECT id, versao, fase, atualizado_em FROM {TABELA_ESTADO}"
    ).fetchall()
    if len(rows) > 1 or (rows and rows[0][0] != 1):
        raise ErroMigracaoMonetaria("tabela de estado contém linhas inesperadas")
    if not rows:
        return None
    _id, versao, fase, atualizado_em = rows[0]
    if versao != 1 or fase not in FASES_VALIDAS or not isinstance(atualizado_em, str):
        raise ErroMigracaoMonetaria("marcador de fase/versão inválido")
    return str(fase)


def migrar_schema_monetario(con: sqlite3.Connection) -> dict[str, object]:
    """Adiciona colunas CHECK sem backfill; repetições são idempotentes.

    A função não cria fatos/acordos_posicao nem modifica dados legados.
    Colunas-alvo preexistentes sem os CHECKs esperados causam aborto; não se
    tenta 'reparar' constraints silenciosamente. A obrigatoriedade de campos
    aplicáveis fica para o importador/diagnóstico durante a migração e triggers
    posteriores ao backfill conciliado.
    """
    if not isinstance(con, sqlite3.Connection):
        raise ErroMigracaoMonetaria("conexão SQLite inválida")
    if con.in_transaction:
        raise ErroMigracaoMonetaria("migração exige conexão fora de transação")

    tabelas = _tabelas(con)
    for tabela, obrigatorias in _COLUNAS_LEGADAS_OBRIGATORIAS.items():
        if tabela not in tabelas:
            raise ErroMigracaoMonetaria(f"tabela legada ausente: {tabela}")
        faltantes = obrigatorias - set(_colunas_tabela(con, tabela))
        if faltantes:
            raise ErroMigracaoMonetaria(
                f"{tabela}: colunas legadas obrigatórias ausentes: {sorted(faltantes)}"
            )

    fase_atual = _validar_estado(con, tabelas)
    plano: list[ColunaAlvo] = []
    for coluna in _COLUNAS:
        presentes = _colunas_tabela(con, coluna.tabela)
        sql_tabela = tabelas[coluna.tabela]
        if coluna.nome in presentes:
            if presentes[coluna.nome] != "INTEGER":
                raise ErroMigracaoMonetaria(
                    f"{coluna.tabela}.{coluna.nome}: tipo existente precisa ser INTEGER"
                )
            if not _tem_check_esperado(sql_tabela, coluna):
                raise ErroMigracaoMonetaria(
                    f"{coluna.tabela}.{coluna.nome}: CHECK ausente ou incompatível; abortando"
                )
        else:
            if fase_atual == "backfill_conciliado":
                raise ErroMigracaoMonetaria(
                    f"{coluna.tabela}.{coluna.nome}: coluna ausente após fase conciliada"
                )
            plano.append(coluna)

    criadas: list[str] = []
    try:
        con.execute("BEGIN IMMEDIATE")
        for coluna in plano:
            # nomes, tabelas e CHECK são constantes internas versionadas acima.
            con.execute(
                f"ALTER TABLE {coluna.tabela} ADD COLUMN {coluna.nome} INTEGER CHECK ({coluna.check})"
            )
            criadas.append(f"{coluna.tabela}.{coluna.nome}")

        tabelas_apos = _tabelas(con)
        estado_ausente = TABELA_ESTADO not in tabelas_apos
        if estado_ausente:
            con.execute(
                f"CREATE TABLE {TABELA_ESTADO} ("
                "id INTEGER PRIMARY KEY CHECK (id=1), "
                "versao INTEGER NOT NULL CHECK (versao=1), "
                "fase TEXT NOT NULL CHECK (fase IN ('schema_adicionado','backfill_em_andamento','backfill_conciliado')), "
                "atualizado_em TEXT NOT NULL)"
            )
            con.execute(
                f"INSERT INTO {TABELA_ESTADO}(id,versao,fase,atualizado_em) "
                "VALUES (1,1,'schema_adicionado',CURRENT_TIMESTAMP)"
            )
        elif fase_atual is None:
            con.execute(
                f"INSERT INTO {TABELA_ESTADO}(id,versao,fase,atualizado_em) "
                "VALUES (1,1,'schema_adicionado',CURRENT_TIMESTAMP)"
            )

        con.commit()
    except BaseException:
        if con.in_transaction:
            con.rollback()
        raise

    return {
        "versao": 1,
        "colunas_criadas": criadas,
        "total_colunas": len(_COLUNAS),
        "fase": _validar_estado(con, _tabelas(con)),
    }


def definir_fase_migracao(con: sqlite3.Connection, fase: str) -> None:
    """Atualiza só o marcador; não preenche dados nem habilita triggers."""
    if fase not in FASES_VALIDAS:
        raise ErroMigracaoMonetaria(f"fase inválida: {fase!r}")
    if con.in_transaction:
        raise ErroMigracaoMonetaria("alteração de fase exige conexão fora de transação")
    tabelas = _tabelas(con)
    if TABELA_ESTADO not in tabelas:
        raise ErroMigracaoMonetaria("schema monetário ainda não foi preparado")
    estado = _validar_estado(con, tabelas)
    if estado is None:
        raise ErroMigracaoMonetaria("marcador de fase ausente")
    ordem = {nome: i for i, nome in enumerate(FASES_VALIDAS)}
    if ordem[fase] < ordem[estado]:
        raise ErroMigracaoMonetaria("não é permitido retroceder a fase sem procedimento de reparo")
    if fase == "backfill_conciliado":
        # Verifica ausência de NULLs aplicáveis apenas quando o gate for
        # declarado; não inventa zero nem modifica dados históricos.
        for tipo, metricas in {
            "deposito": ("deposito_valor_centavos",),
            "acordo": ("acordo_valor_centavos", "acordo_pago_centavos", "acordo_pendente_centavos"),
            "promessa": ("promessa_prometido_centavos", "promessa_cumprido_centavos", "promessa_em_aberto_centavos", "promessa_quebrado_centavos"),
        }.items():
            for metrica in metricas:
                nulos = con.execute(
                    f"SELECT COUNT(*) FROM fatos WHERE tipo=? AND {metrica} IS NULL", (tipo,)
                ).fetchone()[0]
                if nulos:
                    raise ErroMigracaoMonetaria(
                        f"backfill não conciliado: {nulos} linhas aplicáveis com {metrica}=NULL"
                    )
        for metrica in ("recebido_periodo_centavos", "a_vencer_centavos", "vencido_centavos"):
            nulos = con.execute(
                f"SELECT COUNT(*) FROM acordos_posicao WHERE {metrica} IS NULL"
            ).fetchone()[0]
            if nulos:
                raise ErroMigracaoMonetaria(
                    f"backfill não conciliado: {nulos} snapshots com {metrica}=NULL"
                )
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            f"UPDATE {TABELA_ESTADO} SET fase=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=1",
            (fase,),
        )
        con.commit()
    except BaseException:
        if con.in_transaction:
            con.rollback()
        raise
