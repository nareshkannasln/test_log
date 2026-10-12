"""Permission-scoped quality metrics, build comparison and sign-off artifacts."""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, time_diff_in_hours

from test_log.constants import UNSETTLED_STATUSES

CHARTS = {
	"Open Logs by Developer": "open",
	"Mean Fix Time by Severity": "fix_time",
	"Reopen Rate by Developer and Product": "reopen",
	"Defects by Build": "build",
}


def quality_rows(metric="open", product=None):
	filters = {"product": product} if product else {}
	logs = frappe.get_list(
		"Test Log",
		filters=filters,
		fields=[
			"name",
			"status",
			"severity",
			"assigned_developer",
			"product",
			"build_version",
			"creation",
			"resolved_on",
			"first_resolved_on",
			"reopen_count",
		],
		limit=0,
	)
	groups = defaultdict(list)
	for log in logs:
		if metric == "open" and log.status in UNSETTLED_STATUSES:
			groups[log.assigned_developer or _("Unassigned")].append(1)
		elif metric == "build":
			groups[log.build_version or _("Unspecified")].append(1)
		elif metric == "fix_time" and (log.first_resolved_on or log.resolved_on):
			groups[log.severity].append(
				max(0, time_diff_in_hours(log.first_resolved_on or log.resolved_on, log.creation) / 24)
			)
		elif metric == "reopen" and (log.first_resolved_on or log.resolved_on or log.reopen_count):
			groups[f"{log.assigned_developer or _('Unassigned')} · {log.product}"].append(
				int(bool(log.reopen_count))
			)
	if metric not in CHARTS.values():
		frappe.throw(_("Unknown quality metric."))
	rows = []
	for label, values in groups.items():
		value = (
			sum(values)
			if metric in ("open", "build")
			else sum(values) / len(values) * (100 if metric == "reopen" else 1)
		)
		rows.append({"group": label, "value": round(value, 2), "sample_size": len(values)})
	return sorted(rows, key=lambda row: (-row["value"], row["group"]))


@frappe.whitelist()
def quality_chart(chart_name=None, chart=None, filters=None, **kwargs):
	if chart_name is None and chart:
		chart_name = frappe.parse_json(chart).get("name")
	metric = CHARTS.get(chart_name)
	if not metric:
		frappe.throw(_("Unknown quality chart."))
	rows = quality_rows(metric)[:20]
	return {
		"labels": [r["group"] for r in rows],
		"datasets": [{"name": _(chart_name), "values": [r["value"] for r in rows]}],
	}


@frappe.whitelist()
def sla_breached(filters=None):
	return _sla_count("breached")


@frappe.whitelist()
def sla_at_risk(filters=None):
	return _sla_count("at_risk")


def _sla_count(kind):
	filters = {
		"status": ["in", UNSETTLED_STATUSES],
		"target_date": ["<", nowdate()]
		if kind == "breached"
		else ["between", [nowdate(), add_days(nowdate(), 1)]],
	}
	return {
		"value": len(frappe.get_list("Test Log", filters=filters, pluck="name", limit=0)),
		"fieldtype": "Int",
	}


def compare_builds(product, from_build, to_build):
	if not product or not from_build or not to_build or from_build == to_build:
		frappe.throw(_("Choose a product and two different builds."))
	logs = frappe.get_list(
		"Test Log",
		filters={"product": product},
		fields=["name", "subject", "status", "build_version", "fixed_in_build", "reopen_count"],
		limit=0,
	)
	rows = []
	for log in logs:
		category = None
		if log.fixed_in_build == to_build and log.status in ("Fixed", "Completed"):
			category = _("Fixed")
		elif log.build_version == to_build and log.status == "Reopened":
			category = _("Regressed")
		elif log.build_version in (from_build, to_build) and log.status in UNSETTLED_STATUSES:
			category = _("Still Open")
		if category:
			rows.append(
				{
					"category": category,
					"test_log": log.name,
					"title": log.subject,
					"before": log.build_version,
					"after": log.status,
				}
			)
	results = {from_build: {}, to_build: {}}
	runs = frappe.get_list(
		"Test Run",
		filters={"product": product, "build_version": ["in", [from_build, to_build]]},
		fields=["name", "build_version"],
		order_by="run_date asc, creation asc",
		limit=0,
	)
	for run in runs:
		for row in frappe.get_doc("Test Run", run.name).cases:
			results[run.build_version][row.test_case] = row
	for name, current in results[to_build].items():
		previous = results[from_build].get(name)
		if previous and previous.result == "Pass" and current.result == "Fail":
			linked = (
				current.test_log
				if current.test_log and frappe.has_permission("Test Log", "read", doc=current.test_log)
				else None
			)
			rows.append(
				{
					"category": _("Regressed"),
					"test_case": name,
					"test_log": linked,
					"title": current.title,
					"before": previous.result,
					"after": current.result,
				}
			)
	return rows


@frappe.whitelist()
def sign_off_certificate(test_run: str):
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("read")
	if run.status != "Signed Off" or not run.signed_off_by:
		frappe.throw(_("Sign off the run before printing its certificate."))
	logs = frappe.get_all("Test Log", filters={"test_run": run.name}, fields=["name", "status"])
	for log in logs:
		frappe.has_permission("Test Log", "read", doc=log.name, throw=True)
	from frappe.utils.pdf import get_pdf

	from test_log.api.artifacts import deliver

	html = frappe.render_template(
		"templates/test_run_certificate.html",
		{"run": run, "counts": Counter(log.status for log in logs), "total": len(logs)},
	)
	return deliver(get_pdf(html), run, f"Sign-off - {run.name}.pdf", 1)


@frappe.whitelist()
def install_saved_filters():
	frappe.has_permission("Test Log", "read", throw=True)
	user = frappe.session.user
	presets = {
		"My open Critical": [
			["severity", "=", "Critical"],
			["tester", "=", user],
			["status", "in", list(UNSETTLED_STATUSES)],
		],
		"Waiting on me": [["assigned_developer", "=", user], ["status", "in", list(UNSETTLED_STATUSES)]],
		"Needs Info from me": [["tester", "=", user], ["status", "=", "Needs Info"]],
		"Ready to verify": [["tester", "=", user], ["status", "=", "Fixed"]],
	}
	for label, filters in presets.items():
		if not frappe.db.exists(
			"List Filter", {"reference_doctype": "Test Log", "for_user": user, "filter_name": label}
		):
			frappe.get_doc(
				{
					"doctype": "List Filter",
					"reference_doctype": "Test Log",
					"for_user": user,
					"filter_name": label,
					"filters": frappe.as_json([["Test Log", *row, False] for row in filters]),
				}
			).insert()
	return list(presets)
