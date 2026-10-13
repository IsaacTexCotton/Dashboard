import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IntegracaoLocalTestes(unittest.TestCase):
    def executar(self, arquivo, *args):
        return subprocess.run([sys.executable, str(ROOT / "validar_integracao_local.py"),
                               str(arquivo), *args], cwd=ROOT, text=True,
                              capture_output=True, check=False, timeout=90)

    def test_fluxo_completo_com_amostra_ficticia(self):
        proc = self.executar(ROOT / "amostra_resposta.json")
        self.assertEqual(proc.returncode, 0, proc.stderr + "\n" + proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASSED")
        self.assertEqual(report["crm_consultas"], 0)
        self.assertFalse(report["banco_persistente"])
        self.assertEqual(report["metricas"]["fatos"], 5)
        self.assertEqual(report["metricas"]["dias_com_fatos"], 1)
        self.assertEqual(report["metricas"]["registros_log_importacao"], 2)
        self.assertEqual(report["metricas"]["diagnostico_status"], "OK")
        self.assertTrue(all(etapa["status"] == "OK" for etapa in report["etapas"]))

    def test_divergencia_financeira_bloqueia_importacao(self):
        payload = json.loads((ROOT / "amostra_resposta.json").read_text(encoding="utf-8"))
        payload["data"]["depositos"]["valorTotal"] += 100
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "divergente.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            proc = self.executar(path)
        self.assertEqual(proc.returncode, 1, proc.stderr + "\n" + proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "BLOCKED")
        etapas = {etapa["etapa"]: etapa["status"] for etapa in report["etapas"]}
        self.assertEqual(etapas["auditoria_financeira"], "FAIL")
        self.assertEqual(etapas["importacao"], "SKIPPED")
        self.assertNotIn("dry_run", etapas)

    def test_arquivo_ausente_retorna_codigo_dois(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ausente.json"
            proc = self.executar(path)
        self.assertEqual(proc.returncode, 2)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["etapas"][0]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
