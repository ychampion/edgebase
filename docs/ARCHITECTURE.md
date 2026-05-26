# Architecture

Edgebase has one job: return the smallest useful, source-backed work contract for a coding task.

```text
git working tree + git history
        |
        v
language extractors
        |
        v
.edgebase/index.sqlite3
        |
        v
context ranker
        |
        v
edgebase_context(task, changed_files?, budget?)
edgebase_goal(goal, changed_files?, budget?)
edgebase_checkpoint(message, budget?)
edgebase_fork_plan(message, from_id?, branch?, path?, allow_dirty?, budget?)
edgebase_resume(snapshot_id?)
        |
        v
.edgebase/graphs/latest.html|json|dot
```

## Design Constraints

- **Local first:** no Docker, Neo4j, cloud service, or API key for the normal path.
- **Git native:** the index is a cache; git and the working tree remain the source of truth.
- **Agent shaped:** expose small task-router tools, not a pile of low-level graph queries.
- **Honest uncertainty:** every edge carries extractor, source path, source line, commit, freshness, and confidence.
- **Reversible setup:** `edgebase disable` removes or disables generated integrations.

## Graph Cache

The cache lives at `.edgebase/index.sqlite3`.

Tables:

- `files`: repository-relative path, language, module, content hash, test marker, indexed commit.
- `symbols`: name, kind, file, line, signature, exported marker, confidence.
- `edges`: typed relationships with source path, line, extractor, confidence, commit, freshness.
- `file_metrics`: owner, author counts, recent commits, churn count.

The cache can be deleted at any time and rebuilt with:

```bash
python3 -m edgebase index
```

## Graph Artifacts

Hooks and MCP calls can render a narrow, file-level graph from the same SQLite cache. Artifacts are written locally under `.edgebase/graphs/latest.html`, `.json`, and `.dot`.

The HTML artifact is self-contained and static: no CDN, no external assets, no browser launch. The artifact path is surfaced to agents as an optional visual aid, while raw graph data stays out of compact context capsules.

## Extraction

Current extractors are deliberately conservative:

- Python uses `ast` for imports, classes, functions, and call-name extraction.
- JavaScript/TypeScript use shallow regex extraction and lower confidence.
- Go, Rust, and other languages use shallow symbol/import patterns.
- Tests are inferred from common test path and filename conventions.

Dynamic call edges are not presented as facts. They are low-confidence leads unless the extractor can prove more.

## Freshness

Freshness is checked with file hashes, git HEAD, the working tree fingerprint, and a short-lived preflight state file. A context or goal capsule reports stale files when the working tree no longer matches the indexed hash. A preflight capsule is considered stale when it expires, HEAD changes, the working tree changes after recording, or the index reports stale files.

Freshness paths:

- `edgebase index`: full rebuild.
- `edgebase index --changed`: incremental refresh for git-changed files.
- Git `post-commit` hook: refresh after commits.
- Claude Code and Codex `UserPromptSubmit` hooks: record and inject a Goal Capsule before the agent plans.
- Claude Code and Codex `PreToolUse` hooks: block Write/Edit/MultiEdit when no fresh Goal Capsule exists.
- Claude Code and Codex `PostToolUse` hooks: async refresh, edit-delta reporting, and graph artifact update after Write/Edit/MultiEdit.
- Claude Code `PreCompact` and Codex `PreCompact` hooks: save `.edgebase/checkpoints/latest.md` before compaction.
- Claude Code `SessionEnd` and Codex `Stop` hooks: save `.edgebase/passports/latest.md` and `.json`.
- MCP server startup: indexes the repo automatically if no cache exists.

## Context Ranking

`edgebase_context` ranks files using:

- explicit `changed_files`
- task-token matches against paths, modules, symbols, and edges
- graph neighbors of changed files
- inferred tests
- churn hotspots

The returned capsule includes:

- high-signal files
- relevant symbols
- source-backed relationships
- stale-file warnings
- next reads
- machine-readable summary

## Goal Capsules

`edgebase_goal` and `edgebase goal` use the same graph ranking path, then reshape the result into an executable work contract:

- Goal Capsule Markdown for agents and humans.
- Work Contract JSON for structured consumers.
- stable `repo_commit` and `worktree_fingerprint`.
- read-first files, blast radius, protected areas, tests, risks, uncertainties, and provenance.

`edgebase passport` runs after edits and produces a Patch Passport from the current diff plus explicit test evidence. Edgebase records only tests supplied with `--test`; it never infers that a check passed.

`edgebase checkpoint`, `edgebase fork-plan`, and `edgebase resume` preserve compact context across compaction, handoff, and git worktree branching. They reuse the context ranker rather than adding a separate memory store.

## Agent Integration Boundary

Edgebase does not try to control agents. It gives them a reliable tool, a small instruction marker, and client-specific automation where the client has documented hooks:

```text
Use injected Edgebase context when present; otherwise call edgebase_context or edgebase_goal before broad exploration or edits.
```

Claude Code has documented prompt and tool hooks, so Edgebase provides:

- `UserPromptSubmit`: Goal Capsule before Claude plans.
- `SessionStart`: freshness summary when a session opens.
- `PreToolUse`: stale-capsule block before Write/Edit/MultiEdit.
- `PostToolUse`: async refresh and edit delta after Write/Edit/MultiEdit.
- `PreCompact`: context checkpoint before compaction.
- `SessionEnd`: Patch Passport at session end.
- project skill `/edgebase <task>` for explicit manual refresh.
- project skill `/goal <goal>` for explicit Goal Capsules.

Codex setup is MCP plus project-scoped hooks and skills. Edgebase writes `.codex/config.toml`, `[features] hooks = true`, `.codex/hooks.json`, `.agents/skills/edgebase`, and `.agents/skills/goal`. When project hooks are trusted, Codex receives the same preflight gate: prompt-time capsule, stale edit block, post-edit refresh, pre-compact checkpoint, and stop-time Patch Passport.

Cursor, Gemini CLI, OpenCode, and Windsurf are MCP-first. For those clients, setup writes MCP config and an `AGENTS.md` marker that instructs the agent to route broad structural context through Edgebase automatically. Edgebase also exposes MCP prompts named `edgebase` and `goal` for clients that surface prompt menus.

MCP tool and prompt responses also refresh graph artifacts and return the local artifact paths when rendering succeeds. Rendering failures are non-fatal; Edgebase must still return the context or Goal Capsule.

## Failure Modes

Expected safe failures:

- missing MCP client binary: config can still be written and later used by that client
- stale index: capsule reports stale files and suggests refresh
- unsupported language: file still appears as source, but relationships may be sparse
- dynamic-language calls: low confidence
- invalid existing JSON config: setup refuses to overwrite

Unsafe failures Edgebase must avoid:

- silently overwriting unrelated agent config
- requiring external services for local use
- presenting inferred edges as certain
- bloating agent context with raw graph dumps
