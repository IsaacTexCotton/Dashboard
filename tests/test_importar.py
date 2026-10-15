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

    def test_contagem_por_usuario_corresponde_a_fatos_normalizados_e_gravados(self):
        # Fixture sintética com o formato 5+5+3+5 do relato de 18 itens.
        # Cada linha porUsuario deve gerar exatamente um fato; não deduplicar
        # entre tipos diferentes. O contador global de contatos únicos não é aditivo.
        import auditar_resposta

        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        data = payload["data"]
        quantidades = {"depositos": 5, "acordos": 5, "promessas": 3, "contatos": 5}
        totais_por_grupo = {
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
                linhas.append(item)
            data[grupo]["porUsuario"] = linhas
            for campo_total, campo_item in totais_por_grupo[grupo].items():
                data[grupo][campo_total] = sum(linha[campo_item] for linha in linhas)

        checks = auditar_resposta.auditar(payload)
        bloqueios = [check for check in checks if check.status in ("DIVERGÊNCIA", "PENDENTE")]
        self.assertEqual(bloqueios, [], str(bloqueios))

        itens_origem = sum(
            len(data[grupo]["porUsuario"]) for grupo in quantidades
        )
        usuarios, fatos, _ = importar.normalizar(payload, "2026-10-13")
        self.assertEqual(itens_origem, 18)
        self.assertEqual(len(usuarios), 18)
        self.assertEqual(len(fatos), itens_origem)
        self.assertEqual(
            {tipo: sum(1 for fato in fatos if fato[2] == tipo) for tipo in importar.TIPOS},
            {"deposito": 5, "acordo": 5, "promessa": 3, "contato": 5},
        )

        con = sqlite3.connect(":memory:")
        try:
            con.executescript(importar.SCHEMA)
            gravados = importar.gravar(con, "2026-10-13", payload, "teste-sintetico")
            self.assertEqual(gravados, itens_origem)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0], itens_origem)
            self.assertEqual(
                dict(con.execute("SELECT tipo, COUNT(*) FROM fatos GROUP BY tipo").fetchall()),
                {"acordo": 5, "contato": 5, "deposito": 5, "promessa": 3},
            )
            self.assertEqual(
                con.execute("SELECT linhas FROM importacoes").fetchone()[0],
                itens_origem,
            )
        finally:
            con.close()

    def test_rejeita_success_false(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload["success"] = False
        with self.assertRaises(importar.ErroValidacao):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_resposta_vazia(self):
        with self.assertRaisesRegex(importar.ErroValidacao, "success=true"):
            importar.normalizar({}, "2026-10-13")

    def test_timestamp_da_origem_e_preservado_exatamente(self):
        payload = json.loads(json.dumps(AMOSTRA))
        timestamp = "2026-10-13T16:56:19.816961"
        payload["timestamp"] = timestamp
        _, _, posicao = importar.normalizar(payload, "2026-10-13")
        self.assertEqual(posicao[0], timestamp)

    def test_rejeita_timestamp_ausente_sem_gerar_horario_local(self):
        payload = json.loads(json.dumps(AMOSTRA))
        payload.pop("timestamp", None)
        with self.assertRaisesRegex(importar.ErroValidacao, "timestamp: campo obrigatório"):
            importar.normalizar(payload, "2026-10-13")

    def test_rejeita_nome_conflitante_para_mesmo_usuario_entre_grupos(self):
        payload = json.loads(json.dumps(AMOSTRA))
        item = payload["data"]["acordos"]["porUsuario"][0]
        item["usuario"] = "NEGOCIADOR.A"
        item["nome"] = "Nome conflitante"
        with self.assertRaisesRegex(importar.ErroValidacao, "nomes conflitantes"):
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

    def test_negativos_so_sao_permitidos_nos_campos_contratados(self):
        permitidos = [
            (("depositos", "porUsuario", 0, "valor"), -1.25),
            (("acordos", "porUsuario", 0, "pendente"), -1.25),
            (("promessas", "porUsuario", 0, "emAberto"), -1.25),
            (("valoresAcordo", "valorRecebidoPeriodo"), -1.25),
        ]
        for caminho, valor in permitidos:
            with self.subTest(campo=".".join(map(str, caminho))):
                payload = json.loads(json.dumps(AMOSTRA))
                alvo = payload["data"]
                for chave in caminho[:-1]:
                    alvo = alvo[chave]
                alvo[caminho[-1]] = valor
                usuarios, fatos, pos = importar.normalizar(payload, "2026-10-13")
                self.assertTrue(fatos)
                if caminho[-1] == "valorRecebidoPeriodo":
                    self.assertEqual(pos[2], -1.25)

        proibidos = [
            ("acordos", "porUsuario", 0, "valor"),
            ("acordos", "porUsuario", 0, "pagos"),
            ("promessas", "porUsuario", 0, "prometido"),
            ("promessas", "porUsuario", 0, "cumprido"),
            ("promessas", "porUsuario", 0, "quebrado"),
            ("valoresAcordo", "valorAVencer"),
            ("valoresAcordo", "valorVencido"),
        ]
        for caminho in proibidos:
            with self.subTest(campo=".".join(map(str, caminho))):
                payload = json.loads(json.dumps(AMOSTRA))
                alvo = payload["data"]
                for chave in caminho[:-1]:
                    alvo = alvo[chave]
                alvo[caminho[-1]] = -1.25
                with self.assertRaisesRegex(
                    importar.ErroValidacao, "valor monetário negativo não permitido"
                ):
                    importar.normalizar(payload, "2026-10-13")

    def test_normalizar_modo_exato_preserva_decimal_sem_conversao_float(self):
        from decimal import Decimal
        from unittest.mock import patch

        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        with patch.object(
            importar, "_para_real_legado",
            side_effect=AssertionError("adaptador REAL legado não deve ser chamado"),
        ):
            usuarios, fatos, posicao = importar.normalizar(
                payload, "2026-10-13", converter_monetarios_float=False
            )
        self.assertTrue(usuarios)
        self.assertIsInstance(fatos[0][5], Decimal)
        self.assertIsInstance(posicao[2], (int, Decimal))
        self.assertNotIsInstance(posicao[2], float)

    def test_normalizar_duplo_aceita_zeros_finais_e_rejeita_subcentavos(self):
        from decimal import Decimal
        from unittest.mock import patch

        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        with patch.object(
            importar, "_para_real_legado",
            side_effect=AssertionError("adaptador REAL legado não deve ser chamado"),
        ):
            usuarios, fatos, _ = importar.normalizar_duplo(
                payload, "2026-10-13", "2026-10-14T12:00:00"
            )
        self.assertTrue(usuarios)
        self.assertTrue(fatos)

        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0]["valor"] = Decimal("1.230")
        usuarios, fatos, _ = importar.normalizar_duplo(
            payload, "2026-10-13", "2026-10-14T12:00:00"
        )
        deposito = next(f for f in fatos if f["legado"]["tipo"] == "deposito")
        self.assertEqual(deposito["centavos"]["deposito_valor_centavos"], 123)

        payload["data"]["depositos"]["porUsuario"][0]["valor"] = Decimal("1.231")
        with self.assertRaisesRegex(
            importar.ErroValidacao, "precisão excede 2 casas|arredondamento de entrada proibido"
        ):
            importar.normalizar_duplo(
                payload, "2026-10-13", "2026-10-14T12:00:00"
            )

    def test_normalizar_duplo_rejeita_float_intermediario(self):
        payload = json.loads(json.dumps(AMOSTRA))
        with self.assertRaisesRegex(importar.ErroValidacao, "token Decimal/int"):
            importar.normalizar_duplo(
                payload, "2026-10-13", "2026-10-14T12:00:00"
            )


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

    def test_gravar_dupla_escrita_integrada_preserva_centavos_e_real(self):
        from decimal import Decimal
        from migrar_schema_monetario import migrar_schema_monetario

        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(importar.SCHEMA)
            migrar_schema_monetario(con)
            total = importar.gravar(
                con, "2026-10-13", payload, "teste", dupla_escrita=True
            )
            self.assertEqual(total, 5)
            row = con.execute(
                "SELECT valor, deposito_valor_centavos FROM fatos "
                "WHERE tipo='deposito' ORDER BY usuario LIMIT 1"
            ).fetchone()
            self.assertIsInstance(row[0], float)
            self.assertIsInstance(row[1], int)
            self.assertEqual(
                row[1],
                importar.normalizar_duplo(
                    payload, "2026-10-13", "2026-10-14T12:00:00"
                )[1][0]["centavos"]["deposito_valor_centavos"],
            )
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 1
            )
        finally:
            con.close()

    def test_dual_write_em_banco_legado_sem_migracao_falha_sem_modificar_schema(self):
        from migrar_schema_monetario import migrar_schema_monetario

        con = sqlite3.connect(":memory:")
        try:
            con.executescript(importar.SCHEMA)
            before = {r[1] for r in con.execute("PRAGMA table_info(fatos)")}
            payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
            with self.assertRaises(importar.ErroValidacao):
                importar.gravar(
                    con, "2026-10-13", payload, "teste", dupla_escrita=True
                )
            after = {r[1] for r in con.execute("PRAGMA table_info(fatos)")}
            self.assertEqual(after, before)
        finally:
            con.close()

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
            # A resposta da API passa pelo parser JSON estrito; manter Decimal
            # no mock em vez de simular floats provenientes de json.loads comum.
            payload = importar._carregar_arquivo(str(ROOT / "amostra_resposta.json"))
            payload["data"]["depositos"]["valorTotal"] += 100
            with patch.object(importar, "DB", str(db)), patch.dict(
                os.environ, {"CRM_URL": "https://crm.invalid", "CRM_TOKEN": "token-de-teste"}
            ), patch("importar.buscar", return_value=payload):
                codigo = importar.main([])
            self.assertEqual(codigo, 1)
            self.assertFalse(db.exists())

    def test_importacao_local_bloqueia_valor_negativo_antes_de_criar_banco(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            arquivo = Path(td) / "negativo.json"
            payload = json.loads(json.dumps(AMOSTRA))
            payload["data"]["valoresAcordo"]["valorVencido"] = -1
            arquivo.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo", str(arquivo)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("valor monetário negativo não permitido", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertFalse(db.exists())

    def test_importacao_api_bloqueia_valor_negativo_antes_de_criar_banco(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            payload = importar._carregar_arquivo(str(ROOT / "amostra_resposta.json"))
            payload["data"]["promessas"]["porUsuario"][0]["quebrado"] = -1
            with patch.object(importar, "DB", str(db)), patch.dict(
                os.environ, {"CRM_URL": "https://crm.invalid", "CRM_TOKEN": "token-de-teste"}
            ), patch("importar.buscar", return_value=payload), patch(
                "importar.dias", return_value=iter(["2026-10-13"])
            ):
                with self.assertRaisesRegex(
                    importar.ErroValidacao, "valor monetário negativo não permitido"
                ):
                    importar.main([])
            self.assertFalse(db.exists())

    def test_total_agregado_ausente_bloqueia_importacao(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            arquivo = Path(td) / "total_ausente.json"
            payload = json.loads(json.dumps(AMOSTRA))
            del payload["data"]["promessas"]["quebradoTotal"]
            arquivo.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo", str(arquivo)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("PENDENTE", proc.stderr)
            self.assertFalse(db.exists())

    def test_json_malformado_retorna_codigo_dois_sem_criar_banco(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nao_deve_existir.db"
            arquivo = Path(td) / "invalido.json"
            arquivo.write_text("{json invalido", encoding="utf-8")
            env = os.environ.copy()
            env["DASHBOARD_DB"] = str(db)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "importar.py"), "--arquivo", str(arquivo)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Arquivo JSON inválido", proc.stderr)
            self.assertFalse(db.exists())

    def test_dry_run_sem_arquivo_e_barrado(self):
        proc = subprocess.run([sys.executable, str(ROOT / "importar.py"), "--dry-run"],
                              cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--dry-run exige --arquivo", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class PrecisaoEntradaMonetariaTestes(unittest.TestCase):
    def _payload_decimal(self, campo, valor):
        payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
        payload["data"]["depositos"]["porUsuario"][0][campo] = valor
        return payload

    def test_entrada_com_duas_casas_e_valida(self):
        from decimal import Decimal
        payload = self._payload_decimal("valor", Decimal("1.23"))
        _, fatos, _ = importar.normalizar(payload, "2026-10-13")
        deposito = next(f for f in fatos if f[2] == "deposito")
        self.assertEqual(deposito[5], 1.23)

    def test_zeros_excedentes_sao_aceitos_sem_mudar_centavos(self):
        from decimal import Decimal
        for token in ("1.230", "1.2300", "1.230000"):
            with self.subTest(token=token):
                payload = self._payload_decimal("valor", Decimal(token))
                _, fatos, _ = importar.normalizar(payload, "2026-10-13")
                deposito = next(f for f in fatos if f[2] == "deposito")
                self.assertEqual(deposito[5], 1.23)

    def test_fracao_subcentavo_e_rejeitada_sem_arredondamento(self):
        from decimal import Decimal
        for token in ("1.231", "1.2345", "1.0001", "0.001"):
            with self.subTest(token=token):
                payload = self._payload_decimal("valor", Decimal(token))
                with self.assertRaisesRegex(importar.ErroValidacao, "precisão excede"):
                    importar.normalizar(payload, "2026-10-13")

    def test_precisao_excedente_e_rejeitada_em_todos_os_campos_monetarios(self):
        from decimal import Decimal
        casos = [
            ("depositos", "valor"), ("acordos", "valor"),
            ("acordos", "pagos"), ("acordos", "pendente"),
            ("promessas", "prometido"), ("promessas", "cumprido"),
            ("promessas", "emAberto"), ("promessas", "quebrado"),
        ]
        for grupo, campo in casos:
            with self.subTest(grupo=grupo, campo=campo):
                payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
                payload["data"][grupo]["porUsuario"][0][campo] = Decimal("2.675")
                with self.assertRaises(importar.ErroValidacao):
                    importar.normalizar(payload, "2026-10-13")

    def test_limite_integer64_e_rejeitado(self):
        from decimal import Decimal
        payload = self._payload_decimal("valor", Decimal("92233720368547758.08"))
        with self.assertRaisesRegex(importar.ErroValidacao, "fora do intervalo"):
            importar.normalizar(payload, "2026-10-13")

    def test_notacao_cientifica_e_rejeitada_pelo_parser_de_origem(self):
        with self.assertRaises(importar.ErroMonetario):
            importar.loads_json_estrito('{"valor": 1e2}')


class PrecisaoEntradaAtomicidadeTestes(unittest.TestCase):
    def test_payload_com_fracao_subcentavo_nao_altera_fatos_existentes(self):
        from decimal import Decimal
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(importar.SCHEMA)
            con.execute(
                "INSERT INTO fatos VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("2026-10-13", "SINTETICO", "contato", 1, 1, 0, 0, 0, 0, "antes"),
            )
            con.commit()
            payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
            payload["data"]["depositos"]["porUsuario"][0]["valor"] = Decimal("1.231")
            with self.assertRaises(importar.ErroValidacao):
                importar.gravar(con, "2026-10-13", payload, "teste")
            self.assertEqual(
                con.execute("SELECT usuario, tipo FROM fatos").fetchall(),
                [("SINTETICO", "contato")],
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
        finally:
            con.close()

    def test_totais_de_posicao_rejeitam_precisao_excedente(self):
        from decimal import Decimal
        for campo in ("valorRecebidoPeriodo", "valorAVencer", "valorVencido"):
            with self.subTest(campo=campo):
                payload = importar.loads_json_estrito(json.dumps(AMOSTRA))
                payload["data"]["valoresAcordo"][campo] = Decimal("1.231")
                with self.assertRaises(importar.ErroValidacao):
                    importar.normalizar(payload, "2026-10-13")
