from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from .git import run_git
from .hooks import (
    install_claude_hooks,
    install_codex_hooks,
    install_git_hook,
    uninstall_claude_hooks,
    uninstall_codex_hooks,
    uninstall_git_hook,
)
from .indexer import index_repo


ALL_AGENTS = ("claude", "codex", "cursor", "gemini", "opencode", "windsurf")
AGENT_DOC_START = "<!-- EDGEBASE:START -->"
AGENT_DOC_END = "<!-- EDGEBASE:END -->"
CLAUDE_SKILL_START = "<!-- EDGEBASE:CLAUDE-SKILL:START -->"
CLAUDE_SKILL_END = "<!-- EDGEBASE:CLAUDE-SKILL:END -->"
CLAUDE_GOAL_SKILL_START = "<!-- EDGEBASE:CLAUDE-GOAL-SKILL:START -->"
CLAUDE_GOAL_SKILL_END = "<!-- EDGEBASE:CLAUDE-GOAL-SKILL:END -->"
CLAUDE_EDGEBASE_GOAL_SKILL_START = "<!-- EDGEBASE:CLAUDE-EDGEBASE-GOAL-SKILL:START -->"
CLAUDE_EDGEBASE_GOAL_SKILL_END = "<!-- EDGEBASE:CLAUDE-EDGEBASE-GOAL-SKILL:END -->"
CODEX_SKILL_START = "<!-- EDGEBASE:CODEX-SKILL:START -->"
CODEX_SKILL_END = "<!-- EDGEBASE:CODEX-SKILL:END -->"
CODEX_GOAL_SKILL_START = "<!-- EDGEBASE:CODEX-GOAL-SKILL:START -->"
CODEX_GOAL_SKILL_END = "<!-- EDGEBASE:CODEX-GOAL-SKILL:END -->"
CODEX_EDGEBASE_GOAL_SKILL_START = "<!-- EDGEBASE:CODEX-EDGEBASE-GOAL-SKILL:START -->"
CODEX_EDGEBASE_GOAL_SKILL_END = "<!-- EDGEBASE:CODEX-EDGEBASE-GOAL-SKILL:END -->"


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    cli_args: tuple[str, ...]
    description: str
    argument_hint: str
    argument_expr: str
    body: str


EDGEBASE_SLASH_COMMANDS = (
    SlashCommandSpec(
        "edgebase-radius",
        ("radius",),
        "Show advisory change blast radius for a file or proposed plan.",
        '"src/path/file.ts" [--goal "<plan>"]',
        " $ARGUMENTS --budget 1200",
        "Map likely affected routes, tests, downstream modules, migration paths, and side-effect risks. Use it while planning; it is advisory and does not require editing every listed path.",
    ),
    SlashCommandSpec(
        "edgebase-checkpoint",
        ("checkpoint",),
        "Save an Edgebase context checkpoint for compaction or handoff.",
        '"<handoff message>"',
        ' "$ARGUMENTS" --budget 1200',
        "Save a source-backed checkpoint for the current task. Use it before compaction or handoff.",
    ),
    SlashCommandSpec(
        "edgebase-resume",
        ("resume",),
        "Render the latest or named Edgebase checkpoint.",
        "[snapshot id]",
        " $ARGUMENTS",
        "Render a saved Edgebase checkpoint so work can resume with compact context.",
    ),
    SlashCommandSpec(
        "edgebase-fork-plan",
        ("fork-plan",),
        "Create a git worktree plan from an Edgebase checkpoint.",
        '"<fork objective>"',
        ' "$ARGUMENTS" --budget 1200',
        "Create a branch/worktree plan for parallel agent work from an Edgebase checkpoint.",
    ),
    SlashCommandSpec(
        "edgebase-passport",
        ("passport",),
        "Create a Patch Passport for the current working tree.",
        '"<goal>" --test "command: result"',
        " $ARGUMENTS --budget 1200",
        "Summarize the current patch, changed files, explicit test evidence, risk, and review focus.",
    ),
    SlashCommandSpec(
        "edgebase-preflight-status",
        ("preflight", "status"),
        "Show whether the Edgebase pre-edit Goal Capsule is fresh.",
        "",
        "",
        "Inspect the current preflight gate state before editing.",
    ),
    SlashCommandSpec(
        "edgebase-preflight-refresh",
        ("preflight", "refresh"),
        "Record a fresh Edgebase preflight Goal Capsule.",
        '"<coding goal>"',
        ' "$ARGUMENTS" --budget 1200',
        "Refresh the pre-edit gate with a new Goal Capsule for the current objective.",
    ),
    SlashCommandSpec(
        "edgebase-index",
        ("index",),
        "Build or refresh the local Edgebase graph index.",
        "[--changed | --file path]",
        " $ARGUMENTS",
        "Refresh the local graph index. Use `--changed` for a focused git-status refresh.",
    ),
    SlashCommandSpec(
        "edgebase-stats",
        ("stats",),
        "Show local Edgebase index statistics.",
        "",
        "",
        "Show file, symbol, edge, and metric counts for the local Edgebase index.",
    ),
    SlashCommandSpec(
        "edgebase-doctor",
        ("doctor",),
        "Check the Edgebase index, MCP stdio, and configured agent clients.",
        "[--agents claude,codex --scope project]",
        " $ARGUMENTS",
        "Run Edgebase diagnostics for the current repository and configured agent clients.",
    ),
    SlashCommandSpec(
        "edgebase-setup",
        ("setup",),
        "Configure or repair Edgebase integrations for this repository.",
        "[--agents all --scope both]",
        " $ARGUMENTS",
        "Run local Edgebase setup again to install or repair supported agent integrations.",
    ),
    SlashCommandSpec(
        "edgebase-disable",
        ("disable",),
        "Turn off Edgebase integrations for this repository.",
        "[--agents all --scope both]",
        " $ARGUMENTS",
        "Remove or disable generated Edgebase integrations for the selected agents and scope.",
    ),
    SlashCommandSpec(
        "edgebase-version",
        ("--version",),
        "Show the installed Edgebase version.",
        "",
        "",
        "Print the installed Edgebase version for setup and smoke-test verification.",
    ),
)


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
    results.append(ensure_edgebase_cache_excluded(repo_root))

    if write_agents_md:
        results.append(write_agent_docs(repo_root))

    if "claude" in selected:
        results.extend(setup_claude(repo_root, scope, install_hooks, command))
    if "codex" in selected:
        results.extend(setup_codex(repo_root, scope, install_hooks, command))
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
        results.extend(disable_codex(repo_root, scope, remove_hooks))
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


def ensure_edgebase_cache_excluded(repo_root: Path) -> SetupResult:
    proc = run_git(repo_root, ["rev-parse", "--git-path", "info/exclude"], timeout=3)
    if not proc or proc.returncode != 0 or not proc.stdout.strip():
        return SetupResult(repo_root / ".edgebase", "skipped", "git exclude unavailable")
    exclude_path = Path(proc.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = repo_root / exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    if ".edgebase/" in {line.strip() for line in existing.splitlines()}:
        return SetupResult(exclude_path, "skipped", ".edgebase/ already ignored")
    prefix = "\n" if existing and not existing.endswith("\n") else ""
    exclude_path.write_text(f"{existing}{prefix}# Edgebase cache\n.edgebase/\n", encoding="utf-8")
    return SetupResult(exclude_path, "updated", "ignored local Edgebase cache")


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
        "## Edgebase Preflight Gate\n\n"
        "Edgebase is enabled for this repository. Do not wait for the user to request it explicitly. "
        "Claude Code and Codex hooks record a Goal Capsule before planning and block Write/Edit/MultiEdit "
        "when no fresh capsule exists. MCP clients should call `edgebase_goal` for implementation goals and "
        "`edgebase_context` for read-only investigation before broad exploration.\n\n"
        "Preferred explicit slash commands when skills or MCP prompts are exposed:\n\n"
        "```text\n"
        "/edgebase \"<task>\"\n"
        "/edgebase-goal \"<goal>\"\n"
        "/edgebase-radius \"<file or plan>\"\n"
        "/edgebase-checkpoint \"<handoff message>\"\n"
        "/edgebase-resume\n"
        "/edgebase-preflight-status\n"
        "/edgebase-index --changed\n"
        "/edgebase-doctor --scope project\n"
        "```\n\n"
        "Fallback when MCP tools, slash commands, and automatic hooks are unavailable:\n\n"
        "```bash\n"
        "python3 -m edgebase context \"<task>\" --budget 1200\n"
        "python3 -m edgebase goal \"<goal>\" --budget 1200 --record-preflight\n"
        "python3 -m edgebase radius \"<file or plan>\" --budget 1200\n"
        "python3 -m edgebase checkpoint \"<handoff message>\"\n"
        "python3 -m edgebase resume\n"
        "```\n\n"
        "Keep static instructions here minimal; Edgebase supplies fresh structure, symbols, tests, owners, "
        "and change-hotspot context from the local git working tree. Local checkpoint and patch-passport files are "
        "saved under `.edgebase/` for compaction and session-end recovery. Hooks and MCP calls may update local graph "
        "artifacts under `.edgebase/graphs/latest.*`; use surfaced artifact paths when a visual relationship view helps, "
        "but do not paste raw graph dumps into agent context. Turn the gate off with `EDGEBASE_PREFLIGHT=off` for an "
        "emergency session, or remove integrations with `python3 -m edgebase disable --scope both`.\n"
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
        try:
            skill_path = install_claude_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(repo_root / ".claude" / "skills" / "edgebase" / "SKILL.md", "skipped", str(exc))
            )
        else:
            results.append(SetupResult(skill_path, "updated", "Claude Code project skill /edgebase"))
        try:
            goal_skill_path = install_claude_goal_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(repo_root / ".claude" / "skills" / "goal" / "SKILL.md", "skipped", str(exc))
            )
        else:
            results.append(SetupResult(goal_skill_path, "updated", "Claude Code project skill /goal"))
        try:
            edgebase_goal_skill_path = install_claude_edgebase_goal_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(
                    repo_root / ".claude" / "skills" / "edgebase-goal" / "SKILL.md",
                    "skipped",
                    str(exc),
                )
            )
        else:
            results.append(SetupResult(edgebase_goal_skill_path, "updated", "Claude Code project skill /edgebase-goal"))
        for spec in EDGEBASE_SLASH_COMMANDS:
            try:
                command_skill_path = install_claude_command_skill(repo_root, command, spec)
            except RuntimeError as exc:
                results.append(
                    SetupResult(repo_root / ".claude" / "skills" / spec.name / "SKILL.md", "skipped", str(exc))
                )
            else:
                results.append(SetupResult(command_skill_path, "updated", f"Claude Code project skill /{spec.name}"))
        if install_hooks:
            hooks_path = install_claude_hooks(repo_root)
            results.append(SetupResult(hooks_path, "updated", "Claude Code automatic prompt and freshness hooks"))
    if scope in {"global", "both"}:
        results.append(
            SetupResult(
                Path.home() / ".claude.json",
                "skipped",
                "Claude global MCP is best installed with `claude mcp add`; project .mcp.json was written instead",
            )
        )
    return results


def install_claude_skill(repo_root: Path, command: str | None) -> Path:
    skill_path = repo_root / ".claude" / "skills" / "edgebase" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists():
        existing = skill_path.read_text(encoding="utf-8")
        if CLAUDE_SKILL_START not in existing:
            raise RuntimeError(f"Refusing to overwrite existing Claude skill without Edgebase marker: {skill_path}")
    skill_path.write_text(claude_skill_content(repo_root, command), encoding="utf-8")
    return skill_path


def claude_skill_content(repo_root: Path, command: str | None) -> str:
    executable, prefix = command_parts(command)
    command_prefix = " ".join(
        shlex.quote(part)
        for part in [executable, *prefix, "--root", str(repo_root), "context"]
    )
    return (
        f"{CLAUDE_SKILL_START}\n"
        "---\n"
        "name: edgebase\n"
        "description: Fetch source-backed Edgebase context for a coding task before broad code exploration or edits.\n"
        "argument-hint: \"<coding task>\"\n"
        "---\n\n"
        "# Edgebase\n\n"
        "Fetch the current Edgebase context capsule for this task, then use it as the first read set before broad "
        "repository exploration or edits.\n\n"
        "```bash\n"
        f"{command_prefix} \"$ARGUMENTS\" --budget 1200\n"
        "```\n\n"
        "If `$ARGUMENTS` is empty, infer the task from the current user request. Prefer the MCP tool "
        "`edgebase_context` when it is available; otherwise run the command above. If the response includes "
        "`.edgebase/graphs/latest.*` artifact paths, open or inspect those local files only when a visual "
        "relationship view helps the task.\n"
        f"{CLAUDE_SKILL_END}\n"
    )


def install_claude_goal_skill(repo_root: Path, command: str | None) -> Path:
    return install_claude_goal_skill_named(
        repo_root,
        command,
        "goal",
        CLAUDE_GOAL_SKILL_START,
        CLAUDE_GOAL_SKILL_END,
    )


def install_claude_edgebase_goal_skill(repo_root: Path, command: str | None) -> Path:
    return install_claude_goal_skill_named(
        repo_root,
        command,
        "edgebase-goal",
        CLAUDE_EDGEBASE_GOAL_SKILL_START,
        CLAUDE_EDGEBASE_GOAL_SKILL_END,
    )


def install_claude_goal_skill_named(
    repo_root: Path,
    command: str | None,
    skill_name: str,
    marker_start: str,
    marker_end: str,
) -> Path:
    skill_path = repo_root / ".claude" / "skills" / skill_name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists():
        existing = skill_path.read_text(encoding="utf-8")
        if marker_start not in existing:
            raise RuntimeError(f"Refusing to overwrite existing Claude skill without Edgebase marker: {skill_path}")
    skill_path.write_text(
        claude_goal_skill_content(repo_root, command, skill_name, marker_start, marker_end),
        encoding="utf-8",
    )
    return skill_path


def claude_goal_skill_content(
    repo_root: Path,
    command: str | None,
    skill_name: str,
    marker_start: str,
    marker_end: str,
) -> str:
    executable, prefix = command_parts(command)
    command_prefix = " ".join(
        shlex.quote(part)
        for part in [executable, *prefix, "--root", str(repo_root), "goal"]
    )
    return (
        f"{marker_start}\n"
        "---\n"
        f"name: {skill_name}\n"
        "description: Create an executable Edgebase Goal Capsule and Work Contract before editing.\n"
        "argument-hint: \"<coding goal>\"\n"
        "---\n\n"
        "# Goal\n\n"
        "Fetch a Goal Capsule for the current objective and use its Work Contract before write/edit tools.\n\n"
        "```bash\n"
        f"{command_prefix} \"$ARGUMENTS\" --budget 1200 --record-preflight\n"
        "```\n\n"
        "If `$ARGUMENTS` is empty, infer the goal from the current user request. Prefer the MCP tool "
        "`edgebase_goal` when it is available; otherwise run the command above. If the response includes "
        "`.edgebase/graphs/latest.*` artifact paths, use them as local visual aids without copying raw graph "
        "data into the coding context.\n"
        f"{marker_end}\n"
    )


def install_claude_command_skill(repo_root: Path, command: str | None, spec: SlashCommandSpec) -> Path:
    marker_start, marker_end = slash_command_markers("claude", spec.name)
    skill_path = repo_root / ".claude" / "skills" / spec.name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists() and marker_start not in skill_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Refusing to overwrite existing Claude skill without Edgebase marker: {skill_path}")
    skill_path.write_text(claude_command_skill_content(repo_root, command, spec), encoding="utf-8")
    return skill_path


def claude_command_skill_content(repo_root: Path, command: str | None, spec: SlashCommandSpec) -> str:
    marker_start, marker_end = slash_command_markers("claude", spec.name)
    return (
        f"{marker_start}\n"
        "---\n"
        f"name: {spec.name}\n"
        f"description: {spec.description}\n"
        f"argument-hint: {json.dumps(spec.argument_hint)}\n"
        "---\n\n"
        f"# {spec.name}\n\n"
        f"{spec.body}\n\n"
        "```bash\n"
        f"{slash_command_line(repo_root, command, spec)}\n"
        "```\n\n"
        "If the MCP tool or prompt equivalent is available, prefer it for structured results. "
        "Otherwise run the command above from the repository root.\n"
        f"{marker_end}\n"
    )


def setup_codex(repo_root: Path, scope: str, install_hooks: bool, command: str | None) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(SetupResult(path, "updated", "Codex project MCP server"))
        try:
            edgebase_skill = install_codex_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(repo_root / ".agents" / "skills" / "edgebase" / "SKILL.md", "skipped", str(exc))
            )
        else:
            results.append(SetupResult(edgebase_skill, "updated", "Codex project skill /edgebase"))
        try:
            goal_skill = install_codex_goal_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(repo_root / ".agents" / "skills" / "goal" / "SKILL.md", "skipped", str(exc))
            )
        else:
            results.append(SetupResult(goal_skill, "updated", "Codex project skill /goal"))
        try:
            edgebase_goal_skill = install_codex_edgebase_goal_skill(repo_root, command)
        except RuntimeError as exc:
            results.append(
                SetupResult(repo_root / ".agents" / "skills" / "edgebase-goal" / "SKILL.md", "skipped", str(exc))
            )
        else:
            results.append(
                SetupResult(edgebase_goal_skill, "updated", "Codex project skill /edgebase-goal")
            )
        for spec in EDGEBASE_SLASH_COMMANDS:
            try:
                command_skill = install_codex_command_skill(repo_root, command, spec)
            except RuntimeError as exc:
                results.append(
                    SetupResult(repo_root / ".agents" / "skills" / spec.name / "SKILL.md", "skipped", str(exc))
                )
            else:
                results.append(SetupResult(command_skill, "updated", f"Codex project skill /{spec.name}"))
        if install_hooks:
            hooks_path = install_codex_hooks(repo_root)
            results.append(SetupResult(hooks_path, "updated", "Codex preflight hooks"))
    if scope in {"global", "both"}:
        path = Path.home() / ".codex" / "config.toml"
        upsert_codex_toml(path, repo_root, command)
        results.append(SetupResult(path, "updated", "Codex global MCP server"))
    return results


def install_codex_skill(repo_root: Path, command: str | None) -> Path:
    skill_path = repo_root / ".agents" / "skills" / "edgebase" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists() and CODEX_SKILL_START not in skill_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Refusing to overwrite existing Codex skill without Edgebase marker: {skill_path}")
    skill_path.write_text(codex_skill_content(repo_root, command), encoding="utf-8")
    return skill_path


def codex_skill_content(repo_root: Path, command: str | None) -> str:
    executable, prefix = command_parts(command)
    command_prefix = " ".join(shlex.quote(part) for part in [executable, *prefix, "--root", str(repo_root), "context"])
    return (
        f"{CODEX_SKILL_START}\n"
        "---\nname: edgebase\ndescription: Fetch source-backed Edgebase context before broad exploration or edits.\n---\n\n"
        "# Edgebase\n\nUse `edgebase_context` when available. Otherwise run:\n\n"
        "```bash\n"
        f"{command_prefix} \"$ARGUMENTS\" --budget 1200\n"
        "```\n\nUse `edgebase_checkpoint`, `edgebase_fork_plan`, and `edgebase_resume` for handoffs.\n"
        f"{CODEX_SKILL_END}\n"
    )


def install_codex_goal_skill(repo_root: Path, command: str | None) -> Path:
    return install_codex_goal_skill_named(
        repo_root,
        command,
        "goal",
        CODEX_GOAL_SKILL_START,
        CODEX_GOAL_SKILL_END,
    )


def install_codex_edgebase_goal_skill(repo_root: Path, command: str | None) -> Path:
    return install_codex_goal_skill_named(
        repo_root,
        command,
        "edgebase-goal",
        CODEX_EDGEBASE_GOAL_SKILL_START,
        CODEX_EDGEBASE_GOAL_SKILL_END,
    )


def install_codex_goal_skill_named(
    repo_root: Path,
    command: str | None,
    skill_name: str,
    marker_start: str,
    marker_end: str,
) -> Path:
    skill_path = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists() and marker_start not in skill_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Refusing to overwrite existing Codex skill without Edgebase marker: {skill_path}")
    skill_path.write_text(
        codex_goal_skill_content(repo_root, command, skill_name, marker_start, marker_end),
        encoding="utf-8",
    )
    return skill_path


def codex_goal_skill_content(
    repo_root: Path,
    command: str | None,
    skill_name: str,
    marker_start: str,
    marker_end: str,
) -> str:
    executable, prefix = command_parts(command)
    command_prefix = " ".join(shlex.quote(part) for part in [executable, *prefix, "--root", str(repo_root), "goal"])
    return (
        f"{marker_start}\n"
        f"---\nname: {skill_name}\ndescription: Create and record an Edgebase Goal Capsule before editing.\n---\n\n"
        "# Goal\n\nUse `edgebase_goal` when available. Otherwise run:\n\n"
        "```bash\n"
        f"{command_prefix} \"$ARGUMENTS\" --budget 1200 --record-preflight\n"
        "```\n\nThe recorded Goal Capsule satisfies the pre-edit gate when hooks are trusted.\n"
        f"{marker_end}\n"
    )


def install_codex_command_skill(repo_root: Path, command: str | None, spec: SlashCommandSpec) -> Path:
    marker_start, marker_end = slash_command_markers("codex", spec.name)
    skill_path = repo_root / ".agents" / "skills" / spec.name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if skill_path.exists() and marker_start not in skill_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Refusing to overwrite existing Codex skill without Edgebase marker: {skill_path}")
    skill_path.write_text(codex_command_skill_content(repo_root, command, spec), encoding="utf-8")
    return skill_path


def codex_command_skill_content(repo_root: Path, command: str | None, spec: SlashCommandSpec) -> str:
    marker_start, marker_end = slash_command_markers("codex", spec.name)
    return (
        f"{marker_start}\n"
        "---\n"
        f"name: {spec.name}\n"
        f"description: {spec.description}\n"
        f"argument-hint: {json.dumps(spec.argument_hint)}\n"
        "---\n\n"
        f"# {spec.name}\n\n"
        f"{spec.body}\n\n"
        "```bash\n"
        f"{slash_command_line(repo_root, command, spec)}\n"
        "```\n"
        f"{marker_end}\n"
    )


def slash_command_markers(host: str, skill_name: str) -> tuple[str, str]:
    marker = skill_name.upper().replace("-", "_")
    return (
        f"<!-- EDGEBASE:{host.upper()}-COMMAND-{marker}-SKILL:START -->",
        f"<!-- EDGEBASE:{host.upper()}-COMMAND-{marker}-SKILL:END -->",
    )


def slash_command_line(repo_root: Path, command: str | None, spec: SlashCommandSpec) -> str:
    executable, prefix = command_parts(command)
    if spec.cli_args and spec.cli_args[0].startswith("--"):
        parts = [executable, *prefix, *spec.cli_args]
    else:
        parts = [executable, *prefix, *spec.cli_args, "--root", str(repo_root)]
    command_prefix = shlex.join(parts)
    return command_prefix + spec.argument_expr


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
    updated = upsert_codex_hooks_feature(updated)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def upsert_codex_hooks_feature(content: str) -> str:
    hooks_line = "hooks = true"
    feature_pattern = re.compile(r"(?ms)^\[features\]\n.*?(?=^\[|\Z)")
    match = feature_pattern.search(content)
    if not match:
        return content.rstrip() + ("\n\n" if content.strip() else "") + "[features]\nhooks = true\n"
    section = match.group(0).rstrip()
    if re.search(r"(?m)^hooks\s*=", section):
        section = re.sub(r"(?m)^hooks\s*=.*$", hooks_line, section)
    else:
        section = section + "\n" + hooks_line
    return feature_pattern.sub(section + "\n", content).rstrip() + "\n"


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
        skill_path = uninstall_claude_skill(repo_root)
        results.append(SetupResult(skill_path, "updated", "removed Claude Code project skill /edgebase"))
        goal_skill_path = uninstall_claude_goal_skill(repo_root)
        results.append(SetupResult(goal_skill_path, "updated", "removed Claude Code project skill /goal"))
        edgebase_goal_skill_path = uninstall_claude_edgebase_goal_skill(repo_root)
        results.append(
            SetupResult(edgebase_goal_skill_path, "updated", "removed Claude Code project skill /edgebase-goal")
        )
        for spec in EDGEBASE_SLASH_COMMANDS:
            command_skill_path = uninstall_claude_command_skill(repo_root, spec)
            results.append(SetupResult(command_skill_path, "updated", f"removed Claude Code project skill /{spec.name}"))
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


def uninstall_claude_skill(repo_root: Path) -> Path:
    skill_path = repo_root / ".claude" / "skills" / "edgebase" / "SKILL.md"
    if not skill_path.exists():
        return skill_path
    existing = skill_path.read_text(encoding="utf-8")
    if CLAUDE_SKILL_START not in existing:
        return skill_path
    skill_path.unlink()
    for parent in (skill_path.parent, skill_path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return skill_path


def uninstall_claude_goal_skill(repo_root: Path) -> Path:
    return uninstall_claude_goal_skill_named(repo_root, "goal", CLAUDE_GOAL_SKILL_START)


def uninstall_claude_edgebase_goal_skill(repo_root: Path) -> Path:
    return uninstall_claude_goal_skill_named(repo_root, "edgebase-goal", CLAUDE_EDGEBASE_GOAL_SKILL_START)


def uninstall_claude_goal_skill_named(repo_root: Path, skill_name: str, marker_start: str) -> Path:
    skill_path = repo_root / ".claude" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        return skill_path
    existing = skill_path.read_text(encoding="utf-8")
    if marker_start not in existing:
        return skill_path
    skill_path.unlink()
    for parent in (skill_path.parent, skill_path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return skill_path


def uninstall_claude_command_skill(repo_root: Path, spec: SlashCommandSpec) -> Path:
    marker_start, _ = slash_command_markers("claude", spec.name)
    return uninstall_claude_goal_skill_named(repo_root, spec.name, marker_start)


def disable_codex(repo_root: Path, scope: str, remove_hooks: bool) -> list[SetupResult]:
    results: list[SetupResult] = []
    if scope in {"project", "both"}:
        path = repo_root / ".codex" / "config.toml"
        action = "updated" if remove_codex_toml(path) else "skipped"
        results.append(SetupResult(path, action, "Codex project MCP server removed"))
        skill_path = uninstall_codex_skill(repo_root)
        results.append(SetupResult(skill_path, "updated", "removed Codex project skill /edgebase"))
        goal_skill_path = uninstall_codex_goal_skill(repo_root)
        results.append(SetupResult(goal_skill_path, "updated", "removed Codex project skill /goal"))
        edgebase_goal_skill_path = uninstall_codex_edgebase_goal_skill(repo_root)
        results.append(SetupResult(edgebase_goal_skill_path, "updated", "removed Codex project skill /edgebase-goal"))
        for spec in EDGEBASE_SLASH_COMMANDS:
            command_skill_path = uninstall_codex_command_skill(repo_root, spec)
            results.append(SetupResult(command_skill_path, "updated", f"removed Codex project skill /{spec.name}"))
        if remove_hooks:
            hooks_path = uninstall_codex_hooks(repo_root)
            results.append(SetupResult(hooks_path, "updated", "removed Codex hooks"))
    if scope in {"global", "both"}:
        path = Path.home() / ".codex" / "config.toml"
        action = "updated" if remove_codex_toml(path) else "skipped"
        results.append(SetupResult(path, action, "Codex global MCP server removed"))
    return results


def uninstall_codex_skill(repo_root: Path) -> Path:
    skill_path = repo_root / ".agents" / "skills" / "edgebase" / "SKILL.md"
    if not skill_path.exists() or CODEX_SKILL_START not in skill_path.read_text(encoding="utf-8"):
        return skill_path
    skill_path.unlink()
    for parent in (skill_path.parent, skill_path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return skill_path


def uninstall_codex_goal_skill(repo_root: Path) -> Path:
    return uninstall_codex_goal_skill_named(repo_root, "goal", CODEX_GOAL_SKILL_START)


def uninstall_codex_edgebase_goal_skill(repo_root: Path) -> Path:
    return uninstall_codex_goal_skill_named(repo_root, "edgebase-goal", CODEX_EDGEBASE_GOAL_SKILL_START)


def uninstall_codex_goal_skill_named(repo_root: Path, skill_name: str, marker_start: str) -> Path:
    skill_path = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists() or marker_start not in skill_path.read_text(encoding="utf-8"):
        return skill_path
    skill_path.unlink()
    for parent in (skill_path.parent, skill_path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return skill_path


def uninstall_codex_command_skill(repo_root: Path, spec: SlashCommandSpec) -> Path:
    marker_start, _ = slash_command_markers("codex", spec.name)
    return uninstall_codex_goal_skill_named(repo_root, spec.name, marker_start)


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
