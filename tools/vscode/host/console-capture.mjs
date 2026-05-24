#!/usr/bin/env node
// Capture browser console messages, uncaught page errors, and HTTP 4xx/5xx
// responses from a URL using Playwright + the system Chrome. For dev-time
// diagnosis (no expectations, no asserts) — e2e tests live in
// tools/vscode/e2e/.
//
// Usage:
//   node tools/vscode/scripts/console-capture.mjs [url]
//
// Env vars:
//   CHROME_PATH  path to a Chromium-family browser (default /usr/bin/google-chrome)
//   WAIT_MS      ms to wait after domcontentloaded before exiting (default 6000)
//   FILTER       regex to keep only matching event text (default: keep all)
//
// Why playwright-core + system Chrome:
//   Playwright's bundled Chromium has no build for ubuntu26.04-x64 (see
//   tools/theia/theia/e2e/blink-debug.spec.ts for the same workaround on
//   the Theia side).
//
// Output: JSON Lines. Each line is a structured event:
//   {"kind":"console","level":"error","text":"…","loc":"…"}
//   {"kind":"pageerror","text":"…","stack":"…"}
//   {"kind":"requestfailed","url":"…","method":"…","reason":"…"}
//   {"kind":"response","status":404,"url":"…"}

import { chromium } from "playwright-core";

// Default to localhost (NOT 127.0.0.1): @vscode/test-web embeds the request's
// Host header in its iframe URL template, and "xyz.127.0.0.1" is not a valid
// hostname (URL parser rejects it). See scripts/serve.sh for the same gotcha.
const url = process.argv[2] || "http://localhost:3000/";
const chromePath = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const waitMs = Number.parseInt(process.env.WAIT_MS || "6000", 10);
const filter = process.env.FILTER ? new RegExp(process.env.FILTER) : null;

const emit = (event) => {
    if (filter && !filter.test(JSON.stringify(event))) return;
    process.stdout.write(JSON.stringify(event) + "\n");
};

const browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox"],
});
const ctx = await browser.newContext();
const page = await ctx.newPage();

page.on("console", (msg) => {
    const loc = msg.location();
    emit({
        kind: "console",
        level: msg.type(),
        text: msg.text(),
        loc: loc?.url ? `${loc.url}:${loc.lineNumber}` : undefined,
    });
});
page.on("pageerror", (err) => {
    emit({ kind: "pageerror", text: err.message, stack: err.stack });
});
page.on("requestfailed", (req) => {
    emit({
        kind: "requestfailed",
        url: req.url(),
        method: req.method(),
        reason: req.failure()?.errorText,
    });
});
page.on("response", (resp) => {
    const s = resp.status();
    if (s >= 400) emit({ kind: "response", status: s, url: resp.url() });
});

try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
} catch (e) {
    emit({ kind: "navigation_error", text: String(e) });
}
await new Promise((r) => setTimeout(r, waitMs));

await browser.close();
