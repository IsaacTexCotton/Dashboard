#!/usr/bin/env python3
"""Valida fluxo completo com JSON local e SQLite temporário; nunca chama o CRM."""
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
        proc = subprocess.run([sys.executable, str(ROOT / nome), *args], cwd=ROOT, env=env,
                              text=True, capture_output=True, timeout=timeout, check=False)
        db = env.get("DASHBOARD_DB", "")
        return {"etapa": nome, "codigo_saida": proc.returncode,
                "stdout": proc.stdout.strip().replace(db, "<sqlite-temporario>") if db else proc.stdout.strip(),
                "stderr": proc.stderr.strip().replace(db, "<sqlite-temporario>") if db else proc.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"etapa": nome, "codigo_saida": 124, "stdout": "", "stderr": f"Tempo limite de {timeout}s excedido"}


def consultar_banco(path: Path) -> dict[str, Any]:
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        fatos = con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0]
        dias = con.execute("SELECT COUNT(DISTINCT data) FROM fatos").fetchone()[0]
        logs = con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0]
        snapshots = con.execute("SELECT COUNT(*) FROM acordos_posicao").fetchone()[0]
        tipos = dict(con.execute("SELECT tipo, COUNT(*) FROM fatos GROUP BY tipo").fetchall())
    return {"fatos": fatos, "dias_com_fatos": dias, "registros_log_importacao": logs,
            "snapshots_acordo": snapshots, "fatos_por_tipo": tipos}


def finalizar(report: dict[str, Any], caminho: str | None, codigo: int) -> int:
    saida = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if caminho:
        destino = Path(caminho).expanduser().resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(saida + "\n", encoding="utf-8")
    print(saida)
    return codigo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita, simula e reimporta em SQLite temporário; nunca chama o CRM."
    )
    parser.add_argument("arquivo", help="JSON local de resposta consolidada")
    parser.add_argument("--relatorio", help="salva relatório JSON neste caminho")
    args = parser.parse_args(argv)
    entrada = Path(args.arquivo).expanduser().resolve()
    report: dict[str, Any] = {
        "ferramenta": "validar_integracao_local",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivo": entrada.name, "crm_consultas": 0, "banco_persistente": False,
        "etapas": [], "metricas": {}, "status": "FAIL",
    }
    if not entrada.is_file():
        report["etapas"].append({"etapa": "arquivo_local", "status": "FAIL", "detalhe": "Arquivo não encontrado"})
        return finalizar(report, args.relatorio, 2)
    conteudo = entrada.read_bytes()
    report["sha256_arquivo"] = hashlib.sha256(conteudo).hexdigest()
    try:
        json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report["etapas"].append({"etapa": "arquivo_local", "status": "FAIL",
                                 "detalhe": f"JSON inválido: {exc.__class__.__name__}"})
        return finalizar(report, args.relatorio, 2)
    report["etapas"].append({"etapa": "arquivo_local", "status": "OK",
                             "detalhe": "Arquivo legível e JSON sintaticamente válido"})

    with tempfile.TemporaryDirectory(prefix="caixa-futuro-integracao-") as temp_dir:
        db = Path(temp_dir) / "integracao.db"
        env = os.environ.copy()
        env["DASHBOARD_DB"] = str(db)
        for key in ("CRM_TOKEN", "CRM_COOKIE", "CRM_URL"):
            env.pop(key, None)

        auditoria = executar("auditar_resposta.py", [str(entrada)], env)
        report["etapas"].append({"etapa": "auditoria_financeira",
            "status": "OK" if auditoria["codigo_saida"] == 0 else "FAIL",
            "codigo_saida": auditoria["codigo_saida"], "saida": auditoria["stdout"], "erro": auditoria["stderr"]})
        if auditoria["codigo_saida"] != 0:
            report["etapas"].append({"etapa": "importacao", "status": "SKIPPED",
                                     "detalhe": "Bloqueada porque a auditoria não foi aprovada"})
            report["status"] = "BLOCKED"
            return finalizar(report, args.relatorio, 1)

        dry = executar("importar.py", ["--arquivo", str(entrada), "--dry-run"], env)
        dry_ok = dry["codigo_saida"] == 0 and not db.exists()
        report["etapas"].append({"etapa": "dry_run", "status": "OK" if dry_ok else "FAIL",
            "codigo_saida": dry["codigo_saida"], "saida": dry["stdout"], "erro": dry["stderr"],
            "banco_nao_criado": not db.exists()})
        if not dry_ok:
            report["etapas"].append({"etapa": "importacao", "status": "SKIPPED",
                                     "detalhe": "Dry-run falhou ou abriu/criou banco"})
            return finalizar(report, args.relatorio, 1)

        first = executar("importar.py", ["--arquivo", str(entrada)], env)
        import_ok = first["codigo_saida"] == 0 and db.is_file()
        report["etapas"].append({"etapa": "importacao_temporaria_1",
            "status": "OK" if import_ok else "FAIL", "codigo_saida": first["codigo_saida"],
            "saida": first["stdout"], "erro": first["stderr"]})
        if not import_ok:
            return finalizar(report, args.relatorio, 1)
        try:
            state_1 = consultar_banco(db)
        except (sqlite3.Error, OSError) as exc:
            report["etapas"].append({"etapa": "leitura_temporaria_1", "status": "FAIL",
                                     "detalhe": exc.__class__.__name__})
            return finalizar(report, args.relatorio, 1)

        second = executar("importar.py", ["--arquivo", str(entrada)], env)
        second_ok = second["codigo_saida"] == 0
        report["etapas"].append({"etapa": "reimportacao_mesmo_dia",
            "status": "OK" if second_ok else "FAIL", "codigo_saida": second["codigo_saida"],
            "saida": second["stdout"], "erro": second["stderr"]})
        if not second_ok:
            return finalizar(report, args.relatorio, 1)
        try:
            state_2 = consultar_banco(db)
        except (sqlite3.Error, OSError) as exc:
            report["etapas"].append({"etapa": "leitura_temporaria_2", "status": "FAIL",
                                     "detalhe": exc.__class__.__name__})
            return finalizar(report, args.relatorio, 1)

        idempotente = (state_1["fatos"] == state_2["fatos"]
            and state_1["dias_com_fatos"] == state_2["dias_com_fatos"]
            and state_2["registros_log_importacao"] == state_1["registros_log_importacao"] + 1)
        report["etapas"].append({"etapa": "idempotencia_fatos",
            "status": "OK" if idempotente else "FAIL",
            "detalhe": "Reimportação mantém fatos e registra nova execução",
            "antes": state_1, "depois": state_2})
        if not idempotente:
            return finalizar(report, args.relatorio, 1)

        diagnostic = executar("diagnosticar_banco.py", [str(db), "--json"], env)
        try:
            diagnostic_json = json.loads(diagnostic["stdout"])
            diagnostic_ok = diagnostic["codigo_saida"] == 0 and diagnostic_json.get("status") == "OK"
        except json.JSONDecodeError:
            diagnostic_json, diagnostic_ok = None, False
        report["etapas"].append({"etapa": "diagnostico_banco",
            "status": "OK" if diagnostic_ok else "FAIL", "codigo_saida": diagnostic["codigo_saida"],
            "resumo": diagnostic_json.get("summary") if diagnostic_json else None,
            "erro": diagnostic["stderr"]})
        report["metricas"] = state_2
        report["metricas"]["diagnostico_status"] = diagnostic_json.get("status") if diagnostic_json else None
        report["status"] = "PASSED" if diagnostic_ok else "FAIL"
    return finalizar(report, args.relatorio, 0 if report["status"] == "PASSED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
