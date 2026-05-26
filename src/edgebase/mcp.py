from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .context import build_context
from .indexer import index_repo
from .store import Store


TOOL_NAME = "edgebase_context"


def tool_definition() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "title": "Edgebase Context",
        "description": "Return a compact, source-backed context capsule for a coding task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The coding task or investigation goal.",
                },
                "changed_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional repository-relative files already changed or about to change.",
                },
                "budget": {
                    "type": "integer",
                    "minimum": 300,
                    "maximum": 8000,
                    "description": "Approximate token budget for the returned context capsule.",
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    }


class McpServer:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        try:
            if method == "initialize":
                return self._result(
                    request_id,
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "edgebase", "version": "0.1.0"},
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": [tool_definition()]})
            if method == "tools/call":
                params = request.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                if name != TOOL_NAME:
                    return self._error(request_id, -32602, f"Unknown tool: {name}")
                task = str(args.get("task") or "").strip()
                if not task:
                    return self._error(request_id, -32602, "`task` is required")
                budget = int(args.get("budget") or 1200)
                changed_files = [str(p) for p in args.get("changed_files") or []]
                if not Store(self.root).exists():
                    index_repo(self.root)
                capsule = build_context(self.root, task, changed_files, budget)
                return self._result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": capsule.markdown}],
                        "structuredContent": {
                            "selected_files": list(capsule.selected_files),
                            "token_estimate": capsule.token_estimate,
                            "stale_files": list(capsule.stale_files),
                        },
                    },
                )
            return self._error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # MCP servers should return JSON-RPC errors, not crash.
            return self._error(request_id, -32603, str(exc))

    def _result(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(root: str | Path) -> int:
    server = McpServer(root)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        else:
            response = server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0
