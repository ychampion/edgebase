# Launch Post

I built Edgebase: a local, git-native preflight layer for coding agents.

The problem is simple: coding agents are good at exploring repos, but they often start from a blank slate. They grep broadly, read too much, miss nearby tests, and sometimes edit with stale assumptions.

Edgebase gives agents a small source-backed Goal Capsule before they edit:

- what to read first
- likely blast radius
- nearby tests
- protected areas to avoid touching yet
- stale context warnings
- provenance for why each file or edge was selected

It is not a vector DB, not a cloud memory service, and not a Neo4j wrapper. It is a rebuildable local cache plus MCP/tools/hooks that fit into the workflow developers already use.

Current support:

- Claude Code hooks: prompt capsule, stale-edit blocking, post-edit refresh, pre-compact checkpoint, session-end patch passport
- Codex setup: MCP config, project hooks, project skills, AGENTS.md routing
- Cursor, Gemini CLI, OpenCode, Windsurf: MCP-first setup
- One pasteable agent prompt for setup

Explicit commands are available when a client exposes project skills or MCP prompts:

```text
/edgebase "what should I read before this change?"
/edgebase-goal "ship this feature without breaking the nearby tests"
```

The goal is narrow: reduce wasted search/read calls without lowering patch quality.

Repo: https://github.com/ychampion/edgebase

If you use coding agents on medium or large repos, I would love feedback on where the capsule helps, where it misses, and what benchmark would convince you it is worth keeping installed.

## Short Version

Launched Edgebase.

It gives coding agents fresh, source-backed context before they edit:

- read-first files
- blast radius
- nearby tests
- protected areas
- stale-context warnings
- provenance/confidence for graph edges

Local-first. Git-native. No Docker, cloud, API key, or graph DB.

Claude Code gets hooks. Codex gets MCP + project hooks/skills. Other agents get MCP. Slash-capable clients get `/edgebase` and `/edgebase-goal`.

Repo: https://github.com/ychampion/edgebase
