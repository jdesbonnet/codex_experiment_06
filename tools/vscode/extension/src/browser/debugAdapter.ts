// In-process DebugAdapter for tiny_vm bytecode.
//
// Drives a WasmTinyVm via the coroutine handshake (HOST_PENDING -> JS handles
// host call -> complete_host_call). Source-line stepping is driven by a
// SourceMap loaded next to the .bin. No transport: VS Code calls
// `handleMessage(msg)` directly; we fire events through `onDidSendMessage`.
//
// References:
//   - DAP spec: https://microsoft.github.io/debug-adapter-protocol/specification
//   - tools/theia/dap/handlers.py for the Python-version's equivalent
//   - docs/vscode_proposal.md §5.3 for the request table

import * as vscode from "vscode";
import {
    WasmTinyVm,
    STATUS,
    HOST,
    ensureSimReady,
    statusName,
} from "./sim";
import {
    SourceMap,
    parseSourceMap,
    pcToEntry,
    adjustBreakpoint,
    nextLineBoundaryPcs,
} from "./sourcemap";

interface LaunchArgs {
    program: string; // workspace-relative or fully-qualified URI string of the .bin
    stopOnEntry?: boolean;
}

// Variable references for DAP variables/scopes:
const REF_LOCALS = 1000;
const REF_STACK = 1001;
const REF_MEMORY = 1002;

// Single thread — tiny_vm is single-threaded.
const THREAD_ID = 1;

export class TinyVmDebugAdapter implements vscode.DebugAdapter {
    private readonly sender = new vscode.EventEmitter<vscode.DebugProtocolMessage>();
    public readonly onDidSendMessage = this.sender.event;

    private vm: WasmTinyVm | null = null;
    private map: SourceMap | null = null;
    private sourcePath: string | null = null; // canonical source path for stackTrace
    private programUri: vscode.Uri | null = null;

    /** Source-line breakpoints keyed by source path: PCs to halt at. */
    private breakpoints = new Map<string, Set<number>>();

    /** Bookkeeping for pause requests issued while we are in a run loop. */
    private pauseRequested = false;

    /** Captured stdout — surfaced via DAP 'output' events. */
    private stdoutBuffer: string[] = [];

    /** Outgoing seq counter (separate from incoming). */
    private outSeq = 1;

    /**
     * Resolves when `onLaunch` has fully finished (vm constructed, map
     * loaded, response sent). `configurationDone` waits on this so the
     * race between an async launch and a near-immediate
     * configurationDone (which fires the stopOnEntry handshake) is
     * serialised properly.
     */
    private launchPromise: Promise<void> = Promise.resolve();

    constructor(
        private readonly context: vscode.ExtensionContext,
        _session: vscode.DebugSession,
    ) {
        // session is reserved for future use (multi-session disambiguation,
        // session.customRequest passthrough); not needed in v1.
    }

    handleMessage(message: vscode.DebugProtocolMessage): void {
        const m = message as Record<string, unknown>;
        if (m.type !== "request") return;
        const req = m as { seq: number; command: string; arguments?: unknown };
        this.dispatch(req).catch((err) => {
            this.respond(req, false, undefined, String(err));
        });
    }

    dispose(): void {
        if (this.vm) {
            this.vm.free();
            this.vm = null;
        }
    }

    // ---- dispatch ----------------------------------------------------------

    private async dispatch(req: {
        seq: number;
        command: string;
        arguments?: unknown;
    }): Promise<void> {
        switch (req.command) {
            case "initialize":
                this.respond(req, true, {
                    supportsConfigurationDoneRequest: true,
                    supportsSteppingGranularity: true,
                    supportsDisassembleRequest: true,
                    supportsBreakpointLocationsRequest: false,
                    supportsConditionalBreakpoints: false,
                    supportsValueFormattingOptions: false,
                });
                this.fireEvent("initialized");
                return;

            case "launch":
                this.launchPromise = this.onLaunch(req, req.arguments as LaunchArgs);
                await this.launchPromise;
                return;

            case "configurationDone":
                // Wait for any in-flight launch so this.vm is built before
                // we check stopOnEntry. Without this, configurationDone
                // arrives while launch is still doing async I/O and the
                // stopped-on-entry event silently never fires.
                await this.launchPromise;
                this.respond(req, true);
                if (this.vm && this.shouldStopOnEntry) {
                    this.fireStopped("entry");
                } else if (this.vm) {
                    void this.runUntilStop("continue");
                }
                return;

            case "threads":
                this.respond(req, true, {
                    threads: [{ id: THREAD_ID, name: "main" }],
                });
                return;

            case "stackTrace":
                this.respond(req, true, this.buildStackTrace());
                return;

            case "scopes":
                this.respond(req, true, {
                    scopes: [
                        {
                            name: "Locals",
                            variablesReference: REF_LOCALS,
                            expensive: false,
                        },
                        {
                            name: "Stack",
                            variablesReference: REF_STACK,
                            expensive: false,
                        },
                        {
                            name: "Memory (128 bytes)",
                            variablesReference: REF_MEMORY,
                            expensive: false,
                        },
                    ],
                });
                return;

            case "variables":
                this.respond(req, true, {
                    variables: this.buildVariables(
                        (req.arguments as { variablesReference: number })
                            .variablesReference,
                    ),
                });
                return;

            case "setBreakpoints":
                this.respond(req, true, this.onSetBreakpoints(req.arguments));
                return;

            case "continue":
                this.respond(req, true, { allThreadsContinued: true });
                void this.runUntilStop("continue");
                return;

            case "pause":
                this.pauseRequested = true;
                this.respond(req, true);
                return;

            case "next":
                this.respond(req, true);
                void this.runUntilStop("next");
                return;

            case "stepIn":
            case "stepOut":
                // tiny_vm has no calls in v1 — alias to next.
                this.respond(req, true);
                void this.runUntilStop("next");
                return;

            case "stepInstruction":
                this.respond(req, true);
                this.singleInstructionStep();
                return;

            case "disassemble":
                this.respond(req, true, this.buildDisassembly(req.arguments));
                return;

            case "evaluate":
                this.respond(req, true, {
                    result: "(evaluate not supported in v1)",
                    variablesReference: 0,
                });
                return;

            case "disconnect":
                this.respond(req, true);
                this.fireEvent("terminated");
                this.dispose();
                return;

            case "source":
                // VS Code only asks for this when a Source has no path; we
                // always emit a path, so this should not fire. Stub it.
                this.respond(req, true, { content: "" });
                return;

            default:
                this.respond(req, false, undefined, `unknown command ${req.command}`);
        }
    }

    // ---- launch -----------------------------------------------------------

    private shouldStopOnEntry = false;

    private async onLaunch(
        req: { seq: number; command: string },
        args: LaunchArgs,
    ): Promise<void> {
        this.shouldStopOnEntry = !!args.stopOnEntry;
        try {
            await ensureSimReady(this.context);
            const programUri = vscode.Uri.parse(args.program);
            this.programUri = programUri;
            const code = await vscode.workspace.fs.readFile(programUri);

            // Adjacent .map file (e.g. count10.bin -> count10.bin.map).
            const mapUri = programUri.with({ path: programUri.path + ".map" });
            try {
                const mapBytes = await vscode.workspace.fs.readFile(mapUri);
                this.map = parseSourceMap(new TextDecoder().decode(mapBytes));
                this.sourcePath = this.map.source;
            } catch {
                this.map = null;
                this.sourcePath = null;
                this.fireOutput(
                    `[tinyVm] no source map alongside ${programUri.path} — source-line stepping disabled\n`,
                    "console",
                );
            }

            this.vm = new WasmTinyVm(code);
            this.fireOutput(
                `[tinyVm] launched ${args.program} (${code.length} bytes)\n`,
                "console",
            );
            this.respond(req, true);
        } catch (e) {
            this.respond(req, false, undefined, `launch failed: ${e}`);
            this.fireEvent("terminated");
        }
    }

    // ---- stack / variables ------------------------------------------------

    private buildStackTrace(): {
        stackFrames: vscode.DebugProtocolMessage[];
        totalFrames: number;
    } {
        if (!this.vm) return { stackFrames: [], totalFrames: 0 };
        const pc = this.vm.pc();
        const entry = this.map ? pcToEntry(this.map, pc) : null;
        const frame: Record<string, unknown> = {
            id: 1,
            name: `pc=${pc} (op=0x${this.vm
                .code_byte(pc)
                .toString(16)
                .padStart(2, "0")})`,
            line: entry?.line ?? 0,
            column: entry?.col ?? 0,
            instructionPointerReference: pc.toString(),
        };
        if (this.map && this.sourcePath && entry) {
            const sourceUri = this.resolveSource(this.sourcePath);
            frame.source = {
                name: this.sourcePath.split("/").pop(),
                path: sourceUri.toString(),
            };
        }
        return {
            stackFrames: [frame as unknown as vscode.DebugProtocolMessage],
            totalFrames: 1,
        };
    }

    private buildVariables(ref: number): vscode.DebugProtocolMessage[] {
        if (!this.vm) return [];
        if (ref === REF_LOCALS) {
            const out: Record<string, unknown>[] = [];
            const declared = this.map?.locals ?? [];
            // Cover all declared locals plus any slot referenced by code; for
            // simplicity show all 16 slots, naming the declared ones.
            for (let slot = 0; slot < 16; slot++) {
                const dec = declared.find((l) => l.slot === slot);
                out.push({
                    name: dec ? `${dec.name} (slot ${slot})` : `slot ${slot}`,
                    value: this.vm.local_at(slot).toString(),
                    variablesReference: 0,
                });
            }
            return out as unknown as vscode.DebugProtocolMessage[];
        }
        if (ref === REF_STACK) {
            const sp = this.vm.sp();
            const out: Record<string, unknown>[] = [];
            for (let i = sp - 1; i >= 0; i--) {
                out.push({
                    name: `[${i}]${i === sp - 1 ? " (top)" : ""}`,
                    value: this.vm.stack_at(i).toString(),
                    variablesReference: 0,
                });
            }
            return out as unknown as vscode.DebugProtocolMessage[];
        }
        if (ref === REF_MEMORY) {
            const out: Record<string, unknown>[] = [];
            // Show 16 rows of 8 bytes.
            for (let row = 0; row < 16; row++) {
                const base = row * 8;
                const cells: string[] = [];
                for (let col = 0; col < 8; col++) {
                    cells.push(
                        this.vm
                            .mem_byte(base + col)
                            .toString(16)
                            .padStart(2, "0"),
                    );
                }
                out.push({
                    name: `0x${base.toString(16).padStart(2, "0")}`,
                    value: cells.join(" "),
                    variablesReference: 0,
                });
            }
            return out as unknown as vscode.DebugProtocolMessage[];
        }
        return [];
    }

    // ---- breakpoints ------------------------------------------------------

    private onSetBreakpoints(args: unknown): unknown {
        const a = args as {
            source: { path?: string };
            breakpoints?: { line: number }[];
        };
        const sourcePath = a.source?.path ?? "";
        const requested = a.breakpoints ?? [];
        const pcs = new Set<number>();
        const verified: { line: number; verified: boolean }[] = [];
        if (!this.map) {
            for (const bp of requested) {
                verified.push({ line: bp.line, verified: false });
            }
        } else {
            for (const bp of requested) {
                const adj = adjustBreakpoint(this.map, bp.line);
                if (adj) {
                    pcs.add(adj.pc);
                    verified.push({ line: adj.line, verified: true });
                } else {
                    verified.push({ line: bp.line, verified: false });
                }
            }
        }
        this.breakpoints.set(sourcePath, pcs);
        return { breakpoints: verified };
    }

    private breakpointPcs(): Set<number> {
        const all = new Set<number>();
        for (const pcs of this.breakpoints.values()) {
            for (const pc of pcs) all.add(pc);
        }
        return all;
    }

    // ---- execution --------------------------------------------------------

    /**
     * Run the sim until something causes a stop: breakpoint, pause, halt,
     * error, or — for `next` — the next source-line boundary. Emits the
     * appropriate `stopped`/`terminated` event.
     */
    private async runUntilStop(mode: "continue" | "next"): Promise<void> {
        if (!this.vm) return;
        const bps = this.breakpointPcs();
        const lineBoundaries =
            mode === "next" && this.map
                ? nextLineBoundaryPcs(this.map, this.vm.pc())
                : new Set<number>();

        const STEP_BUDGET = 200_000;
        let stepsThisChunk = 0;

        while (true) {
            if (this.pauseRequested) {
                this.pauseRequested = false;
                this.fireStopped("pause");
                return;
            }
            if (this.vm.halted()) {
                const last = this.vm.last_status();
                if (last === STATUS.HALT) {
                    this.fireOutput(
                        `[tinyVm] halted normally\n`,
                        "console",
                    );
                } else {
                    this.fireOutput(
                        `[tinyVm] aborted: status=${statusName(last)}\n`,
                        "console",
                    );
                }
                this.fireEvent("terminated");
                return;
            }
            const r = this.vm.step();
            stepsThisChunk += 1;
            if (r.status === STATUS.HOST_PENDING) {
                const rc = this.handleHostCall();
                this.vm.complete_host_call(rc);
            } else if (r.status < 0) {
                this.fireOutput(
                    `[tinyVm] runtime error: status=${statusName(r.status)} at pc=${r.pc_before}\n`,
                    "stderr",
                );
                this.fireEvent("terminated");
                return;
            }
            // Stop conditions:
            const newPc = this.vm.pc();
            if (bps.has(newPc)) {
                this.fireStopped("breakpoint");
                return;
            }
            if (mode === "next" && lineBoundaries.has(newPc)) {
                this.fireStopped("step");
                return;
            }
            // Yield to the event loop occasionally so pause requests are
            // visible. 200k steps is plenty for the small programs we run.
            if (stepsThisChunk >= STEP_BUDGET) {
                stepsThisChunk = 0;
                await new Promise((r) => setTimeout(r, 0));
            }
        }
    }

    private singleInstructionStep(): void {
        if (!this.vm) return;
        if (this.vm.halted()) {
            this.fireEvent("terminated");
            return;
        }
        const r = this.vm.step();
        if (r.status === STATUS.HOST_PENDING) {
            const rc = this.handleHostCall();
            this.vm.complete_host_call(rc);
        }
        if (this.vm.halted() && this.vm.last_status() !== STATUS.OK) {
            this.fireStopped(this.vm.last_status() === STATUS.HALT ? "step" : "exception");
        } else {
            this.fireStopped("step");
        }
    }

    private handleHostCall(): number {
        if (!this.vm) return -1;
        const host = this.vm.pending_host_id();
        switch (host) {
            case HOST.LED_WRITE: {
                const v = this.vm.pop();
                if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
                this.fireOutput(`led=${v}\n`, "stdout");
                return 0;
            }
            case HOST.DELAY_MS: {
                const v = this.vm.pop();
                if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
                this.fireOutput(`delay_ms=${v}\n`, "stdout");
                return 0;
            }
            case HOST.UART_PRINTLN_U32: {
                const v = this.vm.pop();
                if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
                this.fireOutput(`${v}\n`, "stdout");
                this.stdoutBuffer.push(`${v}`);
                return 0;
            }
            case HOST.UART_PRINTLN_HEX32: {
                const v = this.vm.pop();
                if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
                const hex = (v >>> 0).toString(16).toUpperCase().padStart(8, "0");
                this.fireOutput(`${hex}\n`, "stdout");
                this.stdoutBuffer.push(hex);
                return 0;
            }
            default:
                return -1;
        }
    }

    // ---- disassembly ------------------------------------------------------

    private buildDisassembly(args: unknown): unknown {
        if (!this.vm) return { instructions: [] };
        const a = args as {
            memoryReference: string;
            offset?: number;
            instructionOffset?: number;
            instructionCount: number;
        };
        const pcStart = Math.max(0, parseInt(a.memoryReference, 10) || 0);
        const count = a.instructionCount;
        const out: Record<string, unknown>[] = [];
        let pc = pcStart;
        for (let i = 0; i < count && pc < this.vm.code_len(); i++) {
            const op = this.vm.code_byte(pc);
            out.push({
                address: pc.toString(),
                instruction: opcodeName(op),
                instructionBytes: `0x${op.toString(16).padStart(2, "0")}`,
            });
            pc += instructionLength(op);
        }
        return { instructions: out };
    }

    // ---- DAP plumbing -----------------------------------------------------

    private respond(
        req: { seq: number; command: string },
        success: boolean,
        body?: unknown,
        message?: string,
    ): void {
        const msg: Record<string, unknown> = {
            seq: this.outSeq++,
            type: "response",
            request_seq: req.seq,
            command: req.command,
            success,
        };
        if (body !== undefined) msg.body = body;
        if (message !== undefined) msg.message = message;
        this.sender.fire(msg as unknown as vscode.DebugProtocolMessage);
    }

    private fireEvent(event: string, body?: unknown): void {
        const msg: Record<string, unknown> = {
            seq: this.outSeq++,
            type: "event",
            event,
        };
        if (body !== undefined) msg.body = body;
        this.sender.fire(msg as unknown as vscode.DebugProtocolMessage);
    }

    private fireStopped(reason: string): void {
        this.fireEvent("stopped", {
            reason,
            threadId: THREAD_ID,
            allThreadsStopped: true,
        });
    }

    private fireOutput(output: string, category: "stdout" | "stderr" | "console"): void {
        this.fireEvent("output", { category, output });
    }

    private resolveSource(sourcePath: string): vscode.Uri {
        // The map's "source" field is repo-relative. Try to resolve it
        // relative to the program URI's workspace folder.
        if (this.programUri) {
            const folder = vscode.workspace.getWorkspaceFolder(this.programUri);
            if (folder) {
                return vscode.Uri.joinPath(folder.uri, sourcePath);
            }
        }
        // Fall back to the first workspace folder.
        const first = vscode.workspace.workspaceFolders?.[0];
        if (first) return vscode.Uri.joinPath(first.uri, sourcePath);
        return vscode.Uri.file(sourcePath);
    }
}

// Approximate opcode -> mnemonic for disassembly. Authoritative table in
// common/include/tiny_vm.h.
function opcodeName(op: number): string {
    const names: Record<number, string> = {
        0x00: "NOP", 0x01: "PUSH8", 0x02: "ADD", 0x03: "SUB",
        0x04: "DUP", 0x05: "DROP", 0x06: "SWAP", 0x07: "JMP",
        0x08: "JZ", 0x09: "HOST", 0x0a: "LGET", 0x0b: "LSET",
        0x0c: "EQ", 0x0d: "LT", 0x0e: "PUSH16", 0x0f: "MOD",
        0x10: "MUL", 0x11: "DIV", 0x12: "MGET", 0x13: "MSET",
        0x14: "PUSH32", 0x15: "AND", 0x16: "OR", 0x17: "XOR",
        0x18: "NOT", 0x19: "SHL", 0x1a: "SHR", 0x1b: "ROL",
        0x1c: "ROR", 0x1d: "MGET32", 0x1e: "MSET32", 0xff: "HALT",
    };
    return names[op] ?? `OP_0x${op.toString(16)}`;
}

function instructionLength(op: number): number {
    switch (op) {
        case 0x01: // PUSH8
        case 0x09: // HOST id8
        case 0x0a: // LGET slot8
        case 0x0b: // LSET slot8
            return 2;
        case 0x07: // JMP target16
        case 0x08: // JZ target16
        case 0x0e: // PUSH16
            return 3;
        case 0x14: // PUSH32
            return 5;
        default:
            return 1;
    }
}
