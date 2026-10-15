import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def json_schema(value):
    """Preserva chaves, tipos escalares e estrutura/quantidade das listas."""
    if isinstance(value, dict):
        return {key: json_schema(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_schema(item) for item in value]
    return type(value).__name__


class WebDemoPeriodValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web-demo" / "index.html").read_text(encoding="utf-8")
        cls.source = json.loads((ROOT / "amostra_resposta.json").read_text(encoding="utf-8"))
        cls.synthetic = json.loads((ROOT / "amostra_resposta_ficticia.json").read_text(encoding="utf-8"))
        match = re.search(
            r'<script id="demo-payload" type="application/json">\s*(.*?)\s*</script>',
            cls.html,
            re.DOTALL,
        )
        if not match:
            raise AssertionError("O payload sintético precisa estar embutido no HTML.")
        cls.embedded = json.loads(match.group(1))

    def test_period_inputs_are_present_and_default_to_payload_date(self):
        self.assertIn('id="start" value="2026-10-15" required', self.html)
        self.assertIn('id="end" value="2026-10-15" required', self.html)
        self.assertIn('id="reset"', self.html)
        self.assertIn("const defaultStart=sourceData.inicio,defaultEnd=sourceData.fim;", self.html)

    def test_invalid_period_marks_fields_and_hides_previous_results(self):
        self.assertIn('const invalid=!start||!end||start>end;', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!start||start>end))', self.html)
        self.assertIn('setAttribute("aria-invalid",String(!end||start>end))', self.html)
        self.assertIn("dashboard.hidden=true;", self.html)
        self.assertIn("sections.forEach(s=>s.hidden=true);", self.html)
        self.assertIn("Período inválido. Informe uma data inicial igual ou anterior à data final.", self.html)

    def test_valid_period_restores_dashboard_after_an_error(self):
        self.assertIn("dashboard.hidden=false;sections.forEach(s=>s.hidden=false);", self.html)
        self.assertIn('status.classList.toggle("error",invalid);', self.html)

    def test_demo_remains_offline_and_uses_only_synthetic_json(self):
        self.assertIn('id="demo-payload" type="application/json"', self.html)
        self.assertIn('JSON.parse(document.getElementById("demo-payload").textContent)', self.html)
        self.assertIn("dados fictícios", self.html)
        self.assertIn("Sem conexão com CRM", self.html)
        self.assertIn("banco real", self.html)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("XMLHttpRequest", self.html)
        self.assertNotIn("WebSocket(", self.html)

    def test_synthetic_payload_keeps_identical_schema_and_array_structure(self):
        self.assertEqual(json_schema(self.synthetic), json_schema(self.source))
        self.assertNotEqual(self.synthetic, self.source)
        self.assertEqual(self.embedded, self.synthetic)
        self.assertEqual(set(self.synthetic["data"]["depositos"]), set(self.source["data"]["depositos"]))
        self.assertEqual(
            len(self.synthetic["data"]["depositos"]["porUsuario"]),
            len(self.source["data"]["depositos"]["porUsuario"]),
        )

    def test_demo_changes_values_without_inventing_a_historical_series(self):
        data = self.synthetic["data"]
        self.assertEqual(data["inicio"], data["fim"])
        self.assertEqual(data["depositos"]["valorTotal"], 27800.0)
        self.assertEqual(data["acordos"]["valorTotal"], 26300.0)
        self.assertEqual(data["promessas"]["prometidoTotal"], 46700.0)
        self.assertEqual(data["contatos"]["registrosTotaisTotal"], 148)
        self.assertIn("const dailyData=[{", self.html)
        self.assertIn("date:sourceData.inicio", self.html)
        self.assertNotIn('date:"2026-10-08"', self.html)
        self.assertNotIn("A série de oito dias foi criada artificialmente", self.html)
        self.assertIn("não foram adicionados campos, usuários ou datas históricas", self.html)
        self.assertIn("Payload fictício de 1 data", self.html)

    def test_cockpit_groups_flow_and_portfolio_snapshot_separately(self):
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

    def test_user_contact_metric_is_directly_read_from_payload(self):
        self.assertIn(
            "sourceData.contatos.porUsuario.map(row=>({usuario:row.usuario,nome:row.nome,quantidade:row.contatosUnicos}))",
            self.html,
        )
        self.assertIn(
            "sourceData.contatos.porUsuario.forEach(row=>{const u=get(row);u.unicos=row.contatosUnicos;});",
            self.html,
        )
        self.assertIn("não são um total global deduplicado", self.html)
        self.assertNotIn("function split(total", self.html)

    def test_demo_discloses_missing_individual_case_data_and_absent_history(self):
        self.assertIn("não identifica clientes ou títulos prioritários", self.html)
        self.assertIn("identificador do título/acordo", self.html)
        self.assertIn("Comparação com período anterior", self.html)
        self.assertIn("o JSON de referência contém uma única data", self.html)
        self.assertIn("não há série histórica nesta amostra", self.html)

    def test_no_data_period_clears_snapshot_and_shows_empty_states(self):
        self.assertIn('setText("received",last?money(last.posicao.recebido):"—")', self.html)
        self.assertIn('setText("focusOverdue",last?money(last.posicao.vencido):"—")', self.html)
        self.assertIn('$("tableEmpty").style.display=has?"none":"block"', self.html)
        self.assertIn('$("barsEmpty").style.display=has?"none":"block"', self.html)
        self.assertIn("datas com dados fictícios", self.html)

    def test_missing_period_does_not_look_like_a_zero_result(self):
        self.assertIn('setText("depValue",has?money(totals.depValor):"—")', self.html)
        self.assertIn('setText("agrValue",has?money(totals.agrValor):"—")', self.html)
        self.assertIn('setText("promValue",has?money(totals.promValor):"—")', self.html)
        self.assertIn('setText("contactRecords",has?integer(totals.contactos):"—")', self.html)
        self.assertIn('"Sem dados no período"', self.html)
        self.assertIn('setText("agrPaid",has?money(totals.agrPago):"—")', self.html)

    def test_comparison_is_unavailable_without_an_explicit_previous_period(self):
        self.assertIn("function renderComparison(start,end,currentDays)", self.html)
        self.assertIn("currentDays.length!==duration||previousDays.length!==duration", self.html)
        self.assertIn(
            "Comparação indisponível: o JSON de referência contém uma única data, sem período anterior para comparar.",
            self.html,
        )
        self.assertIn('id="comparisonGrid"', self.html)
        self.assertIn('id="comparisonUnavailable"', self.html)
        self.assertIn("O payload não inclui série histórica", self.html)

    def test_daily_chart_uses_the_selected_sample_date_without_claiming_a_trend(self):
        self.assertIn("function renderTrend(days)", self.html)
        self.assertIn("const days=selectDays(start,end)", self.html)
        self.assertIn("renderTrend(days);renderComparison(start,end,days);", self.html)
        self.assertIn('id="dailyTrend"', self.html)
        self.assertIn("Movimentos da data informada", self.html)
        self.assertNotIn('const dailyData=[\n {date:', self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
