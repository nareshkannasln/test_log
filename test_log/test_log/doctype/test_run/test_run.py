# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

STATUS_FIELD_MAP = {
	"Open": "open_count",
	"Reopened": "open_count",
	"Ongoing": "ongoing_count",
	"Fixed": "fixed_count",
	"Completed": "completed_count",
	"Won't Fix": "wont_fix_count",
}


class TestRun(Document):
	def update_summary(self, save=True):
		"""Recount child test logs by status and cache the totals on this run."""
		counts = frappe.get_all(
			"Test Log",
			filters={"test_run": self.name},
			fields=["status", "count(name) as qty"],
			group_by="status",
		)

		for fieldname in set(STATUS_FIELD_MAP.values()):
			self.set(fieldname, 0)
		self.total_logs = 0

		for row in counts:
			self.total_logs += row.qty
			fieldname = STATUS_FIELD_MAP.get(row.status)
			if fieldname:
				self.set(fieldname, self.get(fieldname) + row.qty)

		if save:
			self.db_set(
				{
					"total_logs": self.total_logs,
					"open_count": self.open_count,
					"ongoing_count": self.ongoing_count,
					"fixed_count": self.fixed_count,
					"completed_count": self.completed_count,
					"wont_fix_count": self.wont_fix_count,
				},
				update_modified=False,
			)


def refresh_summary(test_run: str | None):
	"""Safe entry point used by Test Log hooks."""
	if not test_run:
		return

	if not frappe.db.exists("Test Run", test_run):
		return

	frappe.get_doc("Test Run", test_run).update_summary()
