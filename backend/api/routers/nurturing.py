"""Nurturing sequences endpoints - Full implementation"""
from fastapi import APIRouter, Body, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging
import os
import json
from datetime import datetime

from core.nurturing import (
    get_nurturing_manager,
    NURTURING_SEQUENCES,
    SequenceType,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nurturing", tags=["nurturing"])

# Storage path for sequence configurations
SEQUENCES_CONFIG_PATH = "data/nurturing/sequences_config.json"


# ============================================================================
# Pydantic Models
# ============================================================================

class SequenceStep(BaseModel):
    delay_hours: int
    message: str


class UpdateSequenceRequest(BaseModel):
    steps: List[SequenceStep]


class ToggleSequenceRequest(BaseModel):
    enabled: Optional[bool] = None


# ============================================================================
# Sequence Configuration Manager
# ============================================================================

def _get_default_sequences() -> List[Dict[str, Any]]:
    """Get default sequences from NURTURING_SEQUENCES"""
    sequence_meta = {
        "interest_cold": {"name": "Cold Interest Followup", "id": "seq_interest_cold"},
        "objection_price": {"name": "Price Objection", "id": "seq_objection_price"},
        "objection_time": {"name": "Time Objection", "id": "seq_objection_time"},
        "objection_doubt": {"name": "Doubt Objection", "id": "seq_objection_doubt"},
        "objection_later": {"name": "Later Objection", "id": "seq_objection_later"},
        "abandoned": {"name": "Abandoned Cart", "id": "seq_abandoned"},
        "re_engagement": {"name": "Re-engagement", "id": "seq_re_engagement"},
        "post_purchase": {"name": "Post Purchase", "id": "seq_post_purchase"},
    }

    sequences = []
    for seq_type, steps in NURTURING_SEQUENCES.items():
        meta = sequence_meta.get(seq_type, {"name": seq_type.replace("_", " ").title(), "id": f"seq_{seq_type}"})
        sequences.append({
            "id": meta["id"],
            "type": seq_type,
            "name": meta["name"],
            "is_active": True,  # Default to active
            "steps": [{"delay_hours": delay, "message": msg} for delay, msg in steps],
            "enrolled_count": 0,
            "sent_count": 0,
        })

    return sequences


def _load_sequences_config(creator_id: str) -> Dict[str, Any]:
    """Load sequence configurations for a creator"""
    config_path = f"data/nurturing/{creator_id}_sequences.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading sequences config for {creator_id}: {e}")

    # Return default config
    return {"sequences": {}}


def _save_sequences_config(creator_id: str, config: Dict[str, Any]):
    """Save sequence configurations for a creator"""
    os.makedirs("data/nurturing", exist_ok=True)
    config_path = f"data/nurturing/{creator_id}_sequences.json"
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving sequences config for {creator_id}: {e}")


def _get_sequences_with_stats(creator_id: str) -> List[Dict[str, Any]]:
    """Get all sequences with real stats"""
    manager = get_nurturing_manager()
    config = _load_sequences_config(creator_id)
    stats = manager.get_stats(creator_id)
    by_sequence = stats.get("by_sequence", {})

    sequences = []
    for seq in _get_default_sequences():
        seq_type = seq["type"]

        # Apply config overrides
        if seq_type in config.get("sequences", {}):
            seq_config = config["sequences"][seq_type]
            if "is_active" in seq_config:
                seq["is_active"] = seq_config["is_active"]
            if "steps" in seq_config:
                seq["steps"] = seq_config["steps"]

        # Apply real stats
        seq_stats = by_sequence.get(seq_type, {})
        seq["enrolled_count"] = seq_stats.get("pending", 0)
        seq["sent_count"] = seq_stats.get("sent", 0)

        sequences.append(seq)

    return sequences


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{creator_id}/sequences")
async def get_nurturing_sequences(creator_id: str):
    """Get all nurturing sequences with configuration and stats"""
    sequences = _get_sequences_with_stats(creator_id)
    return {
        "status": "ok",
        "creator_id": creator_id,
        "sequences": sequences
    }


@router.get("/{creator_id}/followups")
async def get_nurturing_followups(
    creator_id: str,
    status: Optional[str] = None,
    limit: int = 50
):
    """Get all followups for a creator"""
    manager = get_nurturing_manager()
    followups = manager.get_all_followups(creator_id, status)

    # Limit results
    followups = followups[:limit]

    return {
        "status": "ok",
        "creator_id": creator_id,
        "followups": [fu.to_dict() for fu in followups],
        "count": len(followups)
    }


@router.get("/{creator_id}/stats")
async def get_nurturing_stats(creator_id: str):
    """Get nurturing statistics"""
    manager = get_nurturing_manager()
    stats = manager.get_stats(creator_id)

    # Count active sequences
    config = _load_sequences_config(creator_id)
    active_count = 0
    for seq in _get_default_sequences():
        seq_type = seq["type"]
        is_active = True  # Default
        if seq_type in config.get("sequences", {}):
            is_active = config["sequences"][seq_type].get("is_active", True)
        if is_active:
            active_count += 1

    return {
        "status": "ok",
        "creator_id": creator_id,
        "total": stats.get("total", 0),
        "pending": stats.get("pending", 0),
        "sent": stats.get("sent", 0),
        "cancelled": stats.get("cancelled", 0),
        "active_sequences": active_count,
        "by_sequence": stats.get("by_sequence", {})
    }


@router.post("/{creator_id}/sequences/{sequence_type}/toggle")
async def toggle_nurturing_sequence(
    creator_id: str,
    sequence_type: str,
    data: Optional[ToggleSequenceRequest] = Body(default=None)
):
    """Toggle a nurturing sequence on/off"""
    config = _load_sequences_config(creator_id)

    if "sequences" not in config:
        config["sequences"] = {}

    if sequence_type not in config["sequences"]:
        config["sequences"][sequence_type] = {}

    # Toggle or set explicitly
    current_active = config["sequences"][sequence_type].get("is_active", True)
    if data and data.enabled is not None:
        new_active = data.enabled
    else:
        new_active = not current_active

    config["sequences"][sequence_type]["is_active"] = new_active
    _save_sequences_config(creator_id, config)

    logger.info(f"Toggled sequence {sequence_type} for {creator_id}: is_active={new_active}")

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "is_active": new_active
    }


@router.put("/{creator_id}/sequences/{sequence_type}")
async def update_nurturing_sequence(
    creator_id: str,
    sequence_type: str,
    data: UpdateSequenceRequest
):
    """Update nurturing sequence steps"""
    config = _load_sequences_config(creator_id)

    if "sequences" not in config:
        config["sequences"] = {}

    if sequence_type not in config["sequences"]:
        config["sequences"][sequence_type] = {}

    # Update steps
    config["sequences"][sequence_type]["steps"] = [
        {"delay_hours": step.delay_hours, "message": step.message}
        for step in data.steps
    ]

    _save_sequences_config(creator_id, config)

    logger.info(f"Updated sequence {sequence_type} for {creator_id} with {len(data.steps)} steps")

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "steps": config["sequences"][sequence_type]["steps"]
    }


@router.get("/{creator_id}/sequences/{sequence_type}/enrolled")
async def get_enrolled_followers(creator_id: str, sequence_type: str):
    """Get followers enrolled in a specific sequence"""
    manager = get_nurturing_manager()
    followups = manager.get_all_followups(creator_id, status="pending")

    # Group by follower_id for this sequence type
    enrolled_map: Dict[str, Dict[str, Any]] = {}

    for fu in followups:
        if fu.sequence_type != sequence_type:
            continue

        fid = fu.follower_id
        if fid not in enrolled_map:
            enrolled_map[fid] = {
                "follower_id": fid,
                "next_scheduled": fu.scheduled_at,
                "pending_steps": []
            }

        enrolled_map[fid]["pending_steps"].append({
            "step": fu.step,
            "scheduled_at": fu.scheduled_at,
            "message_preview": fu.message_template[:50] + "..." if len(fu.message_template) > 50 else fu.message_template
        })

        # Update next_scheduled to earliest
        if fu.scheduled_at < enrolled_map[fid]["next_scheduled"]:
            enrolled_map[fid]["next_scheduled"] = fu.scheduled_at

    enrolled_list = list(enrolled_map.values())

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "enrolled": enrolled_list,
        "count": len(enrolled_list)
    }


@router.delete("/{creator_id}/cancel/{follower_id}")
async def cancel_nurturing(
    creator_id: str,
    follower_id: str,
    sequence_type: Optional[str] = None
):
    """Cancel nurturing for a follower"""
    manager = get_nurturing_manager()
    cancelled = manager.cancel_followups(creator_id, follower_id, sequence_type)

    logger.info(f"Cancelled {cancelled} followups for {follower_id} (creator: {creator_id}, sequence: {sequence_type})")

    return {
        "status": "ok",
        "follower_id": follower_id,
        "cancelled": cancelled
    }


# Legacy endpoint for backwards compatibility
@router.delete("/{creator_id}/followers/{follower_id}/nurturing")
async def cancel_nurturing_legacy(creator_id: str, follower_id: str):
    """Cancel all nurturing for a follower (legacy endpoint)"""
    return await cancel_nurturing(creator_id, follower_id, None)
