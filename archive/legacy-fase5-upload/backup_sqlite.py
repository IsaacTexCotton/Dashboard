#!/usr/bin/env python3
"""Cria e verifica backups consistentes de SQLite, sem sobrescrever arquivos.

Exemplos:
  python backup_sqlite.py criar cobranca.db --destino backups/cobranca-antes.db
  python backup_sqlite.py verificar backups/cobranca-antes.db

Cada backup vem acompanhado de <backup>.manifest.json, contendo tamanho, SHA-256,
resultado de integrity_check e contagens agregadas por tabela. O backup é feito
pela API online backup do SQLite e não por cópia simples do arquivo .db.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1


class ErroBackup(RuntimeError):
    """Erro de criação ou verificação de backup."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _abrir_leitura(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def _integridade(con: sqlite3.Connection) -> list[str]:
    return [str(row[0]) for row in con.execute("PRAGMA integrity_check").fetchall()]


def _tabelas_e_contagens(con: sqlite3.Connection) -> dict[str, int]:
    nomes = [row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    resultado: dict[str, int] = {}
    for nome in nomes:
        # O nome vem do catálogo do próprio SQLite; aspas são escapadas para SQL.
        seguro = '"' + nome.replace('"', '""') + '"'
        resultado[nome] = int(con.execute(f"SELECT COUNT(*) FROM {seguro}").fetchone()[0])
    return resultado


def _manifest_path(backup: Path) -> Path:
    return Path(str(backup) + ".manifest.json")


def criar_backup(origem: str | Path, destino: str | Path | None = None) -> dict[str, Any]:
    source = Path(origem).expanduser().resolve()
    if not source.is_file():
        raise ErroBackup(f"Banco de origem não encontrado: {source}")

    if destino is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = source.parent / f"{source.stem}-backup-{stamp}{source.suffix or '.sqlite3'}"
    else:
        target = Path(destino).expanduser().resolve()

    manifest_path = _manifest_path(target)
    if target == source:
        raise ErroBackup("O destino não pode ser o próprio banco de origem")
    if not target.parent.is_dir():
        raise ErroBackup(f"Diretório de destino não existe: {target.parent}")
    if target.exists():
        raise FileExistsError(f"O backup já existe; não será sobrescrito: {target}")
    if manifest_path.exists():
        raise FileExistsError(f"O manifesto já existe; não será sobrescrito: {manifest_path}")

    reservado = False
    manifesto_criado = False
    sucesso = False
    src: sqlite3.Connection | None = None
    dst: sqlite3.Connection | None = None
    try:
        # Criação exclusiva evita substituir backups de uma execução anterior.
        with target.open("xb"):
            reservado = True
        src = _abrir_leitura(source)
        dst = sqlite3.connect(str(target), timeout=15)
        src.backup(dst)
        dst.commit()
        checks = _integridade(dst)
        if checks != ["ok"]:
            raise ErroBackup("O backup criado não passou em PRAGMA integrity_check: " + "; ".join(checks))
        tables = _tabelas_e_contagens(dst)
        user_version = int(dst.execute("PRAGMA user_version").fetchone()[0])
        dst.close()
        dst = None
        src.close()
        src = None

        metadata = {
            "manifest_version": MANIFEST_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_file": source.name,
            "backup_file": target.name,
            "backup_size_bytes": target.stat().st_size,
            "backup_sha256": _sha256(target),
            "integrity_check": "ok",
            "user_version": user_version,
            "tables": tables,
        }
        # Modo x impede substituir um manifesto mesmo se aparecer entre as verificações.
        with manifest_path.open("x", encoding="utf-8") as fh:
            manifesto_criado = True
            json.dump(metadata, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        sucesso = True
        return metadata
    except Exception:
        # Remove apenas o arquivo reservado por esta execução se não publicou manifesto.
        if manifesto_criado and not sucesso:
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass
        if reservado and not sucesso:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()


def verificar_backup(backup: str | Path, manifest: str | Path | None = None) -> dict[str, Any]:
    target = Path(backup).expanduser().resolve()
    manifest_path = Path(manifest).expanduser().resolve() if manifest else _manifest_path(target)
    report: dict[str, Any] = {
        "status": "OK",
        "backup": target.name,
        "manifest": manifest_path.name,
        "checks": [],
    }

    def add(name: str, status: str, detail: str) -> None:
        report["checks"].append({"check": name, "status": status, "detail": detail})
        if status != "OK":
            report["status"] = "FAIL"

    if not target.is_file():
        add("arquivo_backup", "FAIL", "Arquivo de backup não encontrado")
        return report
    add("arquivo_backup", "OK", f"Arquivo presente ({target.stat().st_size} bytes)")

    if not manifest_path.is_file():
        add("manifesto", "FAIL", "Manifesto ausente; não é possível validar origem e hash esperado")
        return report
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add("manifesto", "FAIL", f"Manifesto inválido ou ilegível: {exc}")
        return report
    if not isinstance(metadata, dict) or metadata.get("manifest_version") != MANIFEST_VERSION:
        add("manifesto", "FAIL", "Versão ou estrutura do manifesto não suportada")
        return report
    if metadata.get("backup_file") != target.name:
        add("nome_backup", "FAIL", "Nome do arquivo diverge do manifesto")
    else:
        add("nome_backup", "OK", "Nome corresponde ao manifesto")

    actual_size = target.stat().st_size
    if metadata.get("backup_size_bytes") == actual_size:
        add("tamanho", "OK", f"Tamanho confere ({actual_size} bytes)")
    else:
        add("tamanho", "FAIL", f"Tamanho divergente: manifesto={metadata.get('backup_size_bytes')}, arquivo={actual_size}")

    try:
        actual_hash = _sha256(target)
        expected_hash = metadata.get("backup_sha256")
        if isinstance(expected_hash, str) and actual_hash == expected_hash:
            add("sha256", "OK", "SHA-256 confere com o manifesto")
        else:
            add("sha256", "FAIL", "SHA-256 não confere com o manifesto")
    except OSError as exc:
        add("sha256", "FAIL", f"Não foi possível calcular SHA-256: {exc}")

    try:
        con = _abrir_leitura(target)
        try:
            checks = _integridade(con)
            if checks == ["ok"]:
                add("integridade_sqlite", "OK", "PRAGMA integrity_check retornou ok")
            else:
                add("integridade_sqlite", "FAIL", "; ".join(checks[:10]))
            current_tables = _tabelas_e_contagens(con)
        finally:
            con.close()
        expected_tables = metadata.get("tables")
        if isinstance(expected_tables, dict) and current_tables == expected_tables:
            add("contagens_tabelas", "OK", "Tabelas e contagens correspondem ao manifesto")
        else:
            add("contagens_tabelas", "FAIL", "Tabelas ou contagens divergem do manifesto")
    except sqlite3.DatabaseError as exc:
        add("integridade_sqlite", "FAIL", f"SQLite não conseguiu ler o backup: {exc}")
    except OSError as exc:
        add("integridade_sqlite", "FAIL", f"Falha ao abrir backup em modo somente leitura: {exc}")

    report["created_at_utc"] = metadata.get("created_at_utc")
    report["source_file"] = metadata.get("source_file")
    report["backup_sha256"] = metadata.get("backup_sha256")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Criar e verificar backups SQLite do CAIXA FUTURO")
    subs = parser.add_subparsers(dest="comando", required=True)
    p_create = subs.add_parser("criar", help="cria backup consistente sem sobrescrever arquivos existentes")
    p_create.add_argument("origem", help="caminho do SQLite existente")
    p_create.add_argument("--destino", help="caminho de saída; diretório deve existir e arquivos não podem existir")
    p_check = subs.add_parser("verificar", help="verifica hash, tamanho, integridade e contagens")
    p_check.add_argument("backup", help="caminho do backup")
    p_check.add_argument("--manifesto", help="caminho do manifesto; padrão: <backup>.manifest.json")
    args = parser.parse_args(argv)

    try:
        if args.comando == "criar":
            resultado = criar_backup(args.origem, args.destino)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return 0
        resultado = verificar_backup(args.backup, args.manifesto)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0 if resultado["status"] == "OK" else 1
    except (ErroBackup, FileExistsError, OSError, sqlite3.Error) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
