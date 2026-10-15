import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backup_sqlite


class BackupSQLiteTestes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "origem.db"
        self.backup = self.root / "copia.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
            CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, nome TEXT);
            CREATE TABLE fatos (data TEXT NOT NULL, usuario TEXT NOT NULL, tipo TEXT NOT NULL);
            INSERT INTO usuarios VALUES ('USR1', 'Pessoa Teste');
            INSERT INTO fatos VALUES ('2026-10-13', 'USR1', 'contato');
        """)
        con.commit()
        con.close()

    def test_cria_backup_e_manifesto(self):
        metadata = backup_sqlite.criar_backup(self.db, self.backup)
        self.assertTrue(self.backup.is_file())
        self.assertTrue(Path(str(self.backup) + ".manifest.json").is_file())
        self.assertEqual(metadata["integrity_check"], "ok")
        self.assertEqual(metadata["tables"], {"fatos": 1, "usuarios": 1})

    def test_verifica_backup_recente(self):
        backup_sqlite.criar_backup(self.db, self.backup)
        report = backup_sqlite.verificar_backup(self.backup)
        self.assertEqual(report["status"], "OK", report)
        self.assertTrue(all(check["status"] == "OK" for check in report["checks"]))

    def test_recusa_sobrescrever_backup_existente(self):
        self.backup.write_bytes(b"nao sobrescrever")
        with self.assertRaises(FileExistsError):
            backup_sqlite.criar_backup(self.db, self.backup)
        self.assertEqual(self.backup.read_bytes(), b"nao sobrescrever")

    def test_recusa_manifesto_existente_sem_backup(self):
        manifest = Path(str(self.backup) + ".manifest.json")
        manifest.write_text("preservar", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            backup_sqlite.criar_backup(self.db, self.backup)
        self.assertFalse(self.backup.exists())
        self.assertEqual(manifest.read_text(encoding="utf-8"), "preservar")

    def test_recusa_destino_igual_origem(self):
        with self.assertRaisesRegex(backup_sqlite.ErroBackup, "próprio banco"):
            backup_sqlite.criar_backup(self.db, self.db)

    def test_recusa_diretorio_inexistente(self):
        with self.assertRaisesRegex(backup_sqlite.ErroBackup, "não existe"):
            backup_sqlite.criar_backup(self.db, self.root / "ausente" / "copia.db")

    def test_detecta_alteracao_de_bytes(self):
        backup_sqlite.criar_backup(self.db, self.backup)
        with self.backup.open("ab") as fh:
            fh.write(b"mudanca")
        report = backup_sqlite.verificar_backup(self.backup)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("FAIL", {c["status"] for c in report["checks"]})

    def test_detecta_manifesto_com_contagens_alteradas(self):
        backup_sqlite.criar_backup(self.db, self.backup)
        manifest = Path(str(self.backup) + ".manifest.json")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["tables"]["fatos"] = 99
        manifest.write_text(json.dumps(data), encoding="utf-8")
        report = backup_sqlite.verificar_backup(self.backup)
        self.assertEqual(report["status"], "FAIL")
        checks = {c["check"]: c["status"] for c in report["checks"]}
        self.assertEqual(checks["contagens_tabelas"], "FAIL")

    def test_detecta_manifesto_ausente(self):
        backup_sqlite.criar_backup(self.db, self.backup)
        Path(str(self.backup) + ".manifest.json").unlink()
        report = backup_sqlite.verificar_backup(self.backup)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("manifesto", {c["check"] for c in report["checks"]})

    def test_falha_com_sqlite_invalido_remove_backup_parcial(self):
        invalid = self.root / "nao-sqlite.db"
        invalid.write_text("isto nao e um banco sqlite", encoding="utf-8")
        with self.assertRaises(sqlite3.DatabaseError):
            backup_sqlite.criar_backup(invalid, self.backup)
        self.assertFalse(self.backup.exists())
        self.assertFalse(Path(str(self.backup) + ".manifest.json").exists())

    def test_backup_tem_os_registros_no_destino(self):
        backup_sqlite.criar_backup(self.db, self.backup)
        con = sqlite3.connect(f"file:{self.backup}?mode=ro", uri=True)
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 1)
        finally:
            con.close()

    def test_cli_criar_e_verificar(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "backup_sqlite.py"), "criar", str(self.db), "--destino", str(self.backup)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "backup_sqlite.py"), "verificar", str(self.backup)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
