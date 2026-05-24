// IDE commands for the cloud projects API. The CloudFileSystemProvider
// is registered separately; these commands talk to the API to manage
// projects and surface them as workspace folders.

import * as vscode from "vscode";
import * as api from "./api-client";
import { fileUri } from "./filesystem/cloud";

const STARTER_FILENAME = "hello.cvm.c";
const STARTER_CONTENT = `/* tiny_vm starter — blink the on-board LED forever */
const int ON = 1;
const int OFF = 0;
const int TICK_MS = 500;

while (1) {
    led_write(ON);
    delay_ms(TICK_MS);
    led_write(OFF);
    delay_ms(TICK_MS);
}
`;

export async function newProjectCommand(): Promise<void> {
    const name = await vscode.window.showInputBox({
        prompt: "Name for the new tiny_vm project",
        placeHolder: "my-blink",
        validateInput: (v) => {
            if (!v.trim()) return "name cannot be empty";
            if (v.length > 200) return "name too long";
            return null;
        },
    });
    if (!name) return;

    let project: api.Project;
    try {
        project = await api.createProject(name.trim());
    } catch (e) {
        vscode.window.showErrorMessage(`tiny_vm: create failed: ${e}`);
        return;
    }

    // Seed with a starter file so the user lands somewhere productive.
    try {
        await api.writeFile(
            project.id,
            STARTER_FILENAME,
            new TextEncoder().encode(STARTER_CONTENT),
        );
    } catch (e) {
        vscode.window.showWarningMessage(
            `tiny_vm: project created but starter file failed: ${e}`,
        );
    }

    await openStarterFile(project);
}

export async function openProjectCommand(): Promise<void> {
    let projects: api.Project[];
    try {
        projects = await api.listProjects();
    } catch (e) {
        vscode.window.showErrorMessage(`tiny_vm: list failed: ${e}`);
        return;
    }
    if (projects.length === 0) {
        const action = await vscode.window.showInformationMessage(
            "tiny_vm: no projects yet. Create one?",
            "New Project",
        );
        if (action === "New Project") {
            await newProjectCommand();
        }
        return;
    }
    const picked = await vscode.window.showQuickPick(
        projects.map((p) => ({
            label: p.name,
            description: `(modified ${shortDate(p.modifiedAt)})`,
            detail: p.id,
            project: p,
        })),
        { placeHolder: "Pick a tiny_vm project to open" },
    );
    if (!picked) return;
    await openStarterFile(picked.project);
}

/**
 * Pick a file to open from the project and surface it in the editor.
 * If the project has hello.cvm.c, prefer that; otherwise open the first
 * file we find. v1 doesn't add the project as a workspace folder
 * because adding a workspace folder to a single-folder workspace
 * triggers a multi-root conversion + page reload in VS Code Web —
 * disruptive UX. Files can still be navigated via File > Open File.
 */
async function openStarterFile(project: api.Project): Promise<void> {
    let entries: api.FileEntry[] = [];
    try {
        entries = await api.listFiles(project.id);
    } catch (e) {
        vscode.window.showErrorMessage(`tiny_vm: open failed: ${e}`);
        return;
    }
    const fileEntries = entries.filter((e) => e.type === "file");
    if (fileEntries.length === 0) {
        vscode.window.showInformationMessage(
            `tiny_vm: project "${project.name}" has no files yet`,
        );
        return;
    }
    const preferred =
        fileEntries.find((e) => e.path === STARTER_FILENAME) ?? fileEntries[0]!;
    const uri = fileUri(project.id, preferred.path);
    try {
        const doc = await vscode.workspace.openTextDocument(uri);
        await vscode.window.showTextDocument(doc);
    } catch (e) {
        vscode.window.showErrorMessage(
            `tiny_vm: failed to open ${preferred.path}: ${e}`,
        );
    }
}

export async function deleteProjectCommand(): Promise<void> {
    let projects: api.Project[];
    try {
        projects = await api.listProjects();
    } catch (e) {
        vscode.window.showErrorMessage(`tiny_vm: list failed: ${e}`);
        return;
    }
    if (projects.length === 0) {
        vscode.window.showInformationMessage("tiny_vm: no projects to delete");
        return;
    }
    const picked = await vscode.window.showQuickPick(
        projects.map((p) => ({ label: p.name, detail: p.id, project: p })),
        { placeHolder: "Pick a tiny_vm project to delete" },
    );
    if (!picked) return;
    const confirm = await vscode.window.showWarningMessage(
        `Delete project "${picked.project.name}" and all its files?`,
        { modal: true },
        "Delete",
    );
    if (confirm !== "Delete") return;
    try {
        await api.deleteProject(picked.project.id);
    } catch (e) {
        vscode.window.showErrorMessage(`tiny_vm: delete failed: ${e}`);
        return;
    }
    vscode.window.showInformationMessage(`tiny_vm: deleted "${picked.project.name}"`);
}

function shortDate(iso: string): string {
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}
