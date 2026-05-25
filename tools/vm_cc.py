#!/usr/bin/env python3
"""
tiny_vm minimal C-like compiler (v2).

Supported subset:
  - const int NAME = <number>;
  - int var;
  - int var = <expr>;
  - var = <expr>;
  - while (<expr>) { ... }
  - if (<expr>) { ... } [else { ... }]
  - calls:
      led_write(expr);
      delay_ms(expr);
      print_u32(expr);
      print_hex32(expr);
      host(const_expr, expr);
      store8(index_expr, value_expr);
      store32le(index_expr, value_expr);
  - expressions over int literals/vars/constants:
      +, -, *, /, %, <, >, ==
      load8(index_expr)
      load32le(index_expr)
      and32(a,b), or32(a,b), xor32(a,b), not32(a)
      shl32(a,b), shr32(a,b)
      rol32(a,b), ror32(a,b)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass


# Instruction byte sizes (must match tools/vm_asm.py first_pass).
INSTR_SIZE = {
    "NOP": 1, "ADD": 1, "SUB": 1, "DUP": 1, "DROP": 1, "SWAP": 1, "HALT": 1,
    "EQ": 1, "LT": 1, "MOD": 1, "MUL": 1, "DIV": 1,
    "MGET": 1, "MSET": 1, "MGET32": 1, "MSET32": 1,
    "AND": 1, "OR": 1, "XOR": 1, "NOT": 1, "SHL": 1, "SHR": 1, "ROL": 1, "ROR": 1,
    "PUSH8": 2, "HOST": 2, "LGET": 2, "LSET": 2,
    "PUSH16": 3, "JMP": 3, "JZ": 3,
    "PUSH32": 5,
}


@dataclass
class Token:
    kind: str
    text: str
    line: int = 1
    col: int = 1


class CompileError(Exception):
    """A user-facing compile error carrying source position info.

    Distinct from generic exceptions: only CompileError gets formatted as
    a structured diagnostic (file:line:col: error: msg). Other exceptions
    are treated as internal bugs.
    """

    def __init__(self, line: int, col: int, msg: str) -> None:
        super().__init__(msg)
        self.line = line
        self.col = col
        self.msg = msg


def strip_comments(src: str) -> str:
    # Preserve newlines so lex() line counting stays accurate.
    def _block(m: re.Match[str]) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    src = re.sub(r"/\*.*?\*/", _block, src, flags=re.S)
    src = re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), src)
    return src


def lex(src: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    line = 1
    col = 1
    while i < len(src):
        ch = src[i]
        if ch == "\n":
            line += 1
            col = 1
            i += 1
            continue
        if ch.isspace():
            col += 1
            i += 1
            continue
        if src.startswith("==", i):
            tokens.append(Token("SYM", "==", line, col))
            i += 2
            col += 2
            continue
        if ch in "{}();,=+-*/<>%":
            tokens.append(Token("SYM", ch, line, col))
            i += 1
            col += 1
            continue
        m = re.match(r"[A-Za-z_]\w*", src[i:])
        if m:
            text = m.group(0)
            kind = "KW" if text in {"const", "int", "while", "if", "else"} else "ID"
            tokens.append(Token(kind, text, line, col))
            i += len(text)
            col += len(text)
            continue
        m = re.match(r"[+-]?(?:0x[0-9A-Fa-f]+|\d+)", src[i:])
        if m:
            tokens.append(Token("NUM", m.group(0), line, col))
            i += len(m.group(0))
            col += len(m.group(0))
            continue
        raise CompileError(line, col, f"lex error near: {src[i:i+20]!r}")
    tokens.append(Token("EOF", "", line, col))
    return tokens


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.toks = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.toks[self.pos]

    def take(self) -> Token:
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def expect(self, kind: str, text: str | None = None) -> Token:
        t = self.peek()
        if t.kind != kind or (text is not None and t.text != text):
            raise CompileError(
                t.line,
                t.col,
                f"expected {kind} {text or ''}, got {t.kind} {t.text!r}",
            )
        return self.take()

    def _err(self, msg: str, tok: Token | None = None) -> CompileError:
        t = tok or self.peek()
        return CompileError(t.line, t.col, msg)

    def parse_program(self) -> list[dict]:
        out: list[dict] = []
        while self.peek().kind != "EOF":
            out.append(self.parse_stmt())
        return out

    def parse_block(self) -> list[dict]:
        self.expect("SYM", "{")
        stmts: list[dict] = []
        while not (self.peek().kind == "SYM" and self.peek().text == "}"):
            stmts.append(self.parse_stmt())
        self.expect("SYM", "}")
        return stmts

    def parse_stmt(self) -> dict:
        t = self.peek()
        line = t.line
        col = t.col
        node = self._parse_stmt_inner()
        node["line"] = line
        node["col"] = col
        return node

    def _parse_stmt_inner(self) -> dict:
        t = self.peek()
        if t.kind == "KW" and t.text == "const":
            self.take()
            self.expect("KW", "int")
            name = self.expect("ID").text
            self.expect("SYM", "=")
            expr = self.parse_expr()
            self.expect("SYM", ";")
            return {"kind": "const_decl", "name": name, "expr": expr}
        if t.kind == "KW" and t.text == "int":
            self.take()
            name = self.expect("ID").text
            init = None
            if self.peek().kind == "SYM" and self.peek().text == "=":
                self.take()
                init = self.parse_expr()
            self.expect("SYM", ";")
            return {"kind": "var_decl", "name": name, "init": init}
        if t.kind == "KW" and t.text == "while":
            self.take()
            self.expect("SYM", "(")
            cond = self.parse_expr()
            self.expect("SYM", ")")
            body = self.parse_block()
            return {"kind": "while", "cond": cond, "body": body}
        if t.kind == "KW" and t.text == "if":
            self.take()
            self.expect("SYM", "(")
            cond = self.parse_expr()
            self.expect("SYM", ")")
            then_body = self.parse_block()
            else_body = None
            if self.peek().kind == "KW" and self.peek().text == "else":
                self.take()
                else_body = self.parse_block()
            return {"kind": "if", "cond": cond, "then": then_body, "else": else_body}
        if t.kind == "SYM" and t.text == "{":
            return {"kind": "block", "body": self.parse_block()}
        if t.kind == "ID":
            name = self.take().text
            if self.peek().kind == "SYM" and self.peek().text == "=":
                self.take()
                expr = self.parse_expr()
                self.expect("SYM", ";")
                return {"kind": "assign", "name": name, "expr": expr}
            if self.peek().kind == "SYM" and self.peek().text == "(":
                args = self.parse_call_args()
                self.expect("SYM", ";")
                return {"kind": "call", "name": name, "args": args}
            raise self._err(f"invalid statement starting with identifier {name}", t)
        raise self._err(f"unexpected token {t.kind} {t.text!r}", t)

    def parse_call_args(self) -> list[dict]:
        out: list[dict] = []
        self.expect("SYM", "(")
        if not (self.peek().kind == "SYM" and self.peek().text == ")"):
            out.append(self.parse_expr())
            while self.peek().kind == "SYM" and self.peek().text == ",":
                self.take()
                out.append(self.parse_expr())
        self.expect("SYM", ")")
        return out

    def parse_expr(self) -> dict:
        return self.parse_eq()

    def parse_eq(self) -> dict:
        node = self.parse_rel()
        while self.peek().kind == "SYM" and self.peek().text == "==":
            tok = self.take()
            rhs = self.parse_rel()
            node = {"kind": "bin", "op": tok.text, "l": node, "r": rhs, "line": tok.line, "col": tok.col}
        return node

    def parse_rel(self) -> dict:
        node = self.parse_add()
        while self.peek().kind == "SYM" and self.peek().text in {"<", ">"}:
            tok = self.take()
            rhs = self.parse_add()
            node = {"kind": "bin", "op": tok.text, "l": node, "r": rhs, "line": tok.line, "col": tok.col}
        return node

    def parse_add(self) -> dict:
        node = self.parse_mul()
        while self.peek().kind == "SYM" and self.peek().text in {"+", "-"}:
            tok = self.take()
            rhs = self.parse_mul()
            node = {"kind": "bin", "op": tok.text, "l": node, "r": rhs, "line": tok.line, "col": tok.col}
        return node

    def parse_mul(self) -> dict:
        node = self.parse_term()
        while self.peek().kind == "SYM" and self.peek().text in {"*", "/", "%"}:
            tok = self.take()
            rhs = self.parse_term()
            node = {"kind": "bin", "op": tok.text, "l": node, "r": rhs, "line": tok.line, "col": tok.col}
        return node

    def parse_term(self) -> dict:
        t = self.peek()
        if t.kind == "NUM":
            self.take()
            return {"kind": "num", "value": int(t.text, 0), "line": t.line, "col": t.col}
        if t.kind == "ID":
            name = self.take().text
            if self.peek().kind == "SYM" and self.peek().text == "(":
                args = self.parse_call_args()
                return {"kind": "call_expr", "name": name, "args": args, "line": t.line, "col": t.col}
            return {"kind": "name", "value": name, "line": t.line, "col": t.col}
        if t.kind == "SYM" and t.text == "(":
            self.take()
            node = self.parse_expr()
            self.expect("SYM", ")")
            return node
        raise self._err(f"unexpected token in expr: {t.kind} {t.text!r}", t)


class Compiler:
    def __init__(self) -> None:
        self.consts: dict[str, int] = {}
        self.vars: dict[str, int] = {}
        self.lines: list[str] = []
        self.label_id = 0
        self.pc = 0
        self.entries: list[dict] = []
        self.local_decls: list[dict] = []
        # Tracks the AST node currently being lowered so semantic errors
        # (e.g. unknown identifier) can carry source position even when
        # raised from deep helpers like eval_const_expr or emit_call.
        self.cur_line: int = 1
        self.cur_col: int = 1

    def _track(self, node: dict) -> None:
        if "line" in node and node["line"] is not None:
            self.cur_line = node["line"]
            self.cur_col = node.get("col") or 1

    def _err(self, msg: str) -> CompileError:
        return CompileError(self.cur_line, self.cur_col, msg)

    def new_label(self, prefix: str) -> str:
        name = f"{prefix}_{self.label_id}"
        self.label_id += 1
        return name

    def emit(self, line: str) -> None:
        self.lines.append(line)
        stripped = line.strip()
        if not stripped or stripped.endswith(":"):
            return
        op = stripped.split()[0].upper()
        size = INSTR_SIZE.get(op)
        if size is None:
            raise ValueError(f"internal: unknown opcode '{op}' in emit()")
        self.pc += size

    def record_entry(self, line: int | None, col: int | None, kind: str) -> None:
        if line is None:
            return
        if self.entries and self.entries[-1]["pc"] == self.pc:
            # Replace earlier zero-width record with the inner kind so source
            # line stays attached to the actual emitted instruction.
            self.entries[-1]["line"] = line
            self.entries[-1]["col"] = col
            self.entries[-1]["kind"] = kind
            return
        self.entries.append(
            {"pc": self.pc, "line": line, "col": col, "kind": kind}
        )

    def alloc_var(self, name: str) -> int:
        if name in self.vars:
            raise self._err(f"duplicate variable {name}")
        if len(self.vars) >= 16:
            raise self._err("too many variables (max 16)")
        idx = len(self.vars)
        self.vars[name] = idx
        return idx

    def eval_const_expr(self, node: dict) -> int:
        self._track(node)
        kind = node["kind"]
        if kind == "num":
            return int(node["value"])
        if kind == "name":
            name = node["value"]
            if name not in self.consts:
                raise self._err(f"'{name}' is not a compile-time const")
            return self.consts[name]
        if kind == "bin":
            l = self.eval_const_expr(node["l"])
            r = self.eval_const_expr(node["r"])
            op = node["op"]
            if op == "+":
                return l + r
            if op == "-":
                return l - r
            if op == "%":
                if r == 0:
                    raise self._err("mod by zero in const expression")
                return l % r
            if op == "*":
                return l * r
            if op == "/":
                if r == 0:
                    raise self._err("div by zero in const expression")
                return int(l / r)
            if op == "==":
                return 1 if l == r else 0
            if op == "<":
                return 1 if l < r else 0
            if op == ">":
                return 1 if l > r else 0
        raise self._err("unsupported const expression")

    def emit_push_imm(self, value: int) -> None:
        if -128 <= value <= 127:
            self.emit(f"PUSH8 {value}")
        elif -32768 <= value <= 32767:
            self.emit(f"PUSH16 {value}")
        elif -2147483648 <= value <= 2147483647:
            self.emit(f"PUSH32 {value}")
        elif 0 <= value <= 0xFFFFFFFF:
            self.emit(f"PUSH32 {value - 0x100000000}")
        else:
            raise self._err(f"literal out of PUSH32 range: {value}")

    def emit_expr(self, node: dict) -> None:
        self._track(node)
        kind = node["kind"]
        if kind == "num":
            self.emit_push_imm(int(node["value"]))
            return
        if kind == "name":
            name = node["value"]
            if name in self.vars:
                self.emit(f"LGET {self.vars[name]}")
                return
            if name in self.consts:
                self.emit_push_imm(self.consts[name])
                return
            raise self._err(f"unknown symbol '{name}'")
        if kind == "call_expr":
            name = node["name"]
            args = node["args"]
            if name == "load8":
                if len(args) != 1:
                    raise self._err("load8 expects 1 arg")
                self.emit_expr(args[0])
                self.emit("MGET")
                return
            if name == "load32le":
                if len(args) != 1:
                    raise self._err("load32le expects 1 arg")
                self.emit_expr(args[0])
                self.emit("MGET32")
                return
            if name == "and32":
                if len(args) != 2:
                    raise self._err("and32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("AND")
                return
            if name == "or32":
                if len(args) != 2:
                    raise self._err("or32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("OR")
                return
            if name == "xor32":
                if len(args) != 2:
                    raise self._err("xor32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("XOR")
                return
            if name == "not32":
                if len(args) != 1:
                    raise self._err("not32 expects 1 arg")
                self.emit_expr(args[0])
                self.emit("NOT")
                return
            if name == "shl32":
                if len(args) != 2:
                    raise self._err("shl32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("SHL")
                return
            if name == "shr32":
                if len(args) != 2:
                    raise self._err("shr32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("SHR")
                return
            if name == "rol32":
                if len(args) != 2:
                    raise self._err("rol32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("ROL")
                return
            if name == "ror32":
                if len(args) != 2:
                    raise self._err("ror32 expects 2 args")
                self.emit_expr(args[0])
                self.emit_expr(args[1])
                self.emit("ROR")
                return
            raise self._err(f"unsupported expression function '{name}'")
        if kind == "bin":
            op = node["op"]
            if op == ">":
                self.emit_expr(node["r"])
                self.emit_expr(node["l"])
                self.emit("LT")
                return
            self.emit_expr(node["l"])
            self.emit_expr(node["r"])
            if op == "+":
                self.emit("ADD")
            elif op == "-":
                self.emit("SUB")
            elif op == "*":
                self.emit("MUL")
            elif op == "/":
                self.emit("DIV")
            elif op == "%":
                self.emit("MOD")
            elif op == "==":
                self.emit("EQ")
            elif op == "<":
                self.emit("LT")
            else:
                raise self._err(f"unsupported operator {op}")
            return
        raise self._err(f"unsupported expression node {kind}")

    def emit_stmt(self, stmt: dict) -> None:
        self._track(stmt)
        kind = stmt["kind"]
        entry_kind = {
            "while": "loop_head",
            "if": "if_head",
        }.get(kind, "stmt")
        self.record_entry(stmt.get("line"), stmt.get("col"), entry_kind)
        if kind == "const_decl":
            self.consts[stmt["name"]] = self.eval_const_expr(stmt["expr"])
            return
        if kind == "var_decl":
            idx = self.alloc_var(stmt["name"])
            self.local_decls.append(
                {"slot": idx, "name": stmt["name"], "line": stmt.get("line")}
            )
            if stmt["init"] is not None:
                self.emit_expr(stmt["init"])
                self.emit(f"LSET {idx}")
            return
        if kind == "assign":
            if stmt["name"] not in self.vars:
                raise self._err(f"assignment to undeclared variable '{stmt['name']}'")
            self.emit_expr(stmt["expr"])
            self.emit(f"LSET {self.vars[stmt['name']]}")
            return
        if kind == "call":
            self.emit_call(stmt["name"], stmt["args"])
            return
        if kind == "block":
            for s in stmt["body"]:
                self.emit_stmt(s)
            return
        if kind == "while":
            l_start = self.new_label("while")
            l_end = self.new_label("wend")
            self.emit(f"{l_start}:")
            self.emit_expr(stmt["cond"])
            self.emit(f"JZ {l_end}")
            for s in stmt["body"]:
                self.emit_stmt(s)
            self.emit(f"JMP {l_start}")
            self.emit(f"{l_end}:")
            return
        if kind == "if":
            l_else = self.new_label("else")
            l_end = self.new_label("ifend")
            self.emit_expr(stmt["cond"])
            self.emit(f"JZ {l_else}")
            for s in stmt["then"]:
                self.emit_stmt(s)
            self.emit(f"JMP {l_end}")
            self.emit(f"{l_else}:")
            if stmt["else"] is not None:
                for s in stmt["else"]:
                    self.emit_stmt(s)
            self.emit(f"{l_end}:")
            return
        raise self._err(f"unsupported statement kind {kind}")

    def emit_call(self, name: str, args: list[dict]) -> None:
        if name == "led_write":
            if len(args) != 1:
                raise self._err("led_write expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 0")
            return
        if name == "delay_ms":
            if len(args) != 1:
                raise self._err("delay_ms expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 1")
            return
        if name == "print_u32":
            if len(args) != 1:
                raise self._err("print_u32 expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 2")
            return
        if name == "print_hex32":
            if len(args) != 1:
                raise self._err("print_hex32 expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 3")
            return
        if name == "host":
            if len(args) != 2:
                raise self._err("host expects 2 args")
            host_id = self.eval_const_expr(args[0])
            if host_id < 0 or host_id > 255:
                raise self._err("host id out of range 0..255")
            self.emit_expr(args[1])
            self.emit(f"HOST {host_id}")
            return
        if name == "store8":
            if len(args) != 2:
                raise self._err("store8 expects 2 args")
            self.emit_expr(args[0])
            self.emit_expr(args[1])
            self.emit("MSET")
            return
        if name == "store32le":
            if len(args) != 2:
                raise self._err("store32le expects 2 args")
            self.emit_expr(args[0])
            self.emit_expr(args[1])
            self.emit("MSET32")
            return
        raise self._err(f"unsupported function '{name}'")

    def compile(self, stmts: list[dict]) -> str:
        for s in stmts:
            self.emit_stmt(s)
        self.emit("HALT")
        return "\n".join(self.lines) + "\n"

    def build_source_map(self, source: str, bytecode_size: int) -> dict:
        return {
            "version": 1,
            "source": source,
            "bytecode_size": bytecode_size,
            "entries": list(self.entries),
            "locals": list(self.local_decls),
        }


def compile_to_asm(src: str) -> str:
    src = strip_comments(src)
    tokens = lex(src)
    parser = Parser(tokens)
    prog = parser.parse_program()
    return Compiler().compile(prog)


def compile_with_map(src: str, source_path: str) -> tuple[str, Compiler]:
    """Compile to assembly and also return the Compiler (carrying map state)."""
    src = strip_comments(src)
    tokens = lex(src)
    parser = Parser(tokens)
    prog = parser.parse_program()
    comp = Compiler()
    asm = comp.compile(prog)
    return asm, comp


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile tiny C-like source to tiny_vm assembly/bytecode")
    parser.add_argument("input", type=pathlib.Path, help="input .cvm.c file")
    parser.add_argument("-S", "--asm", type=pathlib.Path, help="output assembly file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="output bytecode .bin")
    parser.add_argument(
        "--map",
        action="store_true",
        help="emit source map sidecar JSON at <output>.map",
    )
    parser.add_argument(
        "--json-errors",
        action="store_true",
        help='emit diagnostics on stderr as JSON ({"errors": [{line,col,severity,message}]})',
    )
    args = parser.parse_args()

    if args.map and args.output is None:
        print("error: --map requires --output", file=sys.stderr)
        return 1

    src = args.input.read_text(encoding="utf-8")
    try:
        asm, comp = compile_with_map(src, str(args.input))
    except CompileError as exc:
        if args.json_errors:
            payload = {
                "errors": [
                    {
                        "line": exc.line,
                        "col": exc.col,
                        "severity": "error",
                        "message": exc.msg,
                    }
                ],
            }
            print(json.dumps(payload), file=sys.stderr)
        else:
            print(f"{args.input}:{exc.line}:{exc.col}: error: {exc.msg}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Non-CompileError = internal bug. Emit at line 1 so tooling still
        # has something to anchor the squiggly to.
        if args.json_errors:
            payload = {
                "errors": [
                    {"line": 1, "col": 1, "severity": "error", "message": f"internal: {exc}"}
                ],
            }
            print(json.dumps(payload), file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.asm:
        args.asm.write_text(asm, encoding="utf-8")
        print(f"wrote assembly: {args.asm}")
    else:
        print(asm, end="")

    if args.output:
        with tempfile.NamedTemporaryFile("w", suffix=".vm", delete=False) as tf:
            tf.write(asm)
            tmp_path = pathlib.Path(tf.name)
        try:
            cmd = [str(pathlib.Path("tools/vm_asm.py")), str(tmp_path), "-o", str(args.output)]
            subprocess.run(cmd, check=True)
        finally:
            tmp_path.unlink(missing_ok=True)

        if args.map:
            bytecode_size = args.output.stat().st_size
            mapping = comp.build_source_map(str(args.input), bytecode_size)
            map_path = pathlib.Path(str(args.output) + ".map")
            map_path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
            print(f"wrote source map: {map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
