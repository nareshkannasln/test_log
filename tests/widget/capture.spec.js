const { test, expect } = require("@playwright/test");
const path = require("node:path");

async function loadWidget(page, { enabled = true } = {}) {
	await page.goto("http://127.0.0.1:8769");
	await page.evaluate((enabled) => {
		document.body.innerHTML = "<h1>Page under test</h1>";
		window.frappe = {
			boot: {
				test_log: {
					enabled,
					defaults: { product: "Widget product" },
					runs: [],
					products: [],
					developers: [],
					tools: {},
					context: { page: true, console: false },
				},
			},
		};
	}, enabled);
	await page.route("**/api/method/test_log.api.get_feed", (route) =>
		route.fulfill({ json: { message: [] } })
	);
	for (const file of ["core", "store", "capture", "annotate", "panel", "widget"]) {
		await page.addScriptTag({ path: path.resolve(`test_log/public/js/tester/${file}.js`) });
	}
	await page.addStyleTag({ path: path.resolve("test_log/public/css/tester.css") });
}

test("panel opens by shortcut, validates empty entry, and closes", async ({ page }) => {
	await loadWidget(page);
	await expect(page.locator(".tl-fab")).toBeVisible();
	await page.keyboard.press("Control+Shift+L");
	await expect(page.locator(".tl-panel")).toBeVisible();
	await page.locator(".tl-send").click();
	await expect(page.getByText("Write what happened, or attach a capture.")).toBeVisible();
	await page.getByTitle("Close", { exact: true }).click();
	await expect(page.locator(".tl-panel")).toBeHidden();
});

test("capture submits its description and context once", async ({ page }) => {
	let captured = [];
	await page.route("**/api/method/test_log.api.log_entry", async (route) => {
		const entry = route.request().postDataJSON().entry;
		captured.push(entry);
		await route.fulfill({
			json: {
				message: {
					name: "TL-SMOKE-1",
					subject: entry.description,
					status: "Open",
					severity: "Medium",
				},
			},
		});
	});
	await loadWidget(page);
	await page.locator(".tl-fab").click();
	await page.locator(".tl-text").fill("Saving the form does nothing");
	await page.locator(".tl-send").click();
	await expect.poll(() => captured.length).toBe(1);
	expect(captured[0].description).toBe("Saving the form does nothing");
	expect(captured[0].client_id).toBeTruthy();
	expect(captured[0].page_url).toContain("127.0.0.1:8769");
	await expect(page.locator(".tl-text")).toHaveValue("");
	await expect.poll(() => page.evaluate(() => window.test_log.store.count())).toBe(0);
});

test("disabled widget stays hidden", async ({ page }) => {
	await loadWidget(page, { enabled: false });
	await expect(page.locator(".tl-fab")).toHaveCount(0);
});

test("rejected capture remains queued for explicit retry", async ({ page }) => {
	await page.route("**/api/method/test_log.api.log_entry", (route) =>
		route.fulfill({ status: 403, json: { message: "No access to this file" } })
	);
	await loadWidget(page);
	await page.locator(".tl-fab").click();
	await page.locator(".tl-text").fill("Rejected evidence");
	await page.locator(".tl-send").click();
	await expect(page.getByText("No access to this file")).toBeVisible();
	await expect.poll(() => page.evaluate(() => window.test_log.store.count())).toBe(1);
	await expect(page.getByText("Try again", { exact: true })).toBeVisible();
});
