// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"];
const VIDEO_EXTENSIONS = ["mp4", "webm", "mov", "m4v", "ogv"];

frappe.ui.form.on("Test Log", {
	refresh(frm) {
		frm.trigger("render_evidence");
		frm.trigger("add_status_actions");
		frm.trigger("add_share_action");

		if (frm.doc.assigned_developer && !frm.is_new()) {
			frm.dashboard.add_indicator(
				__("Assigned to {0}", [frm.doc.assigned_developer]),
				"blue"
			);
		}
	},

	attachments(frm) {
		frm.trigger("render_evidence");
	},

	add_status_actions(frm) {
		if (frm.is_new()) return;

		const transitions = {
			Open: ["Ongoing", "Won't Fix"],
			Reopened: ["Ongoing", "Won't Fix"],
			Ongoing: ["Fixed", "Won't Fix"],
			Fixed: ["Completed", "Reopened"],
			Completed: ["Reopened"],
			"Won't Fix": ["Reopened"],
		};

		(transitions[frm.doc.status] || []).forEach((status) => {
			frm.add_custom_button(
				__("Mark {0}", [__(status)]),
				() => update_status(frm, status),
				__("Status")
			);
		});

		frm.page.set_inner_btn_group_as_primary(__("Status"));
	},

	add_share_action(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			__("Word Report"),
			() =>
				frappe.call({
					method: "test_log.api.build_log_report",
					args: { test_log: frm.doc.name },
					freeze: true,
					freeze_message: __("Building the report..."),
					callback(r) {
						if (!r.message?.file_url) return;
						frm.reload_doc();
						window.open(r.message.file_url, "_blank", "noopener");
					},
				}),
			__("Actions")
		);

		frm.add_custom_button(
			__("Share with Developer"),
			() => {
				const dialog = new frappe.ui.Dialog({
					title: __("Share this test log"),
					fields: [
						{
							fieldname: "developer",
							fieldtype: "Link",
							options: "User",
							label: __("Developer"),
							reqd: 1,
							default: frm.doc.assigned_developer,
						},
						{
							fieldname: "note",
							fieldtype: "Small Text",
							label: __("Note for the developer"),
						},
					],
					primary_action_label: __("Share & Assign"),
					primary_action(values) {
						dialog.hide();
						frm.set_value("assigned_developer", values.developer);
						if (values.note) {
							frm.set_value(
								"resolution",
								`${frm.doc.resolution || ""}<p>${frappe.utils.escape_html(values.note)}</p>`
							);
						}
						frm.save();
					},
				});
				dialog.show();
			},
			__("Actions")
		);
	},

	render_evidence(frm) {
		const wrapper = frm.get_field("attachment_preview").$wrapper;
		wrapper.empty();

		const rows = (frm.doc.attachments || []).filter((row) => row.file_url || row.external_link);
		if (!rows.length) {
			wrapper.html(
				`<div class="text-muted small">${__(
					"Add screenshots or screen recordings above — they will preview here."
				)}</div>`
			);
			return;
		}

		const container = $('<div class="test-log-evidence"></div>').appendTo(wrapper);
		rows.forEach((row) => container.append(build_evidence_card(row)));

		wrapper.append(`
			<style>
				.test-log-evidence {
					display: grid;
					grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
					gap: var(--margin-md, 12px);
				}
				.test-log-evidence .evidence-card {
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					overflow: hidden;
					background: var(--card-bg, var(--fg-color));
				}
				.test-log-evidence .evidence-card img,
				.test-log-evidence .evidence-card video {
					width: 100%;
					max-height: 220px;
					object-fit: contain;
					background: var(--bg-color);
					display: block;
				}
				.test-log-evidence .evidence-meta {
					padding: 8px 10px;
					font-size: var(--text-sm, 12px);
					display: flex;
					flex-direction: column;
					gap: 2px;
				}
				.test-log-evidence .evidence-meta a { word-break: break-all; }
			</style>
		`);
	},
});

function build_evidence_card(row) {
	const url = row.file_url || row.external_link;
	const extension = (url.split("?")[0].split(".").pop() || "").toLowerCase();
	const caption = frappe.utils.escape_html(row.caption || row.attachment_type || "");
	const safe_url = frappe.utils.escape_html(url);

	let media = "";
	if (row.file_url && IMAGE_EXTENSIONS.includes(extension)) {
		media = `<a href="${safe_url}" target="_blank"><img src="${safe_url}" loading="lazy" alt="${caption}"></a>`;
	} else if (row.file_url && VIDEO_EXTENSIONS.includes(extension)) {
		media = `<video src="${safe_url}" controls preload="metadata"></video>`;
	} else {
		media = `<div class="evidence-meta" style="padding:24px;text-align:center">${frappe.utils.icon(
			"file",
			"lg"
		)}</div>`;
	}

	return $(`
		<div class="evidence-card">
			${media}
			<div class="evidence-meta">
				<span class="text-muted">${frappe.utils.escape_html(row.attachment_type || "")}</span>
				<strong>${caption}</strong>
				<a href="${safe_url}" target="_blank">${__("Open")}</a>
			</div>
		</div>
	`);
}

function update_status(frm, status) {
	const needs_note = ["Fixed", "Won't Fix"].includes(status);

	const apply = (resolution) =>
		frappe.call({
			method: "test_log.test_log.doctype.test_log.test_log.set_status",
			args: { name: frm.doc.name, status, resolution },
			freeze: true,
			freeze_message: __("Updating status..."),
			callback: () => {
				frappe.show_alert({ message: __("Marked {0}", [__(status)]), indicator: "green" });
				frm.reload_doc();
			},
		});

	if (!needs_note) {
		apply();
		return;
	}

	frappe.prompt(
		[
			{
				fieldname: "resolution",
				fieldtype: "Text Editor",
				label: __("What changed?"),
				default: frm.doc.resolution,
			},
		],
		(values) => apply(values.resolution),
		__("Mark {0}", [__(status)]),
		__("Update")
	);
}
