# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Turns a test run — or a single log — into a Word document a developer can read.

Screenshots are embedded inline under the note they belong to; recordings and other
files are linked, since Word cannot play them. The result is attached to the record it
describes, so the sheet and its evidence travel together.
"""

import html
import re

import frappe
from frappe import _
from frappe.utils import format_datetime, get_url, strip_html_tags

from test_log.constants import IMAGE_EXTENSIONS
from test_log.docx import Document

REPORT_PREFIX = "Test Report"
CONSOLE_EXCERPT = 1500


@frappe.whitelist()
def build_run_report(test_run: str, attach: int = 1):
	"""Word report for a whole run: every log in it, with its evidence."""
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("read")

	logs = frappe.get_all(
		"Test Log", filters={"test_run": run.name}, pluck="name", order_by="creation asc"
	)

	document = Document()
	_run_cover(document, run, len(logs))

	for index, name in enumerate(logs):
		if index:
			document.page_break()
		_log_section(document, frappe.get_doc("Test Log", name))

	if not logs:
		document.paragraph(_("No test logs in this run yet."), italic=True, color="616E7C")

	return _deliver(document, run, f"{REPORT_PREFIX} - {run.name}.docx", int(attach))


@frappe.whitelist()
def build_log_report(test_log: str, attach: int = 1):
	"""Word report for one log — what a tester hands over for a single finding."""
	log = frappe.get_doc("Test Log", test_log)
	log.check_permission("read")

	document = Document()
	document.heading(log.subject, level=0)
	document.paragraph(
		_("{0} · logged by {1} on {2}").format(
			log.name, frappe.utils.get_fullname(log.tester), format_datetime(log.test_date or log.creation)
		),
		size=20,
		color="616E7C",
		space_after=200,
	)
	_log_section(document, log, with_heading=False)

	return _deliver(document, log, f"{REPORT_PREFIX} - {log.name}.docx", int(attach))


# ------------------------------------------------------------------ sections


def _run_cover(document: Document, run, log_count: int):
	document.heading(run.title, level=0)
	document.paragraph(
		_("Test run {0}").format(run.name), size=20, color="616E7C", space_after=200
	)

	document.label_value(_("Product"), run.product)
	document.label_value(_("Build / Version"), run.build_version)
	document.label_value(_("Lead Tester"), frappe.utils.get_fullname(run.tester))
	document.label_value(_("Run Date"), frappe.utils.formatdate(run.run_date))
	document.label_value(_("Status"), run.status)
	document.label_value(
		_("Logs"),
		_("{0} total · {1} open · {2} ongoing · {3} fixed · {4} completed").format(
			log_count, run.open_count, run.ongoing_count, run.fixed_count, run.completed_count
		),
	)

	if run.description:
		document.paragraph("")
		document.heading(_("What is being tested"), level=2)
		document.paragraph(_plain_text(run.description))

	document.rule()


def _log_section(document: Document, log, with_heading: bool = True):
	if with_heading:
		document.heading(f"{log.name} — {log.subject}", level=1)

	document.label_value(_("Status"), log.status)
	document.label_value(_("Severity"), log.severity)
	document.label_value(_("Test Type"), log.test_type)
	document.label_value(_("Module / Feature"), log.module_feature)
	document.label_value(_("Tester"), frappe.utils.get_fullname(log.tester))
	document.label_value(
		_("Assigned Developer"),
		frappe.utils.get_fullname(log.assigned_developer) if log.assigned_developer else None,
	)
	document.label_value(_("Target Fix Date"), frappe.utils.formatdate(log.target_date) if log.target_date else None)
	document.label_value(_("Environment"), log.environment)
	document.label_value(_("Build Tested"), log.build_version)
	document.label_value(_("Page"), log.page_route)
	document.label_value(_("Logged"), format_datetime(log.captured_at or log.test_date or log.creation))

	_block(document, _("Steps to Reproduce"), log.steps_to_reproduce)
	_block(document, _("Expected Result"), log.expected_result)
	_block(document, _("Actual Result"), log.actual_result)

	_evidence(document, log)

	if log.console_errors:
		document.heading(_("Console Errors"), level=2)
		document.paragraph(log.console_errors[:CONSOLE_EXCERPT], size=16, color="616E7C")

	if log.resolution or log.fixed_in_build:
		document.heading(_("Developer Update"), level=2)
		_block(document, None, log.resolution)
		document.label_value(_("Fixed in Build"), log.fixed_in_build)
		document.label_value(
			_("Resolved By"),
			frappe.utils.get_fullname(log.resolved_by) if log.resolved_by else None,
		)


def _block(document: Document, title, value):
	text = _plain_text(value)
	if not text:
		return

	if title:
		document.heading(title, level=2)
	document.paragraph(text)


def _evidence(document: Document, log):
	rows = [row for row in log.attachments if row.file_url or row.external_link]
	if not rows:
		return

	document.heading(_("Evidence"), level=2)

	files = _files_by_url([row.file_url for row in rows if row.file_url])

	for row in rows:
		caption = row.caption or row.attachment_type

		if row.external_link:
			document.link(f"{caption} — {row.external_link}", row.external_link)
			continue

		file = files.get(row.file_url)
		extension = (row.file_url.rsplit(".", 1)[-1] or "").lower()

		if file and extension in IMAGE_EXTENSIONS and extension != "svg":
			content = _file_content(file)
			if content and document.image(content, extension, caption=caption):
				continue

		# Recordings and everything else Word cannot render — link them instead.
		size = f" ({_readable_size(file.file_size)})" if file and file.file_size else ""
		document.link(f"{caption} — {row.file_url.rsplit('/', 1)[-1]}{size}", get_url(row.file_url))


# ------------------------------------------------------------------ plumbing


def _files_by_url(urls: list[str]) -> dict:
	if not urls:
		return {}

	rows = frappe.get_all(
		"File",
		filters={"file_url": ["in", list(set(urls))]},
		fields=["name", "file_url", "file_size", "is_private"],
	)

	return {row.file_url: row for row in rows}


def _file_content(file) -> bytes | None:
	"""Raw bytes of an attachment.

	Deliberately not File.get_content(): that tries a list of text encodings and
	windows-1252 accepts almost any byte, so a PNG comes back as a mangled string and
	the image lands in the document corrupt.
	"""
	try:
		path = frappe.get_doc("File", file.name).get_full_path()
		if path.startswith(("http://", "https://", "ftp://")):
			return None

		with open(path, "rb") as handle:
			return handle.read()
	except Exception:
		# A missing file on disk should not sink the whole report.
		return None


def _readable_size(size: int) -> str:
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024 or unit == "GB":
			return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
		size /= 1024

	return str(size)


def _plain_text(value) -> str:
	"""Text Editor fields hold HTML; the report wants readable lines."""
	if not value:
		return ""

	text = re.sub(r"<\s*br\s*/?>", "\n", str(value), flags=re.IGNORECASE)
	text = re.sub(r"</\s*(p|div|li|h\d)\s*>", "\n", text, flags=re.IGNORECASE)
	text = strip_html_tags(text)

	return html.unescape(text).strip()


def _deliver(document: Document, doc, file_name: str, attach: int):
	"""Write the document out as a File — attached to the record unless asked otherwise.

	Attaching replaces the previous report rather than piling up a new copy each time.
	"""
	target = (
		{"attached_to_doctype": doc.doctype, "attached_to_name": doc.name} if attach else {}
	)

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
			"content": document.render(),
			**target,
		}
	).insert(ignore_permissions=True)

	return {"file_name": file_name, "file_url": file.file_url, "size": file.file_size}


def refresh_run_report(test_run: str):
	"""Background refresh, used when the settings ask for an always-current report."""
	if not test_run or not frappe.db.exists("Test Run", test_run):
		return

	build_run_report(test_run, attach=1)
	frappe.db.commit()
