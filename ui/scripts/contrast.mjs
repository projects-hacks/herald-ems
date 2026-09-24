// Re-checks the contrast of every token pair (docs/UX_PLAN.md §2.2 semantics; values in src/styles/tokens.css) against src/styles/tokens.css (WCAG 2.x
// relative luminance). Text needs >= 4.5:1; controls, borders and fills (non-text, WCAG 1.4.11) need >= 3:1.
// Exits non-zero on any failure. Usage: npm run contrast
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");

function block(selector) {
  const i = css.indexOf(selector + " {");
  const j = css.indexOf("}", i);
  const out = {};
  for (const m of css.slice(i, j).matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)) out[m[1]] = m[2];
  return out;
}
const themes = { dark: block('[data-theme="dark"]'), light: block('[data-theme="light"]') };

function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// [foreground, background, minimum, kind]
const TEXT = 4.5, NONTEXT = 3;
const pairs = [
  ["text-primary", "surface-1", TEXT], ["text-secondary", "surface-1", TEXT], ["text-muted", "surface-1", TEXT],
  ["text-primary", "surface-2", TEXT], ["text-muted", "surface-2", TEXT], ["text-primary", "surface-3", TEXT], ["text-muted", "surface-3", TEXT],
  ["text-primary", "bg", TEXT], ["text-secondary", "bg", TEXT], ["text-primary", "canvas", TEXT],
  ["text-secondary", "canvas", TEXT], ["text-muted", "canvas", TEXT], ["accent", "canvas", TEXT], ["accent", "surface-1", TEXT], ["accent", "surface-2", TEXT], ["on-accent", "accent", TEXT],
  ["on-accent-fill", "accent-fill", TEXT], ["accent", "accent-tint", TEXT], ["text-primary", "accent-tint", TEXT],
  ["accent-fill", "surface-1", NONTEXT], ["border-control", "surface-2", NONTEXT], ["text-muted", "bg", TEXT], ["text-secondary", "surface-2", TEXT],
  ["capture", "surface-1", TEXT], ["border-control", "surface-1", NONTEXT],
  ["high-fg", "surface-1", TEXT], ["high-on-fill", "high-fill", TEXT], ["high-fg", "high-tint", TEXT],
  ["text-primary", "high-tint", TEXT], ["high-fill", "surface-1", NONTEXT],
  ["medium-fg", "surface-1", TEXT], ["medium-on-fill", "medium-fill", TEXT], ["medium-fg", "medium-tint", TEXT],
  ["text-primary", "medium-tint", TEXT],
  ["low-fg", "surface-1", TEXT], ["low-on-fill", "low-fill", TEXT], ["low-fg", "low-tint", TEXT],
  ["text-primary", "low-tint", TEXT],
  ["ok-fg", "surface-1", TEXT], ["ok-on-fill", "ok-fill", TEXT], ["ok-fg", "ok-tint", TEXT],
  ["text-primary", "ok-tint", TEXT], ["ok-fill", "surface-1", NONTEXT],
];
// Light medium fill on white is 1.78:1 by design; its 1 px border carries the edge (§2.2).
const extra = { light: [["medium-fill-border", "surface-1", NONTEXT]] };

let failed = 0;
for (const [name, t] of Object.entries(themes)) {
  console.log(`\n${name}`);
  for (const [fg, bg, min] of [...pairs, ...(extra[name] ?? [])]) {
    if (!t[fg] || !t[bg]) { console.log(`  MISSING ${fg} or ${bg}`); failed++; continue; }
    const r = ratio(t[fg], t[bg]);
    const ok = r >= min;
    if (!ok) failed++;
    console.log(`  ${ok ? "ok  " : "FAIL"} ${fg.padEnd(18)} on ${bg.padEnd(11)} ${r.toFixed(2).padStart(6)}:1  (min ${min})`);
  }
}
console.log(failed ? `\n${failed} pair(s) below the minimum` : "\nall pairs pass");
process.exit(failed ? 1 : 0);
