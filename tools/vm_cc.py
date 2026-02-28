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
      host(const_expr, expr);
  - expressions over int literals/vars/constants:
      +, -, *, /, %, <, >, ==
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass


@dataclass
class Token:
    kind: str
    text: str


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//.*$", "", src, flags=re.M)
    return src


def lex(src: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if src.startswith("==", i):
            tokens.append(Token("SYM", "=="))
            i += 2
            continue
        if ch in "{}();,=+-*/<>%":
            tokens.append(Token("SYM", ch))
            i += 1
            continue
        m = re.match(r"[A-Za-z_]\w*", src[i:])
        if m:
            text = m.group(0)
            kind = "KW" if text in {"const", "int", "while", "if", "else"} else "ID"
            tokens.append(Token(kind, text))
            i += len(text)
            continue
        m = re.match(r"[+-]?(?:0x[0-9A-Fa-f]+|\d+)", src[i:])
        if m:
            tokens.append(Token("NUM", m.group(0)))
            i += len(m.group(0))
            continue
        raise ValueError(f"lex error near: {src[i:i+20]!r}")
    tokens.append(Token("EOF", ""))
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
            raise ValueError(f"expected {kind} {text or ''}, got {t.kind} {t.text!r}")
        return self.take()

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
            raise ValueError(f"invalid statement starting with identifier {name}")
        raise ValueError(f"unexpected token {t.kind} {t.text!r}")

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
            op = self.take().text
            rhs = self.parse_rel()
            node = {"kind": "bin", "op": op, "l": node, "r": rhs}
        return node

    def parse_rel(self) -> dict:
        node = self.parse_add()
        while self.peek().kind == "SYM" and self.peek().text in {"<", ">"}:
            op = self.take().text
            rhs = self.parse_add()
            node = {"kind": "bin", "op": op, "l": node, "r": rhs}
        return node

    def parse_add(self) -> dict:
        node = self.parse_mul()
        while self.peek().kind == "SYM" and self.peek().text in {"+", "-"}:
            op = self.take().text
            rhs = self.parse_mul()
            node = {"kind": "bin", "op": op, "l": node, "r": rhs}
        return node

    def parse_mul(self) -> dict:
        node = self.parse_term()
        while self.peek().kind == "SYM" and self.peek().text in {"*", "/", "%"}:
            op = self.take().text
            rhs = self.parse_term()
            node = {"kind": "bin", "op": op, "l": node, "r": rhs}
        return node

    def parse_term(self) -> dict:
        t = self.peek()
        if t.kind == "NUM":
            self.take()
            return {"kind": "num", "value": int(t.text, 0)}
        if t.kind == "ID":
            self.take()
            return {"kind": "name", "value": t.text}
        if t.kind == "SYM" and t.text == "(":
            self.take()
            node = self.parse_expr()
            self.expect("SYM", ")")
            return node
        raise ValueError(f"unexpected token in expr: {t.kind} {t.text!r}")


class Compiler:
    def __init__(self) -> None:
        self.consts: dict[str, int] = {}
        self.vars: dict[str, int] = {}
        self.lines: list[str] = []
        self.label_id = 0

    def new_label(self, prefix: str) -> str:
        name = f"{prefix}_{self.label_id}"
        self.label_id += 1
        return name

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def alloc_var(self, name: str) -> int:
        if name in self.vars:
            raise ValueError(f"duplicate variable {name}")
        if len(self.vars) >= 16:
            raise ValueError("too many variables (max 16)")
        idx = len(self.vars)
        self.vars[name] = idx
        return idx

    def eval_const_expr(self, node: dict) -> int:
        kind = node["kind"]
        if kind == "num":
            return int(node["value"])
        if kind == "name":
            name = node["value"]
            if name not in self.consts:
                raise ValueError(f"'{name}' is not a compile-time const")
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
                    raise ValueError("mod by zero in const expression")
                return l % r
            if op == "*":
                return l * r
            if op == "/":
                if r == 0:
                    raise ValueError("div by zero in const expression")
                return int(l / r)
            if op == "==":
                return 1 if l == r else 0
            if op == "<":
                return 1 if l < r else 0
            if op == ">":
                return 1 if l > r else 0
        raise ValueError("unsupported const expression")

    def emit_push_imm(self, value: int) -> None:
        if -128 <= value <= 127:
            self.emit(f"PUSH8 {value}")
        elif -32768 <= value <= 32767:
            self.emit(f"PUSH16 {value}")
        else:
            raise ValueError(f"literal out of PUSH16 range: {value}")

    def emit_expr(self, node: dict) -> None:
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
            raise ValueError(f"unknown symbol '{name}'")
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
                raise ValueError(f"unsupported operator {op}")
            return
        raise ValueError(f"unsupported expression node {kind}")

    def emit_stmt(self, stmt: dict) -> None:
        kind = stmt["kind"]
        if kind == "const_decl":
            self.consts[stmt["name"]] = self.eval_const_expr(stmt["expr"])
            return
        if kind == "var_decl":
            idx = self.alloc_var(stmt["name"])
            if stmt["init"] is not None:
                self.emit_expr(stmt["init"])
                self.emit(f"LSET {idx}")
            return
        if kind == "assign":
            if stmt["name"] not in self.vars:
                raise ValueError(f"assignment to undeclared variable '{stmt['name']}'")
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
        raise ValueError(f"unsupported statement kind {kind}")

    def emit_call(self, name: str, args: list[dict]) -> None:
        if name == "led_write":
            if len(args) != 1:
                raise ValueError("led_write expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 0")
            return
        if name == "delay_ms":
            if len(args) != 1:
                raise ValueError("delay_ms expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 1")
            return
        if name == "print_u32":
            if len(args) != 1:
                raise ValueError("print_u32 expects 1 arg")
            self.emit_expr(args[0])
            self.emit("HOST 2")
            return
        if name == "host":
            if len(args) != 2:
                raise ValueError("host expects 2 args")
            host_id = self.eval_const_expr(args[0])
            if host_id < 0 or host_id > 255:
                raise ValueError("host id out of range 0..255")
            self.emit_expr(args[1])
            self.emit(f"HOST {host_id}")
            return
        raise ValueError(f"unsupported function '{name}'")

    def compile(self, stmts: list[dict]) -> str:
        for s in stmts:
            self.emit_stmt(s)
        self.emit("HALT")
        return "\n".join(self.lines) + "\n"


def compile_to_asm(src: str) -> str:
    src = strip_comments(src)
    tokens = lex(src)
    parser = Parser(tokens)
    prog = parser.parse_program()
    return Compiler().compile(prog)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile tiny C-like source to tiny_vm assembly/bytecode")
    parser.add_argument("input", type=pathlib.Path, help="input .cvm.c file")
    parser.add_argument("-S", "--asm", type=pathlib.Path, help="output assembly file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="output bytecode .bin")
    args = parser.parse_args()

    src = args.input.read_text(encoding="utf-8")
    try:
        asm = compile_to_asm(src)
    except Exception as exc:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
