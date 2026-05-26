from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import stale_files
from .git import changed_files as git_changed_files
from .git import current_commit, find_repo_root
from .goal import build_patch_passport
from .preflight import load_preflight_state, preflight_status, write_text_atomic
from .store import Store


STATE_VERSION = 1
ACTIVE_GOAL_REL = Path(".edgebase") / "session" / "active-goal.json"


def active_goal_path(root: str | Path) -> Path:
    return find_repo_root(root) / ACTIVE_GOAL_REL


def load_active_goal(root: str | Path) -> dict[str, Any] | None:
    path = active_goal_path(root)
    if not path.exists():
        return load_preflight_state(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return load_preflight_state(root)
    return data if isinstance(data, dict) else load_preflight_state(root)


def status_payload(root: str | Path) -> dict[str, Any]:
    repo_root = find_repo_root(root)
    state = load_active_goal(repo_root)
    store = Store(repo_root)
    graph = store.load_graph() if store.exists() else {"files": []}
    stale = stale_files(repo_root, graph["files"]) if store.exists() else []
    changed = git_changed_files(repo_root)
    required = list((state.get("test_plan") if isinstance(state, dict) else []) or [])
    recorded_tests = list((state.get("recorded_tests") if isinstance(state, dict) else []) or [])
    blast_radius = list((state.get("blast_radius") if isinstance(state, dict) else []) or [])
    blast_set = set(str(path) for path in blast_radius)
    preflight = preflight_status(repo_root)
    latest_passport = latest_file(repo_root / ".edgebase" / "passports", "latest.md")
    latest_checkpoint = latest_file(repo_root / ".edgebase" / "checkpoints", "latest.md")
    return {
        "repo": str(repo_root),
        "active_goal": state.get("goal") if isinstance(state, dict) else None,
        "state_fresh": bool(preflight.get("fresh")) and not stale,
        "freshness_reason": preflight.get("reason"),
        "changed_files": changed,
        "stale_files": stale,
        "blast_radius": blast_radius,
        "blast_radius_drift": [path for path in changed if blast_set and path not in blast_set],
        "elevated_tests": required,
        "required_checks_unrecorded": unrecorded_checks(required, recorded_tests),
        "latest_passport": str(latest_passport) if latest_passport else None,
        "latest_checkpoint": str(latest_checkpoint) if latest_checkpoint else None,
    }


def render_status(payload: dict[str, Any]) -> str:
    lines = ["# Edgebase Status", ""]
    lines.append(f"Active goal: {payload.get('active_goal') or 'none'}")
    lines.append(f"State fresh: {str(payload.get('state_fresh')).lower()}")
    if payload.get("freshness_reason"):
        lines.append(f"Freshness reason: {payload['freshness_reason']}")
    lines.append("")
    for title, key in (
        ("Changed files", "changed_files"),
        ("Stale files", "stale_files"),
        ("Blast radius", "blast_radius"),
        ("Blast radius drift", "blast_radius_drift"),
        ("Elevated tests", "elevated_tests"),
        ("Required checks unrecorded", "required_checks_unrecorded"),
    ):
        lines.append(f"{title}:")
        values = list(payload.get(key) or [])
        lines.extend(f"- {value}" for value in values) if values else lines.append("- none")
        lines.append("")
    lines.append(f"Latest Patch Passport: {payload.get('latest_passport') or 'none'}")
    lines.append(f"Latest checkpoint: {payload.get('latest_checkpoint') or 'none'}")
    return "\n".join(lines)


def write_finish_passport(
    root: str | Path,
    goal: str,
    tests: list[str],
    changed_files: list[str] | None = None,
    budget: int = 1200,
) -> dict[str, Any]:
    repo_root = find_repo_root(root)
    passport = build_patch_passport(repo_root, goal, tests, changed_files, budget)
    passports = repo_root / ".edgebase" / "passports"
    passports.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "created_at_iso": iso_timestamp(time.time()),
        "goal": passport.goal,
        "files_changed": passport.files_changed,
        "tests_run": passport.tests_run,
        "required_checks": passport.required_checks,
        "missing_tests": unrecorded_checks(passport.required_checks, passport.tests_run),
        "passport_markdown": passport.markdown,
    }
    write_json(passports / "latest.json", payload)
    write_text_atomic(passports / "latest.md", passport.markdown + "\n")
    state = load_active_goal(repo_root)
    if isinstance(state, dict):
        state["recorded_tests"] = passport.tests_run
        state["latest_passport"] = str(passports / "latest.md")
        state["latest_passport_json"] = str(passports / "latest.json")
        state["updated_at_iso"] = iso_timestamp(time.time())
        write_json(active_goal_path(repo_root), state)
    return payload


def latest_file(directory: Path, name: str) -> Path | None:
    path = directory / name
    return path if path.exists() else None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def unrecorded_checks(required: list[str], tests: list[str]) -> list[str]:
    recorded = {test_command(test) for test in tests}
    return [check for check in required if check not in recorded]


def test_command(test: str) -> str:
    if ":" not in test:
        return test.strip()
    command, _status = test.rsplit(":", 1)
    return command.strip()


def iso_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
