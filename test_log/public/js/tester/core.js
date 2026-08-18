// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * Shared plumbing for the tester widget: DOM helpers, the HTTP layer, and the two
 * recorders that run from the moment this file loads — console errors and page
 * context — so an entry logged five minutes into a session still knows what broke.
 *
 * Everything hangs off `window.test_log` and nothing here assumes Frappe's desk
 * bundle is present, because the widget also rides along on portal pages.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.util) return;

	const t = (text) => (typeof window.__ === "function" ? window.__(text) : text);

	// ---------------------------------------------------------------- dom + misc

	function el(tag, props = {}, children = []) {
		const node = document.createElement(tag);

		for (const [key, value] of Object.entries(props)) {
			if (value === null || value === undefined || value === false) continue;

			if (key === "class") node.className = value;
			else if (key === "text") node.textContent = value;
			else if (key === "style") Object.assign(node.style, value);
			else if (key === "dataset") Object.assign(node.dataset, value);
			else if (key.startsWith("on") && typeof value === "function")
				node.addEventListener(key.slice(2).toLowerCase(), value);
			else node.setAttribute(key, value === true ? "" : value);
		}

		for (const child of [].concat(children)) {
			if (child === null || child === undefined || child === false) continue;
			node.append(child.nodeType ? child : document.createTextNode(String(child)));
		}

		return node;
	}

	const ICONS = {
		camera: '<path d="M3 7h3l2-2h8l2 2h3v12H3z"/><circle cx="12" cy="13" r="4"/>',
		record: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4" fill="currentColor"/>',
		stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
		scissors:
			'<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 16M8.1 8 20 20"/>',
		paperclip:
			'<path d="M21 11.5 12 20.5a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>',
		close: '<path d="M6 6l12 12M18 6 6 18"/>',
		send: '<path d="M4 12 20 4l-4 16-4-7z"/>',
		bug: '<path d="M9 6a3 3 0 0 1 6 0M8 9h8v6a4 4 0 0 1-8 0zM4 12h4M16 12h4M5 7l3 2M19 7l-3 2M5 18l3-2M19 18l-3-2"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		chevron: '<path d="m6 9 6 6 6-6"/>',
		cloud: '<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.5A3.5 3.5 0 0 1 18 18z"/>',
		clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
		refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>',
		trash: '<path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/>',
		grip: '<path d="M9 5v14M15 5v14"/>',
		document:
			'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6"/>',
	};

	function icon(name, size = 16) {
		const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
		svg.setAttribute("viewBox", "0 0 24 24");
		svg.setAttribute("width", size);
		svg.setAttribute("height", size);
		svg.setAttribute("fill", "none");
		svg.setAttribute("stroke", "currentColor");
		svg.setAttribute("stroke-width", "1.6");
		svg.setAttribute("stroke-linecap", "round");
		svg.setAttribute("stroke-linejoin", "round");
		svg.innerHTML = ICONS[name] || "";
		return svg;
	}

	function uuid() {
		if (window.crypto?.randomUUID) return window.crypto.randomUUID();

		return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
			const r = (Math.random() * 16) | 0;
			return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
		});
	}

	function bytes(size) {
		if (!size) return "";
		const units = ["B", "KB", "MB", "GB"];
		let value = size;
		let unit = 0;
		while (value >= 1024 && unit < units.length - 1) {
			value /= 1024;
			unit += 1;
		}
		return `${value < 10 && unit ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
	}

	function debounce(fn, wait) {
		let timer;

		const run = (...args) => {
			clearTimeout(timer);
			timer = setTimeout(() => fn(...args), wait);
		};

		// Needed when the thing being saved stops existing — a draft that was just sent.
		run.cancel = () => clearTimeout(timer);
		return run;
	}

	function timeAgo(value) {
		const then = new Date(String(value).replace(" ", "T")).getTime();
		if (Number.isNaN(then)) return "";

		const seconds = Math.max(0, (Date.now() - then) / 1000);
		if (seconds < 60) return t("just now");
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
		if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
		return `${Math.floor(seconds / 86400)}d`;
	}

	NS.util = { el, icon, uuid, bytes, debounce, timeAgo, t };

	// ---------------------------------------------------------------- http

	class RequestError extends Error {
		constructor(message, { permanent = false, status = 0 } = {}) {
			super(message);
			this.permanent = permanent;
			this.status = status;
		}
	}

	function csrfToken() {
		return window.frappe?.csrf_token || "";
	}

	function serverMessage(payload, fallback) {
		try {
			const messages = JSON.parse(payload?._server_messages || "[]");
			const first = messages.length ? JSON.parse(messages[0]) : null;
			if (first?.message) return String(first.message).replace(/<[^>]*>/g, "");
		} catch (e) {
			// fall through to the generic message
		}
		return payload?.exception || payload?.message || fallback;
	}

	async function readBody(response) {
		const text = await response.text();
		try {
			return JSON.parse(text);
		} catch (e) {
			return { message: text };
		}
	}

	/** POST to a whitelisted method. Throws RequestError; `permanent` means retrying won't help. */
	async function call(method, args = {}) {
		let response;

		try {
			response = await fetch(`/api/method/${method}`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-Frappe-CSRF-Token": csrfToken(),
				},
				body: JSON.stringify(args),
				credentials: "same-origin",
			});
		} catch (e) {
			throw new RequestError(t("Could not reach the site."), { permanent: false });
		}

		const payload = await readBody(response);

		if (!response.ok) {
			throw new RequestError(serverMessage(payload, response.statusText), {
				// 5xx and 429 are worth another go; a rejected document is not.
				permanent: response.status < 500 && response.status !== 429,
				status: response.status,
			});
		}

		return payload.message;
	}

	/** Upload one blob and return the created File document. */
	async function upload(blob, { file_name, is_private = 1, folder = "Home" } = {}) {
		const form = new FormData();
		form.append("file", blob, file_name);
		form.append("file_name", file_name);
		form.append("is_private", is_private ? "1" : "0");
		form.append("folder", folder);

		let response;
		try {
			response = await fetch("/api/method/upload_file", {
				method: "POST",
				headers: { Accept: "application/json", "X-Frappe-CSRF-Token": csrfToken() },
				body: form,
				credentials: "same-origin",
			});
		} catch (e) {
			throw new RequestError(t("Could not reach the site."), { permanent: false });
		}

		const payload = await readBody(response);

		if (!response.ok) {
			throw new RequestError(serverMessage(payload, t("Upload failed.")), {
				permanent: response.status < 500 && response.status !== 429,
				status: response.status,
			});
		}

		return payload.message;
	}

	NS.api = { call, upload, RequestError };

	// ---------------------------------------------------------------- console recorder

	const errors = [];
	let errorLimit = 20;

	function recordError(kind, text, detail) {
		if (!text) return;

		errors.push({
			kind,
			text: String(text).slice(0, 500),
			detail: detail ? String(detail).slice(0, 800) : "",
			at: new Date().toISOString(),
			route: currentRoute(),
		});

		while (errors.length > Math.max(errorLimit, 1)) errors.shift();
	}

	function watchConsole() {
		window.addEventListener("error", (event) => {
			const where = event.filename ? `${event.filename}:${event.lineno}` : "";
			recordError("error", event.message, where);
		});

		window.addEventListener("unhandledrejection", (event) => {
			const reason = event.reason;
			recordError("promise", reason?.message || reason, reason?.stack);
		});

		const original = window.console.error;
		window.console.error = function (...args) {
			recordError("console", args.map(stringify).join(" "));
			return original.apply(window.console, args);
		};
	}

	function stringify(value) {
		if (value instanceof Error) return `${value.message}\n${value.stack || ""}`;
		if (typeof value === "object") {
			try {
				return JSON.stringify(value);
			} catch (e) {
				return String(value);
			}
		}
		return String(value);
	}

	NS.errors = {
		setLimit(limit) {
			errorLimit = limit || 20;
		},
		list: () => errors.slice(),
		clear: () => errors.splice(0, errors.length),
		asText() {
			return errors
				.map(
					(row) =>
						`[${row.at}] ${row.kind}: ${row.text}${
							row.detail ? `\n    ${row.detail}` : ""
						}`
				)
				.join("\n");
		},
	};

	// ---------------------------------------------------------------- page context

	function currentRoute() {
		try {
			if (window.frappe?.get_route_str) {
				const route = window.frappe.get_route_str();
				if (route) return route;
			}
		} catch (e) {
			// desk router not ready
		}
		return `${location.pathname}${location.hash}`;
	}

	function browserName() {
		const brands = navigator.userAgentData?.brands || [];
		const branded = brands.find((b) => !/Not.?A.?Brand/i.test(b.brand));
		if (branded) return `${branded.brand} ${branded.version}`;

		const ua = navigator.userAgent;
		const match = ua.match(/(Edg|OPR|Chrome|Firefox|Safari)\/([\d.]+)/) || [];
		const names = { Edg: "Edge", OPR: "Opera" };
		return match[1] ? `${names[match[1]] || match[1]} ${match[2].split(".")[0]}` : "Browser";
	}

	function platformName() {
		if (navigator.userAgentData?.platform) return navigator.userAgentData.platform;
		const ua = navigator.userAgent;
		if (/Windows/.test(ua)) return "Windows";
		if (/Android/.test(ua)) return "Android";
		if (/iPhone|iPad/.test(ua)) return "iOS";
		if (/Mac OS X/.test(ua)) return "macOS";
		if (/Linux/.test(ua)) return "Linux";
		return "";
	}

	/** A guess at what the tester is looking at, used to prefill Module / Feature. */
	function moduleFromRoute() {
		const route = currentRoute();
		const parts = route.split("/").filter(Boolean).map(decodeURIComponent);

		if (!parts.length) return "";
		if (["Form", "List", "Tree", "Workspaces", "query-report", "print"].includes(parts[0])) {
			return parts[1] || parts[0];
		}
		if (parts[0] === "app") return parts[1] || "";

		return parts[parts.length - 1];
	}

	NS.context = {
		route: currentRoute,
		module: moduleFromRoute,
		collect() {
			return {
				page_route: currentRoute(),
				page_url: location.href,
				viewport: `${window.innerWidth}x${window.innerHeight} @${
					window.devicePixelRatio || 1
				}x`,
				environment: [browserName(), platformName()].filter(Boolean).join(" on "),
			};
		},
	};

	watchConsole();
})();
