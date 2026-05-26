from __future__ import annotations

import hashlib
import os
import subprocess
from collections import Counter
from pathlib import Path


IGNORE_DIRS = {
    ".git",
    ".edgebase",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
}


def run_git(root: Path, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def find_repo_root(start: str | Path) -> Path:
    start_path = Path(start).resolve()
    proc = run_git(start_path, ["rev-parse", "--show-toplevel"], timeout=3)
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return start_path


def is_git_repo(root: Path) -> bool:
    proc = run_git(root, ["rev-parse", "--is-inside-work-tree"], timeout=3)
    return bool(proc and proc.returncode == 0 and proc.stdout.strip() == "true")


def current_commit(root: Path) -> str:
    proc = run_git(root, ["rev-parse", "HEAD"], timeout=3)
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "working-tree"


def changed_files(root: Path) -> list[str]:
    proc = run_git(root, ["status", "--porcelain"], timeout=5)
    if not proc or proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        raw = raw.strip('"')
        if raw and not is_edgebase_cache_path(raw):
            paths.append(raw)
    return sorted(set(paths))


def is_edgebase_cache_path(path: str) -> bool:
    return ".edgebase" in Path(path).parts


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def language_for(path: str) -> str | None:
    return SOURCE_EXTENSIONS.get(Path(path).suffix.lower())


def should_skip_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in IGNORE_DIRS for part in parts):
        return True
    name = Path(path).name
    return (
        name.endswith(".min.js")
        or name.endswith(".map")
        or name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
    )


def iter_source_files(root: Path) -> list[str]:
    paths: list[str] = []
    if is_git_repo(root):
        proc = run_git(root, ["ls-files", "--cached", "--others", "--exclude-standard"], timeout=20)
        if proc and proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if language_for(line) and not should_skip_path(line):
                    paths.append(line)
            return sorted(set(paths))

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        base = Path(dirpath)
        for filename in filenames:
            full = base / filename
            rel = full.relative_to(root).as_posix()
            if language_for(rel) and not should_skip_path(rel):
                paths.append(rel)
    return sorted(paths)


def file_history(root: Path, rel_path: str, max_count: int = 50) -> dict[str, object]:
    if not is_git_repo(root):
        return {"owner": "", "authors": {}, "recent_commits": [], "churn": 0}
    proc = run_git(
        root,
        ["log", f"--max-count={max_count}", "--format=%H%x09%an", "--", rel_path],
        timeout=10,
    )
    if not proc or proc.returncode != 0:
        return {"owner": "", "authors": {}, "recent_commits": [], "churn": 0}
    authors: Counter[str] = Counter()
    commits: list[str] = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        commit, author = line.split("\t", 1)
        commits.append(commit)
        authors[author] += 1
    owner = authors.most_common(1)[0][0] if authors else ""
    return {
        "owner": owner,
        "authors": dict(authors),
        "recent_commits": commits[:5],
        "churn": len(commits),
    }
