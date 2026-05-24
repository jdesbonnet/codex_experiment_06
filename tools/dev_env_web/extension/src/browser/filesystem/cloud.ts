// FileSystemProvider backed by the cloud projects API. Mirrors
// OpfsFileSystemProvider's shape; replaces OPFS calls with REST.
//
// URI scheme: tinyvm-cloud
// URI path:   /projects/{projectId}/{file/path/within/project}
//
// The provider is registered at extension activation so VS Code can
// resolve `tinyvm-cloud:` workspace folders from saved state without
// waiting on any async work.

import * as vscode from "vscode";
import * as api from "../api-client";

export const CLOUD_SCHEME = "tinyvm-cloud";
const URI_RE = /^\/projects\/([^/]+)(?:\/(.*))?$/;

interface Parsed {
    projectId: string;
    relPath: string; // "" for the project root
}

function parse(uri: vscode.Uri): Parsed {
    const m = URI_RE.exec(uri.path);
    if (!m) throw vscode.FileSystemError.FileNotFound(uri);
    return { projectId: m[1], relPath: m[2] ?? "" };
}

export class CloudFileSystemProvider implements vscode.FileSystemProvider {
    private readonly emitter = new vscode.EventEmitter<vscode.FileChangeEvent[]>();
    public readonly onDidChangeFile = this.emitter.event;

    watch(): vscode.Disposable {
        // No server-side push in v1. The IDE updates its view via the
        // events we fire on our own writes.
        return new vscode.Disposable(() => {});
    }

    async stat(uri: vscode.Uri): Promise<vscode.FileStat> {
        const { projectId, relPath } = parse(uri);
        if (relPath === "") {
            // Project root — always a directory if the project exists.
            try {
                await api.getProject(projectId);
            } catch (e) {
                throw this.translate(e, uri);
            }
            return { type: vscode.FileType.Directory, ctime: 0, mtime: 0, size: 0 };
        }
        // Find the entry in the recursive file list. The trees we expect
        // are small (single-digit-to-hundreds of files), so a full list
        // per stat is fine for v1.
        let entries: api.FileEntry[];
        try {
            entries = await api.listFiles(projectId);
        } catch (e) {
            throw this.translate(e, uri);
        }
        const e = entries.find((x) => x.path === relPath);
        if (!e) throw vscode.FileSystemError.FileNotFound(uri);
        return {
            type:
                e.type === "directory"
                    ? vscode.FileType.Directory
                    : vscode.FileType.File,
            ctime: 0,
            mtime: Date.parse(e.modifiedAt) || 0,
            size: e.size,
        };
    }

    async readDirectory(uri: vscode.Uri): Promise<[string, vscode.FileType][]> {
        const { projectId, relPath } = parse(uri);
        let entries: api.FileEntry[];
        try {
            entries = await api.listFiles(projectId);
        } catch (e) {
            throw this.translate(e, uri);
        }
        const prefix = relPath === "" ? "" : relPath + "/";
        const out = new Map<string, vscode.FileType>();
        for (const e of entries) {
            if (!e.path.startsWith(prefix)) continue;
            const rest = e.path.slice(prefix.length);
            if (rest === "" || rest.includes("/")) {
                if (rest.includes("/")) {
                    // Implicit subdirectory — record it once.
                    out.set(rest.split("/")[0]!, vscode.FileType.Directory);
                }
                continue;
            }
            out.set(
                rest,
                e.type === "directory"
                    ? vscode.FileType.Directory
                    : vscode.FileType.File,
            );
        }
        return [...out.entries()];
    }

    async createDirectory(uri: vscode.Uri): Promise<void> {
        // Server stores directories implicitly when a file is written.
        // VS Code occasionally calls this preemptively; treat as no-op.
        // Fire a synthetic change event so the tree refreshes.
        this.emitter.fire([{ type: vscode.FileChangeType.Created, uri }]);
    }

    async readFile(uri: vscode.Uri): Promise<Uint8Array> {
        const { projectId, relPath } = parse(uri);
        if (relPath === "") {
            throw vscode.FileSystemError.FileIsADirectory(uri);
        }
        try {
            return await api.readFile(projectId, relPath);
        } catch (e) {
            throw this.translate(e, uri);
        }
    }

    async writeFile(
        uri: vscode.Uri,
        content: Uint8Array,
        _options: { create: boolean; overwrite: boolean },
    ): Promise<void> {
        const { projectId, relPath } = parse(uri);
        if (relPath === "") {
            throw vscode.FileSystemError.FileIsADirectory(uri);
        }
        // Detect create vs change for the event by stat'ing first.
        let existed = false;
        try {
            await api.readFile(projectId, relPath);
            existed = true;
        } catch {
            // not there yet
        }
        try {
            await api.writeFile(projectId, relPath, content);
        } catch (e) {
            throw this.translate(e, uri);
        }
        this.emitter.fire([
            {
                type: existed
                    ? vscode.FileChangeType.Changed
                    : vscode.FileChangeType.Created,
                uri,
            },
        ]);
    }

    async delete(uri: vscode.Uri): Promise<void> {
        const { projectId, relPath } = parse(uri);
        if (relPath === "") {
            // Deleting the project root from the FS provider is unusual;
            // the user should use tinyVm.cloud.deleteProject instead.
            throw vscode.FileSystemError.NoPermissions(uri);
        }
        try {
            await api.deleteFile(projectId, relPath);
        } catch (e) {
            throw this.translate(e, uri);
        }
        this.emitter.fire([{ type: vscode.FileChangeType.Deleted, uri }]);
    }

    async rename(
        oldUri: vscode.Uri,
        newUri: vscode.Uri,
        options: { overwrite: boolean },
    ): Promise<void> {
        // No native rename endpoint — copy + delete.
        const data = await this.readFile(oldUri);
        await this.writeFile(newUri, data, { create: true, overwrite: options.overwrite });
        await this.delete(oldUri);
    }

    private translate(e: unknown, uri: vscode.Uri): Error {
        if (e instanceof api.ApiError) {
            if (e.status === 404) return vscode.FileSystemError.FileNotFound(uri);
            if (e.status === 400) return vscode.FileSystemError.NoPermissions(uri);
        }
        return e instanceof Error ? e : new Error(String(e));
    }
}

// Helpers used by the new-project / open-project commands.

export function projectFolderUri(id: string): vscode.Uri {
    return vscode.Uri.from({ scheme: CLOUD_SCHEME, path: `/projects/${id}` });
}

export function fileUri(id: string, relPath: string): vscode.Uri {
    return vscode.Uri.from({
        scheme: CLOUD_SCHEME,
        path: `/projects/${id}/${relPath}`,
    });
}
