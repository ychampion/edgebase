# Edgebase Validation

Edgebase should earn adoption with measurements, not positioning.

## Required Comparisons

Run the benchmark harness on at least:

- One TypeScript repository
- One Python repository
- One Go or Rust repository
- One monorepo

Compare:

- Edgebase
- Plain `rg` plus file reads
- CodeGraphContext, if installed
- codebase-memory-mcp, if installed
- GitNexus, if installed

## Metrics

- Context token estimate
- Tool-call estimate
- Wall time
- Stale-context incidents
- False dependency edges found during manual review
- Patch success, when paired with an agent evaluation harness

## Kill Criteria

- Edgebase does not reduce token cost or tool calls versus plain exploration.
- Stale graph answers survive branch switches, rebases, file edits, or generated files.
- Dynamic-language call edges are presented without confidence and provenance.
- Normal onboarding requires Docker, cloud services, API keys, or a graph database.
- Agents ignore the tool or consistently choose the wrong query shape.
