// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

frappe.listview_settings["Test Log"] = {
	add_fields: ["status", "severity", "assigned_developer", "product"],

	filters: [["status", "not in", ["Completed", "Won't Fix"]]],

	get_indicator(doc) {
		const colors = {
			Open: "red",
			Reopened: "orange",
			Ongoing: "blue",
			Fixed: "purple",
			Completed: "green",
			"Won't Fix": "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},

	onload(listview) {
		["Ongoing", "Fixed", "Completed", "Won't Fix"].forEach((status) => {
			listview.page.add_actions_menu_item(
				__("Mark {0}", [__(status)]),
				() => bulk_update(listview, status),
				true
			);
		});

		listview.page.add_actions_menu_item(
			__("Word Report"),
			() => selection_report(listview),
			true
		);

		listview.page.add_actions_menu_item(
			__("Excel Sheet"),
			() => selection_sheet(listview),
			true
		);
	},
};

/** Ticked logs as a spreadsheet — one row each, description and linked evidence. */
function selection_sheet(listview) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Select the test logs you want in the sheet."));
		return;
	}

	frappe.call({
		method: "test_log.api.build_selection_sheet",
		args: { names },
		freeze: true,
		freeze_message: __("Building a sheet of {0} logs...", [names.length]),
		callback(r) {
			if (!r.message?.file_url) return;

			const skipped = r.message.skipped;
			frappe.show_alert({
				message: skipped
					? __("{0} logs in the sheet, {1} skipped — no access", [r.message.logs, skipped])
					: __("{0} logs in the sheet", [r.message.logs]),
				indicator: skipped ? "orange" : "green",
			});

			window.open(r.message.file_url, "_blank", "noopener");
		},
	});
}

/** Ticked logs, gathered into one Word document with their evidence. */
function selection_report(listview) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Select the test logs you want in the report."));
		return;
	}

	frappe.call({
		method: "test_log.api.build_selection_report",
		args: { names },
		freeze: true,
		freeze_message: __("Building a report of {0} logs...", [names.length]),
		callback(r) {
			if (!r.message?.file_url) return;

			const skipped = r.message.skipped;
			frappe.show_alert({
				message: skipped
					? __("{0} logs in the report, {1} skipped — no access", [r.message.logs, skipped])
					: __("{0} logs in the report", [r.message.logs]),
				indicator: skipped ? "orange" : "green",
			});

			window.open(r.message.file_url, "_blank", "noopener");
		},
	});
}

function bulk_update(listview, status) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Select at least one test log."));
		return;
	}

	frappe.call({
		method: "test_log.test_log.doctype.test_log.test_log.bulk_set_status",
		args: { names, status },
		freeze: true,
		freeze_message: __("Updating {0} logs...", [names.length]),
		callback(r) {
			const updated = (r.message || []).length;
			frappe.show_alert({
				message: __("{0} of {1} updated", [updated, names.length]),
				indicator: updated === names.length ? "green" : "orange",
			});
			listview.refresh();
		},
	});
}
