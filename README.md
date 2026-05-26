# Edgebase

Edgebase is a local, git-native context layer for coding agents.

It keeps `AGENTS.md` small, indexes the repository into a rebuildable SQLite graph, and exposes one MCP tool that agents can call before editing:

```text
edgebase_context(task, changed_files?, budget?)
```

The output is a compact, source-backed context capsule: high-signal files, symbols, imports, conservative call edges, inferred tests, owners, churn, freshness, and provenance. Edgebase is not a vector database, a Neo4j wrapper, or a generic memory product. It is a small local substrate for answering:

> Given this task and current diff, what context should the agent read before touching code?

## Why This Exists

Modern coding agents are good at exploring code, but their default exploration loop is wasteful:

- search broad terms
- read too many files
- miss nearby tests or owners
- carry stale generated architecture summaries
- repeat the same exploration in every session

Flat instruction files such as `AGENTS.md`, `CLAUDE.md`, and Cursor rules are still useful for human-written project rules. They are a poor place for generated code structure. Edgebase complements those files by keeping generated structure in a local cache and serving fresh context on demand.

## Install

Run this from the repository you want agents to understand:

```bash
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both
```

Then restart your agent or IDE.

Edgebase is enabled by default after setup. To turn it off:

```bash
python3 -m edgebase disable --scope both
```

To check the installation:

```bash
python3 -m edgebase doctor --scope both
```

## Paste This Into Your Agent

If you want Claude Code, Codex, Cursor, Gemini CLI, OpenCode, or Windsurf to install it for you, paste:

```text
Install Edgebase for this repository. Run:
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both

After setup, restart if needed. Before broad code exploration or edits, use the edgebase_context MCP tool with the task and changed files. If MCP is unavailable, run:
python3 -m edgebase context "<task>" --budget 1200
```

## What Setup Changes

`edgebase setup --scope both` makes local, reversible changes:

| Target | Project file | User file | Behavior |
| --- | --- | --- | --- |
| Edgebase cache | `.edgebase/index.sqlite3` | none | Rebuildable local graph cache, ignored by git |
| Agent instructions | `AGENTS.md` marker block | none | Tells agents to call `edgebase_context` before broad exploration |
| Claude Code | `.mcp.json`, `.claude/settings.json` | none by default | MCP server plus SessionStart/PostToolUse freshness hooks |
| Codex | `.codex/config.toml` | `~/.codex/config.toml` | MCP server entry |
| Cursor | `.cursor/mcp.json` | `~/.cursor/mcp.json` | MCP server entry |
| Gemini CLI | `.gemini/settings.json` | `~/.gemini/settings.json` | MCP server entry |
| OpenCode | `.opencode.json` | `~/.opencode.json` | Enabled local MCP server |
| Windsurf | none | `~/.codeium/windsurf/mcp_config.json` | Global MCP server entry |
| Git | `.git/hooks/post-commit` | none | Refreshes the index after commits |

No Docker, cloud service, graph database, or API key is required.

Setup uses the Python interpreter that ran setup, with `-m edgebase`, instead of assuming GUI agents can see `edgebase` on `PATH`.

## Day-To-Day Usage

Most users do not run Edgebase manually after setup. Agents see the MCP tool and the `AGENTS.md` marker.

Useful manual commands:

```bash
python3 -m edgebase context "change the auth login flow" --budget 1200
python3 -m edgebase index --changed
python3 -m edgebase stats
python3 -m edgebase doctor --scope both
python3 -m edgebase disable --scope both
```

If an MCP client does not use the tool automatically, explicitly ask:

```text
Use edgebase_context for this task before editing.
```

## What It Indexes

- Source files and language/module identity
- Exported symbols
- Imports and conservative call edges
- Test files and inferred `TESTS` relationships
- Git owners, recent commits, and churn hotspots
- Provenance for every edge: source path, line, extractor, confidence, commit, and freshness

Dynamic-language call graphs are confidence-scored. Low-confidence call edges are leads, not proof.

## Supported Agents

| Agent | Status | Notes |
| --- | --- | --- |
| Claude Code | Supported | Project `.mcp.json`; async PostToolUse freshness hook; SessionStart context hook |
| Codex | Supported | Global `~/.codex/config.toml` MCP entry is the verified CLI path; verify with `codex mcp list` |
| Cursor | Supported | Project and global `mcp.json`; tools are used when the agent chooses them |
| Gemini CLI | Supported | Project and global `settings.json` with `mcpServers` |
| OpenCode | Supported | Local MCP server under `mcp.edgebase`, `enabled: true` |
| Windsurf | Supported | Global Cascade MCP config |

See [Agent Client Setup](docs/AGENT_CLIENTS.md) for client-specific details and verification commands.

## Architecture

```text
repo files + git history
        |
        v
extractors -> .edgebase/index.sqlite3 -> context ranker -> edgebase_context
```

The cache is rebuildable. Git remains the source of truth.

See [Architecture](docs/ARCHITECTURE.md) and [Validation](docs/VALIDATION.md).

## Benchmarks

Run the included harness:

```bash
python3 -m edgebase benchmark --repo /path/to/repo --tasks benchmarks/tasks.example.jsonl --out results.json
```

It compares Edgebase against a plain `rg` baseline immediately. External competitors are opt-in through command templates:

- `EDGEBASE_BENCH_CODEGRAPHCONTEXT_CMD`
- `EDGEBASE_BENCH_CODEBASE_MEMORY_CMD`
- `EDGEBASE_BENCH_GITNEXUS_CMD`

## Development

```bash
git clone https://github.com/ychampion/edgebase.git
cd edgebase
python3 -m pip install -e .
python3 -m unittest -v
python3 -m compileall -q src tests
```

Smoke-test MCP stdio:

```bash
python3 -m edgebase mcp --root "$PWD"
```

## Project Status

Edgebase is early OSS software. The production bar for this project is:

- local-first install
- no required services
- reversible setup
- honest confidence and provenance
- small agent-facing tool surface
- public benchmark harness

The first mature target is not graph visualization. It is reliably reducing agent search/read overhead without lowering patch quality.
