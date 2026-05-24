/* @ts-self-types="./tiny_vm_sim.d.ts" */

export class WasmStepResult {
    static __wrap(ptr) {
        const obj = Object.create(WasmStepResult.prototype);
        obj.__wbg_ptr = ptr;
        WasmStepResultFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        WasmStepResultFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_wasmstepresult_free(ptr, 0);
    }
    /**
     * @returns {number}
     */
    get op() {
        const ret = wasm.__wbg_get_wasmstepresult_op(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    get pc_after() {
        const ret = wasm.__wbg_get_wasmstepresult_pc_after(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    get pc_before() {
        const ret = wasm.__wbg_get_wasmstepresult_pc_before(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    get status() {
        const ret = wasm.__wbg_get_wasmstepresult_status(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} arg0
     */
    set op(arg0) {
        wasm.__wbg_set_wasmstepresult_op(this.__wbg_ptr, arg0);
    }
    /**
     * @param {number} arg0
     */
    set pc_after(arg0) {
        wasm.__wbg_set_wasmstepresult_pc_after(this.__wbg_ptr, arg0);
    }
    /**
     * @param {number} arg0
     */
    set pc_before(arg0) {
        wasm.__wbg_set_wasmstepresult_pc_before(this.__wbg_ptr, arg0);
    }
    /**
     * @param {number} arg0
     */
    set status(arg0) {
        wasm.__wbg_set_wasmstepresult_status(this.__wbg_ptr, arg0);
    }
}
if (Symbol.dispose) WasmStepResult.prototype[Symbol.dispose] = WasmStepResult.prototype.free;

/**
 * JS-facing handle. Wraps `TinyVm` and exposes the methods the in-browser
 * DAP server (`tools/vscode/extension/src/browser/debugAdapter.ts`)
 * needs. Methods that can fail return `i32` status codes — JS reads them
 * and translates to DAP events.
 */
export class WasmTinyVm {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        WasmTinyVmFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_wasmtinyvm_free(ptr, 0);
    }
    /**
     * @param {number} idx
     * @returns {number}
     */
    code_byte(idx) {
        const ret = wasm.wasmtinyvm_code_byte(this.__wbg_ptr, idx);
        return ret;
    }
    /**
     * @returns {number}
     */
    code_len() {
        const ret = wasm.wasmtinyvm_code_len(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} rc
     */
    complete_host_call(rc) {
        wasm.wasmtinyvm_complete_host_call(this.__wbg_ptr, rc);
    }
    /**
     * @returns {boolean}
     */
    halted() {
        const ret = wasm.wasmtinyvm_halted(this.__wbg_ptr);
        return ret !== 0;
    }
    /**
     * @returns {number}
     */
    last_status() {
        const ret = wasm.wasmtinyvm_last_status(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} idx
     * @returns {number}
     */
    local_at(idx) {
        const ret = wasm.wasmtinyvm_local_at(this.__wbg_ptr, idx);
        return ret;
    }
    /**
     * @param {number} idx
     * @returns {number}
     */
    mem_byte(idx) {
        const ret = wasm.wasmtinyvm_mem_byte(this.__wbg_ptr, idx);
        return ret;
    }
    /**
     * @param {Uint8Array} code
     */
    constructor(code) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            const ptr0 = passArray8ToWasm0(code, wasm.__wbindgen_export);
            const len0 = WASM_VECTOR_LEN;
            wasm.wasmtinyvm_new(retptr, ptr0, len0);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            var r2 = getDataViewMemory0().getInt32(retptr + 4 * 2, true);
            if (r2) {
                throw takeObject(r1);
            }
            this.__wbg_ptr = r0;
            WasmTinyVmFinalization.register(this, this.__wbg_ptr, this);
            return this;
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * @returns {number}
     */
    pc() {
        const ret = wasm.wasmtinyvm_pc(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    pending_host_id() {
        const ret = wasm.wasmtinyvm_pending_host_id(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    pop() {
        const ret = wasm.wasmtinyvm_pop(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} v
     * @returns {number}
     */
    push(v) {
        const ret = wasm.wasmtinyvm_push(this.__wbg_ptr, v);
        return ret;
    }
    /**
     * @param {number} step_budget
     * @returns {number}
     */
    run(step_budget) {
        const ret = wasm.wasmtinyvm_run(this.__wbg_ptr, step_budget);
        return ret;
    }
    /**
     * @param {number} idx
     * @param {number} v
     */
    set_local(idx, v) {
        wasm.wasmtinyvm_set_local(this.__wbg_ptr, idx, v);
    }
    /**
     * @returns {number}
     */
    sp() {
        const ret = wasm.wasmtinyvm_sp(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} idx
     * @returns {number}
     */
    stack_at(idx) {
        const ret = wasm.wasmtinyvm_stack_at(this.__wbg_ptr, idx);
        return ret;
    }
    /**
     * @returns {WasmStepResult}
     */
    step() {
        const ret = wasm.wasmtinyvm_step(this.__wbg_ptr);
        return WasmStepResult.__wrap(ret);
    }
}
if (Symbol.dispose) WasmTinyVm.prototype[Symbol.dispose] = WasmTinyVm.prototype.free;
function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg___wbindgen_throw_1506f2235d1bdba0: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbindgen_cast_0000000000000001: function(arg0) {
            // Cast intrinsic for `F64 -> Externref`.
            const ret = arg0;
            return addHeapObject(ret);
        },
    };
    return {
        __proto__: null,
        "./tiny_vm_sim_bg.js": import0,
    };
}

const WasmStepResultFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_wasmstepresult_free(ptr, 1));
const WasmTinyVmFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_wasmtinyvm_free(ptr, 1));

function addHeapObject(obj) {
    if (heap_next === heap.length) heap.push(heap.length + 1);
    const idx = heap_next;
    heap_next = heap[idx];

    heap[idx] = obj;
    return idx;
}

function dropObject(idx) {
    if (idx < 1028) return;
    heap[idx] = heap_next;
    heap_next = idx;
}

let cachedDataViewMemory0 = null;
function getDataViewMemory0() {
    if (cachedDataViewMemory0 === null || cachedDataViewMemory0.buffer.detached === true || (cachedDataViewMemory0.buffer.detached === undefined && cachedDataViewMemory0.buffer !== wasm.memory.buffer)) {
        cachedDataViewMemory0 = new DataView(wasm.memory.buffer);
    }
    return cachedDataViewMemory0;
}

function getStringFromWasm0(ptr, len) {
    return decodeText(ptr >>> 0, len);
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function getObject(idx) { return heap[idx]; }

let heap = new Array(1024).fill(undefined);
heap.push(undefined, null, true, false);

let heap_next = heap.length;

function passArray8ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 1, 1) >>> 0;
    getUint8ArrayMemory0().set(arg, ptr / 1);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function takeObject(idx) {
    const ret = getObject(idx);
    dropObject(idx);
    return ret;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

let WASM_VECTOR_LEN = 0;

let wasmModule, wasmInstance, wasm;
function __wbg_finalize_init(instance, module) {
    wasmInstance = instance;
    wasm = instance.exports;
    wasmModule = module;
    cachedDataViewMemory0 = null;
    cachedUint8ArrayMemory0 = null;
    return wasm;
}

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = module.ok && expectedResponseType(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else { throw e; }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }

    function expectedResponseType(type) {
        switch (type) {
            case 'basic': case 'cors': case 'default': return true;
        }
        return false;
    }
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (module !== undefined) {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

async function __wbg_init(module_or_path) {
    if (wasm !== undefined) return wasm;


    if (module_or_path !== undefined) {
        if (Object.getPrototypeOf(module_or_path) === Object.prototype) {
            ({module_or_path} = module_or_path)
        } else {
            console.warn('using deprecated parameters for the initialization function; pass a single object instead')
        }
    }

    if (module_or_path === undefined) {
        module_or_path = new URL('tiny_vm_sim_bg.wasm', import.meta.url);
    }
    const imports = __wbg_get_imports();

    if (typeof module_or_path === 'string' || (typeof Request === 'function' && module_or_path instanceof Request) || (typeof URL === 'function' && module_or_path instanceof URL)) {
        module_or_path = fetch(module_or_path);
    }

    const { instance, module } = await __wbg_load(await module_or_path, imports);

    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };
