# Agent Client Setup

Edgebase is a local stdio MCP server. It exposes one tool:

```text
edgebase_context(task, changed_files?, budget?)
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

Use edgebase_context before broad file exploration or edits. If MCP is unavailable, use:
python3 -m edgebase context "<task>" --budget 1200
```

## What Edgebase Changes

Setup writes or updates only local configuration files:

- `.edgebase/index.sqlite3`: rebuildable local cache, ignored by git.
- `AGENTS.md`: marker-bounded instructions that tell agents when to use Edgebase.
- `.mcp.json`: Claude Code project MCP server.
- `.claude/settings.json`: Claude Code SessionStart and async PostToolUse hooks.
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
- `PostToolUse`: asynchronously reindexes files after Write/Edit/MultiEdit.

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

Cursor uses MCP tools when the agent decides they are relevant. If it does not, prompt:

```text
Use edgebase_context before editing.
```

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
```

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
