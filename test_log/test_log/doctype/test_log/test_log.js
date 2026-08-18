// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"];
const VIDEO_EXTENSIONS = ["mp4", "webm", "mov", "m4v", "ogv"];

// Only reached on a page that booted before the app was migrated; the live copy comes
// from test_log/constants.py through the boot info.
const FALLBACK_TRANSITIONS = {
	Open: ["Ongoing", "Needs Info", "Won't Fix"],
	Reopened: ["Ongoing", "Needs Info", "Won't Fix"],
	Ongoing: ["Fixed", "Needs Info", "Won't Fix"],
	"Needs Info": ["Open", "Ongoing", "Won't Fix"],
	Fixed: ["Completed", "Reopened"],
	Completed: ["Reopened"],
	"Won't Fix": ["Reopened"],
};

// A status change that is really a question or an explanation, and what to ask for.
const STATUS_PROMPTS = {
	Fixed: { field: "resolution", label: __("What changed?") },
	"Won't Fix": { field: "resolution", label: __("Why is this being left?") },
	"Needs Info": { field: "note", label: __("What do you need to know?") },
	Reopened: { field: "note", label: __("What is still wrong?") },
};

frappe.ui.form.on("Test Log", {
	refresh(frm) {
		frm.trigger("render_evidence");
		frm.trigger("add_status_actions");
		frm.trigger("add_share_action");
		frm.trigger("show_similar");

		if (frm.doc.assigned_developer && !frm.is_new()) {
			frm.dashboard.add_indicator(
				__("Assigned to {0}", [frm.doc.assigned_developer]),
				"blue"
			);
		}

		if (frm.doc.verified_by) {
			frm.dashboard.add_indicator(__("Verified by {0}", [frm.doc.verified_by]), "green");
		}

		if (frm.doc.duplicate_of) {
			frm.dashboard.add_comment(
				__("Marked as a duplicate of {0}.", [
					`<a href="/app/test-log/${encodeURIComponent(
						frm.doc.duplicate_of
					)}">${frappe.utils.escape_html(frm.doc.duplicate_of)}</a>`,
				]),
				"blue",
				true
			);
		}
	},

	attachments(frm) {
		frm.trigger("render_evidence");
	},

	add_status_actions(frm) {
		if (frm.is_new()) return;

		// The same map the server validates against, shipped with the boot info — so a
		// button is never offered for a move that will be refused on save.
		const transitions =
			frappe.boot.test_log_vocabulary?.status_transitions || FALLBACK_TRANSITIONS;

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
								`${frm.doc.resolution || ""}<p>${frappe.utils.escape_html(
									values.note
								)}</p>`
							);
						}
						frm.save();
					},
				});
				dialog.show();
			},
			__("Actions")
		);

		frm.add_custom_button(__("Add Note"), () => add_note(frm), __("Actions"));

		// The product's repository, if one is recorded — saves hunting for it when a
		// developer picks the log up.
		if (frm.doc.product) {
			frappe.db.get_value("Test Product", frm.doc.product, "repository_url").then((r) => {
				const url = r?.message?.repository_url;
				if (!url) return;

				frm.add_custom_button(
					__("Open Repository"),
					() => window.open(url, "_blank", "noopener"),
					__("Actions")
				);
			});
		}
	},

	/** Logs that look like this one — the same finding filed twice is the usual mess. */
	show_similar(frm) {
		if (frm.is_new() || frm.doc.duplicate_of) return;

		frappe.call({
			method: "test_log.api.find_similar",
			args: {
				subject: frm.doc.subject,
				test_run: frm.doc.test_run,
				product: frm.doc.product,
				module_feature: frm.doc.module_feature,
				page_route: frm.doc.page_route,
				exclude: frm.doc.name,
			},
			callback(r) {
				const similar = r.message || [];
				if (!similar.length) return;

				const links = similar
					.map(
						(log) =>
							`<a href="/app/test-log/${encodeURIComponent(
								log.name
							)}">${frappe.utils.escape_html(
								log.name
							)}</a> — ${frappe.utils.escape_html(log.subject || "")} (${__(
								log.status
							)})`
					)
					.join("<br>");

				frm.dashboard.add_comment(
					`<b>${__("Possible duplicates")}</b><br>${links}`,
					"yellow",
					true
				);

				frm.add_custom_button(
					__("Mark as Duplicate"),
					() => mark_duplicate(frm, similar),
					__("Actions")
				);
			},
		});
	},

	render_evidence(frm) {
		const wrapper = frm.get_field("attachment_preview").$wrapper;
		wrapper.empty();

		const rows = (frm.doc.attachments || []).filter(
			(row) => row.file_url || row.external_link
		);
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
	const ask = STATUS_PROMPTS[status];

	const apply = (values = {}) =>
		frappe.call({
			method: "test_log.test_log.doctype.test_log.test_log.set_status",
			args: {
				name: frm.doc.name,
				status,
				resolution: values.resolution,
				note: values.note,
			},
			freeze: true,
			freeze_message: __("Updating status..."),
			callback: () => {
				frappe.show_alert({ message: __("Marked {0}", [__(status)]), indicator: "green" });
				frm.reload_doc();
			},
		});

	if (!ask) {
		apply();
		return;
	}

	// A note goes to the timeline and notifies the other party; a resolution is the
	// developer's summary and stays on the record.
	frappe.prompt(
		[
			{
				fieldname: ask.field,
				fieldtype: ask.field === "resolution" ? "Text Editor" : "Small Text",
				label: ask.label,
				default: ask.field === "resolution" ? frm.doc.resolution : "",
				reqd: ask.field === "note" ? 1 : 0,
			},
		],
		(values) => apply(values),
		__("Mark {0}", [__(status)]),
		__("Update")
	);
}

/** A comment on the log that reaches the person on the other side of it. */
function add_note(frm) {
	frappe.prompt(
		[{ fieldname: "note", fieldtype: "Small Text", label: __("Note"), reqd: 1 }],
		(values) =>
			frappe.call({
				method: "test_log.api.add_note",
				args: { name: frm.doc.name, note: values.note },
				callback: () => {
					frappe.show_alert({ message: __("Note added"), indicator: "green" });
					frm.reload_doc();
				},
			}),
		__("Add a note"),
		__("Post")
	);
}

/** Point this log at the one it repeats, so the run is not counted twice. */
function mark_duplicate(frm, similar) {
	frappe.prompt(
		[
			{
				fieldname: "duplicate_of",
				fieldtype: "Link",
				options: "Test Log",
				label: __("Duplicate of"),
				reqd: 1,
				default: similar[0]?.name,
				get_query: () => ({ filters: { name: ["!=", frm.doc.name] } }),
			},
		],
		(values) => {
			frm.set_value("duplicate_of", values.duplicate_of);
			frm.save();
		},
		__("Mark as duplicate"),
		__("Mark")
	);
}
