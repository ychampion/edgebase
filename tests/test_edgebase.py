from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgebase import __version__
from edgebase.context import build_context
from edgebase.doctor import run_doctor
from edgebase.hooks import handle_claude_user_prompt_submit
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

    def test_mcp_exposes_single_context_tool(self) -> None:
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
            self.assertEqual([tool["name"] for tool in tools], ["edgebase_context"])

            prompts = server.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
            self.assertIsNotNone(prompts)
            self.assertEqual([prompt["name"] for prompt in prompts["result"]["prompts"]], ["edgebase"])

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

            cursor = json.loads((repo / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", cursor["mcpServers"])

            gemini = json.loads((repo / ".gemini" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", gemini["mcpServers"])

            opencode = json.loads((repo / ".opencode.json").read_text(encoding="utf-8"))
            self.assertEqual(opencode["mcp"]["edgebase"]["type"], "local")

            codex = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.edgebase]", codex)
            self.assertIn("enabled = true", codex)

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
            checks = {check.name: check for check in run_doctor(repo, agents=["claude"], scope="project")}
            self.assertEqual(checks["Claude Code hooks"].status, "ok")
            self.assertEqual(checks["Claude Code /edgebase skill"].status, "ok")

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
            self.assertIn("# Edgebase Context", output["additionalContext"])
            self.assertIn("app/auth.py", output["additionalContext"])

    def test_index_includes_untracked_non_ignored_sources(self) -> None:
        with sample_repo() as repo:
            (repo / "app" / "scratch.py").write_text("def draft() -> int:\n    return 1\n", encoding="utf-8")
            result = index_repo(repo)
            self.assertEqual(result.files, 4)

            graph = Store(repo).load_graph()
            symbols = {(row["file_path"], row["name"]) for row in graph["symbols"]}
            self.assertIn(("app/scratch.py", "draft"), symbols)


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
