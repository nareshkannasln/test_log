# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url_to_form, now_datetime

from test_log.test_log.doctype.test_run.test_run import refresh_summary

RESOLVED_STATUSES = ("Fixed", "Completed", "Won't Fix")


class TestLog(Document):
	def validate(self):
		self.set_default_developer()
		self.stamp_resolution()

	def on_update(self):
		self.share_and_assign()
		self.notify_status_change()
		refresh_summary(self.test_run)

		previous = self.get_doc_before_save()
		if previous and previous.test_run and previous.test_run != self.test_run:
			refresh_summary(previous.test_run)

	def on_trash(self):
		refresh_summary(self.test_run)

	# ------------------------------------------------------------------ helpers

	def set_default_developer(self):
		if self.assigned_developer or not self.product:
			return

		self.assigned_developer = frappe.db.get_value("Test Product", self.product, "default_developer")

	def stamp_resolution(self):
		"""Record who closed the log and when, and clear it if the log is reopened."""
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else None

		if self.status == previous_status:
			return

		if self.status in RESOLVED_STATUSES:
			self.resolved_by = frappe.session.user
			self.resolved_on = now_datetime()
		else:
			self.resolved_by = None
			self.resolved_on = None

	def share_and_assign(self):
		"""Give the assigned developer access to the log and put it on their to-do list."""
		if not self.assigned_developer or self.assigned_developer == "Administrator":
			return

		previous = self.get_doc_before_save()
		if previous and previous.assigned_developer == self.assigned_developer:
			return

		frappe.share.add(
			self.doctype, self.name, self.assigned_developer, read=1, write=1, share=1, notify=0
		)

		already_assigned = frappe.db.exists(
			"ToDo",
			{
				"reference_type": self.doctype,
				"reference_name": self.name,
				"allocated_to": self.assigned_developer,
				"status": "Open",
			},
		)
		if already_assigned:
			return

		from frappe.desk.form.assign_to import add as assign

		assign(
			{
				"doctype": self.doctype,
				"name": self.name,
				"assign_to": [self.assigned_developer],
				"description": self.subject,
				"date": self.target_date,
				"priority": "High" if self.severity in ("High", "Critical") else "Medium",
			}
		)

	def notify_status_change(self):
		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		recipients = {self.tester, self.assigned_developer} - {None, "", frappe.session.user}
		if not recipients:
			return

		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		enqueue_create_notification(
			list(recipients),
			{
				"type": "Alert",
				"document_type": self.doctype,
				"document_name": self.name,
				"subject": _("{0} moved from {1} to {2}").format(self.name, previous.status, self.status),
				"from_user": frappe.session.user,
				"email_content": f"<p>{frappe.utils.escape_html(self.subject)}</p>"
				f'<p><a href="{get_url_to_form(self.doctype, self.name)}">{_("Open test log")}</a></p>',
			},
		)


# ---------------------------------------------------------------------- desk api


@frappe.whitelist()
def set_status(name: str, status: str, resolution: str | None = None):
	"""One-click status update used by the form and list view buttons."""
	doc = frappe.get_doc("Test Log", name)
	doc.check_permission("write")

	doc.status = status
	if resolution:
		doc.resolution = resolution

	doc.save()
	return doc.status


@frappe.whitelist()
def bulk_set_status(names: str | list, status: str):
	"""Update many logs at once from the list view."""
	if isinstance(names, str):
		names = frappe.parse_json(names)

	updated = []
	for name in names:
		try:
			set_status(name, status)
			updated.append(name)
		except frappe.PermissionError:
			frappe.clear_last_message()

	return updated
