"""Mapeamento semântico de valores monetários para o schema-alvo proposto.

O módulo é isolado: não executa DDL, não abre bancos e não está conectado ao
importador. NULL é emitido para métricas que não se aplicam ao tipo de fato;
métricas aplicáveis em novas entradas são obrigatórias.
"""
from __future__ import annotations

from typing import Any

from precisao_monetaria import ErroMonetario, valor_final_centavos

FATO_METRICAS_CENTAVOS = (
    "deposito_valor_centavos",
    "acordo_valor_centavos",
    "acordo_pago_centavos",
    "acordo_pendente_centavos",
    "promessa_prometido_centavos",
    "promessa_cumprido_centavos",
    "promessa_em_aberto_centavos",
    "promessa_quebrado_centavos",
)

POSICAO_METRICAS_CENTAVOS = (
    "recebido_periodo_centavos",
    "a_vencer_centavos",
    "vencido_centavos",
)

# Cada regra é (campo de origem, coluna semântica de destino, negativos permitidos).
_REGRAS_POR_TIPO: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "deposito": (
        ("valor", "deposito_valor_centavos", True),
    ),
    "acordo": (
        ("valor", "acordo_valor_centavos", False),
        ("pagos", "acordo_pago_centavos", False),
        ("pendente", "acordo_pendente_centavos", True),
    ),
    "promessa": (
        ("prometido", "promessa_prometido_centavos", False),
        ("cumprido", "promessa_cumprido_centavos", False),
        ("emAberto", "promessa_em_aberto_centavos", True),
        ("quebrado", "promessa_quebrado_centavos", False),
    ),
    "contato": (),
}

_REGRAS_POSICAO: tuple[tuple[str, str, bool], ...] = (
    ("valorRecebidoPeriodo", "recebido_periodo_centavos", True),
    ("valorAVencer", "a_vencer_centavos", False),
    ("valorVencido", "vencido_centavos", False),
)


def mapear_fato_centavos(tipo: str, campos: dict[str, Any]) -> dict[str, int | None]:
    """Valida campos aplicáveis e retorna todas as oito métricas semânticas.

    Para métricas não aplicáveis ao tipo, retorna None; zero significa valor
    real zero. Métricas aplicáveis precisam estar presentes e não podem ser
    nulas. O chamador continua responsável por validar todo o payload antes
    de iniciar qualquer transação.
    """
    if tipo not in _REGRAS_POR_TIPO:
        raise ErroMonetario(f"tipo de fato desconhecido: {tipo!r}")
    if not isinstance(campos, dict):
        raise ErroMonetario(f"{tipo}: esperado objeto de campos")

    resultado: dict[str, int | None] = {
        nome: None for nome in FATO_METRICAS_CENTAVOS
    }
    for origem, destino, negativos_permitidos in _REGRAS_POR_TIPO[tipo]:
        if origem not in campos:
            raise ErroMonetario(f"{tipo}: campo monetário obrigatório ausente: {origem}")
        resultado[destino] = valor_final_centavos(
            campos[origem],
            campo=f"{tipo}.{origem}",
            negativos_permitidos=negativos_permitidos,
        )
    return resultado


def mapear_posicao_centavos(campos: dict[str, Any]) -> dict[str, int]:
    """Mapeia as três métricas do snapshot; nenhuma pode faltar em nova entrada."""
    if not isinstance(campos, dict):
        raise ErroMonetario("valoresAcordo: esperado objeto")
    resultado: dict[str, int] = {}
    for origem, destino, negativos_permitidos in _REGRAS_POSICAO:
        if origem not in campos:
            raise ErroMonetario(f"valoresAcordo: campo obrigatório ausente: {origem}")
        resultado[destino] = valor_final_centavos(
            campos[origem],
            campo=f"valoresAcordo.{origem}",
            negativos_permitidos=negativos_permitidos,
        )
    return resultado
