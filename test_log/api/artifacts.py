# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Shared plumbing for the things this app hands out as files.

The Word report and the Excel sheet are built by different writers but land the same
way — as a File, attached to the record they describe when there is one. That last
step, and the HTML-to-readable-text step both of them need, live here so the two
exporters cannot drift apart.
"""

import html
import re

import frappe
from frappe.utils import strip_html_tags


def plain_text(value) -> str:
	"""Text Editor fields hold HTML; an export wants readable lines."""
	if not value:
		return ""

	text = re.sub(r"<\s*br\s*/?>", "\n", str(value), flags=re.IGNORECASE)
	text = re.sub(r"</\s*(p|div|li|h\d)\s*>", "\n", text, flags=re.IGNORECASE)
	text = strip_html_tags(text)

	return html.unescape(text).strip()


def deliver(content: bytes, doc, file_name: str, attach: int) -> dict:
	"""Write the bytes out as a File — attached to the record unless asked otherwise.

	Attaching replaces the previous export rather than piling up a new copy each time.
	A selection of logs has no record to hang off, so it becomes a private file owned by
	whoever asked for it.
	"""
	attach = bool(attach and doc)
	target = {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name} if attach else {}

	if attach:
		for existing in frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"file_name": file_name,
			},
			pluck="name",
		):
			frappe.delete_doc("File", existing, ignore_permissions=True, force=True)

	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"is_private": 1,
			"content": content,
			**target,
		}
	).insert(ignore_permissions=True)

	return {"file_name": file_name, "file_url": file.file_url, "size": file.file_size}
