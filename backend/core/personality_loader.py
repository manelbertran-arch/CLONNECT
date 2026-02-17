"""
Personality Extraction Loader — loads parsed Doc D into production pipeline.

Parses doc_d_bot_configuration.md and caches the result in memory.
Returns None if no extraction exists for a given creator_id.

Used by:
- services/creator_style_loader.py (system prompt injection)
- core/response_fixes.py (blacklist filtering)
- services/response_variator_v2.py (template pools)
- core/prompt_builder.py (calibration overrides)
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory cache: creator_id -> ExtractionData
_cache: Dict[str, "ExtractionData"] = {}

EXTRACTIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "personality_extractions",
)


@dataclass
class TemplateEntry:
    """A single template entry from a pool category."""
    text: str
    count: int = 1


@dataclass
class MultiBubbleTemplate:
    """A multi-bubble template (list of sequential messages)."""
    id: str
    bubbles: List[str] = field(default_factory=list)
    risk: str = "low"
    mode: str = "AUTO"


@dataclass
class ExtractionData:
    """Parsed personality extraction data from Doc D."""
    creator_id: str
    system_prompt: str = ""
    blacklist_phrases: List[str] = field(default_factory=list)
    calibration: Dict = field(default_factory=dict)
    template_pools: Dict[str, List[TemplateEntry]] = field(default_factory=dict)
    template_modes: Dict[str, str] = field(default_factory=dict)
    multi_bubble: List[MultiBubbleTemplate] = field(default_factory=list)


def _find_doc_path(creator_id: str) -> Optional[str]:
    """Find doc_d_bot_configuration.md for a creator_id (slug or UUID).

    Checks: 1) exact match, 2) scan subdirectories for any containing a match.
    This handles the case where the DM agent uses slugs (e.g. 'stefano_bonanno')
    but extractions are stored under UUIDs.
    """
    # Direct match
    direct = os.path.join(EXTRACTIONS_DIR, creator_id, "doc_d_bot_configuration.md")
    if os.path.isfile(direct):
        return direct

    # Scan all subdirectories
    if os.path.isdir(EXTRACTIONS_DIR):
        for entry in os.listdir(EXTRACTIONS_DIR):
            candidate = os.path.join(EXTRACTIONS_DIR, entry, "doc_d_bot_configuration.md")
            if os.path.isfile(candidate):
                return candidate

    return None


def load_extraction(creator_id: str) -> Optional[ExtractionData]:
    """Load and cache personality extraction for a creator.

    Returns None if no extraction exists.
    """
    if creator_id in _cache:
        return _cache[creator_id]

    doc_path = _find_doc_path(creator_id)
    if not doc_path:
        _cache[creator_id] = None
        return None

    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        data = _parse_doc_d(creator_id, content)
        _cache[creator_id] = data
        logger.info(
            "Loaded personality extraction for %s: "
            "prompt=%d chars, blacklist=%d, pools=%d cats, multi_bubble=%d",
            creator_id, len(data.system_prompt), len(data.blacklist_phrases),
            len(data.template_pools), len(data.multi_bubble),
        )
        return data
    except Exception as e:
        logger.error("Failed to parse personality extraction for %s: %s", creator_id, e)
        _cache[creator_id] = None
        return None


def get_calibration_override(creator_id: str) -> Optional[Dict]:
    """Get calibration overrides from Doc D §4.3.

    Returns dict with keys like max_message_length_chars, max_emojis_per_message,
    enforce_fragmentation, etc. Returns None if no extraction exists.
    """
    extraction = load_extraction(creator_id)
    if not extraction or not extraction.calibration:
        return None
    return extraction.calibration


def invalidate_cache(creator_id: Optional[str] = None) -> None:
    """Clear cached extraction data."""
    if creator_id:
        _cache.pop(creator_id, None)
    else:
        _cache.clear()


def _parse_doc_d(creator_id: str, content: str) -> ExtractionData:
    """Parse doc_d_bot_configuration.md into structured data."""
    data = ExtractionData(creator_id=creator_id)

    # Split by top-level sections (## headers)
    _parse_system_prompt(data, content)
    _parse_blacklist(data, content)
    _parse_calibration(data, content)
    _parse_template_pools(data, content)
    _parse_multi_bubble(data, content)

    return data


def _parse_system_prompt(data: ExtractionData, content: str) -> None:
    """Extract §4.1 SYSTEM PROMPT — everything between the first ``` and the closing ```."""
    match = re.search(
        r"## 4\.1 SYSTEM PROMPT[^\n]*\n```\n(.*?)```",
        content, re.DOTALL,
    )
    if match:
        data.system_prompt = match.group(1).strip()


def _parse_blacklist(data: ExtractionData, content: str) -> None:
    """Extract §4.2 BLACKLIST — lines starting with '  - '."""
    match = re.search(
        r"## 4\.2 BLACKLIST[^\n]*\n(.*?)(?=\n## |\Z)",
        content, re.DOTALL,
    )
    if not match:
        return
    for line in match.group(1).split("\n"):
        line = line.strip()
        if line.startswith("- "):
            phrase = line[2:].strip().strip('"').strip("'")
            if phrase:
                data.blacklist_phrases.append(phrase)


def _parse_calibration(data: ExtractionData, content: str) -> None:
    """Extract §4.3 PARAMETROS DE CALIBRACION — key: value lines."""
    match = re.search(
        r"## 4\.3 PARAM[^\n]*\n(.*?)(?=\n## |\Z)",
        content, re.DOTALL,
    )
    if not match:
        return
    for line in match.group(1).split("\n"):
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            key = key.strip()
            value = value.strip()
            # Parse typed values
            if value.lower() in ("true", "false"):
                data.calibration[key] = value.lower() == "true"
            else:
                try:
                    data.calibration[key] = int(value)
                except ValueError:
                    try:
                        data.calibration[key] = float(value)
                    except ValueError:
                        data.calibration[key] = value


def _parse_template_pools(data: ExtractionData, content: str) -> None:
    """Extract §4.4 TEMPLATE POOL — categories with template entries."""
    match = re.search(
        r"## 4\.4 TEMPLATE POOL[^\n]*\n(.*?)(?=\n## 4\.5|\Z)",
        content, re.DOTALL,
    )
    if not match:
        return

    current_cat = None
    for line in match.group(1).split("\n"):
        # Category header: ### laugh (freq=2.2%, risk=low, mode=AUTO)
        cat_match = re.match(
            r"### (\w+)\s*\(.*?mode=(\w+)",
            line.strip(),
        )
        if cat_match:
            current_cat = cat_match.group(1)
            mode = cat_match.group(2)
            data.template_pools[current_cat] = []
            data.template_modes[current_cat] = mode
            continue

        # Template entry:   -> "Jajaja" — real message (22x observed) (22x)
        tmpl_match = re.match(
            r'\s*->\s*"(.+?)"\s*—.*?\((\d+)x',
            line,
        )
        if tmpl_match and current_cat:
            text = tmpl_match.group(1)
            count = int(tmpl_match.group(2))
            data.template_pools[current_cat].append(TemplateEntry(text=text, count=count))


def _parse_multi_bubble(data: ExtractionData, content: str) -> None:
    """Extract §4.5 PLANTILLAS MULTI-BURBUJA."""
    match = re.search(
        r"## 4\.5 PLANTILLAS MULTI[^\n]*\n(.*)",
        content, re.DOTALL,
    )
    if not match:
        return

    current_mb = None
    for line in match.group(1).split("\n"):
        # Header: ### mb_0 (multi-bubble (1x observed), risk=low, mode=AUTO)
        mb_match = re.match(
            r"### (mb_\d+)\s*\(.*?risk=(\w+).*?mode=(\w+)",
            line.strip(),
        )
        if mb_match:
            current_mb = MultiBubbleTemplate(
                id=mb_match.group(1),
                risk=mb_match.group(2),
                mode=mb_match.group(3),
            )
            data.multi_bubble.append(current_mb)
            continue

        # Bubble line:   Burbuja 1: "Hola {nombre}! Como estamos?"
        bubble_match = re.match(
            r'\s*Burbuja \d+:\s*"(.+)"',
            line,
        )
        if bubble_match and current_mb:
            current_mb.bubbles.append(bubble_match.group(1))
