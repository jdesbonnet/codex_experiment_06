# tiny_vm Web IDE — architecture and roadmap

This is the visual companion to the textual proposals in this directory:

- `docs/vscode_proposal.md` — VS Code Web IDE plan + status (M1..M5).
- `docs/cloud_storage_proposal.md` — server-backed projects + Spring migration plan.
- `docs/theia_proposal.md` — the parallel Theia implementation (`tools/theia/`).

Diagrams below are Mermaid. They render natively in GitHub, in the VS
Code Markdown preview, and at <https://mermaid.live>. To export an SVG
from the command line:

```sh
npx -p @mermaid-js/mermaid-cli mmdc -i docs/architecture.md -o /tmp/architecture.svg
```

---

## System overview

Three layers — browser, backend, storage. **Solid green** means shipped
and exercised by the smoke gate; **solid blue** means shipped but not on
the critical path; **dashed grey** means planned or deferred.

```mermaid
flowchart TB
    classDef shipped fill:#d6f5d6,stroke:#2a8a2a,color:#0a3d0a
    classDef ancillary fill:#d6e7f5,stroke:#2a5a8a,color:#0a2a4d
    classDef planned fill:#f5f5f5,stroke:#888,color:#555,stroke-dasharray: 5 5

    subgraph Browser ["🌐 Browser (sandbox)"]
        direction LR
        Mon["Monaco editor<br/>+ tiny_vm syntax"]:::shipped
        Ext["VS Code Web extension<br/>(Web Worker host)"]:::shipped
        Wasm["wasm tiny_vm sim<br/>22 KB · Rust → wasm-pack"]:::shipped
        DAP["In-process DebugAdapter<br/>source-line + opcode step"]:::shipped
        OPFS["OPFS provider<br/>tinyvm-opfs:"]:::ancillary
        Cloud["Cloud provider<br/>tinyvm-cloud:"]:::shipped
        UX["Commands:<br/>newProject · openProject ·<br/>debugBytecode · runBytecode ·<br/>openOpcodeTable"]:::shipped
    end

    subgraph Server ["☁️ Backend (dev: Node :3001 → prod: Spring Boot planned)"]
        direction LR
        Compile["POST /api/compile<br/>(spawns python3 vm_cc.py)"]:::shipped
        Projects["GET / POST /api/projects<br/>GET / PUT / DELETE files"]:::shipped
        Spring["Spring Boot impl<br/>generated from openapi.yaml"]:::planned
        Auth["Auth (OIDC / reverse proxy)<br/>filters projects by owner"]:::planned
    end

    subgraph Storage ["💾 Storage"]
        direction LR
        OPFSstore[("Browser OPFS<br/>per-origin sandbox")]:::ancillary
        FS[("~/.tinyvm-projects/<br/>UUID/files/…")]:::shipped
        S3[("Object storage<br/>(prod)")]:::planned
    end

    subgraph Hardware ["⚡ Hardware (today: host-side; planned: in-browser)"]
        direction LR
        WCH["WCH-LinkE + CH32V003<br/>via tools/flash.sh"]:::ancillary
        WebUSB["WebSerial / WebUSB<br/>flash + UART from browser"]:::planned
    end

    Mon --> Ext
    Ext -- runs --> Wasm
    Ext -- drives --> DAP
    DAP -- steps --> Wasm
    Ext --> OPFS
    Ext --> Cloud
    OPFS --> OPFSstore
    Cloud -- "fetch()" --> Projects
    Ext -- "fetch()" --> Compile
    Projects --> FS
    Spring -.-> FS
    Spring -.-> S3
    Auth -.-> Projects
    Auth -.-> Spring
    Ext -.-> WebUSB
    WebUSB -.-> WCH
```

---

## Milestone status (vscode_proposal.md)

```mermaid
flowchart LR
    classDef shipped fill:#d6f5d6,stroke:#2a8a2a,color:#0a3d0a
    classDef planned fill:#f5f5f5,stroke:#888,color:#555,stroke-dasharray: 5 5

    M1["M1<br/>wasm sim<br/>11+8 tests"]:::shipped
    M2["M2<br/>extension scaffold<br/>+ OPFS"]:::shipped
    M3["M3<br/>in-browser DAP<br/>+ backend compile"]:::shipped
    M4["M4<br/>Playwright e2e<br/>blink-debug"]:::shipped
    M5["M5<br/>smoke + docs"]:::shipped

    CS["Cloud projects<br/>(D2 subset)<br/>+ persistence e2e"]:::shipped

    D1["D1: WebSerial / WebUSB<br/>hardware from browser"]:::planned
    D2auth["D2: Auth (OIDC)<br/>multi-user SaaS"]:::planned
    D4a["D4 stage 1<br/>compile-on-save diagnostics"]:::shipped
    D4["D4 stage 2+<br/>live diagnostics · hover · goto-def"]:::planned
    D5["D5: native MCU debug<br/>via WebUSB"]:::planned
    SB["Spring Boot rewrite<br/>(from openapi.yaml)"]:::planned

    M1 --> M2 --> M3 --> M4 --> M5 --> CS
    CS --> D2auth
    CS --> SB
    M5 --> D1
    M5 --> D4a --> D4
    M5 --> D5
```

---

## Request flow: New Cloud Project → save → close → reopen

The "I should be able to close the browser and reopen and see my project"
loop, end-to-end:

```mermaid
sequenceDiagram
    actor User
    participant IDE as VS Code Web<br/>(extension)
    participant API as compile-server<br/>:3001
    participant Disk as ~/.tinyvm-projects/

    User->>IDE: F1 → tiny_vm: New Cloud Project
    IDE->>User: prompt name
    User->>IDE: "my-blink"
    IDE->>API: POST /api/projects {name}
    API->>Disk: mkdir <uuid>/files/
    API->>Disk: write meta.json
    API-->>IDE: 201 {id, name, …}
    IDE->>API: PUT /api/projects/<id>/files/hello.cvm.c<br/>(starter content)
    API->>Disk: write files/hello.cvm.c (atomic)
    API-->>IDE: 200 FileEntry
    IDE->>IDE: showTextDocument(tinyvm-cloud:/projects/<id>/hello.cvm.c)
    User->>IDE: edit + Ctrl+S
    IDE->>API: PUT /api/projects/<id>/files/hello.cvm.c
    API->>Disk: atomic write
    API-->>IDE: 200

    User-->>IDE: close browser
    Note over IDE,API: server keeps file at<br/>~/.tinyvm-projects/<id>/files/hello.cvm.c

    User->>IDE: reopen, F1 → Open Cloud Project
    IDE->>API: GET /api/projects
    API->>Disk: scan UUIDs + read meta.json
    API-->>IDE: {projects: [...]}
    User->>IDE: pick "my-blink"
    IDE->>API: GET /api/projects/<id>/files
    API-->>IDE: {entries: [hello.cvm.c, …]}
    IDE->>API: GET /api/projects/<id>/files/hello.cvm.c
    API->>Disk: read
    API-->>IDE: file bytes (edited content)
    IDE->>User: editor opens with the saved edit
```

---

## Compile + debug, end-to-end

```mermaid
sequenceDiagram
    actor User
    participant IDE as VS Code Web
    participant API as /api/compile
    participant Py as python3 vm_cc.py
    participant Wasm as wasm sim
    participant DAP as in-process<br/>DebugAdapter

    User->>IDE: F1 → tiny_vm: Debug Bytecode in Simulator
    IDE->>API: POST /api/compile {source, name}
    API->>Py: spawn (cwd = repo root)
    Py-->>API: stdout / writes /tmp/out.bin + .bin.map
    API-->>IDE: {bytecodeBase64, sourceMap}
    IDE->>IDE: write tinyvm-opfs:/.cache/<base>.bin{,.map}
    IDE->>DAP: vscode.debug.startDebugging({program: opfs URI, stopOnEntry: true})
    DAP->>Wasm: new WasmTinyVm(bytes)
    DAP->>IDE: stopped event (reason: entry)
    User->>IDE: F10 step over
    DAP->>Wasm: step()
    Wasm-->>DAP: HOST_PENDING (op=0x09, id=2)
    DAP->>Wasm: complete_host_call(0)
    DAP->>IDE: stopped (reason: step)
    Note over DAP,IDE: source-map maps PC → file:line<br/>editor highlights matching line
```

---

## What's in the repo today

```mermaid
flowchart TB
    classDef shipped fill:#d6f5d6,stroke:#2a8a2a,color:#0a3d0a
    classDef ancillary fill:#d6e7f5,stroke:#2a5a8a,color:#0a2a4d

    subgraph Web ["tools/vscode/ (this work)"]
        direction TB
        Sim["sim/ → Rust + wasm-pack<br/>committed pkg/ for static deploys"]:::shipped
        ExtDir["extension/ → web extension<br/>languages · commands · DAP · FS providers"]:::shipped
        HostDir["host/ → Node sidecar<br/>compile-server + projects-store + openapi.yaml"]:::shipped
        E2E["e2e/ → Playwright<br/>blink-debug.spec.ts · cloud-persistence.spec.ts"]:::shipped
        Scripts["scripts/ → install · serve · smoke · console-capture"]:::shipped
    end

    subgraph Theia ["tools/theia/ (parallel Theia version)"]
        direction TB
        ThSim["sim/ → Python sim (reference)"]:::ancillary
        ThDap["dap/ → Python DAP server"]:::ancillary
        ThIDE["theia/ → Theia browser app"]:::ancillary
    end

    subgraph Common ["common to both"]
        direction TB
        Vmcc["tools/vm_cc.py · vm_asm.py<br/>(authoritative compiler)"]:::shipped
        Runtime["common/src/tiny_vm.c · include/tiny_vm.h<br/>(authoritative VM semantics)"]:::shipped
        Tests["projects/tiny_vm/tests/<br/>(authoritative test cases)"]:::shipped
    end

    Sim -.parity oracle.-> Tests
    ExtDir -.depends on.-> Sim
    ExtDir -.calls.-> HostDir
    HostDir -.spawns.-> Vmcc
    ThSim -.also parity.-> Tests
```

---

## Open decisions

| ID | Question | Current state | Where decided |
|----|----------|---------------|---------------|
| Q1 | Sim language | Rust → wasm-pack | `vscode_proposal.md §8` |
| Q2 | Compile path | Backend API | `vscode_proposal.md §8` + `cloud_storage_proposal.md` |
| – | Storage backend | Filesystem | `cloud_storage_proposal.md §1` |
| – | Project IDs | Server UUIDs | `cloud_storage_proposal.md §1` |
| – | API contract | OpenAPI 3.0 | `tools/vscode/host/openapi.yaml` |
| ❓ | Auth provider | OIDC vs Cloudflare Access vs Tailscale | open |
| ❓ | When to do Spring rewrite | After feature set stabilises | open |
| ❓ | Cloud object storage vs FS in prod | Likely object storage for multi-instance | open |
