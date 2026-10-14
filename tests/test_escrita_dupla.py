"""Testes da escrita dupla usando somente banco SQLite em memória."""
import sqlite3
import unittest
from decimal import Decimal

from escrita_dupla import gravar_dia_duplo
from modelo_monetario import mapear_fato_centavos, mapear_posicao_centavos

DIA = "2026-10-14"


def criar_banco(isolation_level=""):
    con = sqlite3.connect(":memory:", isolation_level=isolation_level)
    con.executescript("""
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
        deposito_valor_centavos INTEGER CHECK (
          deposito_valor_centavos IS NULL OR
          (typeof(deposito_valor_centavos)='integer' AND tipo='deposito')
        ),
        acordo_valor_centavos INTEGER CHECK (
          acordo_valor_centavos IS NULL OR
          (typeof(acordo_valor_centavos)='integer' AND acordo_valor_centavos >= 0 AND tipo='acordo')
        ),
        acordo_pago_centavos INTEGER CHECK (
          acordo_pago_centavos IS NULL OR
          (typeof(acordo_pago_centavos)='integer' AND acordo_pago_centavos >= 0 AND tipo='acordo')
        ),
        acordo_pendente_centavos INTEGER CHECK (
          acordo_pendente_centavos IS NULL OR
          (typeof(acordo_pendente_centavos)='integer' AND tipo='acordo')
        ),
        promessa_prometido_centavos INTEGER CHECK (
          promessa_prometido_centavos IS NULL OR
          (typeof(promessa_prometido_centavos)='integer' AND promessa_prometido_centavos >= 0 AND tipo='promessa')
        ),
        promessa_cumprido_centavos INTEGER CHECK (
          promessa_cumprido_centavos IS NULL OR
          (typeof(promessa_cumprido_centavos)='integer' AND promessa_cumprido_centavos >= 0 AND tipo='promessa')
        ),
        promessa_em_aberto_centavos INTEGER CHECK (
          promessa_em_aberto_centavos IS NULL OR
          (typeof(promessa_em_aberto_centavos)='integer' AND tipo='promessa')
        ),
        promessa_quebrado_centavos INTEGER CHECK (
          promessa_quebrado_centavos IS NULL OR
          (typeof(promessa_quebrado_centavos)='integer' AND promessa_quebrado_centavos >= 0 AND tipo='promessa')
        ),
        PRIMARY KEY(data, usuario, tipo)
    );
    CREATE TABLE acordos_posicao (
        capturado_em TEXT PRIMARY KEY,
        data TEXT,
        recebido_periodo REAL,
        a_vencer REAL,
        vencido REAL,
        recebido_periodo_centavos INTEGER CHECK (
          recebido_periodo_centavos IS NULL OR typeof(recebido_periodo_centavos)='integer'
        ),
        a_vencer_centavos INTEGER CHECK (
          a_vencer_centavos IS NULL OR
          (typeof(a_vencer_centavos)='integer' AND a_vencer_centavos >= 0)
        ),
        vencido_centavos INTEGER CHECK (
          vencido_centavos IS NULL OR
          (typeof(vencido_centavos)='integer' AND vencido_centavos >= 0)
        )
    );
    CREATE TABLE importacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quando TEXT,
        origem TEXT,
        inicio TEXT,
        fim TEXT,
        linhas INTEGER
    );
    """)
    return con


def fatos_exemplo():
    deposito_legado = {
        "data": DIA, "usuario": "ana", "tipo": "deposito", "qtd": 1,
        "qtd_unicos": 0, "valor": 12.34, "valor_pago": 0.0,
        "valor_aberto": 0.0, "valor_quebrado": 0.0, "importado_em": "agora",
    }
    acordo_legado = {
        "data": DIA, "usuario": "bia", "tipo": "acordo", "qtd": 1,
        "qtd_unicos": 0, "valor": 100.0, "valor_pago": 40.0,
        "valor_aberto": 60.0, "valor_quebrado": 0.0, "importado_em": "agora",
    }
    return [
        {"legado": deposito_legado, "centavos": mapear_fato_centavos(
            "deposito", {"valor": Decimal("12.34")}
        )},
        {"legado": acordo_legado, "centavos": mapear_fato_centavos(
            "acordo", {"valor": Decimal("100.00"), "pagos": Decimal("40.00"),
                       "pendente": Decimal("60.00")}
        )},
    ]


def argumentos(fatos=None):
    return {
        "dia": DIA,
        "usuarios": {"ana": "Ana", "bia": "Bia"},
        "fatos": fatos if fatos is not None else fatos_exemplo(),
        "posicao_legada": {
            "capturado_em": "2026-10-14T12:00:00",
            "data": DIA,
            "recebido_periodo": 20.0,
            "a_vencer": 30.0,
            "vencido": 40.0,
        },
        "posicao_centavos": mapear_posicao_centavos({
            "valorRecebidoPeriodo": Decimal("20.00"),
            "valorAVencer": Decimal("30.00"),
            "valorVencido": Decimal("40.00"),
        }),
        "origem": "fixture",
        "quando": "2026-10-14T12:01:00",
    }


def semear_fato_legado(con):
    con.execute(
        """INSERT INTO fatos
        (data, usuario, tipo, qtd, qtd_unicos, valor, valor_pago,
         valor_aberto, valor_quebrado, importado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (DIA, "antigo", "deposito", 1, 0, 9.99, 0.0, 0.0, 0.0, "antes"),
    )
    con.execute(
        "INSERT INTO usuarios(usuario,nome) VALUES (?,?)", ("antigo", "Nome antigo")
    )
    con.commit()


class TestEscritaDupla(unittest.TestCase):
    def test_grava_legado_e_centavos_no_mesmo_lote(self):
        con = criar_banco()
        try:
            total = gravar_dia_duplo(con, **argumentos())
            self.assertEqual(total, 2)
            rows = con.execute(
                "SELECT usuario, valor, deposito_valor_centavos, "
                "acordo_valor_centavos, acordo_pago_centavos, acordo_pendente_centavos "
                "FROM fatos ORDER BY usuario"
            ).fetchall()
            self.assertEqual(rows[0], ("ana", 12.34, 1234, None, None, None))
            self.assertEqual(rows[1], ("bia", 100.0, None, 10000, 4000, 6000))
            pos = con.execute(
                "SELECT recebido_periodo, recebido_periodo_centavos, "
                "a_vencer, a_vencer_centavos, vencido, vencido_centavos "
                "FROM acordos_posicao"
            ).fetchone()
            self.assertEqual(pos, (20.0, 2000, 30.0, 3000, 40.0, 4000))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 1)
        finally:
            con.close()

    def test_falha_em_centavos_reverte_o_dia_inteiro(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            con.execute("""
              CREATE TRIGGER falha_centavos BEFORE INSERT ON fatos
              WHEN NEW.acordo_valor_centavos=999999
              BEGIN SELECT RAISE(ABORT, 'falha simulada em centavos'); END;
            """)
            con.commit()
            fatos = fatos_exemplo()
            fatos[1]["centavos"]["acordo_valor_centavos"] = 999999
            with self.assertRaises(sqlite3.IntegrityError):
                gravar_dia_duplo(con, **argumentos(fatos))
            self.assertEqual(
                con.execute("SELECT usuario, valor FROM fatos WHERE data=?", (DIA,)).fetchall(),
                [("antigo", 9.99)],
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
            self.assertEqual(con.execute(
                "SELECT nome FROM usuarios WHERE usuario='antigo'"
            ).fetchone()[0], "Nome antigo")
        finally:
            con.close()

    def test_falha_no_writer_legado_reverte_tambem_centavos(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            con.execute("""
              CREATE TRIGGER falha_legado BEFORE INSERT ON fatos
              WHEN NEW.valor=777.0
              BEGIN SELECT RAISE(ABORT, 'falha simulada no legado'); END;
            """)
            con.commit()
            fatos = fatos_exemplo()
            fatos[1]["legado"]["valor"] = 777.0
            with self.assertRaises(sqlite3.IntegrityError):
                gravar_dia_duplo(con, **argumentos(fatos))
            self.assertEqual(
                con.execute("SELECT usuario, valor FROM fatos WHERE data=?", (DIA,)).fetchall(),
                [("antigo", 9.99)],
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
        finally:
            con.close()

    def test_autocommit_tambem_usa_transacao_explicita(self):
        con = criar_banco(isolation_level=None)
        try:
            self.assertFalse(con.in_transaction)
            self.assertEqual(gravar_dia_duplo(con, **argumentos()), 2)
            self.assertFalse(con.in_transaction)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fatos").fetchone()[0], 2)
        finally:
            con.close()

    def test_payload_invalido_falha_antes_de_comecar_transacao(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            fatos = fatos_exemplo()
            del fatos[1]["centavos"]["acordo_pago_centavos"]
            with self.assertRaises(Exception):
                gravar_dia_duplo(con, **argumentos(fatos))
            self.assertFalse(con.in_transaction)
            self.assertEqual(
                con.execute("SELECT usuario FROM fatos WHERE data=?", (DIA,)).fetchall(),
                [("antigo",)],
            )
        finally:
            con.close()

    def test_transacao_aninhada_e_rejeitada(self):
        con = criar_banco()
        try:
            con.execute("BEGIN")
            with self.assertRaises(Exception):
                gravar_dia_duplo(con, **argumentos())
            con.rollback()
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
