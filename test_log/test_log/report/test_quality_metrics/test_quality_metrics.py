from frappe import _

from test_log.analytics import quality_rows


def execute(filters=None):
	filters = filters or {}
	rows = quality_rows(filters.get("metric", "open"), filters.get("product"))
	columns = [
		{"fieldname": "group", "label": _("Group"), "fieldtype": "Data", "width": 350},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Float", "width": 140},
		{"fieldname": "sample_size", "label": _("Sample Size"), "fieldtype": "Int", "width": 140},
	]
	chart = {
		"type": "bar",
		"data": {
			"labels": [r["group"] for r in rows[:20]],
			"datasets": [{"name": _("Value"), "values": [r["value"] for r in rows[:20]]}],
		},
	}
	return (
		columns,
		rows,
		_(
			"Fix time is calendar days to first resolution. Reopen rate is the percent of resolved logs ever reopened."
		),
		chart,
	)
