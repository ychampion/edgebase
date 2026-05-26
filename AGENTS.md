# Agent Instructions

This repository is the Edgebase source tree. Keep changes small, tested, and documented.

<!-- EDGEBASE:START -->
## Edgebase Context

Edgebase is enabled for this repository. Before broad code exploration or edits, call the MCP tool `edgebase_context` with the task and any changed files. Use it to get a small, source-backed context capsule instead of loading generated architecture summaries.

Fallback when MCP tools are unavailable:

```bash
python3 -m edgebase context "<task>" --budget 1200
```

Keep static instructions here minimal; Edgebase supplies fresh structure, symbols, tests, owners, and change-hotspot context from the local git working tree. Refresh manually with `python3 -m edgebase index --changed` after edits, or disable with `python3 -m edgebase disable --scope both`.
<!-- EDGEBASE:END -->

## Development Checks

Run focused tests for changed behavior, then:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
```
