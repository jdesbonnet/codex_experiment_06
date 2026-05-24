import { ContainerModule } from '@theia/core/shared/inversify';
import { LanguageGrammarDefinitionContribution } from '@theia/monaco/lib/browser/textmate';
import { CommandContribution } from '@theia/core/lib/common';

import { TinyVmLanguageContribution } from './tiny-vm-language-contribution';
import { TinyVmCommandContribution } from './tiny-vm-commands';

export default new ContainerModule(bind => {
    bind(TinyVmLanguageContribution).toSelf().inSingletonScope();
    bind(LanguageGrammarDefinitionContribution).toService(TinyVmLanguageContribution);

    bind(TinyVmCommandContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(TinyVmCommandContribution);
});
