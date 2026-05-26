# Architecture

Edgebase is deliberately small:

```text
repo files + git history
        |
        v
extractors -> SQLite graph cache -> context ranker -> edgebase_context MCP tool
```

## Graph Cache

The cache lives at `.edgebase/index.sqlite3` and is rebuildable. It stores:

- files: path, language, module, hash, test marker, indexed commit
- symbols: name, kind, file, line, signature, exported marker, confidence
- edges: typed relationships with provenance and confidence
- file metrics: churn, owner, recent commits

Every edge records source path, line, extractor, confidence, commit, and freshness.

## Extraction

- Python uses `ast` for imports, classes, functions, and conservative call names.
- JavaScript/TypeScript use regex extractors with lower confidence.
- Go/Rust/generic source use shallow symbol and import patterns with lower confidence.

Low-confidence relationships are still useful for orientation, but agents should treat them as leads rather than proof.

## Context Routing

`edgebase_context` ranks files using:

- explicit changed-file hints
- task-token matches against path, module, symbols, and relationships
- graph neighbors of changed files
- churn hotspots
- inferred tests

The returned capsule includes only high-signal files, symbols, relationships, next reads, and a machine summary.
