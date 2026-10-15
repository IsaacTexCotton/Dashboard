"""Testes da escrita dupla usando somente banco SQLite em memória."""
import sqlite3
import unittest
from decimal import Decimal

from escrita_dupla import (
    gravar_dia_duplo,
    preparar_fato_duplo,
    preparar_posicao_dupla,
)
from precisao_monetaria import ErroMonetario
from modelo_monetario import mapear_fato_centavos, mapear_posicao_centavos

DIA = "2026-10-14"


def criar_banco(isolation_level="", database=":memory:"):
    con = sqlite3.connect(database, isolation_level=isolation_level)
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
        monetario_fase TEXT NOT NULL DEFAULT 'legado'
          CHECK (monetario_fase IN ('legado','dual','conciliado')),
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
        ),
        monetario_fase TEXT NOT NULL DEFAULT 'legado'
          CHECK (monetario_fase IN ('legado','dual','conciliado'))
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
    deposito = preparar_fato_duplo(
        dia=DIA, usuario="ana", tipo="deposito", quantidade=1,
        importado_em="agora", campos_monetarios={"valor": Decimal("12.34")},
    )
    acordo = preparar_fato_duplo(
        dia=DIA, usuario="bia", tipo="acordo", quantidade=1,
        importado_em="agora",
        campos_monetarios={
            "valor": Decimal("100.00"),
            "pagos": Decimal("40.00"),
            "pendente": Decimal("60.00"),
        },
    )
    return [deposito, acordo]


def argumentos(fatos=None):
    posicao_legada, posicao_centavos = preparar_posicao_dupla(
        capturado_em="2026-10-14T12:00:00",
        dia=DIA,
        campos_monetarios={
            "valorRecebidoPeriodo": Decimal("20.00"),
            "valorAVencer": Decimal("30.00"),
            "valorVencido": Decimal("40.00"),
        },
    )
    return {
        "dia": DIA,
        "usuarios": {"ana": "Ana", "bia": "Bia"},
        "fatos": fatos if fatos is not None else fatos_exemplo(),
        "posicao_legada": posicao_legada,
        "posicao_centavos": posicao_centavos,
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
            self.assertEqual(
                con.execute("SELECT DISTINCT monetario_fase FROM fatos").fetchall(),
                [("dual",)],
            )
            self.assertEqual(
                con.execute("SELECT monetario_fase FROM acordos_posicao").fetchone()[0],
                "dual",
            )
        finally:
            con.close()

    def test_preparadores_derivam_real_e_centavos_da_mesma_origem_decimal(self):
        fato = preparar_fato_duplo(
            dia=DIA, usuario="negativo", tipo="deposito", quantidade=1,
            importado_em="agora", campos_monetarios={"valor": Decimal("-1.23")},
        )
        self.assertEqual(fato["centavos"]["deposito_valor_centavos"], -123)
        self.assertEqual(fato["legado"]["valor"], -1.23)
        self.assertEqual(fato["legado"]["valor_pago"], 0.0)

        with self.assertRaises(Exception):
            preparar_fato_duplo(
                dia=DIA, usuario="inválido", tipo="deposito", quantidade=1,
                importado_em="agora", campos_monetarios={"valor": Decimal("1.231")},
            )
        with self.assertRaises(Exception):
            preparar_posicao_dupla(
                capturado_em="ts", dia=DIA,
                campos_monetarios={
                    "valorRecebidoPeriodo": Decimal("1.00"),
                    "valorAVencer": Decimal("-1.00"),
                    "valorVencido": Decimal("1.00"),
                },
            )

    def test_rollback_pos_corte_encontra_registro_novo_nas_colunas_real(self):
        con = criar_banco()
        try:
            gravar_dia_duplo(con, **argumentos())
            # Simulação de rollback da leitura: query usa REAL legado, mas
            # confirma que registros pós-corte também foram atualizados ali.
            self.assertEqual(
                con.execute(
                    "SELECT valor FROM fatos WHERE usuario='ana' AND tipo='deposito'"
                ).fetchone()[0],
                12.34,
            )
            self.assertEqual(
                con.execute(
                    "SELECT deposito_valor_centavos FROM fatos WHERE usuario='ana' AND tipo='deposito'"
                ).fetchone()[0],
                1234,
            )
            self.assertEqual(
                con.execute(
                    "SELECT recebido_periodo, recebido_periodo_centavos FROM acordos_posicao"
                ).fetchone(),
                (20.0, 2000),
            )
        finally:
            con.close()

    def test_falha_em_centavos_reverte_o_dia_inteiro(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            con.execute("""
              CREATE TRIGGER falha_centavos BEFORE INSERT ON fatos
              WHEN NEW.acordo_valor_centavos=10000
              BEGIN SELECT RAISE(ABORT, 'falha simulada em centavos'); END;
            """)
            con.commit()
            fatos = fatos_exemplo()
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
              WHEN NEW.tipo='acordo'
              BEGIN SELECT RAISE(ABORT, 'falha simulada no legado'); END;
            """)
            con.commit()
            fatos = fatos_exemplo()
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

    def test_payload_legado_e_centavos_desalinhados_e_rejeitado_antes_da_transacao(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            fatos = fatos_exemplo()
            fatos[0]["legado"]["valor"] = 12.35
            with self.assertRaises(ErroMonetario):
                gravar_dia_duplo(con, **argumentos(fatos))
            self.assertFalse(con.in_transaction)
            self.assertEqual(
                con.execute("SELECT usuario, valor FROM fatos WHERE data=?", (DIA,)).fetchall(),
                [("antigo", 9.99)],
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
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


class TestRollbackPosicaoEscritaDupla(unittest.TestCase):
    def _semear_posicao(self, con):
        con.execute(
            """INSERT INTO acordos_posicao
            (capturado_em, data, recebido_periodo, a_vencer, vencido,
             recebido_periodo_centavos, a_vencer_centavos, vencido_centavos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-10-13T12:00:00", "2026-10-13", 7.0, 8.0, 9.0, 700, 800, 900),
        )
        con.commit()

    def _estado_preexistente(self, con):
        fatos = con.execute(
            "SELECT usuario, tipo, valor, deposito_valor_centavos FROM fatos ORDER BY usuario"
        ).fetchall()
        posicoes = con.execute(
            "SELECT capturado_em, recebido_periodo, recebido_periodo_centavos "
            "FROM acordos_posicao ORDER BY capturado_em"
        ).fetchall()
        importacoes = con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0]
        return fatos, posicoes, importacoes

    def test_falha_em_centavos_da_posicao_reverte_fatos_e_lado_legado(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            self._semear_posicao(con)
            antes = self._estado_preexistente(con)
            con.execute("""
              CREATE TRIGGER falha_centavos_posicao BEFORE INSERT ON acordos_posicao
              WHEN NEW.recebido_periodo_centavos=2000
              BEGIN SELECT RAISE(ABORT, 'falha simulada em centavos da posição'); END;
            """)
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                gravar_dia_duplo(con, **argumentos())
            self.assertEqual(self._estado_preexistente(con), antes)
            self.assertFalse(con.in_transaction)
        finally:
            con.close()

    def test_falha_no_real_da_posicao_reverte_fatos_e_centavos(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            self._semear_posicao(con)
            antes = self._estado_preexistente(con)
            con.execute("""
              CREATE TRIGGER falha_real_posicao BEFORE INSERT ON acordos_posicao
              WHEN NEW.recebido_periodo=20.0
              BEGIN SELECT RAISE(ABORT, 'falha simulada no REAL da posição'); END;
            """)
            con.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                gravar_dia_duplo(con, **argumentos())
            self.assertEqual(self._estado_preexistente(con), antes)
            self.assertFalse(con.in_transaction)
        finally:
            con.close()


# Testes adicionais do contrato revisto da Issue #4. Todos os bancos são
# arquivos temporários criados no próprio teste; nunca usam o banco do app.
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class TestAtomicidadeArquivoELeitorConcorrente(unittest.TestCase):
    def _criar_banco_arquivo_com_estado_anterior(self, caminho):
        con = criar_banco(database=str(caminho))
        semear_fato_legado(con)
        con.execute(
            """INSERT INTO acordos_posicao
            (capturado_em, data, recebido_periodo, a_vencer, vencido,
             recebido_periodo_centavos, a_vencer_centavos, vencido_centavos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-10-14T12:00:00", DIA, 7.0, 8.0, 9.0, 700, 800, 900),
        )
        con.commit()
        con.close()

    def test_interrupcao_de_processo_em_transacao_aberta_recupera_estado_anterior(self):
        with tempfile.TemporaryDirectory(prefix="issue4-crash-") as temp_dir:
            caminho = Path(temp_dir) / "financeiro-sintetico.sqlite"
            self._criar_banco_arquivo_com_estado_anterior(caminho)
            root = Path(__file__).resolve().parents[1]
            child = r"""
import os
import sqlite3
import sys
from test_escrita_dupla import argumentos, gravar_dia_duplo

caminho = sys.argv[1]
con = sqlite3.connect(caminho, timeout=3)
def encerrar_processso_no_meio():
    os._exit(86)
con.create_function("encerrar_processso_no_meio", 0, encerrar_processso_no_meio)
con.execute(
    "CREATE TRIGGER interromper_escrita BEFORE INSERT ON fatos "
    "WHEN NEW.usuario = 'bia' BEGIN SELECT encerrar_processso_no_meio(); END"
)
con.commit()
gravar_dia_duplo(con, **argumentos())
"""
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                [str(root / "tests"), str(root), env.get("PYTHONPATH", "")]
            )
            resultado = subprocess.run(
                [sys.executable, "-c", child, str(caminho)],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(resultado.returncode, 86, resultado.stderr)

            con = sqlite3.connect(caminho, timeout=3)
            try:
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(
                    con.execute(
                        "SELECT usuario, valor, deposito_valor_centavos "
                        "FROM fatos WHERE data=? ORDER BY usuario",
                        (DIA,),
                    ).fetchall(),
                    [("antigo", 9.99, None)],
                )
                self.assertEqual(
                    con.execute(
                        "SELECT capturado_em, recebido_periodo, recebido_periodo_centavos "
                        "FROM acordos_posicao"
                    ).fetchall(),
                    [("2026-10-14T12:00:00", 7.0, 700)],
                )
                self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 0)
                self.assertEqual(
                    con.execute("SELECT usuario FROM usuarios ORDER BY usuario").fetchall(),
                    [("antigo",)],
                )
            finally:
                con.close()

    def test_leitor_concorrente_ve_estado_anterior_ou_lote_duplo_completo(self):
        with tempfile.TemporaryDirectory(prefix="issue4-reader-") as temp_dir:
            caminho = Path(temp_dir) / "financeiro-sintetico.sqlite"
            self._criar_banco_arquivo_com_estado_anterior(caminho)
            entrou_na_transacao = threading.Event()
            liberar_escritor = threading.Event()
            erros_escritor = []

            escritor = sqlite3.connect(
                str(caminho), timeout=3, isolation_level=None, check_same_thread=False
            )
            def pausar_apos_delete():
                entrou_na_transacao.set()
                if not liberar_escritor.wait(timeout=8):
                    raise RuntimeError("timeout do teste esperando liberação do escritor")
                return 0

            escritor.create_function("pausar_apos_delete", 0, pausar_apos_delete)
            escritor.execute("""
                CREATE TRIGGER pausar_no_meio
                AFTER DELETE ON fatos
                BEGIN SELECT pausar_apos_delete(); END
            """)
            escritor.commit()

            def executar_escrita():
                try:
                    gravar_dia_duplo(escritor, **argumentos())
                except BaseException as exc:
                    erros_escritor.append(exc)

            thread = threading.Thread(target=executar_escrita, daemon=True)
            try:
                thread.start()
                self.assertTrue(entrou_na_transacao.wait(timeout=5), "escritor não alcançou a escrita parcial")
                leitor = sqlite3.connect(str(caminho), timeout=3)
                try:
                    # A transação já apagou fatos dentro da visão não confirmada,
                    # mas outro processo deve continuar vendo o estado commitado anterior.
                    durante = leitor.execute(
                        "SELECT usuario, valor, deposito_valor_centavos "
                        "FROM fatos WHERE data=? ORDER BY usuario",
                        (DIA,),
                    ).fetchall()
                    self.assertEqual(durante, [("antigo", 9.99, None)])
                    snapshot_durante = leitor.execute(
                        "SELECT recebido_periodo, recebido_periodo_centavos "
                        "FROM acordos_posicao WHERE capturado_em=?",
                        ("2026-10-14T12:00:00",),
                    ).fetchone()
                    self.assertEqual(snapshot_durante, (7.0, 700))
                finally:
                    liberar_escritor.set()
                    thread.join(timeout=8)
                    leitor.close()

                self.assertFalse(thread.is_alive(), "escritor não terminou")
                self.assertEqual(erros_escritor, [])
                after = sqlite3.connect(str(caminho), timeout=3)
                try:
                    self.assertEqual(
                        after.execute(
                            "SELECT usuario, valor, deposito_valor_centavos "
                            "FROM fatos WHERE data=? ORDER BY usuario",
                            (DIA,),
                        ).fetchall(),
                        [("ana", 12.34, 1234), ("bia", 100.0, None)],
                    )
                    # A leitura acordos_posicao acima só selecionou a métrica
                    # de posição; verifica também as outras duas representações.
                    self.assertEqual(
                        after.execute(
                            "SELECT recebido_periodo, recebido_periodo_centavos, "
                            "a_vencer, a_vencer_centavos, vencido, vencido_centavos "
                            "FROM acordos_posicao WHERE capturado_em=?",
                            ("2026-10-14T12:00:00",),
                        ).fetchone(),
                        (20.0, 2000, 30.0, 3000, 40.0, 4000),
                    )
                    self.assertEqual(after.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 1)
                    self.assertEqual(after.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                finally:
                    after.close()
            finally:
                liberar_escritor.set()
                if thread.is_alive():
                    thread.join(timeout=2)
                escritor.close()
