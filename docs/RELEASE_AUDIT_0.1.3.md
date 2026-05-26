# Edgebase 0.1.3 Release Audit

Date: 2026-05-26

Scope: repository-wide release readiness review for Goal Capsules and Context Branches.

## Release Goal

Ship Goal Capsules and Context Branches so coding agents get executable work contracts plus local continuity state:

- `edgebase goal`
- `edgebase passport`
- `edgebase checkpoint`
- `edgebase fork-plan`
- `edgebase resume`
- MCP tools for goal, checkpoint, fork-plan, and resume.

The release must preserve the existing local-first contract: no service, no API key, no new dependency, and no generated work-contract or continuity state committed to the repository.

## Threat Model

Primary trust boundaries:

- User-provided checkpoint and fork messages enter persisted local SQLite state and terminal output.
- User-provided goals and explicit test evidence enter generated Work Contracts and Patch Passports.
- User-provided worktree paths and branch names enter `git worktree add` as argument-vector subprocess inputs.
- Stored context may be rendered later in another agent client through CLI output or MCP tool responses.
- Context snapshots live beside the rebuildable graph cache under `.edgebase/`.

Assets to protect:

- User repository files and git history.
- Uncommitted working-tree edits that should not be silently dropped into a forked plan.
- Integrity of local context snapshots across reindexing.
- Accuracy of generated Work Contracts and explicit test evidence.
- Shell command boundaries in displayed resume hints.

Out of scope:

- Remote synchronization of context snapshots.
- Automatic merging of forked plans.
- Executing tests automatically for Patch Passport evidence.
- Hosted MCP transports or shared team state.

## Findings And Fixes

### EB-2026-003: Edgebase cache paths made indexed repos appear dirty

Status: fixed before release.

Risk:

Creating `.edgebase/index.sqlite3` in a test or newly initialized repository can show up as an untracked `.edgebase/` path when project setup has not yet added the local git exclude entry. That would make `fork-plan` refuse a clean logical tree.

Fix:

Git changed-file detection now filters ignored Edgebase cache paths before reporting dirty state.

### EB-2026-004: Full reindex must not erase context snapshots

Status: fixed before release.

Risk:

Context Branch snapshots are stored in `.edgebase/index.sqlite3`, but graph refreshes are common. A full `edgebase index` reset must refresh graph tables without deleting saved agent continuity records.

Fix:

The graph reset path leaves `context_snapshots` intact. Context Branches remain local cache state, but they survive normal index refreshes.

## Verification Commands

Required local checks:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
git diff --check
```

Context Branch smoke:

```bash
python3 -m edgebase checkpoint "release smoke checkpoint"
python3 -m edgebase resume
EDGEBASE_RELEASE_FORK="$(mktemp -d)/fork"
python3 -m edgebase fork-plan "release smoke fork" --path "$EDGEBASE_RELEASE_FORK" --allow-dirty
python3 -m edgebase resume --root "$EDGEBASE_RELEASE_FORK"
git worktree remove --force "$EDGEBASE_RELEASE_FORK"
```

Goal Capsule smoke:

```bash
python3 -m edgebase goal "change login hashing behavior" --changed-file tests/test_edgebase.py --json
python3 -m edgebase passport "change login hashing behavior" --test "python3 -m unittest -v: pass"
printf '{"goal":"change login hashing behavior","tool_input":{"file_path":"tests/test_edgebase.py"}}' | python3 -m edgebase hooks claude-pre-tool-use --root .
```

MCP smoke:

```bash
python3 -m edgebase mcp --root "$PWD"
```

Verify `tools/list` includes:

- `edgebase_context`
- `edgebase_goal`
- `edgebase_checkpoint`
- `edgebase_fork_plan`
- `edgebase_resume`

## Release Decision

Release `v0.1.3` is acceptable if all verification commands above pass from the final tagged commit and the GitHub release points at that commit.
