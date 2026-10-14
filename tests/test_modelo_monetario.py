"""Testes de mapeamento semântico para as métricas-alvo propostas."""
import unittest
from decimal import Decimal

from precisao_monetaria import ErroMonetario
from modelo_monetario import (
    FATO_METRICAS_CENTAVOS,
    POSICAO_METRICAS_CENTAVOS,
    mapear_fato_centavos,
    mapear_posicao_centavos,
)


class TestMapeamentoFatos(unittest.TestCase):
    def test_deposito_mapeia_apenas_sua_metrica_e_aceita_negativo(self):
        resultado = mapear_fato_centavos("deposito", {"valor": Decimal("-12.34")})
        self.assertEqual(resultado["deposito_valor_centavos"], -1234)
        self.assertEqual(
            [resultado[campo] for campo in FATO_METRICAS_CENTAVOS[1:]],
            [None] * 7,
        )

    def test_acordo_mapeia_colunas_semanticas_independentes(self):
        resultado = mapear_fato_centavos(
            "acordo",
            {
                "valor": Decimal("100.00"),
                "pagos": Decimal("40.00"),
                "pendente": Decimal("-2.00"),
            },
        )
        self.assertEqual(resultado["acordo_valor_centavos"], 10000)
        self.assertEqual(resultado["acordo_pago_centavos"], 4000)
        self.assertEqual(resultado["acordo_pendente_centavos"], -200)
        self.assertIsNone(resultado["deposito_valor_centavos"])
        self.assertIsNone(resultado["promessa_prometido_centavos"])

    def test_acordo_rejeita_negativo_em_valor_de_face_e_pago(self):
        for campos in (
            {"valor": Decimal("-1.00"), "pagos": Decimal("0"), "pendente": Decimal("1")},
            {"valor": Decimal("1.00"), "pagos": Decimal("-1.00"), "pendente": Decimal("2")},
        ):
            with self.subTest(campos=campos), self.assertRaises(ErroMonetario):
                mapear_fato_centavos("acordo", campos)

    def test_promessa_mapeia_quatro_metricas_e_permite_aberto_negativo(self):
        resultado = mapear_fato_centavos(
            "promessa",
            {
                "prometido": Decimal("100.00"),
                "cumprido": Decimal("110.00"),
                "emAberto": Decimal("-10.00"),
                "quebrado": Decimal("0.00"),
            },
        )
        self.assertEqual(resultado["promessa_prometido_centavos"], 10000)
        self.assertEqual(resultado["promessa_cumprido_centavos"], 11000)
        self.assertEqual(resultado["promessa_em_aberto_centavos"], -1000)
        self.assertEqual(resultado["promessa_quebrado_centavos"], 0)
        self.assertIsNone(resultado["acordo_valor_centavos"])

    def test_promessa_rejeita_negativo_em_metricas_nao_autorizadas(self):
        base = {
            "prometido": Decimal("10"),
            "cumprido": Decimal("5"),
            "emAberto": Decimal("4"),
            "quebrado": Decimal("1"),
        }
        for campo in ("prometido", "cumprido", "quebrado"):
            dados = dict(base)
            dados[campo] = Decimal("-1")
            with self.subTest(campo=campo), self.assertRaises(ErroMonetario):
                mapear_fato_centavos("promessa", dados)

    def test_contato_tem_todas_as_metricas_monetarias_null(self):
        resultado = mapear_fato_centavos("contato", {})
        self.assertEqual(tuple(resultado), FATO_METRICAS_CENTAVOS)
        self.assertEqual(set(resultado.values()), {None})

    def test_zero_e_diferente_de_null(self):
        resultado = mapear_fato_centavos("deposito", {"valor": Decimal("0.00")})
        self.assertEqual(resultado["deposito_valor_centavos"], 0)
        self.assertIsNone(resultado["acordo_valor_centavos"])

    def test_metrica_aplicavel_ausente_ou_null_rejeita_entrada(self):
        with self.assertRaises(ErroMonetario):
            mapear_fato_centavos("deposito", {})
        with self.assertRaises(ErroMonetario):
            mapear_fato_centavos("deposito", {"valor": None})

    def test_tipo_desconhecido_e_estrutura_invalida_sao_rejeitados(self):
        with self.assertRaises(ErroMonetario):
            mapear_fato_centavos("outro", {})
        with self.assertRaises(ErroMonetario):
            mapear_fato_centavos("deposito", [])


class TestMapeamentoPosicao(unittest.TestCase):
    def test_posicao_mapeia_tres_metricas_com_sinais_definidos(self):
        resultado = mapear_posicao_centavos(
            {
                "valorRecebidoPeriodo": Decimal("-10.00"),
                "valorAVencer": Decimal("2.50"),
                "valorVencido": Decimal("0.00"),
            }
        )
        self.assertEqual(tuple(resultado), POSICAO_METRICAS_CENTAVOS)
        self.assertEqual(resultado["recebido_periodo_centavos"], -1000)
        self.assertEqual(resultado["a_vencer_centavos"], 250)
        self.assertEqual(resultado["vencido_centavos"], 0)

    def test_posicao_rejeita_negativo_em_snapshot(self):
        with self.assertRaises(ErroMonetario):
            mapear_posicao_centavos(
                {
                    "valorRecebidoPeriodo": Decimal("0"),
                    "valorAVencer": Decimal("-0.01"),
                    "valorVencido": Decimal("0"),
                }
            )
        with self.assertRaises(ErroMonetario):
            mapear_posicao_centavos(
                {
                    "valorRecebidoPeriodo": Decimal("0"),
                    "valorAVencer": Decimal("0"),
                    "valorVencido": Decimal("-0.01"),
                }
            )

    def test_posicao_incompleta_rejeita(self):
        with self.assertRaises(ErroMonetario):
            mapear_posicao_centavos({"valorRecebidoPeriodo": Decimal("1")})


if __name__ == "__main__":
    unittest.main()
