"""Testes isolados do backfill histórico idempotente em SQLite em memória."""
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import backfill_monetario as backfill_module

from backfill_monetario import ErroBackfillMonetario, backfill_monetario
from migrar_schema_monetario import (
    TABELA_ESTADO,
    definir_fase_migracao,
    migrar_schema_monetario,
)

SCHEMA_LEGADO = """
CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, nome TEXT);
CREATE TABLE fatos (
  data TEXT NOT NULL,
  usuario TEXT NOT NULL,
  tipo TEXT NOT NULL,
  qtd INTEGER NOT NULL DEFAULT 0,
  qtd_unicos INTEGER NOT NULL DEFAULT 0,
  valor REAL NOT NULL DEFAULT 0,
  valor_pago REAL NOT NULL DEFAULT 0,
  valor_aberto REAL NOT NULL DEFAULT 0,
  valor_quebrado REAL NOT NULL DEFAULT 0,
  importado_em TEXT NOT NULL,
  PRIMARY KEY (data, usuario, tipo)
);
CREATE TABLE acordos_posicao (
  capturado_em TEXT PRIMARY KEY,
  data TEXT,
  recebido_periodo REAL,
  a_vencer REAL,
  vencido REAL
);
"""


def banco_com_dados():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA_LEGADO)
    usuarios = (("ana", "Ana"), ("bia", "Bia"), ("caio", "Caio"), ("contato", "Contato"))
    con.executemany("INSERT INTO usuarios(usuario,nome) VALUES (?,?)", usuarios)
    con.executemany(
        "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
        "valor_aberto,valor_quebrado,importado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-10-11", "ana", "deposito", 1, 0, 12.345, 0.0, 0.0, 0.0, "origem"),
            ("2026-10-11", "bia", "acordo", 1, 0, 100.0, 30.0, 70.0, 0.0, "origem"),
            ("2026-10-11", "caio", "promessa", 1, 0, 50.0, 20.0, 25.0, 5.0, "origem"),
            ("2026-10-11", "contato", "contato", 4, 3, 0.0, 0.0, 0.0, 0.0, "origem"),
        ],
    )
    con.execute(
        "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido) "
        "VALUES ('2026-10-11T12:00:00','2026-10-11',-10.5,200.0,15.25)"
    )
    con.commit()
    migrar_schema_monetario(con)
    return con


class TestBackfillMonetario(unittest.TestCase):
    def test_simulacao_nao_escreve_e_propoe_mapeamento_semantico(self):
        con = banco_com_dados()
        try:
            antes = con.execute(
                "SELECT valor,deposito_valor_centavos FROM fatos "
                "WHERE tipo='deposito'"
            ).fetchone()
            resultado = backfill_monetario(con)
            depois = con.execute(
                "SELECT valor,deposito_valor_centavos FROM fatos "
                "WHERE tipo='deposito'"
            ).fetchone()
            self.assertEqual(antes, depois)
            self.assertEqual(resultado["modo"], "simulacao")
            self.assertEqual(resultado["updates_previstos"], 4)
            self.assertEqual(resultado["colunas_a_preencher"], 11)
            self.assertEqual(resultado["campos_pendentes_origem_null"], 0)
            self.assertEqual(resultado["colunas_real_alteradas"], 0)
            self.assertFalse(con.in_transaction)
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "schema_adicionado",
            )
        finally:
            con.close()

    def test_aplica_backfill_sem_alterar_real_ou_concluir_conciliacao(self):
        con = banco_com_dados()
        try:
            antes_real = con.execute(
                "SELECT usuario,valor,valor_pago,valor_aberto,valor_quebrado "
                "FROM fatos ORDER BY usuario"
            ).fetchall()
            antes_posicao = con.execute(
                "SELECT recebido_periodo,a_vencer,vencido FROM acordos_posicao"
            ).fetchone()
            resultado = backfill_monetario(con, aplicar=True)
            self.assertEqual(resultado["modo"], "aplicado")
            self.assertEqual(resultado["colunas_a_preencher"], 11)
            self.assertEqual(
                con.execute(
                    "SELECT deposito_valor_centavos FROM fatos WHERE tipo='deposito'"
                ).fetchone()[0],
                1235,
            )
            self.assertEqual(
                con.execute(
                    "SELECT acordo_valor_centavos,acordo_pago_centavos,"
                    "acordo_pendente_centavos FROM fatos WHERE tipo='acordo'"
                ).fetchone(),
                (10000, 3000, 7000),
            )
            self.assertEqual(
                con.execute(
                    "SELECT promessa_prometido_centavos,promessa_cumprido_centavos,"
                    "promessa_em_aberto_centavos,promessa_quebrado_centavos "
                    "FROM fatos WHERE tipo='promessa'"
                ).fetchone(),
                (5000, 2000, 2500, 500),
            )
            self.assertEqual(
                con.execute(
                    "SELECT recebido_periodo_centavos,a_vencer_centavos,vencido_centavos "
                    "FROM acordos_posicao"
                ).fetchone(),
                (-1050, 20000, 1525),
            )
            self.assertEqual(
                con.execute(
                    "SELECT deposito_valor_centavos,acordo_valor_centavos,"
                    "promessa_prometido_centavos FROM fatos WHERE tipo='contato'"
                ).fetchone(),
                (None, None, None),
            )
            self.assertEqual(
                con.execute(
                    "SELECT usuario,valor,valor_pago,valor_aberto,valor_quebrado "
                    "FROM fatos ORDER BY usuario"
                ).fetchall(),
                antes_real,
            )
            self.assertEqual(
                con.execute(
                    "SELECT recebido_periodo,a_vencer,vencido FROM acordos_posicao"
                ).fetchone(),
                antes_posicao,
            )
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "backfill_em_andamento",
            )
            self.assertFalse(resultado["conciliacao_concluida"])
        finally:
            con.close()

    def test_backfill_repetido_e_idempotente(self):
        con = banco_com_dados()
        try:
            backfill_monetario(con, aplicar=True)
            segunda = backfill_monetario(con, aplicar=True)
            self.assertEqual(segunda["updates_previstos"], 0)
            self.assertEqual(segunda["colunas_a_preencher"], 0)
            self.assertEqual(segunda["campos_pendentes_origem_null"], 0)
        finally:
            con.close()

    def test_aplicar_mantem_lock_durante_planejamento_e_escrita(self):
        with tempfile.TemporaryDirectory() as td:
            caminho = f"{td}/backfill.db"
            origem = banco_com_dados()
            con = sqlite3.connect(caminho, timeout=0.1)
            concorrente = None
            try:
                origem.backup(con)
                origem.close()
                concorrente = sqlite3.connect(caminho, timeout=0.01)

                planejar_original = backfill_module._planejar_fato
                lock_verificado = []

                def planejar_com_writer(linha):
                    if not lock_verificado:
                        self.assertTrue(con.in_transaction)
                        with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                            concorrente.execute(
                                "UPDATE fatos SET valor=valor+0.01 WHERE usuario='ana'"
                            )
                        lock_verificado.append(True)
                    return planejar_original(linha)

                with patch.object(
                    backfill_module,
                    "_planejar_fato",
                    side_effect=planejar_com_writer,
                ):
                    resultado = backfill_monetario(con, aplicar=True)

                self.assertEqual(lock_verificado, [True])
                self.assertEqual(resultado["modo"], "aplicado")
                self.assertEqual(
                    con.execute("SELECT valor FROM fatos WHERE usuario='ana'").fetchone()[0],
                    12.345,
                )
                self.assertEqual(
                    con.execute(
                        "SELECT deposito_valor_centavos FROM fatos WHERE usuario='ana'"
                    ).fetchone()[0],
                    1235,
                )
            finally:
                if concorrente is not None:
                    concorrente.close()
                con.close()

    def test_conflito_de_destino_aborta_sem_sobrescrever_ou_gravar_parcial(self):
        con = banco_com_dados()
        try:
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=999 "
                "WHERE tipo='deposito'"
            )
            con.commit()
            with self.assertRaises(ErroBackfillMonetario):
                backfill_monetario(con, aplicar=True)
            self.assertEqual(
                con.execute(
                    "SELECT deposito_valor_centavos FROM fatos WHERE tipo='deposito'"
                ).fetchone()[0],
                999,
            )
            self.assertIsNone(
                con.execute(
                    "SELECT acordo_valor_centavos FROM fatos WHERE tipo='acordo'"
                ).fetchone()[0]
            )
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "schema_adicionado",
            )
            self.assertFalse(con.in_transaction)
        finally:
            con.close()

    def test_origem_null_permanece_null_e_nao_vira_zero(self):
        con = banco_com_dados()
        try:
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido) "
                "VALUES ('ts-null','2026-10-12',NULL,5.0,0.0)"
            )
            con.commit()
            resultado = backfill_monetario(con, aplicar=True)
            self.assertEqual(resultado["campos_pendentes_origem_null"], 1)
            self.assertEqual(
                con.execute(
                    "SELECT recebido_periodo_centavos,a_vencer_centavos,vencido_centavos "
                    "FROM acordos_posicao WHERE capturado_em='ts-null'"
                ).fetchone(),
                (None, 500, 0),
            )
            with self.assertRaises(Exception):
                definir_fase_migracao(con, "backfill_conciliado")
        finally:
            con.close()

    def test_negativo_nao_autorizado_no_real_historico_aborta_todo_lote(self):
        con = banco_com_dados()
        try:
            con.execute("UPDATE fatos SET valor=-1.00 WHERE tipo='acordo'")
            con.commit()
            with self.assertRaises(ErroBackfillMonetario):
                backfill_monetario(con, aplicar=True)
            self.assertIsNone(
                con.execute(
                    "SELECT deposito_valor_centavos FROM fatos WHERE tipo='deposito'"
                ).fetchone()[0]
            )
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "schema_adicionado",
            )
        finally:
            con.close()

    def test_fases_por_linha_somente_conciliam_apos_verificacao_exata(self):
        con = banco_com_dados()
        try:
            backfill_monetario(con, aplicar=True)
            self.assertEqual(
                {row[0] for row in con.execute("SELECT DISTINCT monetario_fase FROM fatos")},
                {"legado"},
            )
            self.assertEqual(
                {row[0] for row in con.execute("SELECT DISTINCT monetario_fase FROM acordos_posicao")},
                {"legado"},
            )

            definir_fase_migracao(con, "backfill_conciliado")

            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "backfill_conciliado",
            )
            self.assertEqual(
                {row[0] for row in con.execute("SELECT DISTINCT monetario_fase FROM fatos")},
                {"conciliado"},
            )
            self.assertEqual(
                {row[0] for row in con.execute("SELECT DISTINCT monetario_fase FROM acordos_posicao")},
                {"conciliado"},
            )
        finally:
            con.close()

    def test_backfill_nao_pode_ser_reexecutado_apos_conciliacao(self):
        con = banco_com_dados()
        try:
            backfill_monetario(con, aplicar=True)
            definir_fase_migracao(con, "backfill_conciliado")
            with self.assertRaises(ErroBackfillMonetario):
                backfill_monetario(con, aplicar=True)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
