import unittest
from pathlib import Path


class WebDemoPeriodValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / "web-demo" / "index.html").read_text(encoding="utf-8")

    def test_period_inputs_are_present_and_required(self):
        self.assertIn('id="start" value="2026-10-13" required', self.html)
        self.assertIn('id="end" value="2026-10-13" required', self.html)

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


if __name__ == "__main__":
    unittest.main()
