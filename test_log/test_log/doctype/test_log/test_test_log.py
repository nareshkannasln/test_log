# Copyright (c) 2026, Aerele and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from test_log.test_log.doctype.test_log.test_log import (
	add_note,
	bulk_set_status,
	bulk_update_field,
	find_similar,
	set_status,
)
from test_log.tests.utils import make_log, make_product, make_run, settings_with


class TestTestLog(IntegrationTestCase):
	def setUp(self):
		self.product = make_product()
		self.run = make_run(self.product)

	# ------------------------------------------------------------------ status flow

	def test_new_log_cannot_start_resolved(self):
		with settings_with(enforce_status_flow=1):
			with self.assertRaises(frappe.ValidationError):
				make_log(self.product, self.run, status="Completed")

	def test_status_cannot_skip_a_step(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			log.status = "Completed"
			with self.assertRaises(frappe.ValidationError):
				log.save()

	def test_status_walks_the_flow(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			for status in ("Ongoing", "Fixed", "Completed", "Reopened"):
				log.status = status
				log.save()
				self.assertEqual(frappe.db.get_value("Test Log", log.name, "status"), status)

	def test_flow_can_be_switched_off(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=0):
			log.status = "Completed"
			log.save()

		self.assertEqual(frappe.db.get_value("Test Log", log.name, "status"), "Completed")

	def test_needs_info_and_back(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			log.status = "Needs Info"
			log.save()
			log.status = "Ongoing"
			log.save()

		self.assertEqual(log.status, "Ongoing")

	# ------------------------------------------------------------------ stamping

	def test_resolved_and_verified_are_stamped_separately(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			log.status = "Ongoing"
			log.save()
			log.status = "Fixed"
			log.save()

			self.assertEqual(log.resolved_by, frappe.session.user)
			self.assertIsNone(log.verified_by)

			log.status = "Completed"
			log.save()
			self.assertEqual(log.verified_by, frappe.session.user)
			self.assertIsNotNone(log.verified_on)

			log.status = "Reopened"
			log.save()
			self.assertIsNone(log.verified_by)
			self.assertIsNone(log.resolved_by)

	# ------------------------------------------------------------------ evidence

	def test_external_link_has_to_be_a_url(self):
		log = make_log(self.product, self.run)
		log.append("attachments", {"attachment_type": "External Link", "external_link": "drive.me/x"})

		with self.assertRaises(frappe.ValidationError):
			log.save()

	def test_evidence_row_needs_a_file_or_a_link(self):
		log = make_log(self.product, self.run)
		log.append("attachments", {"attachment_type": "Screenshot", "caption": "nothing here"})

		with self.assertRaises(frappe.ValidationError):
			log.save()

	# ------------------------------------------------------------------ duplicates

	def test_a_log_cannot_be_its_own_duplicate(self):
		log = make_log(self.product, self.run)
		log.duplicate_of = log.name

		with self.assertRaises(frappe.ValidationError):
			log.save()

	def test_duplicate_chains_collapse_to_the_original(self):
		original = make_log(self.product, self.run, subject="Original")
		second = make_log(self.product, self.run, subject="Second")
		third = make_log(self.product, self.run, subject="Third")

		second.duplicate_of = original.name
		second.save()

		third.duplicate_of = second.name
		third.save()

		self.assertEqual(third.duplicate_of, original.name)

	def test_find_similar_matches_on_subject_and_route(self):
		make_log(self.product, self.run, subject="Invoice total rounds wrongly", page_route="/app/invoice")
		make_log(self.product, self.run, subject="Something else entirely", page_route="/app/other")

		with settings_with(warn_on_duplicates=1):
			matches = find_similar(
				subject="Invoice total rounds badly", test_run=self.run.name, page_route="/app/invoice"
			)

		self.assertTrue(matches)
		self.assertEqual(matches[0].get("subject"), "Invoice total rounds wrongly")

	def test_find_similar_is_silent_when_switched_off(self):
		make_log(self.product, self.run, subject="Invoice total rounds wrongly")

		with settings_with(warn_on_duplicates=0):
			self.assertEqual(find_similar(subject="Invoice total rounds badly", test_run=self.run.name), [])

	# ------------------------------------------------------------------ bulk actions

	def test_bulk_set_status_reports_what_it_skipped(self):
		movable = make_log(self.product, self.run)
		stuck = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			set_status(stuck.name, "Ongoing")
			set_status(stuck.name, "Fixed")

			result = bulk_set_status([movable.name, stuck.name], "Ongoing")

		self.assertEqual(result["updated"], [movable.name])
		self.assertEqual(len(result["skipped"]), 1)
		self.assertEqual(result["skipped"][0]["name"], stuck.name)
		self.assertIn("Fixed", result["skipped"][0]["reason"])

	def test_bulk_update_field_refuses_fields_not_on_the_list(self):
		log = make_log(self.product, self.run)

		with self.assertRaises(frappe.ValidationError):
			bulk_update_field([log.name], "status", "Completed")

	def test_bulk_update_field_sets_the_value(self):
		first = make_log(self.product, self.run)
		second = make_log(self.product, self.run)

		result = bulk_update_field([first.name, second.name], "severity", "Critical")

		self.assertEqual(len(result["updated"]), 2)
		self.assertEqual(frappe.db.get_value("Test Log", first.name, "severity"), "Critical")

	# ------------------------------------------------------------------ conversation

	def test_a_status_note_lands_in_the_timeline(self):
		log = make_log(self.product, self.run)

		with settings_with(enforce_status_flow=1):
			set_status(log.name, "Needs Info", note="Which build was this on?")

		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Test Log", "reference_name": log.name, "comment_type": "Comment"},
			pluck="content",
		)
		self.assertTrue(any("Which build" in (c or "") for c in comments))

	def test_add_note_ignores_an_empty_note(self):
		log = make_log(self.product, self.run)
		self.assertIsNone(add_note(log.name, "   "))
