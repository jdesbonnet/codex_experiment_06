// FileSystemProvider backed by the browser's Origin Private File System.
//
// Surfaced under the URI scheme `tinyvm-opfs`. Files live in OPFS scoped to
// this origin (vscode-test-web's `http://localhost:3000` in dev, the deployed
// host in v2). Persistent across reloads, sandboxed (no host disk access),
// no user permission prompt — the whole point of OPFS for a SaaS-style IDE.
//
// Limitations:
// - No native watch API on OPFS. We fire FileChange events when *we* write,
//   which covers IDE-driven edits but not external mutations (there are none
//   in v1 since OPFS is sandboxed to this origin).
// - rename() is implemented as copy + delete (OPFS has no native rename
//   between directories).
// - Symlinks are not supported.

import * as vscode from "vscode";

export const OPFS_SCHEME = "tinyvm-opfs";

export class OpfsFileSystemProvider implements vscode.FileSystemProvider {
    private readonly emitter = new vscode.EventEmitter<vscode.FileChangeEvent[]>();
    public readonly onDidChangeFile = this.emitter.event;

    watch(_uri: vscode.Uri): vscode.Disposable {
        // OPFS has no native watch; rely on our own writes for events.
        return new vscode.Disposable(() => {});
    }

    async stat(uri: vscode.Uri): Promise<vscode.FileStat> {
        const handle = await this.resolveHandle(uri);
        if (handle.kind === "directory") {
            return {
                type: vscode.FileType.Directory,
                ctime: 0,
                mtime: 0,
                size: 0,
            };
        }
        const file = await (handle as FileSystemFileHandle).getFile();
        return {
            type: vscode.FileType.File,
            ctime: 0,
            mtime: file.lastModified,
            size: file.size,
        };
    }

    async readDirectory(uri: vscode.Uri): Promise<[string, vscode.FileType][]> {
        const dir = await this.resolveDirectory(uri, false);
        const entries: [string, vscode.FileType][] = [];
        // `entries()` is on FileSystemDirectoryHandle but not in the standard
        // lib.dom typings as of TS 5.4 — cast through `any`.
        for await (const [name, handle] of (dir as unknown as {
            entries(): AsyncIterableIterator<[string, FileSystemHandle]>;
        }).entries()) {
            entries.push([
                name,
                handle.kind === "directory"
                    ? vscode.FileType.Directory
                    : vscode.FileType.File,
            ]);
        }
        return entries;
    }

    async createDirectory(uri: vscode.Uri): Promise<void> {
        await this.resolveDirectory(uri, true);
        this.emitter.fire([{ type: vscode.FileChangeType.Created, uri }]);
    }

    async readFile(uri: vscode.Uri): Promise<Uint8Array> {
        const file = await this.resolveFile(uri, false);
        const blob = await file.getFile();
        return new Uint8Array(await blob.arrayBuffer());
    }

    async writeFile(
        uri: vscode.Uri,
        content: Uint8Array,
        options: { create: boolean; overwrite: boolean },
    ): Promise<void> {
        const segments = this.segments(uri);
        if (segments.length === 0) {
            throw vscode.FileSystemError.NoPermissions(uri);
        }
        const name = segments.pop()!;
        const dir = await this.descend(segments, options.create);
        let existed = false;
        try {
            await dir.getFileHandle(name);
            existed = true;
        } catch {
            // Doesn't exist yet.
        }
        if (existed && !options.overwrite) {
            throw vscode.FileSystemError.FileExists(uri);
        }
        if (!existed && !options.create) {
            throw vscode.FileSystemError.FileNotFound(uri);
        }
        const handle = await dir.getFileHandle(name, { create: options.create });
        const writable = await handle.createWritable();
        try {
            await writable.write(content);
        } finally {
            await writable.close();
        }
        this.emitter.fire([
            {
                type: existed ? vscode.FileChangeType.Changed : vscode.FileChangeType.Created,
                uri,
            },
        ]);
    }

    async delete(
        uri: vscode.Uri,
        options: { recursive: boolean },
    ): Promise<void> {
        const segments = this.segments(uri);
        if (segments.length === 0) {
            throw vscode.FileSystemError.NoPermissions(uri);
        }
        const name = segments.pop()!;
        const dir = await this.descend(segments, false);
        try {
            await dir.removeEntry(name, { recursive: options.recursive });
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
        // OPFS has no native cross-directory rename. Copy + delete.
        const data = await this.readFile(oldUri);
        await this.writeFile(newUri, data, {
            create: true,
            overwrite: options.overwrite,
        });
        await this.delete(oldUri, { recursive: false });
    }

    // ---- helpers ----------------------------------------------------------

    private segments(uri: vscode.Uri): string[] {
        return uri.path.split("/").filter((s) => s.length > 0);
    }

    private async root(): Promise<FileSystemDirectoryHandle> {
        return await navigator.storage.getDirectory();
    }

    /**
     * Walk into a directory by segments. With `create=true`, intermediate
     * directories are created as needed.
     */
    private async descend(
        segments: string[],
        create: boolean,
    ): Promise<FileSystemDirectoryHandle> {
        let dir = await this.root();
        for (const s of segments) {
            try {
                dir = await dir.getDirectoryHandle(s, { create });
            } catch (e) {
                throw this.translate(
                    e,
                    vscode.Uri.from({ scheme: OPFS_SCHEME, path: "/" + segments.join("/") }),
                );
            }
        }
        return dir;
    }

    private async resolveDirectory(
        uri: vscode.Uri,
        create: boolean,
    ): Promise<FileSystemDirectoryHandle> {
        try {
            return await this.descend(this.segments(uri), create);
        } catch (e) {
            throw this.translate(e, uri);
        }
    }

    private async resolveFile(
        uri: vscode.Uri,
        create: boolean,
    ): Promise<FileSystemFileHandle> {
        const segments = this.segments(uri);
        if (segments.length === 0) {
            throw vscode.FileSystemError.FileNotFound(uri);
        }
        const name = segments.pop()!;
        const dir = await this.descend(segments, create);
        try {
            return await dir.getFileHandle(name, { create });
        } catch (e) {
            throw this.translate(e, uri);
        }
    }

    private async resolveHandle(uri: vscode.Uri): Promise<FileSystemHandle> {
        const segments = this.segments(uri);
        if (segments.length === 0) return await this.root();
        const name = segments[segments.length - 1]!;
        const parent = await this.descend(segments.slice(0, -1), false);
        try {
            return await parent.getFileHandle(name);
        } catch {
            // Not a file — try directory.
        }
        try {
            return await parent.getDirectoryHandle(name);
        } catch (e) {
            throw this.translate(e, uri);
        }
    }

    /**
     * Translate OPFS-thrown DOMException kinds to vscode.FileSystemError so
     * the IDE shows the right user-facing messages and the right "file not
     * found" handling kicks in.
     */
    private translate(e: unknown, uri: vscode.Uri): Error {
        const name = e instanceof Error ? e.name : "";
        if (name === "NotFoundError") {
            return vscode.FileSystemError.FileNotFound(uri);
        }
        if (name === "TypeMismatchError") {
            return vscode.FileSystemError.FileIsADirectory(uri);
        }
        if (name === "InvalidModificationError") {
            return vscode.FileSystemError.NoPermissions(uri);
        }
        return e instanceof Error ? e : new Error(String(e));
    }
}
