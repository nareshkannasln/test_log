# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Public API surface of the app.

Split by concern — `sharing` hands a run to a developer, `capture` backs the tester
widget. Everything is re-exported here so `test_log.api.<method>` keeps working as the
call path from the desk.
"""

from test_log.api.capture import (
	create_run,
	get_config,
	get_feed,
	log_entry,
)
from test_log.api.excel import build_run_sheet, build_selection_sheet
from test_log.api.report import build_log_report, build_run_report, build_selection_report
from test_log.api.sharing import get_run_stats, share_run

__all__ = (
	"build_log_report",
	"build_run_report",
	"build_run_sheet",
	"build_selection_report",
	"build_selection_sheet",
	"create_run",
	"get_config",
	"get_feed",
	"get_run_stats",
	"log_entry",
	"share_run",
)
