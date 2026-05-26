from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    file_path: str
    line: int
    end_line: int
    signature: str
    exported: bool
    extractor: str
    confidence: float

    @property
    def key(self) -> str:
        return f"{self.file_path}#{self.kind}:{self.name}:{self.line}"


@dataclass(frozen=True)
class Edge:
    src_type: str
    src_key: str
    rel: str
    dst_type: str
    dst_key: str
    file_path: str
    line: int
    extractor: str
    confidence: float


@dataclass
class FileFacts:
    path: str
    language: str
    module: str
    loc: int
    is_test: bool
    symbols: list[Symbol] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@dataclass(frozen=True)
class FileCandidate:
    path: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContextCapsule:
    markdown: str
    selected_files: tuple[str, ...]
    token_estimate: int
    stale_files: tuple[str, ...]
