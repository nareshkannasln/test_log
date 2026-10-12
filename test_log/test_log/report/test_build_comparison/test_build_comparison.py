from frappe import _

from test_log.analytics import compare_builds


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": key, "label": _(label), "fieldtype": kind, "options": options, "width": width}
		for key, label, kind, options, width in [
			("category", "Category", "Data", None, 130),
			("test_log", "Test Log", "Link", "Test Log", 170),
			("test_case", "Test Case", "Link", "Test Case", 150),
			("title", "Finding", "Data", None, 300),
			("before", "Baseline", "Data", None, 130),
			("after", "Comparison", "Data", None, 130),
		]
	]
	return (
		columns,
		compare_builds(filters.get("product"), filters.get("from_build"), filters.get("to_build")),
		_(
			"Defects use current status and recorded fixed build. Case regressions compare the latest accessible run for each build."
		),
	)
