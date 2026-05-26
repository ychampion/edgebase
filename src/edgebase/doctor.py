from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .git import find_repo_root
from .indexer import index_repo
from .setup import (
    CLAUDE_GOAL_SKILL_START,
    CLAUDE_SKILL_START,
    CODEX_GOAL_SKILL_START,
    CODEX_SKILL_START,
    normalize_agents,
)
from .store import Store


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def run_doctor(root: str | Path, agents: list[str] | None = None, scope: str = "project") -> list[Check]:
    repo_root = find_repo_root(root)
    selected = normalize_agents(agents)
    checks: list[Check] = []
    checks.append(Check("python", "ok", sys.executable))

    store = Store(repo_root)
    if not store.exists():
        result = index_repo(repo_root)
        checks.append(Check("index", "ok", f"created index with {result.files} files"))
    else:
        stats = store.stats()
        checks.append(
            Check("index", "ok", f"{stats['files']} files, {stats['symbols']} symbols, {stats['edges']} edges")
        )

    checks.append(mcp_stdio_check(repo_root))
    checks.extend(agent_config_checks(repo_root, selected, scope))
    checks.extend(agent_binary_checks(selected))
    return checks


def mcp_stdio_check(repo_root: Path) -> Check:
    request = "\n".join(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "edgebase-doctor", "version": "0"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            "",
        ]
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "edgebase", "mcp", "--root", str(repo_root)],
            input=request,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("mcp-stdio", "fail", str(exc))
    if proc.returncode != 0:
        return Check("mcp-stdio", "fail", proc.stderr.strip() or f"exit {proc.returncode}")
    try:
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        return Check("mcp-stdio", "fail", f"invalid JSON-RPC response: {exc}")
    tools = []
    for response in responses:
        result = response.get("result") if isinstance(response, dict) else None
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            tools = result["tools"]
    tool_names = {str(tool.get("name")) for tool in tools if isinstance(tool, dict)}
    expected = {"edgebase_context", "edgebase_goal", "edgebase_checkpoint", "edgebase_fork_plan", "edgebase_resume"}
    missing = expected - tool_names
    if not missing:
        return Check("mcp-stdio", "ok", "Edgebase MCP tools listed")
    return Check("mcp-stdio", "fail", "missing from tools/list: " + ", ".join(sorted(missing)))


def agent_config_checks(repo_root: Path, agents: set[str], scope: str) -> list[Check]:
    checks: list[Check] = []
    if "claude" in agents and scope in {"project", "both"}:
        checks.append(json_mcp_check(repo_root / ".mcp.json", "Claude Code project config"))
        checks.append(claude_hooks_check(repo_root / ".claude" / "settings.json"))
        checks.append(
            text_contains_check(
                repo_root / ".claude" / "skills" / "edgebase" / "SKILL.md",
                CLAUDE_SKILL_START,
                "Claude Code /edgebase skill",
            )
        )
        checks.append(
            text_contains_check(
                repo_root / ".claude" / "skills" / "goal" / "SKILL.md",
                CLAUDE_GOAL_SKILL_START,
                "Claude Code /goal skill",
            )
        )
    if "codex" in agents and scope in {"project", "both"}:
        checks.append(text_contains_check(repo_root / ".codex" / "config.toml", "[mcp_servers.edgebase]", "Codex project config"))
        checks.append(text_contains_check(repo_root / ".codex" / "config.toml", "hooks = true", "Codex hooks feature"))
        checks.append(codex_hooks_check(repo_root / ".codex" / "hooks.json"))
        checks.append(text_contains_check(repo_root / ".agents" / "skills" / "edgebase" / "SKILL.md", CODEX_SKILL_START, "Codex /edgebase skill"))
        checks.append(text_contains_check(repo_root / ".agents" / "skills" / "goal" / "SKILL.md", CODEX_GOAL_SKILL_START, "Codex /goal skill"))
    if "codex" in agents and scope in {"global", "both"}:
        checks.append(
            text_contains_check(Path.home() / ".codex" / "config.toml", "[mcp_servers.edgebase]", "Codex global config")
        )
    if "cursor" in agents and scope in {"project", "both"}:
        checks.append(json_mcp_check(repo_root / ".cursor" / "mcp.json", "Cursor project config"))
    if "cursor" in agents and scope in {"global", "both"}:
        checks.append(json_mcp_check(Path.home() / ".cursor" / "mcp.json", "Cursor global config"))
    if "gemini" in agents and scope in {"project", "both"}:
        checks.append(json_mcp_check(repo_root / ".gemini" / "settings.json", "Gemini CLI project config"))
    if "gemini" in agents and scope in {"global", "both"}:
        checks.append(json_mcp_check(Path.home() / ".gemini" / "settings.json", "Gemini CLI global config"))
    if "opencode" in agents and scope in {"project", "both"}:
        checks.append(opencode_check(repo_root / ".opencode.json", "OpenCode project config"))
    if "opencode" in agents and scope in {"global", "both"}:
        checks.append(opencode_check(Path.home() / ".opencode.json", "OpenCode global config"))
    if "windsurf" in agents and scope in {"global", "both"}:
        checks.append(json_mcp_check(Path.home() / ".codeium" / "windsurf" / "mcp_config.json", "Windsurf global config"))
    return checks


def json_mcp_check(path: Path, label: str) -> Check:
    if not path.exists():
        return Check(label, "warn", f"missing {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Check(label, "fail", f"invalid JSON: {exc}")
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if isinstance(servers, dict) and "edgebase" in servers:
        return Check(label, "ok", str(path))
    return Check(label, "warn", "edgebase server not configured")


def opencode_check(path: Path, label: str) -> Check:
    if not path.exists():
        return Check(label, "warn", f"missing {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Check(label, "fail", f"invalid JSON: {exc}")
    mcp = data.get("mcp") if isinstance(data, dict) else None
    edgebase = mcp.get("edgebase") if isinstance(mcp, dict) else None
    if isinstance(edgebase, dict) and edgebase.get("enabled", True):
        return Check(label, "ok", str(path))
    if isinstance(edgebase, dict):
        return Check(label, "warn", "edgebase server configured but disabled")
    return Check(label, "warn", "edgebase server not configured")


def claude_hooks_check(path: Path) -> Check:
    if not path.exists():
        return Check("Claude Code hooks", "warn", f"missing {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Check("Claude Code hooks", "fail", f"invalid JSON: {exc}")
    hooks = data.get("hooks") if isinstance(data, dict) else None
    rendered = json.dumps(hooks) if isinstance(hooks, dict) else ""
    missing = [
        name
        for name in (
            "claude-user-prompt-submit",
            "claude-session-start",
            "claude-pre-tool-use",
            "claude-post-tool-use",
            "claude-pre-compact",
            "claude-session-end",
        )
        if name not in rendered
    ]
    if missing:
        return Check("Claude Code hooks", "warn", "missing " + ", ".join(missing))
    return Check("Claude Code hooks", "ok", str(path))


def codex_hooks_check(path: Path) -> Check:
    if not path.exists():
        return Check("Codex hooks", "warn", f"missing {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Check("Codex hooks", "fail", f"invalid JSON: {exc}")
    rendered = json.dumps(data) if isinstance(data, dict) else ""
    missing = [
        name
        for name in (
            "codex-session-start",
            "codex-user-prompt-submit",
            "codex-pre-tool-use",
            "codex-post-tool-use",
            "codex-pre-compact",
            "codex-stop",
        )
        if name not in rendered
    ]
    if missing:
        return Check("Codex hooks", "warn", "missing " + ", ".join(missing))
    return Check("Codex hooks", "ok", str(path))


def text_contains_check(path: Path, needle: str, label: str) -> Check:
    if not path.exists():
        return Check(label, "warn", f"missing {path}")
    if needle in path.read_text(encoding="utf-8"):
        return Check(label, "ok", str(path))
    return Check(label, "warn", "edgebase server not configured")


def agent_binary_checks(agents: set[str]) -> list[Check]:
    binaries = {
        "claude": "claude",
        "codex": "codex",
        "cursor": "cursor-agent",
        "gemini": "gemini",
        "opencode": "opencode",
        "windsurf": "windsurf",
    }
    checks: list[Check] = []
    for agent, binary in binaries.items():
        if agent not in agents:
            continue
        path = shutil.which(binary)
        if path:
            checks.append(Check(f"{agent}-cli", "ok", path))
        else:
            checks.append(Check(f"{agent}-cli", "warn", f"`{binary}` not found on PATH; config file validation only"))
    return checks
