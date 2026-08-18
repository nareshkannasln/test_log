// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

frappe.query_reports["Test Run Summary"] = {
	filters: [
		{ fieldname: "test_run", label: __("Test Run"), fieldtype: "Link", options: "Test Run" },
		{ fieldname: "product", label: __("Product"), fieldtype: "Link", options: "Test Product" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...(frappe.boot.test_log_vocabulary?.statuses || [])],
		},
		{
			fieldname: "severity",
			label: __("Severity"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Critical"],
		},
		{ fieldname: "tester", label: __("Tester"), fieldtype: "Link", options: "User" },
		{
			fieldname: "assigned_developer",
			label: __("Developer"),
			fieldtype: "Link",
			options: "User",
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Datetime" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Datetime" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "status" && data) {
			const colors = frappe.boot.test_log_vocabulary?.status_colors || {};
			return `<span class="indicator-pill ${colors[data.status] || "gray"}">${__(
				data.status
			)}</span>`;
		}

		if (
			column.fieldname === "severity" &&
			data &&
			["High", "Critical"].includes(data.severity)
		) {
			return `<span style="color: var(--red-500); font-weight: 600">${value}</span>`;
		}

		return value;
	},
};
