#!/usr/bin/env python3
"""Valida o fluxo completo do Caixa Futuro usando apenas um JSON local.

O banco é temporário, criado dentro de um diretório temporário e removido no fim.
Nenhuma chamada de rede/CRM é feita por este orquestrador.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def executar(nome: str, args: list[str], env: dict[str, str], timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / nome), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        banco_temporario = env.get("DASHBOARD_DB", "")
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        if banco_temporario:
            stdout = stdout.replace(banco_temporario, "<sqlite-temporario>")
            stderr = stderr.replace(banco_temporario, "<sqlite-temporario>")
        return {
            "etapa": nome,
            "codigo_saida": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "etapa": nome,
            "codigo_saida": 124,
            "stdout": "",
            "stderr": f"Tempo limite de {timeout}s excedido",
        }


def consultar_banco(path: Path) -> dict[str, Any]:
    # URI mode=ro evita criar um arquivo se o caminho estiver errado.
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        fatos = con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0]
        dias = con.execute("SELECT COUNT(DISTINCT data) FROM fatos").fetchone()[0]
        logs = con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0]
        snapshots = con.execute("SELECT COUNT(*) FROM acordos_posicao").fetchone()[0]
        tipos = dict(con.execute("SELECT tipo, COUNT(*) FROM fatos GROUP BY tipo").fetchall())
    return {
        "fatos": fatos,
        "dias_com_fatos": dias,
        "registros_log_importacao": logs,
        "snapshots_acordo": snapshots,
        "fatos_por_tipo": tipos,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita, simula e importa duas vezes em SQLite temporário; nunca chama o CRM."
    )
    parser.add_argument("arquivo", help="JSON local de resposta consolidada")
    parser.add_argument("--relatorio", help="salva relatório JSON neste caminho")
    args = parser.parse_args(argv)

    entrada = Path(args.arquivo).expanduser().resolve()
    report: dict[str, Any] = {
        "ferramenta": "validar_integracao_local",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivo": entrada.name,
        "crm_consultas": 0,
        "banco_persistente": False,
        "etapas": [],
        "metricas": {},
        "status": "FAIL",
    }

    if not entrada.is_file():
        report["etapas"].append({"etapa": "arquivo_local", "status": "FAIL", "detalhe": "Arquivo não encontrado"})
        return finalizar(report, args.relatorio, 2)

    conteudo = entrada.read_bytes()
    report["sha256_arquivo"] = hashlib.sha256(conteudo).hexdigest()

    try:
        json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report["etapas"].append({"etapa": "arquivo_local", "status": "FAIL", "detalhe": f"JSON inválido: {exc.__class__.__name__}"})
        return finalizar(report, args.relatorio, 2)

    report["etapas"].append({"etapa": "arquivo_local", "status": "OK", "detalhe": "Arquivo legível e JSON sintaticamente válido"})

    with tempfile.TemporaryDirectory(prefix="caixa-futuro-integracao-") as diretorio:
        db = Path(diretorio) / "integracao.db"
        env = os.environ.copy()
        env["DASHBOARD_DB"] = str(db)
        # Não passar credenciais para os subprocessos: este pipeline não consulta a rede.
        env.pop("CRM_TOKEN", None)
        env.pop("CRM_COOKIE", None)
        env.pop("CRM_URL", None)

        auditoria = executar("auditar_resposta.py", [str(entrada)], env)
        report["etapas"].append({
            "etapa": "auditoria_financeira",
            "status": "OK" if auditoria["codigo_saida"] == 0 else "FAIL",
            "codigo_saida": auditoria["codigo_saida"],
            "saida": auditoria["stdout"],
            "erro": auditoria["stderr"],
        })
        if auditoria["codigo_saida"] != 0:
            report["etapas"].append({"etapa": "importacao", "status": "SKIPPED", "detalhe": "Bloqueada porque a auditoria não foi aprovada"})
            report["status"] = "BLOCKED"
            return finalizar(report, args.relatorio, 1)

        dry = executar("importar.py", ["--arquivo", str(entrada), "--dry-run"], env)
        dry_ok = dry["codigo_saida"] == 0 and not db.exists()
        report["etapas"].append({
            "etapa": "dry_run",
            "status": "OK" if dry_ok else "FAIL",
            "codigo_saida": dry["codigo_saida"],
            "saida": dry["stdout"],
            "erro": dry["stderr"],
            "banco_nao_criado": not db.exists(),
        })
        if not dry_ok:
            report["etapas"].append({"etapa": "importacao", "status": "SKIPPED", "detalhe": "Dry-run falhou ou abriu/criou banco"})
            return finalizar(report, args.relatorio, 1)

        primeira = executar("importar.py", ["--arquivo", str(entrada)], env)
        import_ok = primeira["codigo_saida"] == 0 and db.is_file()
        report["etapas"].append({
            "etapa": "importacao_temporaria_1",
            "status": "OK" if import_ok else "FAIL",
            "codigo_saida": primeira["codigo_saida"],
            "saida": primeira["stdout"],
            "erro": primeira["stderr"],
        })
        if not import_ok:
            return finalizar(report, args.relatorio, 1)

        try:
            estado_1 = consultar_banco(db)
        except (sqlite3.Error, OSError) as exc:
            report["etapas"].append({"etapa": "leitura_temporaria_1", "status": "FAIL", "detalhe": exc.__class__.__name__})
            return finalizar(report, args.relatorio, 1)

        segunda = executar("importar.py", ["--arquivo", str(entrada)], env)
        segunda_ok = segunda["codigo_saida"] == 0
        report["etapas"].append({
            "etapa": "reimportacao_mesmo_dia",
            "status": "OK" if segunda_ok else "FAIL",
            "codigo_saida": segunda["codigo_saida"],
            "saida": segunda["stdout"],
            "erro": segunda["stderr"],
        })
        if not segunda_ok:
            return finalizar(report, args.relatorio, 1)

        try:
            estado_2 = consultar_banco(db)
        except (sqlite3.Error, OSError) as exc:
            report["etapas"].append({"etapa": "leitura_temporaria_2", "status": "FAIL", "detalhe": exc.__class__.__name__})
            return finalizar(report, args.relatorio, 1)

        idempotente = (
            estado_1["fatos"] == estado_2["fatos"]
            and estado_1["dias_com_fatos"] == estado_2["dias_com_fatos"]
            and estado_2["registros_log_importacao"] == estado_1["registros_log_importacao"] + 1
        )
        report["etapas"].append({
            "etapa": "idempotencia_fatos",
            "status": "OK" if idempotente else "FAIL",
            "detalhe": "Reimportar a mesma resposta mantém o conjunto de fatos e registra a nova execução",
            "antes": estado_1,
            "depois": estado_2,
        })
        if not idempotente:
            return finalizar(report, args.relatorio, 1)

        diagnostico = executar("diagnosticar_banco.py", [str(db), "--json"], env)
        try:
            diagnostico_json = json.loads(diagnostico["stdout"])
            diagnostico_ok = diagnostico["codigo_saida"] == 0 and diagnostico_json.get("status") == "OK"
        except json.JSONDecodeError:
            diagnostico_json = None
            diagnostico_ok = False
        report["etapas"].append({
            "etapa": "diagnostico_banco",
            "status": "OK" if diagnostico_ok else "FAIL",
            "codigo_saida": diagnostico["codigo_saida"],
            "resumo": diagnostico_json.get("summary") if diagnostico_json else None,
            "erro": diagnostico["stderr"],
        })
        report["metricas"] = estado_2
        report["metricas"]["diagnostico_status"] = diagnostico_json.get("status") if diagnostico_json else None
        report["status"] = "PASSED" if diagnostico_ok else "FAIL"

    return finalizar(report, args.relatorio, 0 if report["status"] == "PASSED" else 1)


def finalizar(report: dict[str, Any], caminho: str | None, codigo: int) -> int:
    saida = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if caminho:
        destino = Path(caminho).expanduser().resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(saida + "\n", encoding="utf-8")
    print(saida)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
