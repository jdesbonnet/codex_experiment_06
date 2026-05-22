"""
Loader and lookup helpers for the source-map JSON files emitted by
tools/vm_cc.py --map and tools/vm_asm.py --map.

Map schema (see docs/dev_env_proposal.md section 5.2):

    {
      "version": 1,
      "source": "path/to/input.cvm.c",
      "bytecode_size": int,
      "entries": [ { "pc": int, "line": int, "col"?: int, "kind"?: str } ],
      "locals":  [ { "slot": int, "name": str, "line": int } ]   # vm_cc only
    }
"""

from __future__ import annotations

import bisect
import json
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    pc: int
    line: int
    col: int | None = None
    kind: str = "stmt"


@dataclass(frozen=True)
class LocalVar:
    slot: int
    name: str
    line: int | None


@dataclass
class SourceMap:
    version: int
    source: str
    bytecode_size: int
    entries: list[Entry]
    locals: list[LocalVar]
    _pcs: list[int]

    def entry_for_pc(self, pc: int) -> Entry | None:
        """Return the most recent entry whose pc <= given pc.

        Used to map a running PC back to a source line."""
        if not self._pcs:
            return None
        idx = bisect.bisect_right(self._pcs, pc) - 1
        if idx < 0:
            return None
        return self.entries[idx]

    def pc_for_line(self, line: int) -> int | None:
        """Return the lowest pc associated with the given source line."""
        for e in self.entries:
            if e.line == line:
                return e.pc
        return None

    def pc_for_line_at_or_after(self, line: int) -> int | None:
        """Return the smallest pc whose source line is >= the given line.

        Useful when the user sets a breakpoint on a blank or comment line: we
        resolve it to the next executable statement."""
        best: tuple[int, int] | None = None
        for e in self.entries:
            if e.line >= line:
                if best is None or e.line < best[0] or (e.line == best[0] and e.pc < best[1]):
                    best = (e.line, e.pc)
        return None if best is None else best[1]

    def name_for_local(self, slot: int) -> str | None:
        for loc in self.locals:
            if loc.slot == slot:
                return loc.name
        return None


def load(path: str | pathlib.Path) -> SourceMap:
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return parse(raw)


def parse(raw: dict) -> SourceMap:
    if raw.get("version") != 1:
        raise ValueError(f"unsupported source-map version {raw.get('version')}")
    entries_raw = raw.get("entries") or []
    entries = [
        Entry(
            pc=int(e["pc"]),
            line=int(e["line"]),
            col=int(e["col"]) if "col" in e and e["col"] is not None else None,
            kind=str(e.get("kind", "stmt")),
        )
        for e in entries_raw
    ]
    locals_raw = raw.get("locals") or []
    locals_ = [
        LocalVar(
            slot=int(loc["slot"]),
            name=str(loc["name"]),
            line=int(loc["line"]) if loc.get("line") is not None else None,
        )
        for loc in locals_raw
    ]
    pcs = [e.pc for e in entries]
    return SourceMap(
        version=int(raw["version"]),
        source=str(raw.get("source", "")),
        bytecode_size=int(raw.get("bytecode_size", 0)),
        entries=entries,
        locals=locals_,
        _pcs=pcs,
    )
