from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Iterable

from .context import build_context
from .git import changed_files, find_repo_root, is_git_repo
from .goal import build_goal_capsule, render_edit_delta, render_work_contract
from .graph import graph_artifact_summary, write_graph_artifacts
from .indexer import index_repo
from .store import Store


def install_git_hook(root: str | Path) -> Path:
    repo_root = find_repo_root(root)
    if not is_git_repo(repo_root):
        raise RuntimeError(f"Not a git repository: {repo_root}")
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    marker = "# edgebase post-commit hook"
    command = f"\n{marker}\n{hook_command(repo_root, 'git-post-commit')}\n"
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
                "command": hook_command(repo_root, "claude-session-start"),
                "timeout": 30,
            }
        ]
    }
    append_unique(hooks["SessionStart"], session_hook)
    hooks.setdefault("UserPromptSubmit", [])
    user_prompt_hook = {
        "hooks": [
            {
                "type": "command",
                "command": hook_command(repo_root, "claude-user-prompt-submit"),
                "timeout": 30,
            }
        ]
    }
    append_unique(hooks["UserPromptSubmit"], user_prompt_hook)
    pre_tool = hooks.setdefault("PreToolUse", [])
    for matcher in ("Write", "Edit", "MultiEdit"):
        append_unique(
            pre_tool,
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command(repo_root, "claude-pre-tool-use"),
                        "timeout": 30,
                    }
                ],
            },
        )
    post_tool = hooks.setdefault("PostToolUse", [])
    for matcher in ("Write", "Edit", "MultiEdit"):
        append_unique(
            post_tool,
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command(repo_root, "claude-post-tool-use"),
                        "async": True,
                        "timeout": 60,
                    }
                ],
            },
        )
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return settings_path


def hook_command(repo_root: Path, hook_name: str) -> str:
    return shlex.join([sys.executable, "-m", "edgebase", "hooks", hook_name, "--root", str(repo_root)])


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
        for event_name in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"):
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


def append_optional_section(text: str, section: str) -> str:
    return text + ("\n\n" + section if section else "")


def safe_graph_artifact_summary(
    root: str | Path,
    task: str | None,
    changed: list[str],
    selected_files: Iterable[str] | None,
) -> str:
    try:
        artifacts = write_graph_artifacts(
            root,
            task=task,
            changed_files=changed,
            selected_files=selected_files,
        )
    except Exception:
        return ""
    return graph_artifact_summary(artifacts)


def handle_git_post_commit(root: str | Path) -> int:
    result = index_repo(root)
    print(f"edgebase indexed {result.files} files at {result.commit_sha}")
    return 0


def handle_claude_session_start(root: str | Path) -> int:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    if not store.exists():
        result = index_repo(repo_root)
        msg = f"Edgebase initialized graph with {result.files} files. Prompt-time context is enabled."
    else:
        stats = store.stats()
        changed = changed_files(repo_root)
        msg = (
            f"Edgebase graph available: {stats['files']} files, {stats['symbols']} symbols, "
            f"{stats['edges']} edges. Changed files: {len(changed)}."
        )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
    return 0


def handle_claude_user_prompt_submit(root: str | Path) -> int:
    payload = read_json_stdin()
    prompt = extract_prompt(payload)
    if not should_inject_prompt_context(prompt):
        return 0
    repo_root = find_repo_root(root)
    try:
        store = Store(repo_root)
        if not store.exists():
            index_repo(repo_root)
        changed = changed_files(repo_root)
        capsule = build_context(repo_root, prompt, changed, budget=1100)
        graph_summary = safe_graph_artifact_summary(repo_root, prompt, changed, capsule.selected_files)
        msg = (
            "Edgebase automatic context for this coding prompt. "
            "Use this source-backed capsule as the first read set before broad exploration or edits.\n\n"
            f"{append_optional_section(capsule.markdown, graph_summary)}"
        )
    except Exception as exc:
        msg = f"Edgebase automatic context was unavailable: {exc}. Continue with normal repository exploration."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
    return 0


def handle_claude_pre_tool_use(root: str | Path) -> int:
    payload = read_json_stdin()
    repo_root = find_repo_root(root)
    touched = extract_tool_paths(payload, repo_root)
    goal = extract_goal(payload) or "pending edit"
    try:
        capsule = build_goal_capsule(repo_root, goal, touched, budget=700)
        graph_summary = graph_artifact_summary(capsule.graph_artifacts)
        msg = (
            "Edgebase pre-edit Work Contract. Use this contract before writing files.\n\n"
            f"{append_optional_section(render_work_contract(capsule.contract), graph_summary)}"
        )
    except Exception as exc:
        msg = f"Edgebase pre-edit Work Contract was unavailable: {exc}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))
    return 0


def handle_claude_post_tool_use(root: str | Path) -> int:
    payload = read_json_stdin()
    repo_root = find_repo_root(root)
    touched = extract_tool_paths(payload, repo_root)
    if touched:
        index_repo(repo_root, touched, reset=False)
        task = extract_goal(payload) or "recent edit"
        delta = render_edit_delta(repo_root, str(task), touched, budget=700)
        graph_summary = safe_graph_artifact_summary(repo_root, str(task), touched, None)
        msg = (
            f"Edgebase refreshed {len(touched)} edited file(s).\n\n"
            f"{append_optional_section(delta, graph_summary)}"
        )
    else:
        msg = "Edgebase hook ran but found no edited file path in the tool input."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0


def extract_goal(payload: dict[str, Any]) -> str:
    prompt = extract_prompt(payload)
    if prompt:
        return prompt
    for key in ("goal", "task", "description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    for key in ("goal", "task", "description"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_prompt(payload: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def should_inject_prompt_context(prompt: str) -> bool:
    text = " ".join(prompt.lower().split())
    if not text:
        return False
    trivial = {
        "ok",
        "okay",
        "yes",
        "no",
        "thanks",
        "thank you",
        "continue",
        "go on",
        "sounds good",
    }
    if text in trivial:
        return False
    hints = (
        "add",
        "build",
        "change",
        "debug",
        "error",
        "fail",
        "fix",
        "implement",
        "install",
        "migrate",
        "refactor",
        "remove",
        "rename",
        "review",
        "test",
        "update",
        "where",
        "why",
    )
    return any(hint in text for hint in hints) or len(text.split()) >= 6


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
