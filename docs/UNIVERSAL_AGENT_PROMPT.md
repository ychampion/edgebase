# Universal Agent Install Prompt

Paste this into Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Windsurf, or any coding agent with shell access.

Use `Repository target: current working directory` when the agent is already inside the repo. Use `Repository target: https://github.com/OWNER/REPO` when the agent should clone a repo first.

## Short Prompt

```text
Set up Edgebase in this repo: current working directory. Install it from https://github.com/ychampion/edgebase, run the local setup and doctor checks yourself, preserve existing agent config, do not commit, and report exactly what changed.
```

For a remote repo:

```text
Set up Edgebase in this repo: https://github.com/OWNER/REPO. Clone it if needed, install Edgebase from https://github.com/ychampion/edgebase, run the local setup and doctor checks yourself, preserve existing agent config, do not commit, and report exactly what changed.
```

## Full Prompt

```text
Set up Edgebase for this repository.

Repository target: current working directory.

Do the setup yourself. Do not ask me to run `edgebase setup` manually.

Steps:
1. Confirm you are inside a git repository. If I gave you a repository URL instead of a local repo, clone it first and cd into it.
2. Run:
   python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
3. Run:
   python3 -m edgebase setup --scope both
4. Run:
   python3 -m edgebase doctor --scope both
5. Report the files Edgebase changed and whether doctor passed.

Rules:
- Do not add generated architecture summaries to AGENTS.md.
- Do not remove existing agent config.
- Do not commit unless I explicitly ask.
- Explain that Edgebase is on by default after setup, can be disabled with `python3 -m edgebase disable --scope both`, and can be bypassed for one emergency session with `EDGEBASE_PREFLIGHT=off`.
```

## What The Agent Should Report Back

The agent should report:

- whether install succeeded
- whether `edgebase doctor --scope both` passed
- which config files were created or updated
- whether Claude Code and Codex hooks were installed
- how to disable Edgebase
- whether the user needs to restart the agent or IDE

## Expected Files

Depending on installed clients and setup scope, Edgebase may create or update:

- `.edgebase/`
- `.git/info/exclude`
- `AGENTS.md`
- `.mcp.json`
- `.claude/settings.json`
- `.claude/skills/edgebase/SKILL.md`
- `.claude/skills/goal/SKILL.md`
- `.codex/config.toml`
- `.codex/hooks.json`
- `.agents/skills/edgebase/SKILL.md`
- `.agents/skills/goal/SKILL.md`
- `.cursor/mcp.json`
- `.gemini/settings.json`
- `.opencode.json`
- global MCP config files under the user's home directory

## After Setup

Most users do not need to run Edgebase manually. Supported hooks and MCP config make agents fetch or record fresh source-backed context before broad exploration or edits.

Manual checks remain available:

```bash
python3 -m edgebase doctor --scope both
python3 -m edgebase preflight status
python3 -m edgebase disable --scope both
```
