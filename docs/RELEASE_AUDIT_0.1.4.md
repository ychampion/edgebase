# Edgebase 0.1.4 Release Audit

Date: 2026-05-26

Scope: install documentation patch release.

## Release Goal

Make the first install instruction a universal prompt users paste into their coding agent, not a command they personally run. The agent should install, run setup, verify with doctor, and report changed files.

## Release Changes Reviewed

- README install section now leads with "Install With Any Agent."
- Agent client docs now state that the normal install path is a prompt.
- `docs/UNIVERSAL_AGENT_PROMPT.md` provides the standalone prompt for Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Windsurf, and similar tools.
- Manual `pip install` and `edgebase setup` commands remain documented as fallback/reference.

## Safety Review

- The prompt tells agents not to overwrite existing agent config and not to commit unless explicitly asked.
- The prompt keeps generated architecture summaries out of `AGENTS.md`.
- The prompt requires `edgebase doctor --scope both` after setup.
- The prompt documents the disable path and emergency preflight bypass.

## Verification

Required checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Remote install smoke:

```bash
python3 -m pip install --user --upgrade git+https://github.com/ychampion/edgebase.git@v0.1.4
python3 -m edgebase setup --scope project --agents claude,codex
python3 -m edgebase doctor --scope project --agents claude,codex
```

## Release Decision

Release `v0.1.4` is acceptable if the checks pass and the GitHub release tag points at the final commit.
