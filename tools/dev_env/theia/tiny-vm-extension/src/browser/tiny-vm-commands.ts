import { inject, injectable } from '@theia/core/shared/inversify';
import { Command, CommandContribution, CommandRegistry, MessageService } from '@theia/core/lib/common';
import { DebugSessionManager } from '@theia/debug/lib/browser/debug-session-manager';
import { EditorManager } from '@theia/editor/lib/browser';
import { TINY_VM_DEBUG_TYPE } from '../common/tiny-vm-debug';

export const TINY_VM_DEBUG_IN_SIM: Command = {
    id: 'tinyVm.debugInSim',
    label: 'tiny_vm: Debug Current File in Simulator',
    category: 'tiny_vm'
};

export const TINY_VM_RUN_IN_SIM: Command = {
    id: 'tinyVm.runInSim',
    label: 'tiny_vm: Run Current File in Simulator',
    category: 'tiny_vm'
};

@injectable()
export class TinyVmCommandContribution implements CommandContribution {

    @inject(EditorManager)
    protected readonly editorManager!: EditorManager;

    @inject(DebugSessionManager)
    protected readonly debugSessionManager!: DebugSessionManager;

    @inject(MessageService)
    protected readonly messageService!: MessageService;

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(TINY_VM_DEBUG_IN_SIM, {
            execute: () => this.startDebugSession(true)
        });
        commands.registerCommand(TINY_VM_RUN_IN_SIM, {
            execute: () => this.startDebugSession(false)
        });
    }

    protected async startDebugSession(stopOnEntry: boolean): Promise<void> {
        const current = this.editorManager.currentEditor;
        if (!current) {
            this.messageService.warn('tiny_vm: open a .cvm.c or .vm file first');
            return;
        }
        const uri = current.editor.uri.toString();
        const program = uri.replace(/^file:\/\//, '');
        const name = `tiny_vm: ${program.split('/').pop() || program}`;
        try {
            await this.debugSessionManager.start({
                name,
                configuration: {
                    type: TINY_VM_DEBUG_TYPE,
                    request: 'launch',
                    name,
                    program,
                    stopOnEntry
                }
            });
        } catch (err) {
            this.messageService.error(`tiny_vm: failed to start: ${err}`);
        }
    }
}
