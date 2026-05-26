from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import stale_files
from .git import changed_files as git_changed_files
from .git import current_commit, find_repo_root
from .goal import GoalCapsule, build_goal_capsule, build_patch_passport
from .indexer import index_repo
from .store import Store


PREFLIGHT_TTL_SECONDS = 45 * 60
OFF_VALUES = {"0", "false", "no", "off", "disable", "disabled"}


def preflight_disabled() -> bool:
    return os.environ.get("EDGEBASE_PREFLIGHT", "").strip().lower() in OFF_VALUES


def preflight_state_path(root: str | Path) -> Path:
    return find_repo_root(root) / ".edgebase" / "preflight.json"


def preflight_markdown_path(root: str | Path) -> Path:
    return find_repo_root(root) / ".edgebase" / "preflight.md"


def prepare_goal_capsule(
    root: str | Path,
    goal: str,
    changed_files: list[str] | None = None,
    budget: int = 1200,
    source: str = "manual",
) -> GoalCapsule:
    repo_root = find_repo_root(root)
    capsule = build_goal_capsule(repo_root, goal, changed_files or [], budget)
    markdown_path = preflight_markdown_path(repo_root)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(markdown_path, capsule.markdown + "\n")
    state = {
        "schema_version": 1,
        "created_at": time.time(),
        "created_at_iso": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": PREFLIGHT_TTL_SECONDS,
        "source": source,
        "goal": capsule.contract.goal,
        "repo_root": str(repo_root),
        "repo_commit": current_commit(repo_root),
        "worktree_fingerprint": capsule.contract.worktree_fingerprint,
        "worktree_changed_files": git_changed_files(repo_root),
        "selected_files": capsule.contract.selected_files,
        "must_read": capsule.contract.must_read,
        "blast_radius": capsule.contract.blast_radius,
        "test_plan": capsule.contract.test_plan,
        "stale_files": current_stale_files(repo_root),
        "graph_artifacts": capsule.graph_artifacts,
        "capsule_path": str(markdown_path),
    }
    write_preflight_state(repo_root, state)
    return capsule


def load_preflight_state(root: str | Path) -> dict[str, Any] | None:
    path = preflight_state_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_preflight_state(root: str | Path, state: dict[str, Any]) -> Path:
    path = preflight_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    return path


def preflight_status(root: str | Path) -> dict[str, Any]:
    if preflight_disabled():
        return {"fresh": True, "reason": "disabled by EDGEBASE_PREFLIGHT", "disabled": True}
    repo_root = find_repo_root(root)
    state = load_preflight_state(repo_root)
    if not state:
        return {"fresh": False, "reason": "no Goal Capsule has been recorded"}
    return evaluate_state_freshness(repo_root, state)


def ensure_fresh_preflight(
    root: str | Path,
    touched_files: list[str] | None = None,
    budget: int = 900,
) -> tuple[bool, dict[str, Any]]:
    repo_root = find_repo_root(root)
    state = load_preflight_state(repo_root)
    if not state:
        return False, {"fresh": False, "reason": "no fresh Edgebase Goal Capsule exists"}
    status = evaluate_state_freshness(repo_root, state)
    if status.get("fresh"):
        return True, status
    goal = str(state.get("goal") or "").strip()
    if not goal:
        return False, status
    changed = sorted(set(str(path) for path in touched_files or []) | set(git_changed_files(repo_root)))
    try:
        prepare_goal_capsule(repo_root, goal, changed, budget, source="preflight-auto-refresh")
    except Exception as exc:
        return False, {"fresh": False, "reason": f"auto-refresh failed: {exc}"}
    refreshed = preflight_status(repo_root)
    return bool(refreshed.get("fresh")), refreshed


def update_after_edit(
    root: str | Path,
    touched_files: list[str],
    goal: str | None = None,
    budget: int = 900,
) -> GoalCapsule | None:
    repo_root = find_repo_root(root)
    if touched_files:
        index_repo(repo_root, touched_files, reset=False)
    state = load_preflight_state(repo_root) or {}
    active_goal = " ".join((goal or str(state.get("goal") or "recent edit")).split()).strip()
    if not active_goal:
        return None
    return prepare_goal_capsule(
        repo_root,
        active_goal,
        sorted(set(touched_files) | set(git_changed_files(repo_root))),
        budget,
        source="post-edit-refresh",
    )


def save_context_checkpoint(root: str | Path, reason: str = "pre-compact") -> Path:
    repo_root = find_repo_root(root)
    state = load_preflight_state(repo_root) or {}
    goal = str(state.get("goal") or "session checkpoint")
    capsule_path = Path(str(state.get("capsule_path") or ""))
    capsule_text = capsule_path.read_text(encoding="utf-8") if capsule_path.exists() else ""
    checkpoint = [
        "# Edgebase Context Checkpoint",
        "",
        f"Reason: {reason}",
        f"Saved: {datetime.now(timezone.utc).isoformat()}",
        f"Repo commit: {current_commit(repo_root)}",
        f"Goal: {goal}",
        "",
        capsule_text.strip() or "No recorded Goal Capsule was available.",
    ]
    path = repo_root / ".edgebase" / "checkpoints" / "latest.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, "\n".join(checkpoint).rstrip() + "\n")
    return path


def save_patch_passport(root: str | Path, reason: str = "session-end") -> dict[str, str]:
    repo_root = find_repo_root(root)
    state = load_preflight_state(repo_root) or {}
    goal = str(state.get("goal") or "session patch")
    passport = build_patch_passport(repo_root, goal, [], git_changed_files(repo_root), budget=1200)
    directory = repo_root / ".edgebase" / "passports"
    directory.mkdir(parents=True, exist_ok=True)
    md_path = directory / "latest.md"
    json_path = directory / "latest.json"
    write_text_atomic(md_path, passport.markdown + "\n")
    payload = {
        "schema_version": 1,
        "reason": reason,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "goal": passport.goal,
        "files_changed": passport.files_changed,
        "tests_run": passport.tests_run,
        "required_checks": passport.required_checks,
        "markdown": str(md_path),
    }
    write_text_atomic(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {"markdown": str(md_path), "json": str(json_path)}


def evaluate_state_freshness(repo_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    created_at = float(state.get("created_at") or 0)
    ttl = int(state.get("ttl_seconds") or PREFLIGHT_TTL_SECONDS)
    if created_at <= 0:
        return {"fresh": False, "reason": "preflight state is missing a timestamp"}
    age = now - created_at
    if age > ttl:
        return {"fresh": False, "reason": "Goal Capsule expired", "age_seconds": int(age)}
    if str(state.get("repo_commit") or "") != current_commit(repo_root):
        return {"fresh": False, "reason": "HEAD changed since Goal Capsule was recorded"}
    current_changed = git_changed_files(repo_root)
    recorded_changed = [str(path) for path in state.get("worktree_changed_files") or []]
    if current_changed != recorded_changed:
        return {
            "fresh": False,
            "reason": "working tree changed since Goal Capsule was recorded",
            "changed_files": current_changed,
        }
    stale = current_stale_files(repo_root)
    if stale:
        return {"fresh": False, "reason": "index has stale files", "stale_files": stale}
    return {
        "fresh": True,
        "reason": "Goal Capsule is fresh",
        "age_seconds": int(age),
        "goal": state.get("goal"),
        "selected_files": state.get("selected_files") or [],
    }


def current_stale_files(repo_root: Path) -> list[str]:
    store = Store(repo_root)
    if not store.exists():
        return []
    try:
        return stale_files(repo_root, store.load_graph()["files"])
    except Exception:
        return []


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
