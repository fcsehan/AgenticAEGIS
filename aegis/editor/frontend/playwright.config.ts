import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: "http://127.0.0.1:18101",
    trace: "retain-on-failure",
    actionTimeout: 10000,
  },
  webServer: {
    command: `${process.env.AEGIS_TEST_PYTHON ?? "python3"} ../../../tests/editor/serve_web_e2e.py`,
    url: "http://127.0.0.1:18101/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
