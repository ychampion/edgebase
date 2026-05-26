from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HostCapability:
    name: str
    display_name: str
    mcp: bool
    project_skills: bool = False
    global_skills: bool = False
    hooks: bool = False
    agent_docs: bool = True
    verified_hooks: bool = False


HOSTS: dict[str, HostCapability] = {
    "claude": HostCapability(
        name="claude",
        display_name="Claude Code",
        mcp=True,
        project_skills=True,
        hooks=True,
        verified_hooks=True,
    ),
    "codex": HostCapability(
        name="codex",
        display_name="Codex",
        mcp=True,
        project_skills=True,
        global_skills=True,
        hooks=True,
        verified_hooks=True,
    ),
    "cursor": HostCapability(name="cursor", display_name="Cursor", mcp=True),
    "gemini": HostCapability(name="gemini", display_name="Gemini CLI", mcp=True),
    "opencode": HostCapability(name="opencode", display_name="OpenCode", mcp=True),
    "windsurf": HostCapability(name="windsurf", display_name="Windsurf", mcp=True),
}

ALL_AGENTS = tuple(HOSTS)


def host_capabilities() -> list[HostCapability]:
    return [HOSTS[name] for name in ALL_AGENTS]


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
                if name not in HOSTS:
                    raise ValueError(f"Unknown agent `{name}`. Supported: {', '.join(ALL_AGENTS)}")
                normalized.add(name)
    return normalized
