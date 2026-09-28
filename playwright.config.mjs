import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./bot/tests/visual",
  outputDir: "./test-results/playwright",
  snapshotPathTemplate: "{testDir}/__screenshots__/{projectName}/{arg}{ext}",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 30_000,
  expect: {
    timeout: 8_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.001,
      scale: "css",
    },
  },
  reporter: process.env.CI
    ? [["github"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    colorScheme: "dark",
    deviceScaleFactor: 1,
    locale: "en-US",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    serviceWorkers: "block",
    timezoneId: "America/New_York",
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "node bot/tests/visual/server.mjs",
    url: "http://127.0.0.1:4173/dashboard",
    reuseExistingServer: !process.env.CI,
    timeout: 10_000,
  },
});
