import * as path from 'path';
import * as os from 'os';
import * as fs from 'fs';
import * as cp from 'child_process';
import { injectable } from '@theia/core/shared/inversify';
import { DebugAdapterContribution, DebugAdapterExecutable } from '@theia/debug/lib/common/debug-model';
import { DebugConfiguration } from '@theia/debug/lib/common/debug-configuration';
import { MaybePromise } from '@theia/core/lib/common';
import {
    TINY_VM_DEBUG_TYPE,
    TINY_VM_DEBUG_LABEL,
    TINY_VM_LANGUAGE_C,
    TINY_VM_LANGUAGE_ASM
} from '../common/tiny-vm-debug';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..', '..');
const DAP_SERVER = path.join(REPO_ROOT, 'tools', 'theia', 'dap', 'server.py');
const VM_CC = path.join(REPO_ROOT, 'tools', 'vm_cc.py');
const VM_ASM = path.join(REPO_ROOT, 'tools', 'vm_asm.py');

@injectable()
export class TinyVmDebugAdapterContribution implements DebugAdapterContribution {

    readonly type = TINY_VM_DEBUG_TYPE;
    readonly label: MaybePromise<string> = TINY_VM_DEBUG_LABEL;
    readonly languages: MaybePromise<string[]> = [TINY_VM_LANGUAGE_C, TINY_VM_LANGUAGE_ASM];

    provideDebugConfigurations(): MaybePromise<DebugConfiguration[]> {
        return [{
            type: TINY_VM_DEBUG_TYPE,
            request: 'launch',
            name: 'tiny_vm: run current file in simulator',
            program: '${file}',
            stopOnEntry: false
        }];
    }

    async resolveDebugConfiguration(config: DebugConfiguration): Promise<DebugConfiguration | undefined> {
        // Lazy-import-friendly: if the user opened a .cvm.c or .vm file, build a .bin
        // and feed it to the DAP server. We also pass the .map sidecar when present.
        const sourcePath: string | undefined = (config as any).program;
        if (!sourcePath) {
            return config;
        }
        const isC = sourcePath.endsWith('.cvm.c');
        const isAsm = sourcePath.endsWith('.vm');
        if (!isC && !isAsm) {
            // Already a .bin or unknown; pass through.
            return config;
        }
        const outDir = path.join(os.tmpdir(), 'tiny-vm-theia');
        await fs.promises.mkdir(outDir, { recursive: true });
        const base = path.basename(sourcePath).replace(/\.cvm\.c$/, '').replace(/\.vm$/, '');
        const binPath = path.join(outDir, `${base}.bin`);
        const mapPath = `${binPath}.map`;

        await new Promise<void>((resolve, reject) => {
            const tool = isC ? VM_CC : VM_ASM;
            const proc = cp.spawn('python3', [tool, sourcePath, '-o', binPath, '--map'], {
                cwd: REPO_ROOT,
                stdio: ['ignore', 'pipe', 'pipe']
            });
            let stderr = '';
            proc.stderr.on('data', (d: Buffer) => { stderr += d.toString('utf-8'); });
            proc.on('error', reject);
            proc.on('exit', code => {
                if (code === 0) {
                    resolve();
                } else {
                    reject(new Error(`${path.basename(tool)} exited ${code}: ${stderr}`));
                }
            });
        });

        return {
            ...config,
            program: binPath,
            source: sourcePath,
            sourceMap: mapPath
        };
    }

    async provideDebugAdapterExecutable(_config: DebugConfiguration): Promise<DebugAdapterExecutable> {
        return {
            command: 'python3',
            args: [DAP_SERVER, '--stdio']
        };
    }
}
