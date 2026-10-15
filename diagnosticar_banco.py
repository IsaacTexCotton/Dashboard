#!/usr/bin/env python3
"""Diagnóstico somente-leitura do SQLite CAIXA FUTURO.

Não cria bancos, migrações, não consulta o CRM e não corrige dados.
Uso: python diagnosticar_banco.py [caminho.db] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {
    "usuarios": {"usuario", "nome"},
    "fatos": {"data", "usuario", "tipo", "qtd", "qtd_unicos", "valor",
              "valor_pago", "valor_aberto", "valor_quebrado", "importado_em"},
    "acordos_posicao": {"capturado_em", "data", "recebido_periodo", "a_vencer", "vencido"},
    "importacoes": {"id", "quando", "origem", "inicio", "fim", "linhas"},
}
FACT_TYPES = ("deposito", "acordo", "promessa", "contato")
FACT_MONEY_COLUMNS = ("valor", "valor_pago", "valor_aberto", "valor_quebrado")
SNAPSHOT_MONEY_COLUMNS = ("recebido_periodo", "a_vencer", "vencido")
FATO_CENTAVOS_COLUNAS = (
    "deposito_valor_centavos", "acordo_valor_centavos", "acordo_pago_centavos",
    "acordo_pendente_centavos", "promessa_prometido_centavos",
    "promessa_cumprido_centavos", "promessa_em_aberto_centavos", "promessa_quebrado_centavos",
)
POSICAO_CENTAVOS_COLUNAS = (
    "recebido_periodo_centavos", "a_vencer_centavos", "vencido_centavos",
)
FASES_LINHA_MONETARIA = {"legado", "dual", "conciliado"}
MAPA_FATO_CENTAVOS = {
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


def _check(nome: str, status: str, detalhe: str) -> dict[str, str]:
    return {"check": nome, "status": status, "detail": detalhe}


def _canonical_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _read_only_connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con



def _diagnostico_coerencia_fase_monetaria(
    con: sqlite3.Connection,
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    """Valida fases por linha e igualdade exata REAL -> centavos, sem escrever."""
    tables = {
        row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    cols = {
        table: {row[1]: str(row[2]).upper() for row in con.execute(f'PRAGMA table_info("{table}")')}
        for table in ("fatos", "acordos_posicao")
        if table in tables
    }
    has_phase = {table: "monetario_fase" in cols.get(table, {}) for table in ("fatos", "acordos_posicao")}
    has_any_centavos = any(
        col in cols.get(table, {})
        for table, names in (
            ("fatos", FATO_CENTAVOS_COLUNAS),
            ("acordos_posicao", POSICAO_CENTAVOS_COLUNAS),
        )
        for col in names
    )
    if not any(has_phase.values()) and not has_any_centavos:
        return None, {}
    if not all(has_phase.values()):
        return _check(
            "coerencia_fase_monetaria", "FAIL",
            "marcadores monetario_fase ausentes ou presentes em apenas parte do esquema",
        ), {}
    for table, names in (
        ("fatos", FATO_CENTAVOS_COLUNAS),
        ("acordos_posicao", POSICAO_CENTAVOS_COLUNAS),
    ):
        missing = [name for name in names if name not in cols.get(table, {})]
        if missing:
            return _check(
                "coerencia_fase_monetaria", "FAIL",
                f"{table}: colunas de centavos ausentes: {', '.join(missing)}",
            ), {}
        if cols[table].get("monetario_fase") != "TEXT":
            return _check(
                "coerencia_fase_monetaria", "FAIL",
                f"{table}.monetario_fase precisa ser TEXT",
            ), {}

    from precisao_monetaria import ErroMonetario, real_legado_para_centavos

    fases_contagem: dict[str, int] = {}
    pendencias = 0
    verificadas = 0
    erros: list[str] = []

    def verificar_par(*, fase: Any, legado: Any, centavos: Any, campo: str,
                      negativos_permitidos: bool) -> None:
        nonlocal pendencias, verificadas
        if fase == "legado":
            if legado is None or centavos is None:
                pendencias += 1
            return
        if fase not in ("dual", "conciliado"):
            erros.append(f"{campo}: monetario_fase inválido {fase!r}")
            return
        if legado is None or centavos is None:
            erros.append(f"{campo}: REAL ou centavos ausente na fase {fase}")
            return
        if isinstance(centavos, bool) or not isinstance(centavos, int):
            erros.append(f"{campo}: centavos não está armazenado como INTEGER")
            return
        try:
            esperado = real_legado_para_centavos(
                legado, campo=campo, negativos_permitidos=negativos_permitidos
            )
        except ErroMonetario as exc:
            erros.append(f"{campo}: {exc}")
            return
        if esperado is None or centavos != esperado:
            erros.append(f"{campo}: REAL convertido ({esperado}) diverge dos centavos ({centavos})")
            return
        verificadas += 1

    fatos = con.execute(
        "SELECT data,usuario,tipo,monetario_fase,valor,valor_pago,valor_aberto,valor_quebrado,"
        + ",".join(FATO_CENTAVOS_COLUNAS)
        + " FROM fatos ORDER BY data,usuario,tipo"
    ).fetchall()
    for row in fatos:
        fase = row["monetario_fase"]
        fases_contagem[f"fatos.{fase}"] = fases_contagem.get(f"fatos.{fase}", 0) + 1
        if fase not in FASES_LINHA_MONETARIA:
            erros.append(f"fatos[{row['data']},{row['usuario']}]: monetario_fase inválido {fase!r}")
            continue
        tipo = row["tipo"]
        if tipo not in MAPA_FATO_CENTAVOS:
            erros.append(f"fatos[{row['data']},{row['usuario']}]: tipo inválido {tipo!r}")
            continue
        aplicaveis = {destino for _origem, destino, _neg in MAPA_FATO_CENTAVOS[tipo]}
        for coluna in FATO_CENTAVOS_COLUNAS:
            if coluna not in aplicaveis and row[coluna] is not None:
                erros.append(
                    f"fatos[{row['data']},{row['usuario']},{tipo}]: "
                    f"{coluna} preenchida em tipo não aplicável"
                )
        for origem, destino, negativos in MAPA_FATO_CENTAVOS[tipo]:
            verificar_par(
                fase=fase, legado=row[origem], centavos=row[destino],
                campo=f"fatos[{row['data']},{row['usuario']},{tipo}].{destino}",
                negativos_permitidos=negativos,
            )

    posicoes = con.execute(
        "SELECT capturado_em,monetario_fase,recebido_periodo,a_vencer,vencido,"
        + ",".join(POSICAO_CENTAVOS_COLUNAS)
        + " FROM acordos_posicao ORDER BY capturado_em"
    ).fetchall()
    for row in posicoes:
        fase = row["monetario_fase"]
        fases_contagem[f"acordos_posicao.{fase}"] = fases_contagem.get(f"acordos_posicao.{fase}", 0) + 1
        if fase not in FASES_LINHA_MONETARIA:
            erros.append(f"acordos_posicao[{row['capturado_em']}]: monetario_fase inválido {fase!r}")
            continue
        for origem, destino, negativos in (
            ("recebido_periodo", "recebido_periodo_centavos", True),
            ("a_vencer", "a_vencer_centavos", False),
            ("vencido", "vencido_centavos", False),
        ):
            verificar_par(
                fase=fase, legado=row[origem], centavos=row[destino],
                campo=f"acordos_posicao[{row['capturado_em']}].{destino}",
                negativos_permitidos=negativos,
            )

    status = "FAIL" if erros else "WARN" if pendencias else "OK"
    detalhe = (
        f"{verificadas} pares REAL/centavos verificados; {pendencias} pendência(s) "
        f"em linhas legado; {len(erros)} incoerência(s)"
    )
    if erros:
        detalhe += "; exemplos: " + " | ".join(erros[:3])
    metrics = {
        "rows_by_phase": fases_contagem,
        "verified_pairs": verificadas,
        "legacy_pending_pairs": pendencias,
        "incoherences": len(erros),
    }
    return _check("coerencia_fase_monetaria", status, detalhe), metrics


def diagnosticar(caminho: str | Path) -> dict[str, Any]:
    path = Path(caminho).expanduser()
    report: dict[str, Any] = {
        "database": str(path.resolve()), "mode": "read-only", "status": "OK",
        "checks": [], "metrics": {},
    }
    checks: list[dict[str, str]] = report["checks"]
    if not path.is_file():
        raise FileNotFoundError(f"Banco não encontrado; nenhum arquivo foi criado: {path}")
    con = _read_only_connect(path)
    try:
        try:
            integrity_values = [row[0] for row in con.execute("PRAGMA integrity_check").fetchall()]
            checks.append(_check("integridade_sqlite", "OK" if integrity_values == ["ok"] else "FAIL",
                                 "PRAGMA integrity_check retornou ok" if integrity_values == ["ok"]
                                 else "; ".join(str(value) for value in integrity_values[:10])))
        except sqlite3.DatabaseError as exc:
            checks.append(_check("integridade_sqlite", "FAIL", str(exc)))

        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        missing_tables = sorted(set(REQUIRED_COLUMNS) - tables)
        if missing_tables:
            checks.append(_check("schema_tabelas", "FAIL", "Tabelas ausentes: " + ", ".join(missing_tables)))
            report["status"] = "FAIL"
            return report
        checks.append(_check("schema_tabelas", "OK", "Todas as quatro tabelas esperadas existem"))

        missing_columns: dict[str, list[str]] = {}
        for table, required in REQUIRED_COLUMNS.items():
            found = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
            missing = sorted(required - found)
            if missing:
                missing_columns[table] = missing
        if missing_columns:
            detail = "; ".join(f"{table}: {', '.join(columns)}" for table, columns in missing_columns.items())
            checks.append(_check("schema_colunas", "FAIL", "Colunas ausentes — " + detail))
            report["status"] = "FAIL"
            return report
        checks.append(_check("schema_colunas", "OK", "Colunas necessárias estão presentes"))

        row_count = con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0]
        day_summary = con.execute("SELECT COUNT(DISTINCT data), MIN(data), MAX(data) FROM fatos").fetchone()
        import_summary = con.execute("SELECT COUNT(*), MAX(quando), MAX(fim) FROM importacoes").fetchone()
        snapshot_summary = con.execute("SELECT COUNT(*), MAX(capturado_em), MAX(data) FROM acordos_posicao").fetchone()
        report["metrics"].update({
            "fact_rows": row_count, "fact_days": day_summary[0], "first_fact_date": day_summary[1],
            "last_fact_date": day_summary[2], "import_log_rows": import_summary[0],
            "latest_import_at": import_summary[1], "latest_logged_end_date": import_summary[2],
            "agreement_snapshot_rows": snapshot_summary[0], "latest_snapshot_at": snapshot_summary[1],
            "latest_snapshot_reference_date": snapshot_summary[2],
        })
        if row_count:
            checks.append(_check("fatos_presentes", "OK", f"{row_count} linhas em {day_summary[0]} dia(s) distintos"))
        else:
            checks.append(_check("fatos_presentes", "WARN", "A tabela fatos está vazia"))
        if import_summary[0] == 0:
            checks.append(_check("log_importacoes", "WARN", "Ainda não há execuções registradas"))
        else:
            checks.append(_check("log_importacoes", "OK", f"{import_summary[0]} execução(ões) registrada(s)"))

        duplicates = con.execute(
            "SELECT COUNT(*) FROM (SELECT data, usuario, tipo FROM fatos "
            "GROUP BY data, usuario, tipo HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        checks.append(_check("chave_fatos", "OK" if duplicates == 0 else "FAIL",
                             "Sem chaves duplicadas" if duplicates == 0 else f"{duplicates} chaves duplicadas"))
        unknown = con.execute(
            "SELECT tipo, COUNT(*) AS n FROM fatos WHERE tipo NOT IN (?, ?, ?, ?) GROUP BY tipo", FACT_TYPES
        ).fetchall()
        if unknown:
            detail = ", ".join(f"{row['tipo']!r}: {row['n']}" for row in unknown)
            checks.append(_check("tipos_fato", "FAIL", "Tipos desconhecidos: " + detail))
        else:
            checks.append(_check("tipos_fato", "OK", "Todos os fatos usam tipos conhecidos"))

        bad_quantities = con.execute(
            "SELECT COUNT(*) FROM fatos WHERE typeof(qtd) <> 'integer' OR qtd < 0 "
            "OR typeof(qtd_unicos) <> 'integer' OR qtd_unicos < 0"
        ).fetchone()[0]
        checks.append(_check("quantidades", "OK" if bad_quantities == 0 else "FAIL",
                             "Quantidades são inteiros não negativos" if bad_quantities == 0
                             else f"{bad_quantities} linha(s) com quantidade inválida"))
        bad_dates = [str(row[0]) for row in con.execute("SELECT DISTINCT data FROM fatos")
                     if not _canonical_date(row[0])]
        checks.append(_check("datas_fatos", "OK" if not bad_dates else "FAIL",
                             "Datas canônicas AAAA-MM-DD" if not bad_dates
                             else "Datas inválidas: " + ", ".join(bad_dates[:10])))
        bad_users = con.execute(
            "SELECT COUNT(*) FROM fatos f LEFT JOIN usuarios u ON u.usuario=f.usuario "
            "WHERE u.usuario IS NULL OR trim(f.usuario) = ''"
        ).fetchone()[0]
        checks.append(_check("referencias_usuarios", "OK" if bad_users == 0 else "WARN",
                             "Todo fato aponta para usuário cadastrado" if bad_users == 0
                             else f"{bad_users} fato(s) sem usuário correspondente"))
        bad_money = 0
        for row in con.execute("SELECT valor, valor_pago, valor_aberto, valor_quebrado FROM fatos"):
            if any(not isinstance(row[col], (int, float)) or not math.isfinite(row[col])
                   for col in FACT_MONEY_COLUMNS):
                bad_money += 1
        checks.append(_check("valores_fatos", "OK" if bad_money == 0 else "FAIL",
                             "Valores são numéricos e finitos" if bad_money == 0
                             else f"{bad_money} linha(s) com valor inválido"))
        bad_snapshots = 0
        for row in con.execute("SELECT recebido_periodo, a_vencer, vencido FROM acordos_posicao"):
            if any(not isinstance(row[col], (int, float)) or not math.isfinite(row[col])
                   for col in SNAPSHOT_MONEY_COLUMNS):
                bad_snapshots += 1
        checks.append(_check("valores_snapshots", "OK" if bad_snapshots == 0 else "WARN",
                             "Valores dos snapshots presentes e finitos" if bad_snapshots == 0
                             else f"{bad_snapshots} snapshot(s) com valores inválidos"))
        fase_check, fase_metrics = _diagnostico_coerencia_fase_monetaria(con)
        if fase_check is not None:
            checks.append(fase_check)
            report["metrics"]["monetary_phase"] = fase_metrics
        foreign_key_rows = con.execute("PRAGMA foreign_key_check").fetchall()
        checks.append(_check("chaves_estrangeiras", "OK" if not foreign_key_rows else "WARN",
                             "Nenhuma violação de chave estrangeira declarada" if not foreign_key_rows
                             else f"{len(foreign_key_rows)} violação(ões) reportada(s)"))
        summaries = con.execute(
            "SELECT tipo, COUNT(*) AS linhas, SUM(qtd) AS qtd_total FROM fatos GROUP BY tipo ORDER BY tipo"
        ).fetchall()
        report["metrics"]["facts_by_type"] = {
            row["tipo"]: {"rows": row["linhas"], "quantity_sum": row["qtd_total"] or 0}
            for row in summaries
        }
    finally:
        con.close()
    statuses = {check["status"] for check in checks}
    report["status"] = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "OK"
    report["summary"] = {
        "checks": len(checks), "ok": sum(check["status"] == "OK" for check in checks),
        "warnings": sum(check["status"] == "WARN" for check in checks),
        "failures": sum(check["status"] == "FAIL" for check in checks),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico SQLite somente-leitura")
    parser.add_argument("banco", nargs="?", default=os.environ.get("DASHBOARD_DB", "cobranca.db"))
    parser.add_argument("--json", action="store_true", help="emite relatório estruturado JSON")
    args = parser.parse_args(argv)
    try:
        report = diagnosticar(args.banco)
    except (OSError, sqlite3.Error, ValueError) as exc:
        error = {"database": str(args.banco), "mode": "read-only", "status": "ERROR", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False, indent=2) if args.json else f"ERRO: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Banco: {report['database']} (somente leitura)")
        print(f"Resultado: {report['status']}")
        for check in report["checks"]:
            print(f"[{check['status']}] {check['check']}: {check['detail']}")
        if "summary" in report:
            s = report["summary"]
            print(f"Checks: {s['ok']} OK; {s['warnings']} aviso(s); {s['failures']} falha(s)")
    if report["status"] in ("FAIL", "ERROR"):
        return 1 if report["status"] == "FAIL" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
