# Copyright (c) 2026, Aerele and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from test_log.test_log.doctype.test_log.test_log import set_status
from test_log.test_log.doctype.test_run.test_run import sign_off
from test_log.tests.utils import make_log, make_product, make_run, settings_with


class TestTestRun(IntegrationTestCase):
	def setUp(self):
		self.product = make_product()
		self.run = make_run(self.product)

	# ------------------------------------------------------------------ counters

	def test_counts_roll_up_by_status(self):
		make_log(self.product, self.run)
		second = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			set_status(second.name, "Needs Info")

		self.run.reload()
		self.assertEqual(self.run.total_logs, 2)
		self.assertEqual(self.run.open_count, 1)
		self.assertEqual(self.run.needs_info_count, 1)

	def test_moving_a_log_recounts_both_runs(self):
		other = make_run(self.product, title="_Test Run 2")
		log = make_log(self.product, self.run)

		log.test_run = other.name
		log.save()

		self.run.reload()
		other.reload()
		self.assertEqual(self.run.total_logs, 0)
		self.assertEqual(other.total_logs, 1)

	# ------------------------------------------------------------------ sign-off

	def test_sign_off_is_blocked_while_logs_are_open(self):
		make_log(self.product, self.run)

		with self.assertRaises(frappe.ValidationError):
			sign_off(self.run.name)

	def test_sign_off_stamps_who_and_when(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			set_status(log.name, "Ongoing")
			set_status(log.name, "Fixed")
			set_status(log.name, "Completed")

		sign_off(self.run.name, notes="All clear")

		self.run.reload()
		self.assertEqual(self.run.status, "Signed Off")
		self.assertEqual(self.run.signed_off_by, frappe.session.user)
		self.assertIsNotNone(self.run.signed_off_on)

	def test_forced_sign_off_needs_a_reason(self):
		make_log(self.product, self.run)

		with self.assertRaises(frappe.ValidationError):
			sign_off(self.run.name, force=1)

		sign_off(self.run.name, notes="Shipping with two known issues", force=1)

		self.run.reload()
		self.assertEqual(self.run.status, "Signed Off")
		self.assertEqual(self.run.sign_off_notes, "Shipping with two known issues")

	def test_a_signed_off_run_takes_no_new_logs(self):
		sign_off(self.run.name, notes="Nothing to test")

		with settings_with(block_signed_off_runs=1):
			with self.assertRaises(frappe.ValidationError):
				make_log(self.product, self.run)

	def test_a_signed_off_run_can_still_be_reported_on(self):
		"""Logs already in the run stay editable — only new arrivals are refused."""
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			set_status(log.name, "Ongoing")

		sign_off(self.run.name, notes="Known issue", force=1)

		with settings_with(block_signed_off_runs=1):
			log.reload()
			log.actual_result = "still wrong after the release"
			log.save()

		self.assertEqual(frappe.db.get_value("Test Log", log.name, "test_run"), self.run.name)
