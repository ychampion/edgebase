from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgebase.context import build_context
from edgebase.indexer import index_repo
from edgebase.mcp import McpServer
from edgebase.setup import setup_repo
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
            listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertIsNotNone(listed)
            tools = listed["result"]["tools"]
            self.assertEqual([tool["name"] for tool in tools], ["edgebase_context"])

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
            self.assertTrue(any(result.path.name == "EDGEBASE.md" for result in results))
            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), "# Existing\n")

            claude = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(claude["mcpServers"]["edgebase"]["command"], "edgebase")

            cursor = json.loads((repo / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", cursor["mcpServers"])

            gemini = json.loads((repo / ".gemini" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("edgebase", gemini["mcpServers"])

            opencode = json.loads((repo / ".opencode.json").read_text(encoding="utf-8"))
            self.assertEqual(opencode["mcp"]["edgebase"]["type"], "local")

            codex = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.edgebase]", codex)

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
