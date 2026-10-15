import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import diagnosticar_banco
import importar
from migrar_schema_monetario import TABELA_ESTADO, migrar_schema_monetario

with (ROOT / "amostra_resposta.json").open(encoding="utf-8") as arquivo:
    AMOSTRA = json.load(arquivo)


class DiagnosticoBancoTestes(unittest.TestCase):
    def _criar_banco_valido(self, path):
        con = sqlite3.connect(path)
        con.executescript(importar.SCHEMA)
        importar.gravar(con, "2026-10-13", AMOSTRA, "teste")
        con.close()

    def test_banco_valido_retorna_ok_e_metricas(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "teste.db"
            self._criar_banco_valido(path)
            report = diagnosticar_banco.diagnosticar(path)
        self.assertEqual(report["status"], "OK", report["checks"])
        self.assertEqual(report["metrics"]["fact_rows"], 5)
        self.assertEqual(report["metrics"]["fact_days"], 1)
        self.assertEqual(report["metrics"]["facts_by_type"]["deposito"]["rows"], 2)
        self.assertEqual(report["mode"], "read-only")

    def _criar_banco_fase_monetaria(self, path, *, fase, centavos):
        con = sqlite3.connect(path)
        con.executescript(importar.SCHEMA)
        con.execute("INSERT INTO usuarios(usuario,nome) VALUES ('U','Usuário')")
        con.execute(
            "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
            "valor_aberto,valor_quebrado,importado_em) "
            "VALUES ('2026-10-13','U','deposito',1,0,12.34,0.0,0.0,0.0,'agora')"
        )
        con.commit()
        migrar_schema_monetario(con)
        con.execute(
            "UPDATE fatos SET deposito_valor_centavos=?, monetario_fase=? "
            "WHERE data='2026-10-13' AND usuario='U'",
            (centavos, fase),
        )
        con.commit()
        con.close()

    def test_coerencia_fase_dual_compara_real_e_centavos_exatamente(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fase-dual.db"
            self._criar_banco_fase_monetaria(path, fase="dual", centavos=1234)
            report = diagnosticar_banco.diagnosticar(path)
        check = next(c for c in report["checks"] if c["check"] == "coerencia_fase_monetaria")
        self.assertEqual(check["status"], "OK", check["detail"])
        self.assertEqual(report["metrics"]["monetary_phase"]["verified_pairs"], 1)

    def test_coerencia_fase_dual_detecta_divergencia_real_centavos(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fase-divergente.db"
            self._criar_banco_fase_monetaria(path, fase="dual", centavos=1235)
            report = diagnosticar_banco.diagnosticar(path)
        check = next(c for c in report["checks"] if c["check"] == "coerencia_fase_monetaria")
        self.assertEqual(check["status"], "FAIL", check["detail"])
        self.assertEqual(report["metrics"]["monetary_phase"]["incoherences"], 1)

    def test_coerencia_fase_legado_com_centavos_ausentes_e_pendencia(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fase-legado.db"
            self._criar_banco_fase_monetaria(path, fase="legado", centavos=None)
            report = diagnosticar_banco.diagnosticar(path)
        check = next(c for c in report["checks"] if c["check"] == "coerencia_fase_monetaria")
        self.assertEqual(check["status"], "WARN", check["detail"])
        self.assertEqual(report["metrics"]["monetary_phase"]["legacy_pending_pairs"], 1)

    def test_fase_legado_apos_conciliacao_global_e_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legado-pos-conciliacao.db"
            self._criar_banco_fase_monetaria(path, fase="legado", centavos=None)
            con = sqlite3.connect(path)
            try:
                # Simula um estado inconsistente numa fixture sintética;
                # a transição normal usa verificar_conciliacao_monetaria.
                con.execute(
                    f"UPDATE {TABELA_ESTADO} SET fase='backfill_conciliado' WHERE id=1"
                )
                con.commit()
            finally:
                con.close()
            report = diagnosticar_banco.diagnosticar(path)
        check = next(c for c in report["checks"] if c["check"] == "coerencia_fase_monetaria")
        self.assertEqual(check["status"], "FAIL", check["detail"])
        self.assertIn("fase legado após backfill_conciliado", check["detail"])
        self.assertEqual(report["metrics"]["monetary_phase"]["legacy_pending_pairs"], 0)

    def test_banco_inexistente_nao_e_criado(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ausente.db"
            with self.assertRaises(FileNotFoundError):
                diagnosticar_banco.diagnosticar(path)
            self.assertFalse(path.exists())

    def test_tabela_ausente_retorna_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "parcial.db"
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE fatos (data TEXT)")
            con.commit()
            con.close()
            report = diagnosticar_banco.diagnosticar(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(c["check"] == "schema_tabelas" and c["status"] == "FAIL"
                            for c in report["checks"]))

    def test_tipo_fato_desconhecido(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tipo.db"
            con = sqlite3.connect(path)
            con.executescript(importar.SCHEMA)
            con.execute("INSERT INTO usuarios(usuario,nome) VALUES ('U','Usuário')")
            con.execute("INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("2026-10-13", "U", "tipo_invalido", 1, 0, 10.0, 0.0, 0.0, 0.0, "agora"))
            con.commit()
            con.close()
            report = diagnosticar_banco.diagnosticar(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(next(c for c in report["checks"] if c["check"] == "tipos_fato")["status"], "FAIL")

    def test_usuario_orfao_gera_aviso(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "orfaos.db"
            con = sqlite3.connect(path)
            con.executescript(importar.SCHEMA)
            con.execute("INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("2026-10-13", "SEM_USUARIO", "contato", 1, 1, 0.0, 0.0, 0.0, 0.0, "agora"))
            con.commit()
            con.close()
            report = diagnosticar_banco.diagnosticar(path)
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(next(c for c in report["checks"] if c["check"] == "referencias_usuarios")["status"], "WARN")

    def test_nao_modifica_bytes_do_banco(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "teste.db"
            self._criar_banco_valido(path)
            antes = path.read_bytes()
            diagnosticar_banco.diagnosticar(path)
            depois = path.read_bytes()
        self.assertEqual(antes, depois)

    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "teste.db"
            self._criar_banco_valido(path)
            proc = subprocess.run([sys.executable, str(ROOT / "diagnosticar_banco.py"),
                                   str(path), "--json"], cwd=ROOT,
                                  capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["mode"], "read-only")

    def test_banco_ausente_nao_e_criado_pelo_cli(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ausente.db"
            proc = subprocess.run([sys.executable, str(ROOT / "diagnosticar_banco.py"), str(path)],
                                  cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
