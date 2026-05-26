from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .context import build_context
from .goal import build_goal_capsule
from .indexer import index_repo
from .store import Store


TOOL_NAME = "edgebase_context"
GOAL_TOOL_NAME = "edgebase_goal"


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


def goal_tool_definition() -> dict[str, Any]:
    return {
        "name": GOAL_TOOL_NAME,
        "title": "Edgebase Goal Capsule",
        "description": "Return an executable Goal Capsule and Work Contract for a coding goal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The coding goal to turn into a work contract.",
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
                    "description": "Approximate token budget for the returned goal capsule.",
                },
            },
            "required": ["goal"],
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
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "prompts": {"listChanged": False},
                        },
                        "serverInfo": {"name": "edgebase", "version": __version__},
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": [tool_definition(), goal_tool_definition()]})
            if method == "prompts/list":
                return self._result(
                    request_id,
                    {
                        "prompts": [
                            {
                                "name": "edgebase",
                                "title": "Edgebase Context",
                                "description": "Fetch source-backed codebase context before editing.",
                                "arguments": [
                                    {
                                        "name": "task",
                                        "description": "The coding task or investigation goal.",
                                        "required": True,
                                    },
                                    {
                                        "name": "budget",
                                        "description": "Approximate token budget.",
                                        "required": False,
                                    },
                                ],
                            },
                            {
                                "name": "goal",
                                "title": "Edgebase Goal Capsule",
                                "description": "Fetch an executable Goal Capsule and Work Contract before editing.",
                                "arguments": [
                                    {
                                        "name": "goal",
                                        "description": "The coding goal to turn into a work contract.",
                                        "required": True,
                                    },
                                    {
                                        "name": "budget",
                                        "description": "Approximate token budget.",
                                        "required": False,
                                    },
                                ],
                            }
                        ]
                    },
                )
            if method == "prompts/get":
                params = request.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                budget = int(args.get("budget") or 1200)
                if not Store(self.root).exists():
                    index_repo(self.root)
                if name == "edgebase":
                    task = str(args.get("task") or "").strip()
                    if not task:
                        return self._error(request_id, -32602, "`task` is required")
                    capsule = build_context(self.root, task, [], budget)
                    text = (
                        f"{capsule.markdown}\n\n"
                        "Use this Edgebase context as the first read set before broad exploration or edits."
                    )
                    description = "Edgebase source-backed context capsule."
                elif name == "goal":
                    goal = str(args.get("goal") or args.get("task") or "").strip()
                    if not goal:
                        return self._error(request_id, -32602, "`goal` is required")
                    capsule = build_goal_capsule(self.root, goal, [], budget)
                    text = (
                        f"{capsule.markdown}\n\n"
                        "Use this Goal Capsule as the executable work contract before editing."
                    )
                    description = "Edgebase executable Goal Capsule."
                else:
                    return self._error(request_id, -32602, f"Unknown prompt: {name}")
                return self._result(
                    request_id,
                    {
                        "description": description,
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": text,
                                },
                            }
                        ],
                    },
                )
            if method == "tools/call":
                params = request.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                budget = int(args.get("budget") or 1200)
                changed_files = [str(p) for p in args.get("changed_files") or []]
                if not Store(self.root).exists():
                    index_repo(self.root)
                if name == TOOL_NAME:
                    task = str(args.get("task") or "").strip()
                    if not task:
                        return self._error(request_id, -32602, "`task` is required")
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
                if name == GOAL_TOOL_NAME:
                    goal = str(args.get("goal") or args.get("task") or "").strip()
                    if not goal:
                        return self._error(request_id, -32602, "`goal` is required")
                    capsule = build_goal_capsule(self.root, goal, changed_files, budget)
                    return self._result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": capsule.markdown}],
                            "structuredContent": capsule.contract.to_dict(),
                        },
                    )
                return self._error(request_id, -32602, f"Unknown tool: {name}")
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
