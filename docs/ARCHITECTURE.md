# Architecture

Edgebase has one job: return the smallest useful, source-backed context capsule for a coding task.

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
```

## Design Constraints

- **Local first:** no Docker, Neo4j, cloud service, or API key for the normal path.
- **Git native:** the index is a cache; git and the working tree remain the source of truth.
- **Agent shaped:** expose one task-router tool, not a pile of low-level graph queries.
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

## Extraction

Current extractors are deliberately conservative:

- Python uses `ast` for imports, classes, functions, and call-name extraction.
- JavaScript/TypeScript use shallow regex extraction and lower confidence.
- Go, Rust, and other languages use shallow symbol/import patterns.
- Tests are inferred from common test path and filename conventions.

Dynamic call edges are not presented as facts. They are low-confidence leads unless the extractor can prove more.

## Freshness

Freshness is checked with file hashes. A context capsule reports stale files when the working tree no longer matches the indexed hash.

Freshness paths:

- `edgebase index`: full rebuild.
- `edgebase index --changed`: incremental refresh for git-changed files.
- Git `post-commit` hook: refresh after commits.
- Claude Code `UserPromptSubmit` hook: inject a small context capsule next to likely coding prompts.
- Claude Code `PostToolUse` hook: async refresh after Write/Edit/MultiEdit.
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

## Agent Integration Boundary

Edgebase does not try to control agents. It gives them a reliable tool, a small instruction marker, and client-specific automation where the client has documented hooks:

```text
Use injected Edgebase context when present; otherwise call edgebase_context before broad exploration or edits.
```

Claude Code has documented prompt and tool hooks, so Edgebase provides:

- `UserPromptSubmit`: prompt-time context capsule before Claude explores.
- `SessionStart`: freshness summary when a session opens.
- `PostToolUse`: async refresh after Write/Edit/MultiEdit.
- project skill `/edgebase <task>` for explicit manual refresh.

Other clients are MCP-first until their hook semantics are stable and documented. For those clients, setup writes MCP config and an `AGENTS.md` marker that instructs the agent to route broad structural context through Edgebase automatically. Edgebase also exposes an MCP prompt named `edgebase` for clients that surface prompt menus.

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
