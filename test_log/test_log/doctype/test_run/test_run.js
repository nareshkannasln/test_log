// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

frappe.ui.form.on("Test Run", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Add Test Log"), () => {
			frappe.new_doc("Test Log", {
				test_run: frm.doc.name,
				product: frm.doc.product,
				build_version: frm.doc.build_version,
				tester: frm.doc.tester,
			});
		});

		frm.add_custom_button(
			__("Open Test Logs"),
			() => frappe.set_route("List", "Test Log", { test_run: frm.doc.name }),
			__("View")
		);

		frm.add_custom_button(
			__("Export Sheet"),
			() =>
				frappe.set_route("query-report", "Test Run Summary", {
					test_run: frm.doc.name,
				}),
			__("View")
		);

		frm.add_custom_button(__("Word Report"), () => build_report(frm), __("View"));

		frm.add_custom_button(__("Excel Sheet"), () => build_sheet(frm), __("View"));

		frm.add_custom_button(__("Share with Developer"), () => share_dialog(frm), __("Actions"));
		frm.page.set_inner_btn_group_as_primary(__("Actions"));

		render_status_bar(frm);
	},
});

/** Builds the run's Word document — every log with its description and screenshots. */
function build_report(frm) {
	frappe.call({
		method: "test_log.api.build_run_report",
		args: { test_run: frm.doc.name },
		freeze: true,
		freeze_message: __("Building the report..."),
		callback(r) {
			if (!r.message?.file_url) return;

			frappe.show_alert({
				message: __("Report attached to this run"),
				indicator: "green",
			});
			frm.reload_doc();
			window.open(r.message.file_url, "_blank", "noopener");
		},
	});
}

/** The run's logs as a spreadsheet — one row each, description and linked evidence. */
function build_sheet(frm) {
	frappe.call({
		method: "test_log.api.build_run_sheet",
		args: { test_run: frm.doc.name },
		freeze: true,
		freeze_message: __("Building the sheet..."),
		callback(r) {
			if (!r.message?.file_url) return;

			frappe.show_alert({
				message: __("{0} logs in the sheet", [r.message.logs]),
				indicator: "green",
			});
			window.open(r.message.file_url, "_blank", "noopener");
		},
	});
}

function share_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Share this run and all its logs"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				options: "User",
				label: __("Developer"),
				reqd: 1,
			},
			{
				fieldname: "can_write",
				fieldtype: "Check",
				label: __("Allow them to edit status"),
				default: 1,
			},
			{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
		],
		primary_action_label: __("Share"),
		primary_action(values) {
			dialog.hide();
			frappe.call({
				method: "test_log.api.share_run",
				args: { test_run: frm.doc.name, ...values },
				freeze: true,
				freeze_message: __("Sharing..."),
				callback(r) {
					frappe.show_alert({
						message: __("Shared the run and {0} logs with {1}", [
							r.message.shared_logs,
							values.user,
						]),
						indicator: "green",
					});
				},
			});
		},
	});
	dialog.show();
}

function render_status_bar(frm) {
	const colors = {
		Open: "red",
		Reopened: "orange",
		Ongoing: "blue",
		Fixed: "purple",
		Completed: "green",
		"Won't Fix": "gray",
	};

	frappe.call({
		method: "test_log.api.get_run_stats",
		args: { test_run: frm.doc.name },
		callback(r) {
			const stats = r.message || {};
			frm.dashboard.clear_headline();

			if (!Object.keys(stats).length) {
				frm.dashboard.set_headline(__("No test logs in this run yet."));
				return;
			}

			Object.keys(stats).forEach((status) => {
				frm.dashboard.add_indicator(`${__(status)}: ${stats[status]}`, colors[status] || "gray");
			});
		},
	});
}
