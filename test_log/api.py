# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Sharing helpers so a tester can hand a whole test run to a developer in one action."""

import frappe
from frappe import _
from frappe.utils import get_url_to_form, get_url_to_list


@frappe.whitelist()
def share_run(test_run: str, user: str, note: str | None = None, can_write: int = 1):
	"""Share a Test Run and every log inside it with one developer."""
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("share")

	if not frappe.db.exists("User", user):
		frappe.throw(_("{0} is not a user on this site.").format(user))

	can_write = int(can_write)

	frappe.share.add("Test Run", run.name, user, read=1, write=can_write, notify=0)

	logs = frappe.get_all("Test Log", filters={"test_run": run.name}, pluck="name")
	for log in logs:
		frappe.share.add("Test Log", log, user, read=1, write=can_write, notify=0)

	_notify_share(run, user, note, len(logs))

	return {"shared_logs": len(logs)}


def _notify_share(run, user, note, log_count):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	filtered_list = f"{get_url_to_list('Test Log')}?test_run={run.name}"
	body = [
		f"<p>{_('{0} shared a test run with you.').format(frappe.utils.get_fullname(frappe.session.user))}</p>",
		f"<p><b>{frappe.utils.escape_html(run.title)}</b> &mdash; {log_count} {_('test logs')}</p>",
	]
	if note:
		body.append(f"<p>{frappe.utils.escape_html(note)}</p>")
	body.append(f'<p><a href="{get_url_to_form("Test Run", run.name)}">{_("Open the run")}</a> &middot; ')
	body.append(f'<a href="{filtered_list}">{_("Open its test logs")}</a></p>')

	enqueue_create_notification(
		[user],
		{
			"type": "Share",
			"document_type": "Test Run",
			"document_name": run.name,
			"subject": _("Test run shared: {0}").format(run.title),
			"from_user": frappe.session.user,
			"email_content": "".join(body),
		},
	)


@frappe.whitelist()
def get_run_stats(test_run: str):
	"""Status breakdown for the Test Run form dashboard."""
	frappe.has_permission("Test Run", "read", doc=test_run, throw=True)

	rows = frappe.get_all(
		"Test Log",
		filters={"test_run": test_run},
		fields=["status", "count(name) as qty"],
		group_by="status",
		order_by="status",
	)
	return {row.status: row.qty for row in rows}
