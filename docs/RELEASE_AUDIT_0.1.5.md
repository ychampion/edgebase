# Edgebase 0.1.5 Release Audit

Date: 2026-05-26

Scope: GitHub presentation and repository polish release.

## Release Goal

Make the GitHub repository look credible on first visit while preserving the technical promise: Edgebase is a local, git-native preflight context layer for coding agents.

## Release Changes Reviewed

- Added SVG logo and mark assets under `assets/`.
- Added GitHub Actions CI for Python 3.10 and 3.12.
- Added issue templates and pull request template.
- Updated README first screen with logo, badges, clearer positioning, and concrete behavior bullets.
- Added `docs/LAUNCH_POST.md`.
- Updated package description and security docs.

## Safety Review

- SVG assets are static and contain no scripts or external references.
- CI runs only compile and unit tests.
- GitHub templates do not alter runtime behavior.
- README claims remain scoped to implemented behavior: local index, MCP tools, Claude/Codex hooks, preflight gate, provenance, and reversible setup.

## Verification

Required checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Security spot checks:

```bash
rg -n "<script|http://|https://" assets .github docs/LAUNCH_POST.md
```

## Release Decision

Release `v0.1.5` is acceptable if checks pass and the GitHub release tag points at the final commit.
