# Edgebase 0.1.7 Release Audit

Date: 2026-05-26

Scope: Agent-visible lifecycle command and graph verification release.

## Release Goal

Make Edgebase's lifecycle operations available from slash-capable agent clients, then verify that the local knowledge graph, freshness updates, preflight memory, checkpoint memory, graph artifacts, and patch passports work together end to end.

## Release Changes Reviewed

- Added `/edgebase-checkpoint`, `/edgebase-resume`, `/edgebase-fork-plan`, `/edgebase-passport`, `/edgebase-preflight-status`, `/edgebase-preflight-refresh`, `/edgebase-index`, `/edgebase-stats`, `/edgebase-doctor`, `/edgebase-setup`, `/edgebase-disable`, and `/edgebase-version` project skills for Claude Code and Codex.
- Added MCP prompt aliases for the same `/edgebase-*` command set.
- Updated `edgebase init`, setup output, README, agent-client docs, architecture docs, validation docs, universal setup prompt, and launch post to describe the lifecycle commands.
- Extended doctor coverage and regression tests for generated lifecycle skills and disable cleanup.
- Added graph lifecycle verification notes in `docs/GRAPH_VERIFICATION_0.1.7.md`.

## Safety Review

- The new slash commands delegate to existing Edgebase CLI/MCP surfaces; they do not add new repository edit behavior.
- Generated skill files are marker-bounded and setup refuses to overwrite unmarked user-owned skills.
- Doctor validates branded, compatibility, and generated `/edgebase-*` command files.
- Disable removes generated lifecycle skills while preserving unrelated user config.
- Graph verification used a throwaway git repository and disposable virtual environment.

## Verification

Required checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Graph lifecycle smoke:

```bash
python3 -m edgebase setup --agents claude,codex --scope project
python3 -m edgebase doctor --agents claude,codex --scope project
python3 -m edgebase context "<task>" --changed-file app/auth.py --json
python3 -m edgebase index --changed
python3 -m edgebase hooks claude-user-prompt-submit
python3 -m edgebase hooks claude-pre-tool-use
python3 -m edgebase hooks claude-post-tool-use
python3 -m edgebase checkpoint "<message>"
python3 -m edgebase resume
python3 -m edgebase hooks claude-pre-compact
python3 -m edgebase hooks claude-session-end
```

Release `v0.1.7` is acceptable if checks pass, graph lifecycle smoke passes, setup smoke passes, CI passes, and the GitHub release tag points at the final commit.
