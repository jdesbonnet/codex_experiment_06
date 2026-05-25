// Compile-on-save diagnostics for tiny_vm sources.
//
// Subscribes to onDidSaveTextDocument for tiny-vm-c / tiny-vm-asm documents,
// re-runs the backend compiler, and publishes the structured diagnostics it
// returns to a shared DiagnosticCollection. Squigglies appear in the gutter
// and entries land in the Problems panel; clearing on success removes them.
//
// This is Stage 1 from docs/vscode_proposal.md §D4 — compile-on-save. Stage 2
// would debounce onDidChangeTextDocument for live as-you-type diagnostics.

import * as vscode from "vscode";
import {
    CompileFailedError,
    CompileDiagnostic,
    compileCvmC,
} from "./compile";

const DIAG_SOURCE = "tiny_vm";
const SUPPORTED_LANGUAGES = new Set(["tiny-vm-c", "tiny-vm-asm"]);

export function registerDiagnostics(
    context: vscode.ExtensionContext,
): vscode.DiagnosticCollection {
    const coll = vscode.languages.createDiagnosticCollection("tiny_vm");
    context.subscriptions.push(coll);

    // Compile on save.
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((doc) => {
            if (!isSupported(doc)) return;
            void runCompile(context, doc, coll);
        }),
    );

    // Drop diagnostics when the file is closed; otherwise stale squigglies
    // linger in the Problems panel for files the user moved on from.
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument((doc) => {
            if (isSupported(doc)) coll.delete(doc.uri);
        }),
    );

    // First-pass compile for any tiny_vm document already open at activation.
    for (const doc of vscode.workspace.textDocuments) {
        if (isSupported(doc)) void runCompile(context, doc, coll);
    }
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument((doc) => {
            if (isSupported(doc)) void runCompile(context, doc, coll);
        }),
    );

    return coll;
}

function isSupported(doc: vscode.TextDocument): boolean {
    return SUPPORTED_LANGUAGES.has(doc.languageId);
}

async function runCompile(
    context: vscode.ExtensionContext,
    doc: vscode.TextDocument,
    coll: vscode.DiagnosticCollection,
): Promise<void> {
    const sourceName = vscode.workspace.asRelativePath(doc.uri);
    try {
        await compileCvmC(context, doc.getText(), sourceName);
        coll.set(doc.uri, []); // success → wipe any previous squigglies
    } catch (e) {
        if (e instanceof CompileFailedError) {
            coll.set(doc.uri, toVsDiagnostics(doc, e.diagnostics));
        } else {
            // Network / server unreachable: don't clobber stale diagnostics
            // with a useless single-line error in the Problems panel. Just
            // log; the user will see the toast from the launch path if they
            // try to run.
            console.warn("[tiny_vm] diagnostics compile failed:", e);
        }
    }
}

function toVsDiagnostics(
    doc: vscode.TextDocument,
    diags: CompileDiagnostic[],
): vscode.Diagnostic[] {
    return diags.map((d) => {
        // vm_cc.py reports 1-based line/col; VS Code Position is 0-based.
        // Clamp to the document so out-of-range positions still render.
        const lineIdx = Math.max(0, Math.min(d.line - 1, doc.lineCount - 1));
        const lineText = doc.lineAt(lineIdx).text;
        const colIdx = Math.max(0, Math.min(d.col - 1, lineText.length));
        // Extend the squiggly to the end of an identifier or to end-of-line
        // — single-char ranges are easy to miss.
        const tail = lineText.slice(colIdx);
        const match = tail.match(/^[A-Za-z_]\w*/);
        const endCol = colIdx + (match ? match[0].length : Math.max(1, tail.length || 1));
        const range = new vscode.Range(lineIdx, colIdx, lineIdx, endCol);
        const sev =
            d.severity === "warning"
                ? vscode.DiagnosticSeverity.Warning
                : vscode.DiagnosticSeverity.Error;
        const diag = new vscode.Diagnostic(range, d.message, sev);
        diag.source = DIAG_SOURCE;
        return diag;
    });
}
