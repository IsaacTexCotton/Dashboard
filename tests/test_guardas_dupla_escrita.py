"""Regressões das guardas de segurança para dupla escrita.

Todos os casos usam somente SQLite descartável; não alteram configurações
externas, não executam migração automática e nunca acessam produção.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import importar
from importar import ErroValidacao
from migrar_schema_monetario import TABELA_ESTADO


class TestGuardasDuplaEscrita(unittest.TestCase):
    def test_dupla_escrita_nao_cria_banco_ausente(self):
        with tempfile.TemporaryDirectory() as diretorio:
            banco = Path(diretorio) / "ausente.sqlite3"
            with patch.object(importar, "DB", str(banco)):
                with self.assertRaisesRegex(
                    ErroValidacao, "banco existente e migrado"
                ):
                    importar._abrir_banco(True)
            self.assertFalse(banco.exists(), "a guarda não pode criar um banco")

    def test_dupla_escrita_nao_migra_banco_legado_automaticamente(self):
        with tempfile.TemporaryDirectory() as diretorio:
            banco = Path(diretorio) / "legado.sqlite3"
            con = sqlite3.connect(banco)
            try:
                con.executescript(importar.SCHEMA)
            finally:
                con.close()

            with patch.object(importar, "DB", str(banco)):
                with self.assertRaisesRegex(
                    ErroValidacao, "schema monetário não está pronto"
                ):
                    importar._abrir_banco(True)

            # Reabre apenas para inspeção: a tentativa de dupla escrita não
            # adicionou colunas, tabela de fase ou triggers de migração.
            con = sqlite3.connect(banco)
            try:
                colunas_fatos = {
                    linha[1] for linha in con.execute("PRAGMA table_info(fatos)")
                }
                colunas_posicao = {
                    linha[1]
                    for linha in con.execute("PRAGMA table_info(acordos_posicao)")
                }
                tabelas = {
                    linha[0]
                    for linha in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                triggers = {
                    linha[0]
                    for linha in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger'"
                    )
                }
            finally:
                con.close()

            self.assertNotIn("deposito_valor_centavos", colunas_fatos)
            self.assertNotIn("monetario_fase", colunas_fatos)
            self.assertNotIn("recebido_periodo_centavos", colunas_posicao)
            self.assertNotIn("monetario_fase", colunas_posicao)
            self.assertNotIn(TABELA_ESTADO, tabelas)
            self.assertEqual(triggers, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
