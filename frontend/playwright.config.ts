import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.pw\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI === "true" ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:5180",
    browserName: "chromium",
    trace: "off",
  },
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 5180 --strictPort",
    url: "http://127.0.0.1:5180",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      FEWIA_API_TARGET: "http://127.0.0.1:9",
    },
  },
  projects: [
    {
      name: "desktop",
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: "mobile",
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
});
