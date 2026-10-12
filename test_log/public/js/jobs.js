// Background actions report only to the initiating user's realtime room.
$(document).on("app_ready", () => {
	frappe.realtime.on("test_log_action_complete", ({ result, error }) => {
		if (error) {
			frappe.msgprint({
				title: __("Test Log action failed"),
				message: error,
				indicator: "red",
			});
			return;
		}
		if (result?.file_url) {
			frappe.msgprint({
				title: __("Your export is ready"),
				message: `<a href="${frappe.utils.escape_html(
					result.file_url
				)}" target="_blank" rel="noopener">${frappe.utils.escape_html(
					result.file_name
				)}</a>`,
			});
		} else {
			frappe.msgprint(
				__("{0} logs updated; {1} skipped.", [
					result?.updated?.length || 0,
					result?.skipped?.length || 0,
				])
			);
			if (result?.skipped?.length) {
				frappe.msgprint(
					result.skipped
						.map(
							(row) =>
								`${frappe.utils.escape_html(row.name)}: ${frappe.utils.escape_html(
									row.reason
								)}`
						)
						.join("<br>")
				);
			}
			if (window.cur_list?.doctype === "Test Log") window.cur_list.refresh();
		}
	});
});
