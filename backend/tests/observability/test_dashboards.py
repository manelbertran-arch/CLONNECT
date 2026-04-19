"""
ARC5 Phase 4 — Tests for Grafana dashboard JSON validity and alert rule integrity.

Validates:
1. All dashboard JSON files parse correctly
2. Required Grafana fields present
3. Alert PromQL queries reference only metrics that exist in the registry
4. Dashboard Prometheus queries only reference registered metrics
"""

import json
import re
from pathlib import Path

import pytest
import yaml

DASHBOARDS_DIR = Path(__file__).parent.parent.parent / "ops" / "grafana" / "dashboards"
ALERTS_FILE = Path(__file__).parent.parent.parent / "ops" / "grafana" / "alerts.yaml"
EXPECTED_DASHBOARD_FILES = [
    "clonnect_pipeline_overview.json",
    "clonnect_arc1_budget.json",
    "clonnect_arc2_memory.json",
    "clonnect_arc3_compactor.json",
    "clonnect_business.json",
]
REQUIRED_DASHBOARD_FIELDS = {"title", "uid", "panels", "schemaVersion", "templating", "time", "tags"}
REQUIRED_PANEL_FIELDS = {"id", "title", "type", "gridPos"}

# Metrics that DO exist in the registry (core/observability/metrics.py _METRIC_SPECS)
REGISTERED_METRICS = {
    "generation_duration_ms",
    "scoring_duration_ms",
    "detection_duration_ms",
    "compaction_applied_total",
    "memory_extraction_total",
    "lead_memories_read_total",
    "lead_memories_read_duration_ms",
    "dual_write_success_total",
    "dual_write_failure_total",
    "llm_api_call_total",
    "llm_api_duration_ms",
    "cache_hit_total",
    "cache_miss_total",
    "webhook_received_total",
    "webhook_processed_total",
    "budget_orchestrator_duration_ms",
    "budget_section_truncation_total",
    "dm_budget_utilization",
    "dm_budget_sections_selected",
    "dm_budget_sections_dropped_total",
    "dm_budget_sections_compressed_total",
    "rule_violation_total",
    "active_conversations_gauge",
}

# Suffixes automatically added by prometheus_client for Histograms
PROMETHEUS_SUFFIXES = {"_bucket", "_count", "_sum", "_total"}


def _strip_prometheus_suffix(name: str) -> str:
    for suffix in PROMETHEUS_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _extract_metric_names_from_promql(expr: str) -> list[str]:
    """Extract bare metric names from a PromQL expression (heuristic, not full parser).

    Strategy:
    1. Strip content inside {...} label selectors so label names/values are not matched
    2. Strip string literals
    3. Match identifiers immediately followed by { or [ (metric selectors)
    """
    # Remove label selector bodies: {creator_id=~"$x", status="ok"}
    stripped = re.sub(r"\{[^}]*\}", "{}", expr)
    # Remove string literals
    stripped = re.sub(r'"[^"]*"', '""', stripped)
    # Match identifiers immediately followed by { or [  (the metric selector pattern)
    pattern = re.compile(r"\b([a-z][a-z0-9_]+)\s*(?:\{|\[)")
    candidates = pattern.findall(stripped)
    # Filter out PromQL functions/keywords
    promql_keywords = {
        "sum", "rate", "increase", "histogram_quantile", "by", "without",
        "label_values", "max", "min", "avg", "count", "irate", "delta",
        "deriv", "predict_linear", "quantile", "stddev", "stdvar", "topk",
        "bottomk", "count_values", "absent", "floor", "ceil", "round",
        "clamp_max", "clamp_min", "exp", "log", "sqrt", "changes",
        "resets", "scalar", "vector", "sort", "sort_desc", "time",
        "minute", "hour", "day", "month", "year", "on", "ignoring",
        "group_left", "group_right", "bool", "le", "offset",
    }
    return [c for c in candidates if c not in promql_keywords]


# ─────────────────────────────────────────────────────────────────────────────
# 1. File existence
# ─────────────────────────────────────────────────────────────────────────────

def test_all_dashboard_files_exist():
    for filename in EXPECTED_DASHBOARD_FILES:
        path = DASHBOARDS_DIR / filename
        assert path.exists(), f"Dashboard file missing: {path}"


def test_alerts_file_exists():
    assert ALERTS_FILE.exists(), f"alerts.yaml missing: {ALERTS_FILE}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. JSON validity
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_valid_json(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, dict), f"{filename} root must be a JSON object"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Required Grafana fields
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_has_required_fields(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    missing = REQUIRED_DASHBOARD_FIELDS - set(data.keys())
    assert not missing, f"{filename} missing fields: {missing}"


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_has_panels(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    panels = data.get("panels", [])
    assert len(panels) >= 1, f"{filename} has no panels"


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_panels_have_required_fields(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    for panel in data.get("panels", []):
        missing = REQUIRED_PANEL_FIELDS - set(panel.keys())
        assert not missing, f"{filename} panel '{panel.get('title', '?')}' missing: {missing}"


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_uid_is_unique_string(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    uid = data.get("uid")
    assert isinstance(uid, str) and len(uid) > 0, f"{filename} uid must be a non-empty string"


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_schema_version_is_grafana_10(filename):
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    schema_version = data.get("schemaVersion", 0)
    assert schema_version >= 38, f"{filename} schemaVersion {schema_version} < 38 (Grafana 10.x)"


def test_all_dashboard_uids_are_distinct():
    uids = []
    for filename in EXPECTED_DASHBOARD_FILES:
        path = DASHBOARDS_DIR / filename
        with open(path) as f:
            data = json.load(f)
        uids.append(data.get("uid"))
    assert len(uids) == len(set(uids)), f"Duplicate UIDs found: {uids}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Alert YAML validity
# ─────────────────────────────────────────────────────────────────────────────

def test_alerts_yaml_valid():
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "alerts.yaml root must be a mapping"
    assert "groups" in data, "alerts.yaml must have 'groups' key"


def test_alerts_yaml_has_expected_groups():
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    group_names = {g["name"] for g in data["groups"]}
    assert "clonnect-critical" in group_names
    assert "clonnect-warning" in group_names


def test_alerts_yaml_has_seven_active_rules():
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    total_rules = sum(len(g.get("rules", [])) for g in data["groups"])
    assert total_rules == 7, f"Expected 7 active alert rules, got {total_rules}"


def test_alerts_yaml_rules_have_required_fields():
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    required = {"alert", "expr", "for", "labels", "annotations"}
    for group in data["groups"]:
        for rule in group.get("rules", []):
            missing = required - set(rule.keys())
            assert not missing, f"Alert rule '{rule.get('alert', '?')}' missing: {missing}"


def test_alerts_yaml_rules_have_severity_label():
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    for group in data["groups"]:
        for rule in group.get("rules", []):
            severity = rule.get("labels", {}).get("severity")
            assert severity in ("critical", "warning"), \
                f"Alert '{rule.get('alert')}' has invalid severity: {severity}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. PromQL queries reference existing metrics
# ─────────────────────────────────────────────────────────────────────────────

def _collect_dashboard_exprs(filename: str) -> list[tuple[str, str]]:
    """Return list of (panel_title, expr) for all targets in a dashboard."""
    path = DASHBOARDS_DIR / filename
    with open(path) as f:
        data = json.load(f)
    results = []
    for panel in data.get("panels", []):
        panel_title = panel.get("title", "untitled")
        for target in panel.get("targets", []):
            expr = target.get("expr", "")
            if expr and not expr.startswith("label_values"):
                results.append((panel_title, expr))
    return results


@pytest.mark.parametrize("filename", EXPECTED_DASHBOARD_FILES)
def test_dashboard_queries_reference_existing_metrics(filename):
    """All PromQL expressions should only reference metrics in REGISTERED_METRICS."""
    exprs = _collect_dashboard_exprs(filename)
    unknown_refs = []
    for panel_title, expr in exprs:
        candidates = _extract_metric_names_from_promql(expr)
        for candidate in candidates:
            base = _strip_prometheus_suffix(candidate)
            if base not in REGISTERED_METRICS and candidate not in REGISTERED_METRICS:
                # Allow Grafana template variables like $__all, $creator_id
                if not candidate.startswith("__") and "_" in candidate:
                    unknown_refs.append((panel_title, candidate, expr[:80]))
    assert not unknown_refs, (
        f"{filename} references unregistered metrics:\n"
        + "\n".join(f"  panel='{p}' metric='{m}' expr='{e}...'" for p, m, e in unknown_refs)
    )


def test_alert_queries_reference_existing_metrics():
    """All active (non-commented) alert PromQL exprs should reference registered metrics."""
    with open(ALERTS_FILE) as f:
        data = yaml.safe_load(f)
    unknown_refs = []
    for group in data["groups"]:
        for rule in group.get("rules", []):
            expr = rule.get("expr", "")
            alert_name = rule.get("alert", "?")
            candidates = _extract_metric_names_from_promql(expr)
            for candidate in candidates:
                base = _strip_prometheus_suffix(candidate)
                if base not in REGISTERED_METRICS and candidate not in REGISTERED_METRICS:
                    if "_" in candidate:
                        unknown_refs.append((alert_name, candidate, expr[:80]))
    assert not unknown_refs, (
        "Alert rules reference unregistered metrics:\n"
        + "\n".join(f"  alert='{a}' metric='{m}' expr='{e}...'" for a, m, e in unknown_refs)
    )
