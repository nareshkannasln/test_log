frappe.query_reports["Test Build Comparison"] = {
	filters: [
		{
			fieldname: "product",
			label: __("Product"),
			fieldtype: "Link",
			options: "Test Product",
			reqd: 1,
		},
		{ fieldname: "from_build", label: __("Baseline Build"), fieldtype: "Data", reqd: 1 },
		{ fieldname: "to_build", label: __("Comparison Build"), fieldtype: "Data", reqd: 1 },
	],
};
