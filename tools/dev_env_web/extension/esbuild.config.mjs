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
  external: ["vscode"],
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
