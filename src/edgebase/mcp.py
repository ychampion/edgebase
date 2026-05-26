from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .context import build_context
from .context_branches import create_checkpoint, create_fork_plan, render_resume, resume_snapshot
from .goal import build_goal_capsule
from .graph import graph_artifact_summary, write_graph_artifacts
from .indexer import index_repo
from .store import Store


TOOL_NAME = "edgebase_context"
GOAL_TOOL_NAME = "edgebase_goal"
CHECKPOINT_TOOL_NAME = "edgebase_checkpoint"
FORK_PLAN_TOOL_NAME = "edgebase_fork_plan"
RESUME_TOOL_NAME = "edgebase_resume"


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


def checkpoint_tool_definition() -> dict[str, Any]:
    return {
        "name": CHECKPOINT_TOOL_NAME,
        "title": "Edgebase Checkpoint",
        "description": "Record a local context checkpoint for cross-agent resume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What the agent understood, decided, or reached.",
                },
                "budget": {
                    "type": "integer",
                    "minimum": 300,
                    "maximum": 8000,
                    "description": "Approximate token budget for the stored context capsule.",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    }


def fork_plan_tool_definition() -> dict[str, Any]:
    return {
        "name": FORK_PLAN_TOOL_NAME,
        "title": "Edgebase Fork Plan",
        "description": "Create a git worktree branch for trying a plan and record resume metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Plan or hypothesis to try in the fork.",
                },
                "from_id": {
                    "type": "string",
                    "description": "Optional parent checkpoint or fork-plan id.",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional git branch name for the new worktree.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional filesystem path for the new worktree.",
                },
                "allow_dirty": {
                    "type": "boolean",
                    "description": "Allow forking from a dirty working tree.",
                },
                "budget": {
                    "type": "integer",
                    "minimum": 300,
                    "maximum": 8000,
                    "description": "Approximate token budget for the stored context capsule.",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    }


def resume_tool_definition() -> dict[str, Any]:
    return {
        "name": RESUME_TOOL_NAME,
        "title": "Edgebase Resume",
        "description": "Render the latest or selected context snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot_id": {
                    "type": "string",
                    "description": "Optional checkpoint or fork-plan id. Defaults to latest.",
                }
            },
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
                return self._result(
                    request_id,
                    {
                        "tools": [
                            tool_definition(),
                            goal_tool_definition(),
                            checkpoint_tool_definition(),
                            fork_plan_tool_definition(),
                            resume_tool_definition(),
                        ]
                    },
                )
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
                    graph_artifacts = safe_write_graph_artifacts(self.root, task, [], capsule.selected_files)
                    graph_summary = graph_artifact_summary(graph_artifacts)
                    text = (
                        f"{append_optional_section(capsule.markdown, graph_summary)}\n\n"
                        "Use this Edgebase context as the first read set before broad exploration or edits."
                    )
                    description = "Edgebase source-backed context capsule."
                elif name == "goal":
                    goal = str(args.get("goal") or args.get("task") or "").strip()
                    if not goal:
                        return self._error(request_id, -32602, "`goal` is required")
                    capsule = build_goal_capsule(self.root, goal, [], budget)
                    graph_summary = graph_artifact_summary(capsule.graph_artifacts)
                    text = (
                        f"{append_optional_section(capsule.markdown, graph_summary)}\n\n"
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
                    graph_artifacts = safe_write_graph_artifacts(
                        self.root,
                        task,
                        changed_files,
                        capsule.selected_files,
                    )
                    graph_summary = graph_artifact_summary(graph_artifacts)
                    return self._result(
                        request_id,
                        {
                            "content": [
                                {"type": "text", "text": append_optional_section(capsule.markdown, graph_summary)}
                            ],
                            "structuredContent": {
                                "selected_files": list(capsule.selected_files),
                                "token_estimate": capsule.token_estimate,
                                "stale_files": list(capsule.stale_files),
                                "graph_artifacts": graph_artifacts,
                            },
                        },
                    )
                if name == GOAL_TOOL_NAME:
                    goal = str(args.get("goal") or args.get("task") or "").strip()
                    if not goal:
                        return self._error(request_id, -32602, "`goal` is required")
                    capsule = build_goal_capsule(self.root, goal, changed_files, budget)
                    structured = capsule.contract.to_dict()
                    structured["graph_artifacts"] = capsule.graph_artifacts
                    graph_summary = graph_artifact_summary(capsule.graph_artifacts)
                    return self._result(
                        request_id,
                        {
                            "content": [
                                {"type": "text", "text": append_optional_section(capsule.markdown, graph_summary)}
                            ],
                            "structuredContent": structured,
                        },
                    )
                if name == CHECKPOINT_TOOL_NAME:
                    message = str(args.get("message") or "").strip()
                    if not message:
                        return self._error(request_id, -32602, "`message` is required")
                    snapshot = create_checkpoint(self.root, message, budget)
                    return self._result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": render_resume(snapshot)}],
                            "structuredContent": snapshot.to_dict(),
                        },
                    )
                if name == FORK_PLAN_TOOL_NAME:
                    message = str(args.get("message") or "").strip()
                    if not message:
                        return self._error(request_id, -32602, "`message` is required")
                    snapshot = create_fork_plan(
                        self.root,
                        message,
                        budget,
                        from_id=str(args.get("from_id") or ""),
                        branch=str(args.get("branch") or ""),
                        path=str(args.get("path") or ""),
                        allow_dirty=bool(args.get("allow_dirty") or False),
                    )
                    return self._result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": render_resume(snapshot)}],
                            "structuredContent": snapshot.to_dict(),
                        },
                    )
                if name == RESUME_TOOL_NAME:
                    snapshot = resume_snapshot(self.root, str(args.get("snapshot_id") or ""))
                    return self._result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": render_resume(snapshot)}],
                            "structuredContent": snapshot.to_dict(),
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


def append_optional_section(text: str, section: str) -> str:
    return text + ("\n\n" + section if section else "")


def safe_write_graph_artifacts(
    root: str | Path,
    task: str,
    changed_files: list[str],
    selected_files: tuple[str, ...],
) -> dict[str, str]:
    try:
        return write_graph_artifacts(
            root,
            task=task,
            changed_files=changed_files,
            selected_files=selected_files,
        )
    except Exception:
        return {}


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
