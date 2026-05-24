import { injectable } from '@theia/core/shared/inversify';
import {
    LanguageGrammarDefinitionContribution,
    TextmateRegistry,
    getEncodedLanguageId
} from '@theia/monaco/lib/browser/textmate';
import * as monaco from '@theia/monaco-editor-core';

import { TINY_VM_LANGUAGE_C, TINY_VM_LANGUAGE_ASM } from '../common/tiny-vm-debug';

const CVM_C_GRAMMAR_SCOPE = 'source.tiny-vm-c';
const VM_ASM_GRAMMAR_SCOPE = 'source.tiny-vm-asm';

@injectable()
export class TinyVmLanguageContribution implements LanguageGrammarDefinitionContribution {

    registerTextmateLanguage(registry: TextmateRegistry): void {
        // Register language IDs and file associations
        monaco.languages.register({
            id: TINY_VM_LANGUAGE_C,
            aliases: ['tiny_vm C', 'cvm-c'],
            extensions: ['.cvm.c'],
            mimetypes: ['text/x-tiny-vm-c']
        });
        monaco.languages.register({
            id: TINY_VM_LANGUAGE_ASM,
            aliases: ['tiny_vm assembly', 'vm-asm'],
            extensions: ['.vm'],
            mimetypes: ['text/x-tiny-vm-asm']
        });

        // Minimal Monaco language configurations
        monaco.languages.setLanguageConfiguration(TINY_VM_LANGUAGE_C, {
            comments: { lineComment: '//', blockComment: ['/*', '*/'] },
            brackets: [['{', '}'], ['(', ')']],
            autoClosingPairs: [
                { open: '{', close: '}' },
                { open: '(', close: ')' }
            ]
        });
        monaco.languages.setLanguageConfiguration(TINY_VM_LANGUAGE_ASM, {
            comments: { lineComment: '#' }
        });

        // Register TextMate grammars
        registry.registerTextmateGrammarScope(CVM_C_GRAMMAR_SCOPE, {
            async getGrammarDefinition() {
                return {
                    format: 'json',
                    content: require('../../data/cvm-c.tmLanguage.json')
                };
            }
        });
        registry.mapLanguageIdToTextmateGrammar(TINY_VM_LANGUAGE_C, CVM_C_GRAMMAR_SCOPE);

        registry.registerTextmateGrammarScope(VM_ASM_GRAMMAR_SCOPE, {
            async getGrammarDefinition() {
                return {
                    format: 'json',
                    content: require('../../data/vm-asm.tmLanguage.json')
                };
            }
        });
        registry.mapLanguageIdToTextmateGrammar(TINY_VM_LANGUAGE_ASM, VM_ASM_GRAMMAR_SCOPE);

        // touch encoded language ids so Monaco loads them eagerly
        getEncodedLanguageId(TINY_VM_LANGUAGE_C);
        getEncodedLanguageId(TINY_VM_LANGUAGE_ASM);
    }
}
