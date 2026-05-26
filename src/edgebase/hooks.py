from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from .commands import shell_join
from .git import changed_files, find_repo_root, is_git_repo
from .goal import render_edit_delta
from .graph import graph_artifact_summary, write_graph_artifacts
from .indexer import index_repo
from .preflight import (
    ensure_fresh_preflight,
    prepare_goal_capsule,
    preflight_disabled,
    save_context_checkpoint,
    save_patch_passport,
    update_after_edit,
)
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


def hook_entry(repo_root: Path, hook_name: str, matcher: str | None = None, timeout: int = 30, asynchronous: bool = False) -> dict[str, object]:
    command: dict[str, object] = {"type": "command", "command": hook_command(repo_root, hook_name), "timeout": timeout}
    if asynchronous:
        command["async"] = True
    entry: dict[str, object] = {"hooks": [command]}
    if matcher is not None:
        entry["matcher"] = matcher
    return entry


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
    append_unique(hooks.setdefault("SessionStart", []), hook_entry(repo_root, "claude-session-start"))
    append_unique(hooks.setdefault("UserPromptSubmit", []), hook_entry(repo_root, "claude-user-prompt-submit"))
    pre_tool = hooks.setdefault("PreToolUse", [])
    post_tool = hooks.setdefault("PostToolUse", [])
    for matcher in ("Write", "Edit", "MultiEdit"):
        append_unique(pre_tool, hook_entry(repo_root, "claude-pre-tool-use", matcher=matcher))
        append_unique(post_tool, hook_entry(repo_root, "claude-post-tool-use", matcher=matcher, timeout=60, asynchronous=True))
    append_unique(hooks.setdefault("PreCompact", []), hook_entry(repo_root, "claude-pre-compact"))
    append_unique(hooks.setdefault("SessionEnd", []), hook_entry(repo_root, "claude-session-end"))
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return settings_path


def install_codex_hooks(root: str | Path) -> Path:
    repo_root = Path(root).resolve()
    hooks_path = repo_root / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if hooks_path.exists():
        try:
            loaded = json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Refusing to overwrite invalid JSON: {hooks_path}") from exc
        if isinstance(loaded, dict):
            payload = loaded
    hooks = codex_hooks_without_edgebase(payload.get("hooks"))
    for event_name, entries in codex_hook_entries(repo_root).items():
        event_entries = hooks.setdefault(event_name, [])
        for entry in entries:
            append_unique(event_entries, entry)
    payload["hooks"] = hooks
    hooks_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hooks_path


def codex_hook_entries(repo_root: Path) -> dict[str, list[dict[str, object]]]:
    return {
        "SessionStart": [
            codex_hook_entry(
                repo_root,
                "codex-session-start",
                timeout=30,
                status_message="Loading Edgebase context",
            )
        ],
        "UserPromptSubmit": [
            codex_hook_entry(
                repo_root,
                "codex-user-prompt-submit",
                timeout=60,
                status_message="Recording Edgebase Goal Capsule",
            )
        ],
        "PreToolUse": [
            codex_hook_entry(
                repo_root,
                "codex-pre-tool-use",
                timeout=30,
                status_message="Checking Edgebase preflight",
            )
        ],
        "PostToolUse": [
            codex_hook_entry(
                repo_root,
                "codex-post-tool-use",
                timeout=60,
                status_message="Refreshing Edgebase context",
            )
        ],
        "PreCompact": [
            codex_hook_entry(
                repo_root,
                "codex-pre-compact",
                timeout=30,
                status_message="Saving Edgebase checkpoint",
            )
        ],
        "Stop": [
            codex_hook_entry(
                repo_root,
                "codex-stop",
                timeout=30,
                status_message="Saving Edgebase Patch Passport",
            )
        ],
    }


def codex_hook_entry(
    repo_root: Path,
    hook_name: str,
    matcher: str | None = None,
    timeout: int = 30,
    status_message: str | None = None,
) -> dict[str, object]:
    command: dict[str, object] = {
        "type": "command",
        "command": hook_command(repo_root, hook_name),
        "timeout": timeout,
    }
    if status_message:
        command["statusMessage"] = status_message
    entry: dict[str, object] = {"hooks": [command]}
    if matcher is not None:
        entry["matcher"] = matcher
    return entry


def codex_hooks_without_edgebase(existing_hooks: object) -> dict[str, list[dict[str, object]]]:
    if isinstance(existing_hooks, dict):
        normalized: dict[str, list[dict[str, object]]] = {}
        for event_name, entries in existing_hooks.items():
            if not isinstance(event_name, str) or not isinstance(entries, list):
                continue
            kept = [entry for entry in entries if isinstance(entry, dict) and not codex_hook_runs_edgebase(entry)]
            if kept:
                normalized[event_name] = kept
        return normalized
    if isinstance(existing_hooks, list):
        normalized: dict[str, list[dict[str, object]]] = {}
        for entry in existing_hooks:
            converted = convert_legacy_codex_hook(entry)
            if converted is None or codex_hook_runs_edgebase(converted[1]):
                continue
            event_entries = normalized.setdefault(converted[0], [])
            append_unique(event_entries, converted[1])
        return normalized
    return {}


def convert_legacy_codex_hook(entry: object) -> tuple[str, dict[str, object]] | None:
    if not isinstance(entry, dict):
        return None
    event = entry.get("event")
    command_text = entry.get("command")
    if not isinstance(event, str) or not isinstance(command_text, str):
        return None
    command: dict[str, object] = {"type": "command", "command": command_text}
    timeout = entry.get("timeout")
    if isinstance(timeout, int):
        command["timeout"] = timeout
    status_message = entry.get("statusMessage") or entry.get("status_message")
    if isinstance(status_message, str):
        command["statusMessage"] = status_message
    group: dict[str, object] = {"hooks": [command]}
    matcher = entry.get("matcher")
    if isinstance(matcher, str):
        group["matcher"] = matcher
    return event, group


def codex_hook_runs_edgebase(entry: object) -> bool:
    if isinstance(entry, dict):
        return any(codex_hook_runs_edgebase(value) for value in entry.values())
    if isinstance(entry, list):
        return any(codex_hook_runs_edgebase(value) for value in entry)
    return isinstance(entry, str) and "edgebase hooks codex-" in entry


def hook_command(repo_root: Path, hook_name: str) -> str:
    return shell_join([sys.executable, "-m", "edgebase", "hooks", hook_name, "--root", str(repo_root)])


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
        for event_name in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "SessionEnd"):
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


def uninstall_codex_hooks(root: str | Path) -> Path:
    hooks_path = Path(root).resolve() / ".codex" / "hooks.json"
    if not hooks_path.exists():
        return hooks_path
    try:
        payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Refusing to edit invalid JSON: {hooks_path}") from exc
    if not isinstance(payload, dict):
        hooks_path.unlink()
        return hooks_path
    hooks = payload.get("hooks")
    if isinstance(hooks, dict):
        cleaned = codex_hooks_without_edgebase(hooks)
        if cleaned:
            payload["hooks"] = cleaned
        else:
            payload.pop("hooks", None)
    elif isinstance(hooks, list):
        cleaned = codex_hooks_without_edgebase(hooks)
        if cleaned:
            payload["hooks"] = cleaned
        else:
            payload.pop("hooks", None)
    if not payload:
        hooks_path.unlink()
    else:
        hooks_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hooks_path


def hook_entry_runs_edgebase(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(isinstance(hook, dict) and "edgebase hooks" in str(hook.get("command", "")) for hook in hooks)


def append_unique(items: list[object], value: object) -> None:
    if value not in items:
        items.append(value)


def append_optional_section(text: str, section: str) -> str:
    return text + ("\n\n" + section if section else "")


def safe_graph_artifact_summary(root: str | Path, task: str | None, changed: list[str], selected_files: Iterable[str] | None) -> str:
    try:
        artifacts = write_graph_artifacts(root, task=task, changed_files=changed, selected_files=selected_files)
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
        msg = f"Edgebase graph available: {stats['files']} files, {stats['symbols']} symbols, {stats['edges']} edges. Changed files: {len(changed)}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
    return 0


def handle_claude_user_prompt_submit(root: str | Path) -> int:
    payload = read_json_stdin()
    prompt = extract_prompt(payload)
    if not should_inject_prompt_context(prompt):
        return 0
    repo_root = find_repo_root(root)
    try:
        changed = changed_files(repo_root)
        capsule = prepare_goal_capsule(repo_root, prompt, changed, budget=1100, source="claude-user-prompt-submit")
        graph_summary = graph_artifact_summary(capsule.graph_artifacts)
        msg = "Edgebase Goal Capsule was recorded for this coding prompt. Use it as the planning brief before broad exploration or edits.\n\n" + append_optional_section(capsule.markdown, graph_summary)
    except Exception as exc:
        msg = f"Edgebase Goal Capsule was unavailable: {exc}. Continue with normal repository exploration."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
    return 0


def handle_claude_pre_tool_use(root: str | Path) -> int:
    payload = read_json_stdin()
    if preflight_disabled() or not is_edit_tool(payload):
        return 0
    repo_root = find_repo_root(root)
    touched = extract_tool_paths(payload, repo_root)
    fresh, status = ensure_fresh_preflight(repo_root, touched, budget=900)
    if not fresh:
        print(deny_pre_tool_payload("PreToolUse", status.get("reason") or "Goal Capsule is stale"))
    return 0


def handle_claude_post_tool_use(root: str | Path) -> int:
    payload = read_json_stdin()
    repo_root = find_repo_root(root)
    touched = extract_tool_paths(payload, repo_root)
    if touched:
        task = extract_goal(payload) or "recent edit"
        update_after_edit(repo_root, touched, task, budget=900)
        delta = render_edit_delta(repo_root, str(task), touched, budget=700)
        graph_summary = safe_graph_artifact_summary(repo_root, str(task), touched, None)
        msg = f"Edgebase refreshed {len(touched)} edited file(s).\n\n" + append_optional_section(delta, graph_summary)
    else:
        msg = "Edgebase hook ran but found no edited file path in the tool input."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0


def handle_claude_pre_compact(root: str | Path) -> int:
    path = save_context_checkpoint(root, "claude-pre-compact")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": f"Edgebase saved a context checkpoint before compaction: {path}"}}))
    return 0


def handle_claude_session_end(root: str | Path) -> int:
    paths = save_patch_passport(root, "claude-session-end")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionEnd", "additionalContext": f"Edgebase saved a patch passport: {paths['markdown']}"}}))
    return 0


def handle_codex_session_start(root: str | Path) -> int:
    return handle_claude_session_start(root)


def handle_codex_user_prompt_submit(root: str | Path) -> int:
    return handle_claude_user_prompt_submit(root)


def handle_codex_pre_tool_use(root: str | Path) -> int:
    return handle_claude_pre_tool_use(root)


def handle_codex_post_tool_use(root: str | Path) -> int:
    return handle_claude_post_tool_use(root)


def handle_codex_pre_compact(root: str | Path) -> int:
    path = save_context_checkpoint(root, "codex-pre-compact")
    print(json.dumps({"event": "PreCompact", "additionalContext": f"Edgebase saved checkpoint: {path}"}))
    return 0


def handle_codex_stop(root: str | Path) -> int:
    paths = save_patch_passport(root, "codex-stop")
    print(json.dumps({"event": "Stop", "additionalContext": f"Edgebase saved patch passport: {paths['markdown']}"}))
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
    if text in {"ok", "okay", "yes", "no", "thanks", "thank you", "continue", "go on", "sounds good"}:
        return False
    hints = ("add", "build", "change", "debug", "error", "fail", "fix", "implement", "install", "migrate", "refactor", "remove", "rename", "review", "test", "update", "where", "why")
    return any(hint in text for hint in hints) or len(text.split()) >= 6


def is_edit_tool(payload: dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "").lower()
    if tool_name:
        return tool_name in {"write", "edit", "multiedit", "apply_patch"}
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    return any(key in tool_input for key in ("file_path", "path", "edits"))


def deny_pre_tool_payload(event_name: str, reason: object) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "Edgebase blocked this edit because no fresh Goal Capsule exists. "
                    f"Reason: {reason}. Use `/edgebase-goal <goal>`, `/edgebase-preflight-refresh <goal>`, or `/goal <goal>`, "
                    "or submit a coding prompt so Edgebase can inject one automatically. "
                    "Set EDGEBASE_PREFLIGHT=off only for emergency bypass."
                ),
            }
        }
    )


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
