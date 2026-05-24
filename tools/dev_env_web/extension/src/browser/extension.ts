// VS Code Web extension entry point (web target).
//
// Runs inside a Web Worker. No Node built-ins available: no `fs`, no
// `child_process`, no `net`. All I/O must go through the `vscode` API or
// fetch().

import * as vscode from "vscode";
import { OpfsFileSystemProvider, OPFS_SCHEME } from "./filesystem/opfs";
import { ensureSimReady, runProgram, statusName, STATUS } from "./sim";
import { TinyVmDebugAdapter } from "./debugAdapter";
import { compileCvmC } from "./compile";

const DEBUG_TYPE = "tiny-vm";

// Files we copy from the dev-mount workspace into OPFS when the user runs
// `tinyVm.seedOpfs`. Mirror of projects/tiny_vm/tests/*.cvm.c plus the
// blink demo plus the README that holds the opcode table.
const SEED_FILES = [
    "projects/tiny_vm/tests/count10.cvm.c",
    "projects/tiny_vm/tests/primes1000.cvm.c",
    "projects/tiny_vm/tests/collatz_max.cvm.c",
    "projects/tiny_vm/tests/checksum8.cvm.c",
    "projects/tiny_vm/tests/crc32.cvm.c",
    "projects/tiny_vm/tests/rotate32.cvm.c",
    "projects/tiny_vm/tests/mem32.cvm.c",
    "projects/tiny_vm/tests/sha1_abc.cvm.c",
    "projects/tiny_vm/demos/blink.cvm.c",
    "projects/tiny_vm/README.md",
];

let output: vscode.OutputChannel | null = null;

function getOutput(): vscode.OutputChannel {
    if (!output) {
        output = vscode.window.createOutputChannel("tiny_vm");
    }
    return output;
}

export function activate(context: vscode.ExtensionContext): void {
    const opfs = new OpfsFileSystemProvider();
    context.subscriptions.push(
        vscode.workspace.registerFileSystemProvider(OPFS_SCHEME, opfs, {
            isCaseSensitive: true,
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("tinyVm.openOpcodeTable", () =>
            openOpcodeTable(context),
        ),
        vscode.commands.registerCommand("tinyVm.seedOpfs", () => seedOpfs()),
        vscode.commands.registerCommand("tinyVm.openOpfsRoot", () =>
            openOpfsRoot(),
        ),
        vscode.commands.registerCommand("tinyVm.runBytecode", () =>
            runBytecodeCommand(context),
        ),
        vscode.commands.registerCommand("tinyVm.debugBytecode", () =>
            debugBytecodeCommand(context),
        ),
    );

    // Register the tiny_vm debug type with an in-process adapter factory.
    // The factory creates a fresh TinyVmDebugAdapter per session — VS Code
    // calls handleMessage(req) on it directly with DAP messages and we fire
    // events back via onDidSendMessage.
    context.subscriptions.push(
        vscode.debug.registerDebugAdapterDescriptorFactory(DEBUG_TYPE, {
            createDebugAdapterDescriptor(session) {
                return new vscode.DebugAdapterInlineImplementation(
                    new TinyVmDebugAdapter(context, session),
                );
            },
        }),
    );

    console.log("[tiny_vm] web extension activated");
}

export function deactivate(): void {
    // Web extension host tears down the worker on its own. Nothing to do.
}

async function openOpcodeTable(context: vscode.ExtensionContext): Promise<void> {
    const panel = vscode.window.createWebviewPanel(
        "tinyVmOpcodes",
        "tiny_vm Opcode Table",
        vscode.ViewColumn.Active,
        { enableScripts: false, retainContextWhenHidden: true },
    );
    panel.webview.html = renderOpcodeHtml();
    void context; // unused for now; will hold the bundled .md once a seed mechanism exists in M2.2
}

// v1 stub: render an inlined summary. M2.2 will replace this with a fetch of
// the bundled projects/tiny_vm/README.md "Opcode summary" section from OPFS.
function renderOpcodeHtml(): string {
    const rows: Array<[string, string, string]> = [
        ["0x00", "NOP",       "no-op"],
        ["0x01", "PUSH8 imm", "push sign-extended 8-bit immediate"],
        ["0x02", "ADD",       "pop b, a; push a+b (i32 wrapping)"],
        ["0x03", "SUB",       "pop b, a; push a-b"],
        ["0x04", "DUP",       "push copy of top"],
        ["0x05", "DROP",      "pop top"],
        ["0x06", "SWAP",      "swap top two"],
        ["0x07", "JMP target16", "pc = target"],
        ["0x08", "JZ target16",  "pop cond; if cond==0 pc = target"],
        ["0x09", "HOST id8",  "host call by id (LED/DELAY/PRINT_U32/PRINT_HEX32)"],
        ["0x0A", "LGET slot8","push locals[slot]"],
        ["0x0B", "LSET slot8","pop and store into locals[slot]"],
        ["0x0C", "EQ",        "pop b,a; push (a==b)?1:0"],
        ["0x0D", "LT",        "pop b,a; push (a<b)?1:0 (signed)"],
        ["0x0E", "PUSH16 imm","push sign-extended 16-bit LE immediate"],
        ["0x0F", "MOD",       "pop b,a; push a%b (C-style, sign of dividend)"],
        ["0x10", "MUL",       "pop b,a; push a*b"],
        ["0x11", "DIV",       "pop b,a; push a/b (truncated toward zero)"],
        ["0x12", "MGET",      "pop idx; push (i32)mem[idx] (zero-extended)"],
        ["0x13", "MSET",      "pop value, idx; mem[idx] = value & 0xFF"],
        ["0x14", "PUSH32 imm","push 32-bit LE immediate"],
        ["0x15", "AND",       "bitwise and"],
        ["0x16", "OR",        "bitwise or"],
        ["0x17", "XOR",       "bitwise xor"],
        ["0x18", "NOT",       "bitwise not (top only)"],
        ["0x19", "SHL",       "pop b,a; push a << (b & 31)"],
        ["0x1A", "SHR",       "logical shift right"],
        ["0x1B", "ROL",       "rotate left by (b & 31)"],
        ["0x1C", "ROR",       "rotate right by (b & 31)"],
        ["0x1D", "MGET32",    "pop idx; push 32-bit LE from mem[idx..idx+4]"],
        ["0x1E", "MSET32",    "pop value, idx; store 32-bit LE"],
        ["0xFF", "HALT",      "halt (status HALT)"],
    ];
    const body = rows
        .map(
            ([h, m, d]) =>
                `<tr><td class="op">${h}</td><td class="m">${escapeHtml(
                    m,
                )}</td><td>${escapeHtml(d)}</td></tr>`,
        )
        .join("");
    return `<!doctype html>
<html><head><meta charset="utf-8"><title>tiny_vm Opcodes</title>
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 1rem; }
  h1 { font-size: 1.1rem; margin-bottom: 0.6rem; }
  table { border-collapse: collapse; font-family: var(--vscode-editor-font-family); font-size: 0.85rem; }
  td { padding: 2px 12px 2px 0; vertical-align: top; }
  td.op { color: var(--vscode-textLink-foreground); }
  td.m { font-weight: 600; }
  p.tag { color: var(--vscode-descriptionForeground); font-size: 0.85rem; }
</style></head><body>
  <h1>tiny_vm opcodes</h1>
  <p class="tag">Authoritative source: <code>common/include/tiny_vm.h</code>.
  Sim implementations: <code>tools/dev_env/sim/tiny_vm_sim.py</code> and
  <code>tools/dev_env_web/sim/rust/src/lib.rs</code>.</p>
  <table><tbody>${body}</tbody></table>
</body></html>`;
}

function escapeHtml(s: string): string {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

/**
 * Copy a handful of files from the workspace mount into OPFS. The user runs
 * this once to populate the OPFS workspace; afterwards their edits live in
 * OPFS persistently across reloads.
 *
 * Source URI is whatever the current workspace mount is (e.g.
 * vscode-test-web://mount/... in dev). Destination is tinyvm-opfs:/...
 */
async function seedOpfs(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        vscode.window.showErrorMessage(
            "tiny_vm: no workspace folder open to seed OPFS from",
        );
        return;
    }
    // Pick the first non-OPFS folder as the source.
    const srcRoot = folders.find((f) => f.uri.scheme !== OPFS_SCHEME)?.uri;
    if (!srcRoot) {
        vscode.window.showErrorMessage(
            "tiny_vm: no non-OPFS workspace folder to seed from",
        );
        return;
    }

    let copied = 0;
    let skipped = 0;
    for (const rel of SEED_FILES) {
        const src = vscode.Uri.joinPath(srcRoot, rel);
        const dst = vscode.Uri.from({ scheme: OPFS_SCHEME, path: "/" + rel });
        try {
            const data = await vscode.workspace.fs.readFile(src);
            await vscode.workspace.fs.writeFile(dst, data);
            copied += 1;
        } catch (e) {
            console.warn(`[tiny_vm] seed: skipped ${rel}: ${e}`);
            skipped += 1;
        }
    }
    vscode.window.showInformationMessage(
        `tiny_vm: seeded OPFS — ${copied} files copied, ${skipped} skipped. ` +
            `Run "tiny_vm: Open OPFS Workspace" to view.`,
    );
}

/**
 * Add the OPFS root (`tinyvm-opfs:/`) as a workspace folder. The user can
 * then browse and edit OPFS files alongside (or instead of) the original
 * workspace mount.
 */
/**
 * Smoke command for the M3 wasm integration. Prompts the user to pick a
 * .bin file from the workspace, runs it through the wasm sim with default
 * host call handlers, and streams output into the tiny_vm output channel.
 * This is the run-only path; the DAP-driven debug path comes next.
 */
async function runBytecodeCommand(
    context: vscode.ExtensionContext,
): Promise<void> {
    const out = getOutput();
    out.show(true);

    // Priority 1: if the active editor holds a .bin URI, run that.
    // Priority 2: open file dialog (uses the registered FileSystemProvider's
    //   readDirectory, which works for both vscode-test-web:// and
    //   tinyvm-opfs://, whereas vscode.workspace.findFiles does not).
    let target: vscode.Uri | undefined;
    const active = vscode.window.activeTextEditor?.document.uri;
    if (active && active.path.endsWith(".bin")) {
        target = active;
    } else {
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            openLabel: "Run in tiny_vm sim",
            filters: { "tiny_vm bytecode": ["bin"] },
            defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri,
        });
        target = picked?.[0];
    }
    if (!target) {
        out.appendLine(`[tinyVm] cancelled`);
        return;
    }

    out.appendLine(`[tinyVm] loading ${target.toString()}`);
    await ensureSimReady(context);
    const code = await vscode.workspace.fs.readFile(target);
    out.appendLine(`[tinyVm] running ${code.length} bytes`);
    const t0 = Date.now();
    const { status, stdout } = runProgram(code, (line) => {
        out.appendLine(line);
    });
    const elapsed = Date.now() - t0;
    out.appendLine(
        `[tinyVm] finished: status=${statusName(status)} ` +
            `(${status}), ${stdout.length} lines, ${elapsed}ms`,
    );
    if (status !== STATUS.HALT) {
        vscode.window.showWarningMessage(
            `tiny_vm: program ended with ${statusName(status)} — see Output panel`,
        );
    }
}

/**
 * Start a tiny_vm debug session against a bytecode file. Pick from the
 * active editor if it ends in .bin, otherwise prompt with a file dialog.
 * Session loads the .bin + its companion .bin.map, stops on entry, and
 * surfaces DAP for stepping/breakpoints/inspection through the
 * TinyVmDebugAdapter.
 */
/**
 * Compile (if needed) and start a debug session.
 *
 * If the active editor is a .cvm.c (or .vm), we compile it via Pyodide
 * to bytecode + map, write the artefacts to OPFS at /.cache/<base>.bin{,.map},
 * and launch against those. If the active editor is a .bin, we launch
 * directly. Otherwise we prompt for a .bin via the open dialog.
 */
async function debugBytecodeCommand(context: vscode.ExtensionContext): Promise<void> {
    const out = getOutput();
    let target: vscode.Uri | undefined;
    const active = vscode.window.activeTextEditor?.document;

    if (active && (active.fileName.endsWith(".cvm.c") || active.fileName.endsWith(".vm"))) {
        out.show(true);
        target = await compileAndStage(context, active, out);
        if (!target) return;
    } else if (active && active.uri.path.endsWith(".bin")) {
        target = active.uri;
    } else {
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            openLabel: "Debug in tiny_vm sim",
            filters: { "tiny_vm bytecode + source": ["bin", "cvm.c", "vm"] },
            defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri,
        });
        if (!picked || picked.length === 0) return;
        const u = picked[0];
        if (u.path.endsWith(".cvm.c") || u.path.endsWith(".vm")) {
            out.show(true);
            const doc = await vscode.workspace.openTextDocument(u);
            target = await compileAndStage(context, doc, out);
            if (!target) return;
        } else {
            target = u;
        }
    }

    const folder = vscode.workspace.getWorkspaceFolder(target);
    await vscode.debug.startDebugging(folder, {
        type: DEBUG_TYPE,
        request: "launch",
        name: `tiny_vm: ${target.path.split("/").pop()}`,
        program: target.toString(),
        stopOnEntry: true,
    });
}

/**
 * Compile a .cvm.c (or .vm) document and write the .bin + .bin.map into
 * OPFS at /.cache/<base>.bin{,.map}. Returns the .bin URI for launching
 * the debug session, or undefined on compile failure.
 */
async function compileAndStage(
    context: vscode.ExtensionContext,
    doc: vscode.TextDocument,
    out: vscode.OutputChannel,
): Promise<vscode.Uri | undefined> {
    const base = doc.uri.path.split("/").pop()!.replace(/\.(cvm\.c|vm)$/, "");
    const sourceName = vscode.workspace.asRelativePath(doc.uri);
    try {
        const { bytecode, sourceMap } = await compileCvmC(
            context,
            doc.getText(),
            sourceName,
            out,
        );
        const binUri = vscode.Uri.from({
            scheme: OPFS_SCHEME,
            path: `/.cache/${base}.bin`,
        });
        const mapUri = vscode.Uri.from({
            scheme: OPFS_SCHEME,
            path: `/.cache/${base}.bin.map`,
        });
        await vscode.workspace.fs.writeFile(binUri, bytecode);
        await vscode.workspace.fs.writeFile(
            mapUri,
            new TextEncoder().encode(sourceMap),
        );
        out.appendLine(`[tinyVm] staged ${binUri.toString()}`);
        return binUri;
    } catch (e) {
        const msg = `tiny_vm: compile failed: ${e}`;
        out.appendLine(`[tinyVm] ${msg}`);
        vscode.window.showErrorMessage(msg);
        return undefined;
    }
}

async function openOpfsRoot(): Promise<void> {
    const uri = vscode.Uri.from({ scheme: OPFS_SCHEME, path: "/" });
    const existing = vscode.workspace.workspaceFolders ?? [];
    const already = existing.some((f) => f.uri.toString() === uri.toString());
    if (already) {
        vscode.window.showInformationMessage(
            "tiny_vm: OPFS workspace folder already open.",
        );
        return;
    }
    const added = vscode.workspace.updateWorkspaceFolders(existing.length, 0, {
        uri,
        name: "tiny_vm OPFS",
    });
    if (!added) {
        vscode.window.showErrorMessage(
            "tiny_vm: failed to add OPFS folder to workspace",
        );
    }
}
