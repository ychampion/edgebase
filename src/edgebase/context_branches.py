from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .context import build_context
from .git import changed_files as git_changed_files
from .git import current_commit, find_repo_root, run_git


SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ContextSnapshot:
    id: str
    kind: str
    message: str
    repo_root: str
    branch: str
    commit_sha: str
    dirty: bool
    changed_files: list[str]
    context_markdown: str
    token_estimate: int
    stale_files: list[str]
    next_command: str
    parent_id: str = ""
    worktree_path: str = ""
    worktree_branch: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["schema_version"] = SNAPSHOT_SCHEMA_VERSION
        return data


def create_checkpoint(root: str | Path, message: str, budget: int = 1200) -> ContextSnapshot:
    repo_root = find_repo_root(root)
    snapshot = build_snapshot(repo_root, "checkpoint", message, budget)
    write_snapshot(repo_root, snapshot)
    write_latest(repo_root, snapshot.id)
    return snapshot


def create_fork_plan(
    root: str | Path,
    message: str,
    budget: int = 1200,
    from_id: str = "",
    branch: str = "",
    path: str = "",
    allow_dirty: bool = False,
) -> ContextSnapshot:
    repo_root = find_repo_root(root)
    dirty_files = git_changed_files(repo_root)
    if dirty_files and not allow_dirty:
        raise RuntimeError("fork-plan refused: working tree is dirty: " + ", ".join(dirty_files))
    parent = resume_snapshot(repo_root, from_id) if from_id else create_checkpoint(repo_root, message, budget)
    branch_name = branch or f"edgebase/{safe_slug(message) or parent.id}"
    worktree_path = Path(path).expanduser() if path else repo_root.parent / f"{repo_root.name}-{branch_name.replace('/', '-')}"
    worktree_path = worktree_path.resolve()
    if worktree_path.exists() and any(worktree_path.iterdir()):
        raise RuntimeError(f"fork-plan refused: worktree path is not empty: {worktree_path}")
    proc = run_git(repo_root, ["worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"], timeout=30)
    if not proc or proc.returncode != 0:
        detail = proc.stderr.strip() if proc else "git worktree failed"
        raise RuntimeError(f"fork-plan refused: {detail}")
    snapshot = ContextSnapshot(
        id=new_snapshot_id("fork"),
        kind="fork-plan",
        message=message,
        repo_root=str(repo_root),
        branch=current_branch(repo_root),
        commit_sha=current_commit(repo_root),
        dirty=bool(dirty_files),
        changed_files=dirty_files,
        context_markdown=parent.context_markdown,
        token_estimate=parent.token_estimate,
        stale_files=parent.stale_files,
        next_command=f"/edgebase-resume {parent.id}",
        parent_id=parent.id,
        worktree_path=str(worktree_path),
        worktree_branch=branch_name,
    )
    write_snapshot(repo_root, snapshot)
    write_latest(repo_root, snapshot.id)
    write_snapshot(worktree_path, parent)
    write_latest(worktree_path, parent.id)
    return snapshot


def resume_snapshot(root: str | Path, snapshot_id: str = "") -> ContextSnapshot:
    repo_root = find_repo_root(root)
    target_id = snapshot_id.strip() or read_latest(repo_root)
    if not target_id:
        raise RuntimeError("No Edgebase checkpoint found. Run `/edgebase-checkpoint \"<message>\"` first, or use `edgebase checkpoint \"<message>\"` from a shell.")
    path = snapshots_dir(repo_root) / f"{target_id}.json"
    if not path.exists():
        raise RuntimeError(f"Edgebase checkpoint not found: {target_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid Edgebase checkpoint: {path}") from exc
    return snapshot_from_dict(data)


def render_resume(snapshot: ContextSnapshot) -> str:
    lines = [
        "# Edgebase Resume",
        "",
        f"Snapshot: `{snapshot.id}`",
        f"Kind: {snapshot.kind}",
        f"Message: {snapshot.message}",
        f"Branch: {snapshot.branch}",
        f"Commit: {snapshot.commit_sha}",
        "",
    ]
    if snapshot.worktree_path:
        lines.extend(["Fork plan:", f"- worktree: {snapshot.worktree_path}", f"- branch: {snapshot.worktree_branch}", ""])
    lines.append(snapshot.context_markdown.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def build_snapshot(repo_root: Path, kind: str, message: str, budget: int) -> ContextSnapshot:
    changed = git_changed_files(repo_root)
    capsule = build_context(repo_root, message, changed, budget)
    snapshot_id = new_snapshot_id(kind)
    return ContextSnapshot(
        id=snapshot_id,
        kind=kind,
        message=message,
        repo_root=str(repo_root),
        branch=current_branch(repo_root),
        commit_sha=current_commit(repo_root),
        dirty=bool(changed),
        changed_files=changed,
        context_markdown=capsule.markdown,
        token_estimate=capsule.token_estimate,
        stale_files=list(capsule.stale_files),
        next_command=f"/edgebase-resume {snapshot_id}",
    )


def snapshot_from_dict(data: dict[str, object]) -> ContextSnapshot:
    return ContextSnapshot(
        id=str(data.get("id") or ""),
        kind=str(data.get("kind") or "checkpoint"),
        message=str(data.get("message") or ""),
        repo_root=str(data.get("repo_root") or ""),
        branch=str(data.get("branch") or ""),
        commit_sha=str(data.get("commit_sha") or ""),
        dirty=bool(data.get("dirty")),
        changed_files=[str(item) for item in data.get("changed_files") or []],
        context_markdown=str(data.get("context_markdown") or ""),
        token_estimate=int(data.get("token_estimate") or 0),
        stale_files=[str(item) for item in data.get("stale_files") or []],
        next_command=str(data.get("next_command") or ""),
        parent_id=str(data.get("parent_id") or ""),
        worktree_path=str(data.get("worktree_path") or ""),
        worktree_branch=str(data.get("worktree_branch") or ""),
    )


def snapshots_dir(root: str | Path) -> Path:
    return find_repo_root(root) / ".edgebase" / "context-branches"


def write_snapshot(root: str | Path, snapshot: ContextSnapshot) -> Path:
    directory = snapshots_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot.id}.json"
    write_text_atomic(path, json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def write_latest(root: str | Path, snapshot_id: str) -> None:
    path = snapshots_dir(root) / "latest"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, snapshot_id + "\n")


def read_latest(root: str | Path) -> str:
    path = snapshots_dir(root) / "latest"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def current_branch(repo_root: Path) -> str:
    proc = run_git(repo_root, ["branch", "--show-current"], timeout=3)
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "HEAD"


def new_snapshot_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"


def safe_slug(value: str) -> str:
    chars: list[str] = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
        if len(chars) >= 42:
            break
    return "".join(chars).strip("-")


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
