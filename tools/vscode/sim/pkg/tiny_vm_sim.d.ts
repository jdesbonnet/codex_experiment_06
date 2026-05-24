/* tslint:disable */
/* eslint-disable */

export class WasmStepResult {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    op: number;
    pc_after: number;
    pc_before: number;
    status: number;
}

/**
 * JS-facing handle. Wraps `TinyVm` and exposes the methods the in-browser
 * DAP server (`tools/vscode/extension/src/browser/debugAdapter.ts`)
 * needs. Methods that can fail return `i32` status codes — JS reads them
 * and translates to DAP events.
 */
export class WasmTinyVm {
    free(): void;
    [Symbol.dispose](): void;
    code_byte(idx: number): number;
    code_len(): number;
    complete_host_call(rc: number): void;
    halted(): boolean;
    last_status(): number;
    local_at(idx: number): number;
    mem_byte(idx: number): number;
    constructor(code: Uint8Array);
    pc(): number;
    pending_host_id(): number;
    pop(): number;
    push(v: number): number;
    run(step_budget: number): number;
    set_local(idx: number, v: number): void;
    sp(): number;
    stack_at(idx: number): number;
    step(): WasmStepResult;
}

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_get_wasmstepresult_op: (a: number) => number;
    readonly __wbg_get_wasmstepresult_pc_after: (a: number) => number;
    readonly __wbg_get_wasmstepresult_pc_before: (a: number) => number;
    readonly __wbg_get_wasmstepresult_status: (a: number) => number;
    readonly __wbg_set_wasmstepresult_op: (a: number, b: number) => void;
    readonly __wbg_set_wasmstepresult_pc_after: (a: number, b: number) => void;
    readonly __wbg_set_wasmstepresult_pc_before: (a: number, b: number) => void;
    readonly __wbg_set_wasmstepresult_status: (a: number, b: number) => void;
    readonly __wbg_wasmstepresult_free: (a: number, b: number) => void;
    readonly __wbg_wasmtinyvm_free: (a: number, b: number) => void;
    readonly wasmtinyvm_code_byte: (a: number, b: number) => number;
    readonly wasmtinyvm_code_len: (a: number) => number;
    readonly wasmtinyvm_complete_host_call: (a: number, b: number) => void;
    readonly wasmtinyvm_halted: (a: number) => number;
    readonly wasmtinyvm_last_status: (a: number) => number;
    readonly wasmtinyvm_local_at: (a: number, b: number) => number;
    readonly wasmtinyvm_mem_byte: (a: number, b: number) => number;
    readonly wasmtinyvm_new: (a: number, b: number, c: number) => void;
    readonly wasmtinyvm_pc: (a: number) => number;
    readonly wasmtinyvm_pending_host_id: (a: number) => number;
    readonly wasmtinyvm_pop: (a: number) => number;
    readonly wasmtinyvm_push: (a: number, b: number) => number;
    readonly wasmtinyvm_run: (a: number, b: number) => number;
    readonly wasmtinyvm_set_local: (a: number, b: number, c: number) => void;
    readonly wasmtinyvm_sp: (a: number) => number;
    readonly wasmtinyvm_stack_at: (a: number, b: number) => number;
    readonly wasmtinyvm_step: (a: number) => number;
    readonly __wbindgen_add_to_stack_pointer: (a: number) => number;
    readonly __wbindgen_export: (a: number, b: number) => number;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
