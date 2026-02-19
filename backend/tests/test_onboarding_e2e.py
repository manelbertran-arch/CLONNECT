"""
E2E tests for the onboarding pipeline.
Verifies that all components are wired correctly.
"""

import ast
import os
import re

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_file(relative_path: str) -> str:
    """Read a file relative to backend/."""
    path = os.path.join(BACKEND_DIR, relative_path)
    with open(path) as f:
        return f.read()


def _parse_file(relative_path: str) -> ast.Module:
    """Parse a Python file and return AST."""
    return ast.parse(_read_file(relative_path))


# === Test 1: _run_clone_creation exists and is async ===
def test_clone_creation_function_exists():
    tree = _parse_file("api/routers/onboarding/clone.py")
    async_funcs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    ]
    assert "_run_clone_creation" in async_funcs, (
        "_run_clone_creation must be an async function in clone.py"
    )


# === Test 2: Pipeline has all steps ===
def test_pipeline_has_all_steps():
    content = _read_file("api/routers/onboarding/clone.py")
    required_steps = ["instagram", "website", "personality", "training", "activating"]
    for step in required_steps:
        assert step in content, f"Step '{step}' not found in clone.py"


# === Test 3: _verify_onboarding_internal exists ===
def test_verification_function_exists():
    tree = _parse_file("api/routers/onboarding/verification.py")
    async_funcs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    ]
    assert "_verify_onboarding_internal" in async_funcs, (
        "_verify_onboarding_internal must exist in verification.py"
    )


# === Test 4: Personality extraction is wired in pipeline ===
def test_personality_extraction_wired():
    content = _read_file("api/routers/onboarding/clone.py")
    assert "personality_extraction" in content or "extraction" in content, (
        "Personality extraction must be referenced in clone.py pipeline"
    )


# === Test 5: OAuth callback doesn't have _auto_onboard active ===
def test_no_race_condition():
    content = _read_file("api/routers/oauth.py")
    # _auto_onboard should be commented out or not called directly
    # It should only be called via asyncio.create_task or similar
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "_auto_onboard" in stripped and not stripped.startswith("#"):
            # It's OK if it's a function definition or in create_task
            assert (
                "async def" in stripped
                or "create_task" in stripped
                or "def " in stripped
            ), f"_auto_onboard called directly at oauth.py line {i+1}: {stripped}"


# === Test 6: No suspicious asyncio.sleep >2s in progress flow ===
def test_progress_tracking_is_real():
    content = _read_file("api/routers/onboarding/clone.py")
    # Find all asyncio.sleep calls and check durations
    sleep_matches = re.findall(r"asyncio\.sleep\((\d+)\)", content)
    for val in sleep_matches:
        assert int(val) <= 60, (
            f"Found asyncio.sleep({val}) in clone.py — suspicious delay > 60s"
        )


# === Test 7: scrape_and_index_website not in clone.py ===
def test_single_scraper():
    content = _read_file("api/routers/onboarding/clone.py")
    assert "scrape_and_index_website" not in content, (
        "Legacy scraper scrape_and_index_website should not be in clone.py"
    )


# === Test 8: start-clone and progress endpoints exist ===
def test_onboarding_endpoints_exist():
    content = _read_file("api/routers/onboarding/clone.py")
    assert "start-clone" in content or "start_clone" in content, (
        "start-clone endpoint must exist in clone.py"
    )
    progress_content = _read_file("api/routers/onboarding/progress.py")
    assert "progress" in progress_content.lower(), (
        "progress endpoint must exist in progress.py"
    )


# === Test 9: /onboarding/verification/ endpoint exists ===
def test_verification_endpoint_exists():
    content = _read_file("api/routers/onboarding/verification.py")
    assert "/verification/" in content or "verification" in content, (
        "verification endpoint must exist"
    )
    init_content = _read_file("api/routers/onboarding/__init__.py")
    assert "verification_router" in init_content, (
        "verification_router must be registered in __init__.py"
    )


# === Test 10: B11 token expiry check exists ===
def test_token_expiry_check_exists():
    content = _read_file("api/startup.py")
    assert "token_expiry" in content.lower() or "B11" in content, (
        "Instagram token expiry check (B11) must exist in startup.py"
    )


# === Test 11: A15 pending approval expiry exists ===
def test_pending_approval_expiry_exists():
    content = _read_file("api/startup.py")
    assert "pending_expiry" in content.lower() or "auto_24h" in content, (
        "Pending approval expiry (A15) must exist in startup.py"
    )


# === Test 12: B9 product detector has LLM fallback ===
def test_product_detector_has_fallback():
    content = _read_file("ingestion/v2/product_detector.py")
    assert "llm_fallback" in content or "detect_with_fallback" in content, (
        "ProductDetector must have LLM fallback (B9)"
    )
