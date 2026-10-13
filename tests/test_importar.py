import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import importar

with (ROOT / "amostra_resposta.json").open(encoding="utf-8") as arquivo:
    AMOSTRA = json.load(arquivo)


class NormalizacaoTestes(unittest.TestCase):
    def test_amostra_valida(self):
        usuarios, fatos, pos = importar.normalizar(AMOSTRA, "2026-10-13")
        self.assertEqual(set(usuarios), {"NEGOCIADOR.A", "NEGOCIADOR.B"})
        self.assertEqual(len(fatos), 5)
        self.assertEqual(pos[1], "2026-10-13")
        self.assertEqual(pos[2:], (0.0, 1_000_000.0, 200_000.0))

    def test_rejeita_success_false(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["success"] = False
        with self.assertRaises(importar.ErroValidacao):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_periodo_divergente(self):
        with self.assertRaisesRegex(importar.ErroValidacao, "período divergente"):
            importar.normalizar(AMOSTRA, "2026-10-12")

    def test_rejeita_grupo_ausente(self):
        payload = json.loads(json.dumps(AMOSTRA))
        del payload["data"]["promessas"]
        with self.assertRaises(importar.ErroValidacao):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_valor_nao_finito(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["valor"] = float("nan")
        with self.assertRaisesRegex(importar.ErroValidacao, "não finito"):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_valor_monetario_nulo(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["valor"] = None
        with self.assertRaisesRegex(importar.ErroValidacao, "esperado número"):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_valor_monetario_em_texto(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["valor"] = "123,45"
        with self.assertRaisesRegex(importar.ErroValidacao, "esperado número"):
            importar.normalizar(payload, "2026-10-13")

    def test_negativo_monetario_nao_e_bloqueado_sem_politica_aprovada(self):
        # Comportamento temporário deliberado: negatividade requer definição de negócio.
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["valor"] = -1.25
        usuarios, fatos, _ = importar.normalizar(payload, "2026-10-13")
        deposito = next(f for f in fatos if f[2] == "deposito" and f[1] == "NEGOCIADOR.A")
        self.assertEqual(deposito[5], -1.25)

    def test_grupos_vazios_com_totais_zero_sao_validos(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"] = {
            "quantidadeTotal": 0, "valorTotal": 0, "porUsuario": []
        }
        payload["data"]["acordos"] = {
            "quantidadeTotal": 0, "valorTotal": 0, "pagosTotal": 0,
            "pendenteTotal": 0, "porUsuario": []
        }
        payload["data"]["promessas"] = {
            "quantidadeTotal": 0, "prometidoTotal": 0, "cumpridoTotal": 0,
            "emAbertoTotal": 0, "quebradoTotal": 0, "porUsuario": []
        }
        payload["data"]["contatos"] = {
            "contatosUnicosTotal": 0, "registrosTotaisTotal": 0, "porUsuario": []
        }
        payload["data"]["valoresAcordo"] = {
            "valorRecebidoPeriodo": 0, "valorAVencer": 0, "valorVencido": 0
        }
        usuarios, fatos, posicao = importar.normalizar(payload, "2026-10-13")
        self.assertEqual(usuarios, {})
        self.assertEqual(fatos, [])
        self.assertEqual(posicao[2:], (0.0, 0.0, 0.0))

    def test_rejeita_quantidade_booleana(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["quantidade"] = True
        with self.assertRaises(importar.ErroValidacao):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_usuario_duplicado_no_grupo(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"].append(
            dict(payload["data"]["depositos"]["porUsuario"][0])
        )
        with self.assertRaisesRegex(importar.ErroValidacao, "duplicado"):
            importar.normalizar(payload, "2026-10-13")

    def test_url_substitui_datas_sem_duplicar_parametros(self):
        url = importar._url_do_dia(
            "https://exemplo.invalid/api?inicio=2026-10-01&token_ref=x&fim=2026-10-02&inicio=2026-10-03",
            "2026-10-13",
        )
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["inicio"], ["2026-10-13"])
        self.assertEqual(query["fim"], ["2026-10-13"])
        self.assertEqual(query["token_ref"], ["x"])


class PersistenciaTestes(unittest.TestCase):
    def test_reimportar_mesmo_dia_substitui_fatos_sem_duplicar(self):
        con = sqlite3.connect(":memory:")
        con.executescript(importar.SCHEMA)
        importar.gravar(con, "2026-10-13", AMOSTRA, "teste")
        payload = json.loads(json.dumps(AMOSTRA))
        payload["timestamp"] = "2026-10-13T16:08:31"
        importar.gravar(con, "2026-10-13", payload, "teste")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0], 5)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 2)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM acordos_posicao").fetchone()[0], 2)
        con.close()

    def test_payload_invalido_preserva_fatos_existentes(self):
        con = sqlite3.connect(":memory:")
        con.executescript(importar.SCHEMA)
        dia = "2026-10-13"
        con.execute("INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (dia, "ANTIGO", "contato", 1, 1, 0, 0, 0, 0, "antes"))
        con.commit()
        payload = json.loads(json.dumps(AMOSTRA))
        payload["data"]["valoresAcordo"].pop("valorVencido")
        with self.assertRaises(importar.ErroValidacao):
            importar.gravar(con, dia, payload, "teste")
        self.assertEqual(con.execute("SELECT usuario FROM fatos WHERE data=?", (dia,)).fetchall(),
                         [("ANTIGO",)])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
        con.close()

    def test_falha_reverte_o_dia_inteiro(self):
        con = sqlite3.connect(":memory:")
        con.executescript(importar.SCHEMA)
        dia = "2026-10-13"
        con.execute("INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (dia, "ANTIGO", "contato", 1, 1, 0, 0, 0, 0, "antes"))
        con.commit()
        con.execute("CREATE TRIGGER falhar_insert_fato BEFORE INSERT ON fatos "
                    "BEGIN SELECT RAISE(ABORT, 'falha de teste'); END")
        con.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            importar.gravar(con, dia, AMOSTRA, "teste")
        self.assertEqual(con.execute("SELECT usuario FROM fatos WHERE data=?", (dia,)).fetchall(),
                         [("ANTIGO",)])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 0)
        con.close()

    def test_dry_run_nao_cria_banco_e_nao_precisa_de_credenciais(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            for key in ("CRM_URL", "CRM_TOKEN", "CRM_COOKIE"):
                env.pop(key, None)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo",
                 str(ROOT / "amostra_resposta.json"), "--dry-run"],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("VALIDAÇÃO OK", proc.stdout)
            self.assertIn("nenhuma chamada ao CRM", proc.stdout)
            self.assertFalse(db.exists())

    def test_dry_run_bloqueia_divergencia_financeira(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            payload = json.loads(json.dumps(AMOSTRA))
            payload["data"]["depositos"]["valorTotal"] += 100
            arquivo = Path(td) / "divergente.json"
            arquivo.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo", str(arquivo), "--dry-run"],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("Importação bloqueada pela auditoria financeira", proc.stderr)
            self.assertFalse(db.exists())

    def test_importacao_local_bloqueia_divergencia_antes_de_criar_banco(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            arquivo = Path(td) / "divergente.json"
            payload = json.loads(json.dumps(AMOSTRA))
            payload["data"]["depositos"]["valorTotal"] += 100
            arquivo.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo", str(arquivo)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("DIVERGÊNCIA", proc.stderr)
            self.assertFalse(db.exists())

    def test_importacao_api_bloqueia_divergencia_antes_de_criar_banco(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            payload = json.loads(json.dumps(AMOSTRA))
            payload["data"]["depositos"]["valorTotal"] += 100
            with patch.object(importar, "DB", str(db)), patch.dict(
                os.environ, {"CRM_URL": "https://crm.invalid", "CRM_TOKEN": "token-de-teste"}
            ), patch("importar.buscar", return_value=payload):
                codigo = importar.main([])
            self.assertEqual(codigo, 1)
            self.assertFalse(db.exists())

    def test_dry_run_sem_arquivo_e_barrado(self):
        proc = subprocess.run([sys.executable, str(ROOT / "importar.py"), "--dry-run"],
                              cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--dry-run exige --arquivo", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
