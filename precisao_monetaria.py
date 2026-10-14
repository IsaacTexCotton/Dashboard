"""Primitivas monetárias exatas para revisão isolada.

Este módulo é um protótipo deliberadamente NÃO conectado ao importador,
auditor ou schema de produção. Não o ative sem ratificação formal da Política
v1.1/contrato e revisão de integração.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
_TOKEN_INTEIRO = re.compile(r"-?\d+\Z")
_TOKEN_DECIMAL = re.compile(r"-?\d+(?:\.\d+)?\Z")


class ErroMonetario(ValueError):
    """Entrada monetária ou grandeza incompatível com o contrato proposto."""


def _parse_int_token(token: str) -> int:
    """Valida o token inteiro original antes de convertê-lo."""
    if not _TOKEN_INTEIRO.fullmatch(token):
        raise ErroMonetario(f"token inteiro JSON fora da gramática permitida: {token!r}")
    try:
        return int(token)
    except ValueError as exc:
        raise ErroMonetario("inteiro JSON inválido ou fora do limite do interpretador") from exc


def _parse_decimal_token(token: str) -> Decimal:
    """Valida o token decimal original, rejeitando notação científica."""
    if not _TOKEN_DECIMAL.fullmatch(token):
        raise ErroMonetario(
            f"token decimal JSON fora da gramática permitida (sem expoente): {token!r}"
        )
    try:
        valor = Decimal(token)
    except InvalidOperation as exc:
        raise ErroMonetario(f"token decimal inválido: {token!r}") from exc
    if not valor.is_finite():
        raise ErroMonetario("valor decimal não finito")
    return valor


def _parse_constant(token: str) -> None:
    """Rejeita NaN e Infinity, aceitos por padrão por json.loads do Python."""
    raise ErroMonetario(f"constante JSON não permitida: {token}")


def loads_json_estrito(texto: str) -> Any:
    """Carrega JSON preservando decimais e validando tokens numéricos brutos.

    Inteiros permanecem int; tokens com parte decimal tornam-se Decimal.
    Strings permanecem strings, mas só devem ser aceitas em campos cujo
    contrato de origem declare explicitamente esse tipo.
    """
    if not isinstance(texto, str):
        raise ErroMonetario("o JSON deve ser fornecido como texto")
    try:
        return json.loads(
            texto,
            parse_int=_parse_int_token,
            parse_float=_parse_decimal_token,
            parse_constant=_parse_constant,
        )
    except ErroMonetario:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ErroMonetario("JSON inválido ou fora dos limites suportados") from exc


def _decimal_de_origem(
    valor: Any,
    campo: str,
    *,
    permitir_texto: bool = False,
) -> Decimal:
    """Obtém Decimal sem aceitar float ou boolean implicitamente."""
    if isinstance(valor, bool):
        raise ErroMonetario(f"{campo}: booleano não é valor numérico")
    if isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, int):
        numero = Decimal(valor)
    elif isinstance(valor, str) and permitir_texto:
        if not _TOKEN_DECIMAL.fullmatch(valor):
            raise ErroMonetario(
                f"{campo}: texto decimal inválido ou com notação científica"
            )
        try:
            numero = Decimal(valor)
        except InvalidOperation as exc:
            raise ErroMonetario(f"{campo}: texto decimal inválido") from exc
    elif isinstance(valor, float):
        raise ErroMonetario(
            f"{campo}: float intermediário proibido; carregue o JSON com loads_json_estrito"
        )
    else:
        raise ErroMonetario(f"{campo}: esperado int ou Decimal")
    if not numero.is_finite():
        raise ErroMonetario(f"{campo}: valor não finito")
    return numero


def inteiro_escalado_exato(
    valor: Any,
    casas: int,
    *,
    campo: str = "valor",
    negativos_permitidos: bool = False,
    permitir_texto: bool = False,
) -> int:
    """Converte um decimal exato em inteiro escalado sem arredondamento.

    Exemplo: casas=2 converte reais finais em centavos; casas=4 converte uma
    grandeza _e4. Casas excedentes só são aceitas se não alterarem o valor
    escalado (por exemplo, 1.230 com casas=2). O resultado deve caber em
    INTEGER assinado de 64 bits, compatível com SQLite.
    """
    if isinstance(casas, bool) or not isinstance(casas, int) or not 0 <= casas <= 18:
        raise ErroMonetario("casas precisa ser um inteiro entre 0 e 18")
    numero = _decimal_de_origem(valor, campo, permitir_texto=permitir_texto)
    partes = numero.as_tuple()
    digitos = "".join(str(d) for d in partes.digits).lstrip("0") or "0"

    # Normaliza qualquer representação numérica de zero, inclusive -0.00.
    if digitos == "0":
        return 0

    negativo = partes.sign == 1
    if negativo and not negativos_permitidos:
        raise ErroMonetario(f"{campo}: valor negativo não permitido")

    deslocamento = partes.exponent + casas
    if deslocamento >= 0:
        # Evita criar inteiros gigantes antes de detectar overflow.
        if len(digitos) + deslocamento > 19:
            raise ErroMonetario(f"{campo}: fora do intervalo INTEGER de 64 bits")
        absoluto = int(digitos) * (10**deslocamento)
    else:
        remover = -deslocamento
        zeros_finais = len(digitos) - len(digitos.rstrip("0"))
        if zeros_finais < remover:
            raise ErroMonetario(
                f"{campo}: precisão excede {casas} casas; arredondamento de entrada proibido"
            )
        parte_inteira = digitos[:-remover] if remover else digitos
        absoluto = int(parte_inteira or "0")

    limite = abs(INT64_MIN) if negativo else INT64_MAX
    if absoluto > limite:
        raise ErroMonetario(f"{campo}: fora do intervalo INTEGER de 64 bits")
    return -absoluto if negativo else absoluto


def valor_final_centavos(
    valor: Any,
    *,
    campo: str = "valor",
    negativos_permitidos: bool = False,
    permitir_texto: bool = False,
) -> int:
    """Converte valor monetário final para centavos sem arredondar entrada."""
    return inteiro_escalado_exato(
        valor,
        2,
        campo=campo,
        negativos_permitidos=negativos_permitidos,
        permitir_texto=permitir_texto,
    )


def grandeza_para_escala(
    valor: Any,
    casas: int,
    *,
    campo: str = "grandeza",
    negativos_permitidos: bool = False,
    permitir_texto: bool = False,
) -> int:
    """Converte taxa, preço unitário ou quantidade para a escala contratada."""
    return inteiro_escalado_exato(
        valor,
        casas,
        campo=campo,
        negativos_permitidos=negativos_permitidos,
        permitir_texto=permitir_texto,
    )


def resultado_calculado_para_centavos(
    valor: Any,
    *,
    campo: str = "resultado",
    negativos_permitidos: bool = False,
) -> int:
    """Aplica half-up uma única vez ao resultado de cálculo e retorna centavos.

    Esta função é para resultados calculados, não para aceitar/normalizar
    valores monetários finais recebidos da origem.
    """
    numero = _decimal_de_origem(valor, campo)
    # Valores muito grandes não devem chegar ao quantize; a checagem evita
    # contextos desnecessários e mantém explícito o limite do armazenamento.
    limite_amplo = Decimal(abs(INT64_MIN) + 100) / Decimal(100)
    if numero.copy_abs() > limite_amplo:
        raise ErroMonetario(f"{campo}: resultado fora do intervalo monetário suportado")
    partes = numero.as_tuple()
    precisao = max(28, len(partes.digits) + max(0, numero.adjusted()) + 5)
    try:
        with localcontext() as contexto:
            contexto.prec = precisao
            arredondado = numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ErroMonetario(f"{campo}: resultado não pode ser arredondado com segurança") from exc
    return valor_final_centavos(
        arredondado,
        campo=campo,
        negativos_permitidos=negativos_permitidos,
    )
