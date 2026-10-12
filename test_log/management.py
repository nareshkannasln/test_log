"""Test execution, SLAs and tester-owned workflow actions."""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_url_to_list, getdate, now_datetime

from test_log.constants import UNSETTLED_STATUSES


def require_tester():
	if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & {"Tester", "System Manager"}:
		frappe.throw(_("Only testers can perform this action."), frappe.PermissionError)


def validate_cases(run):
	previous = run.get_doc_before_save()
	old = {row.name: row for row in previous.get("cases", [])} if previous else {}
	for row in run.get("cases", []):
		before = old.get(row.name)
		if not before or before.test_case != row.test_case:
			require_tester()
			case = frappe.get_doc("Test Case", row.test_case)
			case.check_permission("read")
			if not case.is_active or case.product != run.product:
				frappe.throw(_("Choose an active test case from this product."))
			row.title, row.steps, row.expected_result = case.title, case.steps, case.expected_result
			row.test_log = None
		else:
			for key in ("title", "steps", "expected_result", "test_log", "executed_by", "executed_on"):
				row.set(key, before.get(key))
		if not before or row.result != before.result or row.actual_result != before.actual_result:
			require_tester()
			if previous and previous.status == "Signed Off":
				frappe.throw(_("Signed-off test results cannot be changed."))
			if row.result == "Fail" and not row.actual_result:
				frappe.throw(_("Describe the actual result for a failed case."))
			row.executed_by = frappe.session.user if row.result != "Not Run" else None
			row.executed_on = now_datetime() if row.result != "Not Run" else None
	if old.keys() - {row.name for row in run.get("cases", [])}:
		require_tester()
		if previous.status == "Signed Off":
			frappe.throw(_("Signed-off test results cannot be removed."))
	run.case_count = len(run.get("cases", []))
	for result, key in (
		("Pass", "passed_count"),
		("Fail", "failed_count"),
		("Blocked", "blocked_count"),
		("Skipped", "skipped_count"),
	):
		run.set(key, sum(row.result == result for row in run.get("cases", [])))
	run.coverage_percent = (
		100 * (run.passed_count + run.failed_count) / run.case_count if run.case_count else 0
	)


def raise_failed_cases(run):
	for row in run.get("cases", []):
		if row.result != "Fail" or row.test_log:
			continue
		case = frappe.get_doc("Test Case", row.test_case)
		log = frappe.get_doc(
			{
				"doctype": "Test Log",
				"subject": row.title[:140],
				"product": run.product,
				"test_run": run.name,
				"test_case": row.test_case,
				"build_version": run.build_version,
				"steps_to_reproduce": row.steps,
				"expected_result": row.expected_result,
				"actual_result": row.actual_result,
				"tester": frappe.session.user,
				"severity": case.severity,
				"module_feature": case.module_feature,
				"status": "Open",
			}
		).insert()
		row.db_set("test_log", log.name)


@frappe.whitelist()
def add_cases(test_run: str, cases: str | list):
	require_tester()
	run = frappe.get_doc("Test Run", test_run)
	run.check_permission("write")
	if run.status == "Signed Off":
		frappe.throw(_("This run is signed off."))
	cases = frappe.parse_json(cases) if isinstance(cases, str) else cases
	if not isinstance(cases, list) or not cases:
		frappe.throw(_("Select test cases."))
	existing = {row.test_case for row in run.cases}
	for name in dict.fromkeys(cases):
		if name not in existing:
			run.append("cases", {"test_case": name, "result": "Not Run"})
	run.save()
	return run.name


def apply_sla(log):
	if not log.target_date and log.product:
		days = cint(
			frappe.db.get_value("Test Product", log.product, f"sla_{(log.severity or '').lower()}_days")
		)
		if days > 0:
			log.target_date = add_days(getdate(log.test_date or log.creation), days)
	previous = log.get_doc_before_save()
	if previous:
		log.reopen_count = cint(previous.get("reopen_count")) + int(
			log.status == "Reopened" and previous.status != "Reopened"
		)
		log.first_resolved_on = previous.get("first_resolved_on")
	if log.status in ("Fixed", "Completed", "Won't Fix") and not log.get("first_resolved_on"):
		log.first_resolved_on = now_datetime()


@frappe.whitelist()
def verify_build(product: str, build: str):
	require_tester()
	if not product or not build:
		frappe.throw(_("Choose a product and fixed build."))
	from test_log.test_log.doctype.test_log.test_log import bulk_set_status

	names = frappe.get_list(
		"Test Log",
		filters={"product": product, "fixed_in_build": build, "status": "Fixed"},
		pluck="name",
		limit=0,
	)
	return bulk_set_status(names, "Completed")


def ready_to_verify_url(tester):
	return get_url_to_list("Test Log") + "?" + urlencode({"status": "Fixed", "tester": tester})


@frappe.whitelist()
def merge_duplicate(source: str, target: str):
	require_tester()
	if source == target:
		frappe.throw(_("Choose a different original log."))
	# A stable lock order makes simultaneous merges safe.
	for name in sorted([source, target]):
		frappe.db.get_value("Test Log", name, "name", for_update=True)
	duplicate, original = frappe.get_doc("Test Log", source), frappe.get_doc("Test Log", target)
	for doc in (duplicate, original):
		doc.check_permission("write")
	if duplicate.merged_into == target:
		return target
	if duplicate.merged_into or original.duplicate_of or original.merged_into:
		frappe.throw(_("Merge directly into an original log that has not been merged."))
	if original.product != duplicate.product:
		frappe.throw(_("Duplicates must belong to the same product."))
	from test_log.evidence import readable_file

	mapping = {}
	for row in duplicate.attachments:
		if row.file_url:
			file = readable_file(row.file_url, duplicate, throw=True)
			frappe.get_doc(
				{
					"doctype": "File",
					"file_url": file.file_url,
					"file_name": file.file_name,
					"is_private": file.is_private,
					"attached_to_doctype": "Test Log",
					"attached_to_name": original.name,
				}
			).insert(ignore_permissions=True)
		new_row = original.append(
			"attachments",
			{key: row.get(key) for key in ("attachment_type", "file_url", "external_link", "caption")},
		)
		mapping[row.name] = new_row
	original.save()
	for old_name, new_row in mapping.items():
		frappe.db.set_value(
			"Test Evidence Comment",
			{"test_log": source, "evidence_row": old_name},
			{"test_log": target, "evidence_row": new_row.name},
		)
	frappe.db.set_value(
		"Comment",
		{"reference_doctype": "Test Log", "reference_name": source, "comment_type": "Comment"},
		"reference_name",
		target,
	)
	duplicate.attachments = []
	duplicate.duplicate_of = duplicate.merged_into = target
	duplicate.status = "Won't Fix"
	duplicate.flags.ignore_status_flow = True
	duplicate.save()
	original.add_comment(
		"Comment", _("Merged duplicate {0}, including its evidence and comments.").format(source)
	)
	return target
