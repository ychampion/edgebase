# Agent Client Setup

Edgebase exposes one MCP tool, `edgebase_context`, and a CLI fallback:

```bash
edgebase context "<task>" --budget 1200
```

## One Command

Run this from the repository you want agents to work on:

```bash
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both
```

Restart your agent or IDE after setup.

## Claude Code

Project setup writes `.mcp.json` and Claude freshness hooks:

```bash
edgebase setup --agents claude --scope project
```

Claude Code will ask for approval before using project-scoped MCP servers from `.mcp.json`.

## Codex

Project setup writes `.codex/config.toml`; global setup writes `~/.codex/config.toml`:

```bash
edgebase setup --agents codex --scope both
codex mcp list
```

## Cursor

Project setup writes `.cursor/mcp.json`; global setup writes `~/.cursor/mcp.json`:

```bash
edgebase setup --agents cursor --scope both
```

## Gemini CLI

Project setup writes `.gemini/settings.json`; global setup writes `~/.gemini/settings.json`:

```bash
edgebase setup --agents gemini --scope both
```

## OpenCode

Project setup writes `.opencode.json`; global setup writes `~/.opencode.json`:

```bash
edgebase setup --agents opencode --scope both
```

## Windsurf

Windsurf uses a global MCP config, so use global or both scope:

```bash
edgebase setup --agents windsurf --scope global
```

## Prompt To Paste Into Agents

```text
Install and configure Edgebase for this repo. Run:
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both

After setup, use the edgebase_context MCP tool before broad file exploration or edits.
```

## Troubleshooting

- If an agent cannot start the MCP server, rerun setup with `--command /absolute/path/to/edgebase`.
- If the context says files are stale, run `edgebase index --changed` or `edgebase index`.
- If your repo already has `AGENTS.md`, setup creates `EDGEBASE.md` instead of overwriting it.
