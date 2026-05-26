# Edgebase Graph Verification 0.1.7

Date: 2026-05-26

## Result

The graph lifecycle smoke passed in a throwaway git repository using an editable install from this source tree.

Verified behaviors:

- SQLite graph creation under `.edgebase/index.sqlite3`.
- File rows for source and test files.
- Python symbol extraction for `login`, `logout`, and `AuthService`.
- Import edges such as `app/auth.py -[IMPORTS]-> hashlib`.
- Conservative call edges such as `app/auth.py -[CALLS]-> hashlib.sha256`.
- Inferred test relationship `tests/test_auth.py -[TESTS]-> app/auth.py`.
- Provenance on every inspected edge: path, line, extractor, confidence, commit, and freshness.
- Git owner/churn metrics for indexed files.
- Context capsule selection for a login/auth task.
- Stale-file detection after editing `app/auth.py`.
- Incremental `edgebase index --changed` refresh that added the new `logout` symbol and cleared staleness.
- PreToolUse edit denial when no fresh Goal Capsule existed.
- UserPromptSubmit preflight memory recording.
- PostToolUse reindex plus preflight refresh after editing `tests/test_auth.py`.
- Graph artifact writes for `.edgebase/graphs/latest.html`, `.json`, and `.dot`.
- Checkpoint and resume memory through `edgebase checkpoint` and `edgebase resume`.
- PreCompact checkpoint persistence at `.edgebase/checkpoints/latest.md`.
- SessionEnd Patch Passport persistence at `.edgebase/passports/latest.md` and `.json`.
- Disable cleanup for generated Claude Code and Codex lifecycle skills.

## Evidence Snapshot

Initial graph stats from the smoke repository:

```json
{
  "files": 4,
  "symbols": 8,
  "edges": 14
}
```

Representative source-backed edges:

```json
[
  {
    "rel": "IMPORTS",
    "dst_key": "hashlib",
    "file_path": "app/auth.py",
    "line": 1,
    "extractor": "python.ast",
    "confidence": 0.95,
    "freshness": "fresh"
  },
  {
    "rel": "CALLS",
    "dst_key": "db.get_user",
    "file_path": "app/auth.py",
    "line": 10,
    "extractor": "python.ast",
    "confidence": 0.55,
    "freshness": "fresh"
  },
  {
    "rel": "CALLS",
    "dst_key": "hashlib.sha256",
    "file_path": "app/auth.py",
    "line": 11,
    "extractor": "python.ast",
    "confidence": 0.55,
    "freshness": "fresh"
  }
]
```

Incremental update evidence:

```text
Indexed 6 files, 9 symbols, 16 edges
```

The smoke then confirmed the new `logout` symbol and fresh `log_event` call edge existed in SQLite after `edgebase index --changed`.

A final current-state smoke from this release state printed:

```text
GRAPH_LIFECYCLE_SMOKE_OK
edgebase 0.1.7
stats: {"edges": 13, "files": 4, "symbols": 8}
checks: {"authservice_symbol": true, "hashlib_import": true, "login_symbol": true, "metrics": true, "provenance": true, "sha256_call": true, "test_edge": true}
incremental: Indexed 6 files, 9 symbols, 14 edges
```

## Honest Limits

- Dynamic-language call edges are intentionally conservative and confidence-scored; they are leads, not compiler-grade proof.
- Edgebase does not replace local tests or human review. It narrows the agent's first-read set and records provenance for why context was selected.
- The graph cache is rebuildable and local; Git remains the source of truth.
