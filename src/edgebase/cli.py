from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import run_benchmark
from .context import build_context
from .git import changed_files, find_repo_root
from .hooks import (
    handle_claude_post_tool_use,
    handle_claude_session_start,
    handle_git_post_commit,
    install_claude_hooks,
    install_git_hook,
)
from .indexer import index_repo
from .mcp import serve
from .setup import ALL_AGENTS, setup_repo
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgebase",
        description="Git-native, provenance-backed context capsules for coding agents.",
    )
    parser.add_argument("--root", default=".", help="Repository root or any path inside it.")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Create local Edgebase state and optional agent instructions.")
    init_p.add_argument("--write-agents-md", action="store_true", help="Write a minimal AGENTS.md if missing.")
    init_p.set_defaults(func=cmd_init)

    index_p = sub.add_parser("index", help="Build or refresh the local graph index.")
    index_p.add_argument("--changed", action="store_true", help="Only reindex files changed in git status.")
    index_p.add_argument("--file", action="append", default=[], help="Repository-relative file to reindex.")
    index_p.set_defaults(func=cmd_index)

    setup_p = sub.add_parser("setup", help="Index repo and configure supported coding agents.")
    setup_p.add_argument(
        "--agents",
        default="all",
        help=f"Comma-separated agents to configure. Supported: all,{','.join(ALL_AGENTS)}.",
    )
    setup_p.add_argument(
        "--scope",
        choices=("project", "global", "both"),
        default="project",
        help="Where to write supported MCP configs.",
    )
    setup_p.add_argument(
        "--no-hooks",
        action="store_true",
        help="Skip git and Claude Code freshness hooks.",
    )
    setup_p.add_argument(
        "--no-agent-docs",
        action="store_true",
        help="Do not create AGENTS.md or EDGEBASE.md guidance.",
    )
    setup_p.add_argument(
        "--command",
        default="edgebase",
        help="Command MCP clients should run. Use an absolute path if edgebase is not on PATH.",
    )
    setup_p.set_defaults(func=cmd_setup)

    context_p = sub.add_parser("context", help="Return a compact context capsule for a task.")
    context_p.add_argument("task", help="Coding task or investigation goal.")
    context_p.add_argument("--changed-file", action="append", default=[], help="Changed file hint.")
    context_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    context_p.add_argument("--json", action="store_true", help="Emit JSON with markdown and metadata.")
    context_p.set_defaults(func=cmd_context)

    mcp_p = sub.add_parser("mcp", help="Run the Edgebase MCP server over stdio.")
    mcp_p.set_defaults(func=cmd_mcp)

    hooks_p = sub.add_parser("install-hooks", help="Install git and/or Claude Code hooks.")
    hooks_p.add_argument("--git", action="store_true", help="Install git post-commit hook.")
    hooks_p.add_argument("--claude", action="store_true", help="Install Claude Code hooks.")
    hooks_p.set_defaults(func=cmd_install_hooks)

    hook_p = sub.add_parser("hooks", help=argparse.SUPPRESS)
    hook_sub = hook_p.add_subparsers(dest="hook_command")
    git_hook = hook_sub.add_parser("git-post-commit")
    git_hook.set_defaults(func=lambda args: handle_git_post_commit(args.root))
    session_hook = hook_sub.add_parser("claude-session-start")
    session_hook.set_defaults(func=lambda args: handle_claude_session_start(args.root))
    post_hook = hook_sub.add_parser("claude-post-tool-use")
    post_hook.set_defaults(func=lambda args: handle_claude_post_tool_use(args.root))

    bench_p = sub.add_parser("benchmark", help="Run the validation benchmark harness.")
    bench_p.add_argument("--repo", required=True, help="Repository to benchmark.")
    bench_p.add_argument("--tasks", required=True, help="JSONL task file.")
    bench_p.add_argument("--out", required=True, help="Output JSON file.")
    bench_p.set_defaults(func=cmd_benchmark)

    stats_p = sub.add_parser("stats", help="Show local index stats.")
    stats_p.set_defaults(func=cmd_stats)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    with Store(root).connect():
        pass
    if args.write_agents_md:
        agents_path = root / "AGENTS.md"
        if not agents_path.exists():
            agents_path.write_text(
                "# Agent Instructions\n\n"
                "Keep static instructions minimal. For codebase structure, run:\n\n"
                "```bash\nedgebase context \"<task>\" --budget 1200\n```\n",
                encoding="utf-8",
            )
    print(f"Initialized Edgebase at {root / '.edgebase'}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    paths = list(args.file)
    reset = True
    if args.changed:
        paths.extend(changed_files(root))
        reset = False
    if paths:
        reset = False
    result = index_repo(root, sorted(set(paths)) if paths else None, reset=reset)
    print(
        f"Indexed {result.files} files, {result.symbols} symbols, {result.edges} edges at {result.commit_sha}"
    )
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    try:
        results = setup_repo(
            root,
            agents=[args.agents],
            scope=args.scope,
            install_hooks=not args.no_hooks,
            write_agents_md=not args.no_agent_docs,
            command=args.command,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.action}: {result.path} ({result.detail})")
    print("")
    print("Restart your agent/IDE, then ask it: `Use edgebase_context for this task before editing.`")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    capsule = build_context(args.root, args.task, args.changed_file, args.budget)
    if args.json:
        print(
            json.dumps(
                {
                    "markdown": capsule.markdown,
                    "selected_files": list(capsule.selected_files),
                    "token_estimate": capsule.token_estimate,
                    "stale_files": list(capsule.stale_files),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(capsule.markdown)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    return serve(find_repo_root(args.root))


def cmd_install_hooks(args: argparse.Namespace) -> int:
    if not args.git and not args.claude:
        print("Choose at least one hook target: --git or --claude", file=sys.stderr)
        return 2
    root = find_repo_root(args.root)
    if args.git:
        print(f"Installed git hook: {install_git_hook(root)}")
    if args.claude:
        print(f"Installed Claude hooks: {install_claude_hooks(root)}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    results = run_benchmark(args.repo, args.tasks, args.out)
    print(f"Wrote {len(results)} benchmark rows to {args.out}")
    skipped = [r for r in results if r.skipped_reason]
    if skipped:
        print(f"Skipped {len(skipped)} external runs; set EDGEBASE_BENCH_* command templates to enable them.")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    store = Store(root)
    if not store.exists():
        print("No Edgebase index found. Run `edgebase index`.")
        return 1
    print(json.dumps(store.stats(), indent=2, sort_keys=True))
    return 0
