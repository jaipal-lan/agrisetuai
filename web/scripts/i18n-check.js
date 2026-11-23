#!/usr/bin/env node
/*
 * Localization guard (QA Suite tab 10).
 *
 * Static, dependency-free check over web/lib/i18n.js. Fails (exit 1) if:
 *   1. Coverage parity — any key present in `en` is missing from `te` or `hi`
 *      (and vice-versa), so no user ever falls back to another language.
 *   2. snake_case leak — any *value* still looks like a raw enum/key
 *      (e.g. "payment_pending", "pass_with_adjustment") instead of a
 *      human, translated string reaching the UI.
 *   3. Empty values — a key defined with an empty string.
 *
 * Run: `npm run i18n-check` (also wired into CI).
 */
const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "..", "lib", "i18n.js");
const src = fs.readFileSync(FILE, "utf8");

// --- Extract the STRINGS object literal by brace-matching ---
const start = src.indexOf("const STRINGS = {");
if (start === -1) {
  console.error("i18n-check: could not find `const STRINGS = {` in", FILE);
  process.exit(1);
}
const braceStart = src.indexOf("{", start);
let depth = 0,
  end = -1,
  inStr = null;
for (let i = braceStart; i < src.length; i++) {
  const c = src[i];
  if (inStr) {
    if (c === "\\") i++; // skip escaped char
    else if (c === inStr) inStr = null;
    continue;
  }
  if (c === '"' || c === "'" || c === "`") inStr = c;
  else if (c === "{") depth++;
  else if (c === "}") {
    depth--;
    if (depth === 0) {
      end = i;
      break;
    }
  }
}
if (end === -1) {
  console.error("i18n-check: could not brace-match the STRINGS object.");
  process.exit(1);
}
const objText = src.slice(braceStart, end + 1);

let STRINGS;
try {
  // Pure object literal of string values + nested string maps — no calls.
  STRINGS = new Function("return (" + objText + ")")();
} catch (e) {
  console.error("i18n-check: failed to parse STRINGS object:", e.message);
  process.exit(1);
}

const langs = Object.keys(STRINGS);
const expected = ["te", "en", "hi"];
for (const l of expected) {
  if (!langs.includes(l)) {
    console.error(`i18n-check: missing language block "${l}".`);
    process.exit(1);
  }
}

// Flatten nested maps (enum groups) to dotted keys.
function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      Object.assign(out, flatten(v, key));
    } else {
      out[key] = v;
    }
  }
  return out;
}

const flat = Object.fromEntries(expected.map((l) => [l, flatten(STRINGS[l])]));

const errors = [];

// 1. Coverage parity against the union of all keys.
const allKeys = new Set();
for (const l of expected) Object.keys(flat[l]).forEach((k) => allKeys.add(k));
for (const key of allKeys) {
  for (const l of expected) {
    if (!(key in flat[l])) errors.push(`missing [${l}] key: ${key}`);
  }
}

// 2 & 3. Value sanity. snake_case = two+ lowercase runs joined by "_".
//     Allow a short allowlist of legitimately code-like tokens.
const SNAKE = /^[a-z0-9]+(_[a-z0-9]+)+$/;
const ALLOW = new Set(["te", "en", "hi"]); // language self-labels etc.
for (const l of expected) {
  for (const [key, val] of Object.entries(flat[l])) {
    if (typeof val !== "string") {
      errors.push(`non-string value [${l}] ${key}: ${JSON.stringify(val)}`);
      continue;
    }
    if (val.trim() === "") errors.push(`empty value [${l}] ${key}`);
    if (SNAKE.test(val.trim()) && !ALLOW.has(val.trim())) {
      errors.push(`snake_case value leaking to UI [${l}] ${key} = "${val}"`);
    }
  }
}

const counts = expected.map((l) => `${l}:${Object.keys(flat[l]).length}`).join("  ");
if (errors.length) {
  console.error(`\ni18n-check FAILED — ${errors.length} issue(s)\n`);
  errors.slice(0, 50).forEach((e) => console.error("  • " + e));
  if (errors.length > 50) console.error(`  … and ${errors.length - 50} more`);
  console.error(`\nkey counts: ${counts}`);
  process.exit(1);
}

console.log(`i18n-check PASSED — keys balanced across te/en/hi, no snake_case/empty leaks.`);
console.log(`key counts: ${counts}`);
