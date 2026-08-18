# Copyright (c) 2026, Aerele and contributors
# See license.txt

"""The capture endpoint — mostly about the same entry arriving more than once."""

import frappe
from frappe.tests import IntegrationTestCase

from test_log.api.capture import log_entry
from test_log.tests.utils import make_log, make_product, make_run, settings_with


class TestCapture(IntegrationTestCase):
	def setUp(self):
		self.product = make_product()
		self.run = make_run(self.product)

	def entry(self, **kwargs) -> dict:
		values = {
			"client_id": frappe.generate_hash(length=12),
			"description": "The save button does nothing",
			"test_run": self.run.name,
			"product": self.product.name,
			"page_route": "/app/test-log/new",
		}
		values.update(kwargs)
		return values

	def test_an_entry_becomes_a_test_log(self):
		row = log_entry(self.entry())

		log = frappe.get_doc("Test Log", row["name"])
		self.assertEqual(log.subject, "The save button does nothing")
		self.assertEqual(log.logged_via, "Tester Widget")
		self.assertEqual(log.test_run, self.run.name)

	def test_the_same_client_id_never_makes_two_logs(self):
		entry = self.entry()

		first = log_entry(entry)
		second = log_entry(entry)

		self.assertEqual(first["name"], second["name"])
		self.assertTrue(second["duplicate"])

	def test_steps_keep_their_line_breaks(self):
		row = log_entry(self.entry(steps_to_reproduce="Open the form\nHit save"))

		steps = frappe.db.get_value("Test Log", row["name"], "steps_to_reproduce")
		self.assertIn("<br>", steps)

	def test_a_long_subject_is_trimmed_not_rejected(self):
		row = log_entry(self.entry(subject="x" * 400))

		self.assertEqual(len(frappe.db.get_value("Test Log", row["name"], "subject")), 140)

	def test_the_entry_carries_a_duplicate_hint(self):
		make_log(self.product, self.run, subject="The save button does nothing")

		with settings_with(warn_on_duplicates=1):
			row = log_entry(self.entry())

		self.assertTrue(row.get("similar"))

	def test_an_entry_cannot_be_filed_as_completed(self):
		with settings_with(enforce_status_flow=1):
			with self.assertRaises(frappe.ValidationError):
				log_entry(self.entry(status="Completed"))
