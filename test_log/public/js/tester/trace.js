/** Opt-in, bounded capture. Never records request bodies, headers or input values. */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.trace) return;
	let config = {},
		started = false;
	const requests = [],
		steps = [];
	const sensitive =
		/password|passwd|token|secret|authorization|cookie|api[_-]?key|session|csrf/i;
	function safeURL(value) {
		try {
			const url = new URL(value, location.href);
			if (
				url.origin !== location.origin ||
				/login|auth|password|\/private\/files|test_log\.api|upload_file/i.test(
					url.pathname
				)
			)
				return null;
			return url.pathname;
		} catch {
			return null;
		}
	}
	function redact(text) {
		try {
			return JSON.stringify(JSON.parse(text), (key, value) =>
				sensitive.test(key) ? "[redacted]" : value
			).slice(0, 2048);
		} catch {
			return String(text)
				.replace(
					/((?:password|passwd|token|secret|authorization|cookie|api[_-]?key|session|csrf)[\w-]*["']?\s*[:=]\s*)["']?[^\s,"'}<]+["']?/gi,
					"$1[redacted]"
				)
				.slice(0, 2048);
		}
	}
	function addRequest(url, method, status, response) {
		if (!config.network) return;
		const path = safeURL(url);
		if (!path) return;
		requests.push({ at: Date.now(), path, method, status, response: redact(response || "") });
		while (requests.length > 20) requests.shift();
	}
	async function excerpt(response) {
		if (!/json|text\//i.test(response.headers.get("Content-Type") || "")) return "";
		const reader = response.clone().body?.getReader();
		if (!reader) return "";
		const decoder = new TextDecoder();
		let text = "";
		try {
			while (text.length < 2048) {
				const { done, value } = await reader.read();
				if (done) break;
				text += decoder.decode(value.subarray(0, 2048 - text.length));
			}
		} finally {
			reader.cancel().catch(() => {});
		}
		return text.slice(0, 2048);
	}
	function prune() {
		while (steps.length && steps[0].at < Date.now() - 60000) steps.shift();
	}
	function step(kind, target) {
		if (!config.replay) return;
		prune();
		steps.push({ at: Date.now(), kind, target, path: location.pathname });
		while (steps.length > 50) steps.shift();
	}
	function start(value) {
		config = value || {};
		if (started || (!config.network && !config.replay)) return;
		started = true;
		const originalFetch = window.fetch;
		window.fetch = function (input, options) {
			const url =
				typeof input === "string" || input instanceof URL ? String(input) : input.url;
			const method = options?.method || input?.method || "GET";
			return originalFetch.apply(this, arguments).then(
				(response) => {
					if (!response.ok && safeURL(url) && config.network)
						excerpt(response)
							.then((text) => addRequest(url, method, response.status, text))
							.catch(() => {});
					return response;
				},
				(error) => {
					addRequest(url, method, 0, "Network error");
					throw error;
				}
			);
		};
		const originalOpen = XMLHttpRequest.prototype.open;
		XMLHttpRequest.prototype.open = function (method, url) {
			this.addEventListener(
				"loadend",
				() => {
					if (this.status && this.status < 400) return;
					let response = "";
					try {
						if (!this.responseType || this.responseType === "text")
							response = this.responseText.slice(0, 2048);
					} catch {
						/* unavailable */
					}
					addRequest(url, method, this.status, response);
				},
				{ once: true }
			);
			return originalOpen.apply(this, arguments);
		};
		document.addEventListener(
			"click",
			(event) => {
				if (event.target.closest?.(".tl-panel, .tl-fab, .tl-annotate")) return;
				const target = event.target.closest?.("button, a, input, select, [role=button]");
				if (target)
					step(
						"click",
						target.tagName.toLowerCase() + (target.type ? `[type=${target.type}]` : "")
					);
			},
			true
		);
		window.addEventListener("popstate", () => step("navigate", location.pathname));
		window.addEventListener("hashchange", () => step("navigate", location.pathname));
		const push = history.pushState;
		history.pushState = function () {
			const result = push.apply(this, arguments);
			step("navigate", location.pathname);
			return result;
		};
	}
	NS.trace = {
		start,
		network: () => (config.network ? JSON.stringify(requests) : ""),
		replay: () => {
			prune();
			return config.replay ? JSON.stringify(steps) : "";
		},
	};
})();
