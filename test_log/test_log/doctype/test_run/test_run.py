# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Count

from test_log.constants import RUN_COUNT_FIELDS


def count_by_status(test_run: str | None = None):
	"""Logs grouped by status. Built with the query builder because Frappe v16 rejects
	raw aggregate strings such as "count(name) as qty" in get_all()."""
	log = frappe.qb.DocType("Test Log")
	query = frappe.qb.from_(log).select(log.status, Count("*").as_("qty")).groupby(log.status)

	if test_run:
		query = query.where(log.test_run == test_run)

	return query.run(as_dict=True)


class TestRun(Document):
	def update_summary(self, save=True):
		"""Recount child test logs by status and cache the totals on this run."""
		counts = count_by_status(self.name)

		for fieldname in set(RUN_COUNT_FIELDS.values()):
			self.set(fieldname, 0)
		self.total_logs = 0

		for row in counts:
			self.total_logs += row.qty
			fieldname = RUN_COUNT_FIELDS.get(row.status)
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
