# Edgebase

Edgebase is a local, git-native work-contract layer for coding agents.

Its flagship feature is **Goal Capsules**: short, executable briefs that tell Codex, Claude Code, Continue-style agents, and human reviewers what to read, what not to touch yet, what tests matter, and what evidence the final patch must include.

```bash
python3 -m edgebase goal "Add passwordless login support without breaking existing OAuth"
```

```text
# Edgebase Goal Capsule

Goal:
Add passwordless login support without breaking existing OAuth

Current hypothesis:
Edgebase ranks `src/auth/login.py` as the strongest lead, with related context in `src/auth/oauth.py`.

Blast radius:
- src/auth/login.py
- src/auth/oauth.py
- tests/auth/test_login.py
- tests/auth/test_oauth.py

Read first:
1. src/auth/login.py
2. src/auth/oauth.py
3. tests/auth/test_login.py

Do not edit yet:
- migrations/*
- provider configs
Reason: no schema or provider-configuration change is proven necessary by the current graph evidence.

Required checks:
- pytest tests/auth/test_login.py
- pytest tests/auth/test_oauth.py

Patch contract:
The final PR must include changed files, rationale, tests run, regression evidence, and unresolved assumptions.
```

Goal Capsules are backed by the local graph index, git state, inferred tests, provenance, and working-tree freshness. They are recorded automatically by supported hooks, exposed as `/goal ...` when a manual command is useful, and called through CLI/MCP before write tools run. The same agent-facing paths also refresh optional local graph artifacts at `.edgebase/graphs/latest.html`, `.json`, and `.dot`; agents surface the paths without dumping raw graph data into context.

Edgebase also keeps `AGENTS.md` small, indexes the repository into a rebuildable SQLite graph, and exposes MCP tools that agents can use before editing:

```text
edgebase_context(task, changed_files?, budget?)
edgebase_goal(goal, changed_files?, budget?)
edgebase_checkpoint(message, budget?)
edgebase_fork_plan(message, from_id?, branch?, path?, allow_dirty?, budget?)
edgebase_resume(snapshot_id?)
```

The companion context output remains a compact, source-backed capsule: high-signal files, symbols, imports, conservative call edges, inferred tests, owners, churn, freshness, and provenance. Claude Code and Codex project setup also get an automatic preflight gate, so users do not need to remember a special phrase before each task.

Edgebase is not a vector database, a Neo4j wrapper, or a generic memory product. It is a small local substrate for answering:

> Given this task and current diff, what context should the agent read before touching code?

With Goal Capsules, Edgebase also answers:

> What is the executable contract for this goal, and what evidence must the patch return?

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

To bypass only the edit gate for one emergency session without removing MCP config:

```bash
EDGEBASE_PREFLIGHT=off
```

## Paste This Into Your Agent

If you want Claude Code, Codex, Cursor, Gemini CLI, OpenCode, or Windsurf to install it for you, paste:

```text
Install Edgebase for this repository. Run:
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git && python3 -m edgebase setup --scope both

After setup, restart if needed and verify with:
python3 -m edgebase doctor --scope both

Do not add generated architecture summaries to AGENTS.md. Edgebase keeps AGENTS.md minimal, installs MCP server config, and enables automatic context routing where the agent client supports it.
```

## What Setup Changes

`edgebase setup --scope both` makes local, reversible changes:

| Target | Project file | User file | Behavior |
| --- | --- | --- | --- |
| Edgebase cache/artifacts | `.edgebase/index.sqlite3`, `.edgebase/graphs/latest.*` | none | Rebuildable local graph cache plus optional visual artifacts, ignored by git |
| Git ignore | `.git/info/exclude` | none | Locally ignores `.edgebase/` without changing committed ignore files |
| Agent instructions | `AGENTS.md` marker block | none | Tells agents to use Edgebase automatically for broad exploration/editing |
| Claude Code | `.mcp.json`, `.claude/settings.json`, `.claude/skills/edgebase/SKILL.md`, `.claude/skills/goal/SKILL.md` | none by default | MCP server, automatic Goal Capsules, PreToolUse stale-capsule blocking, SessionStart/PostToolUse/PreCompact/SessionEnd hooks, `/edgebase` and `/goal` skills |
| Codex | `.codex/config.toml`, `.codex/hooks.json`, `.agents/skills/edgebase/SKILL.md`, `.agents/skills/goal/SKILL.md` | `~/.codex/config.toml` | MCP server entry, project hook config, project skills, AGENTS.md routing |
| Cursor | `.cursor/mcp.json` | `~/.cursor/mcp.json` | MCP server entry |
| Gemini CLI | `.gemini/settings.json` | `~/.gemini/settings.json` | MCP server entry |
| OpenCode | `.opencode.json` | `~/.opencode.json` | Enabled local MCP server |
| Windsurf | none | `~/.codeium/windsurf/mcp_config.json` | Global MCP server entry |
| Git | `.git/hooks/post-commit` | none | Refreshes the index after commits |

No Docker, cloud service, graph database, or API key is required.

Setup uses the Python interpreter that ran setup, with `-m edgebase`, instead of assuming GUI agents can see `edgebase` on `PATH`.

## Day-To-Day Usage

Most users do not run Edgebase manually after setup.

- Claude Code: `UserPromptSubmit` records and injects a Goal Capsule before planning. `PreToolUse` blocks Write/Edit/MultiEdit if no fresh capsule exists. `PostToolUse` refreshes the graph after edits. `PreCompact` saves a checkpoint, and `SessionEnd` saves a Patch Passport. Project skills `/edgebase <task>` and `/goal <goal>` are installed as explicit commands.
- Codex: setup writes MCP config, project `.codex/hooks.json`, `[features] hooks = true`, `.agents/skills/edgebase`, `.agents/skills/goal`, and the `AGENTS.md` marker. Codex uses MCP plus project skills by default; when trusted hook support is active, the same preflight gate records capsules, blocks stale edits, refreshes after edits, checkpoints before compaction, and saves a Patch Passport on stop.
- Cursor, Gemini CLI, OpenCode, and Windsurf: Edgebase installs MCP config and a marker-bounded `AGENTS.md` instruction telling agents to use `edgebase_context` or `edgebase_goal` automatically before broad code exploration or edits. Those MCP calls update `.edgebase/graphs/latest.*` and return the artifact paths.
- Any client: the MCP prompts named `edgebase` and `goal` are available for clients that expose MCP prompts or slash-command-style prompt menus.

Useful manual commands:

```bash
python3 -m edgebase context "change the auth login flow" --budget 1200
python3 -m edgebase goal "add passwordless login without breaking OAuth" --budget 1200
python3 -m edgebase passport "add passwordless login without breaking OAuth" --test "python3 -m unittest -v: pass"
python3 -m edgebase preflight status
python3 -m edgebase checkpoint "handoff after auth refactor"
python3 -m edgebase resume
python3 -m edgebase index --changed
python3 -m edgebase stats
python3 -m edgebase doctor --scope both
python3 -m edgebase disable --scope both
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
| Claude Code | Supported | Project `.mcp.json`; automatic UserPromptSubmit Goal Capsule; PreToolUse stale-capsule block; async PostToolUse refresh; PreCompact checkpoint; SessionEnd Patch Passport; `/edgebase` and `/goal` project skills |
| Codex | Supported | Project `.codex/config.toml`, `.codex/hooks.json`, `.agents/skills`; global `~/.codex/config.toml` MCP entry for CLI discovery; verify with `codex mcp list` and `edgebase doctor` |
| Cursor | Supported | Project and global `mcp.json`; Cursor says Composer Agent automatically uses relevant MCP tools |
| Gemini CLI | Supported | Project and global `settings.json` with `mcpServers` |
| OpenCode | Supported | Local MCP server under `mcp.edgebase`, `enabled: true` |
| Windsurf | Supported | Global Cascade MCP config |

See [Agent Client Setup](docs/AGENT_CLIENTS.md) for client-specific details and verification commands.

## Architecture

```text
repo files + git history
        |
        v
extractors -> .edgebase/index.sqlite3 -> context ranker -> edgebase_context / edgebase_goal
                                           |
                                           v
                                  .edgebase/graphs/latest.*
```

The cache is rebuildable. Git remains the source of truth.

Automation layers:

- prompt hook: Claude Code and trusted Codex hooks record a Goal Capsule before the agent starts planning
- pre-edit hook: Write/Edit/MultiEdit is blocked when no fresh Goal Capsule exists
- edit hook: edited files are reindexed and edit deltas are returned after Write/Edit/MultiEdit
- compaction hook: `.edgebase/checkpoints/latest.md` preserves the active capsule before context compaction
- session-end hook: `.edgebase/passports/latest.md` and `.json` preserve changed files and explicit evidence at stop/session end
- git hook: post-commit refresh keeps the cache aligned with committed changes
- MCP: every supported agent gets `edgebase_context`, `edgebase_goal`, checkpoint, fork-plan, and resume tools over stdio
- graph artifacts: hooks and MCP calls refresh self-contained local HTML, JSON, and DOT files and surface their paths as optional visual aids
- AGENTS marker: static repo instructions stay tiny and tell agents to route structural context through Edgebase

This is not a separate graph UI or a new agent control surface; visualization is kept as a local artifact attached to the existing agent context flow.

See [Architecture](docs/ARCHITECTURE.md) and [Validation](docs/VALIDATION.md).
The release audit for `v0.1.3` is documented in [Release Audit](docs/RELEASE_AUDIT_0.1.3.md).

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
