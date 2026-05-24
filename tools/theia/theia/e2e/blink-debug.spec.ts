import { test, expect, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

/**
 * End-to-end test: open blink.cvm.c in the tiny_vm Theia IDE, start a debug
 * session in the host-side simulator, and step through the source line by
 * line. Verifies that line numbers advance and the session can be paused.
 *
 * Theia is launched by Playwright's `webServer` config-side (see
 * playwright.config.ts) with the repo root as the workspace, so files
 * resolve relative to <repo>/projects/tiny_vm/demos/blink.cvm.c.
 */

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const BLINK_PATH = path.join(REPO_ROOT, 'projects', 'tiny_vm', 'demos', 'blink.cvm.c');
const SNAPSHOT_DIR = path.join(__dirname, 'snapshots');

if (!fs.existsSync(BLINK_PATH)) {
    throw new Error(`fixture missing: ${BLINK_PATH}`);
}
fs.mkdirSync(SNAPSHOT_DIR, { recursive: true });

const SLOW = !!process.env.RECORD_VIDEO;
const SLOW_PAUSE_MS = SLOW ? 1500 : 200;

async function snap(page: Page, name: string): Promise<void> {
    const file = path.join(SNAPSHOT_DIR, `${name}.png`);
    await page.screenshot({ path: file, fullPage: false });
    if (SLOW) {
        await page.waitForTimeout(SLOW_PAUSE_MS);
    }
}

async function waitForWorkbench(page: Page): Promise<void> {
    await page.waitForSelector('.theia-ApplicationShell', { timeout: 90_000 });
    // Theia takes a moment after the shell appears to finish wiring contributions.
    await page.waitForLoadState('networkidle').catch(() => undefined);
    await page.waitForTimeout(1500);
}

async function typeIntoQuickInput(page: Page, text: string): Promise<void> {
    const input = page.locator('.quick-input-widget input').first();
    await input.waitFor({ state: 'visible', timeout: 10_000 });
    await input.click();
    // Some Theia Monaco inputs reject .fill(); slow per-char typing works.
    await page.keyboard.type(text, { delay: 20 });
}

async function runCommand(page: Page, query: string): Promise<void> {
    await page.keyboard.press('F1');
    await typeIntoQuickInput(page, query);
    await page.waitForTimeout(600);
    await page.keyboard.press('Enter');
}

async function openFileQuickly(page: Page, fileName: string): Promise<void> {
    await page.keyboard.press('Control+P');
    await typeIntoQuickInput(page, fileName);
    await page.waitForTimeout(1200);
    await page.keyboard.press('Enter');
    // Tab labels in Theia 1.71 are .lm-TabBar-tabLabel (lumino).
    await page
        .locator(
            '.lm-TabBar-tabLabel, .p-TabBar-tabLabel, .theia-tab-icon-label, [class*="TabBar-tabLabel"]'
        )
        .filter({ hasText: fileName })
        .first()
        .waitFor({ state: 'visible', timeout: 20_000 });
}

async function readCallStackLine(page: Page): Promise<string | null> {
    // Theia debug stack frames are rendered as tree nodes. The DAP server
    // names each frame "line N" (or "pc=0xNNNN" if no source map). Grab
    // whatever the topmost frame label is.
    const candidates = [
        '.theia-debug-stack-frames .theia-TreeNode .theia-TreeNodeContent',
        '.debug-call-stack .theia-TreeNodeContent',
        '[id*="debug.threads"] .theia-TreeNode .theia-TreeNodeContent'
    ];
    for (const sel of candidates) {
        const items = page.locator(sel);
        const n = await items.count();
        if (n === 0) {
            continue;
        }
        for (let i = 0; i < n; i++) {
            const t = (await items.nth(i).innerText()).trim();
            const m = t.match(/(line\s+\d+|pc=0x[0-9a-fA-F]+)/);
            if (m) {
                return m[1];
            }
        }
    }
    // Fall back to scanning the whole page for a frame-like label.
    const body = await page.locator('body').innerText();
    const m = body.match(/(line\s+\d+|pc=0x[0-9a-fA-F]+)/);
    return m ? m[1] : null;
}

async function waitForStoppedAt(page: Page, attempt: number): Promise<string> {
    // Poll the call-stack label for up to 15s. We accept any "line N" / "pc=…"
    // label change between attempts so the function is also useful on the
    // initial stop.
    const deadline = Date.now() + 15_000;
    let last: string | null = null;
    while (Date.now() < deadline) {
        const v = await readCallStackLine(page);
        if (v) {
            return v;
        }
        last = v;
        await page.waitForTimeout(300);
    }
    throw new Error(`attempt ${attempt}: no debug call-stack frame visible`);
}

test('blink.cvm.c: open, debug, step through source lines', async ({ page }) => {
    test.setTimeout(180_000);

    await page.goto('/');
    await waitForWorkbench(page);
    await snap(page, '01-workbench');

    await openFileQuickly(page, 'blink.cvm.c');
    await snap(page, '02-file-open');

    // Start the debug session via our extension command. Theia matches
    // commands by label, so "tiny_vm: Debug" should yield exactly one hit.
    await runCommand(page, 'tiny_vm: Debug Current File in Simulator');
    await snap(page, '03-debug-started');

    // The first stop should be on entry (we always set stopOnEntry for
    // tinyVm.debugInSim).
    const initialLine = await waitForStoppedAt(page, 0);
    await snap(page, '04-stopped-at-entry');
    expect(initialLine).toMatch(/(line\s+\d+|pc=0x[0-9a-fA-F]+)/);

    // Step through five times. blink is an infinite loop, so every step
    // should land us on a new source line within the body of the while.
    const visited: string[] = [initialLine];
    for (let i = 1; i <= 5; i++) {
        if (SLOW) {
            await page.waitForTimeout(800);
        }
        await page.keyboard.press('F10');
        // Give the DAP server time to dispatch the stopped event and the
        // call-stack to repaint.
        await page.waitForTimeout(SLOW ? 1200 : 500);
        const cur = await waitForStoppedAt(page, i);
        visited.push(cur);
        await snap(page, `05-step-${i}-${cur.replace(/\s+/g, '-')}`);
    }

    console.log('visited frames:', visited);

    // Sanity checks:
    // 1. At least one transition between distinct frames happened.
    const distinct = new Set(visited);
    expect(distinct.size, `expected to visit >1 distinct frames, got ${[...distinct]}`).toBeGreaterThan(1);
    // 2. We saw at least one labelled source line (not just raw pc).
    const sawLine = visited.some(v => /^line\s+\d+$/.test(v));
    expect(sawLine, `expected at least one "line N" frame, got ${visited.join(', ')}`).toBe(true);

    // Stop the session cleanly. blink never halts.
    await runCommand(page, 'Debug: Stop');
    await page.waitForTimeout(1000);
    await snap(page, '06-disconnected');
});
