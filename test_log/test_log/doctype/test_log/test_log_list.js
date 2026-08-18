// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

const STATUS_COLORS = {
	Open: "red",
	Reopened: "orange",
	Ongoing: "blue",
	"Needs Info": "yellow",
	Fixed: "purple",
	Completed: "green",
	"Won't Fix": "gray",
};

// Set on many logs at once. Status is not here — it moves through set_status so the
// flow rules still apply.
const BULK_FIELDS = [
	{
		fieldname: "assigned_developer",
		label: __("Assign Developer"),
		fieldtype: "Link",
		options: "User",
	},
	{ fieldname: "test_run", label: __("Move to Run"), fieldtype: "Link", options: "Test Run" },
	{
		fieldname: "severity",
		label: __("Set Severity"),
		fieldtype: "Select",
		options: "Low\nMedium\nHigh\nCritical",
	},
	{ fieldname: "target_date", label: __("Set Target Date"), fieldtype: "Date" },
];

frappe.listview_settings["Test Log"] = {
	add_fields: ["status", "severity", "assigned_developer", "product", "duplicate_of"],

	filters: [["status", "not in", ["Completed", "Won't Fix"]]],

	get_indicator(doc) {
		return [__(doc.status), STATUS_COLORS[doc.status] || "gray", `status,=,${doc.status}`];
	},

	onload(listview) {
		const statuses = frappe.boot.test_log_vocabulary?.statuses || Object.keys(STATUS_COLORS);

		statuses
			.filter((status) => status !== "Open")
			.forEach((status) => {
				listview.page.add_actions_menu_item(
					__("Mark {0}", [__(status)]),
					() => bulk_update(listview, status),
					true
				);
			});

		BULK_FIELDS.forEach((field) => {
			listview.page.add_actions_menu_item(
				field.label,
				() => bulk_field(listview, field),
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
					? __("{0} logs in the sheet, {1} skipped — no access", [
							r.message.logs,
							skipped,
					  ])
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
					? __("{0} logs in the report, {1} skipped — no access", [
							r.message.logs,
							skipped,
					  ])
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
		method: "test_log.api.bulk_set_status",
		args: { names, status },
		freeze: true,
		freeze_message: __("Updating {0} logs...", [names.length]),
		callback(r) {
			report_result(listview, r.message, names.length);
		},
	});
}

/** Assign a developer, move to another run, change severity — on everything ticked. */
function bulk_field(listview, field) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Select at least one test log."));
		return;
	}

	frappe.prompt(
		[{ ...field, label: field.label, reqd: field.fieldtype !== "Date" }],
		(values) =>
			frappe.call({
				method: "test_log.api.bulk_update_field",
				args: { names, fieldname: field.fieldname, value: values[field.fieldname] },
				freeze: true,
				freeze_message: __("Updating {0} logs...", [names.length]),
				callback(r) {
					report_result(listview, r.message, names.length);
				},
			}),
		field.label,
		__("Apply")
	);
}

/**
 * Say what actually happened. A log the user cannot write, or one the status flow
 * refuses to move, used to disappear from the count with no explanation.
 */
function report_result(listview, result, requested) {
	const updated = result?.updated?.length || 0;
	const skipped = result?.skipped || [];

	frappe.show_alert({
		message: __("{0} of {1} updated", [updated, requested]),
		indicator: skipped.length ? "orange" : "green",
	});

	if (skipped.length) {
		const rows = skipped
			.map(
				(row) =>
					`<li><b>${frappe.utils.escape_html(row.name)}</b> — ${frappe.utils.escape_html(
						row.reason
					)}</li>`
			)
			.join("");

		frappe.msgprint({
			title: __("{0} were left alone", [skipped.length]),
			indicator: "orange",
			message: `<ul>${rows}</ul>`,
		});
	}

	listview.refresh();
}
