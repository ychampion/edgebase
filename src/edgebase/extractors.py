from __future__ import annotations

import ast
import re
from pathlib import Path

from .git import language_for
from .models import Edge, FileFacts, Symbol


def module_name(path: str) -> str:
    p = Path(path)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else p.stem


def is_test_path(path: str) -> bool:
    name = Path(path).name.lower()
    parts = {part.lower() for part in Path(path).parts}
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or name.endswith("_test.go")
        or "tests" in parts
        or "__tests__" in parts
    )


def extract_file(path: str, text: str) -> FileFacts:
    language = language_for(path) or "unknown"
    if language == "python":
        return PythonExtractor(path, text).extract()
    if language in {"javascript", "typescript"}:
        return JsTsExtractor(path, text, language).extract()
    return GenericExtractor(path, text, language).extract()


class PythonExtractor(ast.NodeVisitor):
    extractor = "python.ast"

    def __init__(self, path: str, text: str):
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.stack: list[Symbol] = []

    def extract(self) -> FileFacts:
        try:
            tree = ast.parse(self.text)
        except SyntaxError:
            return FileFacts(
                path=self.path,
                language="python",
                module=module_name(self.path),
                loc=len(self.lines),
                is_test=is_test_path(self.path),
            )
        self.visit(tree)
        return FileFacts(
            path=self.path,
            language="python",
            module=module_name(self.path),
            loc=len(self.lines),
            is_test=is_test_path(self.path),
            symbols=self.symbols,
            edges=self.edges,
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(
                Edge(
                    "file",
                    self.path,
                    "IMPORTS",
                    "module",
                    alias.name,
                    self.path,
                    node.lineno,
                    self.extractor,
                    0.95,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.edges.append(
                Edge(
                    "file",
                    self.path,
                    "IMPORTS",
                    "module",
                    "." * node.level + node.module,
                    self.path,
                    node.lineno,
                    self.extractor,
                    0.9,
                )
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_symbol(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_symbol(node, "function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_symbol(node, "class")

    def visit_Call(self, node: ast.Call) -> None:
        dst = call_name(node.func)
        if dst:
            src_type = "symbol" if self.stack else "file"
            src_key = self.stack[-1].key if self.stack else self.path
            self.edges.append(
                Edge(
                    src_type,
                    src_key,
                    "CALLS",
                    "symbol_name",
                    dst,
                    self.path,
                    getattr(node, "lineno", 1),
                    self.extractor,
                    0.55,
                )
            )
        self.generic_visit(node)

    def _visit_symbol(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name")
        line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", line)
        signature = self.lines[line - 1].strip() if 0 <= line - 1 < len(self.lines) else name
        symbol = Symbol(
            name=name,
            kind=kind,
            file_path=self.path,
            line=line,
            end_line=end_line,
            signature=signature,
            exported=not name.startswith("_"),
            extractor=self.extractor,
            confidence=0.95,
        )
        self.symbols.append(symbol)
        self.stack.append(symbol)
        self.generic_visit(node)
        self.stack.pop()


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class JsTsExtractor:
    extractor = "jsts.regex"

    IMPORT_RE = re.compile(
        r"(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+|require\()\s*['\"]([^'\"]+)['\"]"
    )
    SYMBOL_RES = [
        re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"^\s*export\s+class\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=]*=>"),
    ]
    CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(")
    SKIP_CALLS = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
        "typeof",
        "new",
    }

    def __init__(self, path: str, text: str, language: str):
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.language = language

    def extract(self) -> FileFacts:
        symbols: list[Symbol] = []
        edges: list[Edge] = []
        for index, line in enumerate(self.lines, start=1):
            for match in self.IMPORT_RE.finditer(line):
                edges.append(
                    Edge(
                        "file",
                        self.path,
                        "IMPORTS",
                        "module",
                        match.group(1),
                        self.path,
                        index,
                        self.extractor,
                        0.8,
                    )
                )
            for pattern in self.SYMBOL_RES:
                match = pattern.search(line)
                if not match:
                    continue
                name = match.group(1)
                kind = "class" if "class" in pattern.pattern else "function"
                symbols.append(
                    Symbol(
                        name=name,
                        kind=kind,
                        file_path=self.path,
                        line=index,
                        end_line=index,
                        signature=line.strip(),
                        exported=line.lstrip().startswith("export"),
                        extractor=self.extractor,
                        confidence=0.7,
                    )
                )
                break
            for match in self.CALL_RE.finditer(line):
                dst = match.group(1)
                if dst.split(".", 1)[0] in self.SKIP_CALLS:
                    continue
                edges.append(
                    Edge(
                        "file",
                        self.path,
                        "CALLS",
                        "symbol_name",
                        dst,
                        self.path,
                        index,
                        self.extractor,
                        0.35,
                    )
                )
        return FileFacts(
            path=self.path,
            language=self.language,
            module=module_name(self.path),
            loc=len(self.lines),
            is_test=is_test_path(self.path),
            symbols=symbols,
            edges=edges,
        )


class GenericExtractor:
    extractor = "generic.regex"
    GO_FUNC_RE = re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(")
    RUST_SYMBOL_RE = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(fn|struct|enum|trait)\s+([A-Za-z_]\w*)")
    USE_RE = re.compile(r"^\s*(?:use|import)\s+([^;]+)")
    CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")

    def __init__(self, path: str, text: str, language: str):
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.language = language

    def extract(self) -> FileFacts:
        symbols: list[Symbol] = []
        edges: list[Edge] = []
        for index, line in enumerate(self.lines, start=1):
            use = self.USE_RE.search(line)
            if use:
                edges.append(
                    Edge(
                        "file",
                        self.path,
                        "IMPORTS",
                        "module",
                        use.group(1).strip().strip('"'),
                        self.path,
                        index,
                        self.extractor,
                        0.45,
                    )
                )
            match = self.GO_FUNC_RE.search(line) if self.language == "go" else None
            if not match and self.language == "rust":
                rust_match = self.RUST_SYMBOL_RE.search(line)
                if rust_match:
                    name = rust_match.group(2)
                    kind = "function" if rust_match.group(1) == "fn" else rust_match.group(1)
                    symbols.append(self._symbol(name, kind, line, index, line.strip().startswith("pub ")))
                    continue
            if match:
                symbols.append(self._symbol(match.group(1), "function", line, index, True))
            for call in self.CALL_RE.finditer(line):
                edges.append(
                    Edge(
                        "file",
                        self.path,
                        "CALLS",
                        "symbol_name",
                        call.group(1),
                        self.path,
                        index,
                        self.extractor,
                        0.3,
                    )
                )
        return FileFacts(
            path=self.path,
            language=self.language,
            module=module_name(self.path),
            loc=len(self.lines),
            is_test=is_test_path(self.path),
            symbols=symbols,
            edges=edges,
        )

    def _symbol(self, name: str, kind: str, line: str, index: int, exported: bool) -> Symbol:
        return Symbol(
            name=name,
            kind=kind,
            file_path=self.path,
            line=index,
            end_line=index,
            signature=line.strip(),
            exported=exported,
            extractor=self.extractor,
            confidence=0.5,
        )
