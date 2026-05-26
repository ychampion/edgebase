from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .hooks import install_claude_hooks, install_git_hook, uninstall_claude_hooks, uninstall_git_hook
from .indexer import index_repo


ALL_AGENTS = ("claude", "codex", "cursor", "gemini", "opencode", "windsurf")
AGENT_DOC_START = "<!-- EDGEBASE:START -->"
AGENT_DOC_END = "<!-- EDGEBASE:END -->"


@dataclass(frozen=True)
class SetupResult:
    path: Path
    action: str
    detail: str


def setup_repo(
    root: str | Path,
    agents: list[str] | None = None,
    scope: str = "project",
    install_hooks: bool = True,
    write_agents_md: bool = True,
    command: str | None = None,
) -> list[SetupResult]:
    repo_root = Path(root).resolve()
    selected = normalize_agents(agents)
    results: list[SetupResult] = []
    index = index_repo(repo_root)
    results.append(
        SetupResult(repo_root / ".edgebase" / "index.sqlite3", "indexed", f"{index.files} files")
    )

    if write_agents_md:
        results.append(write_agent_docs(repo_root))

    if "claude" in selected:
        results.extend(setup_claude(repo_root, scope, install_hooks, command))
    if "codex" in selected:
        results.extend(setup_codex(repo_root, scope, command))
    if "cursor" in selected:
        results.extend(setup_cursor(repo_root, scope, command))
    if "gemini" in selected:
        results.extend(setup_gemini(repo_root, scope, command))
    if "opencode" in selected:
        results.extend(setup_opencode(repo_root, scope, command))
    if "windsurf" in selected:
        results.extend(setup_windsurf(repo_root, scope, command))

    if install_hooks:
        try:
            path = install_git_hook(repo_root)
        except RuntimeError as exc:
            results.append(SetupResult(repo_root, "skipped", str(exc)))
        else:
            results.append(SetupResult(path, "updated", "git post-commit refresh hook"))
    return results


def disable_repo(
    root: str | Path,
    agents: list[str] | None = None,
    scope: str = "project",
    remove_hooks: bool = True,
    remove_agent_docs: bool = True,
) -> list[SetupResult]:
    repo_root = Path(root).resolve()
    selected = normalize_agents(agents)
    results: list[SetupResult] = []
    if "claude" in selected:
        results.extend(disable_claude(repo_root, scope, remove_hooks))
    if "codex" in selected:
        results.extend(disable_codex(repo_root, scope))
    if "cursor" in selected:
        results.extend(disable_cursor(repo_root, scope))
    if "gemini" in selected:
        results.extend(disable_gemini(repo_root, scope))
    if "opencode" in selected:
        results.extend(disable_opencode(repo_root, scope))
    if "windsurf" in selected:
        results.extend(disable_windsurf(scope))
    if remove_hooks:
        results.append(SetupResult(uninstall_git_hook(repo_root), "updated", "removed git post-commit refresh hook"))
    if remove_agent_docs:
        results.append(remove_agent_docs_block(repo_root))
    return results


def normalize_agents(agents: list[str] | None) -> set[str]:
    if not agents:
        return set(ALL_AGENTS)
    normalized: set[str] = set()
    for item in agents:
        for part in item.split(","):
            name = part.strip().lower()
            if name == "all":
                normalized.update(ALL_AGENTS)
            elif name:
                if name not in ALL_AGENTS:
                    raise ValueError(f"Unknown agent `{name}`. Supported: {', '.join(ALL_AGENTS)}")
                normalized.add(name)
    return normalized


def stdio_config(repo_root: Path, command: str | None = None) -> dict[str, object]:
    executable, prefix = command_parts(command)
    return {"command": executable, "args": [*prefix, "mcp", "--root", str(repo_root)], "env": {}}


def command_parts(command: str | None = None) -> tuple[str, list[str]]:
    if command:
        return command, []
    return sys.executable, ["-m", "edgebase"]


def command_array(repo_root: Path, command: str | None = None) -> list[str]:
    executable, prefix = command_parts(command)
    return [executable, *prefix, "mcp", "--root", str(repo_root)]


def write_agent_docs(repo_root: Path) -> SetupResult:
    agents_path = repo_root / "AGENTS.md"
    snippet = agent_docs_block()
    if not agents_path.exists():
        agents_path.write_text("# Agent Instructions\n\n" + snippet, encoding="utf-8")
        return SetupResult(agents_path, "created", "minimal agent instructions")
    existing = agents_path.read_text(encoding="utf-8")
    if AGENT_DOC_START in existing and AGENT_DOC_END in existing:
        updated = replace_agent_docs_block(existing, snippet)
        action = "updated"
    else:
        updated = existing.rstrip() + "\n\n" + snippet
        action = "updated"
    agents_path.write_text(updated, encoding="utf-8")
    return SetupResult(agents_path, action, "Edgebase agent instructions")


def agent_docs_block() -> str:
    return (
        f"{AGENT_DOC_START}\n"
        "## Edgebase Context\n\n"
        "Edgebase is enabled for this repository. Before broad code exploration or edits, call the MCP tool "
        "`edgebase_context` with the task and any changed files. Use it to get a small, source-backed context "
        "capsule instead of loading generated architecture summaries.\n\n"
        "Fallback when MCP tools are unavailable:\n\n"
        "```bash\n"
        "edgebase context \"<task>\" --budget 1200\n"
        "```\n\n"
        "Keep static instructions here minimal; Edgebase supplies fresh structure, symbols, tests, owners, "
        "and change-hotspot context from the local git working tree. Refresh manually with "
        "`edgebase index --changed` after edits, or disable with `edgebase disable --scope both`.\n"
        f"{AGENT_DOC_END}\n"
    )


def replace_agent_docs_block(content: str, block: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(AGENT_DOC_START)}\n.*?^{re.escape(AGENT_DOC_END)}\n?"
    )
    return pattern.sub(block, content).rstrip() + "\n"


def remove_agent_docs_block(repo_root: Path) -> SetupResult:
    agents_path = repo_root / "AGENTS.md"
    if not agents_path.exists():
        return SetupResult(agents_path, "skipped", "AGENTS.md not found")
    existing = agents_path.read_text(encoding="utf-8")
    if AGENT_DOC_START not in existing:
        return SetupResult(agents_path, "skipped", "Edgebase agent instructions not found")
    updated = replace_agent_docs_block(existing, "").strip() + "\n"
    agents_path.write_text(updated, encoding="utf-8")
    return SetupResult(agents_path, "updated", "removed Edgebase agent instructions")


def setup_claude(
    repo_root: Path, scope: str, install_hooks: bool, command: str | None
) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".mcp.json"
        merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
        results.append(SetupResult(path, "updated", "Claude Code project MCP server"))
        if install_hooks:
            hooks_path = install_claude_hooks(repo_root)
            results.append(SetupResult(hooks_path, "updated", "Claude Code freshness hooks"))
    if scope in {"global", "both"}:
        results.append(
            SetupResult(
                Path.home() / ".claude.json",
                "skipped",
                "Claude global MCP is best installed with `claude mcp add`; project .mcp.json was written instead",
            )
        )
    return results


def setup_codex(repo_root: Path, scope: str, command: str | None) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(
            SetupResult(
                path,
                "updated",
                "Codex project MCP server (use --scope global or both for current Codex CLI discovery)",
            )
        )
    if scope in {"global", "both"}:
        path = Path.home() / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(SetupResult(path, "updated", "Codex global MCP server"))
    return results


def setup_cursor(repo_root: Path, scope: str, command: str | None) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".cursor" / "mcp.json"
        merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
        results.append(SetupResult(path, "updated", "Cursor project MCP server"))
    if scope in {"global", "both"}:
        path = Path.home() / ".cursor" / "mcp.json"
        merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
        results.append(SetupResult(path, "updated", "Cursor global MCP server"))
    return results


def setup_gemini(repo_root: Path, scope: str, command: str | None) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".gemini" / "settings.json"
        merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
        results.append(SetupResult(path, "updated", "Gemini CLI project MCP server"))
    if scope in {"global", "both"}:
        path = Path.home() / ".gemini" / "settings.json"
        merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
        results.append(SetupResult(path, "updated", "Gemini CLI global MCP server"))
    return results


def setup_opencode(repo_root: Path, scope: str, command: str | None) -> list[SetupResult]:
    results: list[SetupResult] = []
    value = {
        "type": "local",
        "command": command_array(repo_root, command),
        "enabled": True,
    }
    if scope in {"project", "both"}:
        path = repo_root / ".opencode.json"
        merge_json_object(path, ("mcp",), "edgebase", value, schema="https://opencode.ai/config.json")
        results.append(SetupResult(path, "updated", "OpenCode project MCP server"))
    if scope in {"global", "both"}:
        path = Path.home() / ".opencode.json"
        merge_json_object(path, ("mcp",), "edgebase", value, schema="https://opencode.ai/config.json")
        results.append(SetupResult(path, "updated", "OpenCode global MCP server"))
    return results


def setup_windsurf(repo_root: Path, scope: str, command: str | None) -> list[SetupResult]:
    if scope not in {"global", "both"}:
        return [
            SetupResult(
                Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
                "skipped",
                "Windsurf uses a global MCP config; rerun with `--scope global` or `--scope both`",
            )
        ]
    path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    merge_mcp_json(path, "edgebase", stdio_config(repo_root, command))
    return [SetupResult(path, "updated", "Windsurf global MCP server")]


def merge_mcp_json(path: Path, name: str, config: dict[str, object]) -> None:
    merge_json_object(path, ("mcpServers",), name, config)


def remove_mcp_json(path: Path, name: str) -> bool:
    return remove_json_object(path, ("mcpServers",), name)


def merge_json_object(
    path: Path,
    container_path: tuple[str, ...],
    key: str,
    value: dict[str, object],
    schema: str | None = None,
) -> None:
    data: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
        if isinstance(loaded, dict):
            data = loaded
    if schema and "$schema" not in data:
        data["$schema"] = schema
    cursor: dict[str, object] = data
    for part in container_path:
        next_value = cursor.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise RuntimeError(f"Expected object at {'.'.join(container_path)} in {path}")
        cursor = next_value
    cursor[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def remove_json_object(path: Path, container_path: tuple[str, ...], key: str) -> bool:
    if not path.exists():
        return False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return False
    cursor: dict[str, object] = loaded
    for part in container_path:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            return False
        cursor = next_value
    if key not in cursor:
        return False
    del cursor[key]
    path.write_text(json.dumps(loaded, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def upsert_codex_toml(path: Path, repo_root: Path, command: str | None) -> None:
    executable, prefix = command_parts(command)
    args = [*prefix, "mcp", "--root", str(repo_root)]
    args_literal = ", ".join(f'"{escape_toml(arg)}"' for arg in args)
    section = (
        "[mcp_servers.edgebase]\n"
        f'command = "{escape_toml(executable)}"\n'
        f"args = [{args_literal}]\n"
        "enabled = true\n"
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(r"(?ms)^\[mcp_servers\.edgebase\]\n.*?(?=^\[|\Z)")
    if pattern.search(existing):
        updated = pattern.sub(section, existing).rstrip() + "\n"
    else:
        updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + section
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def remove_codex_toml(path: Path) -> bool:
    if not path.exists():
        return False
    existing = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?ms)^\[mcp_servers\.edgebase\]\n.*?(?=^\[|\Z)")
    updated, count = pattern.subn("", existing)
    if count == 0:
        return False
    path.write_text(updated.rstrip() + ("\n" if updated.strip() else ""), encoding="utf-8")
    return True


def disable_claude(repo_root: Path, scope: str, remove_hooks: bool) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".mcp.json"
        action = "updated" if remove_mcp_json(path, "edgebase") else "skipped"
        results.append(SetupResult(path, action, "Claude Code project MCP server removed"))
        if remove_hooks:
            hooks_path = uninstall_claude_hooks(repo_root)
            results.append(SetupResult(hooks_path, "updated", "removed Claude Code freshness hooks"))
    if scope in {"global", "both"}:
        results.append(
            SetupResult(
                Path.home() / ".claude.json",
                "skipped",
                "Claude user-scoped servers are managed by `claude mcp remove edgebase --scope user`",
            )
        )
    return results


def disable_codex(repo_root: Path, scope: str) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".codex" / "config.toml"
        action = "updated" if remove_codex_toml(path) else "skipped"
        results.append(SetupResult(path, action, "Codex project MCP server removed"))
    if scope in {"global", "both"}:
        path = Path.home() / ".codex" / "config.toml"
        action = "updated" if remove_codex_toml(path) else "skipped"
        results.append(SetupResult(path, action, "Codex global MCP server removed"))
    return results


def disable_cursor(repo_root: Path, scope: str) -> list[SetupResult]:
    return disable_json_mcp(repo_root, scope, ".cursor/mcp.json", Path.home() / ".cursor" / "mcp.json", "Cursor")


def disable_gemini(repo_root: Path, scope: str) -> list[SetupResult]:
    return disable_json_mcp(
        repo_root, scope, ".gemini/settings.json", Path.home() / ".gemini" / "settings.json", "Gemini CLI"
    )


def disable_windsurf(scope: str) -> list[SetupResult]:
    path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    if scope not in {"global", "both"}:
        return [SetupResult(path, "skipped", "Windsurf only has a global MCP config")]
    action = "updated" if remove_mcp_json(path, "edgebase") else "skipped"
    return [SetupResult(path, action, "Windsurf global MCP server removed")]


def disable_json_mcp(
    repo_root: Path, scope: str, project_rel: str, global_path: Path, label: str
) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / project_rel
        action = "updated" if remove_mcp_json(path, "edgebase") else "skipped"
        results.append(SetupResult(path, action, f"{label} project MCP server removed"))
    if scope in {"global", "both"}:
        action = "updated" if remove_mcp_json(global_path, "edgebase") else "skipped"
        results.append(SetupResult(global_path, action, f"{label} global MCP server removed"))
    return results


def disable_opencode(repo_root: Path, scope: str) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".opencode.json"
        action = "updated" if set_opencode_enabled(path, False) else "skipped"
        results.append(SetupResult(path, action, "OpenCode project MCP server disabled"))
    if scope in {"global", "both"}:
        path = Path.home() / ".opencode.json"
        action = "updated" if set_opencode_enabled(path, False) else "skipped"
        results.append(SetupResult(path, action, "OpenCode global MCP server disabled"))
    return results


def set_opencode_enabled(path: Path, enabled: bool) -> bool:
    if not path.exists():
        return False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return False
    mcp = loaded.get("mcp")
    if not isinstance(mcp, dict):
        return False
    edgebase = mcp.get("edgebase")
    if not isinstance(edgebase, dict):
        return False
    edgebase["enabled"] = enabled
    path.write_text(json.dumps(loaded, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True
