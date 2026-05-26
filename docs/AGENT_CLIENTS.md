# Agent Client Setup

Edgebase is a local stdio MCP server plus project-scoped hook/skill setup for clients that support it. It exposes six agent-facing MCP tools:

```text
edgebase_context(task, changed_files?, budget?)
edgebase_goal(goal, changed_files?, budget?)
edgebase_radius(targets?, goal?, changed_files?, budget?)
edgebase_checkpoint(message, budget?)
edgebase_fork_plan(message, from_id?, branch?, path?, allow_dirty?, budget?)
edgebase_resume(snapshot_id?)
```

The normal installation path is a prompt, not a command the user has to run manually. Paste this into the coding agent that is already working in the repository:

```text
Set up Edgebase in this repo: current working directory. Install it from https://github.com/ychampion/edgebase, run the local setup and doctor checks yourself, preserve existing agent config, do not commit, and report exactly what changed.
```

For stricter setup, paste the full prompt:

```text
Set up Edgebase for this repository.

Repository target: current working directory.

Do the setup yourself. Do not ask me to run `python3 -m edgebase setup` manually.

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

For a remote repository, replace the target line with `Repository target: https://github.com/OWNER/REPO`.

Default state after setup: **on** for selected agents. In Claude Code, Codex, and clients that expose MCP prompts as slash commands, use:

```text
/edgebase "implement password reset"
/edgebase-goal "implement password reset without regressing login"
/edgebase-radius "src/auth/login.py" --goal "implement password reset"
/edgebase-preflight-status
/edgebase-checkpoint "handoff after password reset"
/edgebase-doctor --scope both
```

The shell fallback commands are:

```bash
python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
python3 -m edgebase setup --scope both
python3 -m edgebase doctor --scope both
```

Turn it off with:

```bash
python3 -m edgebase disable --scope both
```

See [Universal Agent Install Prompt](UNIVERSAL_AGENT_PROMPT.md) for a standalone copy/paste prompt.

## What Edgebase Changes

Setup writes or updates only local configuration files:

- `.edgebase/index.sqlite3`: rebuildable local cache, ignored by git.
- `.edgebase/graphs/latest.html`, `.json`, and `.dot`: optional local graph artifacts refreshed by hooks and MCP calls, ignored by git.
- `.git/info/exclude`: local ignore entry for `.edgebase/`; committed `.gitignore` is not modified.
- `AGENTS.md`: marker-bounded instructions that tell agents to use Edgebase automatically when broad code context is needed.
- `.mcp.json`: Claude Code project MCP server.
- `.claude/settings.json`: Claude Code SessionStart, UserPromptSubmit, PreToolUse, async PostToolUse, PreCompact, and SessionEnd hooks.
- `.claude/skills/edgebase/SKILL.md`: Claude Code project skill exposed as `/edgebase <task>`.
- `.claude/skills/edgebase-goal/SKILL.md`: Claude Code project skill exposed as `/edgebase-goal <goal>`.
- `.claude/skills/edgebase-*/SKILL.md`: Claude Code project skills exposed as `/edgebase-*` operational commands such as `/edgebase-radius`, `/edgebase-checkpoint`, `/edgebase-preflight-status`, `/edgebase-index`, and `/edgebase-doctor`.
- `.claude/skills/goal/SKILL.md`: Claude Code compatibility skill exposed as `/goal <goal>`.
- `.codex/config.toml` and/or `~/.codex/config.toml`: Codex MCP server plus project `[features] hooks = true`.
- `.codex/hooks.json`: Codex project hook commands for the preflight gate.
- `.agents/skills/edgebase/SKILL.md`: Codex project skill exposed as `/edgebase <task>` where project skills are enabled.
- `.agents/skills/edgebase-goal/SKILL.md`: Codex project skill exposed as `/edgebase-goal <goal>` where project skills are enabled.
- `.agents/skills/edgebase-*/SKILL.md`: Codex project skills exposed as `/edgebase-*` operational commands where project skills are enabled.
- `.agents/skills/goal/SKILL.md`: Codex compatibility skill exposed as `/goal <goal>`.
- `.cursor/mcp.json` and/or `~/.cursor/mcp.json`: Cursor MCP server.
- `.gemini/settings.json` and/or `~/.gemini/settings.json`: Gemini CLI MCP server.
- `.opencode.json` and/or `~/.opencode.json`: OpenCode local MCP server.
- `~/.codeium/windsurf/mcp_config.json`: Windsurf Cascade MCP server.
- `.git/hooks/post-commit`: refreshes the Edgebase index after commits.

All generated config points at the Python interpreter that ran setup, so GUI-launched agents do not depend on shell PATH.

## Claude Code

Edgebase writes project-scoped `.mcp.json`:

```json
{
  "mcpServers": {
    "edgebase": {
      "command": "/usr/bin/python3",
      "args": ["-m", "edgebase", "mcp", "--root", "/path/to/repo"],
      "env": {}
    }
  }
}
```

It also writes `.claude/settings.json` hooks:

- `SessionStart`: adds a short freshness note to Claude's context.
- `UserPromptSubmit`: records a Goal Capsule and injects it next to likely coding prompts before Claude starts planning.
- `PreToolUse`: blocks Write/Edit/MultiEdit when no fresh Goal Capsule exists.
- `PostToolUse`: asynchronously reindexes files, reports edit deltas, and refreshes local graph artifacts after Write/Edit/MultiEdit.
- `PreCompact`: saves `.edgebase/checkpoints/latest.md` before compaction.
- `SessionEnd`: saves `.edgebase/passports/latest.md` and `.json` at session end.

It also writes project skills:

```text
/edgebase <task>
/edgebase-goal <goal>
/goal <goal>
/edgebase-radius <file-or-plan> [--goal "<plan>"]
/edgebase-checkpoint <message>
/edgebase-resume [snapshot id]
/edgebase-fork-plan <objective>
/edgebase-passport <goal> --test "command: result"
/edgebase-preflight-status
/edgebase-preflight-refresh <goal>
/edgebase-index --changed
/edgebase-stats
/edgebase-doctor --scope project
/edgebase-setup --scope both
/edgebase-disable --scope both
/edgebase-version
```

Use `/edgebase` when you want a compact read set. Use `/edgebase-goal` when you want an executable Goal Capsule with blast radius, protected areas, required checks, and a patch contract. Use `/edgebase-radius` when a plan names a file and you want likely affected routes, migration paths, tests, downstream modules, and side-effect risks before editing. Radius output is advisory; it tells the agent what may need inspection, not what must be changed. Use the other `/edgebase-*` commands for ordinary checkpoint, resume, preflight, index, doctor, setup, disable, and version tasks from inside the agent. `/goal` is kept as a shorter compatibility alias. Normal coding prompts do not need the phrase "Use edgebase_context"; the prompt hook records and supplies the Goal Capsule automatically when the prompt looks like implementation, debugging, review, or investigation work.

Hook and MCP responses may include `.edgebase/graphs/latest.*` paths. Treat them as local visual aids for relationship inspection; do not paste raw graph JSON or DOT back into agent context.

Useful checks:

```bash
claude mcp list
claude mcp get edgebase
```

Claude Code may ask for approval before using a project-scoped `.mcp.json` server.

## Codex

Edgebase writes TOML:

```toml
[features]
hooks = true

[mcp_servers.edgebase]
command = "/usr/bin/python3"
args = ["-m", "edgebase", "mcp", "--root", "/path/to/repo"]
enabled = true
```

Project setup also writes `.codex/hooks.json`:

```json
{
  "hooks": [
    {"event": "SessionStart", "command": "<generated Edgebase session-start hook command>"},
    {"event": "UserPromptSubmit", "command": "<generated Edgebase prompt hook command>"},
    {"event": "PreToolUse", "command": "<generated Edgebase pre-tool hook command>"},
    {"event": "PostToolUse", "command": "<generated Edgebase post-tool hook command>"},
    {"event": "PreCompact", "command": "<generated Edgebase pre-compact hook command>"},
    {"event": "Stop", "command": "<generated Edgebase stop hook command>"}
  ]
}
```

Those hook entries intentionally use the Python interpreter that ran setup; they are generated runtime config so GUI-launched agents do not depend on shell `PATH`. User-facing commands after setup are the `/edgebase-*` skills or the `python3 -m edgebase ...` module fallback.

And project skills:

```text
/edgebase <task>
/edgebase-goal <goal>
/goal <goal>
/edgebase-radius <file-or-plan> [--goal "<plan>"]
/edgebase-checkpoint <message>
/edgebase-resume [snapshot id]
/edgebase-fork-plan <objective>
/edgebase-passport <goal> --test "command: result"
/edgebase-preflight-status
/edgebase-preflight-refresh <goal>
/edgebase-index --changed
/edgebase-stats
/edgebase-doctor --scope project
/edgebase-setup --scope both
/edgebase-disable --scope both
/edgebase-version
```

Useful check:

```bash
codex mcp list
codex mcp get edgebase
python3 -m edgebase doctor --agents codex --scope project
```

The currently verified Codex CLI path reads `~/.codex/config.toml`, so the frictionless install command uses `--scope both`. Edgebase also writes `.codex/config.toml`, `.codex/hooks.json`, and `.agents/skills/*` for project-local workflows. When Codex trusts project hooks, the hook path gives the same preflight behavior as Claude Code: Goal Capsule before planning, edit block if stale, refresh after edit, checkpoint before compaction, and Patch Passport on stop.

## Cursor

Edgebase writes `.cursor/mcp.json` and/or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "edgebase": {
      "command": "/usr/bin/python3",
      "args": ["-m", "edgebase", "mcp", "--root", "/path/to/repo"],
      "env": {}
    }
  }
}
```

Cursor documents that Composer Agent automatically uses relevant MCP tools listed under available tools. Edgebase also writes the `AGENTS.md` marker so the agent has a repo-local instruction to route broad structural context through `edgebase_context` or `edgebase_goal`.

## Gemini CLI

Edgebase writes `.gemini/settings.json` and/or `~/.gemini/settings.json` under `mcpServers`.

Useful checks:

```bash
gemini mcp list
```

If a Gemini install has an `mcp.allowed` allowlist, include `edgebase` there.

## OpenCode

Edgebase writes:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "edgebase": {
      "type": "local",
      "command": ["/usr/bin/python3", "-m", "edgebase", "mcp", "--root", "/path/to/repo"],
      "enabled": true
    }
  }
}
```

OpenCode supports disabling MCP servers with `enabled: false`; `python3 -m edgebase disable` uses that path.

## Windsurf

Windsurf Cascade uses the global MCP config:

```text
~/.codeium/windsurf/mcp_config.json
```

Project scope is skipped for Windsurf because Windsurf's documented config path is global.

## Manual Use

Inside Claude Code, Codex, or any client that exposes project skills or MCP prompts:

```text
/edgebase "implement password reset"
/edgebase-goal "implement password reset without regressing login"
/edgebase-radius "src/auth/login.py" --goal "implement password reset"
/edgebase-passport "implement password reset without regressing login" --test "python3 -m unittest -v: pass"
/edgebase-preflight-status
/edgebase-preflight-refresh "implement password reset without regressing login"
/edgebase-checkpoint "handoff after password reset"
/edgebase-resume
/edgebase-index --changed
/edgebase-disable --scope both
```

When slash commands and MCP are unavailable, use the console script fallback:

```bash
python3 -m edgebase context "implement password reset" --changed-file src/auth.py --budget 1200
python3 -m edgebase goal "implement password reset without regressing login" --changed-file src/auth.py --budget 1200
python3 -m edgebase radius src/auth.py --goal "implement password reset without regressing login"
python3 -m edgebase passport "implement password reset without regressing login" --test "python3 -m unittest -v: pass"
python3 -m edgebase preflight status
python3 -m edgebase preflight refresh "implement password reset without regressing login"
python3 -m edgebase checkpoint "handoff after password reset"
python3 -m edgebase resume
```

MCP clients that expose prompts can also use the MCP prompts named `edgebase`, `edgebase-goal`, `goal`, and the `edgebase-*` aliases, which return the same source-backed capsule and command surfaces in prompt form.

MCP and hook paths refresh `.edgebase/graphs/latest.html`, `.json`, and `.dot` automatically. Open or inspect those local artifacts only when a visual file relationship view helps the task.

Refresh:

```bash
python3 -m edgebase index --changed
```

Disable:

```bash
python3 -m edgebase disable --scope both
```

Re-enable:

```bash
python3 -m edgebase setup --scope both
```

## Compatibility References

- Claude Code MCP and project `.mcp.json`: https://code.claude.com/docs/en/mcp
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Codex MCP configuration: https://developers.openai.com/learn/docs-mcp
- Cursor MCP configuration: https://docs.cursor.com/context/mcp
- Gemini CLI MCP configuration: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md
- OpenCode MCP configuration: https://opencode.ai/docs/mcp-servers
- Windsurf Cascade MCP configuration: https://docs.windsurf.com/windsurf/cascade/mcp
