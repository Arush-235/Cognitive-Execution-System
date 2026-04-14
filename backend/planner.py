"""Planning engine  -  handles full and partial replanning."""

import json
import logging
from backend.database import get_db
from backend.ai import generate_plan
from backend.priority import compute_priority

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75


def needs_approval(parsed: dict) -> bool:
    """Check if parsed item requires user approval before processing."""
    if parsed.get("layer") == "strategic" and parsed.get("scope") == "global":
        return True
    if parsed.get("confidence", 1.0) < CONFIDENCE_THRESHOLD:
        return True
    return False


def determine_replan_action(parsed: dict) -> str:
    """Determine what replanning action is needed based on the new item.
    Returns: 'none' | 'partial' | 'full'
    """
    layer = parsed.get("layer", "technical")
    scope = parsed.get("scope", "local")

    if scope == "local" and layer == "technical":
        return "none"
    if scope == "cluster" or layer == "tactical":
        return "partial"
    if scope == "global" and layer == "strategic":
        return "full"
    # Default: no replanning for small items
    if layer in ("operational", "technical"):
        return "none"
    return "partial"


async def run_full_replan() -> dict:
    """Full plan rebuild from all active strategic items + high-priority tasks."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT id, content, layer, type, scope, cluster, status,
                      priority, energy_required, duration_minutes,
                      cognitive_load, dopamine_profile, initiation_friction,
                      completion_visibility, skip_count, resistance_flag
               FROM items
               WHERE status NOT IN ('done')
               ORDER BY priority DESC
               LIMIT 50"""
        )
        items = [dict(r) for r in rows]
        if not items:
            return {"now": [], "next": [], "later": [], "reasoning": "No active items."}

        # Recompute priorities
        for item in items:
            item["priority"] = compute_priority(item)
        items.sort(key=lambda x: x["priority"], reverse=True)

        # Fetch context for smarter planning
        completed_recently = await _get_recently_completed(db)
        goal_context = await _get_goal_context(db)

        try:
            plan_result = await generate_plan(
                items, completed_recently=completed_recently, goal_context=goal_context
            )
        except RuntimeError as e:
            logger.error("Full replan AI error: %s", e)
            return {"now": [], "next": [], "later": [], "reasoning": f"Planning failed: {e}"}
        await _save_plan(db, plan_result, items)
        return plan_result
    finally:
        await db.close()


async def run_partial_replan(cluster: str) -> dict:
    """Partial replan for a specific cluster."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT id, content, layer, type, scope, cluster, status,
                      priority, energy_required, duration_minutes,
                      cognitive_load, dopamine_profile, initiation_friction,
                      completion_visibility, skip_count, resistance_flag
               FROM items
               WHERE cluster = ? AND status NOT IN ('done')
               ORDER BY priority DESC
               LIMIT 30""",
            (cluster,),
        )
        items = [dict(r) for r in rows]
        if not items:
            return {"now": [], "next": [], "later": [], "reasoning": "No items in cluster."}

        for item in items:
            item["priority"] = compute_priority(item)
        items.sort(key=lambda x: x["priority"], reverse=True)

        # Fetch context for smarter planning
        completed_recently = await _get_recently_completed(db)
        goal_context = await _get_goal_context(db)

        try:
            plan_result = await generate_plan(
                items, completed_recently=completed_recently, goal_context=goal_context
            )
        except RuntimeError as e:
            logger.error("Partial replan AI error (cluster=%s): %s", cluster, e)
            return {"now": [], "next": [], "later": [], "reasoning": f"Planning failed: {e}"}
        await _save_plan(db, plan_result, items)
        await db.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            ("last_cluster_updated", cluster),
        )
        await db.commit()
        return plan_result
    finally:
        await db.close()


async def _save_plan(db, plan_result: dict, items: list[dict]):
    """Save plan to database."""
    if not isinstance(plan_result, dict):
        logger.error("Invalid plan result type: %s", type(plan_result))
        return

    cursor = await db.execute(
        "INSERT INTO plans (summary) VALUES (?)",
        (json.dumps(plan_result.get("reasoning", "")),),
    )
    plan_id = cursor.lastrowid

    # Map item_ids from plan result
    for role in ("now", "next", "later"):
        for entry in plan_result.get(role, []):
            item_id = entry.get("item_id")
            if item_id:
                await db.execute(
                    "INSERT OR IGNORE INTO plan_items (plan_id, item_id, role) VALUES (?, ?, ?)",
                    (plan_id, item_id, role),
                )
                # Update item status based on role
                status_map = {"now": "doing", "next": "next", "later": "backlog"}
                await db.execute(
                    "UPDATE items SET status = ? WHERE id = ?",
                    (status_map.get(role, "backlog"), item_id),
                )

    await db.execute(
        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
        ("last_plan_version", str(plan_id)),
    )
    await db.commit()


async def _get_recently_completed(db) -> list[dict]:
    """Get recently completed tasks for momentum-aware planning."""
    rows = await db.execute_fetchall(
        """SELECT id, content, cluster FROM items
           WHERE status = 'done'
           ORDER BY created_at DESC LIMIT 3"""
    )
    return [dict(r) for r in rows]


async def _get_goal_context(db) -> str:
    """Get goal summaries for planner context."""
    rows = await db.execute_fetchall(
        "SELECT summary FROM goals ORDER BY created_at DESC LIMIT 5"
    )
    return "; ".join(dict(r)["summary"] for r in rows) if rows else ""
