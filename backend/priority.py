"""Priority scoring engine  -  deterministic backbone.

Uses the ADHD-aware scheduler for full scoring when user state is available,
falls back to a simpler formula for ingestion-time priority.
"""

from backend.scheduler import score_task, LAYER_WEIGHT, ENERGY_LEVEL


def compute_priority(item: dict, user_state: dict = None) -> float:
    """Compute task priority score.

    If user_state is provided, uses the full ADHD-aware scoring engine.
    Otherwise, uses a lightweight formula for ingestion-time ranking.
    """
    if user_state:
        return score_task(item, user_state)

    # Lightweight fallback for ingestion (no user state yet)
    layer_w = LAYER_WEIGHT.get(item.get("layer", "technical"), 1.0)
    urgency = 1.0 if item.get("status") in ("next", "doing") else 0.0
    friction = {"low": 0.0, "medium": 0.5, "high": 1.5}.get(
        item.get("initiation_friction", "medium"), 0.5
    )
    dopamine = {"quick_reward": 0.5, "neutral": 0.0, "delayed_reward": -0.3}.get(
        item.get("dopamine_profile", "neutral"), 0.0
    )
    return round(layer_w + urgency + dopamine - friction + 0.5, 2)
