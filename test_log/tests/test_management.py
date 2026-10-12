from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from test_log.management import add_cases, merge_duplicate, verify_build
from test_log.test_log.doctype.test_evidence_comment.test_evidence_comment import (
	add_evidence_comment,
	get_evidence_comments,
)
from test_log.test_log.doctype.test_run.test_run import sign_off
from test_log.tests.utils import make_log, make_product, make_run


class TestManagement(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.product = make_product()
		self.run = make_run(self.product)
		self.case = frappe.get_doc(
			{
				"doctype": "Test Case",
				"title": "Saving an invoice",
				"product": self.product.name,
				"steps": "Open invoice and save",
				"expected_result": "Invoice is saved",
			}
		).insert()

	def test_failed_case_creates_one_defect_with_snapshot(self):
		add_cases(self.run.name, [self.case.name])
		self.run.reload()
		self.run.cases[0].result = "Fail"
		self.run.cases[0].actual_result = "Server error"
		self.run.save()
		name = self.run.cases[0].test_log
		log = frappe.get_doc("Test Log", name)
		self.assertEqual(log.steps_to_reproduce, self.case.steps)
		self.assertEqual(log.actual_result, "Server error")
		self.assertEqual(self.run.coverage_percent, 100)
		self.run.save()
		self.assertEqual(frappe.db.count("Test Log", {"test_case": self.case.name}), 1)
		with self.assertRaises(frappe.ValidationError):
			sign_off(self.run.name)

	def test_case_snapshot_and_signed_off_results_are_immutable(self):
		add_cases(self.run.name, [self.case.name])
		self.run.reload()
		self.run.cases[0].result = "Pass"
		self.run.save()
		self.case.steps = "Changed library steps"
		self.case.save()
		self.run.cases[0].steps = "Forged snapshot"
		self.run.save()
		self.assertEqual(self.run.cases[0].steps, "Open invoice and save")
		sign_off(self.run.name)
		self.run.reload()
		self.run.cases[0].result = "Skipped"
		with self.assertRaises(frappe.ValidationError):
			self.run.save()

	def test_sla_default_preserves_explicit_date(self):
		self.product.sla_critical_days = 1
		self.product.save()
		log = make_log(self.product, severity="Critical")
		self.assertEqual(getdate(log.target_date), getdate(add_days(log.test_date, 1)))
		explicit = add_days(log.test_date, 10)
		log = make_log(self.product, severity="Critical", target_date=explicit)
		self.assertEqual(getdate(log.target_date), getdate(explicit))

	def test_verify_only_fixed_logs_in_chosen_product_build(self):
		log = make_log(self.product, self.run)
		log.status = "Ongoing"
		log.save()
		log.status, log.fixed_in_build = "Fixed", "v2"
		log.save()
		other = make_log(self.product, self.run, fixed_in_build="v3")
		result = verify_build(self.product.name, "v2")
		self.assertEqual(result["updated"], [log.name])
		self.assertEqual(frappe.db.get_value("Test Log", other.name, "status"), "Open")

	def test_merge_moves_evidence_comments_and_thread(self):
		original, duplicate = make_log(self.product), make_log(self.product)
		duplicate.append(
			"attachments",
			{
				"attachment_type": "External Link",
				"external_link": "https://example.com/evidence",
				"caption": "Capture",
			},
		)
		duplicate.save()
		comment = duplicate.add_comment("Comment", "More reproduction steps")
		thread = add_evidence_comment(
			duplicate.name, duplicate.attachments[0].name, "The red box", annotation="top left"
		)
		merge_duplicate(duplicate.name, original.name)
		original.reload()
		duplicate.reload()
		self.assertEqual(duplicate.status, "Won't Fix")
		self.assertFalse(duplicate.attachments)
		self.assertEqual(duplicate.merged_into, original.name)
		self.assertEqual(frappe.db.get_value("Comment", comment.name, "reference_name"), original.name)
		self.assertEqual(get_evidence_comments(original.name, original.attachments[0].name)[0].name, thread)
		merge_duplicate(duplicate.name, original.name)
		original.reload()
		self.assertEqual(len(original.attachments), 1)

	def test_evidence_reply_cannot_cross_screenshots(self):
		log = make_log(self.product)
		for i in range(2):
			log.append(
				"attachments",
				{"attachment_type": "External Link", "external_link": f"https://example.com/{i}"},
			)
		log.save()
		thread = add_evidence_comment(log.name, log.attachments[0].name, "First screenshot")
		with self.assertRaises(frappe.ValidationError):
			add_evidence_comment(log.name, log.attachments[1].name, "Wrong thread", reply_to=thread)
