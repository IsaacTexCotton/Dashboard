"""Escrita dupla transacional em protótipo, sem conexão com o importador.

O módulo exige schema preexistente contendo colunas legadas e _centavos; não
cria tabelas/colunas e não executa backfill. O uso em produção permanece fora
do escopo até que migração, compatibilidade, backup/restauração, testes e rollback
sejam demonstrados em ambiente isolado e os procedimentos operacionais sejam cumpridos.
"""
from __future__ import annotations

import math
import sqlite3
from decimal import Decimal
from typing import Any

from modelo_monetario import (
    FATO_METRICAS_CENTAVOS,
    POSICAO_METRICAS_CENTAVOS,
    mapear_fato_centavos,
    mapear_posicao_centavos,
)
from precisao_monetaria import (
    ErroMonetario,
    INT64_MAX,
    INT64_MIN,
    valor_final_centavos,
)

COLUNAS_FATO_LEGADO = (
    "data",
    "usuario",
    "tipo",
    "qtd",
    "qtd_unicos",
    "valor",
    "valor_pago",
    "valor_aberto",
    "valor_quebrado",
    "importado_em",
)
COLUNAS_POSICAO_LEGADO = (
    "capturado_em",
    "data",
    "recebido_periodo",
    "a_vencer",
    "vencido",
)

_APLICAVEIS_POR_TIPO = {
    "deposito": {"deposito_valor_centavos"},
    "acordo": {
        "acordo_valor_centavos",
        "acordo_pago_centavos",
        "acordo_pendente_centavos",
    },
    "promessa": {
        "promessa_prometido_centavos",
        "promessa_cumprido_centavos",
        "promessa_em_aberto_centavos",
        "promessa_quebrado_centavos",
    },
    "contato": set(),
}
_NEGATIVOS_PERMITIDOS = {
    "deposito_valor_centavos",
    "acordo_pendente_centavos",
    "promessa_em_aberto_centavos",
}


def _texto(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroMonetario(f"{campo}: texto obrigatório ausente ou inválido")
    return valor


def _inteiro_nao_negativo(valor: Any, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ErroMonetario(f"{campo}: esperado inteiro não negativo")
    return valor


def _real_legado(valor: Any, campo: str) -> int | float:
    # O valor é passado ao adaptador legado sem recalcular sua semântica.
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroMonetario(f"{campo}: esperado número para coluna REAL legada")
    if not math.isfinite(float(valor)):
        raise ErroMonetario(f"{campo}: REAL legado não finito")
    return valor


def _real_de_decimal_validado(
    valor: Any,
    campo: str,
    *,
    negativos_permitidos: bool,
) -> float:
    """Cast confinado ao adaptador de compatibilidade REAL."""
    valor_final_centavos(
        valor,
        campo=campo,
        negativos_permitidos=negativos_permitidos,
    )
    if isinstance(valor, bool):
        raise ErroMonetario(f"{campo}: booleano não permitido")
    if isinstance(valor, Decimal):
        decimal_origem = valor
    elif isinstance(valor, int):
        decimal_origem = Decimal(valor)
    else:
        raise ErroMonetario(
            f"{campo}: o adaptador REAL aceita somente int/Decimal validados"
        )
    convertido = float(decimal_origem)
    if not math.isfinite(convertido):
        raise ErroMonetario(f"{campo}: conversão para REAL não finita")
    return convertido


def preparar_fato_duplo(
    *,
    dia: str,
    usuario: str,
    tipo: str,
    quantidade: int,
    importado_em: str,
    campos_monetarios: dict[str, Any],
    qtd_unicos: int = 0,
) -> dict[str, dict[str, Any]]:
    """Gera os dois payloads a partir da mesma entrada decimal exata.

    O Decimal validado gera diretamente os inteiros em centavos. Somente o
    adaptador legado faz cast para float/REAL. Este helper não grava no banco.
    """
    dia = _texto(dia, "dia")
    usuario = _texto(usuario, "usuario")
    tipo = _texto(tipo, "tipo")
    importado_em = _texto(importado_em, "importado_em")
    quantidade = _inteiro_nao_negativo(quantidade, "quantidade")
    qtd_unicos = _inteiro_nao_negativo(qtd_unicos, "qtd_unicos")
    if tipo not in _APLICAVEIS_POR_TIPO:
        raise ErroMonetario(f"tipo de fato desconhecido: {tipo!r}")
    if not isinstance(campos_monetarios, dict):
        raise ErroMonetario("campos_monetarios: esperado objeto")

    centavos = mapear_fato_centavos(tipo, campos_monetarios)
    origem_por_legado = {
        "deposito": {"valor": "valor"},
        "acordo": {"valor": "valor", "pagos": "valor_pago", "pendente": "valor_aberto"},
        "promessa": {
            "prometido": "valor",
            "cumprido": "valor_pago",
            "emAberto": "valor_aberto",
            "quebrado": "valor_quebrado",
        },
        "contato": {},
    }[tipo]
    permitidos = {
        "deposito": {"valor"},
        "acordo": {"pendente"},
        "promessa": {"emAberto"},
        "contato": set(),
    }[tipo]
    valores_legados = {
        "valor": 0.0,
        "valor_pago": 0.0,
        "valor_aberto": 0.0,
        "valor_quebrado": 0.0,
    }
    for campo_origem, coluna_legada in origem_por_legado.items():
        valores_legados[coluna_legada] = _real_de_decimal_validado(
            campos_monetarios[campo_origem],
            f"{tipo}.{campo_origem}",
            negativos_permitidos=campo_origem in permitidos,
        )

    legado = {
        "data": dia,
        "usuario": usuario,
        "tipo": tipo,
        "qtd": quantidade,
        "qtd_unicos": qtd_unicos,
        **valores_legados,
        "importado_em": importado_em,
    }
    return {"legado": legado, "centavos": centavos}


def preparar_posicao_dupla(
    *,
    capturado_em: str,
    dia: str,
    campos_monetarios: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Prepara snapshot REAL/centavos a partir das mesmas entradas Decimal."""
    capturado_em = _texto(capturado_em, "capturado_em")
    dia = _texto(dia, "dia")
    centavos = mapear_posicao_centavos(campos_monetarios)
    legado = {
        "capturado_em": capturado_em,
        "data": dia,
        "recebido_periodo": _real_de_decimal_validado(
            campos_monetarios["valorRecebidoPeriodo"],
            "valoresAcordo.valorRecebidoPeriodo",
            negativos_permitidos=True,
        ),
        "a_vencer": _real_de_decimal_validado(
            campos_monetarios["valorAVencer"],
            "valoresAcordo.valorAVencer",
            negativos_permitidos=False,
        ),
        "vencido": _real_de_decimal_validado(
            campos_monetarios["valorVencido"],
            "valoresAcordo.valorVencido",
            negativos_permitidos=False,
        ),
    }
    return legado, centavos


def _validar_pareamento_fato(
    tipo: str,
    legado: dict[str, Any],
    centavos: dict[str, Any],
) -> None:
    """Evita aceitar dois payloads diferentes para uma única origem monetária."""
    mapeamento = {
        "deposito": (("deposito_valor_centavos", "valor"),),
        "acordo": (
            ("acordo_valor_centavos", "valor"),
            ("acordo_pago_centavos", "valor_pago"),
            ("acordo_pendente_centavos", "valor_aberto"),
        ),
        "promessa": (
            ("promessa_prometido_centavos", "valor"),
            ("promessa_cumprido_centavos", "valor_pago"),
            ("promessa_em_aberto_centavos", "valor_aberto"),
            ("promessa_quebrado_centavos", "valor_quebrado"),
        ),
        "contato": (),
    }
    usados = {coluna_legada for _, coluna_legada in mapeamento[tipo]}
    for coluna_centavos, coluna_legada in mapeamento[tipo]:
        esperado = float(Decimal(centavos[coluna_centavos]) / Decimal(100))
        recebido = float(legado[coluna_legada])
        if recebido != esperado:
            raise ErroMonetario(
                f"{tipo}: divergência no lote preparado entre {coluna_legada} "
                f"(REAL) e {coluna_centavos} (INTEGER)"
            )
    # Campos legados sem métrica semântica para aquele tipo continuam no valor
    # neutro da compatibilidade; não podem transportar saldo de outro tipo.
    for coluna_legada in ("valor", "valor_pago", "valor_aberto", "valor_quebrado"):
        if coluna_legada not in usados and float(legado[coluna_legada]) != 0.0:
            raise ErroMonetario(
                f"{tipo}: {coluna_legada} legado deve permanecer zero neste tipo"
            )


def _validar_pareamento_posicao(
    legado: dict[str, Any],
    centavos: dict[str, Any],
) -> None:
    for coluna_legada, coluna_centavos in (
        ("recebido_periodo", "recebido_periodo_centavos"),
        ("a_vencer", "a_vencer_centavos"),
        ("vencido", "vencido_centavos"),
    ):
        esperado = float(Decimal(centavos[coluna_centavos]) / Decimal(100))
        if float(legado[coluna_legada]) != esperado:
            raise ErroMonetario(
                f"acordos_posicao: divergência no lote entre {coluna_legada} "
                f"(REAL) e {coluna_centavos} (INTEGER)"
            )


def _validar_centavos_fato(tipo: str, centavos: dict[str, Any]) -> tuple[Any, ...]:
    if not isinstance(centavos, dict) or set(centavos) != set(FATO_METRICAS_CENTAVOS):
        raise ErroMonetario("métricas _centavos do fato não correspondem ao contrato")
    aplicaveis = _APLICAVEIS_POR_TIPO[tipo]
    valores: list[int | None] = []
    for coluna in FATO_METRICAS_CENTAVOS:
        valor = centavos[coluna]
        if coluna not in aplicaveis:
            if valor is not None:
                raise ErroMonetario(f"{tipo}: {coluna} não se aplica e deve ser NULL")
            valores.append(None)
            continue
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErroMonetario(f"{tipo}: {coluna} aplicável precisa ser INTEGER, não NULL")
        if not INT64_MIN <= valor <= INT64_MAX:
            raise ErroMonetario(f"{coluna}: fora do intervalo INTEGER de 64 bits")
        if valor < 0 and coluna not in _NEGATIVOS_PERMITIDOS:
            raise ErroMonetario(f"{coluna}: sinal negativo não permitido")
        valores.append(valor)
    return tuple(valores)


def _validar_centavos_posicao(centavos: dict[str, Any]) -> tuple[int, ...]:
    if not isinstance(centavos, dict) or set(centavos) != set(POSICAO_METRICAS_CENTAVOS):
        raise ErroMonetario("métricas _centavos da posição não correspondem ao contrato")
    valores: list[int] = []
    for coluna in POSICAO_METRICAS_CENTAVOS:
        valor = centavos[coluna]
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErroMonetario(f"{coluna}: INTEGER aplicável obrigatório")
        if not INT64_MIN <= valor <= INT64_MAX:
            raise ErroMonetario(f"{coluna}: fora do intervalo INTEGER de 64 bits")
        if coluna != "recebido_periodo_centavos" and valor < 0:
            raise ErroMonetario(f"{coluna}: sinal negativo não permitido")
        valores.append(valor)
    return tuple(valores)


def gravar_dia_duplo(
    con: sqlite3.Connection,
    *,
    dia: str,
    usuarios: dict[str, str | None],
    fatos: list[dict[str, Any]],
    posicao_legada: dict[str, Any],
    posicao_centavos: dict[str, Any],
    origem: str,
    quando: str,
) -> int:
    """Grava um dia inteiro atomicamente nos campos legados e _centavos.

    Cada fato contém duas chaves: "legado" (todas as colunas legadas) e
    "centavos" (as oito colunas semânticas). O caller deve validar/normalizar
    o payload original e preparar tudo antes de chamar esta função.

    A função exige um schema já migrado, não cria colunas nem faz backfill.
    """
    if not isinstance(con, sqlite3.Connection):
        raise ErroMonetario("conexão SQLite inválida")
    if con.in_transaction:
        raise ErroMonetario("gravar_dia_duplo exige conexão fora de transação")
    dia = _texto(dia, "dia")
    origem = _texto(origem, "origem")
    quando = _texto(quando, "quando")
    if not isinstance(usuarios, dict):
        raise ErroMonetario("usuarios: esperado dicionário")
    if not isinstance(fatos, list):
        raise ErroMonetario("fatos: esperado lista")
    for usuario, nome in usuarios.items():
        _texto(usuario, "usuario")
        if nome is not None and not isinstance(nome, str):
            raise ErroMonetario(f"{usuario}: nome deve ser texto ou NULL")

    fatos_preparados: list[tuple[Any, ...]] = []
    chaves: set[tuple[str, str, str]] = set()
    for indice, fato in enumerate(fatos):
        ctx = f"fatos[{indice}]"
        if not isinstance(fato, dict) or set(fato) != {"legado", "centavos"}:
            raise ErroMonetario(f"{ctx}: esperado objeto com legado e centavos")
        legado, centavos = fato["legado"], fato["centavos"]
        if not isinstance(legado, dict) or set(legado) != set(COLUNAS_FATO_LEGADO):
            raise ErroMonetario(f"{ctx}: colunas legadas incompatíveis")
        if legado["data"] != dia:
            raise ErroMonetario(f"{ctx}: data não corresponde ao dia da importação")
        usuario = _texto(legado["usuario"], f"{ctx}.usuario")
        if usuario not in usuarios:
            raise ErroMonetario(f"{ctx}: usuário não está incluído no lote")
        tipo = legado["tipo"]
        if not isinstance(tipo, str) or tipo not in _APLICAVEIS_POR_TIPO:
            raise ErroMonetario(f"{ctx}: tipo de fato desconhecido")
        chave = (dia, usuario, tipo)
        if chave in chaves:
            raise ErroMonetario(f"{ctx}: fato duplicado no mesmo dia/usuário/tipo")
        chaves.add(chave)
        _inteiro_nao_negativo(legado["qtd"], f"{ctx}.qtd")
        _inteiro_nao_negativo(legado["qtd_unicos"], f"{ctx}.qtd_unicos")
        _real_legado(legado["valor"], f"{ctx}.valor")
        _real_legado(legado["valor_pago"], f"{ctx}.valor_pago")
        _real_legado(legado["valor_aberto"], f"{ctx}.valor_aberto")
        _real_legado(legado["valor_quebrado"], f"{ctx}.valor_quebrado")
        _texto(legado["importado_em"], f"{ctx}.importado_em")
        valores_centavos = _validar_centavos_fato(tipo, centavos)
        _validar_pareamento_fato(tipo, legado, centavos)
        fatos_preparados.append(
            tuple(legado[c] for c in COLUNAS_FATO_LEGADO) + valores_centavos + ("dual",)
        )

    if not isinstance(posicao_legada, dict) or set(posicao_legada) != set(COLUNAS_POSICAO_LEGADO):
        raise ErroMonetario("colunas legadas de acordos_posicao incompatíveis")
    _texto(posicao_legada["capturado_em"], "acordos_posicao.capturado_em")
    if posicao_legada["data"] != dia:
        raise ErroMonetario("acordos_posicao.data não corresponde ao dia")
    valores_posicao_legada = tuple(
        posicao_legada[coluna] for coluna in COLUNAS_POSICAO_LEGADO
    )
    for coluna, valor in zip(COLUNAS_POSICAO_LEGADO[2:], valores_posicao_legada[2:]):
        _real_legado(valor, f"acordos_posicao.{coluna}")
    valores_posicao_centavos = _validar_centavos_posicao(posicao_centavos)
    _validar_pareamento_posicao(posicao_legada, posicao_centavos)

    colunas_fato = COLUNAS_FATO_LEGADO + FATO_METRICAS_CENTAVOS + ("monetario_fase",)
    sql_fato = (
        f"INSERT INTO fatos ({','.join(colunas_fato)}) VALUES "
        f"({','.join('?' for _ in colunas_fato)})"
    )
    colunas_posicao = COLUNAS_POSICAO_LEGADO + POSICAO_METRICAS_CENTAVOS + ("monetario_fase",)
    sql_posicao = (
        f"INSERT OR REPLACE INTO acordos_posicao ({','.join(colunas_posicao)}) VALUES "
        f"({','.join('?' for _ in colunas_posicao)})"
    )

    # Explicit BEGIN makes the atomicity guarantee work even for
    # sqlite3.connect(..., isolation_level=None) autocommit connections.
    try:
        con.execute("BEGIN IMMEDIATE")
        for usuario, nome in usuarios.items():
            con.execute(
                "INSERT INTO usuarios(usuario,nome) VALUES (?,?) "
                "ON CONFLICT(usuario) DO UPDATE SET nome=excluded.nome",
                (usuario, nome),
            )
        con.execute("DELETE FROM fatos WHERE data=?", (dia,))
        con.executemany(sql_fato, fatos_preparados)
        con.execute(sql_posicao, valores_posicao_legada + valores_posicao_centavos + ("dual",))
        con.execute(
            "INSERT INTO importacoes(quando,origem,inicio,fim,linhas) VALUES (?,?,?,?,?)",
            (quando, origem, dia, dia, len(fatos_preparados)),
        )
        con.commit()
    except BaseException:
        if con.in_transaction:
            con.rollback()
        raise
    return len(fatos_preparados)
