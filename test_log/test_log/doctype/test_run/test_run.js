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

		if (frm.doc.status !== "Signed Off") {
			frm.add_custom_button(__("Sign Off"), () => sign_off_dialog(frm), __("Actions"));
		}

		frm.page.set_inner_btn_group_as_primary(__("Actions"));

		if (frm.doc.signed_off_by) {
			frm.dashboard.add_comment(
				__("Signed off by {0} on {1}.", [
					frappe.utils.escape_html(frm.doc.signed_off_by),
					frappe.datetime.str_to_user(frm.doc.signed_off_on),
				]),
				"green",
				true
			);
		}

		render_status_bar(frm);
	},
});

/**
 * Closing the sheet off. The run has to actually be finished — anything still Open,
 * Ongoing or Needs Info blocks it, unless the tester says in writing why it is being
 * signed off regardless.
 */
function sign_off_dialog(frm) {
	const unsettled =
		(frm.doc.open_count || 0) + (frm.doc.ongoing_count || 0) + (frm.doc.needs_info_count || 0);

	const dialog = new frappe.ui.Dialog({
		title: __("Sign off this run"),
		fields: [
			{
				fieldtype: "HTML",
				options: unsettled
					? `<div class="text-danger">${__("{0} logs are still open in this run.", [
							unsettled,
					  ])}</div>`
					: `<div class="text-muted">${__(
							"Every log in this run has been settled."
					  )}</div>`,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Sign-off notes"),
				reqd: unsettled ? 1 : 0,
				description: unsettled
					? __("Say why the run is being signed off with logs still open.")
					: "",
			},
			{
				fieldname: "force",
				fieldtype: "Check",
				label: __("Sign off anyway"),
				depends_on: unsettled ? "eval:1" : "eval:0",
				default: 0,
			},
		],
		primary_action_label: __("Sign Off"),
		primary_action(values) {
			if (unsettled && !values.force) {
				frappe.msgprint(
					__("Close the open logs first, or tick “Sign off anyway” and say why.")
				);
				return;
			}

			dialog.hide();
			frappe.call({
				method: "test_log.api.sign_off",
				args: { test_run: frm.doc.name, notes: values.notes, force: values.force ? 1 : 0 },
				freeze: true,
				freeze_message: __("Signing off..."),
				callback() {
					frappe.show_alert({ message: __("Run signed off"), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

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
	const colors = frappe.boot.test_log_vocabulary?.status_colors || {
		Open: "red",
		Reopened: "orange",
		Ongoing: "blue",
		"Needs Info": "yellow",
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
				frm.dashboard.add_indicator(
					`${__(status)}: ${stats[status]}`,
					colors[status] || "gray"
				);
			});
		},
	});
}
