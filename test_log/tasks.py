# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Scheduled work: chasing logs that have gone past their date, and the daily digest.

Both are off until a site turns them on in Test Log Settings — a testing app that
starts emailing people the day it is installed makes itself unwelcome.
"""

import frappe
from frappe import _
from frappe.utils import get_url_to_form, get_url_to_list, getdate, nowdate

from test_log.constants import UNSETTLED_STATUSES
from test_log.test_log.doctype.test_log_settings.test_log_settings import get_settings

DIGEST_LIMIT = 25


def daily():
	"""Both daily jobs behind one hook, each behind its own switch."""
	settings = get_settings()

	if settings.get("notify_overdue_logs"):
		notify_overdue_logs()

	if settings.get("send_daily_digest"):
		send_daily_digest()


def notify_overdue_logs():
	"""Nudge whoever a log is waiting on once its target date has gone by."""
	logs = frappe.get_all(
		"Test Log",
		filters={
			"target_date": ["<", nowdate()],
			"status": ["in", UNSETTLED_STATUSES],
		},
		fields=["name", "subject", "status", "severity", "target_date", "assigned_developer", "tester"],
		order_by="target_date asc",
		limit=500,
	)

	for log in logs:
		recipients = {log.assigned_developer, log.tester} - {None, ""}
		if not recipients:
			continue

		days = (getdate(nowdate()) - getdate(log.target_date)).days
		_notify(
			list(recipients),
			"Test Log",
			log.name,
			_("{0} is {1} days past its target date").format(log.name, days),
			f"<p><b>{frappe.utils.escape_html(log.subject)}</b></p>"
			f"<p>{_('Status')}: {_(log.status)} &middot; {_('Severity')}: {_(log.severity or '')}</p>"
			f'<p><a href="{get_url_to_form("Test Log", log.name)}">{_("Open test log")}</a></p>',
		)


def send_daily_digest():
	"""One summary per developer of everything still sitting with them."""
	logs = frappe.get_all(
		"Test Log",
		filters={
			"status": ["in", UNSETTLED_STATUSES],
			"assigned_developer": ["is", "set"],
		},
		fields=["name", "subject", "status", "severity", "target_date", "assigned_developer"],
		order_by="severity desc, creation asc",
		limit=2000,
	)

	by_developer = {}
	for log in logs:
		by_developer.setdefault(log.assigned_developer, []).append(log)

	for developer, rows in by_developer.items():
		if not frappe.db.get_value("User", developer, "enabled"):
			continue

		_notify(
			[developer],
			"Test Log",
			rows[0].name,
			_("{0} test logs are waiting on you").format(len(rows)),
			_digest_body(rows),
		)


def _digest_body(rows: list) -> str:
	items = []
	for log in rows[:DIGEST_LIMIT]:
		due = _(" · due {0}").format(log.target_date) if log.target_date else ""
		items.append(
			f'<li><a href="{get_url_to_form("Test Log", log.name)}">{log.name}</a> '
			f"&mdash; {frappe.utils.escape_html(log.subject or '')} "
			f"<span>({_(log.status)}, {_(log.severity or '')}{due})</span></li>"
		)

	body = ["<ul>", *items, "</ul>"]
	if len(rows) > DIGEST_LIMIT:
		body.append(f"<p>{_('and {0} more').format(len(rows) - DIGEST_LIMIT)}</p>")

	body.append(f'<p><a href="{get_url_to_list("Test Log")}">{_("Open the full list")}</a></p>')
	return "".join(body)


def _notify(recipients: list[str], doctype: str, name: str, subject: str, body: str):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	enqueue_create_notification(
		recipients,
		{
			"type": "Alert",
			"document_type": doctype,
			"document_name": name,
			"subject": subject,
			"from_user": "Administrator",
			"email_content": body,
		},
	)
