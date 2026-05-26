# Agent Client Setup

Edgebase is a local stdio MCP server plus project-scoped hook/skill setup for clients that support it. It exposes five agent-facing MCP tools:

```text
edgebase_context(task, changed_files?, budget?)
edgebase_goal(goal, changed_files?, budget?)
edgebase_checkpoint(message, budget?)
edgebase_fork_plan(message, from_id?, branch?, path?, allow_dirty?, budget?)
edgebase_resume(snapshot_id?)
```

The normal installation path is:

```bash
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both
```

Default state after setup: **on** for selected agents. Turn it off with:

```bash
python3 -m edgebase disable --scope both
```

Check the local installation:

```bash
python3 -m edgebase doctor --scope both
```

## Prompt To Paste Into Agents

```text
Install Edgebase for this repository. Run:
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both

Explain the changes before you make unrelated edits. After setup, verify with:
python3 -m edgebase doctor --scope both

Do not add generated architecture summaries to AGENTS.md. Edgebase keeps AGENTS.md minimal, installs MCP server config, and enables automatic context routing where the agent client supports it.
```

## What Edgebase Changes

Setup writes or updates only local configuration files:

- `.edgebase/index.sqlite3`: rebuildable local cache, ignored by git.
- `.edgebase/graphs/latest.html`, `.json`, and `.dot`: optional local graph artifacts refreshed by hooks and MCP calls, ignored by git.
- `.git/info/exclude`: local ignore entry for `.edgebase/`; committed `.gitignore` is not modified.
- `AGENTS.md`: marker-bounded instructions that tell agents to use Edgebase automatically when broad code context is needed.
- `.mcp.json`: Claude Code project MCP server.
- `.claude/settings.json`: Claude Code SessionStart, UserPromptSubmit, PreToolUse, async PostToolUse, PreCompact, and SessionEnd hooks.
- `.claude/skills/edgebase/SKILL.md`: Claude Code project skill exposed as `/edgebase <task>`.
- `.claude/skills/goal/SKILL.md`: Claude Code project skill exposed as `/goal <goal>`.
- `.codex/config.toml` and/or `~/.codex/config.toml`: Codex MCP server plus project `[features] hooks = true`.
- `.codex/hooks.json`: Codex project hook commands for the preflight gate.
- `.agents/skills/edgebase/SKILL.md`: Codex project skill exposed as `/edgebase <task>` where project skills are enabled.
- `.agents/skills/goal/SKILL.md`: Codex project skill exposed as `/goal <goal>`.
- `.cursor/mcp.json` and/or `~/.cursor/mcp.json`: Cursor MCP server.
- `.gemini/settings.json` and/or `~/.gemini/settings.json`: Gemini CLI MCP server.
- `.opencode.json` and/or `~/.opencode.json`: OpenCode local MCP server.
- `~/.codeium/windsurf/mcp_config.json`: Windsurf Cascade MCP server.
- `.git/hooks/post-commit`: refreshes the Edgebase index after commits.

All generated config points at the Python interpreter that ran setup, with `-m edgebase`, so GUI-launched agents do not depend on shell PATH.

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

It also writes a project skill:

```text
/edgebase <task>
/goal <goal>
```

Use `/edgebase` when you want a compact read set. Use `/goal` when you want an executable Goal Capsule with blast radius, protected areas, required checks, and a patch contract. Normal coding prompts do not need the phrase "Use edgebase_context"; the prompt hook records and supplies the Goal Capsule automatically when the prompt looks like implementation, debugging, review, or investigation work.

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
    {"event": "SessionStart", "command": "/usr/bin/python3 -m edgebase hooks codex-session-start --root /path/to/repo"},
    {"event": "UserPromptSubmit", "command": "/usr/bin/python3 -m edgebase hooks codex-user-prompt-submit --root /path/to/repo"},
    {"event": "PreToolUse", "command": "/usr/bin/python3 -m edgebase hooks codex-pre-tool-use --root /path/to/repo"},
    {"event": "PostToolUse", "command": "/usr/bin/python3 -m edgebase hooks codex-post-tool-use --root /path/to/repo"},
    {"event": "PreCompact", "command": "/usr/bin/python3 -m edgebase hooks codex-pre-compact --root /path/to/repo"},
    {"event": "Stop", "command": "/usr/bin/python3 -m edgebase hooks codex-stop --root /path/to/repo"}
  ]
}
```

And project skills:

```text
/edgebase <task>
/goal <goal>
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

OpenCode supports disabling MCP servers with `enabled: false`; `edgebase disable` uses that path.

## Windsurf

Windsurf Cascade uses the global MCP config:

```text
~/.codeium/windsurf/mcp_config.json
```

Project scope is skipped for Windsurf because Windsurf's documented config path is global.

## Manual Use

When MCP is unavailable:

```bash
python3 -m edgebase context "implement password reset" --changed-file src/auth.py --budget 1200
python3 -m edgebase goal "implement password reset without regressing login" --changed-file src/auth.py --budget 1200
python3 -m edgebase passport "implement password reset without regressing login" --test "python3 -m unittest -v: pass"
python3 -m edgebase preflight status
python3 -m edgebase preflight refresh "implement password reset without regressing login"
python3 -m edgebase checkpoint "handoff after password reset"
python3 -m edgebase resume
```

MCP clients that expose prompts can also use the MCP prompts named `edgebase` and `goal`, which return the same source-backed capsule surfaces in prompt form.

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
