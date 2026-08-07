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
	},
};

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
