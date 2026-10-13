import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backup_sqlite
import diagnosticar_banco
import importar

with (ROOT / "amostra_resposta.json").open(encoding="utf-8") as fh:
    AMOSTRA = json.load(fh)


class RecuperacaoBackupTestes(unittest.TestCase):
    def test_backup_verificacao_restauracao_e_diagnostico(self):
        with tempfile.TemporaryDirectory(prefix="caixa-recuperacao-") as td:
            root = Path(td)
            origem = root / "origem.sqlite3"
            backup = root / "backup.sqlite3"
            restaurado = root / "restaurado.sqlite3"

            with sqlite3.connect(origem) as con:
                con.executescript(importar.SCHEMA)
                importar.gravar(con, "2026-10-13", AMOSTRA, "teste-recuperacao")

            origem_antes = diagnosticar_banco.diagnosticar(origem)
            self.assertEqual(origem_antes["status"], "OK")

            manifesto = backup_sqlite.criar_backup(origem, backup)
            self.assertEqual(manifesto["integrity_check"], "ok")
            verificado = backup_sqlite.verificar_backup(backup)
            self.assertEqual(verificado["status"], "OK", verificado)

            # Restauração somente em outro arquivo temporário; nunca sobrescreve a origem.
            with sqlite3.connect(backup) as src, sqlite3.connect(restaurado) as dst:
                src.backup(dst)

            restaurado_diag = diagnosticar_banco.diagnosticar(restaurado)
            self.assertEqual(restaurado_diag["status"], "OK", restaurado_diag)
            self.assertEqual(origem_antes["metrics"], restaurado_diag["metrics"])

            with sqlite3.connect(origem) as src, sqlite3.connect(restaurado) as dst:
                for tabela in ("usuarios", "fatos", "acordos_posicao", "importacoes"):
                    sql = f'SELECT * FROM "{tabela}" ORDER BY 1'
                    self.assertEqual(src.execute(sql).fetchall(), dst.execute(sql).fetchall(), tabela)

            self.assertTrue(origem.exists())
            self.assertTrue(backup.exists())
            self.assertTrue(restaurado.exists())

    def test_manifesto_invalido_bloqueia_verificacao(self):
        with tempfile.TemporaryDirectory(prefix="caixa-manifesto-") as td:
            root = Path(td)
            origem = root / "origem.sqlite3"
            backup = root / "backup.sqlite3"
            with sqlite3.connect(origem) as con:
                con.executescript(importar.SCHEMA)
                importar.gravar(con, "2026-10-13", AMOSTRA, "teste-manifesto")
            backup_sqlite.criar_backup(origem, backup)
            Path(str(backup) + ".manifest.json").write_text("{invalido", encoding="utf-8")
            resultado = backup_sqlite.verificar_backup(backup)
            self.assertEqual(resultado["status"], "FAIL")
            self.assertTrue(any(x["check"] == "manifesto" and x["status"] == "FAIL"
                                for x in resultado["checks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
