from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .context import build_context
from .git import changed_files, find_repo_root, is_git_repo
from .indexer import index_repo
from .store import Store


def install_git_hook(root: str | Path) -> Path:
    repo_root = find_repo_root(root)
    if not is_git_repo(repo_root):
        raise RuntimeError(f"Not a git repository: {repo_root}")
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    marker = "# edgebase post-commit hook"
    command = f'\n{marker}\n"{sys.executable}" -m edgebase hooks git-post-commit --root "{repo_root}"\n'
    existing = hook_path.read_text(encoding="utf-8") if hook_path.exists() else "#!/bin/sh\n"
    if marker not in existing:
        hook_path.write_text(existing.rstrip() + command, encoding="utf-8")
        hook_path.chmod(0o755)
    return hook_path


def uninstall_git_hook(root: str | Path) -> Path:
    repo_root = find_repo_root(root)
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        return hook_path
    lines = hook_path.read_text(encoding="utf-8").splitlines()
    filtered: list[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == "# edgebase post-commit hook":
            skip_next = True
            continue
        filtered.append(line)
    hook_path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
    return hook_path


def install_claude_hooks(root: str | Path) -> Path:
    repo_root = Path(root).resolve()
    settings_path = repo_root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise RuntimeError(f"Refusing to overwrite invalid JSON: {settings_path}")
    hooks = settings.setdefault("hooks", {})
    hooks.setdefault("SessionStart", [])
    session_hook = {
        "hooks": [
            {
                "type": "command",
                "command": f'"{sys.executable}" -m edgebase hooks claude-session-start --root "{repo_root}"',
                "timeout": 30,
            }
        ]
    }
    append_unique(hooks["SessionStart"], session_hook)
    post_tool = hooks.setdefault("PostToolUse", [])
    for matcher in ("Write", "Edit", "MultiEdit"):
        append_unique(
            post_tool,
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": f'"{sys.executable}" -m edgebase hooks claude-post-tool-use --root "{repo_root}"',
                        "async": True,
                        "timeout": 60,
                    }
                ],
            },
        )
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return settings_path


def uninstall_claude_hooks(root: str | Path) -> Path:
    repo_root = Path(root).resolve()
    settings_path = repo_root / ".claude" / "settings.json"
    if not settings_path.exists():
        return settings_path
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Refusing to edit invalid JSON: {settings_path}") from exc
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event_name in ("SessionStart", "PostToolUse"):
            entries = hooks.get(event_name)
            if isinstance(entries, list):
                hooks[event_name] = [entry for entry in entries if not hook_entry_runs_edgebase(entry)]
        for key in list(hooks):
            if hooks.get(key) == []:
                del hooks[key]
    if hooks == {}:
        settings.pop("hooks", None)
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return settings_path


def hook_entry_runs_edgebase(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if isinstance(hook, dict) and "edgebase hooks" in str(hook.get("command", "")):
            return True
    return False


def append_unique(items: list[object], value: object) -> None:
    if value not in items:
        items.append(value)


def handle_git_post_commit(root: str | Path) -> int:
    result = index_repo(root)
    print(f"edgebase indexed {result.files} files at {result.commit_sha}")
    return 0


def handle_claude_session_start(root: str | Path) -> int:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    if not store.exists():
        result = index_repo(repo_root)
        msg = f"Edgebase initialized graph with {result.files} files. Use edgebase_context for structural context."
    else:
        stats = store.stats()
        changed = changed_files(repo_root)
        msg = (
            f"Edgebase graph available: {stats['files']} files, {stats['symbols']} symbols, "
            f"{stats['edges']} edges. Changed files: {len(changed)}."
        )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
    return 0


def handle_claude_post_tool_use(root: str | Path) -> int:
    payload = read_json_stdin()
    repo_root = find_repo_root(root)
    touched = extract_tool_paths(payload, repo_root)
    if touched:
        index_repo(repo_root, touched, reset=False)
        task = payload.get("prompt") or "recent edit"
        capsule = build_context(repo_root, str(task), touched, budget=700, auto_index=False)
        msg = (
            f"Edgebase refreshed {len(touched)} edited file(s). "
            f"Selected context: {', '.join(capsule.selected_files[:4]) or 'none'}."
        )
    else:
        msg = "Edgebase hook ran but found no edited file path in the tool input."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0


def read_json_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_tool_paths(payload: dict[str, Any], root: str | Path | None = None) -> list[str]:
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    candidates: list[str] = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
                candidates.append(edit["file_path"])
    base = Path(root or os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
    rels: list[str] = []
    for candidate in candidates:
        path = Path(candidate)
        try:
            rels.append(path.resolve().relative_to(base).as_posix() if path.is_absolute() else path.as_posix())
        except ValueError:
            rels.append(path.name)
    return sorted(set(rels))
