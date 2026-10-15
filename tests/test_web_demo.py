import re
import unittest
from pathlib import Path


class WebDemoPeriodValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / "web-demo" / "index.html").read_text(encoding="utf-8")

    def test_period_inputs_are_present_and_required(self):
        self.assertIn('id="start" value="2026-10-12" required', self.html)
        self.assertIn('id="end" value="2026-10-15" required', self.html)
        self.assertIn('id="reset"', self.html)

    def test_invalid_period_marks_fields_and_hides_previous_results(self):
        self.assertIn('const invalid=!start||!end||start>end;', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!start||start>end))', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!end||start>end))', self.html)
        self.assertIn('dashboard.hidden=true;', self.html)
        self.assertIn('sections.forEach(s=>s.hidden=true);', self.html)
        self.assertIn('Período inválido. Informe uma data inicial igual ou anterior à data final.', self.html)

    def test_valid_period_restores_dashboard_after_an_error(self):
        self.assertIn('dashboard.hidden=false;sections.forEach(s=>s.hidden=false);', self.html)
        self.assertIn('status.classList.toggle("error",invalid);', self.html)

    def test_demo_remains_offline_and_uses_only_synthetic_data(self):
        self.assertIn("const dailyData=[", self.html)
        self.assertIn("dados fictícios", self.html)
        self.assertIn("Sem conexão com CRM", self.html)
        self.assertIn("banco real", self.html)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("XMLHttpRequest", self.html)
        self.assertNotIn("WebSocket(", self.html)

    def test_synthetic_series_covers_eight_explicit_dates(self):
        dates = re.findall(r'\{date:"(2026-10-\d{2})",depositos:', self.html)
        self.assertEqual(len(dates), 8)
        self.assertEqual(dates[0], "2026-10-08")
        self.assertEqual(dates[-1], "2026-10-15")
        self.assertIn("Cenário sintético: 08–15 out 2026", self.html)
        self.assertIn("nenhum número abaixo representa resultado real", self.html)

    def test_cockpit_groups_flow_and_portfolio_position_separately(self):
        self.assertIn("Resumo do período", self.html)
        self.assertIn("Posição da carteira", self.html)
        self.assertIn("posição não é fluxo acumulado", self.html)
        self.assertIn('id="received"', self.html)
        self.assertIn('id="due"', self.html)
        self.assertIn('id="overdue"', self.html)

    def test_follow_up_indicators_are_descriptive_not_an_automatic_priority(self):
        self.assertIn("Focos para conferência", self.html)
        self.assertIn("não representa priorização automática", self.html)
        self.assertIn("Não somar entre si", self.html)
        self.assertIn('id="focusOverdue"', self.html)
        self.assertIn('id="focusPromise"', self.html)
        self.assertIn('id="focusAgreement"', self.html)

    def test_user_contact_metric_has_non_global_deduplication_caveat(self):
        self.assertIn("não são um total global deduplicado", self.html)
        self.assertIn("Únicos por usuário", self.html)
        self.assertIn("Contatos únicos* (última data)", self.html)

    def test_demo_discloses_missing_individual_case_data_and_synthetic_history(self):
        self.assertIn("não identifica clientes ou títulos prioritários", self.html)
        self.assertIn("identificador do título/acordo", self.html)
        self.assertIn("Comparação com período anterior", self.html)
        self.assertIn("A série de oito dias foi criada artificialmente", self.html)
        self.assertIn("não comprova tendência ou resultado real", self.html)

    def test_no_data_period_clears_snapshot_and_shows_empty_states(self):
        self.assertIn('setText("received",last?money(last.posicao.recebido):"—")', self.html)
        self.assertIn('setText("focusOverdue",last?money(last.posicao.vencido):"—")', self.html)
        self.assertIn('$("tableEmpty").style.display=has?"none":"block"', self.html)
        self.assertIn('$("barsEmpty").style.display=has?"none":"block"', self.html)
        self.assertIn('setText("status",days.length+" de "+daysBetween(start,end)+" datas com dados fictícios"', self.html)

    def test_missing_period_does_not_look_like_a_zero_result(self):
        self.assertIn('setText("depValue",has?money(totals.depValor):"—")', self.html)
        self.assertIn('setText("agrValue",has?money(totals.agrValor):"—")', self.html)
        self.assertIn('setText("promValue",has?money(totals.promValor):"—")', self.html)
        self.assertIn('setText("contactRecords",has?integer(totals.contactos):"—")', self.html)
        self.assertIn('"Sem dados no período"', self.html)
        self.assertIn('setText("agrPaid",has?money(totals.agrPago):"—")', self.html)

    def test_comparison_uses_equal_length_periods_and_requires_full_coverage(self):
        self.assertIn("function renderComparison(start,end,currentDays)", self.html)
        self.assertIn("const duration=daysBetween(start,end),previousEnd=addDays(start,-1),previousStart=addDays(previousEnd,-duration+1);", self.html)
        self.assertIn("currentDays.length!==duration||previousDays.length!==duration", self.html)
        self.assertIn("Comparação indisponível: o cenário sintético não contém todas as datas dos dois períodos.", self.html)
        self.assertIn('id="comparisonGrid"', self.html)
        self.assertIn('id="comparisonUnavailable"', self.html)

    def test_percent_change_is_not_computed_for_zero_or_negative_baseline(self):
        self.assertIn("function percentChange(current,previous){return previous<=0?null:", self.html)
        self.assertIn("Variação percentual indisponível: base anterior zero ou negativa.", self.html)
        self.assertIn('id="cmpDepDelta"', self.html)
        self.assertIn('id="cmpAgrDelta"', self.html)
        self.assertIn('id="cmpPromDelta"', self.html)

    def test_daily_trend_is_filtered_by_the_same_selected_dates(self):
        self.assertIn("function renderTrend(days)", self.html)
        self.assertIn("const days=selectDays(start,end)", self.html)
        self.assertIn("renderTrend(days);renderComparison(start,end,days);", self.html)
        self.assertIn('id="dailyTrend"', self.html)
        self.assertIn("Acordos", self.html)
        self.assertIn("Promessas", self.html)


if __name__ == "__main__":
    unittest.main()
