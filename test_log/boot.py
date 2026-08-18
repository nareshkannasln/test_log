# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Ships the tester widget's configuration with the desk boot.

Sending it here rather than over a request means the widget can draw itself on the
very first paint, and — more importantly — that a tester who loses the connection
still has everything the panel needs already in the page.
"""

import frappe

from test_log.constants import vocabulary
from test_log.test_log.doctype.test_log_settings.test_log_settings import widget_config


def boot_session(bootinfo):
	if frappe.session.user in ("Guest", ""):
		return

	# The form and list views need the status flow whether or not the capture widget
	# is switched on, and it is a handful of constants — cheap to always send, and it
	# keeps the buttons the desk offers in step with what the server will accept.
	bootinfo.test_log_vocabulary = vocabulary()

	try:
		bootinfo.test_log = widget_config()
	except Exception:
		# A half-migrated site must still be able to log in — but a silently missing
		# capture button is hard to chase, so leave a trail in the Error Log.
		bootinfo.test_log = {"enabled": False}

		try:
			frappe.log_error(title="Test Log: capture widget could not start")
		except Exception:
			pass
