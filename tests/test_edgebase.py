from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgebase import __version__
from edgebase.benchmark import run_external
from edgebase.context import build_context
from edgebase.doctor import run_doctor
from edgebase.goal import build_goal_capsule, build_patch_passport
from edgebase.preflight import load_preflight_state, preflight_status
from edgebase.graph import build_graph_export, render_dot, render_html, render_json, write_graph_artifacts
from edgebase.hooks import (
    handle_claude_post_tool_use,
    handle_claude_pre_tool_use,
    handle_claude_user_prompt_submit,
    install_claude_hooks,
    install_git_hook,
)
from edgebase.indexer import index_repo
from edgebase.mcp import McpServer
from edgebase.setup import AGENT_DOC_START, disable_repo, setup_repo
from edgebase.store import Store


class EdgebaseTests(unittest.TestCase):
    def test_indexes_python_symbols_edges_tests_and_git_metrics(self) -> None:
        with sample_repo() as repo:
            result = index_repo(repo)
            self.assertEqual(result.files, 3)
            self.assertGreaterEqual(result.symbols, 3)
            self.assertGreaterEqual(result.edges, 4)

            graph = Store(repo).load_graph()
            symbols = {(row["file_path"], row["name"], row["kind"]) for row in graph["symbols"]}
            self.assertIn(("app/auth.py", "login", "function"), symbols)
            self.assertIn(("app/auth.py", "AuthService", "class"), symbols)

            edges = {(row["rel"], row["dst_key"]) for row in graph["edges"]}
            self.assertIn(("IMPORTS", "hashlib"), edges)
            self.assertIn(("CALLS", "hashlib.sha256"), edges)
            self.assertIn(("TESTS", "app/auth.py"), edges)

            metrics = {row["file_path"]: row for row in graph["metrics"]}
            self.assertEqual(metrics["app/auth.py"]["owner"], "Tester")
            self.assertGreaterEqual(metrics["app/auth.py"]["churn_count"], 1)

    def test_context_returns_compact_source_backed_capsule(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            capsule = build_context(
                repo,
                "change login hashing behavior",
                ["app/auth.py"],
                budget=900,
            )
            self.assertIn("app/auth.py", capsule.markdown)
            self.assertIn("login", capsule.markdown)
            self.assertIn("confidence=", capsule.markdown)
            self.assertIn("Machine summary:", capsule.markdown)
            self.assertIn("app/auth.py", capsule.selected_files)

    def test_goal_capsule_markdown_and_contract_schema(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            capsule = build_goal_capsule(
                repo,
                "Add passwordless login support without breaking existing OAuth",
                ["app/auth.py"],
                budget=900,
            )
            self.assertIn("# Edgebase Goal Capsule", capsule.markdown)
            self.assertIn("Current hypothesis:", capsule.markdown)
            self.assertIn("Patch contract:", capsule.markdown)
            self.assertIn("app/auth.py", capsule.contract.selected_files)
            self.assertIn("tests/test_auth.py", capsule.contract.blast_radius)
            self.assertIn("pytest tests/test_auth.py", capsule.contract.test_plan)
            self.assertIn("html", capsule.graph_artifacts)
            self.assertTrue(Path(capsule.graph_artifacts["html"]).exists())
            self.assertEqual(
                set(capsule.contract.to_dict()),
                {
                    "goal",
                    "repo_commit",
                    "worktree_fingerprint",
                    "selected_files",
                    "must_read",
                    "must_not_touch",
                    "blast_radius",
                    "test_plan",
                    "acceptance_criteria",
                    "risk_flags",
                    "uncertainties",
                    "provenance",
                },
            )

    def test_goal_cli_json_emits_contract_schema(self) -> None:
        with sample_repo() as repo:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "edgebase",
                    "goal",
                    "--root",
                    str(repo),
                    "modify login",
                    "--changed-file",
                    "app/auth.py",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=10,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(
                set(data),
                {
                    "goal",
                    "repo_commit",
                    "worktree_fingerprint",
                    "selected_files",
                    "must_read",
                    "must_not_touch",
                    "blast_radius",
                    "test_plan",
                    "acceptance_criteria",
                    "risk_flags",
                    "uncertainties",
                    "provenance",
                },
            )
            self.assertEqual(data["goal"], "modify login")

    def test_graph_export_model_and_static_artifacts(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            export = build_graph_export(repo, max_nodes=120)
            self.assertEqual(export.scope, "repository")
            self.assertIn("app/auth.py", {node.id for node in export.nodes})
            self.assertIn(("tests/test_auth.py", "app/auth.py"), {(edge.source, edge.target) for edge in export.edges})

            graph_json = json.loads(render_json(export))
            self.assertIn("nodes", graph_json)
            self.assertIn("edges", graph_json)

            dot = render_dot(export)
            self.assertIn("digraph edgebase", dot)
            self.assertIn("app/auth.py", dot)

            html = render_html(export)
            self.assertIn("<script id=\"edgebase-data\" type=\"application/json\">", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)

            artifacts = write_graph_artifacts(
                repo,
                task="modify login",
                changed_files=["app/auth.py"],
                selected_files=["app/auth.py", "tests/test_auth.py"],
            )
            self.assertEqual(set(artifacts), {"html", "json", "dot"})
            for path in artifacts.values():
                self.assertTrue(Path(path).exists())
            self.assertNotIn("https://", Path(artifacts["html"]).read_text(encoding="utf-8"))

    def test_stale_detection_and_incremental_reindex(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            auth_path = repo / "app" / "auth.py"
            auth_path.write_text(
                auth_path.read_text(encoding="utf-8") + "\ndef logout() -> None:\n    return None\n",
                encoding="utf-8",
            )
            stale = build_context(repo, "add logout", ["app/auth.py"], budget=700)
            self.assertIn("app/auth.py", stale.stale_files)

            refreshed = index_repo(repo, ["app/auth.py"], reset=False)
            self.assertGreaterEqual(refreshed.files, 3)
            fresh = build_context(repo, "add logout", ["app/auth.py"], budget=700)
            self.assertNotIn("app/auth.py", fresh.stale_files)
            self.assertIn("logout", fresh.markdown)

    def test_mcp_exposes_context_and_goal_surfaces(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            server = McpServer(repo)
            initialized = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
            self.assertIsNotNone(initialized)
            self.assertEqual(initialized["result"]["serverInfo"]["version"], __version__)
            self.assertIn("prompts", initialized["result"]["capabilities"])

            listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertIsNotNone(listed)
            tools = listed["result"]["tools"]
            self.assertEqual([tool["name"] for tool in tools], ["edgebase_context", "edgebase_goal", "edgebase_checkpoint", "edgebase_fork_plan", "edgebase_resume"])

            prompts = server.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
            self.assertIsNotNone(prompts)
            self.assertEqual([prompt["name"] for prompt in prompts["result"]["prompts"]], ["edgebase", "goal"])

            called = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "edgebase_context",
                        "arguments": {"task": "modify login", "changed_files": ["app/auth.py"]},
                    },
                }
            )
            self.assertIsNotNone(called)
            text = called["result"]["content"][0]["text"]
            self.assertIn("# Edgebase Context", text)
            self.assertIn("app/auth.py", text)
            self.assertIn("Edgebase graph artifacts:", text)
            context_artifacts = called["result"]["structuredContent"]["graph_artifacts"]
            self.assertTrue(Path(context_artifacts["html"]).exists())

            prompt = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "prompts/get",
                    "params": {"name": "edgebase", "arguments": {"task": "modify login"}},
                }
            )
            self.assertIsNotNone(prompt)
            prompt_text = prompt["result"]["messages"][0]["content"]["text"]
            self.assertIn("# Edgebase Context", prompt_text)
            self.assertIn("first read set", prompt_text)
            self.assertIn("Edgebase graph artifacts:", prompt_text)

            goal_called = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "edgebase_goal",
                        "arguments": {"goal": "modify login", "changed_files": ["app/auth.py"]},
                    },
                }
            )
            self.assertIsNotNone(goal_called)
            goal_text = goal_called["result"]["content"][0]["text"]
            self.assertIn("# Edgebase Goal Capsule", goal_text)
            self.assertIn("Edgebase graph artifacts:", goal_text)
            self.assertIn("app/auth.py", goal_called["result"]["structuredContent"]["selected_files"])
            goal_artifacts = goal_called["result"]["structuredContent"]["graph_artifacts"]
            self.assertTrue(Path(goal_artifacts["html"]).exists())

            goal_prompt = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "prompts/get",
                    "params": {"name": "goal", "arguments": {"goal": "modify login"}},
                }
            )
            self.assertIsNotNone(goal_prompt)
            goal_prompt_text = goal_prompt["result"]["messages"][0]["content"]["text"]
            self.assertIn("# Edgebase Goal Capsule", goal_prompt_text)
            self.assertIn("executable work contract", goal_prompt_text)
            self.assertIn("Edgebase graph artifacts:", goal_prompt_text)

    def test_mcp_cli_accepts_root_after_subcommand(self) -> None:
        with sample_repo() as repo:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            payload = "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
                    "",
                ]
            )
            proc = subprocess.run(
                [sys.executable, "-m", "edgebase", "mcp", "--root", str(repo)],
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=10,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("edgebase_context", proc.stdout)

    def test_setup_writes_project_agent_configs_without_overwriting_agents_md(self) -> None:
        with sample_repo() as repo:
            (repo / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
            results = setup_repo(
                repo,
                agents=["claude,codex,cursor,gemini,opencode"],
                scope="project",
                install_hooks=False,
                write_agents_md=True,
            )
            self.assertTrue(any(result.path.name == "AGENTS.md" for result in results))
            self.assertIn(".edgebase/", (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
            agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertTrue(agents_md.startswith("# Existing\n"))
            self.assertIn(AGENT_DOC_START, agents_md)
            self.assertIn("Do not wait for the user", agents_md)

            claude = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn("-m", claude["mcpServers"]["edgebase"]["args"])
            self.assertIn("edgebase", claude["mcpServers"]["edgebase"]["args"])

            skill = (repo / ".claude" / "skills" / "edgebase" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: edgebase", skill)
            self.assertIn("argument-hint", skill)
            self.assertIn(".edgebase/graphs/latest.*", skill)

            goal_skill = (repo / ".claude" / "skills" / "goal" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: goal", goal_skill)
            self.assertIn("edgebase_goal", goal_skill)
            self.assertIn(".edgebase/graphs/latest.*", goal_skill)

            cursor = json.loads((repo / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", cursor["mcpServers"])

            gemini = json.loads((repo / ".gemini" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", gemini["mcpServers"])

            opencode = json.loads((repo / ".opencode.json").read_text(encoding="utf-8"))
            self.assertEqual(opencode["mcp"]["edgebase"]["type"], "local")

            codex = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.edgebase]", codex)
            self.assertIn("enabled = true", codex)

    def test_codex_setup_writes_preflight_hooks_and_skills(self) -> None:
        with sample_repo() as repo:
            setup_repo(
                repo,
                agents=["codex"],
                scope="project",
                install_hooks=True,
                write_agents_md=True,
            )
            codex = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[features]", codex)
            self.assertIn("hooks = true", codex)

            hooks = json.loads((repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [hook["event"] for hook in hooks["hooks"]],
                ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop"],
            )
            self.assertTrue(all("edgebase hooks codex-" in hook["command"] for hook in hooks["hooks"]))

            skill = (repo / ".agents" / "skills" / "edgebase" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("edgebase_context", skill)
            self.assertIn("edgebase_checkpoint", skill)
            self.assertNotIn("--record-preflight", skill)

            goal_skill = (repo / ".agents" / "skills" / "goal" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("edgebase_goal", goal_skill)
            self.assertIn("--record-preflight", goal_skill)

            checks = {check.name: check for check in run_doctor(repo, agents=["codex"], scope="project")}
            self.assertEqual(checks["Codex project config"].status, "ok")
            self.assertEqual(checks["Codex hooks feature"].status, "ok")
            self.assertEqual(checks["Codex hooks"].status, "ok")
            self.assertEqual(checks["Codex /edgebase skill"].status, "ok")
            self.assertEqual(checks["Codex /goal skill"].status, "ok")

    def test_codex_hooks_merge_and_disable_preserve_unrelated_hooks(self) -> None:
        with sample_repo() as repo:
            hooks_path = repo / ".codex" / "hooks.json"
            hooks_path.parent.mkdir(parents=True)
            hooks_path.write_text(
                json.dumps({"hooks": [{"event": "PreToolUse", "command": "echo keep"}], "custom": True}) + "\n",
                encoding="utf-8",
            )
            setup_repo(
                repo,
                agents=["codex"],
                scope="project",
                install_hooks=True,
                write_agents_md=False,
            )
            installed = json.loads(hooks_path.read_text(encoding="utf-8"))
            self.assertTrue(installed["custom"])
            self.assertIn({"event": "PreToolUse", "command": "echo keep"}, installed["hooks"])
            self.assertEqual(sum("edgebase hooks codex-" in hook["command"] for hook in installed["hooks"]), 6)

            disable_repo(repo, agents=["codex"], scope="project")
            remaining = json.loads(hooks_path.read_text(encoding="utf-8"))
            self.assertEqual(remaining, {"custom": True, "hooks": [{"event": "PreToolUse", "command": "echo keep"}]})

    def test_disable_removes_project_integrations_and_agent_docs(self) -> None:
        with sample_repo() as repo:
            setup_repo(
                repo,
                agents=["claude,codex,cursor,gemini,opencode"],
                scope="project",
                install_hooks=True,
                write_agents_md=True,
            )
            results = disable_repo(repo, agents=["claude,codex,cursor,gemini,opencode"], scope="project")
            self.assertTrue(results)

            agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn(AGENT_DOC_START, agents_md)

            claude = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))
            self.assertNotIn("edgebase", claude.get("mcpServers", {}))

            cursor = json.loads((repo / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertNotIn("edgebase", cursor.get("mcpServers", {}))

            codex = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertNotIn("[mcp_servers.edgebase]", codex)

            opencode = json.loads((repo / ".opencode.json").read_text(encoding="utf-8"))
            self.assertFalse(opencode["mcp"]["edgebase"]["enabled"])

            claude_hooks = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertNotIn("hooks", claude_hooks)
            self.assertFalse((repo / ".claude" / "skills" / "edgebase" / "SKILL.md").exists())
            self.assertFalse((repo / ".claude" / "skills" / "goal" / "SKILL.md").exists())

    def test_claude_prompt_hook_injects_context_for_coding_prompts(self) -> None:
        with sample_repo() as repo:
            setup_repo(
                repo,
                agents=["claude"],
                scope="project",
                install_hooks=True,
                write_agents_md=True,
            )
            settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("UserPromptSubmit", settings["hooks"])
            self.assertIn("PreToolUse", settings["hooks"])
            checks = {check.name: check for check in run_doctor(repo, agents=["claude"], scope="project")}
            self.assertEqual(checks["Claude Code hooks"].status, "ok")
            self.assertEqual(checks["Claude Code /edgebase skill"].status, "ok")
            self.assertEqual(checks["Claude Code /goal skill"].status, "ok")

            old_stdin = sys.stdin
            stdout = io.StringIO()
            try:
                sys.stdin = io.StringIO(json.dumps({"prompt": "change login hashing behavior"}))
                with contextlib.redirect_stdout(stdout):
                    code = handle_claude_user_prompt_submit(repo)
            finally:
                sys.stdin = old_stdin
            self.assertEqual(code, 0)
            data = json.loads(stdout.getvalue())
            output = data["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "UserPromptSubmit")
            self.assertIn("# Edgebase Goal Capsule", output["additionalContext"])
            self.assertIn("app/auth.py", output["additionalContext"])
            self.assertIn("Edgebase graph artifacts:", output["additionalContext"])
            self.assertTrue((repo / ".edgebase" / "graphs" / "latest.html").exists())
            self.assertTrue(preflight_status(repo)["fresh"])
            self.assertEqual(load_preflight_state(repo)["goal"], "change login hashing behavior")

    def test_claude_pre_tool_hook_injects_work_contract(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            old_stdin = sys.stdin
            stdout = io.StringIO()
            try:
                sys.stdin = io.StringIO(
                    json.dumps(
                        {
                            "goal": "modify login",
                            "tool_input": {"file_path": str(repo / "app" / "auth.py")},
                        }
                    )
                )
                with contextlib.redirect_stdout(stdout):
                    code = handle_claude_pre_tool_use(repo)
            finally:
                sys.stdin = old_stdin
            self.assertEqual(code, 0)
            data = json.loads(stdout.getvalue())
            output = data["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse")
            self.assertEqual(output["permissionDecision"], "deny")
            self.assertIn("no fresh Edgebase Goal Capsule", output["permissionDecisionReason"])

    def test_pre_tool_hook_does_not_block_named_read_tools(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            old_stdin = sys.stdin
            stdout = io.StringIO()
            try:
                sys.stdin = io.StringIO(
                    json.dumps(
                        {
                            "tool_name": "Read",
                            "tool_input": {"file_path": str(repo / "app" / "auth.py")},
                        }
                    )
                )
                with contextlib.redirect_stdout(stdout):
                    code = handle_claude_pre_tool_use(repo)
            finally:
                sys.stdin = old_stdin
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")

    def test_claude_post_tool_hook_emits_edit_delta(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            auth_path = repo / "app" / "auth.py"
            auth_path.write_text(
                auth_path.read_text(encoding="utf-8") + "\ndef magic_link() -> str:\n    return 'token'\n",
                encoding="utf-8",
            )
            old_stdin = sys.stdin
            stdout = io.StringIO()
            try:
                sys.stdin = io.StringIO(
                    json.dumps(
                        {
                            "goal": "modify login",
                            "tool_input": {"file_path": str(auth_path)},
                        }
                    )
                )
                with contextlib.redirect_stdout(stdout):
                    code = handle_claude_post_tool_use(repo)
            finally:
                sys.stdin = old_stdin
            self.assertEqual(code, 0)
            data = json.loads(stdout.getvalue())
            output = data["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PostToolUse")
            self.assertIn("# Edgebase Edit Delta", output["additionalContext"])
            self.assertIn("tests/test_auth.py", output["additionalContext"])
            self.assertIn("Edgebase graph artifacts:", output["additionalContext"])
            self.assertTrue((repo / ".edgebase" / "graphs" / "latest.html").exists())

    def test_patch_passport_records_explicit_tests_only(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            no_tests = build_patch_passport(repo, "modify login", [], ["app/auth.py"])
            self.assertIn("# Patch Passport", no_tests.markdown)
            self.assertIn("No tests recorded by Edgebase.", no_tests.markdown)
            self.assertIn("Required checks not recorded:", no_tests.markdown)

            with_tests = build_patch_passport(
                repo,
                "modify login",
                ["python3 -m unittest -v: pass"],
                ["app/auth.py"],
            )
            self.assertIn("python3 -m unittest -v [pass]", with_tests.markdown)
            self.assertNotIn("No tests recorded by Edgebase.", with_tests.markdown)

    def test_hook_commands_shell_quote_repo_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="edgebase quote ' ") as tmp:
            repo = Path(tmp) / "repo with spaces 'and quotes"
            repo.mkdir()
            run(repo, "git", "init")

            settings_path = install_claude_hooks(repo)
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
            self.assertEqual(
                shlex.split(command),
                [
                    sys.executable,
                    "-m",
                    "edgebase",
                    "hooks",
                    "claude-user-prompt-submit",
                    "--root",
                    str(repo.resolve()),
                ],
            )

            hook_path = install_git_hook(repo)
            hook_lines = hook_path.read_text(encoding="utf-8").splitlines()
            git_command = hook_lines[hook_lines.index("# edgebase post-commit hook") + 1]
            self.assertEqual(
                shlex.split(git_command),
                [
                    sys.executable,
                    "-m",
                    "edgebase",
                    "hooks",
                    "git-post-commit",
                    "--root",
                    str(repo.resolve()),
                ],
            )

    def test_benchmark_external_runner_uses_argument_vector(self) -> None:
        with sample_repo() as repo:
            env_name = "EDGEBASE_TEST_BENCH_CMD"
            old = os.environ.get(env_name)
            os.environ[env_name] = f"{shlex.quote(sys.executable)} -c \"print('bench output')\""
            try:
                result = run_external(
                    repo,
                    {"id": "task-1", "task": "change login", "changed_files": []},
                    "external",
                    env_name,
                )
            finally:
                if old is None:
                    os.environ.pop(env_name, None)
                else:
                    os.environ[env_name] = old
            self.assertEqual(result.skipped_reason, "")
            self.assertGreater(result.token_estimate, 0)

    def test_index_includes_untracked_non_ignored_sources(self) -> None:
        with sample_repo() as repo:
            (repo / "app" / "scratch.py").write_text("def draft() -> int:\n    return 1\n", encoding="utf-8")
            result = index_repo(repo)
            self.assertEqual(result.files, 4)

            graph = Store(repo).load_graph()
            symbols = {(row["file_path"], row["name"]) for row in graph["symbols"]}
            self.assertIn(("app/scratch.py", "draft"), symbols)

    def test_context_changed_flag_includes_git_status_files(self) -> None:
        with sample_repo() as repo:
            index_repo(repo)
            auth_path = repo / "app" / "auth.py"
            auth_path.write_text(auth_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            proc = subprocess.run(
                [sys.executable, "-m", "edgebase", "context", "review auth changes", "--root", str(repo), "--changed", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertIn("app/auth.py", payload["stale_files"])


class sample_repo:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "app").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "app" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "app" / "auth.py").write_text(
            "\n".join(
                [
                    "import hashlib",
                    "",
                    "class AuthService:",
                    "    def verify(self, password: str, digest: str) -> bool:",
                    "        return login(password) == digest",
                    "",
                    "def login(password: str) -> str:",
                    "    return hashlib.sha256(password.encode()).hexdigest()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (self.root / "tests" / "test_auth.py").write_text(
            "\n".join(
                [
                    "from app.auth import login",
                    "",
                    "def test_login():",
                    "    assert login('pw')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        run(self.root, "git", "init")
        run(self.root, "git", "config", "user.email", "tester@example.com")
        run(self.root, "git", "config", "user.name", "Tester")
        run(self.root, "git", "add", ".")
        run(self.root, "git", "commit", "-m", "initial")
        return self.root

    def __exit__(self, exc_type, exc, tb) -> None:
        self.tmp.cleanup()


def run(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
