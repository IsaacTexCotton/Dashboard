"""Testes da prévia visual e da leitura monetária em SQLite sintético."""
import copy
import sqlite3
import unittest
from pathlib import Path

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
        self.assertEqual(result["resumo"]["depositos_centavos"], 2_780_000)
        self.assertEqual(result["resumo"]["acordos_centavos"], 2_630_000)
        self.assertEqual(result["resumo"]["acordos_pagos_centavos"], 650_000)
        self.assertEqual(result["resumo"]["acordos_pendentes_centavos"], 1_980_000)
        self.assertEqual(result["resumo"]["promessas_centavos"], 4_670_000)
        self.assertEqual(result["resumo"]["contatos_registros"], 148)
        self.assertEqual(result["resumo"]["contatos_unicos_por_usuario"], 108)
        self.assertEqual(result["cobertura_dados"]["estado"], "fatos_presentes")
        self.assertEqual(result["cobertura_dados"]["linhas_fatos_no_periodo"], 18)
        self.assertEqual(result["cobertura_dados"]["linhas_por_tipo"], {
            "deposito": 5, "acordo": 5, "promessa": 3, "contato": 5,
        })
        self.assertEqual(result["snapshot"]["a_vencer_centavos"], 88_000_000)
        self.assertEqual(result["snapshot"]["vencido_centavos"], 17_500_000)

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
        self.assertEqual(result["cobertura_dados"]["estado"], "sem_fatos_demo")
        self.assertEqual(result["cobertura_dados"]["linhas_fatos_no_periodo"], 0)
        self.assertEqual(result["cobertura_dados"]["linhas_por_tipo"], {
            "deposito": 0, "acordo": 0, "promessa": 0, "contato": 0,
        })
        self.assertIn("não confirmam", result["cobertura_dados"]["mensagem"])
        self.assertFalse(result["cobertura_dados"]["snapshot_disponivel"])

    def test_ausencia_de_um_tipo_nao_e_apresentada_como_valor_zero_confirmado(self):
        self.con.execute("DELETE FROM fatos WHERE tipo = 'deposito'")
        result = montar_dados_painel(self.con, leitura_centavos=True, demo=True)
        coverage = result["cobertura_dados"]
        self.assertEqual(coverage["estado"], "fatos_presentes")
        self.assertEqual(coverage["linhas_por_tipo"]["deposito"], 0)
        self.assertGreater(coverage["linhas_fatos_no_periodo"], 0)
        self.assertIn('temLinha("deposito")?money(s.depositos_centavos):"—"', HTML)
        self.assertIn("zero não confirma ausência de movimento", HTML)

    def test_snapshot_sem_fatos_fica_separado_da_cobertura_de_fluxo(self):
        self.con.execute("DELETE FROM fatos")
        result = montar_dados_painel(self.con, leitura_centavos=True, demo=True)
        self.assertEqual(result["cobertura_dados"]["estado"], "somente_snapshot")
        self.assertTrue(result["cobertura_dados"]["snapshot_disponivel"])
        self.assertEqual(result["cobertura_dados"]["linhas_fatos_no_periodo"], 0)

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
            self.con, inicio="2026-10-15", fim="2026-10-17",
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
        self.assertEqual(result["resumo"]["depositos_centavos"], 2_780_000)
        self.assertFalse(result["atualizacao"]["disponivel"])
        self.assertIsNone(result["atualizacao"]["ultima_importacao"])

    def test_erro_de_leitura_limpa_resultados_antigos_na_interface_local(self):
        self.assertIn("function limparPainel(mensagem)", HTML)
        self.assertIn("limparPainel(error.message", HTML)
        self.assertIn('"sourceChip","periodLabel","depositosValue"', HTML)
        self.assertIn("Não foi possível validar os dados para o período selecionado.", HTML)
        self.assertIn('$("periodImportCoverage").textContent="—"', HTML)
        self.assertIn('$("dataCoverageNotice").textContent=mensagem', HTML)
        self.assertIn('id="dataCoverageNotice"', HTML)
        self.assertIn('id="acordosMeta"', HTML)
        self.assertIn('id="promessasMeta"', HTML)
        self.assertIn('id="contatosMeta"', HTML)



class TestComparacaoPeriodos(unittest.TestCase):
    def criar_banco_com_importacoes(self, *dias):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.executescript(importar.SCHEMA)
        arquivo = Path(__file__).resolve().parents[1] / "amostra_resposta.json"
        original = importar._carregar_arquivo(str(arquivo))
        for dia in dias:
            resposta = copy.deepcopy(original)
            resposta["data"]["inicio"] = dia
            resposta["data"]["fim"] = dia
            resposta["timestamp"] = dia + "T12:00:00"
            importar.gravar(con, dia, resposta, "arquivo")
        return con

    def test_comparacao_e_suspensa_quando_um_tipo_de_fato_nao_tem_linha_no_periodo_atual(self):
        con = self.criar_banco_com_importacoes("2026-10-12", "2026-10-13")
        try:
            con.execute("DELETE FROM fatos WHERE data = ? AND tipo = 'deposito'", ("2026-10-13",))
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-13",
                leitura_centavos=False, demo=False,
            )
            self.assertFalse(result["comparacao"]["disponivel"])
            self.assertIn("faltam linhas de fatos para depósitos", result["comparacao"]["motivo"])
            self.assertEqual(result["cobertura_dados"]["linhas_por_tipo"]["deposito"], 0)
        finally:
            con.close()

    def test_comparacao_e_suspensa_quando_um_tipo_de_fato_nao_tem_linha_no_periodo_anterior(self):
        con = self.criar_banco_com_importacoes("2026-10-12", "2026-10-13")
        try:
            con.execute("DELETE FROM fatos WHERE data = ? AND tipo = 'promessa'", ("2026-10-12",))
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-13",
                leitura_centavos=False, demo=False,
            )
            self.assertFalse(result["comparacao"]["disponivel"])
            self.assertIn("faltam linhas de fatos para promessas", result["comparacao"]["motivo"])
        finally:
            con.close()

    def test_compara_fluxos_em_periodos_equivalentes_com_cobertura_alinhada(self):
        con = self.criar_banco_com_importacoes("2026-10-12", "2026-10-13")
        try:
            con.execute(
                "UPDATE fatos SET valor = valor + 50 "
                "WHERE data = ? AND tipo = 'deposito'",
                ("2026-10-13",),
            )
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-13",
                leitura_centavos=False, demo=False,
            )
            comparison = result["comparacao"]
            self.assertTrue(comparison["disponivel"], comparison["motivo"])
            self.assertEqual(comparison["periodo_anterior"], {
                "inicio": "2026-10-12", "fim": "2026-10-12",
            })
            deposits = comparison["metricas"]["depositos"]
            self.assertEqual(deposits["anterior_centavos"], 2_500_000)
            self.assertEqual(deposits["atual_centavos"], 2_510_000)
            self.assertEqual(deposits["delta_centavos"], 10_000)
            self.assertEqual(deposits["variacao_percentual"], "0.4")
            self.assertEqual(
                comparison["metricas"]["acordos"]["delta_centavos"], 0,
            )
            self.assertEqual(
                comparison["metricas"]["promessas"]["delta_centavos"], 0,
            )
            self.assertIn("posição da carteira não entra", comparison["nota"])
        finally:
            con.close()

    def test_percentual_nao_e_calculado_quando_base_anterior_e_zero(self):
        con = self.criar_banco_com_importacoes("2026-10-12", "2026-10-13")
        try:
            con.execute(
                "UPDATE fatos SET valor = 0 "
                "WHERE data = ? AND tipo = 'deposito'",
                ("2026-10-12",),
            )
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-13",
                leitura_centavos=False, demo=False,
            )
            deposits = result["comparacao"]["metricas"]["depositos"]
            self.assertTrue(result["comparacao"]["disponivel"])
            self.assertEqual(deposits["anterior_centavos"], 0)
            self.assertIsNone(deposits["variacao_percentual"])
        finally:
            con.close()

    def test_coberturas_com_mesma_quantidade_mas_datas_relativas_diferentes_bloqueiam_comparacao(self):
        con = self.criar_banco_com_importacoes("2026-10-11", "2026-10-14")
        try:
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-14",
                leitura_centavos=False, demo=False,
            )
            comparison = result["comparacao"]
            self.assertFalse(comparison["disponivel"])
            self.assertIn("mesmas posições relativas", comparison["motivo"])
            self.assertEqual(result["atualizacao"]["dias_com_importacao_registrada"], 1)
        finally:
            con.close()

    def test_demo_nao_inventa_historico_para_comparar(self):
        con = self.criar_banco_com_importacoes("2026-10-13")
        try:
            result = montar_dados_painel(
                con, inicio="2026-10-13", fim="2026-10-13",
                leitura_centavos=False, demo=True,
            )
            self.assertFalse(result["comparacao"]["disponivel"])
            self.assertIn("demonstração", result["comparacao"]["motivo"])
        finally:
            con.close()

    def test_interface_identifica_comparacao_indisponivel_e_nao_mostra_valores_antigos(self):
        self.assertIn('id="comparisonGrid"', HTML)
        self.assertIn('id="comparisonUnavailable"', HTML)
        self.assertIn('renderComparacao(d.comparacao)', HTML)
        self.assertIn('function renderComparacao(c)', HTML)
        self.assertIn("Variação percentual não calculada: base anterior zero ou negativa.", HTML)
        self.assertIn("Comparação indisponível", HTML)
        self.assertIn('"comparisonPeriod"].forEach', HTML)




if __name__ == "__main__":
    unittest.main(verbosity=2)
