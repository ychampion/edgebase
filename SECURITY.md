# Security

Edgebase runs locally and indexes source code from the repository where it is installed.

## What Edgebase Does Not Do

- It does not call a cloud API.
- It does not require API keys.
- It does not upload source code.
- It does not execute repository code during indexing.
- It does not install Docker containers or external services.

## Local Files Written

Edgebase may write:

- `.edgebase/index.sqlite3`
- agent MCP config files
- a marker-bounded `AGENTS.md` block
- `.git/hooks/post-commit`
- Claude Code hook entries

Use `python3 -m edgebase disable --scope both` to remove or disable generated integrations.

## Reporting Issues

Please report security issues privately to the repository owner rather than opening a public issue with exploit details.

Include:

- Edgebase version or commit
- operating system
- command run
- affected config file
- whether untrusted repository content was involved
