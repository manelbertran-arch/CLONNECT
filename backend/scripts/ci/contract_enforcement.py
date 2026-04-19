#!/usr/bin/env python3
"""
ARC5 Phase 5 — Contract Enforcement CI Script

Detects violations of the Clonnect observability contracts:
  CHECK 1: Direct metadata assignment (metadata["x"] = ...)
  CHECK 2: prometheus_client Counter/Gauge/Histogram used without emit_metric
  CHECK 3: Metadata schema field declared but no reader exists (define-but-never-read)
  CHECK 4: Magic numbers in pipeline code (zero hardcoding principle)

Usage:
  python scripts/ci/contract_enforcement.py           # warnings only
  python scripts/ci/contract_enforcement.py --strict  # fail on CHECK 1 and CHECK 3

Design: docs/sprint5_planning/ARC5_phase5_contract_enforcement.md
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# Files/dirs excluded from CHECK 1 (direct metadata assignment)
CHECK1_EXCLUDE_DIRS = {
    "tests",
    "scripts",
    "ops",
    "migrations",
    "alembic",
    ".venv",
    "__pycache__",
    "docs",
}

# Files/dirs excluded from ALL checks
GLOBAL_EXCLUDE_DIRS = {".venv", "__pycache__", "node_modules", ".git"}

# Pipeline dirs scanned by CHECK 4 (magic numbers)
CHECK4_SCAN_DIRS = ["core/dm", "core/generation", "core/metadata", "core/observability"]

# Magic number whitelist — obvious constants that don't need extraction
MAGIC_NUMBER_WHITELIST = {
    "0", "1", "-1", "100", "1000",
    "0.0", "1.0", "-1.0", "0.5",
    "2", "3", "4", "5",  # common small counters
    "True", "False", "None",
}

# Annotation to suppress a specific line from contract enforcement
NOQA_ANNOTATION = "# noqa: contract"


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Violation:
    check: str
    file: str
    line: int
    message: str
    is_error: bool = True  # False = warning only


@dataclass
class CheckResult:
    check_name: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(v.is_error for v in self.violations)

    @property
    def has_warnings(self) -> bool:
        return any(not v.is_error for v in self.violations)


# ─────────────────────────────────────────────────────────────────────────────
# File collection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_excluded(path: Path, exclude_dirs: set[str]) -> bool:
    return any(part in exclude_dirs for part in path.parts)


def collect_python_files(
    root: Path,
    exclude_dirs: set[str] | None = None,
) -> list[Path]:
    excl = (exclude_dirs or set()) | GLOBAL_EXCLUDE_DIRS
    return [
        p for p in root.rglob("*.py")
        if not _is_excluded(p.relative_to(root), excl)
    ]


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — Direct metadata assignment
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that indicate direct metadata writes (not going through typed setter)
_DIRECT_META_PATTERNS = [
    re.compile(r'\bmetadata\s*\[\s*["\'][\w]+["\']\s*\]\s*='),   # metadata["key"] =
    re.compile(r'\bmsg\.metadata\s*\[\s*["\'][\w]+["\']\s*\]\s*='),  # msg.metadata["key"] =
    re.compile(r'\bmessage\.metadata\s*\[\s*["\'][\w]+["\']\s*\]\s*='),  # message.metadata["key"] =
    re.compile(r'\bmetadata\.update\s*\(\s*\{'),                   # metadata.update({
]


def check1_direct_metadata_assignment(root: Path) -> CheckResult:
    """Detect direct metadata["key"] = ... assignments outside of allowed locations."""
    result = CheckResult("CHECK 1: Direct metadata assignment")

    files = collect_python_files(root, exclude_dirs=CHECK1_EXCLUDE_DIRS)

    for path in files:
        lines = read_lines(path)
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if NOQA_ANNOTATION in stripped:
                continue
            for pattern in _DIRECT_META_PATTERNS:
                if pattern.search(stripped):
                    result.violations.append(Violation(
                        check="CHECK1",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Direct metadata assignment: `{stripped[:80]}`\n"
                            "  → Use write_metadata() / update_*_metadata() from core.metadata"
                        ),
                        is_error=True,
                    ))
                    break  # only one violation per line

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — prometheus_client import without emit_metric
# ─────────────────────────────────────────────────────────────────────────────

_PROMETHEUS_IMPORT_RE = re.compile(
    r'^(?:from\s+prometheus_client\s+import|import\s+prometheus_client)',
    re.MULTILINE,
)
_PROMETHEUS_METRIC_CLASS_RE = re.compile(
    r'\b(Counter|Gauge|Histogram|Summary)\s*\('
)
_EMIT_METRIC_RE = re.compile(r'\bemit_metric\s*\(')


def check2_counter_without_emit_metric(root: Path) -> CheckResult:
    """Warn when a file imports prometheus_client metric classes without using emit_metric."""
    result = CheckResult("CHECK 2: prometheus_client without emit_metric")

    files = collect_python_files(root)

    for path in files:
        rel = str(path.relative_to(root))
        # Skip core/observability/metrics.py — that's where the registry lives
        if "core/observability/metrics.py" in rel or "core\\observability\\metrics.py" in rel:
            continue

        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if not content:
            continue

        has_prometheus_import = bool(_PROMETHEUS_IMPORT_RE.search(content))
        if not has_prometheus_import:
            continue

        has_metric_instantiation = bool(_PROMETHEUS_METRIC_CLASS_RE.search(content))
        if not has_metric_instantiation:
            continue

        has_emit_metric = bool(_EMIT_METRIC_RE.search(content))
        if not has_emit_metric:
            # Find the first prometheus import line for reporting
            lines = content.splitlines()
            for lineno, line in enumerate(lines, start=1):
                if _PROMETHEUS_IMPORT_RE.match(line.strip()):
                    result.violations.append(Violation(
                        check="CHECK2",
                        file=rel,
                        line=lineno,
                        message=(
                            "Direct prometheus_client metric instantiation without emit_metric.\n"
                            "  → Add metric to core/observability/metrics.py _REGISTRY and use emit_metric()"
                        ),
                        is_error=False,  # warning
                    ))
                    break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — Define-but-never-read metadata fields
# ─────────────────────────────────────────────────────────────────────────────

def _get_metadata_schema_fields(root: Path) -> dict[str, list[str]]:
    """Extract field names from each typed metadata model in core/metadata/models.py."""
    models_path = root / "core" / "metadata" / "models.py"
    if not models_path.exists():
        return {}

    source = models_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    models: dict[str, list[str]] = {}
    target_classes = {"DetectionMetadata", "ScoringMetadata", "GenerationMetadata", "PostGenMetadata"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in target_classes:
            continue
        fields = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
        models[node.name] = fields

    return models


def _build_reader_corpus(root: Path, models_path: Path) -> str:
    """Concatenate all Python source (excluding the models file itself) for reader search."""
    parts: list[str] = []
    for path in root.rglob("*.py"):
        if _is_excluded(path.relative_to(root), GLOBAL_EXCLUDE_DIRS):
            continue
        if path == models_path:
            continue
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
    return "\n".join(parts)


def check3_define_but_never_read(root: Path) -> CheckResult:
    """Detect metadata schema fields with no reader anywhere in the codebase."""
    result = CheckResult("CHECK 3: Define-but-never-read metadata fields")

    models_path = root / "core" / "metadata" / "models.py"
    if not models_path.exists():
        return result  # nothing to check

    schema_fields = _get_metadata_schema_fields(root)
    if not schema_fields:
        return result

    corpus = _build_reader_corpus(root, models_path)

    for model_name, fields in schema_fields.items():
        for field_name in fields:
            has_reader = f".{field_name}" in corpus
            has_emit = f'"{field_name}"' in corpus and "emit_metric" in corpus
            # Check for explicit deprecated annotation in models.py source
            models_src = models_path.read_text(encoding="utf-8")
            has_deprecated = (
                f"deprecated: {field_name}" in models_src
                or f"# deprecated" in models_src
                or NOQA_ANNOTATION in models_src
            )

            if not (has_reader or has_emit or has_deprecated):
                result.violations.append(Violation(
                    check="CHECK3",
                    file=str(models_path.relative_to(root)),
                    line=0,
                    message=(
                        f"Field `{model_name}.{field_name}` declared but never read.\n"
                        "  → Add a reader, emit_metric call, or mark as deprecated"
                    ),
                    is_error=True,
                ))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4 — Magic numbers in pipeline code
# ─────────────────────────────────────────────────────────────────────────────

_MAGIC_NUMBER_RE = re.compile(
    r'(?<!["\'\w])'           # not inside a string or identifier
    r'(-?\d+(?:\.\d+)?)'      # integer or float
    r'(?![\w"\'])',            # not followed by string or identifier
)

# Patterns where numbers are expected/legitimate
_MAGIC_NUMBER_SKIP_PATTERNS = [
    re.compile(r'^\s*#'),                        # comment lines
    re.compile(r'def\s+\w+'),                    # function signatures
    re.compile(r'class\s+\w+'),                  # class definitions
    re.compile(r'version\s*='),                  # version strings
    re.compile(r'schema_version\s*='),           # schema version
    re.compile(r'__version__\s*='),
    re.compile(r'sleep\(\s*\d+'),                # sleep durations (ok as-is)
    re.compile(r'range\(\s*\d+'),                # range calls
    re.compile(r'buckets\s*=\s*\['),             # histogram buckets
    re.compile(r'HTTP_\d+'),                     # HTTP status codes
    re.compile(r'status_code\s*=\s*\d+'),
    re.compile(r'page_size\s*='),
    re.compile(r'max_retries\s*='),
    re.compile(r'timeout\s*='),
]


def _is_magic_number(value_str: str) -> bool:
    return value_str not in MAGIC_NUMBER_WHITELIST


def check4_magic_numbers(root: Path) -> CheckResult:
    """Warn about hardcoded numbers in pipeline directories."""
    result = CheckResult("CHECK 4: Magic numbers in pipeline code")

    scan_paths = [root / d for d in CHECK4_SCAN_DIRS]
    files: list[Path] = []
    for scan_dir in scan_paths:
        if scan_dir.exists():
            files.extend(
                p for p in scan_dir.rglob("*.py")
                if not _is_excluded(p.relative_to(root), GLOBAL_EXCLUDE_DIRS)
            )

    for path in files:
        lines = read_lines(path)
        rel = str(path.relative_to(root))

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()

            if NOQA_ANNOTATION in stripped:
                continue

            # Skip lines that are obviously legitimate
            if any(p.search(stripped) for p in _MAGIC_NUMBER_SKIP_PATTERNS):
                continue

            matches = _MAGIC_NUMBER_RE.findall(stripped)
            for match in matches:
                if _is_magic_number(match):
                    result.violations.append(Violation(
                        check="CHECK4",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Magic number `{match}` in: `{stripped[:80]}`\n"
                            "  → Extract to a named constant or env var"
                        ),
                        is_error=False,  # warning only
                    ))
                    break  # one warning per line

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _separator() -> str:
    return "─" * 72


def print_result(result: CheckResult) -> None:
    errors = [v for v in result.violations if v.is_error]
    warnings = [v for v in result.violations if not v.is_error]

    status = "✅ PASS" if not result.violations else ("❌ FAIL" if errors else "⚠️  WARN")
    print(f"\n{_separator()}")
    print(f"{status}  {result.check_name}")
    print(f"       errors={len(errors)}  warnings={len(warnings)}")
    print(_separator())

    for v in result.violations:
        tag = "ERROR" if v.is_error else "WARN "
        loc = f"{v.file}:{v.line}" if v.line else v.file
        print(f"  [{tag}] {loc}")
        for part in v.message.split("\n"):
            print(f"         {part}")
        print()


def print_summary(results: list[CheckResult], strict: bool) -> None:
    total_errors = sum(len([v for v in r.violations if v.is_error]) for r in results)
    total_warnings = sum(len([v for v in r.violations if not v.is_error]) for r in results)

    print(f"\n{'═' * 72}")
    print("CONTRACT ENFORCEMENT SUMMARY")
    print(f"  total errors:   {total_errors}")
    print(f"  total warnings: {total_warnings}")
    if strict:
        print("  mode: --strict (errors cause non-zero exit)")
    else:
        print("  mode: informative (no exit on warnings)")
    print(f"{'═' * 72}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_all_checks(root: Path, strict: bool = False) -> int:
    """Run all checks; return exit code (0=ok, 1=fail)."""
    checks = [
        check1_direct_metadata_assignment,
        check2_counter_without_emit_metric,
        check3_define_but_never_read,
        check4_magic_numbers,
    ]

    results: list[CheckResult] = []
    for check_fn in checks:
        r = check_fn(root)
        results.append(r)
        print_result(r)

    print_summary(results, strict)

    if strict:
        # Only CHECK 1 and CHECK 3 fail CI in strict mode
        blocking_checks = {"CHECK1", "CHECK3"}
        has_blocking_error = any(
            v.is_error and v.check in blocking_checks
            for r in results
            for v in r.violations
        )
        return 1 if has_blocking_error else 0

    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ARC5 Contract Enforcement CI check")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail CI (exit 1) when CHECK 1 or CHECK 3 violations are found",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (default: auto-detected from script location)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = run_all_checks(root=args.root, strict=args.strict)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
