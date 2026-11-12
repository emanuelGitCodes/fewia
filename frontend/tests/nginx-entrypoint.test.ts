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

describe("nginx security header values", () => {
  const lines = readFileSync(
    fileURLToPath(new URL("../security-headers.conf", import.meta.url)),
    "utf8",
  ).split("\n");

  it.each([
    [
      "Content-Security-Policy",
      "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    ],
    ["X-Content-Type-Options", "nosniff"],
    ["X-Frame-Options", "DENY"],
    ["Referrer-Policy", "no-referrer"],
    ["Permissions-Policy", "camera=(), microphone=(), geolocation=()"],
  ])("sets %s to the exact value with always", (name, value) => {
    expect(lines.filter((line) => line.startsWith(`add_header ${name} `))).toEqual([
      `add_header ${name} "${value}" always;`,
    ]);
  });
});

describe("nginx host check wiring", () => {
  const readRepoFile = (path: string) =>
    readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

  // Return the text between the braces of the block that opens at `opener`.
  function braceBody(text: string, opener: string): string {
    const start = text.indexOf(opener);
    expect(start).toBeGreaterThanOrEqual(0);
    const open = start + opener.length - 1;
    expect(text[open]).toBe("{");
    let depth = 0;
    for (let i = open; i < text.length; i += 1) {
      if (text[i] === "{") depth += 1;
      if (text[i] === "}") depth -= 1;
      if (depth === 0) return text.slice(open + 1, i);
    }
    throw new Error(`Unclosed block: ${opener}`);
  }

  it("denies with 421 before rewrite and proxy_pass in location /api/", () => {
    const block = braceBody(readRepoFile("../nginx.conf"), "location /api/ {");
    const denied = block.match(/if \(\$fewia_host_denied\) \{\s*return 421;\s*\}/);
    expect(denied).not.toBeNull();
    const deniedAt = denied?.index ?? -1;
    const rewriteAt = block.indexOf("rewrite");
    const proxyAt = block.indexOf("proxy_pass");
    expect(rewriteAt).toBeGreaterThan(deniedAt);
    expect(proxyAt).toBeGreaterThan(deniedAt);
  });

  const script = readRepoFile("../docker-entrypoint.d/17-select-host-check.sh");

  function mapLines(branch: string): string[] {
    const arm = script.match(
      new RegExp(`^ {4}${branch}\\)\\n[\\s\\S]*?<<'EOF'\\n([\\s\\S]*?)\\nEOF\\n`, "m"),
    );
    expect(arm).not.toBeNull();
    return (arm?.[1] ?? "").split("\n").map((line) => line.trim());
  }

  it("writes a deny-by-default map with only loopback hosts for local", () => {
    expect(mapLines("local")).toEqual([
      "map $host $fewia_host_denied {",
      "default 1;",
      "localhost 0;",
      "127.0.0.1 0;",
      '"[::1]" 0;',
      "}",
    ]);
  });

  it("writes an allow-all map with no host entry for off", () => {
    expect(mapLines("off")).toEqual([
      "map $host $fewia_host_denied {",
      "default 0;",
      "}",
    ]);
  });

  it("defaults the image to off", () => {
    expect(readRepoFile("../Dockerfile")).toMatch(/^ENV FEWIA_WEB_HOST_CHECK=off$/m);
  });

  it("sets local for the web service in compose.yaml", () => {
    const compose = readRepoFile("../../compose.yaml").split("\n");
    const start = compose.indexOf("  web:");
    expect(start).toBeGreaterThanOrEqual(0);
    const rest = compose.slice(start + 1);
    const end = rest.findIndex((line) => /^ {0,2}\S/.test(line));
    const web = (end === -1 ? rest : rest.slice(0, end)).join("\n");
    expect(web).toMatch(/^ {4}environment:\n(?: {6}\S.*\n)*? {6}FEWIA_WEB_HOST_CHECK: local$/m);
  });
});
