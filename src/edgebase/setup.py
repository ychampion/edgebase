from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .hooks import install_claude_hooks, install_git_hook
from .indexer import index_repo


ALL_AGENTS = ("claude", "codex", "cursor", "gemini", "opencode", "windsurf")


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
    command: str = "edgebase",
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


def stdio_config(repo_root: Path, command: str = "edgebase") -> dict[str, object]:
    return {"command": command, "args": ["mcp", "--root", str(repo_root)], "env": {}}


def write_agent_docs(repo_root: Path) -> SetupResult:
    agents_path = repo_root / "AGENTS.md"
    snippet = (
        "# Agent Instructions\n\n"
        "Keep static instructions minimal. For current codebase structure, use Edgebase before broad exploration:\n\n"
        "```bash\n"
        "edgebase context \"<task>\" --budget 1200\n"
        "```\n\n"
        "Prefer the MCP tool `edgebase_context` when it is available.\n"
    )
    if not agents_path.exists():
        agents_path.write_text(snippet, encoding="utf-8")
        return SetupResult(agents_path, "created", "minimal agent instructions")
    edgebase_doc = repo_root / "EDGEBASE.md"
    edgebase_doc.write_text(
        "# Edgebase Agent Context\n\n"
        "Use Edgebase for fresh, source-backed structure instead of adding generated architecture summaries to AGENTS.md.\n\n"
        "```bash\n"
        "edgebase context \"<task>\" --budget 1200\n"
        "```\n\n"
        "MCP tool name: `edgebase_context`.\n",
        encoding="utf-8",
    )
    return SetupResult(edgebase_doc, "created", "AGENTS.md existed; wrote Edgebase agent note")


def setup_claude(
    repo_root: Path, scope: str, install_hooks: bool, command: str
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


def setup_codex(repo_root: Path, scope: str, command: str) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(SetupResult(path, "updated", "Codex project MCP server"))
    if scope in {"global", "both"}:
        path = Path.home() / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(SetupResult(path, "updated", "Codex global MCP server"))
    return results


def setup_cursor(repo_root: Path, scope: str, command: str) -> list[SetupResult]:
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


def setup_gemini(repo_root: Path, scope: str, command: str) -> list[SetupResult]:
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


def setup_opencode(repo_root: Path, scope: str, command: str) -> list[SetupResult]:
    results: list[SetupResult] = []
    value = {
        "type": "local",
        "command": [command, "mcp", "--root", str(repo_root)],
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


def setup_windsurf(repo_root: Path, scope: str, command: str) -> list[SetupResult]:
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


def upsert_codex_toml(path: Path, repo_root: Path, command: str) -> None:
    section = (
        "[mcp_servers.edgebase]\n"
        f'command = "{escape_toml(command)}"\n'
        f'args = ["mcp", "--root", "{escape_toml(str(repo_root))}"]\n'
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
