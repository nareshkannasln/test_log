# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Turn the new workflow guards on for sites that had the app before they existed.

A field's default only applies to a Single that has never been saved, so an existing
site would come out of the upgrade with the status flow unenforced — which is the
opposite of what the release is for. The reminders stay off: nobody asked to start
getting email.
"""

import frappe

DEFAULTS = {
	"enforce_status_flow": 1,
	"block_signed_off_runs": 1,
	"warn_on_duplicates": 1,
}


def execute():
	stored = frappe.db.get_singles_dict("Test Log Settings")
	if not stored:
		# Never saved — the field defaults will apply on first save.
		return

	for fieldname, value in DEFAULTS.items():
		if fieldname not in stored:
			frappe.db.set_single_value("Test Log Settings", fieldname, value)

	frappe.clear_document_cache("Test Log Settings", "Test Log Settings")
