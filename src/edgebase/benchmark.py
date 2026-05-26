from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .context import build_context, estimate_tokens, tokenize
from .indexer import index_repo


@dataclass
class BenchResult:
    task_id: str
    runner: str
    wall_ms: int
    token_estimate: int
    tool_calls_estimate: int
    stale_context_incidents: int
    skipped_reason: str = ""


def run_benchmark(repo: str | Path, tasks_file: str | Path, out: str | Path) -> list[BenchResult]:
    repo_path = Path(repo).resolve()
    tasks = load_tasks(tasks_file)
    index_repo(repo_path)
    results: list[BenchResult] = []
    for task in tasks:
        results.append(run_edgebase(repo_path, task))
        results.append(run_rg(repo_path, task))
        for runner, env_name in (
            ("codegraphcontext", "EDGEBASE_BENCH_CODEGRAPHCONTEXT_CMD"),
            ("codebase-memory-mcp", "EDGEBASE_BENCH_CODEBASE_MEMORY_CMD"),
            ("gitnexus", "EDGEBASE_BENCH_GITNEXUS_CMD"),
        ):
            results.append(run_external(repo_path, task, runner, env_name))
    Path(out).write_text(
        json.dumps([asdict(result) for result in results], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


def load_tasks(path: str | Path) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        task = json.loads(line)
        task.setdefault("id", f"task-{index}")
        task.setdefault("changed_files", [])
        tasks.append(task)
    return tasks


def run_edgebase(repo: Path, task: dict[str, object]) -> BenchResult:
    started = time.perf_counter()
    capsule = build_context(
        repo,
        str(task["task"]),
        [str(p) for p in task.get("changed_files", [])],
        budget=int(task.get("budget", 1200)),
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    return BenchResult(
        str(task["id"]),
        "edgebase",
        elapsed,
        capsule.token_estimate,
        1,
        len(capsule.stale_files),
    )


def run_rg(repo: Path, task: dict[str, object]) -> BenchResult:
    terms = sorted(tokenize(str(task["task"])))[:6]
    started = time.perf_counter()
    output_parts: list[str] = []
    calls = 0
    for term in terms:
        proc = subprocess.run(
            ["rg", "-n", "--max-count", "8", term],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        calls += 1
        output_parts.append(proc.stdout)
    elapsed = int((time.perf_counter() - started) * 1000)
    text = "\n".join(output_parts)
    return BenchResult(str(task["id"]), "rg", elapsed, estimate_tokens(text), calls, 0)


def run_external(repo: Path, task: dict[str, object], runner: str, env_name: str) -> BenchResult:
    template = os.environ.get(env_name)
    if not template:
        return BenchResult(str(task["id"]), runner, 0, 0, 0, 0, f"{env_name} is not set")
    command = template.format(
        repo=str(repo),
        task=str(task["task"]),
        changed_files=",".join(str(p) for p in task.get("changed_files", [])),
    )
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=repo,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=int(os.environ.get("EDGEBASE_BENCH_TIMEOUT", "120")),
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    skipped = "" if proc.returncode == 0 else f"exit {proc.returncode}"
    return BenchResult(
        str(task["id"]),
        runner,
        elapsed,
        estimate_tokens(proc.stdout),
        1,
        0,
        skipped,
    )
