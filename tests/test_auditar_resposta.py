import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auditar_resposta
import importar

with (ROOT / "amostra_resposta.json").open(encoding="utf-8") as f:
    AMOSTRA = json.load(f)


class AuditoriaTestes(unittest.TestCase):
    def test_amostra_reconcilia_totais_aditivos(self):
        checks = auditar_resposta.auditar(AMOSTRA)
        somaveis = [c for c in checks if c.status != "NÃO ADITIVO"]
        self.assertTrue(somaveis)
        self.assertTrue(all(c.status == "OK" for c in somaveis), somaveis)

    def test_detecta_diferenca_financeira(self):
        payload = copy.deepcopy(AMOSTRA)
        payload["data"]["depositos"]["valorTotal"] = 25001
        checks = auditar_resposta.auditar(payload)
        check = next(c for c in checks if c.grupo == "depositos" and c.metrica == "valorTotal")
        self.assertEqual(check.status, "DIVERGÊNCIA")
        self.assertEqual(check.diferenca, "1.0")

    def test_respeita_tolerancia_de_centavo(self):
        payload = copy.deepcopy(AMOSTRA)
        payload["data"]["depositos"]["valorTotal"] = 25000.01
        checks = auditar_resposta.auditar(payload, Decimal("0.01"))
        check = next(c for c in checks if c.metrica == "valorTotal")
        self.assertEqual(check.status, "OK")

    def test_total_ausente_fica_pendente(self):
        payload = copy.deepcopy(AMOSTRA)
        del payload["data"]["promessas"]["quebradoTotal"]
        checks = auditar_resposta.auditar(payload)
        self.assertEqual(next(c for c in checks if c.metrica == "quebradoTotal").status, "PENDENTE")

    def test_contatos_unicos_nao_sao_somados(self):
        payload = copy.deepcopy(AMOSTRA)
        payload["data"]["contatos"]["porUsuario"].append({
            "usuario": "NEGOCIADOR.B", "nome": "Negociador B",
            "contatosUnicos": 100, "registrosTotais": 20})
        payload["data"]["contatos"]["registrosTotaisTotal"] = 150
        checks = auditar_resposta.auditar(payload)
        check = next(c for c in checks if "não aditivo" in c.metrica)
        self.assertEqual(check.status, "NÃO ADITIVO")

    def test_rejeita_resposta_invalida(self):
        payload = copy.deepcopy(AMOSTRA)
        payload["success"] = False
        with self.assertRaises(importar.ErroValidacao):
            auditar_resposta.auditar(payload)

    def test_cli_local_passa(self):
        proc = subprocess.run([sys.executable, str(ROOT / "auditar_resposta.py"),
                               str(ROOT / "amostra_resposta.json")],
                              cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("NÃO ADITIVO", proc.stdout)

    def test_cli_divergencia_retorna_um(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "resposta.json"
            payload = copy.deepcopy(AMOSTRA)
            payload["data"]["depositos"]["quantidadeTotal"] = 16
            path.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "auditar_resposta.py"), str(path)],
                                  cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("DIVERGÊNCIA", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
