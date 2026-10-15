"""Confere a série histórica sintética embutida na demonstração pública."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auditar_resposta
import importar


class DemoHistoricoMultidatasTestes(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "web-demo" / "index.html").read_text(encoding="utf-8")
        match = re.search(
            r'<script id="demo-history" type="application/json">\s*(.*?)\s*</script>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "histórico sintético não encontrado no HTML")
        self.history = json.loads(match.group(1))

    def test_historico_tem_15_datas_consecutivas(self):
        self.assertEqual(len(self.history), 15)
        self.assertEqual(
            [payload["data"]["inicio"] for payload in self.history],
            [f"2026-10-{day:02d}" for day in range(1, 16)],
        )
        for payload in self.history:
            with self.subTest(dia=payload["data"]["inicio"]):
                dia = payload["data"]["inicio"]
                self.assertEqual(payload["data"]["fim"], dia)
                self.assertTrue(payload["success"])

    def test_primeiras_14_datas_sao_as_fixtures_versionadas(self):
        fixtures = ROOT / "tests" / "fixtures" / "respostas_ficticias"
        for day, payload in enumerate(self.history[:14], start=1):
            caminho = fixtures / f"2026-10-{day:02d}.json"
            with self.subTest(dia=day):
                self.assertEqual(payload, json.loads(caminho.read_text(encoding="utf-8")))

    def test_ultima_data_corresponde_a_amostra_ficticia_existente(self):
        amostra = json.loads((ROOT / "amostra_resposta_ficticia.json").read_text(encoding="utf-8"))
        self.assertEqual(self.history[-1], amostra)

    def test_todas_as_datas_passam_na_auditoria_e_normalizacao(self):
        for payload in self.history:
            with self.subTest(dia=payload["data"]["inicio"]):
                checks = auditar_resposta.auditar(payload)
                bloqueios = [item for item in checks if item.status in ("DIVERGÊNCIA", "PENDENTE")]
                self.assertEqual(bloqueios, [], str(bloqueios))
                _, fatos, _ = importar.normalizar(payload, payload["data"]["inicio"])
                esperados = sum(
                    len(payload["data"][grupo]["porUsuario"])
                    for grupo in ("depositos", "acordos", "promessas", "contatos")
                )
                self.assertEqual(len(fatos), esperados)

    def test_interface_identifica_historico_como_ficticio_e_sem_crm(self):
        self.assertIn("Histórico fictício", self.html)
        self.assertIn("Sem conexão com CRM", self.html)
        self.assertIn("não um histórico operacional", self.html)
        self.assertIn('value="2026-10-01"', self.html)
        self.assertIn('value="2026-10-15"', self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
