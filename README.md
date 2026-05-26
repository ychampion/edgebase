# Edgebase

Edgebase is a local, git-native context substrate for coding agents. It indexes a repository into a small SQLite graph, records provenance for every fact, and exposes one primary agent tool:

```text
edgebase_context(task, changed_files?, budget?)
```

The goal is not to dump a code graph into an agent. The goal is to return a compact, source-backed context capsule right before an agent edits code.

## Install

Paste this in the repository you want your coding agents to understand:

```bash
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both
```

Then restart Claude Code, Codex, Cursor, Gemini CLI, OpenCode, or Windsurf and ask:

```text
Use edgebase_context for this task before editing.
```

For local development on Edgebase itself:

```bash
python3 -m pip install -e .
edgebase setup --scope project
python3 -m unittest
```

## What It Indexes

- Files, modules, exported symbols, imports, and conservative call edges
- Test files and inferred `TESTS` relationships
- Git owners, recent commits, and churn hotspots
- Provenance for graph facts: path, line, extractor, confidence, commit, freshness

## Quick Start

```bash
python -m pip install -e .
edgebase setup --scope project
edgebase context "change the auth login flow" --budget 1200
edgebase mcp
```

`edgebase setup` indexes the repo, creates minimal agent guidance, and configures supported MCP clients where possible. It never needs Docker, Neo4j, cloud services, or API keys.

## MCP

Edgebase runs as a local stdio MCP server:

```bash
edgebase mcp --root /path/to/repo
```

The server exposes one tool, `edgebase_context`, with this input:

```json
{
  "task": "refactor the login controller",
  "changed_files": ["src/auth/login.py"],
  "budget": 1200
}
```

## Supported Agents

`edgebase setup --scope both` configures:

- Claude Code: project `.mcp.json`, plus optional SessionStart/PostToolUse freshness hooks
- Codex: `.codex/config.toml` and `~/.codex/config.toml`
- Cursor: `.cursor/mcp.json` and `~/.cursor/mcp.json`
- Gemini CLI: `.gemini/settings.json` and `~/.gemini/settings.json`
- OpenCode: `.opencode.json` and `~/.opencode.json`
- Windsurf: `~/.codeium/windsurf/mcp_config.json`

Use a narrower install when you only want project-local files:

```bash
edgebase setup --scope project --agents claude,codex,cursor,gemini,opencode
```

Use an absolute command if your agent process cannot see `edgebase` on `PATH`:

```bash
edgebase setup --scope both --command "$(python3 -c 'import shutil; print(shutil.which("edgebase") or "edgebase")')"
```

## Hooks

Edgebase starts with practical hooks rather than a custom runtime:

```bash
edgebase install-hooks --git --claude
```

- Git `post-commit` refreshes the graph after commits.
- Claude Code `SessionStart` reports graph freshness.
- Claude Code `PostToolUse` reindexes edited files and can feed a short freshness note back into the session.

## Benchmarks

The benchmark harness is intentionally evidence-first:

```bash
edgebase benchmark --repo /path/to/repo --tasks benchmarks/tasks.example.jsonl --out results.json
```

It can compare Edgebase against a plain `rg` baseline immediately. Third-party competitors are opt-in through command templates so results are reproducible without bundling external tools:

- `EDGEBASE_BENCH_CODEGRAPHCONTEXT_CMD`
- `EDGEBASE_BENCH_CODEBASE_MEMORY_CMD`
- `EDGEBASE_BENCH_GITNEXUS_CMD`

## Design Rules

- Local first: no Docker, Neo4j, cloud, or API keys for the normal path.
- Rebuildable: `.edgebase/index.sqlite3` is cache, not source of truth.
- Honest confidence: dynamic call edges are low confidence unless the extractor can prove more.
- Small surface: one task-router MCP tool is preferred over many graph tools.
- Minimal instructions: `AGENTS.md` should hold non-inferable rules and point to Edgebase for fresh structure.

## Current Status

This is an alpha OSS prototype. Python extraction is strongest because it uses `ast`; JavaScript/TypeScript, Go, and Rust extraction is intentionally conservative and confidence-scored. The benchmark harness is included so improvements can be judged against plain search and competing MCP graph tools.
