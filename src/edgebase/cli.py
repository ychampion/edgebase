from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .benchmark import run_benchmark
from .context import build_context
from .context_branches import create_checkpoint, create_fork_plan, render_resume, resume_snapshot
from .doctor import run_doctor
from .git import changed_files, find_repo_root
from .goal import build_goal_capsule, build_patch_passport
from .hooks import (
    handle_claude_pre_compact,
    handle_claude_pre_tool_use,
    handle_claude_post_tool_use,
    handle_claude_session_end,
    handle_claude_session_start,
    handle_claude_user_prompt_submit,
    handle_codex_pre_compact,
    handle_codex_pre_tool_use,
    handle_codex_post_tool_use,
    handle_codex_session_start,
    handle_codex_stop,
    handle_codex_user_prompt_submit,
    handle_git_post_commit,
    install_claude_hooks,
    install_codex_hooks,
    install_git_hook,
)
from .indexer import index_repo
from .mcp import serve
from .preflight import load_preflight_state, preflight_status, prepare_goal_capsule
from .setup import ALL_AGENTS, disable_repo, setup_repo
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", default=".", help="Repository root or any path inside it.")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Create local Edgebase state and optional agent instructions.")
    add_subcommand_root(init_p)
    init_p.add_argument("--write-agents-md", action="store_true", help="Write a minimal AGENTS.md if missing.")
    init_p.set_defaults(func=cmd_init)

    index_p = sub.add_parser("index", help="Build or refresh the local graph index.")
    add_subcommand_root(index_p)
    index_p.add_argument("--changed", action="store_true", help="Only reindex files changed in git status.")
    index_p.add_argument("--file", action="append", default=[], help="Repository-relative file to reindex.")
    index_p.set_defaults(func=cmd_index)

    setup_p = sub.add_parser("setup", help="Index repo and configure supported coding agents.")
    add_subcommand_root(setup_p)
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
    setup_p.add_argument("--no-hooks", action="store_true", help="Skip git and agent freshness hooks.")
    setup_p.add_argument("--no-agent-docs", action="store_true", help="Do not create AGENTS.md guidance.")
    setup_p.add_argument(
        "--command",
        default=None,
        help="Executable MCP clients should run. Defaults to the current Python with `-m edgebase`.",
    )
    setup_p.set_defaults(func=cmd_setup)

    disable_p = sub.add_parser("disable", help="Turn off Edgebase agent integrations for this repo.")
    add_subcommand_root(disable_p)
    disable_p.add_argument(
        "--agents",
        default="all",
        help=f"Comma-separated agents to disable. Supported: all,{','.join(ALL_AGENTS)}.",
    )
    disable_p.add_argument(
        "--scope",
        choices=("project", "global", "both"),
        default="project",
        help="Where to remove or disable supported MCP configs.",
    )
    disable_p.add_argument("--keep-hooks", action="store_true", help="Leave installed hooks in place.")
    disable_p.add_argument("--keep-agent-docs", action="store_true", help="Leave AGENTS.md Edgebase instructions.")
    disable_p.set_defaults(func=cmd_disable)

    context_p = sub.add_parser("context", help="Return a compact context capsule for a task.")
    add_subcommand_root(context_p)
    context_p.add_argument("task", help="Coding task or investigation goal.")
    context_p.add_argument("--changed-file", action="append", default=[], help="Changed file hint.")
    context_p.add_argument("--changed", action="store_true", help="Include changed files from `git status`.")
    context_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    context_p.add_argument("--json", action="store_true", help="Emit JSON with markdown and metadata.")
    context_p.set_defaults(func=cmd_context)

    goal_p = sub.add_parser("goal", help="Return an executable Goal Capsule and pre-edit Work Contract.")
    add_subcommand_root(goal_p)
    goal_p.add_argument("goal", help="Coding goal to turn into a work contract.")
    goal_p.add_argument("--changed-file", action="append", default=[], help="Changed file hint.")
    goal_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    goal_p.add_argument("--json", action="store_true", help="Emit the Work Contract JSON schema.")
    goal_p.add_argument("--record-preflight", action="store_true", help="Record this Goal Capsule as fresh preflight.")
    goal_p.set_defaults(func=cmd_goal)

    passport_p = sub.add_parser("passport", help="Return a Patch Passport for the current working tree.")
    add_subcommand_root(passport_p)
    passport_p.add_argument("goal", help="Goal the patch is meant to satisfy.")
    passport_p.add_argument("--changed-file", action="append", default=[], help="Changed file hint.")
    passport_p.add_argument(
        "--test",
        action="append",
        default=[],
        help='Explicit test evidence, for example "python3 -m unittest -v: pass".',
    )
    passport_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    passport_p.set_defaults(func=cmd_passport)

    checkpoint_p = sub.add_parser("checkpoint", help="Save an Edgebase context checkpoint for later resume.")
    add_subcommand_root(checkpoint_p)
    checkpoint_p.add_argument("message", help="Checkpoint goal or handoff message.")
    checkpoint_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    checkpoint_p.add_argument("--json", action="store_true", help="Emit machine-readable snapshot JSON.")
    checkpoint_p.set_defaults(func=cmd_checkpoint)

    fork_p = sub.add_parser("fork-plan", help="Create a git worktree plan from an Edgebase checkpoint.")
    add_subcommand_root(fork_p)
    fork_p.add_argument("message", help="Fork objective or handoff message.")
    fork_p.add_argument("--from-id", default="", help="Checkpoint id to branch from. Defaults to a new checkpoint.")
    fork_p.add_argument("--branch", default="", help="Worktree branch name. Defaults to edgebase/<message>.")
    fork_p.add_argument("--path", default="", help="Worktree path. Defaults next to the repo.")
    fork_p.add_argument("--allow-dirty", action="store_true", help="Allow creating a fork plan from a dirty tree.")
    fork_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    fork_p.add_argument("--json", action="store_true", help="Emit machine-readable snapshot JSON.")
    fork_p.set_defaults(func=cmd_fork_plan)

    resume_p = sub.add_parser("resume", help="Render a saved Edgebase checkpoint.")
    add_subcommand_root(resume_p)
    resume_p.add_argument("snapshot_id", nargs="?", default="", help="Checkpoint id. Defaults to latest.")
    resume_p.add_argument("--json", action="store_true", help="Emit machine-readable snapshot JSON.")
    resume_p.set_defaults(func=cmd_resume)

    preflight_p = sub.add_parser("preflight", help="Inspect or refresh the Edgebase pre-edit gate.")
    add_subcommand_root(preflight_p)
    preflight_sub = preflight_p.add_subparsers(dest="preflight_command")
    preflight_status_p = preflight_sub.add_parser("status", help="Show whether the Goal Capsule is fresh.")
    add_subcommand_root(preflight_status_p)
    preflight_status_p.add_argument("--json", action="store_true", help="Emit machine-readable status JSON.")
    preflight_status_p.set_defaults(func=cmd_preflight_status)
    preflight_refresh_p = preflight_sub.add_parser("refresh", help="Record a fresh Goal Capsule for the gate.")
    add_subcommand_root(preflight_refresh_p)
    preflight_refresh_p.add_argument("goal", help="Coding goal to record.")
    preflight_refresh_p.add_argument("--changed-file", action="append", default=[], help="Changed file hint.")
    preflight_refresh_p.add_argument("--budget", type=int, default=1200, help="Approximate token budget.")
    preflight_refresh_p.add_argument("--json", action="store_true", help="Emit the Work Contract JSON schema.")
    preflight_refresh_p.set_defaults(func=cmd_preflight_refresh)

    mcp_p = sub.add_parser("mcp", help="Run the Edgebase MCP server over stdio.")
    add_subcommand_root(mcp_p)
    mcp_p.set_defaults(func=cmd_mcp)

    hooks_p = sub.add_parser("install-hooks", help="Install git, Claude Code, and Codex hooks.")
    add_subcommand_root(hooks_p)
    hooks_p.add_argument("--git", action="store_true", help="Install git post-commit hook.")
    hooks_p.add_argument("--claude", action="store_true", help="Install Claude Code hooks.")
    hooks_p.add_argument("--codex", action="store_true", help="Install Codex hooks.")
    hooks_p.set_defaults(func=cmd_install_hooks)

    hook_p = sub.add_parser("hooks", help=argparse.SUPPRESS)
    add_subcommand_root(hook_p)
    hook_sub = hook_p.add_subparsers(dest="hook_command")
    add_hook_command(hook_sub, "git-post-commit", handle_git_post_commit)
    add_hook_command(hook_sub, "claude-session-start", handle_claude_session_start)
    add_hook_command(hook_sub, "claude-user-prompt-submit", handle_claude_user_prompt_submit)
    add_hook_command(hook_sub, "claude-pre-tool-use", handle_claude_pre_tool_use)
    add_hook_command(hook_sub, "claude-post-tool-use", handle_claude_post_tool_use)
    add_hook_command(hook_sub, "claude-pre-compact", handle_claude_pre_compact)
    add_hook_command(hook_sub, "claude-session-end", handle_claude_session_end)
    add_hook_command(hook_sub, "codex-session-start", handle_codex_session_start)
    add_hook_command(hook_sub, "codex-user-prompt-submit", handle_codex_user_prompt_submit)
    add_hook_command(hook_sub, "codex-pre-tool-use", handle_codex_pre_tool_use)
    add_hook_command(hook_sub, "codex-post-tool-use", handle_codex_post_tool_use)
    add_hook_command(hook_sub, "codex-pre-compact", handle_codex_pre_compact)
    add_hook_command(hook_sub, "codex-stop", handle_codex_stop)

    bench_p = sub.add_parser("benchmark", help="Run the validation benchmark harness.")
    add_subcommand_root(bench_p)
    bench_p.add_argument("--repo", required=True, help="Repository to benchmark.")
    bench_p.add_argument("--tasks", required=True, help="JSONL task file.")
    bench_p.add_argument("--out", required=True, help="Output JSON file.")
    bench_p.set_defaults(func=cmd_benchmark)

    stats_p = sub.add_parser("stats", help="Show local index stats.")
    add_subcommand_root(stats_p)
    stats_p.set_defaults(func=cmd_stats)

    doctor_p = sub.add_parser("doctor", help="Check index, MCP stdio, and configured agent clients.")
    add_subcommand_root(doctor_p)
    doctor_p.add_argument(
        "--agents",
        default="all",
        help=f"Comma-separated agents to check. Supported: all,{','.join(ALL_AGENTS)}.",
    )
    doctor_p.add_argument(
        "--scope",
        choices=("project", "global", "both"),
        default="project",
        help="Which config scope to check.",
    )
    doctor_p.add_argument("--json", action="store_true", help="Emit machine-readable check results.")
    doctor_p.set_defaults(func=cmd_doctor)

    return parser


def add_hook_command(subparsers: argparse._SubParsersAction, name: str, func) -> None:
    hook = subparsers.add_parser(name)
    add_subcommand_root(hook)
    hook.set_defaults(func=lambda args: func(args.root))


def add_subcommand_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        default=argparse.SUPPRESS,
        help="Repository root or any path inside it. May appear before or after the subcommand.",
    )


def cmd_init(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    with Store(root).connect():
        pass
    if args.write_agents_md:
        agents_path = root / "AGENTS.md"
        if not agents_path.exists():
            agents_path.write_text(
                "# Agent Instructions\n\n"
                "Keep static instructions minimal. For codebase structure, use slash commands when available:\n\n"
                "```text\n/edgebase \"<task>\"\n/edgebase-goal \"<goal>\"\n```\n\n"
                "Fallback commands:\n\n"
                "```bash\nedgebase context \"<task>\" --budget 1200\n"
                "edgebase goal \"<goal>\" --budget 1200 --record-preflight\n"
                "edgebase resume\n```\n",
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
    print(f"Indexed {result.files} files, {result.symbols} symbols, {result.edges} edges at {result.commit_sha}")
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
    print("Edgebase is enabled for the selected agents.")
    print("Restart your agent/IDE. Claude Code and Codex load Edgebase automatically when hooks are trusted.")
    print("Slash-capable clients get /edgebase and /edgebase-goal. MCP clients also get edgebase_context and edgebase_goal.")
    print("Turn it off with: `edgebase disable --scope {}`".format(args.scope))
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    root = find_repo_root(args.root)
    try:
        results = disable_repo(
            root,
            agents=[args.agents],
            scope=args.scope,
            remove_hooks=not args.keep_hooks,
            remove_agent_docs=not args.keep_agent_docs,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"disable failed: {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.action}: {result.path} ({result.detail})")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    changed = list(args.changed_file)
    if args.changed:
        changed.extend(changed_files(find_repo_root(args.root)))
    capsule = build_context(args.root, args.task, sorted(set(changed)), args.budget)
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


def cmd_goal(args: argparse.Namespace) -> int:
    if args.record_preflight:
        capsule = prepare_goal_capsule(args.root, args.goal, args.changed_file, args.budget, source="cli-goal")
    else:
        capsule = build_goal_capsule(args.root, args.goal, args.changed_file, args.budget)
    if args.json:
        print(json.dumps(capsule.contract.to_dict(), indent=2, sort_keys=True))
    else:
        print(capsule.markdown)
    return 0


def cmd_passport(args: argparse.Namespace) -> int:
    passport = build_patch_passport(args.root, args.goal, args.test, args.changed_file, args.budget)
    print(passport.markdown)
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    try:
        snapshot = create_checkpoint(args.root, args.message, args.budget)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Checkpoint {snapshot.id} recorded.")
        print(f"Resume with: edgebase resume {snapshot.id}")
    return 0


def cmd_fork_plan(args: argparse.Namespace) -> int:
    try:
        snapshot = create_fork_plan(
            args.root,
            args.message,
            args.budget,
            from_id=args.from_id,
            branch=args.branch,
            path=args.path,
            allow_dirty=args.allow_dirty,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Fork plan {snapshot.id} created.")
        print(f"Worktree: {snapshot.worktree_path}")
        print(f"Branch: {snapshot.worktree_branch}")
        print(f"Resume with: {snapshot.to_dict()['next_command']}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    try:
        snapshot = resume_snapshot(args.root, args.snapshot_id)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_resume(snapshot))
    return 0


def cmd_preflight_status(args: argparse.Namespace) -> int:
    status = preflight_status(args.root)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        state = load_preflight_state(args.root)
        outcome = "fresh" if status.get("fresh") else "stale"
        print(f"{outcome}: {status.get('reason')}")
        if state and state.get("goal"):
            print(f"goal: {state['goal']}")
        if state and state.get("created_at_iso"):
            print(f"created: {state['created_at_iso']}")
    return 0 if status.get("fresh") else 1


def cmd_preflight_refresh(args: argparse.Namespace) -> int:
    capsule = prepare_goal_capsule(args.root, args.goal, args.changed_file, args.budget, source="cli-preflight-refresh")
    if args.json:
        print(json.dumps(capsule.contract.to_dict(), indent=2, sort_keys=True))
    else:
        print(capsule.markdown)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    return serve(find_repo_root(args.root))


def cmd_install_hooks(args: argparse.Namespace) -> int:
    if not args.git and not args.claude and not args.codex:
        args.git = True
        args.claude = True
        args.codex = True
    root = find_repo_root(args.root)
    if args.git:
        print(f"Installed git hook: {install_git_hook(root)}")
    if args.claude:
        print(f"Installed Claude hooks: {install_claude_hooks(root)}")
    if args.codex:
        print(f"Installed Codex hooks: {install_codex_hooks(root)}")
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


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        checks = run_doctor(args.root, [args.agents], args.scope)
    except ValueError as exc:
        print(f"doctor failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([check.__dict__ for check in checks], indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"{check.status.upper():5} {check.name}: {check.detail}")
    return 1 if any(check.status == "fail" for check in checks) else 0
