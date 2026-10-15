"""Testes isolados da migração aditiva monetária em SQLite descartável."""
import hashlib
import sqlite3
import unittest
from unittest.mock import patch

import migrar_schema_monetario as schema_monetario

from migrar_schema_monetario import (
    ErroMigracaoMonetaria,
    FASES_VALIDAS,
    TABELA_ESTADO,
    _COLUNAS,
    ativar_triggers_obrigatoriedade,
    definir_fase_migracao,
    migrar_schema_monetario,
    validar_schema_monetario,
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


def banco_legado():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA_LEGADO)
    con.execute("INSERT INTO usuarios(usuario,nome) VALUES ('ana','Ana')")
    con.execute(
        "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
        "valor_aberto,valor_quebrado,importado_em) "
        "VALUES ('2026-10-14','ana','deposito',1,0,12.34,0.0,0.0,0.0,'origem')"
    )
    con.commit()
    return con


class TestMigracaoSchemaMonetario(unittest.TestCase):
    def test_adiciona_13_colunas_sem_alterar_valores_legados(self):
        con = banco_legado()
        try:
            resultado = migrar_schema_monetario(con)
            self.assertEqual(resultado["total_colunas"], 13)
            self.assertEqual(len(resultado["colunas_criadas"]), 13)
            self.assertEqual(len(resultado["triggers_fase_criados"]), 4)
            self.assertEqual(resultado["fase"], "schema_adicionado")
            self.assertEqual(
                con.execute(
                    "SELECT data, usuario, tipo, valor, valor_pago, valor_aberto, "
                    "valor_quebrado, importado_em FROM fatos"
                ).fetchone(),
                ("2026-10-14", "ana", "deposito", 12.34, 0.0, 0.0, 0.0, "origem"),
            )
            self.assertIsNone(
                con.execute(
                    "SELECT deposito_valor_centavos FROM fatos"
                ).fetchone()[0]
            )
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM fatos").fetchone()[0],
                "legado",
            )
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM acordos_posicao").fetchall(),
                [],
            )
        finally:
            con.close()

    def test_checksum_preserva_todos_os_valores_real_legados(self):
        con = banco_legado()
        try:
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido) "
                "VALUES ('2026-10-14T12:00:00','2026-10-14',123.45,67.89,10.11)"
            )
            con.commit()

            def checksum_reais():
                fatos = con.execute(
                    "SELECT data,usuario,tipo,valor,valor_pago,valor_aberto,valor_quebrado "
                    "FROM fatos ORDER BY data,usuario,tipo"
                ).fetchall()
                posicoes = con.execute(
                    "SELECT capturado_em,data,recebido_periodo,a_vencer,vencido "
                    "FROM acordos_posicao ORDER BY capturado_em"
                ).fetchall()
                serializado = repr((fatos, posicoes)).encode("utf-8")
                return hashlib.sha256(serializado).hexdigest()

            antes = checksum_reais()
            migrar_schema_monetario(con)
            depois = checksum_reais()

            self.assertEqual(antes, depois)
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM fatos").fetchone()[0],
                "legado",
            )
            self.assertEqual(
                con.execute(
                    "SELECT monetario_fase FROM acordos_posicao WHERE capturado_em=?",
                    ("2026-10-14T12:00:00",),
                ).fetchone()[0],
                "legado",
            )
        finally:
            con.close()

    def test_migracao_e_idempotente(self):
        con = banco_legado()
        try:
            primeira = migrar_schema_monetario(con)
            segunda = migrar_schema_monetario(con)
            self.assertEqual(len(primeira["colunas_criadas"]), 13)
            self.assertEqual(len(primeira["triggers_fase_criados"]), 4)
            self.assertEqual(segunda["colunas_criadas"], [])
            self.assertEqual(segunda["triggers_fase_criados"], [])
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM pragma_table_info('fatos')").fetchone()[0],
                19,
            )
        finally:
            con.close()

    def test_checks_por_tipo_e_sinal(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            # Completa a linha de depósito com um valor novo para que os CHECKs
            # por tipo e de inteiro possam ser avaliados.
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=-1234 WHERE tipo='deposito'"
            )
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET acordo_valor_centavos=100 WHERE tipo='deposito'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET deposito_valor_centavos=1.5 WHERE tipo='deposito'"
                )
            # Limpa a transação aberta pelas tentativas que falharam.
            con.rollback()
            con.execute(
                "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
                "valor_aberto,valor_quebrado,importado_em,acordo_valor_centavos,"
                "acordo_pago_centavos,acordo_pendente_centavos) "
                "VALUES ('2026-10-14','bia','acordo',1,0,10.0,5.0,5.0,0.0,'origem',"
                "1000,500,-50)"
            )
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET acordo_pago_centavos=-1 "
                    "WHERE usuario='bia' AND tipo='acordo'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET promessa_quebrado_centavos=-1 "
                    "WHERE usuario='bia' AND tipo='acordo'"
                )
        finally:
            con.close()

    def test_checks_de_posicao_permitindo_sinal_somente_em_recebido(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,"
                "a_vencer,vencido,recebido_periodo_centavos,a_vencer_centavos,"
                "vencido_centavos) VALUES ('ts','2026-10-14',-1.0,2.0,3.0,-100,200,300)"
            )
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE acordos_posicao SET a_vencer_centavos=-1 WHERE capturado_em='ts'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE acordos_posicao SET vencido_centavos=-1 WHERE capturado_em='ts'"
                )
        finally:
            con.close()

    def test_validacao_recusa_guarda_fase_ausente_e_migracao_reconstroi(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            con.execute("DROP TRIGGER trg_monetario_fatos_fase_global_insert")
            con.commit()

            with self.assertRaisesRegex(
                ErroMigracaoMonetaria,
                "guarda de fase global ausente",
            ):
                validar_schema_monetario(con)

            resultado = migrar_schema_monetario(con)
            self.assertIn(
                "trg_monetario_fatos_fase_global_insert",
                resultado["triggers_fase_criados"],
            )
            self.assertEqual(validar_schema_monetario(con), "schema_adicionado")
        finally:
            con.close()

    def test_marcador_por_linha_aceita_somente_fases_validas(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            con.execute("UPDATE fatos SET monetario_fase='dual' WHERE usuario='ana'")
            con.commit()
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM fatos WHERE usuario='ana'").fetchone()[0],
                "dual",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET monetario_fase='fase_desconhecida' WHERE usuario='ana'"
                )
        finally:
            con.close()

    def test_schema_incompativel_aborta_sem_alterar(self):
        con = banco_legado()
        try:
            con.execute("ALTER TABLE fatos ADD COLUMN deposito_valor_centavos INTEGER")
            con.commit()
            antes = [r[1] for r in con.execute("PRAGMA table_info(fatos)")]
            with self.assertRaises(ErroMigracaoMonetaria):
                migrar_schema_monetario(con)
            depois = [r[1] for r in con.execute("PRAGMA table_info(fatos)")]
            self.assertEqual(depois, antes)
            self.assertNotIn(TABELA_ESTADO, {
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            })
        finally:
            con.close()

    def test_nao_inferir_legado_se_ja_existirem_centavos_sem_marcador(self):
        con = banco_legado()
        try:
            for coluna in _COLUNAS:
                con.execute(
                    f"ALTER TABLE {coluna.tabela} ADD COLUMN {coluna.nome} "
                    f"INTEGER CHECK ({coluna.check})"
                )
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1234 WHERE tipo='deposito'"
            )
            con.commit()

            with self.assertRaisesRegex(
                ErroMigracaoMonetaria,
                "já existem valores em centavos",
            ):
                migrar_schema_monetario(con)

            self.assertNotIn(
                "monetario_fase",
                {row[1] for row in con.execute("PRAGMA table_info(fatos)")},
            )
            self.assertNotIn(TABELA_ESTADO, {
                row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            })
        finally:
            con.close()

    def test_tabela_legada_ausente_aborta(self):
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE TABLE fatos (data TEXT, usuario TEXT, tipo TEXT)")
            con.commit()
            with self.assertRaises(ErroMigracaoMonetaria):
                migrar_schema_monetario(con)
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM pragma_table_info('fatos')").fetchone()[0],
                3,
            )
        finally:
            con.close()

    def test_fases_validas_e_progressao(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            self.assertEqual(FASES_VALIDAS[0], "schema_adicionado")
            definir_fase_migracao(con, "backfill_em_andamento")
            with self.assertRaises(ErroMigracaoMonetaria):
                definir_fase_migracao(con, "schema_adicionado")
            with self.assertRaises(ErroMigracaoMonetaria):
                definir_fase_migracao(con, "backfill_conciliado")
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1234 WHERE tipo='deposito'"
            )
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido,"
                "recebido_periodo_centavos,a_vencer_centavos,vencido_centavos) "
                "VALUES ('ts_existente','2026-10-14',1.0,2.0,3.0,100,200,300)"
            )
            con.commit()
            definir_fase_migracao(con, "backfill_conciliado")
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO} WHERE id=1").fetchone()[0],
                "backfill_conciliado",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
                    "valor_aberto,valor_quebrado,importado_em) "
                    "VALUES ('2026-10-15','legado_novo','deposito',1,0,1.0,0,0,0,'agora')"
                )
            con.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE fatos SET monetario_fase='legado' WHERE usuario='ana'")
            con.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido) "
                    "VALUES ('ts_novo','2026-10-14',1.0,2.0,3.0)"
                )
            con.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE acordos_posicao SET monetario_fase='legado' "
                    "WHERE capturado_em='ts_existente'"
                )
            con.rollback()
            with self.assertRaises(ErroMigracaoMonetaria):
                definir_fase_migracao(con, "backfill_em_andamento")
        finally:
            con.close()

    def test_conciliacao_e_transicao_ocorrem_dentro_de_begin_immediate(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            definir_fase_migracao(con, "backfill_em_andamento")
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1234 WHERE tipo='deposito'"
            )
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido,"
                "recebido_periodo_centavos,a_vencer_centavos,vencido_centavos) "
                "VALUES ('ts_lock','2026-10-14',-10.5,200.0,15.25,-1050,20000,1525)"
            )
            con.commit()

            original = schema_monetario.verificar_conciliacao_monetaria
            chamadas = []

            def verificar_com_transacao(conexao):
                chamadas.append(conexao.in_transaction)
                self.assertTrue(conexao.in_transaction, "verificação fora de transação")
                return original(conexao)

            with patch.object(
                schema_monetario,
                "verificar_conciliacao_monetaria",
                side_effect=verificar_com_transacao,
            ):
                definir_fase_migracao(con, "backfill_conciliado")

            self.assertEqual(chamadas, [True])
            self.assertFalse(con.in_transaction)
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO} WHERE id=1").fetchone()[0],
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

    def test_conciliacao_divergente_nao_altera_nenhuma_fase(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            definir_fase_migracao(con, "backfill_em_andamento")
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1235 WHERE tipo='deposito'"
            )
            con.commit()

            with self.assertRaisesRegex(
                ErroMigracaoMonetaria,
                "conciliação incompleta ou divergente",
            ):
                definir_fase_migracao(con, "backfill_conciliado")

            self.assertFalse(con.in_transaction)
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO} WHERE id=1").fetchone()[0],
                "backfill_em_andamento",
            )
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM fatos WHERE usuario='ana'").fetchone()[0],
                "legado",
            )
        finally:
            con.close()

    def test_fase_nao_pode_pular_backfill(self):
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(SCHEMA_LEGADO)
            con.commit()
            migrar_schema_monetario(con)
            with self.assertRaises(ErroMigracaoMonetaria):
                definir_fase_migracao(con, "backfill_conciliado")
            self.assertEqual(
                con.execute(f"SELECT fase FROM {TABELA_ESTADO}").fetchone()[0],
                "schema_adicionado",
            )
        finally:
            con.close()

    def test_triggers_so_ativam_depois_de_backfill_conciliado(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            with self.assertRaises(ErroMigracaoMonetaria):
                ativar_triggers_obrigatoriedade(con)
            definir_fase_migracao(con, "backfill_em_andamento")
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1234 WHERE tipo='deposito'"
            )
            con.commit()
            definir_fase_migracao(con, "backfill_conciliado")
            criados = ativar_triggers_obrigatoriedade(con)
            self.assertEqual(len(criados), 4)
            self.assertEqual(ativar_triggers_obrigatoriedade(con), [])
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
                    "valor_aberto,valor_quebrado,importado_em,monetario_fase) "
                    "VALUES ('2026-10-15','sem-centavos','deposito',1,0,1.0,0,0,0,'agora','dual')"
                )
            con.rollback()
            con.execute(
                "INSERT INTO fatos(data,usuario,tipo,qtd,qtd_unicos,valor,valor_pago,"
                "valor_aberto,valor_quebrado,importado_em,deposito_valor_centavos,monetario_fase) "
                "VALUES ('2026-10-15','com-centavos','deposito',1,0,1.0,0,0,0,'agora',100,'dual')"
            )
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE fatos SET deposito_valor_centavos=NULL "
                    "WHERE usuario='com-centavos'"
                )
        finally:
            con.close()

    def test_trigger_posicao_exige_tres_metricas_apos_conciliacao(self):
        con = banco_legado()
        try:
            migrar_schema_monetario(con)
            definir_fase_migracao(con, "backfill_em_andamento")
            con.execute(
                "UPDATE fatos SET deposito_valor_centavos=1234 WHERE tipo='deposito'"
            )
            con.execute(
                "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,"
                "a_vencer,vencido,recebido_periodo_centavos,a_vencer_centavos,"
                "vencido_centavos) VALUES ('ts','2026-10-14',1,2,3,100,200,300)"
            )
            con.commit()
            definir_fase_migracao(con, "backfill_conciliado")
            ativar_triggers_obrigatoriedade(con)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO acordos_posicao(capturado_em,data,recebido_periodo,a_vencer,vencido,monetario_fase) "
                    "VALUES ('ts2','2026-10-14',1,2,3,'dual')"
                )
        finally:
            con.close()

    def test_falha_no_meio_da_migracao_faria_rollback_ddl(self):
        con = banco_legado()
        try:
            # Coluna preexistente sem CHECK detectada antes de qualquer DDL.
            con.execute("ALTER TABLE acordos_posicao ADD COLUMN vencido_centavos TEXT")
            con.commit()
            antes_fatos = [r[1] for r in con.execute("PRAGMA table_info(fatos)")]
            antes_pos = [r[1] for r in con.execute("PRAGMA table_info(acordos_posicao)")]
            with self.assertRaises(ErroMigracaoMonetaria):
                migrar_schema_monetario(con)
            self.assertEqual([r[1] for r in con.execute("PRAGMA table_info(fatos)")], antes_fatos)
            self.assertEqual([r[1] for r in con.execute("PRAGMA table_info(acordos_posicao)")], antes_pos)
            self.assertNotIn(TABELA_ESTADO, {
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            })
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
