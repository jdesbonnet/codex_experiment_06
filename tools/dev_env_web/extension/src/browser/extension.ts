// VS Code Web extension entry point (web target).
//
// Runs inside a Web Worker. No Node built-ins available: no `fs`, no
// `child_process`, no `net`. All I/O must go through the `vscode` API or
// fetch().

import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext): void {
    // Smoke command — proves the extension activated and commands are
    // registered. Later milestones add tinyVm.runInSim, tinyVm.debugInSim,
    // tinyVm.compile, etc.
    context.subscriptions.push(
        vscode.commands.registerCommand("tinyVm.openOpcodeTable", () =>
            openOpcodeTable(context),
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
