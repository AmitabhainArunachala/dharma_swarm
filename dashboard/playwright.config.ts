import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./playwright",
  timeout: 60_000,
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3420",
    channel: "chrome",
    headless: true,
    viewport: { width: 1680, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3420",
    url: "http://127.0.0.1:3420",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
