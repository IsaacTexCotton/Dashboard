"""Testes operacionais exclusivamente sintéticos para a migração monetária."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backup_sqlite
from backfill_monetario import backfill_monetario
from migrar_schema_monetario import TABELA_ESTADO, migrar_schema_monetario
from precisao_monetaria import (
    ErroMonetario,
    grandeza_para_escala,
    loads_json_estrito,
    resultado_calculado_para_centavos,
    valor_final_centavos,
)

FIXTURE = ROOT / "tests" / "fixtures" / "amostra_monetaria_erp_systextil_sintetica.json"


class PreparacaoMigracaoMonetariaTestes(unittest.TestCase):
    def _carregar_fixture(self):
        payload = loads_json_estrito(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(payload["classificacao"], "SINTETICO_NAO_REAL")
        self.assertFalse(payload["origem_autorizada_real_disponivel"])
        self.assertEqual(payload["quantidade_registros"], len(payload["registros"]))
        self.assertGreaterEqual(len(payload["registros"]), 30)
        return payload["registros"]

    def test_fixture_sintetica_cobre_conversoes_e_rejeicoes_contratadas(self):
        registros = self._carregar_fixture()
        ids = [registro["id"] for registro in registros]
        self.assertEqual(len(ids), len(set(ids)))

        operacoes = {
            "final": lambda r: valor_final_centavos(
                r["valor_origem"],
                campo=r["id"],
                negativos_permitidos=r["negativos_permitidos"],
            ),
            "scale": lambda r: grandeza_para_escala(
                r["valor_origem"],
                r["escala"],
                campo=r["id"],
                negativos_permitidos=r["negativos_permitidos"],
            ),
            "half_up": lambda r: resultado_calculado_para_centavos(
                r["valor_origem"],
                campo=r["id"],
                negativos_permitidos=r["negativos_permitidos"],
            ),
            "nullable": lambda r: r["valor_origem"],
        }

        aceitos = rejeitados = 0
        for registro in registros:
            with self.subTest(fixture=registro["id"], operacao=registro["operacao"]):
                operacao = operacoes[registro["operacao"]]
                if registro["resultado_esperado"] == "reject":
                    with self.assertRaises(ErroMonetario):
                        operacao(registro)
                    rejeitados += 1
                else:
                    resultado = operacao(registro)
                    esperado = registro["esperado"]
                    if registro["operacao"] == "nullable":
                        self.assertIsNone(resultado)
                        self.assertIsNone(esperado)
                    else:
                        self.assertEqual(resultado, esperado)
                    aceitos += 1

        self.assertGreaterEqual(aceitos, 25)
        self.assertGreaterEqual(rejeitados, 5)

    def test_backfill_simulacao_30_fatos_e_3_snapshots_sem_escrita(self):
        with tempfile.TemporaryDirectory() as td:
            banco = Path(td) / "backfill-sintetico.sqlite3"
            con = sqlite3.connect(banco)
            try:
                con.executescript("""
                    CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, nome TEXT);
                    CREATE TABLE fatos (
                        data TEXT NOT NULL, usuario TEXT NOT NULL, tipo TEXT NOT NULL,
                        qtd INTEGER NOT NULL DEFAULT 0, qtd_unicos INTEGER NOT NULL DEFAULT 0,
                        valor REAL NOT NULL DEFAULT 0, valor_pago REAL NOT NULL DEFAULT 0,
                        valor_aberto REAL NOT NULL DEFAULT 0, valor_quebrado REAL NOT NULL DEFAULT 0,
                        importado_em TEXT NOT NULL, PRIMARY KEY (data, usuario, tipo)
                    );
                    CREATE TABLE acordos_posicao (
                        capturado_em TEXT PRIMARY KEY, data TEXT,
                        recebido_periodo REAL, a_vencer REAL, vencido REAL
                    );
                """)
                tipos = ("deposito", "acordo", "promessa", "contato")
                for i in range(30):
                    tipo = tipos[i % len(tipos)]
                    usuario = f"SINTETICO-{i:02d}"
                    dia = f"2026-10-{(i % 28) + 1:02d}"
                    if tipo == "deposito":
                        valor, pago, aberto, quebrado = (1001 + i) / 100, 0.0, 0.0, 0.0
                    elif tipo == "acordo":
                        valor, pago, aberto, quebrado = 100.0 + i / 100, 25.0, 75.0 + i / 100, 0.0
                    elif tipo == "promessa":
                        valor, pago, aberto, quebrado = 50.0 + i / 100, 10.0, 40.0 + i / 100, 0.0
                    else:
                        valor, pago, aberto, quebrado = 0.0, 0.0, 0.0, 0.0
                    con.execute(
                        "INSERT INTO usuarios(usuario,nome) VALUES (?,?)",
                        (usuario, "Fixture sintética"),
                    )
                    con.execute(
                        "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
                        "valor_aberto,valor_quebrado,importado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (dia, usuario, tipo, 1, 0, valor, pago, aberto, quebrado, "SINTETICO"),
                    )
                for i in range(3):
                    con.execute(
                        "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido) "
                        "VALUES (?,?,?,?,?)",
                        (f"2026-10-{i+1:02d}T12:00:00", f"2026-10-{i+1:02d}", -10.5, 100.0 + i, 200.0 + i),
                    )
                con.commit()
                migrar_schema_monetario(con)
                con.commit()

                antes_real = con.execute(
                    "SELECT data,usuario,tipo,valor,valor_pago,valor_aberto,valor_quebrado "
                    "FROM fatos ORDER BY data,usuario,tipo"
                ).fetchall()
                antes_centavos = con.execute(
                    "SELECT data,usuario,tipo,deposito_valor_centavos,acordo_valor_centavos,"
                    "acordo_pago_centavos,acordo_pendente_centavos,promessa_prometido_centavos,"
                    "promessa_cumprido_centavos,promessa_em_aberto_centavos,promessa_quebrado_centavos "
                    "FROM fatos ORDER BY data,usuario,tipo"
                ).fetchall()
                antes_snapshot = con.execute(
                    "SELECT capturado_em,recebido_periodo,a_vencer,vencido,"
                    "recebido_periodo_centavos,a_vencer_centavos,vencido_centavos "
                    "FROM acordos_posicao ORDER BY capturado_em"
                ).fetchall()

                resultado = backfill_monetario(con)  # aplicar=False por padrão
                self.assertEqual(resultado["modo"], "simulacao")
                self.assertEqual(resultado["linhas_fatos"], 30)
                self.assertEqual(resultado["snapshots_posicao"], 3)
                self.assertEqual(resultado["updates_previstos"], 26)
                self.assertEqual(resultado["colunas_a_preencher"], 69)
                self.assertEqual(resultado["campos_pendentes_origem_null"], 0)
                self.assertEqual(resultado["colunas_real_alteradas"], 0)
                self.assertFalse(resultado["conciliacao_concluida"])
                self.assertEqual(
                    con.execute(
                        f"SELECT fase FROM {TABELA_ESTADO} WHERE id=1"
                    ).fetchone()[0],
                    "schema_adicionado",
                )
                self.assertEqual(
                    con.execute(
                        "SELECT data,usuario,tipo,valor,valor_pago,valor_aberto,valor_quebrado "
                        "FROM fatos ORDER BY data,usuario,tipo"
                    ).fetchall(),
                    antes_real,
                )
                self.assertEqual(
                    con.execute(
                        "SELECT data,usuario,tipo,deposito_valor_centavos,acordo_valor_centavos,"
                        "acordo_pago_centavos,acordo_pendente_centavos,promessa_prometido_centavos,"
                        "promessa_cumprido_centavos,promessa_em_aberto_centavos,promessa_quebrado_centavos "
                        "FROM fatos ORDER BY data,usuario,tipo"
                    ).fetchall(),
                    antes_centavos,
                )
                self.assertEqual(
                    con.execute(
                        "SELECT capturado_em,recebido_periodo,a_vencer,vencido,"
                        "recebido_periodo_centavos,a_vencer_centavos,vencido_centavos "
                        "FROM acordos_posicao ORDER BY capturado_em"
                    ).fetchall(),
                    antes_snapshot,
                )
            finally:
                con.close()

    def test_backup_verificacao_e_restauracao_em_sqlite_descartavel(self):
        registros = self._carregar_fixture()
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td)
            origem = raiz / "origem-sintetica.sqlite3"
            backup = raiz / "backup-sintetico.sqlite3"
            restaurado = raiz / "restaurado-sintetico.sqlite3"

            con = sqlite3.connect(origem)
            try:
                con.execute(
                    "CREATE TABLE fatos_fixture ("
                    "id TEXT PRIMARY KEY, classificacao TEXT NOT NULL, "
                    "valor_legado REAL, valor_centavos INTEGER)"
                )
                linhas = []
                for registro in registros:
                    valor = registro["valor_origem"]
                    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
                        legado = float(valor)
                    else:
                        legado = None
                    centavos = (
                        registro["esperado"]
                        if registro["resultado_esperado"] == "ok"
                        and registro["operacao"] in ("final", "half_up")
                        and isinstance(registro["esperado"], int)
                        else None
                    )
                    linhas.append((
                        registro["id"], "SINTETICO_NAO_REAL", legado, centavos
                    ))
                con.executemany(
                    "INSERT INTO fatos_fixture VALUES (?, ?, ?, ?)", linhas
                )
                con.commit()
                antes = con.execute(
                    "SELECT id, classificacao, valor_legado, valor_centavos "
                    "FROM fatos_fixture ORDER BY id"
                ).fetchall()
            finally:
                con.close()

            manifesto = backup_sqlite.criar_backup(origem, backup)
            verificacao = backup_sqlite.verificar_backup(backup)
            self.assertEqual(verificacao["status"], "OK", verificacao)
            self.assertEqual(manifesto["tables"]["fatos_fixture"], len(registros))

            fonte_backup = sqlite3.connect(backup)
            destino_restaurado = sqlite3.connect(restaurado)
            try:
                fonte_backup.backup(destino_restaurado)
                destino_restaurado.commit()
                integridade = destino_restaurado.execute(
                    "PRAGMA integrity_check"
                ).fetchall()
                self.assertEqual(integridade, [("ok",)])
                depois = destino_restaurado.execute(
                    "SELECT id, classificacao, valor_legado, valor_centavos "
                    "FROM fatos_fixture ORDER BY id"
                ).fetchall()
                self.assertEqual(depois, antes)
                self.assertEqual(
                    destino_restaurado.execute(
                        "SELECT COUNT(*) FROM fatos_fixture"
                    ).fetchone()[0],
                    len(registros),
                )
            finally:
                fonte_backup.close()
                destino_restaurado.close()

            # A evidência é local, descartável e não contém dados empresariais.
            self.assertTrue(origem.is_file())
            self.assertTrue(backup.is_file())
            self.assertTrue(restaurado.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
