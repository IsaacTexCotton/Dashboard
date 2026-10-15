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
        self.assertIn('dashboard.hidden=false;', self.html)
        self.assertIn('sections.forEach(s=>s.hidden=false);', self.html)
        self.assertIn('status.classList.toggle("error",invalid);', self.html)

    def test_demo_remains_offline_and_clearly_uses_synthetic_multi_day_data(self):
        self.assertIn("const dailyData=[", self.html)
        self.assertIn("valores integralmente sintéticos", self.html)
        self.assertIn("Sem conexão com CRM", self.html)
        self.assertIn('date:"2026-10-08"', self.html)
        self.assertIn('date:"2026-10-15"', self.html)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("XMLHttpRequest", self.html)

    def test_cockpit_groups_flow_and_portfolio_position_separately(self):
        self.assertIn("Resumo do período", self.html)
        self.assertIn("Posição da carteira", self.html)
        self.assertIn("posição não é fluxo acumulado", self.html)
        self.assertIn('id="received"', self.html)
        self.assertIn('id="due"', self.html)
        self.assertIn('id="overdue"', self.html)
        self.assertIn('last?money(last.posicao.vencido)', self.html)

    def test_follow_up_indicators_are_descriptive_not_an_automatic_priority(self):
        self.assertIn("Focos para conferência", self.html)
        self.assertIn("não representa priorização automática", self.html)
        self.assertIn("Não somar entre si", self.html)
        self.assertIn('id="focusOverdue"', self.html)
        self.assertIn('id="focusPromise"', self.html)
        self.assertIn('id="focusAgreement"', self.html)

    def test_unique_contacts_are_only_shown_for_last_date_and_not_globally_summed(self):
        self.assertIn("Únicos por usuário · última data", self.html)
        self.assertIn("Contatos únicos são exibidos somente na última data", self.html)
        self.assertIn('last?"A: "+integer(last.contatos.unicos[0])', self.html)
        self.assertIn("não são um total global deduplicado", self.html)

    def test_demo_discloses_missing_individual_case_data_and_synthetic_history(self):
        self.assertIn("não identifica clientes ou títulos prioritários", self.html)
        self.assertIn("identificador do título/acordo", self.html)
        self.assertIn("A comparação usa um cenário de simulação", self.html)
        self.assertIn("A série de oito dias foi criada artificialmente", self.html)
        self.assertIn("previsão", self.html)
        self.assertIn("aging por título", self.html)

    def test_comparison_requires_full_equal_length_period_coverage(self):
        self.assertIn('id="comparisonGrid"', self.html)
        self.assertIn('id="comparisonUnavailable"', self.html)
        self.assertIn('function renderComparison(start,end,currentDays)', self.html)
        self.assertIn('if(currentDays.length!==duration||previousDays.length!==duration)', self.html)
        self.assertIn('const previousEnd=addDays(start,-1),previousStart=addDays(previousEnd,-duration+1)', self.html)
        self.assertIn('Variação percentual indisponível: base anterior zero ou negativa.', self.html)
        self.assertIn("Comparação indisponível", self.html)
        self.assertIn('setText(m.details,"Atual "+money(now)+" · anterior "+money(before))', self.html)

    def test_daily_trend_uses_same_selected_period(self):
        self.assertIn('id="dailyTrend"', self.html)
        self.assertIn('function renderTrend(days)', self.html)
        self.assertIn("renderTrend(days);renderComparison(start,end,days);", self.html)
        self.assertIn("data-filter-section", self.html)
        self.assertIn("Três métricas de movimento", self.html)

    def test_no_data_period_does_not_look_like_zero_and_uses_latest_snapshot(self):
        self.assertIn('setText("depValue",has?money(totals.depValor):"—")', self.html)
        self.assertIn('setText("agrValue",has?money(totals.agrValor):"—")', self.html)
        self.assertIn('setText("promValue",has?money(totals.promValor):"—")', self.html)
        self.assertIn('setText("contactRecords",has?integer(totals.contactos):"—")', self.html)
        self.assertIn('"Sem dados no período"', self.html)
        self.assertIn('setText("agrPaid",has?money(totals.agrPago):"—")', self.html)
        self.assertIn('setText("received",last?money(last.posicao.recebido):"—")', self.html)
        self.assertIn('$("tableEmpty").style.display=has?"none":"block";', self.html)
        self.assertIn('$("barsEmpty").style.display=has?"none":"block";', self.html)


if __name__ == "__main__":
    unittest.main()
