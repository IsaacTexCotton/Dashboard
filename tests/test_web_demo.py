import unittest
from pathlib import Path


class WebDemoPeriodValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / "web-demo" / "index.html").read_text(encoding="utf-8")

    def test_period_inputs_are_present_and_required(self):
        self.assertIn('id="start" value="2026-10-13" required', self.html)
        self.assertIn('id="end" value="2026-10-13" required', self.html)
        self.assertIn('id="reset"', self.html)

    def test_invalid_period_marks_fields_and_hides_previous_results(self):
        self.assertIn('const invalid=!start||!end||start>end;', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!start||start>end))', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!end||start>end))', self.html)
        self.assertIn('dashboard.hidden=true;', self.html)
        self.assertIn('sections.forEach(section=>section.hidden=true);', self.html)
        self.assertIn('Período inválido. Informe uma data inicial igual ou anterior à data final.', self.html)

    def test_valid_period_restores_dashboard_after_an_error(self):
        self.assertIn('dashboard.hidden=false;', self.html)
        self.assertIn('sections.forEach(section=>section.hidden=false);', self.html)
        self.assertIn('status.classList.toggle("error",invalid);', self.html)

    def test_demo_remains_offline_and_uses_synthetic_data(self):
        self.assertIn("const data={", self.html)
        self.assertIn("dados fictícios", self.html)
        self.assertIn("Sem conexão com CRM", self.html)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("XMLHttpRequest", self.html)

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
        self.assertIn("Contatos únicos não são deduplicação global", self.html)
        self.assertIn("Únicos por usuário", self.html)

    def test_demo_discloses_missing_individual_case_data_and_history(self):
        self.assertIn("não identifica clientes ou títulos prioritários", self.html)
        self.assertIn("identificador do título/acordo", self.html)
        self.assertIn("Comparação histórica indisponível", self.html)
        self.assertIn("A amostra cobre somente 13/10/2026", self.html)

    def test_no_data_period_clears_snapshot_and_shows_empty_states(self):
        self.assertIn('setText("received",has?money(data.posicao.recebido):"—")', self.html)
        self.assertIn('setText("focusOverdue",has?money(data.posicao.vencido):"—")', self.html)
        self.assertIn('document.getElementById("tableEmpty").style.display=has?"none":"block";', self.html)
        self.assertIn('document.getElementById("barsEmpty").style.display=has?"none":"block";', self.html)
        self.assertIn('setText("status",has?"1 dia com dados fictícios":"Nenhum dia com dados na amostra");', self.html)


if __name__ == "__main__":
    unittest.main()
