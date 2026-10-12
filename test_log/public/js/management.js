frappe.provide("test_log.management");
window.test_log.management.can_test = () =>
	frappe.session.user === "Administrator" ||
	["Tester", "System Manager"].some((role) => frappe.user_roles.includes(role));
window.test_log.management.verify_build = () =>
	frappe.prompt(
		[
			{
				fieldname: "product",
				fieldtype: "Link",
				options: "Test Product",
				label: __("Product"),
				reqd: 1,
			},
			{ fieldname: "build", fieldtype: "Data", label: __("Fixed in Build"), reqd: 1 },
		],
		(values) =>
			frappe.call({
				method: "window.test_log.management.verify_build",
				args: values,
				freeze: true,
				callback(r) {
					frappe.msgprint(
						r.message?.queued
							? __("Queued. You will be notified when it finishes.")
							: __("{0} verified, {1} skipped", [
									r.message?.updated?.length || 0,
									r.message?.skipped?.length || 0,
							  ])
					);
					window.cur_list?.refresh();
				},
			}),
		__("Verify all in this build")
	);
