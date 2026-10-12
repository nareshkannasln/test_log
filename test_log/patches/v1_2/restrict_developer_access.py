"""Remove old customized blanket permissions as well as standard DocPerm rows."""

import frappe


def execute():
	for doctype in ("Test Log", "Test Run"):
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": "Developer"})
		frappe.clear_cache(doctype=doctype)
