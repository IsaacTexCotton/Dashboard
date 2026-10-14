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
    if ordem[fase] > ordem[estado] + 1:
        raise ErroMigracaoMonetaria("não é permitido pular fases da migração")
    if fase == "backfill_conciliado":
        validar_schema_monetario(con)
        verificar_conciliacao_monetaria(con)
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



def ativar_triggers_obrigatoriedade(con: sqlite3.Connection) -> list[str]:
    """Instala triggers de NOT NULL semântico só após backfill conciliado.

    A função não converte nem escreve valores de negócio. A ativação verifica
    novamente o marcador e a ausência de NULLs aplicáveis; a criação de todos
    os triggers é transacional e idempotente.
    """
    if not isinstance(con, sqlite3.Connection):
        raise ErroMigracaoMonetaria("conexão SQLite inválida")
    if con.in_transaction:
        raise ErroMigracaoMonetaria("ativação de triggers exige conexão fora de transação")
    tabelas = _tabelas(con)
    if TABELA_ESTADO not in tabelas:
        raise ErroMigracaoMonetaria("schema monetário ainda não foi preparado")
    fase = _validar_estado(con, tabelas)
    if fase != "backfill_conciliado":
        raise ErroMigracaoMonetaria(
            "triggers de obrigatoriedade só podem ser ativados após backfill_conciliado"
        )

    # A fase somente pode ser declarada conciliada se todas as métricas
    # aplicáveis estiverem preenchidas; esta verificação é repetida como defesa.
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
                    f"obrigatoriedade não ativada: {nulos} linhas com {metrica}=NULL"
                )
    for metrica in ("recebido_periodo_centavos", "a_vencer_centavos", "vencido_centavos"):
        nulos = con.execute(
            f"SELECT COUNT(*) FROM acordos_posicao WHERE " + metrica + " IS NULL"
        ).fetchone()[0]
        if nulos:
            raise ErroMigracaoMonetaria(
                f"obrigatoriedade não ativada: {nulos} snapshots com {metrica}=NULL"
            )

    fato_incompleto = (
        "(NEW.tipo='deposito' AND NEW.deposito_valor_centavos IS NULL) OR "
        "(NEW.tipo='acordo' AND (NEW.acordo_valor_centavos IS NULL OR "
        "NEW.acordo_pago_centavos IS NULL OR NEW.acordo_pendente_centavos IS NULL)) OR "
        "(NEW.tipo='promessa' AND (NEW.promessa_prometido_centavos IS NULL OR "
        "NEW.promessa_cumprido_centavos IS NULL OR NEW.promessa_em_aberto_centavos IS NULL OR "
        "NEW.promessa_quebrado_centavos IS NULL))"
    )
    sql_triggers = {
        "trg_monetario_fatos_obrigatorio_insert": (
            f"CREATE TRIGGER IF NOT EXISTS trg_monetario_fatos_obrigatorio_insert "
            f"BEFORE INSERT ON fatos WHEN {fato_incompleto} "
            "BEGIN SELECT RAISE(ABORT, 'métrica monetária aplicável obrigatória após backfill'); END"
        ),
        "trg_monetario_fatos_obrigatorio_update": (
            f"CREATE TRIGGER IF NOT EXISTS trg_monetario_fatos_obrigatorio_update "
            f"BEFORE UPDATE ON fatos WHEN {fato_incompleto} "
            "BEGIN SELECT RAISE(ABORT, 'métrica monetária aplicável obrigatória após backfill'); END"
        ),
        "trg_monetario_posicao_obrigatoria_insert": (
            "CREATE TRIGGER IF NOT EXISTS trg_monetario_posicao_obrigatoria_insert "
            "BEFORE INSERT ON acordos_posicao WHEN "
            "NEW.recebido_periodo_centavos IS NULL OR NEW.a_vencer_centavos IS NULL OR "
            "NEW.vencido_centavos IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'métricas monetárias da posição são obrigatórias após backfill'); END"
        ),
        "trg_monetario_posicao_obrigatoria_update": (
            "CREATE TRIGGER IF NOT EXISTS trg_monetario_posicao_obrigatoria_update "
            "BEFORE UPDATE ON acordos_posicao WHEN "
            "NEW.recebido_periodo_centavos IS NULL OR NEW.a_vencer_centavos IS NULL OR "
            "NEW.vencido_centavos IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'métricas monetárias da posição são obrigatórias após backfill'); END"
        ),
    }
    criados: list[str] = []
    try:
        con.execute("BEGIN IMMEDIATE")
        for nome, sql in sql_triggers.items():
            ja_existe = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (nome,)
            ).fetchone()
            if ja_existe:
                # Não considerar uma trigger de mesmo nome, mas definição
                # divergente, como ativação válida.
                sql_existente = _normalizar_sql(str(ja_existe[0])).replace("ifnotexists", "")
                sql_esperado = _normalizar_sql(sql).replace("ifnotexists", "")
                if sql_existente != sql_esperado:
                    raise ErroMigracaoMonetaria(f"trigger preexistente divergente: {nome}")
            else:
                con.execute(sql)
                criados.append(nome)
        con.commit()
    except BaseException:
        if con.in_transaction:
            con.rollback()
        raise
    return criados


def verificar_conciliacao_monetaria(con: sqlite3.Connection) -> dict[str, int]:
    """Compara cada coluna INTEGER com a conversão determinística do REAL legado.

    Não altera dados e não conta uma métrica aplicável com origem NULL como
    conciliada. A janela de dez dias úteis e a revisão humana são gates externos
    e não são inferidos por esta verificação de igualdade.
    """
    from precisao_monetaria import ErroMonetario, real_legado_para_centavos

    fase = validar_schema_monetario(con)
    if fase not in ("backfill_em_andamento", "backfill_conciliado"):
        raise ErroMigracaoMonetaria(
            "conciliação só pode ser verificada após iniciar o backfill"
        )

    mapa_fatos = {
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
    colunas_centavos = {
        "deposito_valor_centavos", "acordo_valor_centavos", "acordo_pago_centavos",
        "acordo_pendente_centavos", "promessa_prometido_centavos",
        "promessa_cumprido_centavos", "promessa_em_aberto_centavos",
        "promessa_quebrado_centavos",
    }
    verificadas = 0
    divergencias = 0
    pendencias = 0
    consulta = (
        "SELECT data,usuario,tipo,valor,valor_pago,valor_aberto,valor_quebrado,"
        + ",".join(sorted(colunas_centavos))
        + " FROM fatos ORDER BY data,usuario,tipo"
    )
    # Usa a ordem fixa do schema, não depende da ordenação lexical ao comparar.
    ordem_centavos = sorted(colunas_centavos)
    for linha in con.execute(consulta):
        data, usuario, tipo, valor, pago, aberto, quebrado = linha[:7]
        if tipo not in mapa_fatos:
            raise ErroMigracaoMonetaria(f"tipo histórico desconhecido: {tipo!r}")
        fonte = {
            "valor": valor,
            "valor_pago": pago,
            "valor_aberto": aberto,
            "valor_quebrado": quebrado,
        }
        atuais = dict(zip(ordem_centavos, linha[7:]))
        aplicaveis = {col for _src, col, _neg in mapa_fatos[tipo]}
        for coluna in colunas_centavos - aplicaveis:
            if atuais[coluna] is not None:
                divergencias += 1
        for origem, coluna, negativos in mapa_fatos[tipo]:
            bruto = fonte[origem]
            atual = atuais[coluna]
            if bruto is None:
                pendencias += 1
                continue
            try:
                esperado = real_legado_para_centavos(
                    bruto,
                    campo=f"fatos[{data},{usuario},{tipo}].{origem}",
                    negativos_permitidos=negativos,
                )
            except ErroMonetario as exc:
                raise ErroMigracaoMonetaria(str(exc)) from exc
            if atual is None:
                pendencias += 1
            elif isinstance(atual, bool) or not isinstance(atual, int) or atual != esperado:
                divergencias += 1
            else:
                verificadas += 1

    for linha in con.execute(
        "SELECT capturado_em,recebido_periodo,a_vencer,vencido,"
        "recebido_periodo_centavos,a_vencer_centavos,vencido_centavos "
        "FROM acordos_posicao ORDER BY capturado_em"
    ):
        capturado_em, recebido, a_vencer, vencido, rec_c, vencer_c, vencido_c = linha
        for origem, coluna, bruto, atual, negativos in (
            ("recebido_periodo", "recebido_periodo_centavos", recebido, rec_c, True),
            ("a_vencer", "a_vencer_centavos", a_vencer, vencer_c, False),
            ("vencido", "vencido_centavos", vencido, vencido_c, False),
        ):
            if bruto is None:
                pendencias += 1
                continue
            try:
                esperado = real_legado_para_centavos(
                    bruto,
                    campo=f"acordos_posicao[{capturado_em}].{origem}",
                    negativos_permitidos=negativos,
                )
            except ErroMonetario as exc:
                raise ErroMigracaoMonetaria(str(exc)) from exc
            if atual is None:
                pendencias += 1
            elif isinstance(atual, bool) or not isinstance(atual, int) or atual != esperado:
                divergencias += 1
            else:
                verificadas += 1
    if pendencias or divergencias:
        raise ErroMigracaoMonetaria(
            f"conciliação não aprovada: {pendencias} pendência(s), "
            f"{divergencias} divergência(s); não marque backfill_conciliado"
        )
    return {"campos_verificados": verificadas, "pendencias": pendencias, "divergencias": divergencias}


def validar_schema_monetario(con: sqlite3.Connection) -> str:
    """Valida as 11 colunas, seus CHECKs e o marcador de fase sem escrever."""
    if not isinstance(con, sqlite3.Connection):
        raise ErroMigracaoMonetaria("conexão SQLite inválida")
    tabelas = _tabelas(con)
    for tabela in ("fatos", "acordos_posicao"):
        if tabela not in tabelas:
            raise ErroMigracaoMonetaria(f"tabela obrigatória ausente: {tabela}")
    for coluna in _COLUNAS:
        tipos = _colunas_tabela(con, coluna.tabela)
        if tipos.get(coluna.nome) != "INTEGER":
            raise ErroMigracaoMonetaria(
                f"{coluna.tabela}.{coluna.nome}: coluna INTEGER ausente ou incompatível"
            )
        if not _tem_check_esperado(tabelas[coluna.tabela], coluna):
            raise ErroMigracaoMonetaria(
                f"{coluna.tabela}.{coluna.nome}: CHECK ausente ou incompatível"
            )
    fase = _validar_estado(con, tabelas)
    if fase is None:
        raise ErroMigracaoMonetaria("marcador de fase monetária ausente")
    return fase
