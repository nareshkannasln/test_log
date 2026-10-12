# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_url_to_form, now_datetime

from test_log.constants import (
	BULK_EDITABLE_FIELDS,
	INITIAL_STATUSES,
	RESOLVED_STATUSES,
	STATUS_TRANSITIONS,
	URGENT_SEVERITIES,
	VERIFIED_STATUSES,
	can_transition,
)
from test_log.evidence import readable_file
from test_log.jobs import background_large
from test_log.test_log.doctype.test_run.test_run import refresh_summary

SIMILAR_LIMIT = 5
# Words too common in a bug report to tell two of them apart.
STOP_WORDS = set(
	"the and for with when that this from into not was are is in on of to an it at "
	"error issue bug page button click shows showing".split()
)


class TestLog(Document):
	def validate(self):
		self.validate_developer_changes()
		self.set_default_developer()
		self.validate_status_flow()
		self.validate_run_open()
		self.validate_duplicate_of()
		self.validate_attachments()
		self.stamp_resolution()
		from test_log.management import apply_sla

		apply_sla(self)

	def on_update(self):
		self.share_and_assign()
		self.inherit_run_shares()
		self.notify_status_change()
		refresh_summary(self.test_run)

		previous = self.get_doc_before_save()
		if previous and previous.test_run and previous.test_run != self.test_run:
			refresh_summary(previous.test_run)

		self.queue_run_report()

	def on_trash(self):
		refresh_summary(self.test_run)

	# ------------------------------------------------------------------ validation

	def validate_status_flow(self):
		"""Keep the status on the path the app offers.

		The transitions are what the form buttons and the widget already draw; without
		this they were advisory only, so the list view, the REST API or a stale tab
		could move a log straight from Open to Completed.
		"""
		if self.flags.ignore_status_flow or not _flow_enforced():
			return

		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else None

		if can_transition(previous_status, self.status):
			return

		if not previous_status:
			frappe.throw(
				_("A new test log starts as {0}.").format(", ".join(_(s) for s in INITIAL_STATUSES)),
				title=_("Not a valid status"),
			)

		allowed = STATUS_TRANSITIONS.get(previous_status, ())
		frappe.throw(
			_("{0} cannot move from {1} to {2}. From {1} it can go to: {3}.").format(
				self.name,
				_(previous_status),
				_(self.status),
				", ".join(_(s) for s in allowed) or _("nowhere"),
			),
			title=_("Not a valid status change"),
		)

	def validate_run_open(self):
		"""A signed-off run is a closed book — nothing new gets filed against it."""
		if not self.test_run or not _settings().get("block_signed_off_runs"):
			return

		previous = self.get_doc_before_save()
		if previous and previous.test_run == self.test_run:
			# Already in that run; let it be updated, only new arrivals are blocked.
			return

		if frappe.db.get_value("Test Run", self.test_run, "status") == "Signed Off":
			frappe.throw(
				_("{0} has been signed off. Pick another run for this log.").format(self.test_run),
				title=_("That run is closed"),
			)

	def validate_duplicate_of(self):
		if not self.duplicate_of:
			return

		if self.duplicate_of == self.name:
			frappe.throw(_("A test log cannot be a duplicate of itself."))

		parent = frappe.db.get_value("Test Log", self.duplicate_of, "duplicate_of")
		if parent:
			# Point at the original rather than building a chain of duplicates.
			self.duplicate_of = parent

	def validate_attachments(self):
		"""Enforce the upload rules on the server too.

		The capture panel already checks the size limit and the link scheme, but a
		direct API call skipped both.
		"""
		limit_mb = cint(_settings().get("max_attachment_mb")) or 50

		for row in self.attachments or []:
			if not row.file_url and not row.external_link:
				frappe.throw(
					_("Row {0}: attach a file or give an external link.").format(row.idx),
					title=_("Empty evidence row"),
				)

			if row.external_link and not row.external_link.lower().startswith(("http://", "https://")):
				frappe.throw(
					_("Row {0}: an external link has to start with http:// or https://.").format(row.idx)
				)

			if not row.file_url:
				continue

			file = readable_file(row.file_url, self, throw=True)
			size = file.file_size
			if size and size > limit_mb * 1024 * 1024:
				frappe.throw(
					_("Row {0}: {1} is over the {2} MB limit set in Test Log Settings.").format(
						row.idx, row.file_url, limit_mb
					),
					title=_("Attachment too large"),
				)

	# ------------------------------------------------------------------ helpers

	def validate_developer_changes(self):
		roles = set(frappe.get_roles())
		if frappe.session.user == "Administrator" or roles & {"Tester", "System Manager"}:
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		# Shared write access is only for the developer's response, including REST/bulk saves.
		allowed = {"status", "resolution", "fixed_in_build"}
		for field in self.meta.fields:
			if field.fieldtype in frappe.model.table_fields:
				columns = [
					f.fieldname
					for f in frappe.get_meta(field.options).fields
					if f.fieldtype not in frappe.model.no_value_fields
				]
				before = [[row.get(c) for c in columns] for row in previous.get(field.fieldname)]
				after = [[row.get(c) for c in columns] for row in self.get(field.fieldname)]
				if before != after:
					frappe.throw(_("Only testers can change evidence."), frappe.PermissionError)
				continue
			if field.fieldtype in frappe.model.no_value_fields or field.fieldname in allowed:
				continue
			if self.has_value_changed(field.fieldname):
				frappe.throw(_("Only testers can change {0}.").format(_(field.label)), frappe.PermissionError)
		if self.status != previous.status and self.status == "Completed":
			frappe.throw(_("Only testers can verify a fix."), frappe.PermissionError)

	def inherit_run_shares(self):
		previous = self.get_doc_before_save()
		if not self.test_run or (previous and previous.test_run == self.test_run):
			return
		for share in frappe.get_all(
			"DocShare",
			filters={"share_doctype": "Test Run", "share_name": self.test_run},
			fields=["user", "everyone", "read", "write", "share"],
		):
			existing = (
				frappe.db.get_value(
					"DocShare",
					{
						"share_doctype": self.doctype,
						"share_name": self.name,
						**({"everyone": 1} if share.everyone else {"user": share.user}),
					},
					["read", "write", "share"],
					as_dict=True,
				)
				or {}
			)
			frappe.share.add_docshare(
				self.doctype,
				self.name,
				share.user,
				everyone=share.everyone,
				**{
					key: max(share.get(key) or 0, existing.get(key) or 0)
					for key in ("read", "write", "share")
				},
				flags={"ignore_share_permission": True},
				notify=0,
			)

	def set_default_developer(self):
		if self.assigned_developer or not self.product:
			return

		self.assigned_developer = frappe.db.get_value("Test Product", self.product, "default_developer")

	def stamp_resolution(self):
		"""Record who closed the log and who verified it, and clear both on reopen.

		Resolving is the developer's half (Fixed / Won't Fix); verifying is the
		tester's (Completed), and the two are worth telling apart on a handover.
		"""
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else None

		if self.status == previous_status:
			return

		if self.status in RESOLVED_STATUSES:
			if not self.resolved_by:
				self.resolved_by = frappe.session.user
				self.resolved_on = now_datetime()
		else:
			self.resolved_by = None
			self.resolved_on = None

		if self.status in VERIFIED_STATUSES:
			self.verified_by = frappe.session.user
			self.verified_on = now_datetime()
		else:
			self.verified_by = None
			self.verified_on = None

	def share_and_assign(self):
		"""Give the assigned developer access to the log and put it on their to-do list."""
		if not self.assigned_developer or self.assigned_developer == "Administrator":
			return

		previous = self.get_doc_before_save()
		if previous and previous.assigned_developer == self.assigned_developer:
			return

		frappe.share.add(self.doctype, self.name, self.assigned_developer, read=1, write=1, share=1, notify=0)

		already_assigned = frappe.db.exists(
			"ToDo",
			{
				"reference_type": self.doctype,
				"reference_name": self.name,
				"allocated_to": self.assigned_developer,
				"status": "Open",
			},
		)
		if already_assigned:
			return

		from frappe.desk.form.assign_to import add as assign

		assign(
			{
				"doctype": self.doctype,
				"name": self.name,
				"assign_to": [self.assigned_developer],
				"description": self.subject,
				"date": self.target_date,
				"priority": "High" if self.severity in URGENT_SEVERITIES else "Medium",
			}
		)

	def queue_run_report(self):
		"""Keep the run's Word report current, if the site asked for that.

		Deduplicated per run, so a burst of logs rebuilds the document once.
		"""
		# .get() rather than attribute access: an app updated but not yet migrated must
		# not break saving a test log.
		if not _settings().get("auto_attach_run_report"):
			return

		previous = self.get_doc_before_save()
		if previous and previous.status == self.status and previous.test_run == self.test_run:
			return

		runs = {self.test_run, previous.test_run if previous else None} - {None, ""}
		for run in runs:
			if not frappe.has_permission("Test Run", "write", doc=run):
				continue
			frappe.enqueue(
				"test_log.api.report.refresh_run_report",
				queue="long",
				job_id=f"test-log-report::{run}",
				deduplicate=True,
				enqueue_after_commit=True,
				test_run=run,
			)

	def counterparts(self) -> set[str]:
		"""The other people on this log — everyone but whoever is acting."""
		return {self.tester, self.assigned_developer} - {None, "", frappe.session.user}

	def notify_status_change(self):
		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		recipients = self.counterparts()
		if not recipients:
			return

		from test_log.management import ready_to_verify_url

		body = f"<p>{frappe.utils.escape_html(self.subject)}</p>"
		if self.status == "Fixed":
			body += f'<p><a href="{ready_to_verify_url(self.tester)}">{_("Ready to verify")}</a></p>'
		notify(
			self,
			list(recipients),
			_("{0} moved from {1} to {2}").format(self.name, _(previous.status), _(self.status)),
			body,
		)


def notify(doc, recipients: list[str], subject: str, body: str, notification_type: str = "Alert"):
	"""One notification, with a link back to the log."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	enqueue_create_notification(
		recipients,
		{
			"type": notification_type,
			"document_type": doc.doctype,
			"document_name": doc.name,
			"subject": subject,
			"from_user": frappe.session.user,
			"email_content": body
			+ f'<p><a href="{get_url_to_form(doc.doctype, doc.name)}">{_("Open test log")}</a></p>',
		},
	)


def _settings():
	from test_log.test_log.doctype.test_log_settings.test_log_settings import get_settings

	return get_settings()


def _flow_enforced() -> bool:
	settings = _settings()
	# Sites that installed before the switch existed have no value stored; the flow
	# is the app's intended behaviour, so treat a missing value as on.
	value = settings.get("enforce_status_flow")
	return True if value is None else bool(value)


# ---------------------------------------------------------------------- desk api


@frappe.whitelist()
def set_status(name: str, status: str, resolution: str | None = None, note: str | None = None):
	"""One-click status update used by the form and list view buttons.

	`note` is the conversation half — it lands in the timeline and reaches the other
	party, so a "why" travels with every status change rather than being overwritten
	in the resolution field.
	"""
	doc = frappe.get_doc("Test Log", name)
	doc.check_permission("write")

	doc.status = status
	if resolution:
		doc.resolution = resolution

	doc.save()

	if note:
		add_note(doc.name, note)

	return doc.status


@frappe.whitelist()
@background_large
def bulk_set_status(names: str | list, status: str):
	"""Update many logs at once from the list view.

	Returns what happened to each one — a log the user cannot write, or one the status
	flow will not move, is reported back rather than quietly dropped.
	"""
	if isinstance(names, str):
		names = frappe.parse_json(names)

	updated, skipped = [], []
	for name in names:
		savepoint = f"bulk_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			set_status(name, status)
			updated.append(name)
		except frappe.PermissionError:
			frappe.db.rollback(save_point=savepoint)
			skipped.append({"name": name, "reason": _("You cannot edit this log.")})
			frappe.clear_last_message()
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			skipped.append({"name": name, "reason": _clean_message(e)})
			# The thrown message is reported per row instead; leaving it queued would
			# raise one dialog per failure on top of the summary.
			frappe.clear_last_message()

	return {"updated": updated, "skipped": skipped}


@frappe.whitelist()
@background_large
def bulk_update_field(names: str | list, fieldname: str, value):
	"""Set one field on many logs — assign a developer, move them to another run.

	Only the fields in BULK_EDITABLE_FIELDS are allowed; status has its own route so
	the flow rules cannot be sidestepped.
	"""
	if fieldname not in BULK_EDITABLE_FIELDS:
		frappe.throw(_("{0} cannot be set in bulk.").format(fieldname))

	if isinstance(names, str):
		names = frappe.parse_json(names)

	updated, skipped = [], []
	for name in names:
		savepoint = f"bulk_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			doc = frappe.get_doc("Test Log", name)
			doc.check_permission("write")
			doc.set(fieldname, value)
			doc.save()
			updated.append(name)
		except frappe.PermissionError:
			frappe.db.rollback(save_point=savepoint)
			skipped.append({"name": name, "reason": _("You cannot edit this log.")})
			frappe.clear_last_message()
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			skipped.append({"name": name, "reason": _clean_message(e)})
			# The thrown message is reported per row instead; leaving it queued would
			# raise one dialog per failure on top of the summary.
			frappe.clear_last_message()

	return {"updated": updated, "skipped": skipped}


@frappe.whitelist()
def add_note(name: str, note: str):
	"""Post a comment on a log, so a status change carries its "why" with it.

	The notification is not sent from here — every comment on a Test Log goes out
	through the Comment hook, whether it was typed in the timeline or came with a
	status change, so nobody gets told twice.
	"""
	doc = frappe.get_doc("Test Log", name)
	doc.check_permission("read")

	note = frappe.utils.strip_html_tags(note or "").strip()
	if not note:
		return

	doc.add_comment("Comment", note)

	return {"comment": True}


@frappe.whitelist()
def find_similar(
	subject: str,
	test_run: str | None = None,
	product: str | None = None,
	module_feature: str | None = None,
	page_route: str | None = None,
	exclude: str | None = None,
):
	"""Logs that look like the one being written — the same finding filed twice is
	the commonest complaint about a capture panel.

	Match indexed route/feature context first, then distinctive subject words in the
	latest 200 logs in the same run or product. get_list keeps both stages restricted
	to logs the caller is allowed to see.
	"""
	if not _settings().get("warn_on_duplicates"):
		return []

	words = _keywords(subject)
	if not words and not page_route and not module_feature:
		return []

	scope = {}
	if test_run:
		scope["test_run"] = test_run
	elif product:
		scope["product"] = product

	or_filters = []
	if page_route:
		or_filters.append(["page_route", "=", page_route])
	if module_feature:
		or_filters.append(["module_feature", "=", module_feature])

	filters = dict(scope)
	filters["duplicate_of"] = ["is", "not set"]
	if exclude:
		filters["name"] = ["!=", exclude]

	fields = ["name", "subject", "status", "severity", "module_feature", "page_route", "creation"]
	candidates = (
		frappe.get_list(
			"Test Log",
			filters=filters,
			or_filters=or_filters,
			fields=fields,
			order_by="creation desc",
			limit=20,
		)
		if or_filters
		else []
	)
	if words and len(candidates) < SIMILAR_LIMIT:
		# Keep the fallback bounded: score recent scoped logs in Python, avoiding a
		# full-table OR of leading-wildcard LIKE predicates on every keystroke.
		seen = {row.name for row in candidates}
		recent = frappe.get_list(
			"Test Log",
			filters=filters,
			fields=fields,
			order_by="creation desc",
			limit=200,
		)
		candidates.extend(row for row in recent if row.name not in seen and _score(row, words, None, None))

	scored = sorted(candidates, key=lambda row: -_score(row, words, module_feature, page_route))
	return scored[:SIMILAR_LIMIT]


def _keywords(subject: str) -> list[str]:
	words = {word.strip(".,:;!?()[]\"'").lower() for word in frappe.utils.cstr(subject).split()}
	return sorted(word for word in words if len(word) > 3 and word not in STOP_WORDS)[:6]


def _score(row, words, module_feature, page_route) -> int:
	subject = (row.get("subject") or "").lower()
	score = sum(1 for word in words if word in subject)
	if module_feature and row.get("module_feature") == module_feature:
		score += 2
	if page_route and row.get("page_route") == page_route:
		score += 2
	return score


def _clean_message(exception: Exception) -> str:
	"""A thrown validation message, without the markup frappe.throw wraps it in."""
	message = frappe.utils.strip_html_tags(str(exception)).strip()
	return message or _("Could not be updated.")
