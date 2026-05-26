<p align="center">
  <img src="assets/edgebase-logo.svg" alt="Edgebase" width="620">
</p>

<p align="center">
  <strong>Automatic work-contract runtime for coding agents.</strong>
</p>

<p align="center">
  <a href="https://github.com/ychampion/edgebase/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ychampion/edgebase/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ychampion/edgebase/releases"><img alt="Release" src="https://img.shields.io/github/v/release/ychampion/edgebase?display_name=tag"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/ychampion/edgebase"></a>
  <a href="https://github.com/ychampion/edgebase"><img alt="Local-first" src="https://img.shields.io/badge/local--first-no%20cloud%20required-1237b7"></a>
</p>

# Edgebase

Edgebase is a local, git-native work-contract runtime for coding agents. Install it once, and supported agents automatically record a source-backed Goal Capsule before work, check the active Work Contract before edits, refresh context after changes, and finish with a Patch Passport.

Its flagship workflow is **Goal Capsules + active Work Contracts + Patch Passports**: short, executable briefs that tell Codex, Claude Code, Cursor-style agents, and human reviewers what to read, what not to touch yet, what tests matter, and what evidence the final patch must include.

## What It Does

- Prints pasteable `edgebase install-prompt` and `edgebase bootstrap` prompts for Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and Windsurf.
- Records a Goal Capsule and active Work Contract before coding agents plan or edit.
- Warns before unsafe edits by default, with opt-in strict blocking for stale contracts or protected paths.
- Shows an advisory Change Blast Radius for likely routes, migrations, tests, downstream modules, and side-effect risks.
- Refreshes the graph after edits, commits, checkouts, merges, rebases, and MCP calls.
- Shows active workflow state with `edgebase status`.
- Writes final Patch Passports with `edgebase finish`.
- Keeps generated structure out of `AGENTS.md`.
- Runs locally with no Docker, cloud service, graph database, or API key.
- Preserves provenance for every edge: path, line, extractor, confidence, commit, and freshness.

```text
/edgebase-goal "Add passwordless login support without breaking existing OAuth"
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

Change blast radius (advisory):
- API route: `src/routes/auth.py` (imports `src/auth/login.py`; confidence=0.80)
- tests: `tests/auth/test_login.py` (tests `src/auth/login.py`; confidence=0.45)
- downstream module: `src/auth/oauth.py` (calls exported symbol `login`; confidence=0.55)
- risk: auth provider side effects if the provider flow changes
Note: inspect affected areas when behavior reaches them; this does not require editing every listed path.

Patch contract:
The final PR must include changed files, rationale, tests run, regression evidence, and unresolved assumptions.
```

Goal Capsules are backed by the local graph index, git state, inferred tests, provenance, and working-tree freshness. They are recorded automatically by supported hooks, exposed as `/edgebase-goal ...` when a manual command is useful, and called through CLI/MCP before write tools run. `/edgebase-radius ...` is the explicit planning command when an agent proposes a file-level plan and needs to see likely affected areas without being forced to edit them. `/goal ...` remains installed as a shorter compatibility alias. The same agent-facing paths also refresh optional local graph artifacts at `.edgebase/graphs/latest.html`, `.json`, and `.dot`; agents surface the paths without dumping raw graph data into context.

Edgebase also keeps `AGENTS.md` small, indexes the repository into a rebuildable SQLite graph, and exposes MCP tools that agents can use before editing:

```text
edgebase_context(task, changed_files?, budget?)
edgebase_goal(goal, changed_files?, budget?)
edgebase_radius(targets?, goal?, changed_files?, budget?)
edgebase_checkpoint(message, budget?)
edgebase_fork_plan(message, from_id?, branch?, path?, allow_dirty?, budget?)
edgebase_resume(snapshot_id?)
```

The companion context output remains a compact, source-backed capsule: high-signal files, symbols, imports, conservative call edges, inferred tests, owners, churn, freshness, and provenance. Claude Code and Codex project setup also get an automatic work-contract runtime, so users do not need to remember a special phrase before each task.

Edgebase is not a vector database, a Neo4j wrapper, or a generic memory product. It is a small local substrate for answering:

> Given this task and current diff, what context should the agent read before touching code?

With Goal Capsules, Edgebase also answers:

> What is the executable contract for this goal, and what evidence must the patch return?

With Change Blast Radius, it also answers:

> If this file changes, what routes, migrations, tests, downstream modules, and side effects should be inspected before editing?

## Why This Matters

Modern coding agents are good at exploring code, but their default exploration loop is wasteful:

- search broad terms
- read too many files
- miss nearby tests or owners
- carry stale generated architecture summaries
- repeat the same exploration in every session

Flat instruction files such as `AGENTS.md`, `CLAUDE.md`, and Cursor rules are still useful for human-written project rules. They are a poor place for generated code structure. Edgebase complements those files by keeping generated structure in a local cache and serving fresh context on demand.

## Install With Any Agent

Generate the copy/paste setup prompt for a specific agent:

```bash
python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
python3 -m edgebase install-prompt --agent all
python3 -m edgebase install-prompt --agent claude
python3 -m edgebase install-prompt --agent codex
```

Paste that prompt into Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Windsurf, or any coding agent with shell access. It tells the agent to install Edgebase, run `edgebase setup --scope both`, run `edgebase doctor --scope both`, and report exactly what became automatic.

If Edgebase is not installed yet and you want a one-shot prompt to paste directly:

```text
Install Edgebase for this repository and verify the automatic work-contract runtime.

Run:
python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
python3 -m edgebase setup --scope both --agents all
python3 -m edgebase doctor --scope both --agents all
python3 -m edgebase status --json

After setup, report exactly which capabilities became automatic: MCP tools and prompts, prompt-time Goal Capsule creation where hooks are supported, pre-edit Work Contract checks where hooks are supported, post-edit refresh, checkpoints, Patch Passport finish flow, and slash commands or skills installed for this agent host.
```

For stricter setup, paste the full prompt:

```text
Set up Edgebase for this repository.

Repository target: current working directory.

Do the setup yourself. Do not ask me to run `python3 -m edgebase setup` manually.

Steps:
1. Confirm you are inside a git repository. If I gave you a repository URL instead of a local repo, clone it first and cd into it.
2. Run:
   python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
3. Run:
   python3 -m edgebase setup --scope both
4. Run:
   python3 -m edgebase doctor --scope both
5. Report the files Edgebase changed and whether doctor passed.

Rules:
- Do not add generated architecture summaries to AGENTS.md.
- Do not remove existing agent config.
- Do not commit unless I explicitly ask.
- Explain that Edgebase is on by default after setup, can be disabled with `python3 -m edgebase disable --scope both`, and can be bypassed for one emergency session with `EDGEBASE_PREFLIGHT=off`.
```

If you are setting up a remote repository, change the target line:

```text
Repository target: https://github.com/OWNER/REPO
```

Then paste the same prompt.

See [Universal Agent Install Prompt](docs/UNIVERSAL_AGENT_PROMPT.md) for a copy/paste version with client-specific verification notes.

Manual fallback, from inside the repo:

```bash
python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git
python3 -m edgebase setup --scope both
python3 -m edgebase doctor --scope both
```

Edgebase is enabled by default after setup. Turn it off with `python3 -m edgebase disable --scope both`.

To bypass only the edit gate for one emergency session without removing MCP config:

```bash
EDGEBASE_PREFLIGHT=off
```

## What Setup Changes

`python3 -m edgebase setup --scope both` makes local, reversible changes:

| Target | Project file | User file | Behavior |
| --- | --- | --- | --- |
| Edgebase cache/artifacts | `.edgebase/index.sqlite3`, `.edgebase/graphs/latest.*` | none | Rebuildable local graph cache plus optional visual artifacts, ignored by git |
| Edgebase session state | `.edgebase/session/active-goal.json`, `.edgebase/passports/latest.*` | none | Active Work Contract, recorded checks, latest Patch Passport, ignored by git |
| Git ignore | `.git/info/exclude` | none | Locally ignores `.edgebase/` without changing committed ignore files |
| Agent instructions | `AGENTS.md` marker block | none | Tells agents to use Edgebase automatically for broad exploration/editing |
| Claude Code | `.mcp.json`, `.claude/settings.json`, `.claude/skills/edgebase*/SKILL.md`, `.claude/skills/goal/SKILL.md` | none by default | MCP server, automatic Goal Capsules, PreToolUse Work Contract warnings or strict denials, SessionStart/PostToolUse/PreCompact/SessionEnd hooks, `/edgebase`, `/edgebase-goal`, `/goal`, and `/edgebase-*` command skills |
| Codex | `.codex/config.toml`, `.codex/hooks.json`, `.agents/skills/edgebase*/SKILL.md`, `.agents/skills/goal/SKILL.md` | `~/.codex/config.toml`, `~/.codex/skills/edgebase*/SKILL.md`, `~/.codex/skills/goal/SKILL.md` | MCP server entry, project hook config, project/global skills including `/edgebase-*`, AGENTS.md routing |
| Cursor | `.cursor/mcp.json` | `~/.cursor/mcp.json` | MCP server entry |
| Gemini CLI | `.gemini/settings.json` | `~/.gemini/settings.json` | MCP server entry |
| OpenCode | `.opencode.json` | `~/.opencode.json` | Enabled local MCP server |
| Windsurf | none | `~/.codeium/windsurf/mcp_config.json` | Global MCP server entry |
| Git | `.git/hooks/post-commit`, `post-checkout`, `post-merge`, `post-rewrite` | none | Refreshes the index after commits, branch switches, merges, and rebases |

No Docker, cloud service, graph database, or API key is required.

Generated hook and MCP config use the Python interpreter that ran setup instead of assuming GUI agents can see `edgebase` on `PATH`.

## Day-To-Day Usage

Most users do not run Edgebase manually after setup. When an explicit action is useful, run slash commands inside Claude Code, Codex, or any client that exposes project skills or MCP prompts.

- Claude Code: `UserPromptSubmit` records `.edgebase/session/active-goal.json` and injects a Goal Capsule before planning. `PreToolUse` warns before stale or risky Write/Edit/MultiEdit calls; `edgebase setup --strict` can deny unsafe edits. `PostToolUse` refreshes the graph after edits. `PreCompact` saves a checkpoint, and `SessionEnd` saves a Patch Passport. Project skills install `/edgebase`, `/edgebase-goal`, `/goal`, and the `/edgebase-*` command set.
- Codex: setup writes MCP config, project `.codex/hooks.json`, `[features] hooks = true`, `.agents/skills/edgebase*`, `.agents/skills/goal`, global Codex skills when global scope is selected, and the `AGENTS.md` marker. Codex uses MCP plus skills by default; when trusted hook support is active, the same runtime records capsules, checks the Work Contract before edits, refreshes after edits, checkpoints before compaction, and saves a Patch Passport on stop.
- Cursor, Gemini CLI, OpenCode, and Windsurf: Edgebase installs MCP config and a marker-bounded `AGENTS.md` instruction telling agents to use `edgebase_context` or `edgebase_goal` automatically before broad code exploration or edits. Those MCP calls update `.edgebase/graphs/latest.*` and return the artifact paths.
- Any client: the MCP prompts named `edgebase`, `edgebase-goal`, `goal`, and the `/edgebase-*` aliases are available for clients that expose MCP prompts or slash-command-style prompt menus.

Useful explicit slash commands inside supported agent REPLs/apps:

```text
/edgebase "change the auth login flow"
/edgebase-goal "add passwordless login without breaking OAuth"
/edgebase-radius "src/auth/login.py" --goal "add passwordless login without breaking OAuth"
/edgebase-passport "add passwordless login without breaking OAuth" --test "python3 -m unittest -v: pass"
/edgebase-status
/edgebase-preflight-status
/edgebase-finish "add passwordless login without breaking OAuth" --test "python3 -m unittest -v: pass"
/edgebase-preflight-refresh "add passwordless login without breaking OAuth"
/edgebase-checkpoint "handoff after auth refactor"
/edgebase-resume
/edgebase-fork-plan "split auth UI and token backend work"
/edgebase-index --changed
/edgebase-stats
/edgebase-doctor --scope both
/edgebase-disable --scope both
/edgebase-version
```

Shell fallback and server/development commands:

```bash
python3 -m edgebase install-prompt --agent codex
python3 -m edgebase context "change the auth login flow" --budget 1200
python3 -m edgebase goal "add passwordless login without breaking OAuth" --budget 1200 --record
python3 -m edgebase radius src/auth/login.py --goal "add passwordless login without breaking OAuth"
python3 -m edgebase passport "add passwordless login without breaking OAuth" --test "python3 -m unittest -v: pass"
python3 -m edgebase status
python3 -m edgebase finish "add passwordless login without breaking OAuth" --test "python3 -m unittest -v: pass"
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
| Claude Code | Supported | Project `.mcp.json`; automatic UserPromptSubmit Goal Capsule; warn-by-default PreToolUse Work Contract checks with optional strict denial; async PostToolUse refresh; PreCompact checkpoint; SessionEnd Patch Passport; `/edgebase`, `/edgebase-goal`, `/edgebase-radius`, `/goal`, and `/edgebase-*` project skills |
| Codex | Supported | Project `.codex/config.toml`, `.codex/hooks.json`, `.agents/skills`; global `~/.codex/config.toml` MCP entry and global skills for CLI discovery; verify with `codex mcp list` and `python3 -m edgebase doctor` |
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
- pre-edit hook: Write/Edit/MultiEdit receives Work Contract warnings by default; strict setup can deny missing/stale contracts or protected-path edits
- edit hook: edited files are reindexed and edit deltas are returned after Write/Edit/MultiEdit
- compaction hook: `.edgebase/checkpoints/latest.md` preserves the active capsule before context compaction
- session-end hook: `.edgebase/passports/latest.md` and `.json` preserve changed files and explicit evidence at stop/session end
- git hook: post-commit, post-checkout, post-merge, and post-rewrite refresh keep the cache aligned with branch and history changes
- MCP: every supported agent gets `edgebase_context`, `edgebase_goal`, checkpoint, fork-plan, and resume tools over stdio
- graph artifacts: hooks and MCP calls refresh self-contained local HTML, JSON, and DOT files and surface their paths as optional visual aids
- AGENTS marker: static repo instructions stay tiny and tell agents to route structural context through Edgebase

This is not a separate graph UI or a new agent control surface; visualization is kept as a local artifact attached to the existing agent context flow.

See [Architecture](docs/ARCHITECTURE.md), [Validation](docs/VALIDATION.md), and [Graph Verification](docs/GRAPH_VERIFICATION_0.1.7.md).
The latest release audit is documented in [Release Audit](docs/RELEASE_AUDIT_0.1.9.md).

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
