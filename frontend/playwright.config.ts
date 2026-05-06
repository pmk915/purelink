import { defineConfig, devices } from "@playwright/test";

const frontendBaseUrl = process.env.PURELINK_FRONTEND_BASE_URL ?? "http://127.0.0.1:3000";
const browserExecutablePath = process.env.PLAYWRIGHT_BROWSER_EXECUTABLE_PATH;
const outputDir = process.env.PLAYWRIGHT_OUTPUT_DIR ?? "test-results";

export default defineConfig({
  testDir: "./e2e",
  outputDir,
  timeout: 5 * 60 * 1000,
  expect: {
    timeout: 30 * 1000
  },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: frontendBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    launchOptions: browserExecutablePath
      ? {
          executablePath: browserExecutablePath
        }
      : undefined
  }
});
