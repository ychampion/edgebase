from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .extractors import extract_file
from .git import current_commit, file_history, file_sha, find_repo_root, iter_source_files
from .models import Edge
from .store import Store


@dataclass(frozen=True)
class IndexResult:
    root: Path
    files: int
    symbols: int
    edges: int
    commit_sha: str


def index_repo(root: str | Path, paths: list[str] | None = None, reset: bool = True) -> IndexResult:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    commit_sha = current_commit(repo_root)
    if reset:
        store.reset()
    selected_paths = sorted(set(paths or iter_source_files(repo_root)))
    now = datetime.now(timezone.utc).isoformat()

    indexed_files: list[str] = []
    for rel_path in selected_paths:
        full = repo_root / rel_path
        if not full.exists() or not full.is_file():
            store.delete_file(rel_path)
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        facts = extract_file(rel_path, text)
        store.upsert_file(facts, file_sha(full), commit_sha, now)
        history = file_history(repo_root, rel_path)
        store.upsert_metrics(
            rel_path,
            int(history["churn"]),
            str(history["recent_commits"][0]) if history["recent_commits"] else commit_sha,
            str(history["owner"]),
            dict(history["authors"]),
            list(history["recent_commits"]),
        )
        indexed_files.append(rel_path)

    infer_test_edges(store, repo_root, commit_sha)
    store.set_meta("root", str(repo_root))
    store.set_meta("commit_sha", commit_sha)
    store.set_meta("indexed_at", now)
    stats = store.stats()
    return IndexResult(repo_root, stats["files"], stats["symbols"], stats["edges"], commit_sha)


def infer_test_edges(store: Store, repo_root: Path, commit_sha: str) -> None:
    store.delete_edges_by_extractor("tests.infer")
    graph = store.load_graph()
    files = graph["files"]
    source_paths = {row["path"] for row in files if not row["is_test"]}
    for test_row in (row for row in files if row["is_test"]):
        test_path = str(test_row["path"])
        candidates = test_targets(test_path, source_paths)
        for target in candidates[:3]:
            store.add_edge(
                Edge(
                    "file",
                    test_path,
                    "TESTS",
                    "file",
                    target,
                    test_path,
                    1,
                    "tests.infer",
                    0.45,
                ),
                commit_sha,
                "fresh",
            )


def test_targets(test_path: str, source_paths: set[str]) -> list[str]:
    p = Path(test_path)
    stem = p.stem
    normalized = (
        stem.removeprefix("test_")
        .removesuffix("_test")
        .replace(".test", "")
        .replace(".spec", "")
    )
    matches: list[str] = []
    for source in sorted(source_paths):
        source_stem = Path(source).stem
        if source_stem == normalized:
            matches.append(source)
        elif normalized and normalized in source:
            matches.append(source)
    return matches
