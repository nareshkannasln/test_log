const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
	testDir: "./tests/widget",
	use: { headless: true },
	webServer: {
		command: "python3 -m http.server 8769 --bind 127.0.0.1",
		url: "http://127.0.0.1:8769",
		reuseExistingServer: false,
	},
});
