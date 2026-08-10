// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * The capture panel — a drawer that slides in over the right edge of whatever page
 * the tester is on.
 *
 * It reads like a conversation because that is how testing actually goes: capture,
 * say what went wrong, send, carry on. Each sent entry becomes one Test Log in the
 * sheet, and the feed above the composer shows what has been filed so far, including
 * anything still waiting for the connection to come back.
 *
 * The drawer deliberately has no backdrop — the page behind it stays clickable,
 * because the tester is still testing it.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.createPanel) return;

	const { el, icon, uuid, bytes, debounce, timeAgo, t } = NS.util;

	const MIN_WIDTH = 320;
	const MAX_WIDTH = 720;
	const WIDTH_KEY = "test_log:panel_width";

	function createPanel({ config, handlers }) {
		const tools = config.tools || {};
		const vocabulary = config.vocabulary || {};
		const defaults = config.defaults || {};

		let attachments = [];
		let feed = [];
		let queue = [];
		let recording = null;
		let open = false;
		const previews = new Map();

		// ------------------------------------------------------------------ shell

		const runSelect = el("select", { class: "tl-select tl-run", onchange: onRunChange });
		const feedList = el("div", { class: "tl-feed" });
		const netStrip = el("div", { class: "tl-net", hidden: true });
		const thumbs = el("div", { class: "tl-thumbs", hidden: true });
		const recordBar = el("div", { class: "tl-recording", hidden: true });

		const textarea = el("textarea", {
			class: "tl-text",
			rows: 3,
			placeholder: t("What happened? Paste a screenshot here, or use the tools below."),
			onpaste: onPaste,
			onkeydown: onComposerKey,
			oninput: () => {
				autoGrow();
				saveDraft();
			},
		});

		const subjectInput = detailField("subject", t("Subject"), "input");
		const moduleInput = detailField("module_feature", t("Module / feature"), "input");
		const stepsInput = detailField("steps_to_reproduce", t("Steps to reproduce"), "textarea");
		const expectedInput = detailField("expected_result", t("Expected result"), "textarea");

		const severitySelect = el(
			"select",
			{ class: "tl-select", title: t("Severity"), onchange: () => saveDraft() },
			(vocabulary.severities || ["Low", "Medium", "High", "Critical"]).map((value) =>
				el("option", { value, selected: value === (defaults.severity || "Medium") }, t(value))
			)
		);

		const typeSelect = el(
			"select",
			{ class: "tl-select", title: t("Test type"), onchange: () => saveDraft() },
			(vocabulary.test_types || ["Functional"]).map((value) =>
				el("option", { value, selected: value === (defaults.test_type || "Functional") }, t(value))
			)
		);

		// Handing the finding straight to a developer: saving with one set shares the log
		// with them, assigns it, and notifies them — the same path the form uses.
		const developerSelect = el(
			"select",
			{ class: "tl-input", title: t("Assign to a developer"), onchange: () => saveDraft() },
			[
				el("option", { value: "" }, t("Route by product default")),
				...(config.developers || []).map((row) =>
					el("option", { value: row.name }, row.full_name || row.name)
				),
			]
		);

		const developerField = el("label", { class: "tl-field" }, [
			el("span", { text: t("Assign to developer") }),
			developerSelect,
		]);

		const details = el("div", { class: "tl-details", hidden: true }, [
			subjectInput.wrapper,
			moduleInput.wrapper,
			developerField,
			stepsInput.wrapper,
			expectedInput.wrapper,
		]);

		const detailsToggle = el(
			"button",
			{
				type: "button",
				class: "tl-btn tl-btn-ghost",
				title: t("More fields"),
				onclick: () => {
					details.hidden = !details.hidden;
					detailsToggle.classList.toggle("is-active", !details.hidden);
					if (!details.hidden && !subjectInput.field.value) {
						moduleInput.field.value = moduleInput.field.value || NS.context.module();
					}
				},
			},
			t("Details")
		);

		const submitButton = el(
			"button",
			{ type: "submit", class: "tl-btn tl-btn-primary tl-send", title: t("Log this entry") },
			[icon("send"), el("span", { text: t("Log entry") })]
		);

		const fileInput = el("input", {
			type: "file",
			multiple: true,
			hidden: true,
			onchange: (event) => {
				addItems(NS.capture.fromFiles(event.target.files));
				event.target.value = "";
			},
		});

		// Screen capture is a browser privilege, not a setting — if it is unavailable, say so
		// once, up front, instead of letting every click fail with a toast.
		const captureBlocked = NS.capture.unavailableReason();
		const recordBlocked = NS.capture.recordingUnavailableReason();

		const captureNote = el("div", {
			class: "tl-note",
			hidden: !captureBlocked,
			text: captureBlocked
				? `${captureBlocked} ${t("Pasting a screenshot from your own snipping tool still works.")}`
				: "",
		});

		const toolRow = el("div", { class: "tl-tools" }, [
			toolButton("camera", t("Screenshot"), takeScreenshot, tools.screenshot !== false, captureBlocked),
			toolButton("scissors", t("Snip & annotate"), snip, tools.snip !== false, captureBlocked),
			toolButton("record", t("Record screen"), startRecording, tools.recording !== false, recordBlocked),
			toolButton("paperclip", t("Attach a file"), () => fileInput.click(), tools.attach !== false),
			el("span", { class: "tl-spacer" }),
			severitySelect,
			detailsToggle,
			submitButton,
		]);

		const composer = el("form", { class: "tl-composer", onsubmit: onSubmit, onkeydown: guardEnter }, [
			recordBar,
			thumbs,
			textarea,
			details,
			el("div", { class: "tl-meta-row" }, [
				el("label", { class: "tl-inline-label", text: t("Type") }),
				typeSelect,
			]),
			captureNote,
			toolRow,
			fileInput,
		]);

		const newRunForm = buildNewRunForm();

		const header = el("header", { class: "tl-head" }, [
			el("div", { class: "tl-head-title" }, [icon("bug", 18), el("strong", { text: t("Test Log") })]),
			el("div", { class: "tl-head-actions" }, [
				runSelect,
				iconButton("document", t("Word report for this run"), buildReport),
				iconButton("refresh", t("Refresh feed"), () => handlers.refreshFeed?.()),
				iconButton("close", t("Close"), close),
			]),
		]);

		const grip = el("div", { class: "tl-grip", title: t("Drag to resize") }, icon("grip", 14));

		const root = el("aside", { class: "tl-panel", hidden: true, "aria-label": t("Test Log capture") }, [
			grip,
			header,
			netStrip,
			newRunForm.wrapper,
			feedList,
			composer,
		]);

		root.style.width = `${clampWidth(Number(localStorage.getItem(WIDTH_KEY)) || 400)}px`;
		enableResize();

		// ------------------------------------------------------------------ small builders

		function toolButton(iconName, label, action, enabled, blockedReason) {
			const button = el(
				"button",
				{
					type: "button",
					class: "tl-btn tl-btn-icon",
					title: blockedReason ? `${label} — ${blockedReason}` : label,
					"aria-label": label,
					onclick: action,
				},
				icon(iconName, 17)
			);

			if (!enabled) button.hidden = true;
			if (blockedReason) button.disabled = true;

			return button;
		}

		function iconButton(iconName, label, action) {
			return el(
				"button",
				{ type: "button", class: "tl-btn tl-btn-ghost tl-btn-icon", title: label, "aria-label": label, onclick: action },
				icon(iconName, 16)
			);
		}

		function detailField(name, label, kind) {
			const field = el(kind === "textarea" ? "textarea" : "input", {
				class: "tl-input",
				rows: kind === "textarea" ? 2 : null,
				placeholder: label,
				oninput: () => saveDraft(),
			});
			return { field, wrapper: el("label", { class: "tl-field" }, [el("span", { text: label }), field]) };
		}

		function buildNewRunForm() {
			const title = el("input", { class: "tl-input", placeholder: t("New run title") });
			const product = el(
				"select",
				{ class: "tl-select" },
				(config.products || []).map((row) => el("option", { value: row.name }, row.product_name || row.name))
			);

			const wrapper = el("div", { class: "tl-newrun", hidden: true }, [
				title,
				product,
				el(
					"button",
					{
						type: "button",
						class: "tl-btn tl-btn-primary",
						onclick: async () => {
							if (!title.value.trim()) return;

							const run = await handlers.createRun?.({
								title: title.value.trim(),
								product: product.value,
							});
							if (run) {
								addRun(run);
								runSelect.value = run.name;
								onRunChange();
							}
							title.value = "";
							wrapper.hidden = true;
						},
					},
					t("Create")
				),
				el("button", { type: "button", class: "tl-btn", onclick: () => (wrapper.hidden = true) }, t("Cancel")),
			]);

			return { wrapper, title };
		}

		// ------------------------------------------------------------------ run selector

		function fillRuns() {
			runSelect.replaceChildren(
				el("option", { value: "" }, t("No run — file loose")),
				...(config.runs || []).map((run) =>
					el("option", { value: run.name }, `${run.title || run.name}`)
				),
				el("option", { value: "__new__" }, t("＋ New run…"))
			);

			const remembered = localStorage.getItem("test_log:run") || defaults.test_run || "";
			if (remembered && (config.runs || []).some((run) => run.name === remembered)) {
				runSelect.value = remembered;
			}
		}

		function addRun(run) {
			config.runs = [run, ...(config.runs || []).filter((row) => row.name !== run.name)];
			fillRuns();
		}

		function onRunChange() {
			if (runSelect.value === "__new__") {
				runSelect.value = localStorage.getItem("test_log:run") || "";
				newRunForm.wrapper.hidden = false;
				newRunForm.title.focus();
				return;
			}

			localStorage.setItem("test_log:run", runSelect.value);
			handlers.refreshFeed?.();
		}

		function currentRun() {
			return runSelect.value && runSelect.value !== "__new__" ? runSelect.value : null;
		}

		function runProduct() {
			const run = (config.runs || []).find((row) => row.name === currentRun());
			return run?.product || defaults.product || null;
		}

		// ------------------------------------------------------------------ attachments

		function previewUrl(item) {
			if (!previews.has(item.id)) previews.set(item.id, URL.createObjectURL(item.blob));
			return previews.get(item.id);
		}

		function addItems(items) {
			const limit = (tools.max_attachment_mb || 50) * 1024 * 1024;
			const kept = [];

			items.forEach((item) => {
				if (!item.size) {
					notify(t("That capture is empty, so it was not attached."), "warn");
					return;
				}
				if (limit && item.size > limit) {
					notify(t("That file is larger than the allowed size.") + ` (${bytes(item.size)})`, "warn");
					return;
				}
				kept.push(item);
			});

			if (!kept.length) return;

			attachments = attachments.concat(kept);
			renderThumbs();
			saveDraft();
			textarea.focus();
		}

		function removeItem(id) {
			const url = previews.get(id);
			if (url) {
				URL.revokeObjectURL(url);
				previews.delete(id);
			}
			attachments = attachments.filter((item) => item.id !== id);
			renderThumbs();
			saveDraft();
		}

		function renderThumbs() {
			thumbs.replaceChildren(
				...attachments.map((item) => {
					const media =
						item.kind === "image"
							? el("img", { src: previewUrl(item), alt: item.file_name })
							: item.kind === "video"
							? el("video", { src: previewUrl(item), muted: true, playsinline: true })
							: el("div", { class: "tl-thumb-file" }, icon("paperclip", 18));

					const actions = el("div", { class: "tl-thumb-actions" }, [
						item.kind === "image" && tools.snip !== false
							? el(
									"button",
									{ type: "button", title: t("Snip & annotate"), onclick: () => editItem(item) },
									icon("scissors", 13)
							  )
							: null,
						el(
							"button",
							{ type: "button", title: t("Remove"), onclick: () => removeItem(item.id) },
							icon("close", 13)
						),
					]);

					const caption = el("input", {
						class: "tl-thumb-caption",
						placeholder: t("Caption"),
						value: item.caption || "",
						oninput: (event) => {
							item.caption = event.target.value;
							saveDraft();
						},
					});

					return el("div", { class: "tl-thumb", title: `${item.file_name} · ${bytes(item.size)}` }, [
						media,
						actions,
						caption,
					]);
				})
			);

			thumbs.hidden = !attachments.length;
		}

		async function editItem(item) {
			const edited = await NS.annotate.open(item, { startWith: "box" });
			if (!edited) return;

			const url = previews.get(item.id);
			if (url) {
				URL.revokeObjectURL(url);
				previews.delete(item.id);
			}

			attachments = attachments.map((row) => (row.id === item.id ? edited : row));
			renderThumbs();
			saveDraft();
		}

		// ------------------------------------------------------------------ capture actions

		async function withHiddenPanel(work) {
			// Keep the drawer out of the tester's own screenshot.
			document.body.classList.add("tl-capturing");
			try {
				return await work();
			} finally {
				document.body.classList.remove("tl-capturing");
			}
		}

		async function takeScreenshot({ thenAnnotate = false } = {}) {
			try {
				const item = await withHiddenPanel(() => NS.capture.screenshot());
				if (!thenAnnotate) {
					addItems([item]);
					return;
				}

				const edited = await NS.annotate.open(item, { startWith: "crop" });
				if (edited) addItems([edited]);
			} catch (error) {
				if (error.name === "NotAllowedError") return; // tester dismissed the picker
				notify(error.message, "warn");
			}
		}

		function snip() {
			return takeScreenshot({ thenAnnotate: true });
		}

		async function startRecording() {
			if (recording) return;

			const withMic = recordBar.dataset.mic === "1";

			try {
				const timer = el("span", { class: "tl-rec-time", text: "0:00" });
				const handle = await NS.capture.record({
					withMic,
					limitSeconds: tools.recording_limit_seconds || 0,
					maxBytes: (tools.max_attachment_mb || 50) * 1024 * 1024,
					onTick: (seconds) => {
						timer.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
					},
					onStop: (item, info) => {
						recording = null;
						recordBar.hidden = true;
						recordBar.replaceChildren();

						if (info?.overflowed) notify(t("Recording stopped — size limit reached."), "warn");
						if (info?.empty) {
							notify(t("Nothing was recorded — the screen share ended before any video arrived."), "warn");
							return;
						}

						if (item) addItems([item]);
					},
				});

				recording = handle;
				recordBar.hidden = false;
				recordBar.replaceChildren(
					el("span", { class: "tl-rec-dot" }),
					el("span", { text: t("Recording") }),
					timer,
					el("span", { class: "tl-spacer" }),
					el("button", { type: "button", class: "tl-btn", onclick: () => handle.cancel() }, t("Discard")),
					el(
						"button",
						{ type: "button", class: "tl-btn tl-btn-primary", onclick: () => handle.stop() },
						t("Stop")
					)
				);
			} catch (error) {
				if (error.name === "NotAllowedError") return;
				notify(error.message, "warn");
			}
		}

		// ------------------------------------------------------------------ composing

		function onPaste(event) {
			const items = NS.capture.fromClipboard(event);
			if (!items.length) return;

			event.preventDefault();
			addItems(items);
		}

		/** Enter in a one-line field would otherwise submit the whole entry mid-thought. */
		function guardEnter(event) {
			if (event.key === "Enter" && event.target.tagName === "INPUT") event.preventDefault();
		}

		function onComposerKey(event) {
			if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
				event.preventDefault();
				composer.requestSubmit();
			}
		}

		function autoGrow() {
			textarea.style.height = "auto";
			textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
		}

		function onSubmit(event) {
			event.preventDefault();

			const description = textarea.value.trim();
			if (!description && !attachments.length) {
				textarea.focus();
				notify(t("Write what happened, or attach a capture."), "warn");
				return;
			}

			const context = config.context?.page !== false ? NS.context.collect() : {};
			const consoleErrors = config.context?.console !== false ? NS.errors.asText() : "";

			const entry = {
				client_id: uuid(),
				created_at: Date.now(),
				status: "queued",
				attempts: 0,
				next_attempt_at: 0,
				error: null,
				payload: {
					...context,
					subject: subjectInput.field.value.trim() || null,
					description,
					module_feature: moduleInput.field.value.trim() || NS.context.module(),
					steps_to_reproduce: stepsInput.field.value.trim() || null,
					expected_result: expectedInput.field.value.trim() || null,
					actual_result: description || null,
					severity: severitySelect.value,
					test_type: typeSelect.value,
					assigned_developer: developerSelect.value || null,
					test_run: currentRun(),
					product: runProduct(),
					console_errors: consoleErrors || null,
					captured_at: toServerDatetime(new Date()),
				},
				attachments,
			};

			resetComposer();
			handlers.submit(entry);
		}

		function resetComposer() {
			// Drop any half-written draft save, or it would land after the entry was sent.
			saveDraft.cancel();

			attachments = [];
			previews.forEach((url) => URL.revokeObjectURL(url));
			previews.clear();

			textarea.value = "";
			[subjectInput, moduleInput, stepsInput, expectedInput].forEach((f) => (f.field.value = ""));
			details.hidden = true;
			detailsToggle.classList.remove("is-active");

			renderThumbs();
			autoGrow();
			handlers.clearDraft?.();
		}

		function toServerDatetime(date) {
			const pad = (n) => String(n).padStart(2, "0");
			return (
				`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
				`${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
			);
		}

		// ------------------------------------------------------------------ drafts

		const saveDraft = debounce(() => {
			handlers.saveDraft?.({
				text: textarea.value,
				subject: subjectInput.field.value,
				module_feature: moduleInput.field.value,
				steps: stepsInput.field.value,
				expected: expectedInput.field.value,
				severity: severitySelect.value,
				test_type: typeSelect.value,
				assigned_developer: developerSelect.value,
				attachments,
			});
		}, 400);

		function restoreDraft(draft) {
			if (!draft) return;

			textarea.value = draft.text || "";
			subjectInput.field.value = draft.subject || "";
			moduleInput.field.value = draft.module_feature || "";
			stepsInput.field.value = draft.steps || "";
			expectedInput.field.value = draft.expected || "";
			if (draft.severity) severitySelect.value = draft.severity;
			if (draft.test_type) typeSelect.value = draft.test_type;
			if (draft.assigned_developer) developerSelect.value = draft.assigned_developer;

			attachments = (draft.attachments || []).filter((item) => item.blob);
			renderThumbs();
			autoGrow();
		}

		// ------------------------------------------------------------------ feed

		function renderFeed() {
			const rows = [
				...feed.map((log) => feedRow(log)),
				...queue.map((entry) => queueRow(entry)),
			];

			feedList.replaceChildren(
				rows.length
					? el("div", { class: "tl-feed-rows" }, rows)
					: el("div", { class: "tl-empty" }, [
							icon("bug", 22),
							el("p", { text: t("Nothing logged here yet.") }),
							el("small", {
								text: t("Capture the screen, say what went wrong, and it lands in the sheet."),
							}),
					  ])
			);

			feedList.scrollTop = feedList.scrollHeight;
		}

		function feedRow(log) {
			const colour = (vocabulary.status_colors || {})[log.status] || "gray";

			return el(
				"article",
				{
					class: "tl-entry",
					tabindex: "0",
					onclick: () => openLog(log),
					onkeydown: (event) => event.key === "Enter" && openLog(log),
				},
				[
					log.thumbnail
						? el("img", {
								class: "tl-entry-thumb",
								src: log.thumbnail,
								alt: "",
								// Offline the file cannot load; an empty frame reads better than a broken one.
								onerror: (event) => event.target.remove(),
						  })
						: null,
					el("div", { class: "tl-entry-body" }, [
						el("div", { class: "tl-entry-subject", text: log.subject }),
						el("div", { class: "tl-entry-meta" }, [
							el("span", { class: `tl-pill tl-pill-${colour}`, text: t(log.status) }),
							el("span", { text: log.name }),
							log.evidence_count
								? el("span", { text: `${log.evidence_count} ${t("files")}` })
								: null,
							el("span", { class: "tl-muted", text: timeAgo(log.creation) }),
						]),
					]),
				]
			);
		}

		function queueRow(entry) {
			const failed = entry.status === "failed";
			const preview = entry.attachments?.find((item) => item.kind === "image");

			return el("article", { class: `tl-entry tl-entry-queued${failed ? " is-failed" : ""}` }, [
				preview ? el("img", { class: "tl-entry-thumb", src: previewUrl(preview), alt: "" }) : null,
				el("div", { class: "tl-entry-body" }, [
					el("div", {
						class: "tl-entry-subject",
						text: entry.payload.subject || entry.payload.description || t("Capture"),
					}),
					el("div", { class: "tl-entry-meta" }, [
						el("span", { class: `tl-pill tl-pill-${failed ? "red" : "gray"}` }, [
							icon("clock", 11),
							failed ? t("Not sent") : t("Waiting"),
						]),
						entry.error ? el("span", { class: "tl-muted", text: entry.error }) : null,
					]),
					failed
						? el("div", { class: "tl-entry-actions" }, [
								el(
									"button",
									{ type: "button", class: "tl-btn tl-btn-mini", onclick: () => handlers.retry(entry) },
									t("Try again")
								),
								el(
									"button",
									{
										type: "button",
										class: "tl-btn tl-btn-mini",
										onclick: () => handlers.discard(entry),
									},
									t("Discard")
								),
						  ])
						: null,
				]),
			]);
		}

		/** Build the run's Word document — every log in it, with its evidence embedded. */
		async function buildReport() {
			const run = currentRun();
			if (!run) {
				notify(t("Pick a test run first — the report covers a whole run."), "warn");
				return;
			}

			notify(t("Building the report…"));
			const report = await handlers.buildReport?.(run);
			if (report?.file_url) window.open(report.file_url, "_blank", "noopener");
		}

		function openLog(log) {
			if (window.frappe?.set_route) frappe.set_route("Form", "Test Log", log.name);
			else window.open(log.url, "_blank", "noopener");
		}

		// ------------------------------------------------------------------ status strip

		function renderNet({ online, syncing, pending, durable }) {
			const parts = [];

			if (!online) {
				parts.push(
					el("span", { class: "tl-net-tag tl-net-offline" }, [icon("cloud", 13), t("Offline")]),
					el("span", {
						class: "tl-muted",
						text: t("Entries are saved on this device and sent when the site is back."),
					})
				);
			} else if (pending) {
				parts.push(
					el("span", { class: "tl-net-tag" }, [icon("refresh", 13), syncing ? t("Sending…") : t("Waiting to send")])
				);
			}

			if (pending) {
				parts.push(el("span", { class: "tl-badge", text: String(pending) }));
				if (online && !syncing) {
					parts.push(
						el(
							"button",
							{ type: "button", class: "tl-btn tl-btn-mini", onclick: () => handlers.syncNow?.() },
							t("Send now")
						)
					);
				}
			}

			if (!durable) {
				parts.push(
					el("span", {
						class: "tl-muted",
						text: t("This browser blocks local storage — do not close the tab with entries waiting."),
					})
				);
			}

			netStrip.replaceChildren(...parts);
			netStrip.hidden = !parts.length;
		}

		// ------------------------------------------------------------------ resize

		function clampWidth(width) {
			return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width));
		}

		function enableResize() {
			let startX = 0;
			let startWidth = 0;

			const move = (event) => {
				const width = clampWidth(startWidth + (startX - event.clientX));
				root.style.width = `${width}px`;
			};

			const up = () => {
				document.removeEventListener("pointermove", move);
				document.removeEventListener("pointerup", up);
				document.body.classList.remove("tl-resizing");
				localStorage.setItem(WIDTH_KEY, String(parseInt(root.style.width, 10)));
			};

			grip.addEventListener("pointerdown", (event) => {
				startX = event.clientX;
				startWidth = parseInt(root.style.width, 10) || 400;
				document.body.classList.add("tl-resizing");
				document.addEventListener("pointermove", move);
				document.addEventListener("pointerup", up);
			});
		}

		// ------------------------------------------------------------------ drag & drop

		root.addEventListener("dragover", (event) => {
			if (!event.dataTransfer?.types.includes("Files")) return;
			event.preventDefault();
			root.classList.add("is-dropping");
		});

		root.addEventListener("dragleave", (event) => {
			if (event.target === root) root.classList.remove("is-dropping");
		});

		root.addEventListener("drop", (event) => {
			if (!event.dataTransfer?.files.length) return;
			event.preventDefault();
			root.classList.remove("is-dropping");
			addItems(NS.capture.fromFiles(event.dataTransfer.files));
		});

		// ------------------------------------------------------------------ notices

		function notify(message, kind = "info") {
			const toast = el("div", { class: `tl-toast tl-toast-${kind}`, text: message });
			root.append(toast);
			setTimeout(() => toast.classList.add("is-out"), 2600);
			setTimeout(() => toast.remove(), 3000);
		}

		// ------------------------------------------------------------------ open / close

		function show() {
			root.hidden = false;
			open = true;
			document.body.classList.add("tl-panel-open");
			requestAnimationFrame(() => root.classList.add("is-open"));
			handlers.refreshFeed?.();
			textarea.focus();
			feedList.scrollTop = feedList.scrollHeight;
		}

		function close() {
			open = false;
			root.classList.remove("is-open");
			document.body.classList.remove("tl-panel-open");
			setTimeout(() => {
				if (!open) root.hidden = true;
			}, 200);
		}

		fillRuns();
		renderFeed();

		return {
			root,
			open: show,
			close,
			toggle: () => (open ? close() : show()),
			isOpen: () => open,
			isRecording: () => Boolean(recording),
			restoreDraft,
			addItems,
			notify,
			setFeed(logs) {
				feed = (logs || []).slice().reverse();
				renderFeed();
			},
			setQueue(entries) {
				queue = entries || [];
				renderFeed();
			},
			setNetwork: renderNet,
			currentRun,
		};
	}

	NS.createPanel = createPanel;
})();
