# Cloud Storage for tiny_vm VS Code Web

## 1. Purpose and Scope

Promotes the "deferred to v2" cloud project storage item from
`docs/vscode_proposal.md` §1 into a built feature. Success criteria
(per the user, 2026-05-24):

- The IDE has commands to create a new project and open an existing one.
- A project is a named, server-backed collection of files.
- Editing a file in the IDE saves it through the API to disk on the server.
- Closing the browser and re-opening it restores the workspace to the same
  project, with the same files at the same content.
- Compile + emulate continue to work, scoped per project.

Out of scope for this iteration:

- **Authentication**. v1 treats every request as belonging to a single
  anonymous user. The API and URL design are nonetheless shaped so that
  adding `user_id` filtering later does not change wire-format paths.
- **Sharing, collaboration, branching, history**. Last-write-wins.
- **Compiled-artifact caching server-side**. The IDE still stages the
  compile output into OPFS at `tinyvm-opfs:/.cache/`.
- **Hardware flashing from the cloud project**. Same `/api/compile`
  pipeline; hardware path is unchanged.

## 2. Existing Components (Reused)

The first cloud-storage iteration reuses, unchanged:

| Component                                          | Role in this plan                             |
| -------------------------------------------------- | --------------------------------------------- |
| `tools/dev_env_web/host/compile-server.mjs`        | Same Node HTTP process now also hosts `/api/projects`. |
| `tools/dev_env_web/extension/src/browser/compile.ts` | Already a `fetch()` client of the same origin. New code uses the same `tinyVm.apiUrl` setting. |
| `OpfsFileSystemProvider` (`filesystem/opfs.ts`)    | Reference implementation of the FileSystemProvider interface. The cloud provider mirrors its shape. |
| `tinyVm.debugBytecode` flow                        | Stays as-is. The cloud provider returns the source bytes; compile + DAP launch are unchanged. |

## 3. Architecture

```
Browser                                          Server (dev: Node sidecar; prod: Spring Boot)

  Monaco editor                                   ┌─ Same process listens on :3001 ─┐
        │                                         │                                  │
  tinyvm-cloud:                                   ├─ POST /api/compile   (existing)  │
  FileSystemProvider  ──── fetch() ─────────────► ├─ GET    /api/projects            │
        │                                         ├─ POST   /api/projects            │
  tinyVm.cloud.* commands                         ├─ GET    /api/projects/{id}       │
        │                                         ├─ DELETE /api/projects/{id}       │
  Workspace folder ◄──── persisted by VS Code     ├─ GET    /api/projects/{id}/files │
  Web's own state (per-origin IndexedDB)          ├─ GET    /api/projects/{id}/files/{path} │
                                                  ├─ PUT    /api/projects/{id}/files/{path} │
                                                  └─ DELETE /api/projects/{id}/files/{path} │
                                                  
                                                  Disk: ~/.tinyvm-projects/
                                                          <uuid>/
                                                            meta.json
                                                            files/
                                                              **/*.cvm.c, *.vm, …
```

Key design notes:

- **Persistence is automatic.** VS Code Web stores the open workspace in
  origin-scoped IndexedDB. As long as the `tinyvm-cloud:` provider is
  registered before the workspace folder is resolved, reload restores
  state without any extra code on our side.
- **Path traversal protection at the server.** Every `{path}` parameter
  is normalized and rejected if it escapes the project root.
- **Anonymous user.** Server tracks no user identity in v1. When auth
  lands, it slots in as middleware that filters `projects/` by owner;
  no client-side URL changes.
- **CORS** unchanged — the existing reflect-localhost-Origin policy
  in `compile-server.mjs` covers the new endpoints.

## 4. Repository Layout

New code lives under `tools/dev_env_web/`:

```
tools/dev_env_web/
  host/
    compile-server.mjs            # extended; now exports getHandler() for routes
    projects-store.mjs            # new — FS-backed project store
    openapi.yaml                  # new — wire contract, used to generate
                                  # Spring stubs in the future
  extension/
    src/
      browser/
        filesystem/
          cloud.ts                # new — tinyvm-cloud: provider
        cloud-commands.ts         # new — tinyVm.cloud.newProject, openProject
        api-client.ts             # new — shared fetch() client
  e2e/
    cloud-persistence.spec.ts     # new — create, edit, close, reopen, verify
docs/
  cloud_storage_proposal.md       # this file
```

## 5. Component Specifications

### 5.1 On-disk storage layout

Root: **`~/.tinyvm-projects/`** (configurable via `TINYVM_PROJECTS_DIR`).

```
~/.tinyvm-projects/
  <uuid>/
    meta.json                     # { id, name, createdAt, modifiedAt }
    files/
      hello.cvm.c
      lib/util.cvm.c
      ...
```

`meta.json` is the source of truth for project metadata. The directory's
mtime is not relied on. `createdAt` and `modifiedAt` are ISO 8601 UTC.

Path normalization rules (server-side):

1. URL-decode the path.
2. Reject if any segment is `..` or empty after splitting on `/`.
3. Reject if normalized path contains backslashes (Windows reserved).
4. Reject if file path is empty (project-root reads are listings, not files).
5. Resolve relative to `projects/<id>/files/` and verify the absolute
   result is still under that root.

### 5.2 OpenAPI wire contract

Lives at `tools/dev_env_web/host/openapi.yaml`. The full spec is in the
sibling file; an abridged human-readable summary:

| Method | Path                                       | Body            | Response                                |
| ------ | ------------------------------------------ | --------------- | --------------------------------------- |
| GET    | `/api/projects`                            | —               | `{ projects: [Project, …] }`            |
| POST   | `/api/projects`                            | `{ name }`      | `Project` (201)                         |
| GET    | `/api/projects/{id}`                       | —               | `Project`                               |
| DELETE | `/api/projects/{id}`                       | —               | 204                                     |
| GET    | `/api/projects/{id}/files`                 | —               | `{ entries: [FileEntry, …] }`           |
| GET    | `/api/projects/{id}/files/{path}`          | —               | binary file bytes (Content-Type sniffed)|
| PUT    | `/api/projects/{id}/files/{path}`          | binary bytes    | `FileEntry`                             |
| DELETE | `/api/projects/{id}/files/{path}`          | —               | 204                                     |

```yaml
components:
  schemas:
    Project:
      type: object
      required: [id, name, createdAt, modifiedAt]
      properties:
        id:         { type: string, format: uuid }
        name:       { type: string, maxLength: 200 }
        createdAt:  { type: string, format: date-time }
        modifiedAt: { type: string, format: date-time }
    FileEntry:
      type: object
      required: [path, type, size, modifiedAt]
      properties:
        path:       { type: string }      # POSIX path inside files/
        type:       { type: string, enum: [file, directory] }
        size:       { type: integer }     # bytes; 0 for directories
        modifiedAt: { type: string, format: date-time }
    Error:
      type: object
      required: [error]
      properties:
        error:  { type: string }
        detail: { type: string }
```

Error envelope: every non-2xx response is `Error`. Status codes follow
standard REST conventions: 400 (bad input), 404 (no such project/file),
409 (name collision — only if we add unique-name validation; v1 does not),
500 (unexpected).

### 5.3 IDE side

#### FileSystemProvider (`extension/src/browser/filesystem/cloud.ts`)

Mirrors `OpfsFileSystemProvider`'s interface. URI shape:
`tinyvm-cloud:/projects/<id>/<path>`.

Implementation: every method makes a single REST call. No client-side
caching in v1 — modern HTTP/2 keeps the connection hot and the latency
on loopback is sub-ms.

- `stat(uri)` → `GET /api/projects/<id>/files/<path>` (HEAD-style; the
  server returns the FileEntry as a JSON header `X-FileEntry` so we
  don't pay for full body downloads on stat)
  
  Actually simpler approach: for stat, fetch the directory listing of
  the parent and find the entry. For v1 the file trees are small. We
  can optimize later.

- `readDirectory(uri)` → `GET /api/projects/<id>/files` returns the
  full tree; filter to entries directly under the requested URI's path.

- `readFile(uri)` → `GET /api/projects/<id>/files/<path>` returns bytes.
- `writeFile(uri, content)` → `PUT /api/projects/<id>/files/<path>` body=bytes.
- `delete(uri)` → `DELETE /api/projects/<id>/files/<path>`.
- `rename(old, new)` → copy + delete (no native rename endpoint v1).
- `createDirectory(uri)` → no-op; directories are implicit (writeFile
  creates parents).
- `watch()` → no-op.

#### Commands (`extension/src/browser/cloud-commands.ts`)

- `tinyVm.cloud.newProject`
  1. Prompt for name (`vscode.window.showInputBox`).
  2. `POST /api/projects` with that name.
  3. Add `tinyvm-cloud:/projects/<id>/` to workspace folders as
     "<name> (cloud)".
  4. Open a starter file (e.g. `hello.cvm.c` with a minimal
     led_write/delay loop) so the user lands somewhere productive.

- `tinyVm.cloud.openProject`
  1. `GET /api/projects` to list.
  2. `vscode.window.showQuickPick` with project names.
  3. Add `tinyvm-cloud:/projects/<id>/` to workspace folders.

- `tinyVm.cloud.deleteProject`
  1. Confirm dialog.
  2. `DELETE /api/projects/<id>`.
  3. Remove workspace folder if present.

#### Persistence semantics

VS Code Web saves the list of workspace folders in origin-scoped
IndexedDB automatically. On reload, it calls our `FileSystemProvider`
to resolve the saved `tinyvm-cloud:` URIs. The provider is registered
at extension activation (`onFileSystem:tinyvm-cloud` activation
event), so the timing is fine.

Caveat: VS Code Web prompts "validate workspace folder" early in
startup. We need the provider registered synchronously in `activate()`,
not behind any async work. The existing OPFS provider already follows
this pattern.

### 5.4 Server side (`compile-server.mjs` + `projects-store.mjs`)

`projects-store.mjs` exports:

```js
class ProjectsStore {
  constructor(root)             // root = ~/.tinyvm-projects (configurable)
  async listProjects()          // → Project[]
  async createProject(name)     // → Project
  async getProject(id)          // → Project | throws
  async deleteProject(id)       // → void
  async listFiles(id)           // → FileEntry[]   (recursive tree)
  async readFile(id, path)      // → Uint8Array | throws
  async writeFile(id, path, body) // → FileEntry
  async deleteFile(id, path)    // → void
}
```

Concurrency: every write goes through `fs.writeFile` with atomic
rename (write to `.tmp`, fsync, rename). Last-write-wins. No locking
across requests in v1.

`compile-server.mjs` adds routing for the new endpoints alongside
`/api/compile`. The handler dispatches to `ProjectsStore` methods.

## 6. Milestones

### CS1 — Backend (4-6 turns)

Scope:
- `projects-store.mjs` with the methods in 5.4.
- `compile-server.mjs` extended with the routes.
- `openapi.yaml`.
- Unit tests for path-traversal rejection (this is the security-critical
  surface).

Acceptance:
- `curl` round-trips: create project, write file, read file back, list,
  delete. Plus rejected `../` traversal attempts.

### CS2 — IDE Integration (4-6 turns)

Scope:
- `filesystem/cloud.ts` (FileSystemProvider).
- `api-client.ts` (shared fetch wrapper with auth-ready interface).
- `cloud-commands.ts` (new/open/delete project).
- Wire activation events and contributions in `package.json`.

Acceptance:
- Manual: F1 → new project → starter file opens → edit + save → reload
  page → file still there.
- Compile + debug continues to work on a cloud-backed file.

### CS3 — E2E + Docs (3-4 turns)

Scope:
- `e2e/cloud-persistence.spec.ts`: new-project / write-file /
  close-context / new-context-same-origin / verify-file-content.
- Update `tools/dev_env_web/README.md` with a "Cloud projects" section.
- Update `docs/vscode_proposal.md` status table — D2 "cloud project
  files" partially shipped (no auth yet).

Acceptance:
- `smoke.sh` includes the new e2e and passes.

## 7. Spring Boot Migration Plan

When we move the server to Spring Boot:

1. **Generate controller stubs**: `openapi-generator-cli generate -i
   openapi.yaml -g spring -o spring-server/`.
2. **Implement handler methods** to delegate to a `ProjectsStore` Spring
   bean. The store reads/writes the same `~/.tinyvm-projects/` directory
   structure — Java's `java.nio.file.Path` covers it.
3. **Reimplement the `/api/compile` endpoint** in Java using
   `ProcessBuilder` to invoke `python3 tools/vm_cc.py`. The Python
   compiler itself does not move.
4. **Flip `tinyVm.apiUrl`** in the IDE settings to point at the Spring
   service. No frontend code changes; the wire contract is identical.
5. **Decommission the Node sidecar.** `compile-server.mjs` is retained
   in the repo for local-only dev (no Java toolchain required) until
   we're confident the Spring service is the canonical path.

Migration order matters: keep both running in parallel for a window so
e2e can flip-flop via `IDE_URL` / `tinyVm.apiUrl` overrides.

## 8. Risks

- **Path-traversal regression.** Mitigation: explicit test suite in CS1.
- **Anonymous-user assumption baking in.** Mitigation: API design treats
  anonymous-user as a special owner ID, so the upgrade is a server-side
  filter, not a URL change.
- **VS Code Web workspace-restoration race.** If our extension activates
  after VS Code Web has already failed to validate the cloud workspace
  folder, the user sees an error toast. Mitigation: workspace folders
  using `tinyvm-cloud:` schemes trigger activation via
  `onFileSystem:tinyvm-cloud`.
- **Last-write-wins data loss in concurrent editing.** Mitigation:
  out of scope for v1; ETag/If-Match is planned for a later iteration.

## 9. Open Questions

1. **Default starter content.** `hello.cvm.c` with a minimal led-blink
   loop is the natural choice. Confirm before CS2.
2. **Project listing pagination.** Probably unnecessary in v1 — a single
   user with hundreds of projects is unlikely. Defer.
3. **File-tree caching in the IDE.** v1 fetches per `readDirectory` call;
   if folder browsing feels sluggish, add a 5-second TTL cache. Defer.

## 10. Reference Files

- `docs/vscode_proposal.md` — the VS Code Web environment plan that this
  proposal extends.
- `tools/dev_env_web/host/compile-server.mjs` — existing sidecar that
  gains the new endpoints.
- `tools/dev_env_web/extension/src/browser/filesystem/opfs.ts` —
  reference FileSystemProvider whose shape we mirror.
