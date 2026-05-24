#!/usr/bin/env node
// Sidecar HTTP service for the tiny_vm VS Code Web IDE.
//
// In dev, this runs alongside @vscode/test-web on a separate port and
// invokes tools/vm_cc.py via child_process. In production (cloud-hosted),
// the same protocol is served by a remote endpoint; the extension flips
// `tinyVm.apiUrl` and the wire format stays identical.
//
// Endpoints:
//   GET  /api/health          -> { ok: true }
//   POST /api/compile         -> compile a .cvm.c source
//     body: { source: string, name?: string }
//     200:  { bytecodeBase64, sourceMap, assembly }
//     4xx:  { error: string, detail?: string }
//
// CORS allows the configured FRONTEND_ORIGIN (default http://localhost:3000)
// because the browser fetches from a different port.
//
// Env:
//   PORT             default 3001
//   HOST             default 127.0.0.1
//   REPO_ROOT        absolute path to the repo root (default auto-detected)
//   FRONTEND_ORIGIN  default http://localhost:3000

import http from "node:http";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";

const __filename = fileURLToPath(import.meta.url);
const HERE = path.dirname(__filename);
const REPO_ROOT = process.env.REPO_ROOT || path.resolve(HERE, "../../..");
const PORT = parseInt(process.env.PORT || "3001", 10);
const HOST = process.env.HOST || "127.0.0.1";
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || "http://localhost:3000";

const VM_CC = path.join(REPO_ROOT, "tools", "vm_cc.py");

// CORS: the extension host worker's origin is whatever VS Code Web's
// {{uuid}} subdomain template produced, e.g. http://abc-123.localhost:3000.
// A static allowlist on FRONTEND_ORIGIN won't match. Reflect any localhost-
// family origin in dev. In production this becomes a real allowlist.
function setCors(req, res) {
    const origin = req.headers.origin || "";
    const allowed =
        /^https?:\/\/([a-z0-9-]+\.)*localhost(:\d+)?$/i.test(origin) ||
        /^https?:\/\/127\.0\.0\.1(:\d+)?$/.test(origin) ||
        origin === FRONTEND_ORIGIN;
    if (allowed && origin) {
        res.setHeader("Access-Control-Allow-Origin", origin);
        res.setHeader("Vary", "Origin");
    }
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

function writeJson(req, res, status, body) {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json");
    setCors(req, res);
    res.end(JSON.stringify(body));
}

async function readJsonBody(req, limitBytes = 1_000_000) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        let total = 0;
        req.on("data", (chunk) => {
            total += chunk.length;
            if (total > limitBytes) {
                req.destroy(new Error(`body too large (>${limitBytes} bytes)`));
                return;
            }
            chunks.push(chunk);
        });
        req.on("error", reject);
        req.on("end", () => {
            try {
                const text = Buffer.concat(chunks).toString("utf-8");
                resolve(text ? JSON.parse(text) : {});
            } catch (e) {
                reject(e);
            }
        });
    });
}

function runVmCc(srcPath, binPath) {
    return new Promise((resolve, reject) => {
        const proc = spawn(
            "python3",
            [VM_CC, srcPath, "-o", binPath, "--map"],
            { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] },
        );
        let stdout = "";
        let stderr = "";
        proc.stdout.on("data", (b) => (stdout += b.toString("utf-8")));
        proc.stderr.on("data", (b) => (stderr += b.toString("utf-8")));
        proc.on("error", reject);
        proc.on("close", (code) => {
            if (code === 0) resolve({ stdout, stderr });
            else reject(new Error(`vm_cc.py exit ${code}: ${stderr || stdout}`));
        });
    });
}

async function handleCompile(req, res) {
    let body;
    try {
        body = await readJsonBody(req);
    } catch (e) {
        return writeJson(req, res, 400, { error: "invalid request body", detail: String(e) });
    }
    const source = typeof body.source === "string" ? body.source : "";
    if (!source) {
        return writeJson(req, res, 400, { error: "missing source" });
    }
    const name = typeof body.name === "string" ? body.name : "input.cvm.c";

    // Stage source + outputs in a per-request temp directory so concurrent
    // compiles don't collide.
    const id = randomBytes(8).toString("hex");
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), `tinyvm-compile-${id}-`));
    const srcPath = path.join(dir, "input.cvm.c");
    const binPath = path.join(dir, "out.bin");
    const mapPath = binPath + ".map";

    try {
        await fs.writeFile(srcPath, source, "utf-8");
        await runVmCc(srcPath, binPath);
        const bin = await fs.readFile(binPath);
        const mapText = await fs.readFile(mapPath, "utf-8");
        // The source name in the map JSON came from the input path. Rewrite
        // it to the caller's desired name so source-map -> source-file lookup
        // works in the IDE.
        let sourceMap;
        try {
            sourceMap = JSON.parse(mapText);
            sourceMap.source = name;
        } catch {
            sourceMap = null;
        }
        return writeJson(req, res, 200, {
            bytecodeBase64: bin.toString("base64"),
            sourceMap,
            assembly: null, // omit for now; can wire vm_cc -S later
        });
    } catch (e) {
        return writeJson(req, res, 400, {
            error: "compile failed",
            detail: String(e?.message ?? e),
        });
    } finally {
        // Best-effort cleanup. Ignore errors (e.g. partial-write paths).
        fs.rm(dir, { recursive: true, force: true }).catch(() => {});
    }
}

async function handleRequest(req, res) {
    if (req.method === "OPTIONS") {
        setCors(req, res);
        res.statusCode = 204;
        return res.end();
    }
    if (req.url === "/api/health" && req.method === "GET") {
        return writeJson(req, res, 200, { ok: true, repoRoot: REPO_ROOT });
    }
    if (req.url === "/api/compile" && req.method === "POST") {
        return handleCompile(req, res);
    }
    writeJson(req, res, 404, { error: "not found" });
}

// Listen on both IPv4 and IPv6 loopback. Chrome/Firefox resolve `localhost`
// to ::1 on most modern systems; binding only to 127.0.0.1 silently leaves
// browser fetches with ERR_CONNECTION_REFUSED while curl still works.
//
// Two HTTP server instances rather than `'::' + dual-stack` because the
// dual-stack option leaks LAN exposure on systems where IPV6_V6ONLY isn't
// the default.
function bind(host, label) {
    const s = http.createServer(handleRequest);
    s.on("error", (e) => {
        if (e.code === "EADDRINUSE") {
            console.error(`[compile-server] ${label} ${host}:${PORT} in use — is another instance running?`);
            process.exit(1);
        } else {
            console.error(`[compile-server] ${label} error:`, e);
        }
    });
    s.listen(PORT, host, () => {
        console.log(`[compile-server] listening on ${label} ${host}:${PORT}`);
    });
    return s;
}
bind("127.0.0.1", "IPv4");
bind("::1", "IPv6");
console.log(
    `[compile-server] repo=${REPO_ROOT}, frontend=${FRONTEND_ORIGIN}`,
);
