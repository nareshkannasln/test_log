# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Test logs as a spreadsheet — the issue descriptions, and little else.

The Word report is the handover document: every field, screenshots embedded. This is
the working list. One row per finding, so a team can sort it, filter it and tick things
off in a tool they already have open. Evidence is linked rather than embedded — a
spreadsheet is a poor place to keep a screen recording — and only when the settings
ask for it.
"""

from io import BytesIO

import frappe
import xlsxwriter
from frappe import _
from frappe.utils import get_url

from test_log.api.artifacts import deliver, plain_text
from test_log.test_log.doctype.test_log_settings.test_log_settings import get_settings

SHEET_PREFIX = "Test Logs"
SHEET_NAME = "Test Logs"

# Excel refuses a longer hyperlink target, and xlsxwriter raises rather than truncate.
MAX_URL_LENGTH = 2079

# Roughly a character count, which is how Excel measures column width.
WIDTH_ID = 18
WIDTH_SUBJECT = 42
WIDTH_DESCRIPTION = 80
WIDTH_EVIDENCE = 34


@frappe.whitelist()
def build_run_sheet(test_run: str, attach: int = 0):
	"""Excel sheet for a whole run — every log in it, oldest first."""
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("read")

	names = frappe.get_all(
		"Test Log", filters={"test_run": run.name}, pluck="name", order_by="creation asc"
	)

	if not names:
		frappe.throw(_("No test logs in this run yet."))

	content = _workbook(_rows(names))

	return deliver(content, run, f"{SHEET_PREFIX} - {run.name}.xlsx", int(attach)) | {
		"logs": len(names),
		"skipped": 0,
	}


@frappe.whitelist()
def build_selection_sheet(names: str | list, attach: int = 0):
	"""One sheet covering the logs ticked in the list view.

	Logs the user cannot read are left out rather than failing the export, which is how
	the Word report behaves too.
	"""
	if isinstance(names, str):
		names = frappe.parse_json(names)

	if not names:
		frappe.throw(_("Select at least one test log."))

	ordered = frappe.get_all(
		"Test Log", filters={"name": ["in", names]}, pluck="name", order_by="creation asc"
	)
	readable = [name for name in ordered if frappe.has_permission("Test Log", "read", doc=name)]

	if not readable:
		frappe.throw(_("You cannot read any of the selected test logs."), frappe.PermissionError)

	content = _workbook(_rows(readable))
	file_name = f"{SHEET_PREFIX} - {len(readable)} logs.xlsx"

	return deliver(content, None, file_name, int(attach)) | {
		"logs": len(readable),
		"skipped": len(names) - len(readable),
	}


# ------------------------------------------------------------------ the rows


def _rows(names: list[str]) -> list[dict]:
	"""One dict per log: what the sheet shows, already flattened."""
	# .get() rather than attribute access: the field is absent until the site migrates.
	with_evidence = bool(get_settings().get("include_evidence_links"))

	rows = []
	for name in names:
		log = frappe.get_doc("Test Log", name)
		rows.append(
			{
				"name": log.name,
				"subject": log.subject,
				"description": _description(log),
				"evidence": _evidence(log) if with_evidence else [],
			}
		)

	return rows


def _description(log) -> str:
	"""Steps, expected and actual as one readable block — the issue in the tester's words."""
	parts = []

	for label, value in (
		(_("Steps"), log.steps_to_reproduce),
		(_("Expected"), log.expected_result),
		(_("Actual"), log.actual_result),
	):
		text = plain_text(value)
		if text:
			parts.append(f"{label}: {text}")

	return "\n\n".join(parts)


def _evidence(log) -> list[tuple[str, str]]:
	"""Screenshots, recordings and external links as (label, url) pairs.

	File URLs are made absolute: the sheet leaves the site, so a relative path would
	dead-end on whoever opens it.
	"""
	items = []

	for row in log.attachments:
		if row.external_link:
			items.append((row.caption or row.attachment_type or _("Link"), row.external_link))
		elif row.file_url:
			label = row.caption or row.file_url.rsplit("/", 1)[-1]
			items.append((label, get_url(row.file_url)))

	return items


# ------------------------------------------------------------------ the sheet


def _workbook(rows: list[dict]) -> bytes:
	"""Render the rows into an .xlsx in memory.

	Evidence gets a column per item rather than several links crammed into one cell,
	because a cell holds exactly one hyperlink. The sheet is only as wide as the log
	with the most attachments needs, so nothing is silently dropped.
	"""
	evidence_columns = max((len(row["evidence"]) for row in rows), default=0)

	buffer = BytesIO()
	workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
	sheet = workbook.add_worksheet(SHEET_NAME)

	header_format = workbook.add_format(
		{"bold": True, "bg_color": "#F0F4F8", "border": 1, "border_color": "#D9E2EC", "valign": "vcenter"}
	)
	cell_format = workbook.add_format({"valign": "top"})
	wrapped_format = workbook.add_format({"valign": "top", "text_wrap": True})
	link_format = workbook.add_format({"valign": "top", "font_color": "#1264A3", "underline": 1})

	headers = [_("ID"), _("Subject"), _("Issue Description")]
	headers += [_("Evidence {0}").format(index + 1) for index in range(evidence_columns)]

	sheet.set_column(0, 0, WIDTH_ID)
	sheet.set_column(1, 1, WIDTH_SUBJECT)
	sheet.set_column(2, 2, WIDTH_DESCRIPTION)
	if evidence_columns:
		sheet.set_column(3, 2 + evidence_columns, WIDTH_EVIDENCE)

	sheet.write_row(0, 0, headers, header_format)
	sheet.freeze_panes(1, 0)
	sheet.autofilter(0, 0, len(rows), len(headers) - 1)

	for index, row in enumerate(rows, start=1):
		sheet.write_string(index, 0, _cell(row["name"]), cell_format)
		sheet.write_string(index, 1, _cell(row["subject"]), cell_format)
		sheet.write_string(index, 2, _cell(row["description"]), wrapped_format)

		for offset, (label, url) in enumerate(row["evidence"]):
			_write_link(sheet, index, 3 + offset, label, url, link_format, cell_format)

	workbook.close()

	return buffer.getvalue()


def _write_link(sheet, row: int, column: int, label: str, url: str, link_format, cell_format):
	"""A clickable link where Excel will take one, the bare text where it will not."""
	if url and len(url) <= MAX_URL_LENGTH and url.startswith(("http://", "https://")):
		sheet.write_url(row, column, url, link_format, string=_cell(label) or url)
		return

	sheet.write_string(row, column, _cell(f"{label} — {url}" if label else url), cell_format)


def _cell(value) -> str:
	"""Excel writes control characters back as literal _x0007_ escapes, so drop them."""
	text = "" if value is None else str(value)

	return "".join(char for char in text if char >= " " or char in "\t\n")
