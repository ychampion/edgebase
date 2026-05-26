# Validation

Edgebase should earn adoption through evidence.

The core claim is narrow:

> For coding-agent tasks in medium and large repos, Edgebase should reduce context tokens and exploratory tool calls without reducing patch quality.

## Baselines

Every benchmark should include:

- plain `rg` plus file reads
- Edgebase
- CodeGraphContext, when installed
- codebase-memory-mcp, when installed
- GitNexus, when installed

External tools are optional command templates so the harness remains usable without downloading competitors.

## Repository Matrix

Run against at least:

- one TypeScript app
- one Python service/library
- one Go or Rust project
- one monorepo
- one repo with generated files and ignored directories

## Metrics

Record:

- context token estimate
- goal capsule token estimate
- tool-call estimate
- wall time
- selected files
- work contract blast radius and required checks
- advisory change radius categories, confidence, and side-effect risks
- stale-context incidents
- false dependency edges found by review
- whether the paired agent patch succeeded
- whether relevant tests were discovered

## Required Smoke Tests

For every release:

```bash
python3 -m unittest -v
python3 -m compileall -q src tests
python3 -m edgebase setup --scope project --agents claude,codex,cursor,gemini,opencode
python3 -m edgebase doctor --scope project --agents claude,codex,cursor,gemini,opencode
python3 -m edgebase goal "change login hashing behavior" --changed-file tests/test_edgebase.py --json
python3 -m edgebase radius tests/test_edgebase.py --goal "change login hashing behavior" --json
python3 -m edgebase preflight refresh "change login hashing behavior" --changed-file tests/test_edgebase.py --json
python3 -m edgebase preflight status --json
python3 -m edgebase passport "change login hashing behavior" --test "python3 -m unittest -v: pass"
python3 -m edgebase checkpoint "release smoke checkpoint"
python3 -m edgebase resume
printf '{"prompt":"change login hashing behavior"}' | python3 -m edgebase hooks claude-user-prompt-submit --root .
printf '{"goal":"change login hashing behavior","tool_input":{"file_path":"tests/test_edgebase.py"}}' | python3 -m edgebase hooks claude-pre-tool-use --root .
printf '{"prompt":"change login hashing behavior"}' | python3 -m edgebase hooks codex-user-prompt-submit --root .
printf '{"goal":"change login hashing behavior","tool_input":{"file_path":"tests/test_edgebase.py"}}' | python3 -m edgebase hooks codex-pre-tool-use --root .
```

When installed from GitHub, verify:

```bash
python3 -m pip install --user git+https://github.com/ychampion/edgebase.git
python3 -m edgebase setup --scope project
python3 -m edgebase doctor --scope project
```

## Agent Client Verification

Where binaries are available:

- Claude Code: `claude mcp list`, `claude mcp get edgebase`
- Codex: `codex mcp list`
- Gemini CLI: `gemini mcp list`
- OpenCode: `opencode mcp list`

For Claude Code, also validate that `.claude/settings.json` contains `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `SessionEnd`, and that `.claude/skills/edgebase/SKILL.md`, `.claude/skills/edgebase-goal/SKILL.md`, `.claude/skills/goal/SKILL.md`, and the generated `.claude/skills/edgebase-*/SKILL.md` command skills exist.

For Codex, validate that `.codex/config.toml` contains `[mcp_servers.edgebase]` and `hooks = true`, `.codex/hooks.json` uses the event-keyed Codex hook shape with `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `Stop`, and `.agents/skills/edgebase/SKILL.md`, `.agents/skills/edgebase-goal/SKILL.md`, `.agents/skills/goal/SKILL.md`, and the generated `.agents/skills/edgebase-*/SKILL.md` command skills exist.

For clients not installed in the verification environment, validate the generated config shape and the Edgebase MCP stdio handshake.

## Kill Criteria

Stop or redesign if:

- Edgebase cannot reduce token cost or search/read calls versus plain exploration.
- Index freshness is unreliable after edits, branch switches, rebases, or generated-file churn.
- Dynamic-language call graph confidence cannot be represented honestly.
- Normal onboarding requires Docker, cloud services, API keys, or a graph database.
- Agents ignore the tool even with a minimal marker instruction.
- Setup cannot be disabled cleanly.

## Reporting

Publish benchmark results with:

- repo name and commit
- task descriptions
- exact Edgebase version and command
- baseline commands
- raw JSON output
- manual review notes for false edges and missing context
