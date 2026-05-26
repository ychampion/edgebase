# Contributing

Edgebase is intentionally small. Contributions should preserve the local-first, git-native design.

## Development Setup

```bash
git clone https://github.com/ychampion/edgebase.git
cd edgebase
python3 -m pip install -e .
python3 -m unittest -v
```

## Quality Bar

Before opening a pull request, run:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
python3 -m edgebase doctor --scope project --agents claude,codex,cursor,gemini,opencode
```

For setup changes, also run a clean temporary install from the GitHub URL and verify `edgebase setup` plus `edgebase disable`.

## Design Rules

- Do not add required cloud services, API keys, Docker, or graph databases.
- Keep the agent tool surface small. Prefer improving `edgebase_context` over adding raw graph-query tools.
- Every inferred relationship needs provenance and confidence.
- Setup must be reversible.
- Existing agent config files must be merged carefully and never blindly overwritten.

## Benchmarks

Behavioral improvements should include benchmark evidence where practical:

```bash
python3 -m edgebase benchmark --repo /path/to/repo --tasks benchmarks/tasks.example.jsonl --out results.json
```

Report token estimates, selected files, stale-context incidents, and false dependency edges.
