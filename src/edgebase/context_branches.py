from __future__ import annotations

import json
import re
import shlex
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .context import build_context
from .git import changed_files, current_commit, find_repo_root, run_git
from .store import Store


@dataclass(frozen=True)
class ContextSnapshot:
    id: str
    kind: str
    message: str
    repo_root: str
    branch: str
    commit_sha: str
    dirty: bool
    changed_files: tuple[str, ...]
    context_markdown: str
    token_estimate: int
    stale_files: tuple[str, ...]
    parent_id: str
    worktree_path: str
    worktree_branch: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["changed_files"] = list(self.changed_files)
        data["stale_files"] = list(self.stale_files)
        data["next_command"] = next_command(self)
        return data


def create_checkpoint(root: str | Path, message: str, budget: int) -> ContextSnapshot:
    repo_root = find_repo_root(root)
    snapshot = build_snapshot(repo_root, "checkpoint", message, budget)
    save_snapshot(repo_root, snapshot)
    return snapshot


def create_fork_plan(
    root: str | Path,
    message: str,
    budget: int,
    from_id: str = "",
    branch: str = "",
    path: str = "",
    allow_dirty: bool = False,
) -> ContextSnapshot:
    repo_root = find_repo_root(root)
    changed = changed_files(repo_root)
    if changed and not allow_dirty:
        listed = "\n".join(f"- {item}" for item in changed[:12])
        raise RuntimeError(
            "fork-plan refused: working tree has uncommitted changes. "
            "Commit, stash, or rerun with --allow-dirty.\n" + listed
        )

    parent = load_snapshot(repo_root, from_id) if from_id else latest_snapshot(repo_root)
    parent_id = parent.id if parent else ""
    snapshot_id = new_snapshot_id("fp")
    slug = slugify(message)
    worktree_branch = branch or f"edgebase/{slug}-{snapshot_id[-8:]}"
    worktree_path = Path(path).expanduser().resolve() if path else default_worktree_path(repo_root, slug, snapshot_id)
    if worktree_path.exists():
        raise RuntimeError(f"fork-plan refused: worktree path already exists: {worktree_path}")

    add_worktree(repo_root, worktree_path, worktree_branch)
    snapshot = build_snapshot(
        repo_root,
        "fork-plan",
        message,
        budget,
        snapshot_id=snapshot_id,
        parent_id=parent_id,
        worktree_path=str(worktree_path),
        worktree_branch=worktree_branch,
    )
    save_snapshot(repo_root, snapshot)
    save_snapshot(worktree_path, snapshot)
    return snapshot


def resume_snapshot(root: str | Path, snapshot_id: str = "") -> ContextSnapshot:
    repo_root = find_repo_root(root)
    snapshot = load_snapshot(repo_root, snapshot_id) if snapshot_id else latest_snapshot(repo_root)
    if not snapshot:
        if snapshot_id:
            raise RuntimeError(f"unknown context snapshot: {snapshot_id}")
        raise RuntimeError("no context snapshots found; run `edgebase checkpoint \"message\"` first")
    return snapshot


def render_resume(snapshot: ContextSnapshot) -> str:
    lines = [
        "# Edgebase Resume",
        "",
        f"Snapshot: `{snapshot.id}` ({snapshot.kind})",
        f"Message: {snapshot.message}",
        f"Created: {snapshot.created_at}",
        f"Source repo: `{snapshot.repo_root}`",
        f"Source branch: `{snapshot.branch}`",
        f"Source commit: `{snapshot.commit_sha}`",
        f"Dirty when captured: {'yes' if snapshot.dirty else 'no'}",
    ]
    if snapshot.parent_id:
        lines.append(f"Parent snapshot: `{snapshot.parent_id}`")
    if snapshot.changed_files:
        lines.append("")
        lines.append("Changed files:")
        for path in snapshot.changed_files:
            lines.append(f"- `{path}`")
    if snapshot.worktree_path:
        lines.extend(
            [
                "",
                f"Fork worktree: `{snapshot.worktree_path}`",
                f"Fork branch: `{snapshot.worktree_branch}`",
                f"Next command: `{next_command(snapshot)}`",
            ]
        )
    lines.extend(["", "## Stored Context", "", snapshot.context_markdown])
    return "\n".join(lines)


def save_snapshot(root: str | Path, snapshot: ContextSnapshot) -> None:
    store = Store(root)
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO context_snapshots(
              id, kind, message, repo_root, branch, commit_sha, dirty,
              changed_files_json, context_markdown, token_estimate,
              stale_files_json, parent_id, worktree_path, worktree_branch, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              kind=excluded.kind,
              message=excluded.message,
              repo_root=excluded.repo_root,
              branch=excluded.branch,
              commit_sha=excluded.commit_sha,
              dirty=excluded.dirty,
              changed_files_json=excluded.changed_files_json,
              context_markdown=excluded.context_markdown,
              token_estimate=excluded.token_estimate,
              stale_files_json=excluded.stale_files_json,
              parent_id=excluded.parent_id,
              worktree_path=excluded.worktree_path,
              worktree_branch=excluded.worktree_branch,
              created_at=excluded.created_at
            """,
            snapshot_row(snapshot),
        )


def load_snapshot(root: str | Path, snapshot_id: str) -> ContextSnapshot:
    store = Store(root)
    if not store.exists():
        raise RuntimeError(f"unknown context snapshot: {snapshot_id}")
    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM context_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
    if not row:
        raise RuntimeError(f"unknown context snapshot: {snapshot_id}")
    return snapshot_from_row(row)


def latest_snapshot(root: str | Path) -> ContextSnapshot | None:
    store = Store(root)
    if not store.exists():
        return None
    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM context_snapshots ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    return snapshot_from_row(row) if row else None


def build_snapshot(
    repo_root: Path,
    kind: str,
    message: str,
    budget: int,
    snapshot_id: str = "",
    parent_id: str = "",
    worktree_path: str = "",
    worktree_branch: str = "",
) -> ContextSnapshot:
    changed = tuple(changed_files(repo_root))
    capsule = build_context(repo_root, message, list(changed), budget)
    return ContextSnapshot(
        id=snapshot_id or new_snapshot_id("cp"),
        kind=kind,
        message=message,
        repo_root=str(repo_root),
        branch=current_branch(repo_root),
        commit_sha=current_commit(repo_root),
        dirty=bool(changed),
        changed_files=changed,
        context_markdown=capsule.markdown,
        token_estimate=capsule.token_estimate,
        stale_files=tuple(capsule.stale_files),
        parent_id=parent_id,
        worktree_path=worktree_path,
        worktree_branch=worktree_branch,
        created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
    )


def current_branch(root: Path) -> str:
    proc = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=3)
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "HEAD"


def add_worktree(root: Path, path: Path, branch: str) -> None:
    proc = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path), "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"git worktree add failed: {detail}")


def new_snapshot_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def slugify(message: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", message.lower()).strip("-")
    return (slug or "plan")[:40].strip("-") or "plan"


def default_worktree_path(repo_root: Path, slug: str, snapshot_id: str) -> Path:
    return repo_root.parent / f"{repo_root.name}-{slug}-{snapshot_id[-8:]}"


def snapshot_row(snapshot: ContextSnapshot) -> tuple[object, ...]:
    return (
        snapshot.id,
        snapshot.kind,
        snapshot.message,
        snapshot.repo_root,
        snapshot.branch,
        snapshot.commit_sha,
        1 if snapshot.dirty else 0,
        json.dumps(list(snapshot.changed_files), sort_keys=True),
        snapshot.context_markdown,
        snapshot.token_estimate,
        json.dumps(list(snapshot.stale_files), sort_keys=True),
        snapshot.parent_id,
        snapshot.worktree_path,
        snapshot.worktree_branch,
        snapshot.created_at,
    )


def snapshot_from_row(row: object) -> ContextSnapshot:
    return ContextSnapshot(
        id=str(row["id"]),
        kind=str(row["kind"]),
        message=str(row["message"]),
        repo_root=str(row["repo_root"]),
        branch=str(row["branch"]),
        commit_sha=str(row["commit_sha"]),
        dirty=bool(row["dirty"]),
        changed_files=tuple(json.loads(str(row["changed_files_json"]))),
        context_markdown=str(row["context_markdown"]),
        token_estimate=int(row["token_estimate"]),
        stale_files=tuple(json.loads(str(row["stale_files_json"]))),
        parent_id=str(row["parent_id"]),
        worktree_path=str(row["worktree_path"]),
        worktree_branch=str(row["worktree_branch"]),
        created_at=str(row["created_at"]),
    )


def next_command(snapshot: ContextSnapshot) -> str:
    if not snapshot.worktree_path:
        return f"edgebase resume {snapshot.id}"
    return f"cd {shlex.quote(snapshot.worktree_path)} && edgebase resume {shlex.quote(snapshot.id)}"
