from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from .git import changed_files as git_changed_files
from .git import file_sha, find_repo_root
from .indexer import index_repo
from .models import ContextCapsule, FileCandidate
from .store import Store


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "change",
    "update",
    "refactor",
    "fix",
    "add",
    "remove",
    "before",
    "after",
}


def tokenize(text: str) -> set[str]:
    return {
        part.lower()
        for part in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        if part.lower() not in STOPWORDS
    }


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.split()) * 1.35))


def build_context(
    root: str | Path,
    task: str,
    changed_files: list[str] | None = None,
    budget: int = 1200,
    auto_index: bool = True,
) -> ContextCapsule:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    if auto_index and not store.exists():
        index_repo(repo_root)

    graph = store.load_graph()
    if not graph["files"] and auto_index:
        index_repo(repo_root)
        graph = store.load_graph()

    changed = sorted(set(changed_files or git_changed_files(repo_root)))
    tokens = tokenize(task) | {Path(path).stem.lower() for path in changed}
    stale = stale_files(repo_root, graph["files"])
    candidates = rank_files(graph, tokens, changed)
    selected = select_files(candidates, graph, budget)
    markdown = render_markdown(repo_root, task, selected, graph, changed, stale, budget)
    return ContextCapsule(
        markdown=markdown,
        selected_files=tuple(candidate.path for candidate in selected),
        token_estimate=estimate_tokens(markdown),
        stale_files=tuple(stale),
    )


def stale_files(repo_root: Path, file_rows: list[object]) -> list[str]:
    stale: list[str] = []
    for row in file_rows:
        path = str(row["path"])
        full = repo_root / path
        if not full.exists():
            stale.append(path)
            continue
        try:
            if file_sha(full) != row["sha"]:
                stale.append(path)
        except OSError:
            stale.append(path)
    return stale


def rank_files(graph: dict[str, list[object]], tokens: set[str], changed: list[str]) -> list[FileCandidate]:
    symbol_by_file: dict[str, list[object]] = defaultdict(list)
    edges_by_file: dict[str, list[object]] = defaultdict(list)
    metric_by_file = {str(row["file_path"]): row for row in graph["metrics"]}
    for symbol in graph["symbols"]:
        symbol_by_file[str(symbol["file_path"])].append(symbol)
    for edge in graph["edges"]:
        edges_by_file[str(edge["file_path"])].append(edge)

    changed_set = set(changed)
    neighbor_files = graph_neighbors(graph, changed_set)
    candidates: list[FileCandidate] = []
    for row in graph["files"]:
        path = str(row["path"])
        score = 0.0
        reasons: list[str] = []
        path_l = path.lower()
        module_l = str(row["module"]).lower()
        if path in changed_set:
            score += 12
            reasons.append("changed file")
        if path in neighbor_files:
            score += 5
            reasons.append("neighbor of changed file")
        path_hits = sorted(t for t in tokens if t in path_l or t in module_l)
        if path_hits:
            score += 4 + len(path_hits)
            reasons.append("path/module matches " + ", ".join(path_hits[:4]))
        symbol_hits = [
            str(s["name"])
            for s in symbol_by_file[path]
            if str(s["name"]).lower() in tokens
            or any(token in str(s["name"]).lower() for token in tokens)
        ]
        if symbol_hits:
            score += 6 + min(4, len(symbol_hits))
            reasons.append("symbol matches " + ", ".join(symbol_hits[:4]))
        edge_hits = [
            str(e["dst_key"])
            for e in edges_by_file[path]
            if any(token in str(e["dst_key"]).lower() for token in tokens)
        ]
        if edge_hits:
            score += 3 + min(3, len(edge_hits))
            reasons.append("relationship matches " + ", ".join(edge_hits[:3]))
        metrics = metric_by_file.get(path)
        if metrics and int(metrics["churn_count"]) > 0:
            churn_score = min(3.0, math.log2(int(metrics["churn_count"]) + 1))
            score += churn_score
            if churn_score >= 2:
                reasons.append(f"hotspot churn={metrics['churn_count']}")
        if row["is_test"]:
            test_hit = any(token in path_l for token in tokens) or any(
                edge["rel"] == "TESTS" and edge["dst_key"] in changed_set for edge in edges_by_file[path]
            )
            if test_hit:
                score += 4
                reasons.append("test coverage candidate")
        if score > 0:
            candidates.append(FileCandidate(path, score, tuple(dict.fromkeys(reasons))))
    return sorted(candidates, key=lambda c: (-c.score, c.path))


def graph_neighbors(graph: dict[str, list[object]], changed: set[str]) -> set[str]:
    neighbors: set[str] = set()
    if not changed:
        return neighbors
    for edge in graph["edges"]:
        src = str(edge["src_key"])
        dst = str(edge["dst_key"])
        file_path = str(edge["file_path"])
        if file_path in changed or src in changed or dst in changed:
            if edge["dst_type"] == "file":
                neighbors.add(dst)
            neighbors.add(file_path)
        if edge["dst_type"] == "file" and dst in changed:
            neighbors.add(file_path)
    return neighbors - changed


def select_files(
    candidates: list[FileCandidate], graph: dict[str, list[object]], budget: int
) -> list[FileCandidate]:
    if not candidates:
        return []
    loc_by_file = {str(row["path"]): int(row["loc"]) for row in graph["files"]}
    selected: list[FileCandidate] = []
    spent = 180
    for candidate in candidates:
        cost = min(280, 40 + loc_by_file.get(candidate.path, 20) * 2)
        if selected and spent + cost > budget:
            continue
        selected.append(candidate)
        spent += cost
        if len(selected) >= 8:
            break
    return selected


def render_markdown(
    repo_root: Path,
    task: str,
    selected: list[FileCandidate],
    graph: dict[str, list[object]],
    changed: list[str],
    stale: list[str],
    budget: int,
) -> str:
    symbol_by_file: dict[str, list[object]] = defaultdict(list)
    edge_by_file: dict[str, list[object]] = defaultdict(list)
    metric_by_file = {str(row["file_path"]): row for row in graph["metrics"]}
    for symbol in graph["symbols"]:
        symbol_by_file[str(symbol["file_path"])].append(symbol)
    for edge in graph["edges"]:
        edge_by_file[str(edge["file_path"])].append(edge)

    lines: list[str] = []
    lines.append("# Edgebase Context")
    lines.append("")
    lines.append(f"Task: {task}")
    lines.append(f"Repo: {repo_root}")
    lines.append(f"Budget: {budget} tokens")
    lines.append("")
    if stale:
        lines.append("Freshness: stale files detected; run `edgebase index --changed` or `edgebase index`.")
        lines.append("")
        for path in stale[:8]:
            lines.append(f"- stale: `{path}`")
        lines.append("")
    else:
        lines.append("Freshness: graph file hashes match the working tree.")
        lines.append("")
    if changed:
        lines.append("Changed files:")
        for path in changed[:12]:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append("High-signal files:")
    if not selected:
        lines.append("- No graph match yet. Run `edgebase index` or use a more specific task.")
    for candidate in selected:
        metrics = metric_by_file.get(candidate.path)
        owner = str(metrics["owner"]) if metrics and metrics["owner"] else "unknown"
        churn = int(metrics["churn_count"]) if metrics else 0
        reason = "; ".join(candidate.reasons) if candidate.reasons else "ranked by graph"
        lines.append(f"- `{candidate.path}` score={candidate.score:.1f} owner={owner} churn={churn}: {reason}")
    lines.append("")

    lines.append("Relevant symbols:")
    symbol_count = 0
    for candidate in selected:
        for symbol in symbol_by_file[candidate.path][:8]:
            exported = "exported" if symbol["exported"] else "internal"
            lines.append(
                f"- `{symbol['name']}` {symbol['kind']} in `{symbol['file_path']}:{symbol['line']}` "
                f"({exported}, confidence={float(symbol['confidence']):.2f})"
            )
            symbol_count += 1
            if symbol_count >= 18:
                break
        if symbol_count >= 18:
            break
    if symbol_count == 0:
        lines.append("- No symbols selected.")
    lines.append("")

    lines.append("Source-backed relationships:")
    edge_count = 0
    for candidate in selected:
        for edge in edge_by_file[candidate.path]:
            if edge["rel"] not in {"IMPORTS", "CALLS", "TESTS"}:
                continue
            lines.append(
                f"- `{edge['src_key']}` -[{edge['rel']}]-> `{edge['dst_key']}` "
                f"@ `{edge['file_path']}:{edge['line']}` "
                f"via {edge['extractor']} confidence={float(edge['confidence']):.2f}"
            )
            edge_count += 1
            if edge_count >= 22:
                break
        if edge_count >= 22:
            break
    if edge_count == 0:
        lines.append("- No relationships selected.")
    lines.append("")

    lines.append("Next reads:")
    for candidate in selected[:5]:
        lines.append(f"- Read `{candidate.path}` before editing.")
    tests = [
        str(edge["file_path"])
        for row in selected
        for edge in edge_by_file[row.path]
        if edge["rel"] == "TESTS"
    ]
    for test in sorted(set(tests))[:4]:
        lines.append(f"- Run or inspect test `{test}`.")
    lines.append("")
    lines.append("Machine summary:")
    lines.append(
        json.dumps(
            {
                "selected_files": [candidate.path for candidate in selected],
                "stale_files": stale,
                "changed_files": changed,
            },
            sort_keys=True,
        )
    )
    return "\n".join(lines)
