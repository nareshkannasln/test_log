# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""The shareable sheet: one row per test log, exportable to Excel/CSV from the report view."""

import frappe
from frappe import _
from frappe.utils import get_url

from test_log.constants import STATUS_COLORS as STATUS_COLOURS


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters), None, get_chart(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Log"), "fieldtype": "Link", "options": "Test Log", "width": 130},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 260},
		{
			"fieldname": "product",
			"label": _("Product"),
			"fieldtype": "Link",
			"options": "Test Product",
			"width": 130,
		},
		{"fieldname": "module_feature", "label": _("Module / Feature"), "fieldtype": "Data", "width": 150},
		{"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "tester",
			"label": _("Tester"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{
			"fieldname": "assigned_developer",
			"label": _("Developer"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{"fieldname": "test_date", "label": _("Tested On"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "resolved_on", "label": _("Resolved On"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "evidence", "label": _("Evidence"), "fieldtype": "Int", "width": 90},
		{"fieldname": "evidence_links", "label": _("Evidence Links"), "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	conditions = {}
	for field in ("test_run", "product", "status", "severity", "tester", "assigned_developer"):
		if filters.get(field):
			conditions[field] = filters.get(field)

	if filters.get("from_date") and filters.get("to_date"):
		conditions["test_date"] = ["between", [filters.from_date, filters.to_date]]

	logs = frappe.get_list(
		"Test Log",
		filters=conditions,
		fields=[
			"name",
			"subject",
			"product",
			"module_feature",
			"severity",
			"status",
			"tester",
			"assigned_developer",
			"test_date",
			"resolved_on",
		],
		order_by="test_date desc",
	)

	attach_evidence(logs)
	return logs


def attach_evidence(logs):
	if not logs:
		return

	rows = frappe.get_all(
		"Test Log Attachment",
		filters={"parent": ["in", [log.name for log in logs]], "parenttype": "Test Log"},
		fields=["parent", "file_url", "external_link", "attachment_type"],
	)

	by_log = {}
	for row in rows:
		url = row.file_url or row.external_link
		if not url:
			continue
		by_log.setdefault(row.parent, []).append(get_url(url) if url.startswith("/") else url)

	for log in logs:
		links = by_log.get(log.name, [])
		log["evidence"] = len(links)
		log["evidence_links"] = ", ".join(links)


def get_chart(filters):
	from test_log.test_log.doctype.test_run.test_run import count_by_status

	rows = count_by_status(filters.get("test_run"))
	if not rows:
		return None

	return {
		"data": {
			"labels": [row.status for row in rows],
			"datasets": [{"name": _("Logs"), "values": [row.qty for row in rows]}],
		},
		"type": "donut",
		"colors": [STATUS_COLOURS.get(row.status, "gray") for row in rows],
	}
