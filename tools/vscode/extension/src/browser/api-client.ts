// Small typed client for the backend API (see host/openapi.yaml).
//
// All requests go to `tinyVm.apiUrl` from VS Code settings (default
// http://localhost:3001). Shaped so adding `Authorization` headers in
// a future auth iteration is a one-line change.

import * as vscode from "vscode";

export interface Project {
    id: string;
    name: string;
    createdAt: string;
    modifiedAt: string;
}

export interface FileEntry {
    path: string;
    type: "file" | "directory";
    size: number;
    modifiedAt: string;
}

export class ApiError extends Error {
    constructor(
        public readonly status: number,
        message: string,
        public readonly detail?: string,
    ) {
        super(message);
    }
}

function baseUrl(): string {
    return (
        vscode.workspace.getConfiguration("tinyVm").get<string>("apiUrl") ??
        "http://localhost:3001"
    );
}

async function request(
    method: string,
    pathSuffix: string,
    init?: RequestInit,
): Promise<Response> {
    const url = `${baseUrl()}${pathSuffix}`;
    let resp: Response;
    try {
        resp = await fetch(url, { method, ...init });
    } catch (e) {
        throw new ApiError(
            0,
            `backend API unreachable at ${baseUrl()}: ${e}`,
        );
    }
    if (!resp.ok) {
        let detail: string | undefined;
        let msg = `${method} ${pathSuffix} -> HTTP ${resp.status}`;
        try {
            const j = (await resp.json()) as { error?: string; detail?: string };
            if (j.error) msg = j.error;
            detail = j.detail;
        } catch {
            // Body wasn't JSON — keep the generic message.
        }
        throw new ApiError(resp.status, msg, detail);
    }
    return resp;
}

export async function listProjects(): Promise<Project[]> {
    const r = await request("GET", "/api/projects");
    const j = (await r.json()) as { projects: Project[] };
    return j.projects;
}

export async function createProject(name: string): Promise<Project> {
    const r = await request("POST", "/api/projects", {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    });
    return (await r.json()) as Project;
}

export async function getProject(id: string): Promise<Project> {
    const r = await request("GET", `/api/projects/${encodeURIComponent(id)}`);
    return (await r.json()) as Project;
}

export async function deleteProject(id: string): Promise<void> {
    await request("DELETE", `/api/projects/${encodeURIComponent(id)}`);
}

export async function listFiles(id: string): Promise<FileEntry[]> {
    const r = await request(
        "GET",
        `/api/projects/${encodeURIComponent(id)}/files`,
    );
    const j = (await r.json()) as { entries: FileEntry[] };
    return j.entries;
}

export async function readFile(id: string, p: string): Promise<Uint8Array> {
    const r = await request(
        "GET",
        `/api/projects/${encodeURIComponent(id)}/files/${encodeFilePath(p)}`,
    );
    return new Uint8Array(await r.arrayBuffer());
}

export async function writeFile(
    id: string,
    p: string,
    content: Uint8Array,
): Promise<FileEntry> {
    const r = await request(
        "PUT",
        `/api/projects/${encodeURIComponent(id)}/files/${encodeFilePath(p)}`,
        {
            headers: { "Content-Type": "application/octet-stream" },
            // BodyInit accepts ArrayBufferView.
            body: content as BodyInit,
        },
    );
    return (await r.json()) as FileEntry;
}

export async function deleteFile(id: string, p: string): Promise<void> {
    await request(
        "DELETE",
        `/api/projects/${encodeURIComponent(id)}/files/${encodeFilePath(p)}`,
    );
}

/**
 * URL-encode each path segment but keep `/` separators intact so the
 * server-side regex matches the rest-of-path capture group.
 */
function encodeFilePath(p: string): string {
    return p
        .split("/")
        .map((seg) => encodeURIComponent(seg))
        .join("/");
}
