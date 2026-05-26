from __future__ import annotations

from .setup import ALL_AGENTS, normalize_agents


DISPLAY_NAMES = {
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
    "windsurf": "Windsurf",
}


def render_install_prompt(agent: str = "all") -> str:
    selected = sorted(normalize_agents([agent]))
    agents_arg = "all" if selected == sorted(ALL_AGENTS) else ",".join(selected)
    host_lines = "\n".join(f"- {DISPLAY_NAMES.get(name, name)}" for name in selected)
    return (
        "Set up Edgebase for this repository.\n\n"
        "Repository target: current working directory.\n\n"
        "Do the setup yourself. Do not ask me to run Edgebase commands manually.\n\n"
        "Steps:\n"
        "1. Confirm you are inside a git repository. If I gave you a repository URL instead of a local repo, "
        "clone it first and cd into it.\n"
        "2. Run:\n"
        "   python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git\n"
        "3. Run:\n"
        f"   python3 -m edgebase setup --scope both --agents {agents_arg}\n"
        "4. Run:\n"
        f"   python3 -m edgebase doctor --scope both --agents {agents_arg}\n"
        "5. Report the files Edgebase changed and whether doctor passed.\n\n"
        "Rules:\n"
        "- Do not add generated architecture summaries to AGENTS.md.\n"
        "- Do not remove existing agent config.\n"
        "- Do not commit unless I explicitly ask.\n"
        "- Explain that Edgebase is on by default after setup, can be disabled with "
        "`python3 -m edgebase disable --scope both`, and can be bypassed for one emergency session with "
        "`EDGEBASE_PREFLIGHT=off`.\n\n"
        "After setup, report exactly which capabilities became automatic:\n"
        "- MCP tools: edgebase_context, edgebase_goal, edgebase_radius, edgebase_checkpoint, "
        "edgebase_fork_plan, and edgebase_resume.\n"
        "- Prompt-time Goal Capsule creation where hooks are supported and trusted.\n"
        "- Pre-edit freshness checks where hooks are supported and trusted.\n"
        "- Post-edit graph refresh, pre-compact checkpoint, and Patch Passport flows where hooks are supported.\n"
        "- Slash commands or skills installed for the selected agent host.\n\n"
        "Selected agent hosts:\n"
        f"{host_lines}"
    )


def render_bootstrap(agent: str = "all") -> str:
    return (
        "# Edgebase Bootstrap\n\n"
        "Paste this into your coding agent from the repository root:\n\n"
        "```text\n"
        f"{render_install_prompt(agent)}\n"
        "```\n"
    )
