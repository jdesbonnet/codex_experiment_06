import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

/**
 * Playwright config for the tiny_vm IDE e2e tests.
 *
 * Uses the system Google Chrome at /usr/bin/google-chrome because
 * Playwright's bundled Chromium does not ship a build for ubuntu26.04-x64
 * (the host this repo currently runs on).
 *
 * The repo root is passed as the Theia workspace so files like
 * projects/tiny_vm/demos/blink.cvm.c are reachable from the navigator
 * and quick-open.
 */
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const THEIA_PORT = process.env.THEIA_PORT || '3001';
const THEIA_URL = process.env.THEIA_URL || `http://127.0.0.1:${THEIA_PORT}`;

export default defineConfig({
    testDir: './e2e',
    timeout: 240_000,
    expect: { timeout: 15_000 },
    fullyParallel: false,
    workers: 1,
    reporter: [['list'], ['html', { outputFolder: 'e2e/report', open: 'never' }]],
    use: {
        baseURL: THEIA_URL,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: process.env.RECORD_VIDEO
            ? { mode: 'on', size: { width: 1400, height: 900 } }
            : 'off',
        actionTimeout: 15_000,
        navigationTimeout: 60_000
    },
    webServer: {
        // Run via npx so we can pass the workspace positional argument; the
        // browser-app's start script hard-codes the port and hostname but
        // does not set a workspace.
        command: `npx theia start ${REPO_ROOT} --hostname 127.0.0.1 --port ${THEIA_PORT}`,
        cwd: path.join(__dirname, 'browser-app'),
        url: THEIA_URL,
        reuseExistingServer: true,
        timeout: 180_000,
        stdout: 'pipe',
        stderr: 'pipe'
    },
    projects: [
        {
            name: 'chrome-system',
            use: {
                ...devices['Desktop Chrome'],
                viewport: { width: 1400, height: 900 },
                channel: undefined,
                launchOptions: {
                    executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
                    args: ['--no-sandbox', '--disable-dev-shm-usage']
                }
            }
        }
    ]
});
