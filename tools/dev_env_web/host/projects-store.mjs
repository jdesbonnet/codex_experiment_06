// Filesystem-backed project store for the tiny_vm cloud API.
//
// Layout (configurable via TINYVM_PROJECTS_DIR; default ~/.tinyvm-projects):
//   <root>/
//     <uuid>/
//       meta.json              # { id, name, createdAt, modifiedAt }
//       files/                 # tree of user files
//         hello.cvm.c
//         lib/util.cvm.c
//
// Design choices:
// - UUIDs (server-generated) so the same scheme works post-auth without
//   user-namespacing path changes.
// - Atomic writes via tmp + rename, so a crashed write does not leave
//   half-written files.
// - Path normalization rejects `..`, empty segments, and backslashes.
//   The Spring migration target reads the same on-disk layout — keep
//   the normalization in one place so the Java port reads identical
//   bytes back.

import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { randomUUID } from "node:crypto";

const DEFAULT_ROOT = path.join(os.homedir(), ".tinyvm-projects");

export class NotFound extends Error {
    constructor(msg) {
        super(msg);
        this.code = 404;
    }
}
export class BadInput extends Error {
    constructor(msg) {
        super(msg);
        this.code = 400;
    }
}

const UUID_RE =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isUuid = (s) => typeof s === "string" && UUID_RE.test(s);

/**
 * Normalize a posix-style relative path. Returns null if the path
 * escapes the project root (.. segments, absolute, backslashes, NUL).
 */
export function safePath(p) {
    if (typeof p !== "string" || p.length === 0) return null;
    if (p.startsWith("/")) return null;
    if (p.includes("\\") || p.includes("\0")) return null;
    const parts = p.split("/");
    for (const seg of parts) {
        if (seg === "" || seg === "." || seg === "..") return null;
    }
    return parts.join("/");
}

export class ProjectsStore {
    constructor(root) {
        this.root = root ?? process.env.TINYVM_PROJECTS_DIR ?? DEFAULT_ROOT;
    }

    async ensureRoot() {
        await fs.mkdir(this.root, { recursive: true });
    }

    // ---- projects ---------------------------------------------------------

    async listProjects() {
        await this.ensureRoot();
        const dirents = await fs.readdir(this.root, { withFileTypes: true });
        const out = [];
        for (const d of dirents) {
            if (!d.isDirectory()) continue;
            if (!isUuid(d.name)) continue;
            try {
                out.push(await this.readMeta(d.name));
            } catch {
                // Skip malformed projects (no meta.json) rather than fail
                // the whole listing.
            }
        }
        out.sort((a, b) => b.modifiedAt.localeCompare(a.modifiedAt));
        return out;
    }

    async createProject(name) {
        if (typeof name !== "string") {
            throw new BadInput("name must be a string");
        }
        const trimmed = name.trim();
        if (!trimmed) throw new BadInput("name must not be empty");
        if (trimmed.length > 200) throw new BadInput("name too long");
        await this.ensureRoot();
        const id = randomUUID();
        const now = new Date().toISOString();
        const meta = { id, name: trimmed, createdAt: now, modifiedAt: now };
        await fs.mkdir(path.join(this.root, id, "files"), { recursive: true });
        await this.writeMeta(id, meta);
        return meta;
    }

    async getProject(id) {
        return await this.readMeta(id);
    }

    async deleteProject(id) {
        if (!isUuid(id)) throw new NotFound("project not found");
        const dir = path.join(this.root, id);
        try {
            await fs.access(path.join(dir, "meta.json"));
        } catch {
            throw new NotFound("project not found");
        }
        await fs.rm(dir, { recursive: true, force: true });
    }

    // ---- files ------------------------------------------------------------

    async listFiles(id) {
        await this.readMeta(id);
        const root = path.join(this.root, id, "files");
        const entries = [];
        await walk(root, "", entries);
        entries.sort((a, b) => a.path.localeCompare(b.path));
        return entries;
    }

    async readFile(id, relPath) {
        await this.readMeta(id);
        const abs = this.fileAbs(id, relPath);
        try {
            return await fs.readFile(abs);
        } catch (e) {
            if (e.code === "ENOENT") throw new NotFound("file not found");
            throw e;
        }
    }

    async writeFile(id, relPath, body) {
        const meta = await this.readMeta(id);
        const abs = this.fileAbs(id, relPath);
        await fs.mkdir(path.dirname(abs), { recursive: true });
        const tmp = abs + ".tmp";
        await fs.writeFile(tmp, body);
        await fs.rename(tmp, abs);
        const stat = await fs.stat(abs);
        meta.modifiedAt = new Date().toISOString();
        await this.writeMeta(id, meta);
        return {
            path: relPath,
            type: "file",
            size: stat.size,
            modifiedAt: stat.mtime.toISOString(),
        };
    }

    async deleteFile(id, relPath) {
        await this.readMeta(id);
        const abs = this.fileAbs(id, relPath);
        try {
            await fs.rm(abs);
        } catch (e) {
            if (e.code === "ENOENT") throw new NotFound("file not found");
            throw e;
        }
    }

    // ---- helpers ----------------------------------------------------------

    fileAbs(id, relPath) {
        if (!isUuid(id)) throw new NotFound("project not found");
        const safe = safePath(relPath);
        if (safe === null) throw new BadInput(`invalid path '${relPath}'`);
        return path.join(this.root, id, "files", safe);
    }

    async readMeta(id) {
        if (!isUuid(id)) throw new NotFound("project not found");
        try {
            const text = await fs.readFile(
                path.join(this.root, id, "meta.json"),
                "utf-8",
            );
            return JSON.parse(text);
        } catch (e) {
            if (e.code === "ENOENT") throw new NotFound("project not found");
            throw e;
        }
    }

    async writeMeta(id, meta) {
        const file = path.join(this.root, id, "meta.json");
        const tmp = file + ".tmp";
        await fs.writeFile(tmp, JSON.stringify(meta, null, 2) + "\n");
        await fs.rename(tmp, file);
    }
}

async function walk(dir, prefix, out) {
    const items = await fs.readdir(dir, { withFileTypes: true });
    for (const it of items) {
        const full = path.join(dir, it.name);
        const relPath = prefix ? `${prefix}/${it.name}` : it.name;
        if (it.isDirectory()) {
            out.push({
                path: relPath,
                type: "directory",
                size: 0,
                modifiedAt: (await fs.stat(full)).mtime.toISOString(),
            });
            await walk(full, relPath, out);
        } else if (it.isFile()) {
            const stat = await fs.stat(full);
            out.push({
                path: relPath,
                type: "file",
                size: stat.size,
                modifiedAt: stat.mtime.toISOString(),
            });
        }
    }
}
