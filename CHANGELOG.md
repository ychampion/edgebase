# Changelog

## 0.1.1 - 2026-05-26

### Added

- Production setup diagnostics with `edgebase doctor`.
- Reversible integrations with `edgebase disable`.
- Marker-bounded `AGENTS.md` instructions for automatic agent adoption.
- More complete agent client documentation for Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and Windsurf.

### Changed

- MCP configs now default to the Python interpreter that ran setup with `-m edgebase`, avoiding GUI PATH issues.
- Claude Code PostToolUse refresh runs asynchronously.
- CLI `--root` works before or after the subcommand.

## 0.1.0 - 2026-05-26

### Added

- Local SQLite graph index for source files, symbols, imports, call edges, tests, owners, commits, churn, confidence, and freshness.
- `edgebase_context` MCP tool for compact source-backed task context.
- CLI commands for setup, indexing, context capsules, MCP stdio serving, diagnostics, benchmarks, and disabling integrations.
- Agent setup support for Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and Windsurf.
- Claude Code SessionStart and async PostToolUse freshness hooks.
- Validation harness and documentation for benchmark-driven adoption.
