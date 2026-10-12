"""Large actions run with the requester's permissions and report to their own room."""

from contextvars import ContextVar
from functools import wraps
from inspect import signature

import frappe
from frappe import _

THRESHOLD = 50
_running = ContextVar("test_log_background_action", default=False)
OPERATIONS = {
	"bulk_set_status": "test_log.api.bulk_set_status",
	"bulk_update_field": "test_log.api.bulk_update_field",
	"build_selection_report": "test_log.api.build_selection_report",
	"build_selection_sheet": "test_log.api.build_selection_sheet",
	"build_run_report": "test_log.api.build_run_report",
	"build_run_sheet": "test_log.api.build_run_sheet",
}


def background_large(function):
	@wraps(function)
	def wrapped(*args, **kwargs):
		if _running.get():
			return function(*args, **kwargs)
		arguments = signature(function).bind(*args, **kwargs).arguments
		if "names" in arguments:
			names = arguments["names"]
			if isinstance(names, str):
				names = frappe.parse_json(names)
			if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
				frappe.throw(_("Select a list of test logs."))
			arguments["names"] = list(dict.fromkeys(names))
			count = len(arguments["names"])
		else:
			frappe.has_permission("Test Run", "read", doc=arguments["test_run"], throw=True)
			count = frappe.db.count("Test Log", {"test_run": arguments["test_run"]})
		if count <= THRESHOLD:
			return function(**arguments)
		job_id = "test-log-action-" + frappe.generate_hash(length=16)
		frappe.enqueue(
			"test_log.jobs.run_action",
			queue="long",
			timeout=3600,
			enqueue_after_commit=True,
			job_id=job_id,
			operation=function.__name__,
			arguments=dict(arguments),
			requester=frappe.session.user,
			action_id=job_id,
		)
		return {"queued": True, "job_id": job_id, "count": count}

	return wrapped


def run_action(operation, arguments, requester, action_id):
	previous_user = frappe.session.user
	token = _running.set(True)
	try:
		frappe.set_user(requester)
		if not frappe.db.get_value("User", requester, "enabled"):
			frappe.throw(_("This user is disabled."), frappe.PermissionError)
		result = frappe.get_attr(OPERATIONS[operation])(**arguments)
		frappe.publish_realtime(
			"test_log_action_complete",
			{"job_id": action_id, "operation": operation, "result": result},
			user=requester,
			after_commit=True,
		)
	except Exception:
		frappe.db.rollback()
		frappe.publish_realtime(
			"test_log_action_complete",
			{
				"job_id": action_id,
				"operation": operation,
				"error": _("The action failed. Please try again or contact your administrator."),
			},
			user=requester,
		)
		raise
	finally:
		_running.reset(token)
		frappe.set_user(previous_user)
