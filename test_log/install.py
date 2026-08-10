# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe

ROLES = (
	("Tester", "Creates test runs and logs findings with evidence."),
	("Developer", "Picks up assigned test logs and updates their status."),
)

NUMBER_CARDS = (
	("Open Test Logs", ["Open", "Reopened"], "red"),
	("Ongoing Test Logs", ["Ongoing"], "blue"),
	("Fixed Test Logs", ["Fixed"], "purple"),
	("Completed Test Logs", ["Completed"], "green"),
)


def before_install():
	"""Roles must exist before the DocType JSONs that reference them are synced."""
	for role_name, description in ROLES:
		if frappe.db.exists("Role", role_name):
			continue

		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"description": description,
			}
		).insert(ignore_permissions=True)


def after_install():
	create_number_cards()
	create_dashboard_chart()
	setup_tester_mode()
	frappe.db.commit()


def setup_tester_mode():
	"""Turn the capture widget on for testers the moment the app lands on a site.

	Only ever writes when the settings have never been saved — an admin who switched
	tester mode off keeps it off across upgrades.
	"""
	if frappe.db.get_singles_dict("Test Log Settings"):
		return

	settings = frappe.get_single("Test Log Settings")
	settings.enable_tester_mode = 1

	for role_name in ("Tester", "System Manager"):
		settings.append("allowed_roles", {"role": role_name})

	settings.save(ignore_permissions=True)


def create_number_cards():
	for label, statuses, colour in NUMBER_CARDS:
		if frappe.db.exists("Number Card", label):
			continue

		frappe.get_doc(
			{
				"doctype": "Number Card",
				"name": label,
				"label": label,
				"type": "Document Type",
				"document_type": "Test Log",
				"function": "Count",
				"filters_json": frappe.as_json([["Test Log", "status", "in", statuses, False]]),
				"is_public": 1,
				"show_percentage_stats": 1,
				"stats_time_interval": "Weekly",
				"color": colour,
			}
		).insert(ignore_permissions=True)


def create_dashboard_chart():
	if frappe.db.exists("Dashboard Chart", "Test Logs by Status"):
		return

	frappe.get_doc(
		{
			"doctype": "Dashboard Chart",
			"name": "Test Logs by Status",
			"chart_name": "Test Logs by Status",
			"chart_type": "Group By",
			"group_by_type": "Count",
			"group_by_based_on": "status",
			"document_type": "Test Log",
			"type": "Donut",
			"is_public": 1,
			"timeseries": 0,
			"filters_json": "[]",
			"number_of_groups": 0,
		}
	).insert(ignore_permissions=True)
