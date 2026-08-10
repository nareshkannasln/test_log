// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

frappe.ui.form.on("Test Log Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open Capture Panel"), () => {
			if (window.test_log?.widget?.open) {
				window.test_log.widget.open();
			} else {
				frappe.msgprint(
					__("Enable tester mode and reload the page to use the capture panel.")
				);
			}
		});

		frm.dashboard.clear_headline();
		if (!frm.doc.enable_tester_mode) {
			frm.dashboard.set_headline(
				__("Tester mode is off — no capture button is shown to anyone.")
			);
		}
	},

	enable_tester_mode(frm) {
		if (frm.doc.enable_tester_mode && !(frm.doc.allowed_roles || []).length) {
			frm.set_value("allowed_roles", [{ role: "Tester" }]);
		}
	},
});
