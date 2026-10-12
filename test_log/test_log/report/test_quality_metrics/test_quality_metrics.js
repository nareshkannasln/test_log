frappe.query_reports["Test Quality Metrics"] = {
	filters: [
		{ fieldname: "product", label: __("Product"), fieldtype: "Link", options: "Test Product" },
		{
			fieldname: "metric",
			label: __("Metric"),
			fieldtype: "Select",
			default: "open",
			options: [
				{ value: "open", label: __("Open Logs by Developer") },
				{ value: "fix_time", label: __("Mean Fix Time by Severity") },
				{ value: "reopen", label: __("Reopen Rate by Developer and Product") },
				{ value: "build", label: __("Defects by Build") },
			],
		},
	],
};
