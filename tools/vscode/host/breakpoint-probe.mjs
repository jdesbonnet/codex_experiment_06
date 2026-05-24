#!/usr/bin/env node
// Diagnostic: drive VS Code Web to open count10.cvm.c, attempt to set a
// breakpoint, and dump enough state for an off-line diagnosis. Writes
// screenshots to /tmp/bp-probe-*.png and a JSONL event log to stdout.
//
// Usage:
//   node host/breakpoint-probe.mjs                  # default localhost:3000
//
// Output (stdout, JSONL):
//   {"step":"loaded"}
//   {"step":"opened-file","language":"…"}
//   {"step":"toggle-breakpoint","gutterEls":N,"breakpointEls":M}
//   {"kind":"console","level":"error","text":"…"}
//   …

import { chromium } from "playwright-core";

const url = process.argv[2] || "http://localhost:3000/";
const chromePath = process.env.CHROME_PATH || "/usr/bin/google-chrome";

const emit = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

const browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await ctx.newPage();

page.on("console", (msg) => {
    if (msg.type() === "error") {
        emit({ kind: "console", level: "error", text: msg.text() });
    }
});
page.on("pageerror", (err) => {
    emit({ kind: "pageerror", text: err.message });
});

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });

// VS Code Web's UI doesn't fully settle until extension host is up. Wait
// for the activity bar to appear, then a bit longer.
await page.waitForSelector(".monaco-workbench", { timeout: 30_000 });
await page.waitForTimeout(4000);
emit({ step: "loaded" });
await page.screenshot({ path: "/tmp/bp-probe-1-loaded.png", fullPage: false });

// Open count10.cvm.c by navigating the file tree.
// Tree entries: projects > tiny_vm > tests > count10.cvm.c
async function clickTreeEntry(name) {
    const sel = `.explorer-folders-view [aria-label*="${name}"], .explorer-folders-view .label-name:has-text("${name}")`;
    const el = await page.waitForSelector(sel, { timeout: 5000 });
    await el.click();
    await page.waitForTimeout(400);
}
try {
    await clickTreeEntry("projects");
    await clickTreeEntry("tiny_vm");
    await clickTreeEntry("tests");
    // tests is selected and expanded. Move down with arrows to land on
    // count10.cvm.c; this also scrolls the tree as needed. Tests directory
    // has 8 files starting with checksum8, collatz_max, count10, ...
    for (let i = 0; i < 3; i++) {
        await page.keyboard.press("ArrowDown");
        await page.waitForTimeout(60);
    }
    // Enter opens the highlighted file in the editor.
    await page.keyboard.press("Enter");
} catch (e) {
    emit({ step: "tree-nav-failed", text: String(e) });
}
await page.waitForTimeout(3000);
emit({ step: "opened-file" });
await page.screenshot({ path: "/tmp/bp-probe-2-opened.png", fullPage: false });

// Inspect the editor: language indicator (status bar), gutter elements,
// breakpoint affordance.
const editorState = await page.evaluate(() => {
    // Language indicator
    const langLabels = Array.from(
        document.querySelectorAll(".statusbar-item .label-name, .statusbar-item"),
    )
        .map((el) => el.textContent?.trim())
        .filter((t) => t && t.length < 40);
    // Gutter elements
    const gutters = document.querySelectorAll(".monaco-editor .margin-view-overlays");
    const lineNumbers = document.querySelectorAll(".monaco-editor .line-numbers");
    const breakpoints = document.querySelectorAll(".monaco-editor .codicon-debug-breakpoint, .monaco-editor .codicon-debug-breakpoint-unverified, .monaco-editor .codicon-debug-hint");
    const glyphMargin = document.querySelector(".monaco-editor .glyph-margin");
    return {
        langLabels: langLabels.slice(0, 30),
        nGutter: gutters.length,
        nLineNumbers: lineNumbers.length,
        nBreakpoints: breakpoints.length,
        hasGlyphMargin: !!glyphMargin,
        glyphMarginRect: glyphMargin
            ? {
                  x: glyphMargin.getBoundingClientRect().x,
                  y: glyphMargin.getBoundingClientRect().y,
                  w: glyphMargin.getBoundingClientRect().width,
                  h: glyphMargin.getBoundingClientRect().height,
              }
            : null,
    };
});
emit({ step: "editor-state", ...editorState });

// Try to toggle breakpoint at the current cursor line via F9 (the keyboard
// shortcut that's wired to editor.debug.action.toggleBreakpoint).
// First click on a line to put cursor there.
await page.keyboard.press("Control+Home");
await page.waitForTimeout(200);
// Move down to a printf-like line (line 7 in count10.cvm.c is the led_write
// /print/delay area; just go to line 4).
await page.keyboard.press("ArrowDown");
await page.keyboard.press("ArrowDown");
await page.keyboard.press("ArrowDown");
await page.waitForTimeout(200);
await page.keyboard.press("F9");
await page.waitForTimeout(800);
emit({ step: "f9-toggled" });
await page.screenshot({ path: "/tmp/bp-probe-3-after-f9.png", fullPage: false });

const afterF9 = await page.evaluate(() => {
    const breakpoints = document.querySelectorAll(
        ".monaco-editor .codicon-debug-breakpoint, .monaco-editor .codicon-debug-breakpoint-unverified, .monaco-editor .codicon-debug-hint",
    );
    return { nBreakpoints: breakpoints.length };
});
emit({ step: "f9-result", ...afterF9 });

// Try clicking in the glyph margin directly.
const margin = await page.evaluate(() => {
    const gm = document.querySelector(".monaco-editor .glyph-margin");
    if (!gm) return null;
    const r = gm.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
});
if (margin && margin.w > 0) {
    // Click roughly on line 4 in the glyph margin: offset ~ line-height * 3.
    const clickX = margin.x + margin.w / 2;
    const clickY = margin.y + 3 * 19 + 9; // 19px line-height is the VS Code default
    await page.mouse.click(clickX, clickY);
    await page.waitForTimeout(800);
    emit({ step: "gutter-clicked", clickX, clickY });
    await page.screenshot({ path: "/tmp/bp-probe-4-after-click.png", fullPage: false });
    const afterClick = await page.evaluate(() => {
        const breakpoints = document.querySelectorAll(
            ".monaco-editor .codicon-debug-breakpoint, .monaco-editor .codicon-debug-breakpoint-unverified, .monaco-editor .codicon-debug-hint",
        );
        return { nBreakpoints: breakpoints.length };
    });
    emit({ step: "gutter-click-result", ...afterClick });
}

await browser.close();
emit({ step: "done" });
