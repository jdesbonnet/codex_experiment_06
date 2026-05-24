import { defineConfig, devices } from "@playwright/test";
import * as path from "node:path";

// Playwright loads this config as CommonJS, so __dirname is fine.
const HERE = __dirname;
const REPO_ROOT = path.resolve(HERE, "..", "..", "..");
const SERVE_SH = path.join(REPO_ROOT, "tools", "vscode", "scripts", "serve.sh");

const IDE_URL = process.env.IDE_URL || "http://localhost:3000/";
const CHROME_PATH = process.env.CHROME_PATH || "/usr/bin/google-chrome";

/**
 * Uses the system Google Chrome at /usr/bin/google-chrome because
 * Playwright's bundled Chromium does not ship a build for ubuntu26.04-x64
 * (same workaround as tools/theia/theia/playwright.config.ts).
 *
 * The serve.sh script starts both @vscode/test-web (port 3000) and the
 * compile-server sidecar (port 3001). Its EXIT trap kills the sidecar
 * when Playwright stops it.
 */
export default defineConfig({
    testDir: ".",
    timeout: 240_000,
    expect: { timeout: 15_000 },
    fullyParallel: false,
    workers: 1,
    reporter: [
        ["list"],
        ["html", { outputFolder: "report", open: "never" }],
    ],
    use: {
        baseURL: IDE_URL,
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        actionTimeout: 15_000,
        navigationTimeout: 60_000,
    },
    projects: [
        {
            name: "chrome-system",
            use: {
                ...devices["Desktop Chrome"],
                channel: undefined,
                launchOptions: { executablePath: CHROME_PATH },
                viewport: { width: 1280, height: 800 },
            },
        },
    ],
    webServer: {
        command: `bash ${SERVE_SH}`,
        url: IDE_URL,
        // First run downloads ~50 MB of VS Code Web; allow generous time.
        timeout: 180_000,
        reuseExistingServer: true,
    },
});
