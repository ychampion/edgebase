from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .context import build_context
from .git import find_repo_root
from .indexer import index_repo
from .store import Store


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    language: str
    loc: int
    is_test: bool
    owner: str
    churn: int


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    rel: str
    line: int
    extractor: str
    confidence: float


@dataclass(frozen=True)
class GraphExport:
    root: str
    scope: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    omitted_nodes: int


def build_graph_export(
    root: str | Path,
    task: str | None = None,
    changed_files: list[str] | None = None,
    selected_files: Iterable[str] | None = None,
    max_nodes: int = 120,
) -> GraphExport:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    if selected_files is not None:
        included_paths = set(selected_files)
        scope = "task" if task else "selected"
        if not store.exists():
            index_repo(repo_root)
    elif task:
        capsule = build_context(repo_root, task, changed_files or [], budget=1200)
        included_paths = set(capsule.selected_files)
        scope = "task"
    else:
        if not store.exists():
            index_repo(repo_root)
        included_paths = None
        scope = "repository"

    graph = store.load_graph()
    file_rows = graph["files"]
    metrics_by_file = {str(row["file_path"]): row for row in graph["metrics"]}
    module_to_file = {str(row["module"]): str(row["path"]) for row in file_rows}
    symbol_name_to_files = symbol_index(graph["symbols"])

    paths = [str(row["path"]) for row in file_rows if included_paths is None or str(row["path"]) in included_paths]
    paths = sorted(paths)[: max(1, max_nodes)]
    path_set = set(paths)

    nodes = tuple(node_from_file(row, metrics_by_file) for row in file_rows if str(row["path"]) in path_set)
    edges = tuple(
        edge
        for edge in file_edges(graph["edges"], module_to_file, symbol_name_to_files, path_set)
        if edge.source in path_set and edge.target in path_set
    )
    omitted = max(0, len(file_rows) - len(paths)) if included_paths is None else max(0, len(included_paths) - len(paths))
    return GraphExport(str(repo_root), scope, nodes, edges, omitted)


def symbol_index(symbols: Iterable[object]) -> dict[str, set[str]]:
    by_name: dict[str, set[str]] = {}
    for symbol in symbols:
        name = str(symbol["name"])
        by_name.setdefault(name, set()).add(str(symbol["file_path"]))
    return by_name


def node_from_file(row: object, metrics_by_file: dict[str, object]) -> GraphNode:
    path = str(row["path"])
    metrics = metrics_by_file.get(path)
    owner = str(metrics["owner"]) if metrics and metrics["owner"] else ""
    churn = int(metrics["churn_count"]) if metrics else 0
    return GraphNode(
        id=path,
        label=Path(path).name,
        language=str(row["language"]),
        loc=int(row["loc"]),
        is_test=bool(row["is_test"]),
        owner=owner,
        churn=churn,
    )


def file_edges(
    edge_rows: Iterable[object],
    module_to_file: dict[str, str],
    symbol_name_to_files: dict[str, set[str]],
    path_set: set[str],
) -> list[GraphEdge]:
    seen: set[tuple[str, str, str, int]] = set()
    edges: list[GraphEdge] = []
    for row in edge_rows:
        source = str(row["file_path"])
        target = resolve_edge_target(row, module_to_file, symbol_name_to_files)
        if not target or source == target or source not in path_set or target not in path_set:
            continue
        key = (source, target, str(row["rel"]), int(row["line"]))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                source=source,
                target=target,
                rel=str(row["rel"]),
                line=int(row["line"]),
                extractor=str(row["extractor"]),
                confidence=float(row["confidence"]),
            )
        )
    return edges


def resolve_edge_target(
    row: object,
    module_to_file: dict[str, str],
    symbol_name_to_files: dict[str, set[str]],
) -> str:
    rel = str(row["rel"])
    dst_type = str(row["dst_type"])
    dst_key = str(row["dst_key"])
    if dst_type == "file":
        return dst_key
    if rel == "IMPORTS" and dst_type == "module":
        return module_to_file.get(dst_key) or module_to_file.get(dst_key.lstrip(".") or dst_key, "")
    if rel == "CALLS" and dst_type == "symbol_name":
        name = dst_key.rsplit(".", 1)[-1]
        matches = symbol_name_to_files.get(name, set())
        return next(iter(matches)) if len(matches) == 1 else ""
    return ""


def render_json(export: GraphExport) -> str:
    return json.dumps(asdict(export), indent=2, sort_keys=True)


def render_dot(export: GraphExport) -> str:
    lines = ["digraph edgebase {", '  graph [rankdir="LR"];', '  node [shape=box, style="rounded"];']
    for node in export.nodes:
        label = f"{node.label}\\n{node.language}"
        lines.append(f'  "{dot_escape(node.id)}" [label="{dot_escape(label)}"];')
    for edge in export.edges:
        label = f"{edge.rel} {edge.confidence:.2f}"
        lines.append(
            f'  "{dot_escape(edge.source)}" -> "{dot_escape(edge.target)}" '
            f'[label="{dot_escape(label)}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_html(export: GraphExport) -> str:
    escaped_data = (
        json.dumps(asdict(export), sort_keys=True)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Edgebase Graph</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f8fa;
  --text: #1f2933;
  --muted: #5f6b7a;
  --line: #c9d2dc;
  --accent: #126d6a;
  --test: #8f5c00;
  --panel: #ffffff;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
header {{
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}}
h1 {{ margin: 0 0 6px; font-size: 22px; }}
.meta {{ color: var(--muted); display: flex; gap: 16px; flex-wrap: wrap; }}
main {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  min-height: calc(100vh - 82px);
}}
svg {{ width: 100%; height: calc(100vh - 82px); display: block; }}
aside {{
  border-left: 1px solid var(--line);
  background: var(--panel);
  padding: 16px;
  overflow: auto;
}}
.node circle {{ fill: var(--accent); stroke: #ffffff; stroke-width: 2; }}
.node.test circle {{ fill: var(--test); }}
.node text {{ font-size: 12px; fill: var(--text); paint-order: stroke; stroke: #fff; stroke-width: 3px; }}
.edge {{ stroke: #748294; stroke-width: 1.4; marker-end: url(#arrow); }}
.edge-label {{ font-size: 11px; fill: var(--muted); }}
.list {{ margin: 16px 0 0; padding: 0; list-style: none; }}
.list li {{ padding: 8px 0; border-top: 1px solid #e4e8ed; }}
.path {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; word-break: break-word; }}
.badge {{ color: var(--muted); font-size: 12px; }}
@media (max-width: 820px) {{
  main {{ grid-template-columns: 1fr; }}
  svg {{ height: 62vh; }}
  aside {{ border-left: 0; border-top: 1px solid var(--line); }}
}}
</style>
</head>
<body>
<header>
  <h1>Edgebase Graph</h1>
  <div class="meta" id="meta"></div>
</header>
<main>
  <svg id="graph" role="img" aria-label="Edgebase file relationship graph"></svg>
  <aside>
    <strong>Files</strong>
    <ul class="list" id="files"></ul>
  </aside>
</main>
<script id="edgebase-data" type="application/json">{escaped_data}</script>
<script>
const data = JSON.parse(document.getElementById("edgebase-data").textContent);
const svg = document.getElementById("graph");
const files = document.getElementById("files");
document.getElementById("meta").textContent =
  `${{data.scope}} scope | ${{data.nodes.length}} files | ${{data.edges.length}} relationships` +
  (data.omitted_nodes ? ` | ${{data.omitted_nodes}} omitted by cap` : "");

const width = 1000;
const height = 700;
svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
const svgParts = [
  `<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#748294"></path></marker></defs>`
];

const centerX = width / 2;
const centerY = height / 2;
const radius = Math.max(120, Math.min(width, height) / 2 - 90);
const positions = new Map();
data.nodes.forEach((node, index) => {{
  const angle = (Math.PI * 2 * index) / Math.max(1, data.nodes.length) - Math.PI / 2;
  positions.set(node.id, {{
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius
  }});
}});

for (const edge of data.edges) {{
  const from = positions.get(edge.source);
  const to = positions.get(edge.target);
  if (!from || !to) continue;
  svgParts.push(`<line class="edge" x1="${{from.x}}" y1="${{from.y}}" x2="${{to.x}}" y2="${{to.y}}"></line>`);
  svgParts.push(
    `<text class="edge-label" x="${{(from.x + to.x) / 2}}" y="${{(from.y + to.y) / 2 - 4}}">${{escapeText(edge.rel)}}</text>`
  );
}}

for (const node of data.nodes) {{
  const pos = positions.get(node.id);
  svgParts.push(
    `<g class="node${{node.is_test ? " test" : ""}}"><circle cx="${{pos.x}}" cy="${{pos.y}}" r="16"></circle>` +
    `<text x="${{pos.x + 22}}" y="${{pos.y + 4}}">${{escapeText(node.label)}}</text></g>`
  );

  const item = document.createElement("li");
  item.innerHTML = `<div class="path"></div><div class="badge"></div>`;
  item.querySelector(".path").textContent = node.id;
  item.querySelector(".badge").textContent = `${{node.language}} | ${{node.loc}} loc | churn ${{node.churn}}`;
  files.appendChild(item);
}}
svg.innerHTML = svgParts.join("");

function escapeText(value) {{
  return String(value).replace(/[&<>"']/g, (char) => ({{
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }}[char]));
}}
</script>
</body>
</html>
"""


def graph_dir(root: str | Path) -> Path:
    return find_repo_root(root) / ".edgebase" / "graphs"


def write_graph_artifacts(
    root: str | Path,
    task: str | None = None,
    changed_files: list[str] | None = None,
    selected_files: Iterable[str] | None = None,
    max_nodes: int = 120,
) -> dict[str, str]:
    repo_root = find_repo_root(root)
    export = build_graph_export(
        repo_root,
        task=task,
        changed_files=changed_files,
        selected_files=selected_files,
        max_nodes=max_nodes,
    )
    directory = graph_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "html": directory / "latest.html",
        "json": directory / "latest.json",
        "dot": directory / "latest.dot",
    }
    rendered = {
        "html": render_html(export),
        "json": render_json(export),
        "dot": render_dot(export),
    }
    for format_name, path in artifacts.items():
        write_text_atomic(path, rendered[format_name] + "\n")
    return {format_name: str(path) for format_name, path in artifacts.items()}


def graph_artifact_summary(artifacts: Mapping[str, str]) -> str:
    paths = {name: path for name, path in artifacts.items() if path}
    if not paths:
        return ""
    lines = ["Edgebase graph artifacts:"]
    for format_name in ("html", "json", "dot"):
        path = paths.get(format_name)
        if path:
            lines.append(f"- {format_name}: {path}")
    return "\n".join(lines)


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
