"""Testes isolados para o protótipo monetário; não alteram produção."""
import unittest
from decimal import Decimal

from precisao_monetaria import (
    INT64_MAX,
    INT64_MIN,
    ErroMonetario,
    grandeza_para_escala,
    inteiro_escalado_exato,
    loads_json_estrito,
    resultado_calculado_para_centavos,
    valor_final_centavos,
)


class TestJsonEstrito(unittest.TestCase):
    def test_preserva_inteiros_e_decimais_sem_float(self):
        dados = loads_json_estrito('{"qtd": 4, "valor": 1.230, "zero": 0}')
        self.assertEqual(dados["qtd"], 4)
        self.assertIsInstance(dados["qtd"], int)
        self.assertEqual(dados["valor"], Decimal("1.230"))
        self.assertIsInstance(dados["valor"], Decimal)
        self.assertEqual(dados["valor"].as_tuple().exponent, -3)

    def test_rejeita_notacao_cientifica_minuscula_e_maiuscula(self):
        for token in ("1e2", "1E2", "1e+2", "1E-2"):
            with self.subTest(token=token), self.assertRaises(ErroMonetario):
                loads_json_estrito('{"valor": ' + token + '}')

    def test_rejeita_nan_e_infinidades(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), self.assertRaises(ErroMonetario):
                loads_json_estrito('{"valor": ' + token + '}')

    def test_booleano_permanece_booleano_para_validacao_do_campo(self):
        dados = loads_json_estrito('{"valor": true}')
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(dados["valor"])

    def test_json_malformado_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            loads_json_estrito('{"valor": 01}')

    def test_raiz_deve_ser_texto(self):
        with self.assertRaises(ErroMonetario):
            loads_json_estrito(b'{"valor": 1.23}')


class TestValoresFinais(unittest.TestCase):
    def test_valor_com_duas_casas(self):
        self.assertEqual(valor_final_centavos(Decimal("1.23")), 123)

    def test_zeros_finais_excedentes_sao_exatos(self):
        self.assertEqual(valor_final_centavos(Decimal("1.230")), 123)
        self.assertEqual(valor_final_centavos(Decimal("1.23000")), 123)

    def test_fracao_subcentavo_e_rejeitada_sem_arredondamento(self):
        for valor in ("1.231", "1.239", "0.001", "-1.231"):
            with self.subTest(valor=valor), self.assertRaises(ErroMonetario):
                valor_final_centavos(Decimal(valor), negativos_permitidos=True)

    def test_inteiro_e_unidade_monetaria_nao_centavos(self):
        self.assertEqual(valor_final_centavos(1), 100)

    def test_sinal_negativo_depende_do_campo(self):
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(Decimal("-1.00"))
        self.assertEqual(
            valor_final_centavos(Decimal("-1.00"), negativos_permitidos=True), -100
        )

    def test_zero_negativo_e_normalizado_para_zero(self):
        self.assertEqual(valor_final_centavos(Decimal("-0.00")), 0)

    def test_float_intermediario_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(1.23)

    def test_texto_decimal_so_com_permissao_explicita(self):
        with self.assertRaises(ErroMonetario):
            valor_final_centavos("1.23")
        self.assertEqual(valor_final_centavos("1.230", permitir_texto=True), 123)

    def test_texto_com_expoente_e_rejeitado_mesmo_quando_habilitado(self):
        with self.assertRaises(ErroMonetario):
            valor_final_centavos("1e2", permitir_texto=True)

    def test_valor_nao_finito_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(Decimal("NaN"))

    def test_limites_assinados_de_64_bits(self):
        self.assertEqual(valor_final_centavos(Decimal("92233720368547758.07")), INT64_MAX)
        self.assertEqual(
            valor_final_centavos(
                Decimal("-92233720368547758.08"), negativos_permitidos=True
            ),
            INT64_MIN,
        )
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(Decimal("92233720368547758.08"))
        with self.assertRaises(ErroMonetario):
            valor_final_centavos(Decimal("-92233720368547758.09"), negativos_permitidos=True)


class TestGrandezasEscaladas(unittest.TestCase):
    def test_escala_e4_exata(self):
        self.assertEqual(grandeza_para_escala(Decimal("1.2345"), 4), 12345)
        self.assertEqual(grandeza_para_escala(Decimal("1.234500"), 4), 12345)

    def test_digito_que_excede_escala_contratada_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            grandeza_para_escala(Decimal("1.23456"), 4)

    def test_negativo_depende_da_grandeza(self):
        with self.assertRaises(ErroMonetario):
            grandeza_para_escala(Decimal("-1.25"), 4)
        self.assertEqual(
            grandeza_para_escala(Decimal("-1.25"), 4, negativos_permitidos=True),
            -12500,
        )

    def test_escala_invalida_e_rejeitada(self):
        for escala in (-1, 19, True, 2.0):
            with self.subTest(escala=escala), self.assertRaises(ErroMonetario):
                inteiro_escalado_exato(Decimal("1"), escala)


class TestHalfUpDeResultadoCalculado(unittest.TestCase):
    def test_half_up_positivo(self):
        self.assertEqual(resultado_calculado_para_centavos(Decimal("0.005")), 1)
        self.assertEqual(resultado_calculado_para_centavos(Decimal("0.004")), 0)
        self.assertEqual(resultado_calculado_para_centavos(Decimal("1.005")), 101)
        self.assertEqual(resultado_calculado_para_centavos(Decimal("2.675")), 268)

    def test_half_up_negativo_para_longe_de_zero_quando_permitido(self):
        self.assertEqual(
            resultado_calculado_para_centavos(
                Decimal("-0.005"), negativos_permitidos=True
            ),
            -1,
        )
        self.assertEqual(
            resultado_calculado_para_centavos(
                Decimal("-0.004"), negativos_permitidos=True
            ),
            0,
        )

    def test_negativo_nao_e_aceito_por_padrao(self):
        with self.assertRaises(ErroMonetario):
            resultado_calculado_para_centavos(Decimal("-0.005"))

    def test_float_intermediario_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            resultado_calculado_para_centavos(0.005)

    def test_resultado_fora_do_intervalo_e_rejeitado(self):
        with self.assertRaises(ErroMonetario):
            resultado_calculado_para_centavos(Decimal("1E100"))


class TestConversaoRealHistorico(unittest.TestCase):
    def test_float_legado_usa_repr_e_half_up(self):
        from precisao_monetaria import real_legado_para_centavos

        self.assertEqual(real_legado_para_centavos(1.005), 101)
        self.assertEqual(real_legado_para_centavos(2.675), 268)
        self.assertEqual(real_legado_para_centavos(0.1 + 0.2), 30)

    def test_null_historico_continua_null(self):
        from precisao_monetaria import real_legado_para_centavos

        self.assertIsNone(real_legado_para_centavos(None))

    def test_negativo_historico_depende_do_campo(self):
        from precisao_monetaria import real_legado_para_centavos

        with self.assertRaises(ErroMonetario):
            real_legado_para_centavos(-1.005)
        self.assertEqual(
            real_legado_para_centavos(-1.005, negativos_permitidos=True), -101
        )

    def test_negativo_nao_autorizado_nao_e_ocultado_por_arredondamento(self):
        from precisao_monetaria import real_legado_para_centavos

        with self.assertRaises(ErroMonetario):
            real_legado_para_centavos(-0.004)

    def test_nao_finitos_e_rejeitado(self):
        from precisao_monetaria import real_legado_para_centavos

        for valor in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(valor=valor), self.assertRaises(ErroMonetario):
                real_legado_para_centavos(valor)

    def test_bool_e_texto_sao_rejeitados(self):
        from precisao_monetaria import real_legado_para_centavos

        for valor in (True, "1.23"):
            with self.subTest(valor=valor), self.assertRaises(ErroMonetario):
                real_legado_para_centavos(valor)


if __name__ == "__main__":
    unittest.main()
