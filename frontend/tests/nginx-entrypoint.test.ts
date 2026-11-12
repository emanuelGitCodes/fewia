import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const scriptPath = fileURLToPath(
  new URL("../docker-entrypoint.d/15-validate-api-upstream.sh", import.meta.url),
);
const marker = "FEWIA_REJECTED_VALUE_MARKER";

function runValidator(value: string | undefined) {
  return spawnSync("/bin/sh", [scriptPath], {
    env: value === undefined ? {} : { FEWIA_API_UPSTREAM: value },
    encoding: "utf8",
    timeout: 2000,
  });
}

describe("nginx upstream validation", () => {
  it.each(["api:8000", "127.0.0.1:8000"])(
    "accepts %s silently",
    (value) => {
      const result = runValidator(value);
      expect(result.error).toBeUndefined();
      expect(result.signal).toBeNull();
      expect(result.status).toBe(0);
      expect(result.stdout).toBe("");
      expect(result.stderr).toBe("");
    },
  );

  const rejected: { name: string; value: string | undefined }[] = [
    { name: "missing", value: undefined },
    { name: "empty", value: "" },
    { name: "other hostname", value: `${marker}:8000` },
    { name: "other port", value: "api:8001" },
    { name: "other loopback port", value: "127.0.0.1:8001" },
    { name: "uppercase hostname", value: "API:8000" },
    { name: "URL", value: "http://api:8000" },
    { name: "leading space", value: " api:8000" },
    { name: "trailing space", value: "api:8000 " },
    { name: "newline", value: `api:8000\n${marker}` },
    { name: "carriage return", value: "api:8000\r" },
    { name: "tab", value: "api:8000\t" },
    { name: "control byte", value: "api:8000\u0001" },
    { name: "semicolon", value: `api:8000; printf ${marker}` },
    { name: "command substitution", value: `api:8000$(printf ${marker})` },
    { name: "backticks", value: `api:8000\`printf ${marker}\`` },
    {
      name: "nginx config injection",
      value: `api:8000;\n}\nserver { return 200 "${marker}"; }\n#`,
    },
  ];

  it.each(rejected)("rejects $name with a static error", ({ value }) => {
    const result = runValidator(value);
    expect(result.error).toBeUndefined();
    expect(result.signal).toBeNull();
    expect(result.status).toBe(1);
    expect(result.stdout).toBe("");
    expect(result.stderr).toBe("Invalid FEWIA_API_UPSTREAM.\n");
    expect(result.stdout + result.stderr).not.toContain(marker);
  });
});

const hostCheckScriptPath = fileURLToPath(
  new URL("../docker-entrypoint.d/16-validate-host-check.sh", import.meta.url),
);

function runHostCheck(value: string | undefined) {
  return spawnSync("/bin/sh", [hostCheckScriptPath], {
    env:
      value === undefined
        ? { FEWIA_API_UPSTREAM: "api:8000" }
        : { FEWIA_API_UPSTREAM: "api:8000", FEWIA_WEB_HOST_CHECK: value },
    encoding: "utf8",
    timeout: 2000,
  });
}

describe("nginx host check selection", () => {
  it.each([
    { name: "off", value: "off" },
    { name: "local", value: "local" },
    { name: "unset", value: undefined },
  ])("accepts $name silently", ({ value }) => {
    const result = runHostCheck(value);
    expect(result.error).toBeUndefined();
    expect(result.signal).toBeNull();
    expect(result.status).toBe(0);
    expect(result.stdout).toBe("");
    expect(result.stderr).toBe("");
  });

  const rejectedModes: { name: string; value: string }[] = [
    { name: "unknown word", value: "maybe" },
    { name: "empty", value: "" },
    { name: "uppercase", value: "LOCAL" },
    { name: "newline", value: `local\n${marker}` },
    { name: "semicolon", value: `local; printf ${marker}` },
  ];

  it.each(rejectedModes)("rejects $name with a static error", ({ value }) => {
    const result = runHostCheck(value);
    expect(result.error).toBeUndefined();
    expect(result.signal).toBeNull();
    expect(result.status).toBe(1);
    expect(result.stdout).toBe("");
    expect(result.stderr).toBe("Invalid FEWIA_WEB_HOST_CHECK.\n");
    expect(result.stdout + result.stderr).not.toContain(marker);
  });
});

describe("nginx security headers", () => {
  const read = (name: string) =>
    readFileSync(fileURLToPath(new URL(`../${name}`, import.meta.url)), "utf8");
  const conf = read("nginx.conf");
  const headers = read("security-headers.conf");

  it.each([
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
  ])("sets %s with always", (name) => {
    expect(conf + headers).toMatch(new RegExp(`add_header ${name} ".+" always;`));
  });

  it("turns server tokens off", () => {
    expect(conf).toContain("server_tokens off;");
  });

  it("includes the header snippet in each location with add_header", () => {
    const include = "include /etc/nginx/security-headers.conf;";
    for (const block of conf.match(/location [^{]+\{[^}]*add_header[^}]*\}/g) ?? []) {
      expect(block).toContain(include);
    }
    expect(conf.split(include).length - 1).toBe(3);
  });
});
