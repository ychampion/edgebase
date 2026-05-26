# Edgebase 0.1.3 Release Audit

Date: 2026-05-26

Scope: release readiness review for the Agent Preflight Gate release.

## Release Goal

Ship Edgebase as an automatic local agent context substrate. A user should install once, restart the agent, and get fresh, source-backed Goal Capsules before edits without saying "use edgebase_context" on every task.

## Threat Model

Primary trust boundaries:

- Local repository paths enter generated hook command strings.
- Agent clients launch Edgebase through stdio MCP config.
- Claude Code and Codex hooks receive prompt/tool JSON from the client.
- Edgebase writes marker-bounded project config and local `.edgebase/` state.
- The MCP server accepts local JSON-RPC from the configured agent process.

Assets to protect:

- User source files and git history.
- Existing agent configuration owned by the user.
- Integrity of preflight state, checkpoints, and patch passports.
- Local shell execution boundaries for generated hooks.

Out of scope:

- Remote hosted MCP transports.
- Secret scanning for arbitrary user repositories.
- Perfect dynamic-language call graph precision.

## Release Changes Reviewed

- Claude Code `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `SessionEnd` hook paths.
- Codex project `.codex/config.toml`, `.codex/hooks.json`, and `.agents/skills/*` setup.
- Preflight state freshness checks across HEAD, working tree changes, stale index files, and TTL.
- MCP tools: `edgebase_context`, `edgebase_goal`, `edgebase_checkpoint`, `edgebase_fork_plan`, and `edgebase_resume`.
- Context checkpoint, fork-plan, resume, and Patch Passport persistence under `.edgebase/`.
- Setup, disable, and doctor paths for reversible integration.

## Findings And Fixes

### EB-2026-003: Context skill accidentally recorded preflight with an unsupported flag

Status: fixed before release.

Risk:

The generated `/edgebase` skill called `edgebase context ... --record-preflight`, but only `edgebase goal` supports `--record-preflight`. That would make the explicit context skill fail for Claude Code.

Fix:

The `/edgebase` skill now calls `edgebase context ... --budget 1200`. The `/goal` skill keeps `--record-preflight`. Regression coverage asserts the Codex `/edgebase` skill does not include the flag and the `/goal` skill does.

### EB-2026-004: Codex setup needed doctor-visible hook and skill validation

Status: fixed before release.

Risk:

Writing only MCP config would not make Edgebase unavoidable for Codex-style project workflows. Setup also needed local hooks, skills, and a verification path that detects partial installs.

Fix:

Project setup now writes `.codex/config.toml` with `hooks = true`, `.codex/hooks.json`, `.agents/skills/edgebase/SKILL.md`, and `.agents/skills/goal/SKILL.md`. `edgebase doctor --agents codex --scope project` validates all of them.

### EB-2026-005: Named read tools should not be blocked by the pre-edit gate

Status: fixed before release.

Risk:

Codex-style hooks may run for every tool call. Treating any payload with `file_path` as an edit would incorrectly block named read tools.

Fix:

The gate now trusts explicit tool names first. `Read` with `file_path` is allowed, while `Write`, `Edit`, `MultiEdit`, and `apply_patch` remain gated. Regression coverage verifies named read tools produce no deny payload.

### EB-2026-006: Codex hook setup must preserve unrelated project hooks

Status: fixed before release.

Risk:

Replacing `.codex/hooks.json` would clobber unrelated project automation and violate the reversible setup contract.

Fix:

Codex hook install now parses existing JSON, removes only prior Edgebase hook entries, appends current Edgebase entries, and preserves unrelated keys and hooks. Disable removes only Edgebase hook entries and leaves unrelated hooks intact. Regression coverage verifies merge and disable behavior.

## Security Review

Manual review covered:

- generated shell command quoting
- hook JSON parsing and invalid-input fallback
- preflight deny decisions
- MCP JSON-RPC request validation
- local config merge and disable paths
- subprocess use
- checkpoint/fork-plan filesystem writes

Notes:

- Hook commands are generated with `shlex.join`.
- Runtime subprocess calls use argument arrays; no release path requires `shell=True`.
- Existing JSON config with invalid syntax is refused instead of overwritten.
- Edgebase state is local and rebuildable under `.edgebase/`, which setup ignores through `.git/info/exclude`.
- The emergency bypass is explicit: `EDGEBASE_PREFLIGHT=off`.
- The normal path needs no Docker, cloud service, graph database, or API key.

## Verification Commands

Required local checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Fresh install smoke:

```bash
python3 -m venv /tmp/edgebase-smoke/venv
/tmp/edgebase-smoke/venv/bin/python -m pip install -q --upgrade pip
/tmp/edgebase-smoke/venv/bin/python -m pip install -q -e .
mkdir /tmp/edgebase-smoke/repo
cd /tmp/edgebase-smoke/repo
git init
git config user.email t@example.com
git config user.name T
mkdir app tests
printf 'def login(x):\n    return x\n' > app/auth.py
printf 'from app.auth import login\n\ndef test_login():\n    assert login("x")\n' > tests/test_auth.py
git add .
git commit -m init
/tmp/edgebase-smoke/venv/bin/edgebase setup --agents claude,codex --scope project
/tmp/edgebase-smoke/venv/bin/edgebase doctor --agents claude,codex --scope project
printf '{"prompt":"change login behavior"}' | /tmp/edgebase-smoke/venv/bin/edgebase hooks claude-user-prompt-submit --root /tmp/edgebase-smoke/repo
printf '{"tool_name":"Edit","tool_input":{"file_path":"app/auth.py"}}' | /tmp/edgebase-smoke/venv/bin/edgebase hooks claude-pre-tool-use --root /tmp/edgebase-smoke/repo
/tmp/edgebase-smoke/venv/bin/edgebase preflight status --root /tmp/edgebase-smoke/repo
```

Security tooling:

```bash
bandit -q -r src --severity-level medium
pip-audit
```

## Client Evidence

- Claude Code: generated `.mcp.json`, `.claude/settings.json`, `/edgebase`, and `/goal` skill files are validated by `edgebase doctor`; hook smoke verifies prompt injection and pre-edit freshness.
- Codex: generated `.codex/config.toml`, `.codex/hooks.json`, `.agents/skills/edgebase`, and `.agents/skills/goal` are validated by `edgebase doctor`.
- Cursor, Gemini CLI, OpenCode, and Windsurf: generated config shape and MCP stdio handshake remain covered by setup/doctor checks when the binaries are not installed.

## Release Decision

Release `v0.1.3` is acceptable if the verification commands above pass from the tagged commit and the GitHub release points at that commit.
