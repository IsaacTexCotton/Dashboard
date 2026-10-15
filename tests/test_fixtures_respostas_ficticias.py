"""Valida fixtures JSON de múltiplas datas sem CRM e sem banco persistente."""
import sqlite3
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "respostas_ficticias"
sys.path.insert(0, str(ROOT))
import auditar_resposta
import importar


class FixturesMultidatasTestes(unittest.TestCase):
    def test_todas_as_datas_sao_validas_e_reconciliadas(self):
        arquivos = sorted(FIXTURES.glob("2026-10-*.json"))
        self.assertEqual(len(arquivos), 14, "esperadas 14 fixtures diárias")
        datas = []
        for arquivo in arquivos:
            with self.subTest(arquivo=arquivo.name):
                payload = importar._carregar_arquivo(str(arquivo))
                dia = arquivo.stem
                datas.append(dia)
                self.assertEqual(payload["data"]["inicio"], dia)
                self.assertEqual(payload["data"]["fim"], dia)
                self.assertTrue(payload["success"])

                checks = auditar_resposta.auditar(payload)
                bloqueios = [c for c in checks if c.status in ("DIVERGÊNCIA", "PENDENTE")]
                self.assertEqual(bloqueios, [], str(bloqueios))

                _usuarios, fatos, _posicao = importar.normalizar(payload, dia)
                esperados = {
                    "deposito": len(payload["data"]["depositos"]["porUsuario"]),
                    "acordo": len(payload["data"]["acordos"]["porUsuario"]),
                    "promessa": len(payload["data"]["promessas"]["porUsuario"]),
                    "contato": len(payload["data"]["contatos"]["porUsuario"]),
                }
                self.assertEqual(Counter(f[2] for f in fatos), esperados)
                self.assertEqual(len(fatos), sum(esperados.values()))
        self.assertEqual(datas, [f"2026-10-{d:02d}" for d in range(1, 15)])

    def test_importa_todas_as_datas_apenas_em_sqlite_em_memoria(self):
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(importar.SCHEMA)
            total_esperado = 0
            for arquivo in sorted(FIXTURES.glob("2026-10-*.json")):
                dia = arquivo.stem
                payload = importar._carregar_arquivo(str(arquivo))
                linhas_origem = sum(
                    len(payload["data"][grupo]["porUsuario"])
                    for grupo in ("depositos", "acordos", "promessas", "contatos")
                )
                self.assertEqual(importar.gravar(con, dia, payload, "fixture-ficticia"), linhas_origem)
                total_esperado += linhas_origem
            self.assertEqual(
                con.execute("SELECT COUNT(DISTINCT data) FROM fatos").fetchone()[0], 14
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0], total_esperado)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 14)
            dia_13 = con.execute(
                "SELECT COUNT(*) FROM fatos WHERE data = ?", ("2026-10-13",)
            ).fetchone()[0]
            self.assertEqual(dia_13, 18)
            self.assertEqual(
                dict(con.execute(
                    "SELECT tipo, COUNT(*) FROM fatos WHERE data = ? GROUP BY tipo",
                    ("2026-10-13",),
                ).fetchall()),
                {"deposito": 5, "acordo": 5, "promessa": 3, "contato": 5},
            )
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
