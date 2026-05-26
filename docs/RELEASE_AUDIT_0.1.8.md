# Edgebase 0.1.8 Release Audit

Date: 2026-05-26

Scope: Advisory Change Blast Radius release.

## Release Goal

Add a careful planning surface that answers: "If this file changes, what routes, migrations, tests, downstream modules, and side effects should the agent inspect before editing?"

The key product constraint is that radius output must not become another edit gate. It should help an agent plan and test around likely impact, while making clear that listed paths are not mandatory edits.

## Release Changes Reviewed

- Added `edgebase radius` CLI command.
- Added `edgebase_radius` MCP tool.
- Added generated `/edgebase-radius` project skills and MCP prompt alias through the existing `/edgebase-*` command set.
- Added advisory Change Blast Radius sections to Goal Capsules when a target file is known.
- Added radius findings with category, path, reason, confidence, and source.
- Documented radius usage in README, agent-client docs, architecture notes, validation docs, and launch copy.

## Safety Review

- Radius is advisory only. It does not affect `PreToolUse`, preflight freshness, or edit blocking.
- Findings are confidence-scored and source-backed when graph edges exist.
- Heuristic findings are labeled with `path.heuristic` and lower confidence.
- Migration paths are phrased as "inspect only if schema or data shape changes."
- Radius output explicitly says it is an impact map, not an edit requirement.

## Verification

Required checks:

```bash
python3 -m compileall -q src tests
python3 -m unittest -v
git diff --check
```

Focused radius checks:

```bash
python3 -m unittest -v \
  tests.test_edgebase.EdgebaseTests.test_change_radius_classifies_routes_tests_migrations_and_risks \
  tests.test_edgebase.EdgebaseTests.test_radius_cli_and_mcp_return_advisory_surface \
  tests.test_edgebase.EdgebaseTests.test_goal_capsule_markdown_and_contract_schema \
  tests.test_edgebase.EdgebaseTests.test_mcp_exposes_context_and_goal_surfaces
```

Expected billing smoke output includes:

```text
Changing `src/billing/subscription.ts` likely affects:
- API route: `src/routes/billing.ts`
- DB migration path: `migrations/*`
- tests: `tests/billing/subscription.test.ts`
- downstream module: `src/notifications/invoices.ts`
- risk: payment provider side effects
Advisory: this is an impact map, not an edit requirement.
```

Release `v0.1.8` is acceptable if checks pass, the public tag install smoke passes, CI passes, and the GitHub release tag points at the final commit.
