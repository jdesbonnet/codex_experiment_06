import { ContainerModule } from '@theia/core/shared/inversify';
import { DebugAdapterContribution } from '@theia/debug/lib/common/debug-model';
import { TinyVmDebugAdapterContribution } from './tiny-vm-debug-adapter-contribution';

export default new ContainerModule(bind => {
    bind(TinyVmDebugAdapterContribution).toSelf().inSingletonScope();
    bind(DebugAdapterContribution).toService(TinyVmDebugAdapterContribution);
});
