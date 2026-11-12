/** @vitest-environment node */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const mainPath = resolve(dirname(fileURLToPath(import.meta.url)), "main.tsx");
const source = readFileSync(mainPath, "utf8");
const fontPaths = [...source.matchAll(/import\s+["'](@fontsource[^"']*)["']/g)].map(
  (match) => match[1] as string,
);

describe("font subsets", () => {
  it("imports only latin subset css files", () => {
    expect(fontPaths.length).toBeGreaterThan(0);
    for (const path of fontPaths) {
      expect(path).toMatch(/latin-\d+\.css$/);
    }
  });

  it("imports the expected latin faces", () => {
    expect(fontPaths).toEqual(
      expect.arrayContaining([
        "@fontsource/lora/latin-400.css",
        "@fontsource/source-sans-3/latin-400.css",
        "@fontsource/source-sans-3/latin-600.css",
      ]),
    );
  });
});
