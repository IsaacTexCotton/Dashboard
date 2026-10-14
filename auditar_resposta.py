#!/usr/bin/env python3
"""Reconcilia totais do consolidado JSON contra as somas por usuário.

Uso: python auditar_resposta.py amostra_resposta.json
Não consulta o CRM e não abre nem altera banco de dados.
Valores monetários são conciliados por igualdade exata; não há tolerância de centavo.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import importar


@dataclass(frozen=True)
class Check:
    grupo: str
    metrica: str
    total_api: str
    soma_usuarios: str
    diferenca: str
    status: str


REGRAS = (
    ("depositos", "quantidadeTotal", "quantidade", "inteiro"),
    ("depositos", "valorTotal", "valor", "dinheiro"),
    ("acordos", "quantidadeTotal", "quantidade", "inteiro"),
    ("acordos", "valorTotal", "valor", "dinheiro"),
    ("acordos", "pagosTotal", "pagos", "dinheiro"),
    ("acordos", "pendenteTotal", "pendente", "dinheiro"),
    ("promessas", "quantidadeTotal", "quantidade", "inteiro"),
    ("promessas", "prometidoTotal", "prometido", "dinheiro"),
    ("promessas", "cumpridoTotal", "cumprido", "dinheiro"),
    ("promessas", "emAbertoTotal", "emAberto", "dinheiro"),
    ("promessas", "quebradoTotal", "quebrado", "dinheiro"),
    ("contatos", "registrosTotaisTotal", "registrosTotais", "inteiro"),
)


_NEGATIVOS_PERMITIDOS = {
    ("depositos", "valor"),
    ("acordos", "pendente"),
    ("promessas", "emAberto"),
}


def _decimal(
    valor: Any,
    campo: str,
    *,
    negativos_permitidos: bool = False,
) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal)):
        raise importar.ErroValidacao(f"{campo}: esperado número JSON")
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise importar.ErroValidacao(f"{campo}: número inválido") from exc
    if not numero.is_finite():
        raise importar.ErroValidacao(f"{campo}: número não finito")
    if numero < 0 and not negativos_permitidos:
        raise importar.ErroValidacao(f"{campo}: valor monetário negativo não permitido")
    return numero


def auditar(resp: Any, tolerancia: Decimal | None = None) -> list[Check]:
    if tolerancia is not None:
        if not isinstance(tolerancia, Decimal) or not tolerancia.is_finite() or tolerancia != 0:
            raise ValueError("tolerância monetária removida pela Política v1.1; a conciliação exige igualdade exata")
    if not isinstance(resp, dict) or not isinstance(resp.get("data"), dict):
        raise importar.ErroValidacao("resposta: estrutura data ausente ou inválida")
    dia = resp["data"].get("inicio")
    importar.normalizar(resp, dia)
    data = resp["data"]
    checks: list[Check] = []

    for grupo, total_campo, linha_campo, tipo in REGRAS:
        grupo_obj = data.get(grupo)
        if not isinstance(grupo_obj, dict):
            raise importar.ErroValidacao(f"data.{grupo}: esperado objeto")
        linhas = grupo_obj.get("porUsuario")
        if not isinstance(linhas, list):
            raise importar.ErroValidacao(f"data.{grupo}.porUsuario: esperado lista")
        if total_campo not in grupo_obj:
            checks.append(Check(grupo, total_campo, "ausente", "não calculado", "—", "PENDENTE"))
            continue
        if tipo == "inteiro":
            total = Decimal(importar._inteiro(
                grupo_obj[total_campo], f"data.{grupo}.{total_campo}"
            ))
        else:
            total = _decimal(
                grupo_obj[total_campo],
                f"data.{grupo}.{total_campo}",
                negativos_permitidos=(grupo, linha_campo) in _NEGATIVOS_PERMITIDOS,
            )
        soma = Decimal("0")
        for indice, linha in enumerate(linhas):
            if not isinstance(linha, dict) or linha_campo not in linha:
                raise importar.ErroValidacao(
                    f"data.{grupo}.porUsuario[{indice}].{linha_campo}: campo ausente"
                )
            soma += _decimal(
                linha[linha_campo],
                f"data.{grupo}.porUsuario[{indice}].{linha_campo}",
                negativos_permitidos=(grupo, linha_campo) in _NEGATIVOS_PERMITIDOS,
            )
        diferenca = total - soma
        limite = Decimal("0")
        fmt = lambda numero: format(numero, "f")
        checks.append(Check(grupo, total_campo, fmt(total), fmt(soma), fmt(diferenca),
                            "OK" if abs(diferenca) <= limite else "DIVERGÊNCIA"))

    # Não somar contatos únicos por negociador: o cliente pode aparecer em mais de uma carteira.
    contatos = data.get("contatos", {})
    if isinstance(contatos, dict) and "contatosUnicosTotal" in contatos:
        checks.append(Check("contatos", "contatosUnicosTotal (não aditivo)",
                            str(contatos["contatosUnicosTotal"]), "não comparada", "—", "NÃO ADITIVO"))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audita totais versus soma por usuário; não grava dados")
    parser.add_argument("arquivo", help="caminho para JSON local")
    args = parser.parse_args(argv)
    try:
        resp = importar._carregar_arquivo(args.arquivo)
        checks = auditar(resp)
    except (OSError, json.JSONDecodeError, ValueError, importar.ErroValidacao) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print("GRUPO | MÉTRICA | TOTAL API | SOMA POR USUÁRIO | DIFERENÇA | STATUS")
    for check in checks:
        print(f"{check.grupo} | {check.metrica} | {check.total_api} | {check.soma_usuarios} | {check.diferenca} | {check.status}")
    falhas = sum(check.status in ("DIVERGÊNCIA", "PENDENTE") for check in checks)
    if falhas:
        print(f"Resultado: {falhas} check(s) exigem revisão.")
        return 1
    print("Resultado: todos os totais aditivos reconciliados.")
    print("A semântica contábil das métricas não foi inferida por esta auditoria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
