import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const frontend = dirname(fileURLToPath(import.meta.url));
const repository = resolve(frontend, "..");
const outputDir = resolve(
  process.env.FEWIA_SECURITY_OUTPUT_DIR ?? join(tmpdir(), "fewia-security-browser-artifacts"),
);
const insideRepository = relative(repository, outputDir);
if (
  insideRepository === "" ||
  (insideRepository !== ".." && !insideRepository.startsWith(`..${sep}`) && !isAbsolute(insideRepository))
) {
  throw new Error("FEWIA_SECURITY_OUTPUT_DIR MUST point outside the repository.");
}

const origin = "http://127.0.0.1:49121";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /security\.browser\.ts$/,
  outputDir,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: origin,
    browserName: "chromium",
    serviceWorkers: "block",
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  projects: [
    {
      name: "desktop-security",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "mobile-security",
      use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: [
    {
      command: "uv run --project ../backend --directory ../backend uvicorn tests.browser_security_app:app --host 127.0.0.1 --port 49122 --no-access-log",
      cwd: frontend,
      url: "http://127.0.0.1:49122/healthz",
      reuseExistingServer: false,
      env: {
        FEWIA_AUTH_MODE: "local_demo",
        FEWIA_PUBLIC_ORIGIN: origin,
        FEWIA_DATABASE_MODE: "local",
        FEWIA_TRANSPORT_MODE: "local",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 49121 --strictPort",
      cwd: frontend,
      url: origin,
      reuseExistingServer: false,
      env: { FEWIA_API_TARGET: "http://127.0.0.1:49122" },
    },
  ],
});
