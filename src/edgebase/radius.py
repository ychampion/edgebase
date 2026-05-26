from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .context import estimate_tokens, rank_files, stale_files, tokenize
from .git import changed_files as git_changed_files
from .git import find_repo_root
from .indexer import index_repo
from .store import Store


ROUTE_PARTS = {"api", "apis", "controller", "controllers", "route", "routes", "router", "routers"}
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs"}
MIGRATION_PARTS = {"migration", "migrations", "schema", "schemas"}
DOWNSTREAM_HINTS = {"notification", "notifications", "invoice", "invoices", "email", "emails", "webhook", "webhooks"}
PERSISTENCE_HINTS = {
    "account",
    "auth",
    "billing",
    "customer",
    "db",
    "invoice",
    "ledger",
    "model",
    "order",
    "payment",
    "plan",
    "schema",
    "subscription",
    "user",
}
PAYMENT_HINTS = {
    "billing",
    "checkout",
    "invoice",
    "invoices",
    "paypal",
    "payment",
    "payments",
    "provider",
    "stripe",
    "subscription",
    "subscriptions",
}


@dataclass(frozen=True)
class RadiusFinding:
    category: str
    path: str
    reason: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ChangeRadius:
    target_files: tuple[str, ...]
    findings: tuple[RadiusFinding, ...]
    risks: tuple[str, ...]
    stale_files: tuple[str, ...]
    markdown: str
    token_estimate: int

    def to_dict(self) -> dict[str, object]:
        return {
            "target_files": list(self.target_files),
            "findings": [finding.to_dict() for finding in self.findings],
            "risks": list(self.risks),
            "stale_files": list(self.stale_files),
            "markdown": self.markdown,
            "token_estimate": self.token_estimate,
        }


def build_change_radius(
    root: str | Path,
    targets: list[str] | None = None,
    goal: str = "",
    changed_files: list[str] | None = None,
    budget: int = 1200,
    auto_index: bool = True,
) -> ChangeRadius:
    repo_root = find_repo_root(root)
    store = Store(repo_root)
    if auto_index and not store.exists():
        index_repo(repo_root)

    graph = store.load_graph()
    if not graph["files"] and auto_index:
        index_repo(repo_root)
        graph = store.load_graph()

    file_paths = {str(row["path"]) for row in graph["files"]}
    explicit_targets, extra_goal = resolve_targets(repo_root, graph, targets or [], changed_files or [])
    full_goal = " ".join(part for part in [goal.strip(), extra_goal.strip()] if part).strip()
    if not explicit_targets:
        explicit_targets = infer_targets_from_goal(graph, full_goal, changed_files or [], budget)

    target_files = tuple(sorted(dict.fromkeys(path for path in explicit_targets if path in file_paths or (repo_root / path).exists())))
    stale = tuple(stale_files(repo_root, graph["files"]))
    findings = tuple(select_findings(collect_findings(repo_root, graph, target_files, full_goal), budget))
    risks = tuple(detect_risks(repo_root, graph, target_files, full_goal, findings))
    markdown = render_change_radius(repo_root, target_files, findings, risks, stale, full_goal)
    return ChangeRadius(target_files, findings, risks, stale, markdown, estimate_tokens(markdown))


def resolve_targets(
    repo_root: Path,
    graph: dict[str, list[object]],
    targets: list[str],
    changed: list[str],
) -> tuple[list[str], str]:
    file_paths = {str(row["path"]) for row in graph["files"]}
    resolved: list[str] = []
    goal_parts: list[str] = []
    for raw in [*targets, *changed]:
        item = raw.strip()
        if not item:
            continue
        rel = normalize_path(repo_root, item)
        if rel in file_paths or (repo_root / rel).exists():
            resolved.append(rel)
        else:
            goal_parts.append(item)
    if not resolved and not goal_parts:
        resolved.extend(path for path in git_changed_files(repo_root) if path in file_paths or (repo_root / path).exists())
    return sorted(dict.fromkeys(resolved)), " ".join(goal_parts)


def normalize_path(repo_root: Path, raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            return path.name
    rel = path.as_posix()
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def infer_targets_from_goal(
    graph: dict[str, list[object]], goal: str, changed_files: list[str], budget: int
) -> list[str]:
    tokens = tokenize(goal) | {Path(path).stem.lower() for path in changed_files}
    candidates = rank_files(graph, tokens, changed_files)
    return [candidate.path for candidate in candidates[: max(1, min(3, budget // 400))]]


def collect_findings(
    repo_root: Path,
    graph: dict[str, list[object]],
    target_files: tuple[str, ...],
    goal: str,
) -> list[RadiusFinding]:
    if not target_files:
        return []
    target_set = set(target_files)
    file_rows = {str(row["path"]): row for row in graph["files"]}
    target_modules = {str(file_rows[path]["module"]) for path in target_files if path in file_rows}
    target_modules.update(path_to_import_keys(path) for path in target_files)
    target_symbols = {
        str(symbol["name"])
        for symbol in graph["symbols"]
        if str(symbol["file_path"]) in target_set and symbol["exported"]
    }
    target_tokens = target_domain_tokens(target_files, goal)

    findings: list[RadiusFinding] = []
    for edge in graph["edges"]:
        edge_file = str(edge["file_path"])
        rel = str(edge["rel"])
        dst_key = str(edge["dst_key"])
        if edge_file in target_set:
            continue
        if rel == "TESTS" and dst_key in target_set:
            findings.append(
                RadiusFinding(
                    "tests",
                    edge_file,
                    f"tests `{dst_key}`",
                    float(edge["confidence"]),
                    str(edge["extractor"]),
                )
            )
            continue
        if rel == "IMPORTS" and import_points_to_target(edge_file, dst_key, target_files, target_modules):
            findings.append(
                RadiusFinding(
                    classify_path(edge_file),
                    edge_file,
                    f"imports `{dst_key}`",
                    min(0.9, float(edge["confidence"])),
                    str(edge["extractor"]),
                )
            )
            continue
        if rel == "CALLS" and dst_key in target_symbols:
            findings.append(
                RadiusFinding(
                    classify_path(edge_file),
                    edge_file,
                    f"calls exported symbol `{dst_key}`",
                    min(0.55, float(edge["confidence"])),
                    str(edge["extractor"]),
                )
            )

    for row in graph["files"]:
        path = str(row["path"])
        if path in target_set:
            continue
        parts = path_parts(path)
        if not (parts & TEST_PARTS or parts & ROUTE_PARTS):
            continue
        overlap = target_tokens & set(tokenize(path.replace("/", " ")))
        if not overlap:
            continue
        findings.append(
            RadiusFinding(
                "tests" if parts & TEST_PARTS else "API route",
                path,
                "path/domain overlap " + ", ".join(sorted(overlap)[:3]),
                0.35,
                "path.heuristic",
            )
        )

    migration = migration_path(repo_root, graph)
    if migration and (target_tokens & PERSISTENCE_HINTS):
        findings.append(
            RadiusFinding(
                "DB migration path",
                migration,
                "domain suggests persisted state; inspect only if schema or data shape changes",
                0.35,
                "path.heuristic",
            )
        )
    return findings


def path_to_import_keys(path: str) -> str:
    p = Path(path)
    without_suffix = p.with_suffix("").as_posix()
    return without_suffix


def import_points_to_target(
    importer_path: str,
    dst_key: str,
    target_files: tuple[str, ...],
    target_modules: set[str],
) -> bool:
    if dst_key in target_modules:
        return True
    if dst_key.startswith("."):
        base = Path(importer_path).parent
        normalized = (base / dst_key).as_posix()
        normalized = normalize_import_path(normalized)
        for target in target_files:
            if normalized == Path(target).with_suffix("").as_posix():
                return True
        return False
    normalized_dst = normalize_import_path(dst_key)
    for target in target_files:
        target_no_suffix = Path(target).with_suffix("").as_posix()
        if normalized_dst == target_no_suffix or normalized_dst.endswith("/" + target_no_suffix):
            return True
        if normalized_dst == Path(target).stem:
            return True
    return False


def normalize_import_path(value: str) -> str:
    parts: list[str] = []
    for part in value.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts).removesuffix("/index")


def classify_path(path: str) -> str:
    parts = path_parts(path)
    if parts & TEST_PARTS:
        return "tests"
    if parts & ROUTE_PARTS:
        return "API route"
    if parts & MIGRATION_PARTS:
        return "DB migration path"
    if parts & DOWNSTREAM_HINTS:
        return "downstream module"
    return "downstream module"


def path_parts(path: str) -> set[str]:
    pieces = set()
    for part in Path(path).parts:
        lower = part.lower()
        pieces.add(lower)
        pieces.update(tokenize(lower.replace(".", " ").replace("-", " ").replace("_", " ")))
    return pieces


def target_domain_tokens(target_files: tuple[str, ...], goal: str) -> set[str]:
    text = " ".join([*target_files, goal]).replace("/", " ").replace("-", " ").replace("_", " ")
    return tokenize(text)


def migration_path(repo_root: Path, graph: dict[str, list[object]]) -> str:
    indexed = sorted({str(row["path"]).split("/", 1)[0] for row in graph["files"] if str(row["path"]).startswith("migrations/")})
    if indexed:
        return "migrations/*"
    for name in ("migrations", "migration", "db/migrations", "database/migrations", "prisma/migrations"):
        if (repo_root / name).exists():
            return name.rstrip("/") + "/*"
    return ""


def select_findings(findings: list[RadiusFinding], budget: int) -> list[RadiusFinding]:
    dedup: dict[tuple[str, str], RadiusFinding] = {}
    for finding in findings:
        key = (finding.category, finding.path)
        current = dedup.get(key)
        if current is None or finding.confidence > current.confidence:
            dedup[key] = finding
    order = {"API route": 0, "DB migration path": 1, "tests": 2, "downstream module": 3}
    limit = max(5, min(16, budget // 90))
    return sorted(
        dedup.values(),
        key=lambda item: (order.get(item.category, 9), -item.confidence, item.path),
    )[:limit]


def detect_risks(
    repo_root: Path,
    graph: dict[str, list[object]],
    target_files: tuple[str, ...],
    goal: str,
    findings: tuple[RadiusFinding, ...] | list[RadiusFinding],
) -> list[str]:
    risk_tokens = target_domain_tokens(target_files, goal)
    for edge in graph["edges"]:
        if str(edge["file_path"]) in set(target_files):
            risk_tokens.update(tokenize(str(edge["dst_key"]).replace(".", " ")))
    risks: list[str] = []
    if risk_tokens & PAYMENT_HINTS:
        risks.append("payment provider side effects")
    if any(f.category == "DB migration path" for f in findings):
        risks.append("database schema or historical data shape changes")
    if any("notification" in f.path.lower() or "invoice" in f.path.lower() for f in findings):
        risks.append("customer notification or invoice side effects")
    if has_generated_paths(repo_root):
        risks.append("generated files may need regeneration rather than manual edits")
    return list(dict.fromkeys(risks))


def has_generated_paths(repo_root: Path) -> bool:
    for name in ("generated", "__generated__", "gen"):
        if (repo_root / name).exists():
            return True
    return False


def render_change_radius(
    repo_root: Path,
    target_files: tuple[str, ...],
    findings: tuple[RadiusFinding, ...],
    risks: tuple[str, ...],
    stale: tuple[str, ...],
    goal: str,
) -> str:
    lines: list[str] = ["# Edgebase Change Blast Radius", ""]
    if goal:
        lines.append(f"Plan/goal: {goal}")
    lines.append(f"Repo: {repo_root}")
    lines.append("")
    if not target_files:
        lines.append("No concrete target file was identified. Provide a file path or run after a plan names files.")
        return "\n".join(lines)
    if len(target_files) == 1:
        lines.append(f"Changing `{target_files[0]}` likely affects:")
    else:
        lines.append("Changing these files likely affects:")
        for path in target_files[:8]:
            lines.append(f"- target: `{path}`")
        lines.append("")

    if findings:
        for finding in findings:
            lines.append(
                f"- {finding.category}: `{finding.path}` "
                f"({finding.reason}; confidence={finding.confidence:.2f})"
            )
    else:
        lines.append("- No source-backed downstream files found yet.")
    for risk in risks:
        lines.append(f"- risk: {risk}")
    if stale:
        lines.append("")
        lines.append("Freshness warning:")
        for path in stale[:8]:
            lines.append(f"- stale: `{path}`")
    lines.append("")
    lines.append(
        "Advisory: this is an impact map, not an edit requirement. Inspect these areas when the proposed change touches their behavior; leave them alone when unaffected."
    )
    lines.append("Machine summary:")
    lines.append(
        json.dumps(
            {
                "target_files": list(target_files),
                "findings": [finding.to_dict() for finding in findings],
                "risks": list(risks),
                "stale_files": list(stale),
            },
            sort_keys=True,
        )
    )
    return "\n".join(lines)


def render_radius_section(radius: ChangeRadius) -> str:
    if not radius.target_files:
        return ""
    lines = ["Change blast radius (advisory):"]
    for finding in radius.findings[:8]:
        lines.append(
            f"- {finding.category}: `{finding.path}` "
            f"({finding.reason}; confidence={finding.confidence:.2f})"
        )
    for risk in radius.risks[:4]:
        lines.append(f"- risk: {risk}")
    if len(lines) == 1:
        lines.append("- No source-backed downstream files found yet.")
    lines.append(
        "Note: inspect affected areas when behavior reaches them; this does not require editing every listed path."
    )
    return "\n".join(lines)
