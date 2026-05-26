# Edgebase 0.1.2 Release Audit

Date: 2026-05-26

Scope: repository-wide release readiness review for the first public `v0.1.2` release.

## Release Goal

Ship Edgebase as a local, git-native agent context substrate that users can install with one command. The release must prove that setup works, the agent integration is reversible, Claude Code receives automatic prompt-time context, and the normal path requires no Docker, cloud service, graph database, or API key.

## Threat Model

Primary trust boundaries:

- Local repository path enters generated shell commands for git hooks and Claude Code hooks.
- Agent clients launch the Edgebase MCP server through generated local config.
- Claude Code hooks receive prompt and tool-use JSON from the agent client.
- Edgebase writes local config files in the project and, for some clients, user config files.
- The MCP server accepts local stdio JSON-RPC from the configured agent client.

Assets to protect:

- User repository files and git history.
- Agent configuration files that may already contain unrelated user settings.
- Local shell execution boundaries for generated hooks.
- Integrity and freshness of the local `.edgebase/` cache.

Out of scope for this release:

- Remote hosted MCP transports.
- Enterprise policy management for agent clients.
- Perfect call graph precision for dynamic languages.

## Findings And Fixes

### EB-2026-001: Generated hook commands needed shell-safe repository path quoting

Status: fixed before release.

Affected code:

- `src/edgebase/hooks.py`
- `.git/hooks/post-commit` command generation
- `.claude/settings.json` command generation

Risk:

Repository paths are local inputs but can contain spaces or shell metacharacters. Hook commands are command strings interpreted by the client or shell, so manual quote construction is not a sufficient boundary.

Fix:

Hook commands now use `shlex.join` over an argument vector. Regression coverage creates a repository path with spaces and quotes, installs both Claude and git hooks, then verifies `shlex.split(command)` reconstructs the intended argument list.

### EB-2026-002: Optional benchmark runner used shell execution for competitor templates

Status: fixed before release.

Affected code:

- `src/edgebase/benchmark.py`

Risk:

External benchmark templates are explicit user-provided commands, but running formatted templates with `shell=True` widens the execution boundary unnecessarily and was flagged by Bandit as high severity.

Fix:

External benchmark templates are now parsed with `shlex.split` and executed as an argument vector with `shell=False`. Empty or malformed templates are skipped with a structured reason.

## Security Checks

Manual review covered:

- subprocess call sites
- shell command construction
- generated config writes
- JSON parsing and invalid JSON refusal paths
- git hook install and removal
- Claude hook install and removal
- MCP JSON-RPC request handling
- benchmark external command templates

Notes:

- Runtime code avoids `shell=True`; subprocess calls use argument arrays.
- No runtime path uses `shell=True`.
- Existing JSON config files are parsed and merged; invalid JSON is refused instead of overwritten.
- The `.edgebase/` cache is local, rebuildable, and ignored through `.git/info/exclude`.

## Verification Commands

Required local checks:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
git diff --check
PYTHONPATH=src python3 -m edgebase --root /root/edgebase mcp
```

Security tooling:

```bash
bandit -q -r src --severity-level medium
pip-audit
```

Public install smoke:

```bash
python3 -m pip install --no-cache-dir git+https://github.com/ychampion/edgebase.git
python3 -m edgebase setup --scope both
python3 -m edgebase doctor --scope both
claude mcp get edgebase
codex mcp get edgebase
printf '{"prompt":"change login behavior"}' | python3 -m edgebase hooks claude-user-prompt-submit --root .
```

## Client Evidence

- Claude Code: `claude mcp get edgebase` reports connected from project `.mcp.json`.
- Codex: `codex mcp get edgebase` reports enabled stdio transport from generated config.
- Cursor, Gemini CLI, OpenCode, and Windsurf: binaries were not installed in the verification environment; generated config shape and MCP stdio handshake were verified.

## Release Decision

Release `v0.1.2` is acceptable if all verification commands above pass from the final tagged commit and the GitHub release points at that commit.
