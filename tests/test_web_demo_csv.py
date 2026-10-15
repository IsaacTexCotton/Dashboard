import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebDemoCsvExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web-demo" / "index.html").read_text(encoding="utf-8")
        match = re.search(
            r'<script id="demo-history" type="application/json">\s*(.*?)\s*</script>',
            cls.html,
            re.DOTALL,
        )
        if not match:
            raise AssertionError("Histórico fictício não encontrado.")
        cls.history = json.loads(match.group(1))
        cls.dates = [item["data"]["inicio"] for item in cls.history]
        start = cls.html.index("function csvCell(value){")
        end = cls.html.index("function apply(event){", start)
        cls.export_source = cls.html[start:end]

    def test_export_button_is_present_and_uses_current_filter(self):
        self.assertIn('id="exportCsv"', self.html)
        self.assertIn("Exportar período para CSV", self.html)
        self.assertIn('$("exportCsv").addEventListener("click",downloadCsv)', self.html)
        self.assertIn("const days=selectDays(start,end),csv=buildCsv(days);", self.export_source)
        self.assertIn('link.download="caixa_futuro_"+start+"_a_"+end+".csv"', self.export_source)

    def test_csv_has_excel_bom_semicolon_and_crlf(self):
        self.assertIn('return "\\uFEFF"+lines.join("\\r\\n")+"\\r\\n";', self.export_source)
        self.assertIn('.join(";")', self.export_source)
        self.assertIn('type:"text/csv;charset=utf-8;"', self.export_source)

    def test_csv_escapes_quotes_delimiters_and_newlines(self):
        self.assertIn('/[;"\\r\\n]/.test(text)', self.export_source)
        self.assertIn('text.replace(/"/g,', self.export_source)

    def test_financial_values_use_two_decimal_places_and_comma_decimal(self):
        self.assertIn("number.toFixed(2).replace(\".\",\",\")", self.export_source)
        self.assertIn('["Valor dos depósitos (R$)",d=>csvMoney(d.depositos.valor)]', self.export_source)
        self.assertIn('["Valor pago dos acordos (R$)",d=>csvMoney(d.acordos.pagos)]', self.export_source)
        self.assertIn('["Valor quebrado das promessas (R$)",d=>csvMoney(d.promessas.quebrado)]', self.export_source)

    def test_export_fields_include_all_flow_metrics_and_explicit_snapshot_captures(self):
        for label in (
            "Data de referência",
            "Quantidade de depósitos",
            "Valor acordado (R$)",
            "Valor pendente dos acordos (R$)",
            "Quantidade de promessas",
            "Valor em aberto das promessas (R$)",
            "Registros de contato",
            "Contatos únicos por usuário (detalhe; não somar)",
            "Captura da carteira — valor recebido na referência (R$)",
            "Captura da carteira — saldo a vencer na referência (R$)",
            "Captura da carteira — saldo vencido na referência (R$)",
        ):
            self.assertIn(label, self.export_source)

    def test_contacts_are_kept_per_user_not_summed_as_global_unique_people(self):
        self.assertIn("JSON.stringify(d.contatos.unicos.map(row=>({usuario:row.usuario,nome:row.nome,quantidade:row.quantidade})))", self.export_source)
        self.assertNotIn("contatosUnicosTotal", self.export_source)

    def test_missing_values_are_blank_not_fabricated_zeros(self):
        self.assertIn("if(value===null||value===undefined)return \"\";", self.export_source)
        self.assertIn('if(value===null||value===undefined||value==="")return "";', self.export_source)
        self.assertIn("if(!Array.isArray(days)||days.length===0)return null;", self.export_source)

    def test_empty_and_invalid_periods_prevent_download(self):
        self.assertIn('const days=selectDays(start,end),csv=buildCsv(days);', self.export_source)
        self.assertIn("if(!csv){", self.export_source)
        self.assertIn("exportação cancelada", self.export_source)
        self.assertIn('start>end){', self.export_source)
        self.assertIn('$("exportCsv").disabled=true', self.export_source)
        self.assertIn('$("exportCsv").disabled=!has;', self.html)

    def test_date_filter_excludes_out_of_range_days_and_keeps_available_dates_only(self):
        self.assertIn("function selectDays(start,end){return dailyData.filter(row=>row.date>=start&&row.date<=end)}", self.html)
        selected = [day for day in self.dates if "2026-10-05" <= day <= "2026-10-07"]
        self.assertEqual(selected, ["2026-10-05", "2026-10-06", "2026-10-07"])
        self.assertEqual([day for day in self.dates if "2026-09-01" <= day <= "2026-09-03"], [])
        self.assertEqual(self.dates[0], "2026-10-01")
        self.assertEqual(self.dates[-1], "2026-10-15")

    def test_export_is_client_side_and_keeps_demo_offline(self):
        self.assertIn("new Blob([csv]", self.export_source)
        self.assertIn("URL.createObjectURL(blob)", self.export_source)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("XMLHttpRequest", self.html)
        self.assertIn("dados fictícios", self.html)
        self.assertIn("Sem conexão com CRM", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
