"""Testes das flags monetárias em ambiente isolado."""

import os
import unittest
from unittest.mock import patch

import importar
from importar import ErroValidacao


class TestFlagsMonetarias(unittest.TestCase):
    def _ler(self, variaveis):
        with patch.dict(os.environ, variaveis, clear=True):
            return importar._modo_dupla_escrita()

    def test_padrao_desliga_escrita_e_leitura(self):
        self.assertFalse(self._ler({}))

    def test_duplica_escrita_usa_nome_atual(self):
        self.assertTrue(self._ler({"DUPLA_ESCRITA": "1"}))

    def test_variavel_antiga_e_fallback_temporario(self):
        self.assertTrue(self._ler({"DASHBOARD_MONETARIO_DUAL_WRITE": "1"}))

    def test_nome_atual_prevalece_sobre_variavel_antiga(self):
        self.assertFalse(
            self._ler({
                "DUPLA_ESCRITA": "0",
                "DASHBOARD_MONETARIO_DUAL_WRITE": "1",
            })
        )

    def test_recusa_valor_invalido_em_dupla_escrita(self):
        with self.assertRaisesRegex(ErroValidacao, "DUPLA_ESCRITA"):
            self._ler({"DUPLA_ESCRITA": "true"})

    def test_recusa_valor_invalido_em_leitura(self):
        with self.assertRaisesRegex(ErroValidacao, "LEITURA_CENTAVOS"):
            self._ler({"LEITURA_CENTAVOS": "yes"})

    def test_recusa_leitura_sem_dupla_escrita(self):
        with self.assertRaisesRegex(ErroValidacao, "exige DUPLA_ESCRITA=1"):
            self._ler({"LEITURA_CENTAVOS": "1"})

    def test_permite_leitura_quando_ambas_as_flags_estao_ativas(self):
        self.assertTrue(self._ler({"DUPLA_ESCRITA": "1", "LEITURA_CENTAVOS": "1"}))

    def test_flag_legada_nao_substitui_dupla_escrita_na_leitura(self):
        with patch.dict(os.environ, {
            "DASHBOARD_MONETARIO_DUAL_WRITE": "1",
            "LEITURA_CENTAVOS": "1",
        }, clear=True):
            with self.assertRaisesRegex(ErroValidacao, "exige DUPLA_ESCRITA=1"):
                importar._modo_dupla_escrita()

    def test_main_recusa_flag_antes_de_abrir_arquivo_ou_banco(self):
        with patch.dict(os.environ, {"LEITURA_CENTAVOS": "1"}, clear=True):
            with self.assertRaisesRegex(ErroValidacao, "exige DUPLA_ESCRITA=1"):
                importar.main(["--dry-run", "--arquivo", "arquivo-que-nao-existe.json"])


if __name__ == "__main__":
    unittest.main()
