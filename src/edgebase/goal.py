from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from .context import estimate_tokens, rank_files, select_files, stale_files, tokenize
from .git import changed_files as git_changed_files
from .git import current_commit, file_sha, find_repo_root
from .indexer import index_repo
from .store import Store


@dataclass(frozen=True)
class WorkContract:
    goal: str
    repo_commit: str
    worktree_fingerprint: str
    selected_files: list[str]
    must_read: list[str]
    must_not_touch: list[str]
    blast_radius: list[str]
    test_plan: list[str]
    acceptance_criteria: list[str]
    risk_flags: list[str]
    uncertainties: list[str]
    provenance: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GoalCapsule:
    markdown: str
    contract: WorkContract
    token_estimate: int


@dataclass(frozen=True)
class PatchPassport:
    markdown: str
    goal: str
    files_changed: list[str]
    tests_run: list[str]
    required_checks: list[str]


def build_goal_capsule(
    root: str | Path,
    goal: str,
    changed_files: list[str] | None = None,
    budget: int = 1200,
    auto_index: bool = True,
) -> GoalCapsule:
    repo_root = find_repo_root(root)
    contract = build_work_contract(repo_root, goal, changed_files, budget, auto_index)
    markdown = render_goal_capsule(contract)
    return GoalCapsule(markdown, contract, estimate_tokens(markdown))


def build_work_contract(
    root: str | Path,
    goal: str,
    changed_files: list[str] | None = None,
    budget: int = 1200,
    auto_index: bool = True,
) -> WorkContract:
    repo_root = find_repo_root(root)
    normalized_goal = " ".join(goal.split()).strip()
    store = Store(repo_root)
    if auto_index and not store.exists():
        index_repo(repo_root)

    graph = store.load_graph()
    if not graph["files"] and auto_index:
        index_repo(repo_root)
        graph = store.load_graph()

    changed = sorted(set(changed_files or []) | set(git_changed_files(repo_root)))
    tokens = tokenize(normalized_goal) | {Path(path).stem.lower() for path in changed}
    candidates = select_files(rank_files(graph, tokens, changed), graph, budget)
    selected = [candidate.path for candidate in candidates]
    tests = inferred_test_paths(graph, selected)
    blast_radius = unique_preserving_order([*selected, *tests])
    must_read = selected[:5]
    required_checks = required_checks_for_tests(tests)
    stale = stale_files(repo_root, graph["files"])

    risk_flags: list[str] = []
    if stale:
        risk_flags.append("Index has stale files; refresh with `edgebase index --changed` before relying on the contract.")
    if not selected:
        risk_flags.append("No high-signal files were selected from the graph.")
    risk_flags.append("Do not change schema or provider configuration until a must-read file proves it is necessary.")

    uncertainties: list[str] = []
    if selected:
        uncertainties.append("Selected files are graph-ranked leads; read them before treating the hypothesis as fact.")
    else:
        uncertainties.append("No source-backed implementation entrypoint is known yet.")
    if not tests:
        uncertainties.append("No inferred focused test file was found for this goal.")

    return WorkContract(
        goal=normalized_goal,
        repo_commit=current_commit(repo_root),
        worktree_fingerprint=worktree_fingerprint(repo_root, changed),
        selected_files=selected,
        must_read=must_read,
        must_not_touch=["migrations/*", "provider configs"],
        blast_radius=blast_radius,
        test_plan=required_checks,
        acceptance_criteria=[
            "Implementation satisfies the stated goal with the smallest justified change set.",
            "Existing behavior near the blast radius has regression evidence.",
            "Final handoff includes changed files, rationale, tests run, and unresolved assumptions.",
        ],
        risk_flags=risk_flags,
        uncertainties=uncertainties,
        provenance=contract_provenance(candidates, graph),
    )


def build_patch_passport(
    root: str | Path,
    goal: str,
    tests: list[str] | None = None,
    changed_files: list[str] | None = None,
    budget: int = 1200,
) -> PatchPassport:
    repo_root = find_repo_root(root)
    files_changed = sorted(set(changed_files or []) | set(git_changed_files(repo_root)))
    contract = build_work_contract(repo_root, goal, files_changed, budget, auto_index=True)
    tests_run = [test.strip() for test in tests or [] if test.strip()]
    markdown = render_patch_passport(contract, files_changed, tests_run)
    return PatchPassport(markdown, contract.goal, files_changed, tests_run, contract.test_plan)


def render_goal_capsule(contract: WorkContract) -> str:
    lines: list[str] = ["# Edgebase Goal Capsule", ""]
    lines.extend(["Goal:", contract.goal or "No goal supplied.", ""])
    lines.extend(["Current hypothesis:", current_hypothesis(contract), ""])
    lines.append("Blast radius:")
    append_bullets(lines, contract.blast_radius, empty="- No blast radius selected yet.")
    lines.append("")
    lines.append("Read first:")
    append_numbered(lines, contract.must_read, empty="1. No must-read files selected yet.")
    lines.append("")
    lines.append("Do not edit yet:")
    append_bullets(lines, contract.must_not_touch, empty="- No protected paths identified.")
    lines.append("Reason: no schema or provider-configuration change is proven necessary by the current graph evidence.")
    lines.append("")
    lines.append("Likely implementation path:")
    path_steps = [
        "Read the must-read files and confirm or revise the hypothesis.",
        "Make the smallest implementation inside the blast radius.",
        "Preserve existing behavior in related files before adding new behavior.",
        "Add or update focused tests, then run the required checks.",
    ]
    append_numbered(lines, path_steps)
    lines.append("")
    lines.append("Required checks:")
    append_bullets(lines, contract.test_plan, empty="- No focused check inferred; run the relevant project test suite.")
    lines.append("")
    lines.append("Known uncertainty:")
    append_bullets(lines, contract.uncertainties, empty="- No uncertainty recorded.")
    lines.append("")
    lines.append("Patch contract:")
    lines.append("The final PR must include:")
    append_bullets(
        lines,
        [
            "changed files",
            "rationale",
            "tests run",
            "regression evidence for existing behavior",
            "unresolved assumptions",
        ],
    )
    return "\n".join(lines)


def render_work_contract(contract: WorkContract) -> str:
    lines = ["# Edgebase Work Contract", ""]
    lines.append(f"Goal: {contract.goal or 'No goal supplied.'}")
    lines.append(f"Repo commit: {contract.repo_commit}")
    lines.append(f"Worktree fingerprint: {contract.worktree_fingerprint}")
    lines.append("")
    lines.append("Must read:")
    append_bullets(lines, contract.must_read, empty="- No must-read files selected yet.")
    lines.append("")
    lines.append("Blast radius:")
    append_bullets(lines, contract.blast_radius, empty="- No blast radius selected yet.")
    lines.append("")
    lines.append("Must not touch:")
    append_bullets(lines, contract.must_not_touch, empty="- No protected paths identified.")
    lines.append("")
    lines.append("Required checks:")
    append_bullets(lines, contract.test_plan, empty="- No focused check inferred.")
    lines.append("")
    lines.append("Risk flags:")
    append_bullets(lines, contract.risk_flags, empty="- No risk flags recorded.")
    return "\n".join(lines)


def render_edit_delta(
    root: str | Path,
    goal: str,
    touched: list[str],
    budget: int = 700,
) -> str:
    contract = build_work_contract(root, goal, touched, budget, auto_index=False)
    elevated_tests = [item for item in contract.test_plan if any(path in item for path in touched) or item.startswith("pytest")]
    unverified = [path for path in contract.blast_radius if path not in touched][:5]
    lines = ["# Edgebase Edit Delta", ""]
    lines.append("Changed files:")
    append_bullets(lines, touched, empty="- No edited file path found.")
    lines.append("")
    lines.append("New impact:")
    append_bullets(lines, contract.blast_radius, empty="- No graph impact selected.")
    lines.append("")
    lines.append("Higher-priority checks:")
    append_bullets(lines, elevated_tests or contract.test_plan, empty="- No focused check inferred.")
    lines.append("")
    lines.append("Still unverified:")
    append_bullets(lines, unverified, empty="- No additional related file selected.")
    lines.append("")
    lines.append("Before finalizing:")
    lines.append("- Run focused checks for touched behavior and any related regression checks.")
    return "\n".join(lines)


def render_patch_passport(contract: WorkContract, files_changed: list[str], tests_run: list[str]) -> str:
    lines: list[str] = ["# Patch Passport", ""]
    lines.extend(["Goal:", contract.goal or "No goal supplied.", ""])
    lines.append("Files changed:")
    append_bullets(lines, files_changed, empty="- No changed files detected.")
    lines.append("")
    lines.append("Evidence used:")
    evidence = contract.provenance[:8] or contract.must_read
    append_bullets(lines, evidence, empty="- No source-backed evidence recorded.")
    lines.append("")
    lines.append("Tests run:")
    if tests_run:
        for test in tests_run:
            lines.append(f"- {format_test_evidence(test)}")
    else:
        lines.append("- No tests recorded by Edgebase.")
        lines.append("Required checks not recorded:")
        append_bullets(lines, contract.test_plan, empty="- No focused check inferred.")
    lines.append("")
    lines.append("Risk:")
    risks = list(contract.risk_flags)
    if not tests_run:
        risks.append("Required checks are unrecorded; do not mark them as passing without explicit evidence.")
    append_bullets(lines, risks, empty="- No risk flags recorded.")
    lines.append("")
    lines.append("Review focus:")
    append_bullets(lines, review_focus(contract), empty="- Review the changed behavior and related regressions.")
    return "\n".join(lines)


def current_hypothesis(contract: WorkContract) -> str:
    if not contract.must_read:
        return "No high-confidence implementation entrypoint has been identified yet."
    primary = contract.must_read[0]
    related = ", ".join(contract.must_read[1:3])
    if related:
        return f"Edgebase ranks `{primary}` as the strongest lead, with related context in {related}."
    return f"Edgebase ranks `{primary}` as the strongest current implementation lead."


def inferred_test_paths(graph: dict[str, list[object]], selected: list[str]) -> list[str]:
    selected_set = set(selected)
    tests: list[str] = [path for path in selected if is_test_path(path)]
    for edge in graph["edges"]:
        if edge["rel"] != "TESTS":
            continue
        test_path = str(edge["file_path"])
        target = str(edge["dst_key"])
        if not is_test_path(test_path):
            continue
        if target in selected_set or test_path in selected_set:
            tests.append(test_path)
    return unique_preserving_order(tests)


def required_checks_for_tests(tests: list[str]) -> list[str]:
    if not tests:
        return []
    checks: list[str] = []
    for path in tests[:6]:
        if path.endswith(".py"):
            checks.append(f"pytest {path}")
        else:
            checks.append(f"Run focused test for {path}")
    return checks


def contract_provenance(candidates: list[object], graph: dict[str, list[object]]) -> list[str]:
    symbol_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    for symbol in graph["symbols"]:
        path = str(symbol["file_path"])
        symbol_counts[path] = symbol_counts.get(path, 0) + 1
    for edge in graph["edges"]:
        path = str(edge["file_path"])
        edge_counts[path] = edge_counts.get(path, 0) + 1
    provenance: list[str] = []
    for candidate in candidates[:8]:
        reasons = "; ".join(candidate.reasons) if candidate.reasons else "ranked by graph"
        provenance.append(
            f"{candidate.path}: score={candidate.score:.1f}; {reasons}; "
            f"symbols={symbol_counts.get(candidate.path, 0)}; edges={edge_counts.get(candidate.path, 0)}"
        )
    return provenance


def worktree_fingerprint(repo_root: Path, changed: list[str] | None = None) -> str:
    paths = sorted(set(changed or git_changed_files(repo_root)))
    parts = [current_commit(repo_root)]
    for path in paths:
        full = repo_root / path
        if full.exists() and full.is_file():
            try:
                digest = file_sha(full)
            except OSError:
                digest = "unreadable"
        else:
            digest = "deleted"
        parts.append(f"{path}:{digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def review_focus(contract: WorkContract) -> list[str]:
    focus = ["Regression behavior around the selected blast radius."]
    if contract.test_plan:
        focus.append("Whether required checks cover both new behavior and existing behavior.")
    if contract.must_not_touch:
        focus.append("Whether changes avoided unproven schema or provider configuration edits.")
    return focus


def format_test_evidence(test: str) -> str:
    if ":" not in test:
        return f"{test} [recorded]"
    command, status = test.rsplit(":", 1)
    return f"{command.strip()} [{status.strip()}]"


def is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    if name == "__init__.py":
        return False
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def append_bullets(lines: list[str], values: list[str], empty: str | None = None) -> None:
    if not values:
        if empty:
            lines.append(empty)
        return
    for value in values:
        lines.append(f"- {value}")


def append_numbered(lines: list[str], values: list[str], empty: str | None = None) -> None:
    if not values:
        if empty:
            lines.append(empty)
        return
    for index, value in enumerate(values, start=1):
        lines.append(f"{index}. {value}")


def unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
