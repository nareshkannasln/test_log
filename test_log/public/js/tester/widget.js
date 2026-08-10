// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * Boots the tester widget on every page and owns the one thing that has to be right:
 * getting queued entries onto the site exactly once.
 *
 * The rules it follows —
 *   1. An entry is written to the local database before anything is sent.
 *   2. Uploads are remembered per attachment, so a retry never re-uploads a file.
 *   3. Every entry carries a client id, so a retry that the server already saw comes
 *      back as the same Test Log instead of a second one.
 *   4. Network trouble backs off and tries again; a rejected document stops and asks
 *      the tester, rather than looping forever.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.widget) return;

	const { el, icon, t } = NS.util;

	const HIDDEN_KEY = "test_log:hidden";
	const MAX_ATTEMPTS = 6;

	let config = null;
	let panel = null;
	let fab = null;
	let badge = null;
	let syncing = false;
	let timer = null;
	let pending = 0;

	// ------------------------------------------------------------------ config

	const CONFIG_TTL = 60 * 60 * 1000;

	function cacheConfig(value) {
		NS.store.setMeta("config", { value, at: Date.now() }).catch(() => {});
	}

	/** Cheap check that avoids pinging the API from the login page and other guest views. */
	function looksLoggedIn() {
		const status = document.body?.getAttribute("frappe-session-status");
		if (status) return status === "logged-in";

		const cookie = document.cookie.match(/(?:^|;\s*)user_id=([^;]+)/);
		const user = cookie ? decodeURIComponent(cookie[1]) : "";
		return Boolean(user && user !== "Guest");
	}

	async function loadConfig() {
		// Desk pages carry the config in the boot payload, so nothing is fetched there.
		const booted = window.frappe?.boot?.test_log;
		if (booted) {
			cacheConfig(booted);
			return booted;
		}

		if (!looksLoggedIn()) return null;

		const cached = await NS.store.getMeta("config", null).catch(() => null);
		if (cached?.at && Date.now() - cached.at < CONFIG_TTL) return cached.value;

		try {
			const fetched = await NS.api.call("test_log.api.get_config");
			cacheConfig(fetched);
			return fetched;
		} catch (error) {
			// Offline, or a page that cannot reach the API — fall back to what we know.
			return cached?.value || null;
		}
	}

	// ------------------------------------------------------------------ sending

	function backoff(attempts) {
		return Math.min(5 * 60 * 1000, 5000 * 2 ** (attempts - 1));
	}

	function filePayload(entry) {
		return (entry.attachments || [])
			.filter((item) => item.file_url)
			.map((item) => ({
				file_url: item.file_url,
				file_name: item.file_name,
				mime: item.mime,
				caption: item.caption || "",
			}));
	}

	/** @returns {'sent'|'retry'|'failed'} */
	async function send(entry) {
		try {
			for (const item of entry.attachments || []) {
				if (item.file_url) continue;

				// An empty blob has nothing to upload and the server rightly rejects it —
				// drop it rather than let one bad attachment strand the whole entry.
				if (!item.blob?.size) {
					item.dropped = true;
					item.file_url = null;
					continue;
				}

				const file = await NS.api.upload(item.blob, {
					file_name: item.file_name,
					is_private: config.tools?.private_uploads === false ? 0 : 1,
				});

				item.file_url = file.file_url;
				// Persist immediately: a failure after this point must not upload twice.
				await NS.store.patch(entry.client_id, { attachments: entry.attachments });
			}

			const log = await NS.api.call("test_log.api.log_entry", {
				entry: { ...entry.payload, client_id: entry.client_id, files: filePayload(entry) },
			});

			await NS.store.remove(entry.client_id);
			onLogged(log);
			return "sent";
		} catch (error) {
			const attempts = (entry.attempts || 0) + 1;
			const done = error.permanent || attempts >= MAX_ATTEMPTS;

			await NS.store.patch(entry.client_id, {
				attempts,
				error: error.message,
				status: done ? "failed" : "queued",
				next_attempt_at: Date.now() + backoff(attempts),
			});

			if (done) {
				panel?.notify(t("Could not save an entry — open the panel to see why."), "warn");
				return "failed";
			}

			return "retry";
		}
	}

	async function flush({ force = false } = {}) {
		if (syncing) return;
		if (!navigator.onLine && !force) {
			await refreshQueue();
			return;
		}

		syncing = true;
		await refreshQueue();

		try {
			const entries = await NS.store.all();

			for (const entry of entries) {
				if (!force && entry.status === "failed") continue;
				if (!force && entry.next_attempt_at > Date.now()) continue;

				const result = await send(entry);
				// A network stall will hit every entry the same way; stop and wait it out.
				if (result === "retry") break;
			}
		} finally {
			syncing = false;
			await refreshQueue();
		}
	}

	function onLogged(log) {
		if (!log || log.duplicate) return;

		panel?.notify(t("Logged") + ` ${log.name}`, "ok");
		refreshFeed();
	}

	// ------------------------------------------------------------------ state → ui

	async function refreshQueue() {
		const entries = await NS.store.all();
		pending = entries.length;

		panel?.setQueue(entries);
		panel?.setNetwork({
			online: navigator.onLine,
			syncing,
			pending,
			durable: NS.store.isDurable(),
		});

		if (badge) {
			badge.textContent = pending ? String(pending) : "";
			badge.hidden = !pending;
			fab?.classList.toggle("has-pending", Boolean(pending));
		}
	}

	let feedTimer = null;
	function refreshFeed() {
		clearTimeout(feedTimer);
		feedTimer = setTimeout(async () => {
			if (!panel?.isOpen()) return;

			try {
				const logs = await NS.api.call("test_log.api.get_feed", {
					test_run: panel.currentRun(),
					limit: 15,
				});
				panel.setFeed(logs);
			} catch (error) {
				// Offline: the queue rows already tell the tester where things stand.
			}
		}, 150);
	}

	// ------------------------------------------------------------------ widget shell

	function buildPanel() {
		panel = NS.createPanel({
			config,
			handlers: {
				async submit(entry) {
					await NS.store.put(entry);
					await refreshQueue();
					flush();
				},

				async retry(entry) {
					await NS.store.patch(entry.client_id, {
						status: "queued",
						attempts: 0,
						next_attempt_at: 0,
						error: null,
					});
					flush({ force: true });
				},

				async discard(entry) {
					await NS.store.remove(entry.client_id);
					await refreshQueue();
				},

				syncNow: () => flush({ force: true }),
				refreshFeed,

				async buildReport(testRun) {
					try {
						return await NS.api.call("test_log.api.build_run_report", { test_run: testRun });
					} catch (error) {
						panel.notify(error.message, "warn");
						return null;
					}
				},

				async createRun(values) {
					try {
						return await NS.api.call("test_log.api.create_run", values);
					} catch (error) {
						panel.notify(error.message, "warn");
						return null;
					}
				},

				saveDraft: (draft) => NS.store.setMeta("draft", draft).catch(() => {}),
				clearDraft: () => NS.store.setMeta("draft", null).catch(() => {}),
			},
		});

		document.body.append(panel.root);

		NS.store.getMeta("draft", null).then((draft) => panel.restoreDraft(draft));
	}

	function buildFab() {
		badge = el("span", { class: "tl-fab-badge", hidden: true });

		fab = el(
			"button",
			{
				type: "button",
				class: "tl-fab",
				title: `${t("Log a test note")} (Ctrl+Shift+L)`,
				"aria-label": t("Log a test note"),
				onclick: () => panel.toggle(),
				oncontextmenu: (event) => {
					event.preventDefault();
					showFabMenu();
				},
			},
			[icon("bug", 20), badge]
		);

		document.body.append(fab);
		if (localStorage.getItem(HIDDEN_KEY) === "1") fab.hidden = true;
	}

	function showFabMenu() {
		document.querySelector(".tl-fab-menu")?.remove();

		const menu = el("div", { class: "tl-fab-menu" }, [
			el(
				"button",
				{
					type: "button",
					onclick: () => {
						localStorage.setItem(HIDDEN_KEY, "1");
						fab.hidden = true;
						menu.remove();
					},
				},
				t("Hide this button for me")
			),
			el(
				"button",
				{
					type: "button",
					onclick: () => {
						menu.remove();
						if (window.frappe?.set_route) frappe.set_route("List", "Test Log");
						else window.open("/app/test-log", "_blank", "noopener");
					},
				},
				t("Open all test logs")
			),
		]);

		document.body.append(menu);
		setTimeout(() => document.addEventListener("click", () => menu.remove(), { once: true }), 0);
	}

	// ------------------------------------------------------------------ wiring

	function scheduleSync() {
		clearInterval(timer);
		const seconds = Math.max(15, config.offline?.retry_seconds || 60);
		timer = setInterval(() => flush(), seconds * 1000);
	}

	function watchConnection() {
		window.addEventListener("online", () => {
			refreshQueue();
			flush();
		});
		window.addEventListener("offline", refreshQueue);

		document.addEventListener("visibilitychange", () => {
			if (document.visibilityState === "visible") flush();
		});

		window.addEventListener("beforeunload", (event) => {
			// Only worth interrupting when the queue would not survive the reload.
			if (pending && !NS.store.isDurable()) {
				event.preventDefault();
				event.returnValue = "";
			}
		});
	}

	function watchShortcut() {
		window.addEventListener("keydown", (event) => {
			if (!event.ctrlKey || !event.shiftKey) return;
			if (String(event.key).toLowerCase() !== "l") return;

			event.preventDefault();
			api.open();
		});
	}

	const api = {
		open() {
			localStorage.removeItem(HIDDEN_KEY);
			if (fab) fab.hidden = false;
			panel?.open();
		},
		close: () => panel?.close(),
		toggle: () => panel?.toggle(),
		flush: () => flush({ force: true }),
		get config() {
			return config;
		},
		get panel() {
			return panel;
		},
	};

	async function boot() {
		if (document.readyState === "loading") {
			await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve));
		}

		config = await loadConfig();

		if (!config?.enabled) {
			// Tester mode may have been switched off with entries still queued here.
			const left = await NS.store.count().catch(() => 0);
			if (left) await flush();
			return;
		}

		NS.errors.setLimit(config.context?.console_limit);

		buildPanel();
		buildFab();
		watchConnection();
		watchShortcut();
		scheduleSync();

		await refreshQueue();
		flush();
	}

	NS.widget = api;

	boot().catch((error) => console.warn("[test log] widget did not start:", error));
})();
