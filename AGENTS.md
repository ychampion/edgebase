# Agent Instructions

This repository is the Edgebase source tree. Keep changes small, tested, and documented.

<!-- EDGEBASE:START -->
## Edgebase Context

Edgebase is enabled for this repository. Use the injected Edgebase context when it is present. When no injected context is present and the task needs broad code exploration or edits, call the MCP tool `edgebase_context` with the task and any changed files before reading many files. Do not wait for the user to request Edgebase explicitly.

Fallback when MCP tools and automatic hooks are unavailable:

```bash
python3 -m edgebase context "<task>" --budget 1200
```

Keep static instructions here minimal; Edgebase supplies fresh structure, symbols, tests, owners, and change-hotspot context from the local git working tree. Claude Code receives automatic prompt-time context through hooks when hooks are installed, and also exposes `/edgebase <task>` as a project skill. Refresh manually with `python3 -m edgebase index --changed` after edits, or disable with `python3 -m edgebase disable --scope both`.
<!-- EDGEBASE:END -->

## Development Checks

Run focused tests for changed behavior, then:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
```
