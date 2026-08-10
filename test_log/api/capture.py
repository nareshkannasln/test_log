# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Endpoints behind the tester capture widget.

The widget writes every entry to the browser's own database first and posts it here
afterwards, which means the same entry can arrive twice — once from an optimistic
send and once from the offline queue draining. `client_id` is what keeps that from
turning into duplicate test logs.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_url_to_form, now_datetime

from test_log.constants import attachment_type_for
from test_log.test_log.doctype.test_log_settings.test_log_settings import (
	get_settings,
	widget_config,
)

SUBJECT_LENGTH = 140
FEED_LIMIT = 25


@frappe.whitelist()
def get_config():
	"""Bootstrap payload for the widget on pages that carry no boot info."""
	return widget_config()


@frappe.whitelist()
def log_entry(entry: str | dict):
	"""Turn one captured entry into a Test Log.

	Returns the same shape whether the log was just created or had already been
	written by an earlier attempt, so the widget can settle its queue either way.
	"""
	entry = _as_dict(entry)
	frappe.has_permission("Test Log", "create", throw=True)

	client_id = cstr(entry.get("client_id")).strip() or None
	if client_id:
		existing = frappe.db.get_value("Test Log", {"client_id": client_id}, "name")
		if existing:
			return _feed_row(existing, duplicate=True)

	doc = frappe.new_doc("Test Log")
	doc.update(_log_values(entry))
	doc.client_id = client_id
	doc.logged_via = "Tester Widget"

	for row in _attachment_rows(entry):
		doc.append("attachments", row)

	try:
		doc.insert()
	except frappe.UniqueValidationError:
		# Two flushes raced. The other one won; hand back its log.
		frappe.db.rollback()
		existing = frappe.db.get_value("Test Log", {"client_id": client_id}, "name")
		if not existing:
			raise
		return _feed_row(existing, duplicate=True)

	_claim_files(doc)

	return _feed_row(doc.name)


@frappe.whitelist()
def get_feed(test_run: str | None = None, limit: int = 15):
	"""Recent entries for the panel — this tester's own, or a whole run's."""
	frappe.has_permission("Test Log", "read", throw=True)

	filters = {"test_run": test_run} if test_run else {"tester": frappe.session.user}
	names = frappe.get_list(
		"Test Log",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=min(cint(limit) or 15, FEED_LIMIT),
	)

	return [_feed_row(name) for name in names]


@frappe.whitelist()
def create_run(title: str, product: str, build_version: str | None = None):
	"""Start a sheet from inside the panel, without leaving the page being tested."""
	frappe.has_permission("Test Run", "create", throw=True)

	run = frappe.get_doc(
		{
			"doctype": "Test Run",
			"title": title,
			"product": product,
			"build_version": build_version,
			"status": "In Progress",
			"tester": frappe.session.user,
		}
	).insert()

	return {"name": run.name, "title": run.title, "product": run.product, "build_version": run.build_version}


# ------------------------------------------------------------------ building the log


def _log_values(entry: frappe._dict) -> dict:
	description = cstr(entry.get("description")).strip()
	settings = get_settings()

	values = {
		"subject": _subject(entry, description),
		"test_run": entry.get("test_run"),
		"product": _product(entry, settings),
		"module_feature": entry.get("module_feature"),
		"severity": entry.get("severity") or settings.default_severity or "Medium",
		"test_type": entry.get("test_type") or settings.default_test_type or "Functional",
		"status": entry.get("status") or "Open",
		"tester": frappe.session.user,
		"test_date": entry.get("captured_at") or now_datetime(),
		"captured_at": entry.get("captured_at") or now_datetime(),
		"assigned_developer": entry.get("assigned_developer"),
		"environment": entry.get("environment"),
		"build_version": entry.get("build_version"),
		"expected_result": entry.get("expected_result"),
		"actual_result": entry.get("actual_result") or description,
		"page_route": entry.get("page_route"),
		"page_url": entry.get("page_url"),
		"viewport": entry.get("viewport"),
		"console_errors": entry.get("console_errors"),
	}

	steps = cstr(entry.get("steps_to_reproduce")).strip()
	if steps:
		values["steps_to_reproduce"] = _to_html(steps)

	return {key: value for key, value in values.items() if value not in (None, "")}


def _subject(entry: frappe._dict, description: str) -> str:
	subject = cstr(entry.get("subject")).strip()
	if not subject:
		# First line of what the tester typed, which is how they tend to write anyway.
		subject = description.split("\n", 1)[0].strip()
	if not subject:
		subject = _("Test note")

	return subject[:SUBJECT_LENGTH]


def _product(entry: frappe._dict, settings) -> str:
	product = entry.get("product")
	if not product and entry.get("test_run"):
		product = frappe.db.get_value("Test Run", entry.get("test_run"), "product")
	if not product:
		product = settings.default_product
	if not product:
		product = frappe.db.get_value("Test Product", {"is_active": 1}, "name", order_by="creation asc")

	if not product:
		frappe.throw(
			_("Set a default product in Test Log Settings, or create one Test Product first."),
			title=_("Nowhere to file this"),
		)

	return product


def _to_html(text: str) -> str:
	"""Plain text from a textarea into the Text Editor fields, newlines intact."""
	paragraphs = [frappe.utils.escape_html(line) for line in text.split("\n")]
	return "<p>" + "<br>".join(paragraphs) + "</p>"


# ------------------------------------------------------------------ evidence


def _attachment_rows(entry: frappe._dict) -> list[dict]:
	rows = []

	for item in entry.get("files") or []:
		item = frappe._dict(item)
		file_url = cstr(item.get("file_url")).strip()
		if not file_url:
			continue

		rows.append(
			{
				"attachment_type": item.get("attachment_type")
				or attachment_type_for(item.get("file_name"), item.get("mime")),
				"file_url": file_url,
				"caption": cstr(item.get("caption"))[:140] or None,
			}
		)

	for item in entry.get("links") or []:
		item = frappe._dict(item)
		if not item.get("url"):
			continue

		rows.append(
			{
				"attachment_type": "External Link",
				"external_link": item.get("url"),
				"caption": cstr(item.get("caption"))[:140] or None,
			}
		)

	return rows


def _claim_files(doc):
	"""Point the uploaded files at the log so it can be shared with a developer.

	Files land unattached (they are uploaded before the log exists), and a private
	unattached file is readable by its uploader alone. Attaching them here is what
	lets the developer open the evidence once the log is shared.
	"""
	urls = [row.file_url for row in doc.attachments if row.file_url]
	if not urls:
		return

	files = frappe.get_all(
		"File",
		filters={"file_url": ["in", urls], "owner": frappe.session.user},
		fields=["name", "attached_to_doctype", "attached_to_name"],
	)

	for file in files:
		if file.attached_to_doctype:
			continue

		frappe.db.set_value(
			"File",
			file.name,
			{"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
			update_modified=False,
		)


# ------------------------------------------------------------------ responses


def _feed_row(name: str, duplicate: bool = False) -> dict:
	log = frappe.db.get_value(
		"Test Log",
		name,
		[
			"name",
			"subject",
			"status",
			"severity",
			"test_run",
			"product",
			"module_feature",
			"creation",
			"assigned_developer",
		],
		as_dict=True,
	)
	log.duplicate = duplicate
	log.url = get_url_to_form("Test Log", name)
	log.thumbnail = frappe.db.get_value(
		"Test Log Attachment",
		{"parent": name, "parenttype": "Test Log", "attachment_type": "Screenshot"},
		"file_url",
		order_by="idx asc",
	)
	log.evidence_count = frappe.db.count(
		"Test Log Attachment", {"parent": name, "parenttype": "Test Log"}
	)

	return log


def _as_dict(entry) -> frappe._dict:
	if isinstance(entry, str):
		entry = frappe.parse_json(entry)
	if not isinstance(entry, dict):
		frappe.throw(_("Malformed capture entry."))

	return frappe._dict(entry)
