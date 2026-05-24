#!/usr/bin/env node
// End-to-end probe of the "open .cvm.c → Run Debug → Pyodide compile →
// stopOnEntry" path. Runs against a serve.sh instance at localhost:3000.
//
// Stdout is JSONL with steps + any console errors.

import { chromium } from "playwright-core";

const url = process.argv[2] || "http://localhost:3000/";
const chromePath = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const emit = (o) => process.stdout.write(JSON.stringify(o) + "\n");

const browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await ctx.newPage();

page.on("console", (msg) => {
    if (msg.type() === "error" || msg.type() === "warning") {
        emit({ kind: "console", level: msg.type(), text: msg.text() });
    } else if (msg.text().includes("[tinyVm.dap")) {
        emit({ kind: "dap", text: msg.text() });
    }
});
page.on("pageerror", (err) => emit({ kind: "pageerror", text: err.message }));

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
await page.waitForSelector(".monaco-workbench", { timeout: 30_000 });
await page.waitForTimeout(4000);
emit({ step: "loaded" });

// Open count10.cvm.c via tree nav (matches breakpoint-probe.mjs).
async function clickTreeEntry(name) {
    const sel = `.explorer-folders-view [aria-label*="${name}"], .explorer-folders-view .label-name:has-text("${name}")`;
    const el = await page.waitForSelector(sel, { timeout: 5000 });
    await el.click();
    await page.waitForTimeout(300);
}
await clickTreeEntry("projects");
await clickTreeEntry("tiny_vm");
await clickTreeEntry("tests");
for (let i = 0; i < 3; i++) {
    await page.keyboard.press("ArrowDown");
    await page.waitForTimeout(60);
}
await page.keyboard.press("Enter");
await page.waitForTimeout(2000);
emit({ step: "opened-source" });

// Open command palette and run "tiny_vm: Debug Bytecode in Simulator".
await page.keyboard.press("F1");
await page.waitForTimeout(300);
await page.keyboard.type("tiny_vm: Debug Bytecode");
await page.waitForTimeout(300);
await page.keyboard.press("Enter");
emit({ step: "command-fired" });

// Wait for Pyodide to load + compile + debug session to start + stopOnEntry.
// Pyodide first-load is the slow part (CDN download + init); allow up to 60s.
const deadline = Date.now() + 60_000;
let stopped = false;
while (Date.now() < deadline) {
    const state = await page.evaluate(() => {
        // The "debug toolbar" is only visible during a debug session.
        const toolbar = document.querySelector(".debug-toolbar");
        const text = document.body.innerText;
        return {
            toolbarVisible: !!toolbar,
            hasStoppedReason: text.includes("Paused on") || text.includes("Paused at"),
            hasCompileLog: text.includes("compiled") || text.includes("Pyodide"),
        };
    });
    if (state.toolbarVisible) {
        emit({ step: "debug-toolbar-visible", ...state });
        stopped = true;
        break;
    }
    await page.waitForTimeout(1000);
}

if (!stopped) {
    emit({ step: "timed-out-waiting-for-debug-session" });
}

await page.screenshot({ path: "/tmp/debug-probe-final.png", fullPage: false });
await browser.close();
emit({ step: "done" });
