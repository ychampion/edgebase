# Edgebase 0.1.6 Release Audit

Date: 2026-05-26

Scope: Branded Goal Capsule command release.

## Release Goal

Make the explicit Goal Capsule path easy to discover as an Edgebase command while keeping the existing `/goal` alias compatible for users who already installed it.

## Release Changes Reviewed

- Added `/edgebase-goal <goal>` Claude Code project skill.
- Added `/edgebase-goal <goal>` Codex project skill.
- Added `edgebase-goal` MCP prompt next to `edgebase` and `goal`.
- Added `edgebase --version` for install and smoke-test verification.
- Updated setup, doctor, AGENTS marker text, README, agent-client docs, architecture docs, validation docs, and the universal setup prompt.
- Kept `/goal <goal>` as a compatibility alias.
- Hardened Codex setup so pre-existing unmarked project skills are skipped instead of overwritten or causing setup to abort.

## Safety Review

- The new command is an alias over the existing `edgebase goal` implementation; it does not add a new execution path for repository edits.
- Skill files are marker-bounded and setup refuses to overwrite unmarked user-owned skills.
- Doctor validates both branded and compatibility command files.
- MCP prompt handling records the prompt source as `mcp-prompt-edgebase-goal` or `mcp-prompt-goal` for provenance.

## Verification

Required checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Setup smoke:

```bash
edgebase setup --agents claude,codex --scope project
edgebase doctor --agents claude,codex --scope project
test -f .claude/skills/edgebase-goal/SKILL.md
test -f .agents/skills/edgebase-goal/SKILL.md
edgebase --version
```

Release `v0.1.6` is acceptable if checks pass, setup smoke passes, and the GitHub release tag points at the final commit.
