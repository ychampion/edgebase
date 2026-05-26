from __future__ import annotations

from .hosts import ALL_AGENTS, HOSTS, normalize_agents


def render_install_prompt(agent: str = "all") -> str:
    selected = sorted(normalize_agents([agent]))
    agents_arg = "all" if selected == sorted(ALL_AGENTS) else ",".join(selected)
    host_lines = "\n".join(f"- {HOSTS[name].display_name}" for name in selected)
    return (
        "Install Edgebase for this repository and verify the automatic work-contract runtime.\n\n"
        "Repository target: current working directory.\n\n"
        "Do the setup yourself. Do not ask me to run Edgebase commands manually.\n\n"
        "Run:\n"
        "```bash\n"
        "python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git &&\n"
        f"python3 -m edgebase setup --scope both --agents {agents_arg} &&\n"
        f"python3 -m edgebase doctor --scope both --agents {agents_arg} &&\n"
        "python3 -m edgebase status --json\n"
        "```\n\n"
        "After setup, report exactly which capabilities became automatic:\n"
        "- MCP tools and prompts, including `edgebase_context`, `edgebase_goal`, and `edgebase_radius`\n"
        "- prompt-time Goal Capsule creation where hooks are supported and trusted\n"
        "- pre-edit Work Contract checks where hooks are supported and trusted\n"
        "- post-edit refresh, checkpoints, and Patch Passport finish flow where hooks are supported\n"
        "- slash commands or skills installed for the selected agent host\n\n"
        "Rules:\n"
        "- Do not add generated architecture summaries to AGENTS.md.\n"
        "- Do not remove existing agent config.\n"
        "- Do not commit unless I explicitly ask.\n"
        "- Explain that Edgebase is on by default after setup, can be disabled with "
        "`python3 -m edgebase disable --scope both`, and can be bypassed for one emergency session with "
        "`EDGEBASE_PREFLIGHT=off`.\n\n"
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
