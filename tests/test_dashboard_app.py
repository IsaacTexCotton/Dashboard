"""Testes da prévia visual e da leitura monetária em SQLite sintético."""
import sqlite3
import unittest

import importar
from dashboard_app import (
    DashboardStore,
    ErroDashboard,
    HTML,
    criar_conexao_demo,
    determinar_modo_leitura,
    montar_dados_painel,
    validar_leitura_centavos,
)


class TestConfiguracaoLeituraDashboard(unittest.TestCase):
    def test_padrao_le_real_legado(self):
        self.assertFalse(determinar_modo_leitura({}))

    def test_leitura_centavos_exige_dupla_escrita_explicita(self):
        with self.assertRaisesRegex(ErroDashboard, "exige DUPLA_ESCRITA=1"):
            determinar_modo_leitura({"LEITURA_CENTAVOS": "1"})
        with self.assertRaisesRegex(ErroDashboard, "exige DUPLA_ESCRITA=1"):
            determinar_modo_leitura({"LEITURA_CENTAVOS": "1", "DUPLA_ESCRITA": "0"})

    def test_flags_invalidas_sao_recusadas(self):
        for env in ({"LEITURA_CENTAVOS": "yes"}, {"DUPLA_ESCRITA": "true"}):
            with self.subTest(env=env), self.assertRaises(ErroDashboard):
                determinar_modo_leitura(env)

    def test_ambas_flags_ativas_habilitam_modo_cents(self):
        self.assertTrue(determinar_modo_leitura({"DUPLA_ESCRITA": "1", "LEITURA_CENTAVOS": "1"}))


class TestPainelDemo(unittest.TestCase):
    def setUp(self):
        self.con = criar_conexao_demo()

    def tearDown(self):
        self.con.close()

    def test_demo_tem_dados_sinteticos_conciliados(self):
        validar_leitura_centavos(self.con)
        result = montar_dados_painel(self.con, leitura_centavos=True, demo=True)
        self.assertTrue(result["demo"])
        self.assertEqual(result["resumo"]["depositos_centavos"], 2_500_000)
        self.assertEqual(result["resumo"]["acordos_centavos"], 2_000_000)
        self.assertEqual(result["resumo"]["acordos_pagos_centavos"], 0)
        self.assertEqual(result["resumo"]["acordos_pendentes_centavos"], 2_000_000)
        self.assertEqual(result["resumo"]["promessas_centavos"], 4_000_000)
        self.assertEqual(result["resumo"]["contatos_registros"], 130)
        self.assertEqual(result["resumo"]["contatos_unicos_por_usuario"], 100)
        self.assertEqual(result["snapshot"]["a_vencer_centavos"], 100_000_000)
        self.assertEqual(result["snapshot"]["vencido_centavos"], 20_000_000)

    def test_leitura_centavos_e_real_produzem_mesmos_valores_na_demo(self):
        legado = montar_dados_painel(self.con, leitura_centavos=False, demo=True)
        centavos = montar_dados_painel(self.con, leitura_centavos=True, demo=True)
        for key in (
            "depositos_centavos", "acordos_centavos", "acordos_pagos_centavos",
            "acordos_pendentes_centavos", "promessas_centavos",
            "promessas_cumpridas_centavos", "promessas_em_aberto_centavos",
            "promessas_quebradas_centavos",
        ):
            self.assertEqual(legado["resumo"][key], centavos["resumo"][key], key)

    def test_filtro_de_periodo_vazio_nao_reusa_totais_fora_da_faixa(self):
        result = montar_dados_painel(
            self.con, inicio="2026-10-12", fim="2026-10-12",
            leitura_centavos=True, demo=True,
        )
        self.assertEqual(result["resumo"]["depositos_centavos"], 0)
        self.assertEqual(result["resumo"]["contatos_registros"], 0)
        self.assertIsNone(result["snapshot"])
        self.assertEqual(result["diario"], [])

    def test_periodo_invertido_e_rejeitado(self):
        with self.assertRaisesRegex(ErroDashboard, "posterior"):
            montar_dados_painel(
                self.con, inicio="2026-10-14", fim="2026-10-13",
                leitura_centavos=True, demo=True,
            )

    def test_demo_store_nao_depende_de_banco_persistente(self):
        store = DashboardStore(demo=True, leitura_centavos=True)
        try:
            self.assertIsNone(store.db_path)
            self.assertTrue(store.data()["demo"])
        finally:
            store.demo_connection.close()

    def test_schema_sem_conciliacao_nao_habilita_leitura_centavos(self):
        con = sqlite3.connect(":memory:")
        try:
            con.row_factory = sqlite3.Row
            con.executescript(importar.SCHEMA)
            with self.assertRaises(ErroDashboard):
                validar_leitura_centavos(con)
        finally:
            con.close()


    def test_metadata_de_importacao_e_intervalo_nao_inferem_cadencia(self):
        result = montar_dados_painel(
            self.con, inicio="2026-10-12", fim="2026-10-14",
            leitura_centavos=True, demo=False,
        )
        meta = result["atualizacao"]
        self.assertTrue(meta["disponivel"])
        self.assertEqual(meta["ultima_importacao"]["origem_rotulo"], "Demonstração sintética")
        self.assertTrue(meta["ultima_importacao"]["quando"])
        self.assertIsInstance(meta["ultima_importacao"]["linhas"], int)
        self.assertEqual(meta["importacoes_no_periodo"], 1)
        self.assertEqual(meta["dias_com_importacao_registrada"], 1)
        self.assertEqual(meta["dias_calendario_periodo"], 3)
        self.assertIn("não prova a cadência", meta["nota"])

    def test_demo_nao_apresenta_horario_de_criacao_como_recencia_operacional(self):
        result = montar_dados_painel(self.con, leitura_centavos=True, demo=True)
        meta = result["atualizacao"]
        self.assertTrue(meta["demo"])
        self.assertFalse(meta["disponivel"])
        self.assertIsNone(meta["ultima_importacao"])
        self.assertIn("sem recência operacional", meta["motivo"])

    def test_metadados_ausentes_nao_bloqueiam_leitura_dos_indicadores(self):
        self.con.execute("DROP TABLE importacoes")
        result = montar_dados_painel(self.con, leitura_centavos=True, demo=False)
        self.assertEqual(result["resumo"]["depositos_centavos"], 2_500_000)
        self.assertFalse(result["atualizacao"]["disponivel"])
        self.assertIsNone(result["atualizacao"]["ultima_importacao"])

    def test_erro_de_leitura_limpa_resultados_antigos_na_interface_local(self):
        self.assertIn("function limparPainel(mensagem)", HTML)
        self.assertIn("limparPainel(error.message", HTML)
        self.assertIn('"sourceChip","periodLabel","depositosValue"', HTML)
        self.assertIn("Não foi possível validar os dados para o período selecionado.", HTML)
        self.assertIn('$("periodImportCoverage").textContent="—"', HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
