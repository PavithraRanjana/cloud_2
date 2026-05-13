#!/usr/bin/env node
/**
 * Fetches OpenAPI specs from each running service (with 2-second timeout),
 * falls back to the local /OpenAPI/*.json files, then runs openapi-typescript
 * to emit TypeScript types into src/types/<service>.ts.
 *
 * Usage:
 *   npm run generate-types           # one-shot
 *   node scripts/generate-types.mjs  # same thing
 */

import { writeFileSync, readFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const openApiDir = join(root, "..", "OpenAPI");
const typesDir = join(root, "src", "types");

/** Each entry maps a service name to its direct port and local fallback file. */
const SERVICES = [
  { name: "auth",         port: 8001, local: "openapi-2.json" },
  { name: "flight",       port: 8002, local: "openapi-3.json" },
  { name: "booking",      port: 8003, local: "openapi-4.json" },
  { name: "payment",      port: 8004, local: "openapi-5.json" },
  { name: "baggage",      port: 8005, local: "openapi-6.json" },
  { name: "checkin",      port: 8006, local: "openapi-7.json" },
  { name: "passenger",    port: 8007, local: "openapi-8.json" },
  { name: "notification", port: 8008, local: "openapi-9.json" },
];

mkdirSync(typesDir, { recursive: true });

let ok = 0;
let failed = 0;

for (const { name, port, local } of SERVICES) {
  let schema;
  let source;

  // 1. Try live service first
  try {
    const res = await fetch(`http://localhost:${port}/openapi.json`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    schema = await res.json();
    source = `http://localhost:${port}/openapi.json`;
  } catch {
    // 2. Fall back to checked-in OpenAPI file
    const fallbackPath = join(openApiDir, local);
    schema = JSON.parse(readFileSync(fallbackPath, "utf-8"));
    source = `local:${local}`;
  }

  // 3. Generate TypeScript types
  try {
    const ast = await openapiTS(schema, {
      exportType: true,
    });
    const content = [
      "// AUTO-GENERATED — do not edit by hand.",
      `// Source: ${source}`,
      "// Re-run: npm run generate-types",
      "",
      astToString(ast),
    ].join("\n");

    writeFileSync(join(typesDir, `${name}.ts`), content, "utf-8");
    console.log(`  ✓  ${name.padEnd(14)} ← ${source}`);
    ok++;
  } catch (err) {
    console.error(`  ✗  ${name}: ${err.message}`);
    failed++;
  }
}

console.log(`\n  Generated ${ok} type file(s)${failed ? `, ${failed} failed` : ""}.`);
if (failed) process.exit(1);
