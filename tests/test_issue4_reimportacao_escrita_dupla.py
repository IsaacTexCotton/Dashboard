"""Contrato de reimportação dupla com dados sintéticos.

Executado junto à suíte padrão para validar as regras de Issue #4.
"""
from decimal import Decimal
import unittest

from test_escrita_dupla import (
    DIA, argumentos, criar_banco, gravar_dia_duplo, preparar_fato_duplo,
    preparar_posicao_dupla, semear_fato_legado,
)

class TestReimportacaoDuplaEscrita(unittest.TestCase):(unittest.TestCase):
    def test_reimportacao_substitui_fatos_nas_duas_representacoes_e_preserva_snapshots(self):
        con = criar_banco()
        try:
            semear_fato_legado(con)
            con.execute(
                """INSERT INTO acordos_posicao
                (capturado_em, data, recebido_periodo, a_vencer, vencido,
                 recebido_periodo_centavos, a_vencer_centavos, vencido_centavos)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2026-10-14T11:00:00", DIA, 7.0, 8.0, 9.0, 700, 800, 900),
            )
            con.commit()

            # Primeira importação: grava ambos os lados para o dia.
            primeira = argumentos()
            self.assertEqual(gravar_dia_duplo(con, **primeira), 2)
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM acordos_posicao WHERE data=?", (DIA,)
                ).fetchone()[0],
                2,
            )

            # Segunda importação do mesmo dia com novos valores, mas mantendo
            # o mesmo capturado_em: fatos devem ser substituídos e a captura
            # existente nesse timestamp atualizada sem apagar capturas antigas.
            novos_fatos = [
                preparar_fato_duplo(
                    dia=DIA, usuario="ana", tipo="deposito", quantidade=2,
                    importado_em="reimportacao",
                    campos_monetarios={"valor": Decimal("13.45")},
                ),
                preparar_fato_duplo(
                    dia=DIA, usuario="bia", tipo="acordo", quantidade=3,
                    importado_em="reimportacao",
                    campos_monetarios={
                        "valor": Decimal("101.00"),
                        "pagos": Decimal("41.00"),
                        "pendente": Decimal("60.00"),
                    },
                ),
            ]
            segunda = argumentos(novos_fatos)
            segunda["quando"] = "2026-10-14T12:30:00"
            segunda["posicao_legada"], segunda["posicao_centavos"] = preparar_posicao_dupla(
                capturado_em="2026-10-14T12:00:00",
                dia=DIA,
                campos_monetarios={
                    "valorRecebidoPeriodo": Decimal("21.00"),
                    "valorAVencer": Decimal("31.00"),
                    "valorVencido": Decimal("41.00"),
                },
            )
            self.assertEqual(gravar_dia_duplo(con, **segunda), 2)

            fatos = con.execute(
                """SELECT usuario, tipo, valor, valor_pago, valor_aberto,
                          deposito_valor_centavos, acordo_valor_centavos,
                          acordo_pago_centavos, acordo_pendente_centavos
                   FROM fatos WHERE data=? ORDER BY usuario""",
                (DIA,),
            ).fetchall()
            self.assertEqual(
                fatos,
                [
                    ("ana", "deposito", 13.45, 0.0, 0.0, 1345, None, None, None),
                    ("bia", "acordo", 101.0, 41.0, 60.0, None, 10100, 4100, 6000),
                ],
            )
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM fatos WHERE data=?", (DIA,)
                ).fetchone()[0],
                2,
            )
            snapshots = con.execute(
                """SELECT capturado_em, recebido_periodo, a_vencer, vencido,
                          recebido_periodo_centavos, a_vencer_centavos,
                          vencido_centavos
                   FROM acordos_posicao ORDER BY capturado_em"""
            ).fetchall()
            self.assertEqual(
                snapshots,
                [
                    ("2026-10-14T11:00:00", 7.0, 8.0, 9.0, 700, 800, 900),
                    ("2026-10-14T12:00:00", 21.0, 31.0, 41.0, 2100, 3100, 4100),
                ],
            )
            self.assertEqual(con.execute("SELECT COUNT(*) FROM acordos_posicao").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 2)
        finally:
            con.close()
