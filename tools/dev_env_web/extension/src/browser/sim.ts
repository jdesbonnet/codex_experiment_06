// Thin TypeScript wrapper around the wasm tiny_vm sim
// (tools/dev_env_web/sim/pkg/). Lazily initialises the wasm module from the
// extension's wasm/ directory and re-exports the JS bindings.

import * as vscode from "vscode";

// The wasm-pack output sits at extension/wasm/, copied there by
// scripts/install.sh from sim/pkg/. Esbuild bundles tiny_vm_sim.js into the
// extension worker; the .wasm bytes are loaded at runtime via
// vscode.workspace.fs.readFile so we don't need a fetch-able URL.
//
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — the .d.ts ships next to the .js but TS doesn't always pick
// it up from a non-package path. The wasm/ folder is gitignored anyway.
import init, { WasmTinyVm, WasmStepResult } from "../../wasm/tiny_vm_sim.js";

export { WasmTinyVm, WasmStepResult };

// Status codes — mirror of constants in
// tools/dev_env_web/sim/rust/src/lib.rs. JS-side consumers compare against
// these instead of magic numbers.
export const STATUS = {
    OK: 0,
    HALT: 1,
    STEP_LIMIT: 2,
    HOST_PENDING: 3,
    ERR_PC_OOB: -1,
    ERR_STACK_OVERFLOW: -2,
    ERR_STACK_UNDERFLOW: -3,
    ERR_BAD_OPCODE: -4,
    ERR_HOST: -5,
    ERR_CODE_TOO_LARGE: -6,
    ERR_MEM_OOB: -7,
} as const;

export const HOST = {
    LED_WRITE: 0,
    DELAY_MS: 1,
    UART_PRINTLN_U32: 2,
    UART_PRINTLN_HEX32: 3,
} as const;

let initPromise: Promise<void> | null = null;

/**
 * Initialise the wasm module exactly once. Subsequent calls return the
 * same promise. Throws on first call if the .wasm bytes cannot be read.
 */
export function ensureSimReady(context: vscode.ExtensionContext): Promise<void> {
    if (!initPromise) {
        initPromise = (async () => {
            const wasmUri = vscode.Uri.joinPath(
                context.extensionUri,
                "wasm",
                "tiny_vm_sim_bg.wasm",
            );
            const bytes = await vscode.workspace.fs.readFile(wasmUri);
            // Pass bytes directly so the wasm-pack JS does not try to
            // resolve a default URL via import.meta.url (undefined in the
            // bundled CJS worker).
            await init({ module_or_path: bytes });
        })();
    }
    return initPromise;
}

/**
 * Run a bytecode image through a fresh WasmTinyVm with the default host call
 * handlers (matching tools/dev_env/sim/host_calls.py DefaultHostCalls).
 * Returns the captured stdout and the final status code.
 *
 * This is the M3 smoke path. The full DAP-driven execution is built on the
 * same coroutine handshake but yields control between steps for break /
 * inspect.
 */
export function runProgram(
    code: Uint8Array,
    onOutput?: (line: string) => void,
): { status: number; stdout: string[] } {
    const vm = new WasmTinyVm(code);
    const stdout: string[] = [];
    try {
        while (true) {
            const status = vm.run(1_000_000);
            if (status !== STATUS.HOST_PENDING) {
                return { status, stdout };
            }
            const host = vm.pending_host_id();
            const rc = handleHostCall(vm, host, (s) => {
                stdout.push(s);
                onOutput?.(s);
            });
            vm.complete_host_call(rc);
        }
    } finally {
        vm.free();
    }
}

function handleHostCall(
    vm: WasmTinyVm,
    host: number,
    emit: (line: string) => void,
): number {
    switch (host) {
        case HOST.LED_WRITE:
        case HOST.DELAY_MS: {
            // Pop the argument; no other observable effect for the smoke path.
            const v = vm.pop();
            if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
            return 0;
        }
        case HOST.UART_PRINTLN_U32: {
            const v = vm.pop();
            if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
            emit(`${v}`);
            return 0;
        }
        case HOST.UART_PRINTLN_HEX32: {
            const v = vm.pop();
            if (v === STATUS.ERR_STACK_UNDERFLOW) return -1;
            const hex = (v >>> 0).toString(16).toUpperCase().padStart(8, "0");
            emit(hex);
            return 0;
        }
        default:
            return -1;
    }
}

export function statusName(code: number): string {
    switch (code) {
        case STATUS.OK: return "OK";
        case STATUS.HALT: return "HALT";
        case STATUS.STEP_LIMIT: return "STEP_LIMIT";
        case STATUS.HOST_PENDING: return "HOST_PENDING";
        case STATUS.ERR_PC_OOB: return "ERR_PC_OOB";
        case STATUS.ERR_STACK_OVERFLOW: return "ERR_STACK_OVERFLOW";
        case STATUS.ERR_STACK_UNDERFLOW: return "ERR_STACK_UNDERFLOW";
        case STATUS.ERR_BAD_OPCODE: return "ERR_BAD_OPCODE";
        case STATUS.ERR_HOST: return "ERR_HOST";
        case STATUS.ERR_CODE_TOO_LARGE: return "ERR_CODE_TOO_LARGE";
        case STATUS.ERR_MEM_OOB: return "ERR_MEM_OOB";
        default: return `UNKNOWN(${code})`;
    }
}
