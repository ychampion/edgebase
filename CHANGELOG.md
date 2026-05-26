# Changelog

## Unreleased

## 0.1.3 - 2026-05-26

### Added

- Goal Capsules with `edgebase goal`, `edgebase_goal`, and MCP prompt `goal`.
- Pre-edit Work Contracts for Claude Code Write/Edit/MultiEdit hooks.
- Patch Passports with `edgebase passport` for changed files, evidence, explicit tests, risk, and review focus.
- Claude Code project skill `/goal <goal>`.
- Local `.edgebase/graphs/latest.html`, `.json`, and `.dot` artifacts refreshed by hooks and MCP calls for optional visual inspection.
- Edgebase Preflight Gate: Claude Code `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `SessionEnd` hooks now record a Goal Capsule before planning, block broad edits when the capsule is missing or stale, refresh after edits, checkpoint before compaction, and save a Patch Passport at session end.
- Codex project setup now writes MCP config, `[features] hooks = true`, `.codex/hooks.json`, and project skills under `.agents/skills/edgebase` and `.agents/skills/goal`.
- Context branch commands and MCP tools: `edgebase checkpoint`, `edgebase fork-plan`, `edgebase resume`, `edgebase_checkpoint`, `edgebase_fork_plan`, and `edgebase_resume`.
- `edgebase preflight status` and `edgebase preflight refresh` for inspecting or manually refreshing the edit gate.

### Changed

- Claude Code PostToolUse refresh now reports an edit delta with impacted files, checks, and unverified related context.
- Documentation now positions Goal Capsules as the executable work-contract surface.
- `edgebase setup` and `edgebase doctor` now validate automatic preflight integrations for both Claude Code and Codex instead of relying on users to ask for `edgebase_context`.

## 0.1.2 - 2026-05-26

### Added

- Claude Code `UserPromptSubmit` hook that injects compact Edgebase context automatically for likely coding prompts.
- Claude Code project skill `/edgebase <task>` for explicit context refresh without memorizing MCP tool syntax.
- MCP prompt named `edgebase` for clients that expose prompt or slash-command style MCP surfaces.

### Changed

- Setup and docs no longer tell users to paste "Use edgebase_context" before each task.
- Agent instructions now tell agents to use Edgebase automatically when broad structural context is needed.
- Setup now adds `.edgebase/` to the local git exclude file instead of dirtying fresh repos with cache files.
- Generated git and Claude hook commands now use shell-safe quoting for repository paths.
- MCP server version now follows the package version.

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
