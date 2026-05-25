// Backend-API compiler client.
//
// The web extension does not compile in-browser. Source goes to a remote
// HTTP endpoint that returns bytecode + source-map JSON. In dev the
// endpoint is `tools/vscode/host/compile-server.mjs` (started by
// `scripts/serve.sh`) running on http://localhost:3001. In production
// the endpoint is the cloud-hosted compile service; the protocol stays
// identical.
//
// This decision (Q2 in docs/vscode_proposal.md) records that we chose
// the "build endpoint as a v1 dependency" path. The proposal originally
// flagged that as a v2 option, but the project is destined for cloud
// hosting and we'd rather exercise the API pattern from day one than
// build an in-browser solution we'll throw away.

import * as vscode from "vscode";

export interface CompileResult {
    bytecode: Uint8Array;
    sourceMap: string; // JSON text matching tools/vm_cc.py --map output
}

export interface CompileDiagnostic {
    line: number;
    col: number;
    severity: "error" | "warning";
    message: string;
}

/**
 * Thrown when /api/compile returns 4xx. Carries structured diagnostics from
 * the backend when present (vm_cc.py --json-errors output), so callers can
 * publish them to vscode.languages.createDiagnosticCollection(...).
 */
export class CompileFailedError extends Error {
    constructor(
        message: string,
        public readonly diagnostics: CompileDiagnostic[],
    ) {
        super(message);
        this.name = "CompileFailedError";
    }
}

function getApiUrl(): string {
    const cfg = vscode.workspace.getConfiguration("tinyVm");
    return cfg.get<string>("apiUrl") ?? "http://localhost:3001";
}

export async function compileCvmC(
    _context: vscode.ExtensionContext,
    sourceText: string,
    sourceName: string,
    progress?: vscode.OutputChannel,
): Promise<CompileResult> {
    const apiUrl = getApiUrl();
    progress?.appendLine(`[tinyVm] POST ${apiUrl}/api/compile (${sourceText.length} bytes)`);
    const t0 = Date.now();
    let resp: Response;
    try {
        resp = await fetch(`${apiUrl}/api/compile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source: sourceText, name: sourceName }),
        });
    } catch (e) {
        throw new Error(
            `compile-server unreachable at ${apiUrl} ` +
                `(is scripts/serve.sh running?): ${e}`,
        );
    }
    if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        let diagnostics: CompileDiagnostic[] = [];
        let detail = text;
        try {
            const parsed = JSON.parse(text) as {
                error?: string;
                detail?: string;
                diagnostics?: CompileDiagnostic[];
            };
            if (Array.isArray(parsed.diagnostics)) {
                diagnostics = parsed.diagnostics;
            }
            detail = parsed.detail ?? parsed.error ?? text;
        } catch {
            // body wasn't JSON; fall back to raw text
        }
        const headline = diagnostics[0]
            ? `${diagnostics[0].line}:${diagnostics[0].col}: ${diagnostics[0].message}`
            : detail || `HTTP ${resp.status} ${resp.statusText}`;
        throw new CompileFailedError(`compile failed: ${headline}`, diagnostics);
    }
    const json = (await resp.json()) as {
        bytecodeBase64: string;
        sourceMap: object | null;
    };
    const bytecode = base64Decode(json.bytecodeBase64);
    const sourceMap =
        json.sourceMap !== null
            ? JSON.stringify(json.sourceMap, null, 2) + "\n"
            : "";
    progress?.appendLine(
        `[tinyVm] compiled ${sourceName} -> ${bytecode.length} bytes ` +
            `(${Date.now() - t0} ms round-trip)`,
    );
    return { bytecode, sourceMap };
}

function base64Decode(s: string): Uint8Array {
    // atob is available in Web Worker globals.
    const binary = atob(s);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
}
