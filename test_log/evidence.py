"""Resolve evidence through File records, never through a caller-supplied path."""

import frappe
from frappe import _


def readable_file(file_url, log=None, *, throw=False):
	# Multiple File rows can reference the same blob. Accept any authorized row.
	for name in frappe.get_all("File", filters={"file_url": file_url}, pluck="name"):
		file = frappe.get_doc("File", name)
		attached = bool(
			log
			and not log.is_new()
			and file.attached_to_doctype == "Test Log"
			and file.attached_to_name == log.name
			and frappe.has_permission("Test Log", "read", doc=log)
		)
		if file.owner == frappe.session.user or attached or frappe.has_permission("File", "read", doc=file):
			return file
	if throw:
		frappe.throw(_("You cannot use this file as evidence."), frappe.PermissionError)
	return None
