# Agent Client Setup

Edgebase is a local stdio MCP server. It exposes these agent-facing tools:

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
- `.edgebase/graphs/latest.html`, `.json`, `.dot`: rebuildable local visualization artifacts written by agent-facing hooks and MCP calls.
- `.git/info/exclude`: local ignore entry for `.edgebase/`; committed `.gitignore` is not modified.
- `AGENTS.md`: marker-bounded instructions that tell agents to use Edgebase automatically when broad code context is needed.
- `.mcp.json`: Claude Code project MCP server.
- `.claude/settings.json`: Claude Code automatic UserPromptSubmit context hook plus SessionStart, PreToolUse, and async PostToolUse hooks.
- `.claude/skills/edgebase/SKILL.md`: Claude Code project skill exposed as `/edgebase <task>`.
- `.claude/skills/goal/SKILL.md`: Claude Code project skill exposed as `/goal <goal>`.
- `.codex/config.toml` and/or `~/.codex/config.toml`: Codex MCP server.
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
- `UserPromptSubmit`: injects a compact Edgebase capsule next to likely coding prompts before Claude starts exploring.
- `PreToolUse`: injects a pre-edit Work Contract before Write/Edit/MultiEdit.
- `PostToolUse`: asynchronously reindexes files, updates local graph artifacts, and reports edit deltas after Write/Edit/MultiEdit.

It also writes a project skill:

```text
/edgebase <task>
/goal <goal>
```

Use `/edgebase` when you want a compact read set. Use `/goal` when you want an executable Goal Capsule with blast radius, protected areas, required checks, and a patch contract. Normal coding prompts do not need the phrase "Use edgebase_context"; the prompt hook supplies context automatically when the prompt looks like implementation, debugging, review, or investigation work.

Useful checks:

```bash
claude mcp list
claude mcp get edgebase
```

Claude Code may ask for approval before using a project-scoped `.mcp.json` server.

## Codex

Edgebase writes TOML:

```toml
[mcp_servers.edgebase]
command = "/usr/bin/python3"
args = ["-m", "edgebase", "mcp", "--root", "/path/to/repo"]
enabled = true
```

Useful check:

```bash
codex mcp list
codex mcp get edgebase
```

The currently verified Codex CLI path reads `~/.codex/config.toml`, so the frictionless install command uses `--scope both`. Edgebase also writes `.codex/config.toml` for project-local workflows, but use global or both scope when you want `codex mcp list` to confirm the server immediately.

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

Cursor documents that Composer Agent automatically uses relevant MCP tools listed under available tools. Edgebase also writes the `AGENTS.md` marker so the agent has a repo-local instruction to route broad structural context through `edgebase_context` or `edgebase_goal` and cross-session continuity through the Context Branch tools.

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
python3 -m edgebase checkpoint "understood password reset flow"
python3 -m edgebase fork-plan "try reset token session boundary"
python3 -m edgebase resume
```

MCP clients that expose prompts can also use the MCP prompts named `edgebase` and `goal`, which return the same source-backed capsule surfaces in prompt form. Context Branches are exposed as MCP tools so agents can checkpoint, fork a plan, or resume without shell access when their client supports tool calls.

When hooks or MCP calls run, Edgebase may refresh `.edgebase/graphs/latest.html`, `.edgebase/graphs/latest.json`, and `.edgebase/graphs/latest.dot`. Agent responses surface those local paths as optional visual aids; Edgebase does not add a raw graph dump to the context payload.

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
