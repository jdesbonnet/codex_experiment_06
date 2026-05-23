// VS Code Web extension entry point (web target).
//
// Runs inside a Web Worker. No Node built-ins available: no `fs`, no
// `child_process`, no `net`. All I/O must go through the `vscode` API or
// fetch().

import * as vscode from "vscode";
import { OpfsFileSystemProvider, OPFS_SCHEME } from "./filesystem/opfs";

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
