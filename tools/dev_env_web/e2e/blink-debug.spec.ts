import { test, expect, Page } from "@playwright/test";
import * as path from "node:path";
import * as fs from "node:fs";

/**
 * End-to-end: open blink.cvm.c, start a debug session via the
 * tinyVm.debugBytecode command (which compiles through the
 * /api/compile sidecar, writes the .bin into OPFS, and launches DAP
 * against the wasm sim), step through, then stop the session.
 *
 * Mirrors tools/dev_env/theia/e2e/blink-debug.spec.ts for the Theia
 * implementation.
 */

const HERE = __dirname;
const REPO_ROOT = path.resolve(HERE, "..", "..", "..");
const BLINK_PATH = path.join(REPO_ROOT, "projects", "tiny_vm", "demos", "blink.cvm.c");
const SNAPSHOT_DIR = path.join(HERE, "snapshots");

if (!fs.existsSync(BLINK_PATH)) {
    throw new Error(`fixture missing: ${BLINK_PATH}`);
}
fs.mkdirSync(SNAPSHOT_DIR, { recursive: true });

async function snap(page: Page, name: string): Promise<void> {
    await page.screenshot({ path: path.join(SNAPSHOT_DIR, `${name}.png`), fullPage: false });
}

async function waitForWorkbench(page: Page): Promise<void> {
    await page.waitForSelector(".monaco-workbench", { timeout: 90_000 });
    // VS Code Web takes a moment after the workbench renders to register
    // extension commands and the OPFS provider.
    await page.waitForTimeout(3000);
}

/**
 * Open projects/tiny_vm/demos/blink.cvm.c via the file explorer.
 *
 * Note: Quick Open (Ctrl+P) doesn't index virtual-fs files in
 * @vscode/test-web's mount, so we navigate the tree manually. The
 * `tests/` row is selected before blink so we expand `demos/` instead.
 */
async function openBlink(page: Page): Promise<void> {
    async function clickEntry(name: string): Promise<void> {
        const sel = `.explorer-folders-view .label-name:has-text("${name}")`;
        await page.waitForSelector(sel, { timeout: 10_000 });
        await page.locator(sel).first().click();
        await page.waitForTimeout(400);
    }
    await clickEntry("projects");
    await clickEntry("tiny_vm");
    await clickEntry("demos");
    // After expanding demos, blink.cvm.c is its first (and only) child.
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    // Wait for the editor tab to actually open.
    await page
        .locator(`.tab .label-name:has-text("blink.cvm.c")`)
        .first()
        .waitFor({ state: "visible", timeout: 15_000 });
}

async function runCommand(page: Page, query: string): Promise<void> {
    await page.keyboard.press("F1");
    const input = page.locator(".quick-input-widget input").first();
    await input.waitFor({ state: "visible", timeout: 10_000 });
    await page.keyboard.type(query, { delay: 15 });
    await page.waitForTimeout(500);
    await page.keyboard.press("Enter");
}

/**
 * Wait for the debug toolbar to appear (the floating bar with continue /
 * step / restart / stop). It's only present when a debug session is
 * active AND a thread is in a known state.
 */
async function waitForDebugToolbar(page: Page): Promise<void> {
    await page.waitForSelector(".debug-toolbar", { timeout: 60_000 });
}

/**
 * Read the currently-highlighted source line in the active editor. VS
 * Code renders the "stopped at" line by snapping the editor cursor and
 * rendering a top-of-line decoration; the status bar's "Ln X, Col Y"
 * indicator is the most stable way to read it without dipping into the
 * undocumented decoration DOM.
 */
async function readActiveLine(page: Page): Promise<number | null> {
    // Status bar shows "Ln 6, Col 1" when the cursor is on line 6.
    const text = await page.locator("body").innerText();
    const m = text.match(/Ln\s+(\d+),\s+Col\s+\d+/);
    return m ? parseInt(m[1], 10) : null;
}

test("blink.cvm.c: open, debug, step through source lines", async ({ page }) => {
    test.setTimeout(180_000);

    await page.goto("/");
    await waitForWorkbench(page);
    await snap(page, "01-workbench");

    await openBlink(page);
    await snap(page, "02-file-open");

    // Sanity: the active editor language should be tiny_vm C. The status
    // bar renders it somewhere; the exact selector varies across VS Code
    // versions, so just grep the page text.
    const bodyText = await page.locator("body").innerText();
    expect(bodyText, "expected 'tiny_vm C' language indicator in status bar")
        .toContain("tiny_vm C");

    await runCommand(page, "tiny_vm: Debug Bytecode in Simulator");
    await waitForDebugToolbar(page);
    // Give VS Code a moment to snap the cursor to the stopped line.
    await page.waitForTimeout(800);
    await snap(page, "03-stopped-at-entry");

    // The first source-map entry for blink.cvm.c lives at `while (1) {`
    // (the const declarations compile to no runtime bytecode). We assert
    // less specifically: any non-null line number means stopOnEntry put
    // us inside the source.
    const entryLine = await readActiveLine(page);
    expect(
        entryLine,
        `expected stopOnEntry to snap the cursor to a source line, got ${entryLine}`,
    ).not.toBeNull();
    expect(entryLine!).toBeGreaterThan(0);

    // Step over 5 times. blink is an infinite loop, so the highlighted
    // line should move across at least two distinct lines.
    const visited: number[] = [entryLine!];
    for (let i = 1; i <= 5; i++) {
        await page.keyboard.press("F10");
        await page.waitForTimeout(700);
        const line = await readActiveLine(page);
        if (line !== null) visited.push(line);
        await snap(page, `04-step-${i}-line${line ?? "?"}`);
    }
    expect(
        new Set(visited).size,
        `expected >1 distinct stopped lines across steps, got ${JSON.stringify(visited)}`,
    ).toBeGreaterThan(1);

    // Stop the session cleanly. blink never halts.
    await runCommand(page, "Debug: Stop");
    await page.waitForTimeout(1000);
    await snap(page, "05-disconnected");
    // VS Code keeps the toolbar element in the DOM and just hides it on
    // session end (aria-hidden). Either hidden or detached counts.
    await expect(page.locator(".debug-toolbar")).toBeHidden({ timeout: 10_000 });
});
