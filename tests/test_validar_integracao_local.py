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
        self.assertEqual(report["contagem_fatos"]["origem_por_grupo"], {
            "depositos": 2, "acordos": 1, "promessas": 1, "contatos": 1,
        })
        self.assertEqual(report["contagem_fatos"]["origem_por_tipo"], {
            "deposito": 2, "acordo": 1, "promessa": 1, "contato": 1,
        })
        self.assertEqual(report["contagem_fatos"]["normalizados_por_tipo"],
                         report["contagem_fatos"]["origem_por_tipo"])
        self.assertEqual(report["contagem_fatos"]["persistidos_primeira_importacao_por_tipo"],
                         report["contagem_fatos"]["origem_por_tipo"])
        self.assertEqual(report["contagem_fatos"]["persistidos_apos_reimportacao_por_tipo"],
                         report["contagem_fatos"]["origem_por_tipo"])
        self.assertTrue(report["contagem_fatos"]["origem_confere_normalizados"])
        self.assertTrue(report["contagem_fatos"]["primeira_importacao_confere"])
        self.assertTrue(report["contagem_fatos"]["reimportacao_confere"])
        self.assertTrue(all(etapa["status"] == "OK" for etapa in report["etapas"]))

    def test_contagem_5_5_3_5_reconcilia_18_fatos_end_to_end(self):
        payload = json.loads((ROOT / "amostra_resposta.json").read_text(encoding="utf-8"))
        data = payload["data"]
        quantidades = {"depositos": 5, "acordos": 5, "promessas": 3, "contatos": 5}
        campos_totais = {
            "depositos": {"quantidadeTotal": "quantidade", "valorTotal": "valor"},
            "acordos": {
                "quantidadeTotal": "quantidade", "valorTotal": "valor",
                "pagosTotal": "pagos", "pendenteTotal": "pendente",
            },
            "promessas": {
                "quantidadeTotal": "quantidade", "prometidoTotal": "prometido",
                "cumpridoTotal": "cumprido", "emAbertoTotal": "emAberto",
                "quebradoTotal": "quebrado",
            },
            "contatos": {"registrosTotaisTotal": "registrosTotais"},
        }
        for grupo, quantidade in quantidades.items():
            base = data[grupo]["porUsuario"][0]
            linhas = []
            for indice in range(quantidade):
                item = dict(base)
                item["usuario"] = f"TESTE.{grupo.upper()}.{indice}"
                item["nome"] = f"Usuário sintético {grupo} {indice}"
                if grupo == "contatos":
                    item["contatosUnicos"] = 20
                linhas.append(item)
            data[grupo]["porUsuario"] = linhas
            for campo_total, campo_item in campos_totais[grupo].items():
                data[grupo][campo_total] = sum(linha[campo_item] for linha in linhas)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "amostra_18_fatos_sintetica.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            proc = self.executar(path)

        self.assertEqual(proc.returncode, 0, proc.stderr + "\\n" + proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASSED")
        contagem = report["contagem_fatos"]
        self.assertEqual(contagem["origem_por_grupo"], quantidades)
        esperado_por_tipo = {
            "deposito": 5, "acordo": 5, "promessa": 3, "contato": 5,
        }
        self.assertEqual(contagem["origem_por_tipo"], esperado_por_tipo)
        self.assertEqual(contagem["normalizados_por_tipo"], esperado_por_tipo)
        self.assertEqual(contagem["persistidos_primeira_importacao_por_tipo"], esperado_por_tipo)
        self.assertEqual(contagem["persistidos_apos_reimportacao_por_tipo"], esperado_por_tipo)
        self.assertEqual(contagem["itens_origem"], 18)
        self.assertEqual(contagem["fatos_normalizados"], 18)
        self.assertEqual(contagem["fatos_persistidos_primeira_importacao"], 18)
        self.assertEqual(contagem["fatos_persistidos_apos_reimportacao"], 18)
        self.assertTrue(contagem["origem_confere_normalizados"])
        self.assertTrue(contagem["primeira_importacao_confere"])
        self.assertTrue(contagem["reimportacao_confere"])
        etapas = {etapa["etapa"]: etapa["status"] for etapa in report["etapas"]}
        self.assertEqual(etapas["conciliacao_contagem_primeira_importacao"], "OK")
        self.assertEqual(etapas["conciliacao_contagem_reimportacao"], "OK")

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
