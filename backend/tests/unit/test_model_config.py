"""Unit tests for core.providers.model_config — shared model-config loader."""
import json
from pathlib import Path

import pytest

from core.providers import model_config as mc

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with a fresh cache."""
    mc.clear_cache()
    yield
    mc.clear_cache()


# ── load_model_config ──────────────────────────────────────────────────────

def test_load_known_config_gemma4_26b():
    cfg = mc.load_model_config("gemma4_26b_a4b")
    assert isinstance(cfg, dict)
    assert cfg["provider"]["name"] == "google_ai_studio"
    assert cfg["model_id"] == "gemma4_26b_a4b"


def test_load_default_config():
    cfg = mc.load_model_config("default")
    assert cfg["model_id"] == "default"
    assert cfg["sampling"]["temperature"] == 0.5
    assert cfg["safety"]["harassment"] == "BLOCK_ONLY_HIGH"


def test_unknown_model_falls_back_to_default(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="core.providers.model_config"):
        cfg = mc.load_model_config("nonexistent_xyz")
    assert cfg["model_id"] == "default"
    assert any("nonexistent_xyz" in r.message for r in caplog.records)


def test_no_default_raises_filenotfound(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "_MODEL_CONFIG_DIRS", [tmp_path])
    mc.clear_cache()
    with pytest.raises(FileNotFoundError):
        mc.load_model_config("totally_missing")


# ── Cache behavior ────────────────────────────────────────────────────────

def test_cache_returns_same_instance():
    a = mc.load_model_config("gemma4_26b_a4b")
    b = mc.load_model_config("gemma4_26b_a4b")
    assert a is b


def test_clear_cache_drops_entries():
    a = mc.load_model_config("gemma4_26b_a4b")
    mc.clear_cache()
    b = mc.load_model_config("gemma4_26b_a4b")
    # After cache clear, a fresh dict instance is loaded.
    assert a is not b
    assert a == b


def test_malformed_json_raises(monkeypatch, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(mc, "_MODEL_CONFIG_DIRS", [tmp_path])
    mc.clear_cache()
    with pytest.raises(json.JSONDecodeError):
        mc.load_model_config("broken")


# ── Accessors: get_sampling ────────────────────────────────────────────────

def test_get_sampling_all_defaults_on_empty():
    s = mc.get_sampling({})
    assert s["temperature"] == 0.7
    assert s["top_p"] == 1.0
    assert s["top_k"] == 64
    assert s["max_tokens"] == 200
    assert s["frequency_penalty"] == 0.0
    assert s["presence_penalty"] == 0.0
    assert s["stop_sequences"] == []
    assert s["seed"] is None


def test_get_sampling_partial_override():
    s = mc.get_sampling({"sampling": {"temperature": 0.3}})
    assert s["temperature"] == 0.3
    assert s["top_p"] == 1.0  # default
    assert s["max_tokens"] == 200  # default


# ── Accessors: get_safety ──────────────────────────────────────────────────

def test_get_safety_defaults_block_only_high():
    s = mc.get_safety({})
    assert s["harassment"] == "BLOCK_ONLY_HIGH"
    assert s["hate_speech"] == "BLOCK_ONLY_HIGH"
    assert s["sexually_explicit"] == "BLOCK_ONLY_HIGH"
    assert s["dangerous_content"] == "BLOCK_ONLY_HIGH"


# ── Accessors: get_runtime / get_thinking / get_chat_template / get_provider_info ──

def test_get_runtime_defaults():
    r = mc.get_runtime({})
    assert r["timeout_seconds"] == 15
    assert r["max_retries"] == 2


def test_get_thinking_defaults():
    t = mc.get_thinking({})
    assert t["enabled"] is False
    assert t["token"] == "<|think|>"
    assert t["no_think_suffix"] == ""


def test_get_chat_template_defaults():
    ct = mc.get_chat_template({})
    assert ct["filter_thought_blocks"] is False
    assert ct["strip_thinking_artifacts"] is False


def test_get_provider_info_defaults():
    p = mc.get_provider_info({"model_id": "x"})
    assert p["name"] == ""
    assert p["model_string"] == "x"
    assert p["base_url"] is None


# ── Step 3: legacy snapshots ───────────────────────────────────────────────

def test_load_qwen3_14b_snapshot():
    cfg = mc.load_model_config("qwen3_14b")
    assert cfg["provider"]["name"] == "deepinfra"
    assert cfg["provider"]["model_string"] == "Qwen/Qwen3-14B"
    assert cfg["sampling"]["temperature"] == 0.7


def test_load_gemini_flash_lite_snapshot():
    cfg = mc.load_model_config("gemini_flash_lite")
    assert cfg["provider"]["name"] == "gemini"
    assert cfg["sampling"]["max_tokens"] == 60
