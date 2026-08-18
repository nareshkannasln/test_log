# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Makes the timeline on a Test Log a conversation rather than a noticeboard.

Frappe already stores comments against every document; what it does not do is tell
the other side that one has been written. On a test log the other side is exactly
who needs to know — a developer asking a question is the whole point of the Needs
Info status, and the answer is no use sitting unread.
"""

import frappe
from frappe import _
from frappe.utils import get_url_to_form


def on_comment(doc, method=None):
	"""Hooked on Comment.after_insert — notify the other party on a Test Log."""
	if doc.reference_doctype != "Test Log" or doc.comment_type != "Comment":
		return

	try:
		notify_counterparts(doc)
	except Exception:
		# A comment must never fail to save because a notification could not go out.
		frappe.log_error(title="Test Log: could not notify about a comment")


def notify_counterparts(comment):
	log = frappe.db.get_value(
		"Test Log",
		comment.reference_name,
		["name", "subject", "tester", "assigned_developer"],
		as_dict=True,
	)
	if not log:
		return

	author = comment.owner or frappe.session.user
	recipients = {log.tester, log.assigned_developer} - {None, "", author}
	if not recipients:
		return

	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	body = frappe.utils.strip_html_tags(comment.content or "").strip()

	enqueue_create_notification(
		list(recipients),
		{
			"type": "Alert",
			"document_type": "Test Log",
			"document_name": log.name,
			"subject": _("{0} commented on {1}").format(frappe.utils.get_fullname(author), log.name),
			"from_user": author,
			"email_content": f"<p>{frappe.utils.escape_html(body[:500])}</p>"
			f"<p><i>{frappe.utils.escape_html(log.subject or '')}</i></p>"
			f'<p><a href="{get_url_to_form("Test Log", log.name)}">{_("Open test log")}</a></p>',
		},
	)
