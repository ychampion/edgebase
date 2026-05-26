# Edgebase 0.1.9 Release Audit

Date: 2026-05-26

Scope: Cross-platform agent command and setup hardening.

## Release Goal

Keep the Context Branch and lifecycle command surfaces usable from Claude Code, Codex, and other agent CLIs on Windows, macOS, and Linux, while making first-run setup easier for agents to perform directly.

## Release Changes Reviewed

- Added platform-aware shell command rendering for generated hook commands and slash-skill fallback snippets.
- Added `edgebase install-prompt --agent <name>` for generating a copy/paste setup prompt for a selected agent host.
- Updated Codex hook setup to write the current event-keyed `hooks.json` shape and migrate older flat Edgebase hook entries.
- Filtered Edgebase's local `.edgebase/` cache from git dirty-state checks so `checkpoint` can be followed by `fork-plan` in a clean repo.
- Kept MCP server configuration as command-plus-args arrays for clients that support structured process launch.
- Shared command rendering across Claude Code skills, Codex skills, MCP prompt fallbacks, and hook config generation.
- Added regression coverage for Windows and POSIX quoting behavior, install prompt output, Codex hook migration, and checkpoint-to-fork-plan flow.

## Safety Review

- No new dependency was added.
- Runtime subprocess calls still use argv vectors where Edgebase launches child processes directly.
- Windows rendering uses Python's `subprocess.list2cmdline`; macOS/Linux rendering uses `shlex.join`.
- Existing MCP command/args configuration remains unchanged and platform-neutral.
- Codex hook migration preserves unrelated user hooks and removes only Edgebase-owned hook entries on disable.

## Verification

Required checks:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
git diff --check
```

Agent CLI smoke:

```bash
python3 -m edgebase --help
python3 -m edgebase install-prompt --agent codex
python3 -m edgebase checkpoint "smoke checkpoint" --json
python3 -m edgebase resume --json
python3 -m edgebase fork-plan "smoke fork" --branch smoke/context --path <temp-worktree> --json
python3 -m edgebase doctor --scope project --agents claude,codex
```

Release `v0.1.9` is acceptable if checks pass, the public tag install smoke passes, CI passes, and the GitHub release tag points at the final commit.
