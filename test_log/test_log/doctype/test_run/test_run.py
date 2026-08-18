# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count
from frappe.utils import now_datetime

from test_log.constants import RUN_COUNT_FIELDS, UNSETTLED_STATUSES


def count_by_status(test_run: str | None = None):
	"""Logs grouped by status. Built with the query builder because Frappe v16 rejects
	raw aggregate strings such as "count(name) as qty" in get_all()."""
	log = frappe.qb.DocType("Test Log")
	query = frappe.qb.from_(log).select(log.status, Count("*").as_("qty")).groupby(log.status)

	if test_run:
		query = query.where(log.test_run == test_run)

	return query.run(as_dict=True)


class TestRun(Document):
	def validate(self):
		self.validate_sign_off()

	def validate_sign_off(self):
		"""Signing off says the sheet is finished, so it has to actually be finished."""
		previous = self.get_doc_before_save()
		if self.status != "Signed Off" or (previous and previous.status == "Signed Off"):
			return

		if self.flags.ignore_unsettled_logs:
			self.stamp_sign_off()
			return

		unsettled = frappe.db.count("Test Log", {"test_run": self.name, "status": ["in", UNSETTLED_STATUSES]})
		if unsettled:
			frappe.throw(
				_(
					"{0} logs in this run are still open. Close them, or sign off with a note explaining why."
				).format(unsettled),
				title=_("Not ready to sign off"),
			)

		self.stamp_sign_off()

	def stamp_sign_off(self):
		self.signed_off_by = frappe.session.user
		self.signed_off_on = now_datetime()

	def update_summary(self, save=True):
		"""Recount child test logs by status and cache the totals on this run."""
		counts = count_by_status(self.name)
		fieldnames = set(RUN_COUNT_FIELDS.values())

		for fieldname in fieldnames:
			self.set(fieldname, 0)
		self.total_logs = 0

		for row in counts:
			self.total_logs += row.qty
			fieldname = RUN_COUNT_FIELDS.get(row.status)
			if fieldname:
				self.set(fieldname, self.get(fieldname) + row.qty)

		if save:
			values = {fieldname: self.get(fieldname) for fieldname in fieldnames}
			values["total_logs"] = self.total_logs
			self.db_set(values, update_modified=False)


def refresh_summary(test_run: str | None):
	"""Safe entry point used by Test Log hooks."""
	if not test_run:
		return

	if not frappe.db.exists("Test Run", test_run):
		return

	frappe.get_doc("Test Run", test_run).update_summary()


@frappe.whitelist()
def sign_off(test_run: str, notes: str | None = None, force: int = 0):
	"""Close a run off, recording who did it and why.

	`force` is for the run that ships with known open findings — allowed, but it has
	to be said out loud in the notes rather than passing silently.
	"""
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("write")

	if run.status == "Signed Off":
		frappe.throw(_("{0} was already signed off by {1}.").format(run.name, run.signed_off_by))

	force = int(force or 0)
	if force and not notes:
		frappe.throw(_("Say why the run is being signed off with logs still open."))

	run.status = "Signed Off"
	run.sign_off_notes = notes
	run.flags.ignore_unsettled_logs = bool(force)
	run.save()

	return {"name": run.name, "signed_off_by": run.signed_off_by, "signed_off_on": run.signed_off_on}
