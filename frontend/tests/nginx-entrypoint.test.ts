import { spawnSync } from "node:child_process";
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
