// Web extension bundle. The "extension host" in vscode.dev / @vscode/test-web
// is a Web Worker, so target=webworker and format=cjs (the host loads
// extensions via importScripts / require-style globals).
//
// `vscode` is provided at runtime by the host; never inline it.
import { build, context } from "esbuild";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const watchMode = process.argv.includes("--watch");

const config = {
  entryPoints: [resolve(__dirname, "src/browser/extension.ts")],
  bundle: true,
  outfile: resolve(__dirname, "dist/web/extension.js"),
  platform: "browser",
  target: "es2022",
  format: "cjs",
  // `vscode` is provided at runtime. Pyodide imports `node:url`/`node:fs`/
  // etc. inside its `if (IN_NODE)` branch — those never execute in the
  // browser worker but esbuild needs them externalized to avoid a build
  // error. They will not be resolvable at runtime either; that's fine
  // because the IN_NODE branch is dead code in the browser.
  external: [
    "vscode",
    "node:url",
    "node:fs",
    "node:fs/promises",
    "node:path",
    "node:child_process",
    "node:vm",
    "node:crypto",
    "url",
    "fs",
    "path",
  ],
  sourcemap: true,
  logLevel: "info",
};

if (watchMode) {
  const ctx = await context(config);
  await ctx.watch();
  console.log("[esbuild] watching…");
} else {
  await build(config);
}
