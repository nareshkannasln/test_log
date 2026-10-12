from io import BytesIO
from shutil import which
from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate
from pypdf import PdfReader, PdfWriter

from test_log.analytics import (
	compare_builds,
	install_saved_filters,
	quality_rows,
	sign_off_certificate,
	sla_at_risk,
	sla_breached,
)
from test_log.management import add_cases
from test_log.test_log.doctype.test_run.test_run import sign_off
from test_log.tests.utils import make_log, make_product, make_run


class TestAnalytics(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.product = make_product("_Test Metrics " + frappe.generate_hash(length=8))
		self.run = make_run(self.product)

	def test_sla_counts_and_metrics_are_permission_scoped(self):
		log = make_log(self.product, target_date=add_days(nowdate(), -1))
		with patch("test_log.analytics.frappe.get_list", return_value=[log.name]) as query:
			self.assertEqual(sla_breached()["value"], 1)
			self.assertEqual(query.call_args.kwargs["filters"]["target_date"][0], "<")
			self.assertEqual(sla_at_risk()["value"], 1)
			self.assertEqual(query.call_args.kwargs["filters"]["target_date"][0], "between")
		with patch("test_log.analytics.frappe.get_list", return_value=[]):
			self.assertEqual(quality_rows("open"), [])

	def test_fix_time_and_reopen_rate(self):
		log = make_log(self.product)
		frappe.db.set_value(
			"Test Log", log.name, {"first_resolved_on": add_days(log.creation, 2), "reopen_count": 1}
		)
		self.assertEqual(quality_rows("fix_time", self.product.name)[0]["value"], 2)
		self.assertEqual(quality_rows("reopen", self.product.name)[0]["value"], 100)

	def test_build_comparison_includes_fixed_open_and_case_regression(self):
		fixed = make_log(self.product, build_version="v1")
		fixed.status = "Ongoing"
		fixed.save()
		fixed.status, fixed.fixed_in_build = "Fixed", "v2"
		fixed.save()
		still_open = make_log(self.product, build_version="v1")
		case = frappe.get_doc(
			{
				"doctype": "Test Case",
				"title": "Regression",
				"product": self.product.name,
				"steps": "Save",
				"expected_result": "Saved",
			}
		).insert()
		for version, result in (("v1", "Pass"), ("v2", "Fail")):
			run = make_run(self.product, build_version=version)
			add_cases(run.name, [case.name])
			run.reload()
			run.cases[0].result = result
			run.cases[0].actual_result = "Observed result"
			run.save()
		rows = compare_builds(self.product.name, "v1", "v2")
		self.assertTrue(any(r.get("test_log") == fixed.name and r["category"] == "Fixed" for r in rows))
		self.assertTrue(
			any(r.get("test_log") == still_open.name and r["category"] == "Still Open" for r in rows)
		)
		self.assertTrue(any(r.get("test_case") == case.name and r["category"] == "Regressed" for r in rows))

	def test_certificate_requires_signoff_and_escapes_notes(self):
		with self.assertRaises(frappe.ValidationError):
			sign_off_certificate(self.run.name)
		sign_off(self.run.name, notes="Release approved")
		# Exercise the template against legacy content that bypassed normal sanitization.
		frappe.db.set_value("Test Run", self.run.name, "sign_off_notes", "<script>alert(1)</script>")
		buffer = BytesIO()
		writer = PdfWriter()
		writer.add_blank_page(width=595, height=842)
		writer.write(buffer)
		with patch("frappe.utils.pdf.get_pdf", return_value=buffer.getvalue()) as render:
			result = sign_off_certificate(self.run.name)
			self.assertTrue(result["file_url"].endswith(".pdf"))
			self.assertNotIn("<script>", render.call_args.args[0])
			self.assertIn("&lt;script&gt;", render.call_args.args[0])

	def test_saved_filters_are_per_user_and_idempotent(self):
		first = install_saved_filters()
		second = install_saved_filters()
		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count(
				"List Filter",
				{"reference_doctype": "Test Log", "for_user": "Administrator", "filter_name": ["in", first]},
			),
			4,
		)

	def test_certificate_checks_each_log_before_rendering(self):
		make_log(self.product, self.run)
		sign_off(self.run.name, notes="Known issue", force=1)
		original = frappe.has_permission

		def check(doctype, *args, **kwargs):
			if doctype == "Test Log":
				raise frappe.PermissionError
			return original(doctype, *args, **kwargs)

		with patch("frappe.has_permission", side_effect=check), patch("frappe.utils.pdf.get_pdf") as pdf:
			with self.assertRaises(frappe.PermissionError):
				sign_off_certificate(self.run.name)
			pdf.assert_not_called()

	@skipUnless(which("wkhtmltopdf"), "Site PDF renderer is not installed")
	def test_certificate_renders_a_real_pdf(self):
		sign_off(self.run.name, notes="Release approved")
		result = sign_off_certificate(self.run.name)
		file = frappe.get_doc("File", {"file_url": result["file_url"]})
		reader = PdfReader(file.get_full_path())
		text = " ".join(page.extract_text() for page in reader.pages)
		self.assertIn(self.run.name, text)
