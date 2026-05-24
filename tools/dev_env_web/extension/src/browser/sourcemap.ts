// Source map types and lookups for tiny_vm bytecode.
//
// Schema matches the JSON emitted by `tools/vm_cc.py --map` (and the smaller
// `tools/vm_asm.py --map` variant). See docs/theia_proposal.md §5.2 and
// tools/dev_env/sim/sourcemap.py for the authoritative source.

export interface MapEntry {
    pc: number;
    line: number;
    col?: number;
    kind?: string;
}

export interface LocalEntry {
    slot: number;
    name: string;
    line: number;
}

export interface SourceMap {
    version: number;
    source: string;
    bytecode_size: number;
    entries: MapEntry[];
    locals?: LocalEntry[];
}

export function parseSourceMap(text: string): SourceMap {
    const obj = JSON.parse(text);
    if (typeof obj !== "object" || obj === null) {
        throw new Error("source map: not a JSON object");
    }
    if (obj.version !== 1) {
        throw new Error(`source map: unsupported version ${obj.version}`);
    }
    if (!Array.isArray(obj.entries)) {
        throw new Error("source map: entries[] missing");
    }
    return obj as SourceMap;
}

/**
 * Find the source line for a given PC by picking the entry whose pc is
 * the largest <= the query. Returns null if no entry covers it.
 */
export function pcToEntry(map: SourceMap, pc: number): MapEntry | null {
    let best: MapEntry | null = null;
    for (const e of map.entries) {
        if (e.pc <= pc && (!best || e.pc > best.pc)) {
            best = e;
        }
    }
    return best;
}

/**
 * First PC for a given source line. Used by setBreakpoints to translate
 * `count10.cvm.c:5` into a bytecode-level break.
 */
export function lineToFirstPc(map: SourceMap, line: number): number | null {
    let best: number | null = null;
    for (const e of map.entries) {
        if (e.line === line && (best === null || e.pc < best)) {
            best = e.pc;
        }
    }
    return best;
}

/**
 * Adjusted breakpoint: VS Code calls `setBreakpoints` with the line the user
 * clicked; if there is no entry for that exact line, we snap forward to the
 * next line that *does* have one. Returns the adjusted line and its PC.
 */
export function adjustBreakpoint(
    map: SourceMap,
    requestedLine: number,
): { line: number; pc: number } | null {
    let bestLine: number | null = null;
    let bestPc: number | null = null;
    for (const e of map.entries) {
        if (e.line >= requestedLine) {
            if (
                bestLine === null ||
                e.line < bestLine ||
                (e.line === bestLine && bestPc !== null && e.pc < bestPc)
            ) {
                bestLine = e.line;
                bestPc = e.pc;
            }
        }
    }
    if (bestLine === null || bestPc === null) return null;
    return { line: bestLine, pc: bestPc };
}

/**
 * Set of PCs that begin a *different* source line than the entry at
 * `currentPc`. Used for source-line stepping (`next`): we want to run
 * until the PC hits one of these.
 */
export function nextLineBoundaryPcs(map: SourceMap, currentPc: number): Set<number> {
    const currentEntry = pcToEntry(map, currentPc);
    const currentLine = currentEntry?.line ?? -1;
    const out = new Set<number>();
    for (const e of map.entries) {
        if (e.line !== currentLine) out.add(e.pc);
    }
    return out;
}
