"""ADHD-aware Psychological Scheduling Engine.

Implements Section 21 of the CES spec:
- User state inference (energy, focus, momentum, time-of-day)
- Circadian mapping
- ADHD-aware task scoring (cognitive load, dopamine, friction, momentum)
- Rule-based selection (start bias, momentum mode, anti-avoidance, energy matching, dopamine sequencing)
- Break enforcement
- Avoidance detection
"""

from datetime import datetime, timedelta
from typing import Optional
import json

# ── Skip Taxonomy ─────────────────────────────────────────────────

SKIP_CATEGORIES = {
    "not_now": {"label": "Not right now", "emoji": "⏰", "weight": 0.0},
    "too_hard": {"label": "Feels too hard", "emoji": "🧱", "weight": -0.5},
    "unclear": {"label": "Not sure what to do", "emoji": "❓", "weight": -0.3},
    "boring": {"label": "Too boring", "emoji": "😴", "weight": -0.2},
    "anxious": {"label": "Makes me anxious", "emoji": "😰", "weight": -1.0},
}

# ── Circadian Strategy Map ────────────────────────────────────────

CIRCADIAN_MAP = {
    "morning":   {"ideal_cognitive": "high",   "ideal_friction": "medium", "strategy": "planning_deep_work"},
    "afternoon": {"ideal_cognitive": "medium",  "ideal_friction": "low",    "strategy": "execution_structured"},
    "evening":   {"ideal_cognitive": "low",     "ideal_friction": "low",    "strategy": "light_admin_review"},
    "night":     {"ideal_cognitive": "medium",  "ideal_friction": "low",    "strategy": "creative_low_stakes"},
}

# ── Numeric maps for scoring ─────────────────────────────────────

COGNITIVE_LEVEL = {"low": 1, "medium": 2, "high": 3}
FRICTION_LEVEL = {"low": 1, "medium": 2, "high": 3}
LAYER_WEIGHT = {"strategic": 4.0, "tactical": 3.0, "operational": 2.0, "technical": 1.0}
ENERGY_LEVEL = {"low": 1, "medium": 2, "high": 3}


def infer_time_of_day(now: Optional[datetime] = None) -> str:
    """Deterministic time-of-day from clock."""
    h = (now or datetime.now()).hour
    if 6 <= h < 12:
        return "morning"
    elif 12 <= h < 17:
        return "afternoon"
    elif 17 <= h < 21:
        return "evening"
    else:
        return "night"


def infer_user_state(
    completed_recently: list[dict],
    history_events: list[dict],
    now: Optional[datetime] = None,
    routine: Optional[dict] = None,
    checkin: Optional[dict] = None,
) -> dict:
    """Infer the user's current cognitive state from observable signals.

    Two-tier model:
    - If a recent check-in exists, use it as ground truth (high confidence)
    - Otherwise, infer from behavioral signals (lower confidence)

    Returns: {energy, focus, momentum, time_of_day, work_minutes_since_break, confidence}
    """
    tod = infer_time_of_day(now)
    current_hour = (now or datetime.now()).hour

    # --- Momentum: based on recent completions ---
    recent_completions = [
        e for e in history_events
        if e.get("event") == "completed"
    ]
    completion_count = len(recent_completions)

    if completion_count == 0:
        momentum = "none"
    elif completion_count <= 2:
        momentum = "building"
    else:
        momentum = "high"

    # --- Check-in path (high confidence) ---
    if checkin and checkin.get("has_recent"):
        ci_energy = checkin.get("energy", 3)
        ci_focus = checkin.get("focus", 3)
        energy = "low" if ci_energy <= 2 else ("high" if ci_energy >= 4 else "medium")
        focus = "scattered" if ci_focus <= 2 else ("locked_in" if ci_focus >= 4 else "normal")
        confidence = 0.9
    else:
        # --- Behavioral inference path (lower confidence) ---
        confidence = 0.4

        # Energy: routine-aware circadian model
        if routine and routine.get("has_routine"):
            energy = _routine_energy(current_hour, routine)
            confidence += 0.1
        else:
            tod_energy = {"morning": "high", "afternoon": "medium", "evening": "low", "night": "low"}
            energy = tod_energy[tod]

        # If they just completed a high cognitive task, downgrade energy slightly
        if recent_completions:
            last = recent_completions[-1]
            if last.get("user_energy"):
                energy = last["user_energy"]
                confidence += 0.15

        # Focus: infer from skip/pause patterns
        recent_skips = sum(1 for e in history_events if e.get("event") == "skipped")
        recent_pauses = sum(1 for e in history_events if e.get("event") == "paused")

        if recent_skips >= 2 or recent_pauses >= 3:
            focus = "scattered"
            confidence += 0.1  # strong signal
        elif completion_count >= 2 and recent_skips == 0:
            focus = "locked_in"
            confidence += 0.15
        else:
            focus = "normal"

    # --- Energy decay: degrade energy after long work ---
    work_minutes = _estimate_work_minutes(history_events, now)
    if work_minutes >= 45 and energy == "high":
        energy = "medium"
    elif work_minutes >= 75 and energy == "medium":
        energy = "low"

    return {
        "energy": energy,
        "focus": focus,
        "momentum": momentum,
        "time_of_day": tod,
        "work_minutes_since_break": work_minutes,
        "confidence": min(round(confidence, 2), 1.0),
    }


def _estimate_work_minutes(events: list[dict], now: Optional[datetime] = None) -> int:
    """Estimate continuous work minutes from recent events."""
    if not events:
        return 0

    now_ts = now or datetime.now()
    total = 0
    for e in events:
        elapsed = e.get("elapsed_seconds", 0) or 0
        total += elapsed
    return total // 60


def _parse_time(t: str) -> Optional[int]:
    """Parse HH:MM string to hour. Returns None if invalid."""
    if not t or ":" not in t:
        return None
    try:
        return int(t.split(":")[0])
    except (ValueError, IndexError):
        return None


def _routine_energy(current_hour: int, routine: dict) -> str:
    """Compute energy level based on user's reported daily routine.

    Energy curve logic:
    - Just woke up (first 1h): medium (warming up)
    - 1-2h after wake: high (peak morning energy)
    - Work hours first half: high
    - Work hours second half: medium (post-lunch dip)
    - 1h after work ends: low (decompression)
    - Evening until 2h before sleep: medium (second wind)
    - 2h before sleep: low (winding down)
    - After sleep time / before wake: low
    """
    wake = _parse_time(routine.get("wake_time", ""))
    work_start = _parse_time(routine.get("work_start", ""))
    work_end = _parse_time(routine.get("work_end", ""))
    sleep = _parse_time(routine.get("sleep_time", ""))

    if wake is None or sleep is None:
        tod_energy = {"morning": "high", "afternoon": "medium", "evening": "low", "night": "low"}
        return tod_energy.get(infer_time_of_day(), "medium")

    # Normalize for overnight (sleep < wake handled by wrapping)
    h = current_hour

    # Before wake or after sleep → low
    if sleep > wake:
        if h >= sleep or h < wake:
            return "low"
    else:  # stays up past midnight
        if h >= sleep and h < wake:
            return "low"

    # First hour after waking → medium (warming up)
    if wake <= h < wake + 1:
        return "medium"

    # 1-2h after wake → high (peak)
    if wake + 1 <= h < wake + 2:
        return "high"

    # Work hours
    if work_start is not None and work_end is not None:
        mid_work = work_start + (work_end - work_start) // 2
        if work_start <= h < mid_work:
            return "high"
        if mid_work <= h < work_end:
            return "medium"
        # First hour after work → low (decompression)
        if work_end <= h < work_end + 1:
            return "low"

    # 2h before sleep → low
    if sleep - 2 <= h < sleep:
        return "low"

    # Evening second wind
    if work_end and h >= work_end + 1:
        return "medium"

    return "medium"


def needs_break(user_state: dict) -> Optional[dict]:
    """Check if user needs a break. Returns break suggestion or None."""
    mins = user_state.get("work_minutes_since_break", 0)
    if mins >= 60:
        return {
            "type": "enforced",
            "message": "You've been working for over an hour. Take a 10-minute break.",
            "duration_minutes": 10,
        }
    elif mins >= 45:
        return {
            "type": "suggested",
            "message": "Good stretch of focus! A 5-minute break could help.",
            "duration_minutes": 5,
        }
    return None


# ── System Maturity ───────────────────────────────────────────────

async def get_system_maturity(db) -> dict:
    """Compute system maturity level based on usage history.

    Levels:
    - cold (0-2 completions): minimal features, gentle start
    - warming (3-9): basic scheduling active
    - stable (10-24): full ADHD rules engaged
    - mature (25+): advanced features (strategic scoring, interventions)
    """
    row = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM task_history WHERE event = 'completed'"
    )
    count = row[0]["cnt"] if row else 0

    if count < 3:
        level = "cold"
    elif count < 10:
        level = "warming"
    elif count < 25:
        level = "stable"
    else:
        level = "mature"

    return {"level": level, "completions": count}


# ── ADHD-Aware Task Scoring ──────────────────────────────────────

def score_task(item: dict, user_state: dict, goal_ids: set = None) -> float:
    """
    ADHD-aware scoring function:
    score = priority_weight + energy_match + dopamine_alignment - friction_penalty
            + momentum_bonus + avoidance_adj + goal_alignment + confidence_damping
    """
    # 1. Priority weight (0-4 based on layer)
    priority_weight = LAYER_WEIGHT.get(item.get("layer", "technical"), 1.0)

    # Boost tasks already marked as next/doing
    if item.get("status") == "doing":
        priority_weight += 1.5
    elif item.get("status") == "next":
        priority_weight += 0.5

    # 2. Energy match (-2 to +2)
    energy_match = _compute_energy_match(item, user_state)

    # 3. Dopamine alignment (0-2)
    dopamine_alignment = _compute_dopamine_alignment(item, user_state)

    # 4. Friction penalty (0-3)
    friction_penalty = _compute_friction_penalty(item, user_state)

    # 5. Momentum bonus (0-2)
    momentum_bonus = _compute_momentum_bonus(item, user_state)

    # 6. Avoidance: category-aware penalty (replaces blanket penalty)
    skip_count = item.get("skip_count", 0)
    dominant_reason = item.get("dominant_skip_reason", "")
    avoidance_adj = _compute_avoidance_adj(skip_count, dominant_reason)

    # 7. Goal alignment: boost tasks linked to active goals
    goal_alignment = 0.0
    if goal_ids and item.get("goal_id") and item["goal_id"] in goal_ids:
        goal_alignment = 1.0

    # 8. Confidence damping: when confidence is low, compress differences
    confidence = user_state.get("confidence", 0.5)
    raw_score = (priority_weight + energy_match + dopamine_alignment
                 - friction_penalty + momentum_bonus + avoidance_adj + goal_alignment)

    # Thinking convergence: penalize thinking tasks near their time budget
    if item.get("type") == "thinking":
        budget = item.get("thinking_time_budget_minutes", 60) or 60
        spent = item.get("thinking_time_spent", 0) or 0
        ratio = spent / budget if budget > 0 else 0
        if ratio >= 1.0:
            raw_score -= 3.0  # force escalation
        elif ratio >= 0.75:
            raw_score -= 1.0  # gentle push

    # Dampen towards mean when confidence is low
    mean_score = 3.0  # approximate center
    damped_score = mean_score + (raw_score - mean_score) * confidence

    return round(damped_score, 2)


def _compute_avoidance_adj(skip_count: int, dominant_reason: str) -> float:
    """Category-aware avoidance scoring."""
    if skip_count == 0:
        return 0.0

    base = SKIP_CATEGORIES.get(dominant_reason, {}).get("weight", -0.3)

    if skip_count >= 3:
        return base * 2.0  # strongly penalized
    elif skip_count >= 2:
        return base
    return 0.0


def _compute_energy_match(item: dict, user_state: dict) -> float:
    """How well the task's energy demand matches user's current energy."""
    user_energy = ENERGY_LEVEL.get(user_state.get("energy", "medium"), 2)
    task_energy = ENERGY_LEVEL.get(item.get("energy_required", "medium"), 2)
    task_cognitive = COGNITIVE_LEVEL.get(item.get("cognitive_load", "medium"), 2)

    # The ideal: task demand ≤ user energy
    demand = max(task_energy, task_cognitive)  # effective demand
    diff = user_energy - demand

    if diff >= 0:
        return 1.0 + (0.5 if diff == 0 else 0)  # perfect match is best
    else:
        return diff * 1.5  # penalty for over-demand


def _compute_dopamine_alignment(item: dict, user_state: dict) -> float:
    """Score based on dopamine profile matching current momentum/state."""
    profile = item.get("dopamine_profile", "neutral")
    momentum = user_state.get("momentum", "none")

    if momentum == "none":
        # Need a quick win to start
        if profile == "quick_reward":
            return 2.0
        elif profile == "neutral":
            return 0.5
        else:
            return -0.5  # delayed reward is hard to start with
    elif momentum == "building":
        # Transitioning — neutral or quick reward keeps it going
        if profile == "quick_reward":
            return 1.5
        elif profile == "neutral":
            return 1.0
        else:
            return 0.5  # can handle delayed now
    else:  # high momentum
        # Can tackle anything, but delayed reward tasks finally viable
        if profile == "delayed_reward":
            return 1.5
        elif profile == "neutral":
            return 1.0
        else:
            return 0.8


def _compute_friction_penalty(item: dict, user_state: dict) -> float:
    """Higher friction = harder to start, especially with low momentum/energy."""
    friction = FRICTION_LEVEL.get(item.get("initiation_friction", "medium"), 2)
    momentum = user_state.get("momentum", "none")
    focus = user_state.get("focus", "normal")

    penalty = friction * 0.5  # base

    # Friction hurts more when momentum is low
    if momentum == "none":
        penalty *= 1.5
    elif momentum == "building":
        penalty *= 1.0
    else:
        penalty *= 0.6  # high momentum overcomes friction

    # Scattered focus makes friction worse
    if focus == "scattered":
        penalty *= 1.3

    return round(penalty, 2)


def _compute_momentum_bonus(item: dict, user_state: dict) -> float:
    """Bonus for tasks that maintain/build momentum."""
    momentum = user_state.get("momentum", "none")
    duration = item.get("duration_minutes", 30)
    visibility = item.get("completion_visibility", "visible")

    bonus = 0.0

    # Short tasks build momentum
    if duration <= 20:
        bonus += 0.5
    elif duration <= 30:
        bonus += 0.25

    # Visible completion boosts dopamine
    if visibility == "visible":
        bonus += 0.5

    # When momentum is high, longer/harder tasks become viable
    if momentum == "high":
        bonus += 0.5

    return bonus


# ── Selection Rules ───────────────────────────────────────────────

def select_next_task(
    items: list[dict],
    user_state: dict,
    completed_clusters: set[str] = None,
    maturity_level: str = "stable",
    active_goal_ids: set = None,
) -> dict:
    """Apply ADHD scheduling rules to select the best next task.

    Rules (gated by maturity):
    Always:  Start Bias, Energy Matching
    warming: + Momentum Mode, Dopamine Sequencing
    stable:  + Anti-Avoidance, Thinking Task Rules
    mature:  + Goal Alignment, Interventions, Strategic Scoring

    Returns: {
        selected: item,
        reasoning: str,
        recovery: optional low-effort task,
        sequence: [up to 3 upcoming],
        anti_loop_warning: optional str
    }
    """
    if not items:
        return {"selected": None, "reasoning": "No tasks available.", "recovery": None, "sequence": []}

    momentum = user_state.get("momentum", "none")
    energy = user_state.get("energy", "medium")
    focus = user_state.get("focus", "normal")
    tod = user_state.get("time_of_day", "afternoon")
    circadian = CIRCADIAN_MAP.get(tod, CIRCADIAN_MAP["afternoon"])
    goal_ids = active_goal_ids or set()

    # Separate thinking tasks from regular tasks
    thinking_tasks = [i for i in items if i.get("type") == "thinking"]
    regular_tasks = [i for i in items if i.get("type") != "thinking"]

    # Anti-loop check: flag thinking tasks revisited too many times
    anti_loop_warning = None
    for t in thinking_tasks:
        if t.get("revisit_count", 0) >= 3:
            anti_loop_warning = (
                f"'{t['content']}' has been revisited {t['revisit_count']} times. "
                f"Consider: force a decision, discard it, or archive for later."
            )

    # RULE 6: Thinking Task Eligibility
    # Only offer thinking tasks when: energy=high, morning/afternoon, momentum != none, max 1 at a time
    thinking_eligible = (
        energy == "high"
        and tod in ("morning", "afternoon")
        and momentum != "none"
        and focus != "scattered"
    )

    # Check if a thinking task is already in "doing" status
    active_thinking = any(
        i.get("type") == "thinking" and i.get("status") == "doing" for i in items
    )
    if active_thinking:
        thinking_eligible = False

    # Score all items
    scored = []
    for item in items:
        # Skip thinking tasks if not eligible (stable+ only)
        if item.get("type") == "thinking" and not thinking_eligible:
            if maturity_level in ("stable", "mature"):
                continue
        s = score_task(item, user_state, goal_ids=goal_ids)

        # Thinking task scoring adjustments
        if item.get("type") == "thinking":
            # Bonus for peak conditions
            if tod == "morning" and energy == "high":
                s += 1.5
            # Penalty for anti-loop items
            revisits = item.get("revisit_count", 0)
            if revisits >= 2:
                s -= revisits * 0.5

        scored.append((s, item))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        # If we filtered out everything (all thinking, not eligible), fall back
        scored = [(score_task(i, user_state), i) for i in items]
        scored.sort(key=lambda x: x[0], reverse=True)

    # RULE 1: Start Bias — when momentum is none, heavily filter (always active)
    if momentum == "none":
        starters = [
            (s, i) for s, i in scored
            if i.get("initiation_friction", "medium") in ("low", "medium")
            and i.get("duration_minutes", 30) <= 25
            and not i.get("resistance_flag")
        ]
        if starters:
            scored = starters

    # RULE 3: Anti-Avoidance — skip resistance-flagged items (stable+ only)
    if maturity_level in ("stable", "mature") and scored and scored[0][1].get("resistance_flag") and len(scored) > 1:
        if scored[0][0] - scored[1][0] < 2.0:
            non_resistant = [(s, i) for s, i in scored if not i.get("resistance_flag")]
            if non_resistant:
                scored = non_resistant

    # RULE 4: Energy Matching — if user energy is low, cap task demand (always active)
    if energy == "low":
        low_demand = [
            (s, i) for s, i in scored
            if COGNITIVE_LEVEL.get(i.get("cognitive_load", "medium"), 2) <= 2
            and ENERGY_LEVEL.get(i.get("energy_required", "medium"), 2) <= 2
        ]
        if low_demand:
            scored = low_demand

    selected = scored[0][1] if scored else items[0]

    # Build reasoning
    reasoning = _build_reasoning(selected, user_state, circadian)

    # Find recovery task (low-effort, different cluster)
    recovery = _find_recovery_task(items, selected, user_state)

    # Build sequence: up to 3 upcoming (including selected)
    sequence = [i for _, i in scored[:3]]

    # RULE 7: Dopamine Sandwich for thinking tasks
    # If selected is a thinking task, prepend a quick win and append an execution task
    dopamine_sandwich = None
    if selected.get("type") == "thinking":
        quick_win = _find_quick_win(regular_tasks, selected)
        exec_after = _find_execution_followup(regular_tasks, selected)
        if quick_win or exec_after:
            dopamine_sandwich = {
                "before": quick_win,
                "after": exec_after,
            }
            reasoning = "🧠 Thinking task with dopamine sandwich: " + reasoning

    result = {
        "selected": selected,
        "reasoning": reasoning,
        "recovery": recovery,
        "sequence": sequence,
    }
    if anti_loop_warning:
        result["anti_loop_warning"] = anti_loop_warning
    if dopamine_sandwich:
        result["dopamine_sandwich"] = dopamine_sandwich
    return result


def _build_reasoning(task: dict, user_state: dict, circadian: dict) -> str:
    """Generate human-readable reasoning for why this task was selected."""
    parts = []
    momentum = user_state.get("momentum", "none")
    energy = user_state.get("energy", "medium")
    tod = user_state.get("time_of_day", "afternoon")

    # Momentum context
    if momentum == "none":
        parts.append(f"Starting with a low-friction task to build momentum")
    elif momentum == "building":
        parts.append(f"Momentum building — stepping up to a meatier task")
    else:
        parts.append(f"Strong momentum — tackling a high-impact task")

    # Energy context
    task_load = task.get("cognitive_load", "medium")
    if energy == "low" and task_load == "low":
        parts.append(f"matched to your current energy level")
    elif energy == "high" and task_load == "high":
        parts.append(f"great time for deep work while energy is high")

    # Dopamine context
    dp = task.get("dopamine_profile", "neutral")
    if dp == "quick_reward":
        parts.append(f"quick visible progress to fuel your drive")
    elif dp == "delayed_reward" and momentum == "high":
        parts.append(f"you have the momentum to tackle something meaningful")

    # Duration context
    dur = task.get("duration_minutes", 30)
    if dur <= 15:
        parts.append(f"just {dur} minutes")

    cluster = task.get("cluster", "")
    result = ". ".join(parts) + "."
    if cluster:
        result = f"[{cluster}] " + result

    return result


def _find_recovery_task(
    items: list[dict],
    selected: dict,
    user_state: dict,
) -> Optional[dict]:
    """Find a low-effort recovery task from a different cluster."""
    sel_cluster = selected.get("cluster", "")
    candidates = [
        i for i in items
        if i["id"] != selected["id"]
        and i.get("cognitive_load", "medium") == "low"
        and i.get("initiation_friction", "medium") == "low"
        and i.get("duration_minutes", 30) <= 15
        and i.get("cluster", "") != sel_cluster
    ]
    if candidates:
        return candidates[0]
    # Fallback: any low-effort task
    fallback = [
        i for i in items
        if i["id"] != selected["id"]
        and i.get("cognitive_load", "medium") == "low"
        and i.get("duration_minutes", 30) <= 20
    ]
    return fallback[0] if fallback else None


# ── Avoidance Handling ────────────────────────────────────────────

def handle_skip(item: dict, skip_category: str = "not_now") -> dict:
    """Process a skipped task with categorized reason.

    Returns updated fields, guidance, and category-specific interventions.
    """
    skip_count = item.get("skip_count", 0) + 1
    resistance = item.get("resistance_flag", False) or (skip_count >= 2)

    # Validate category
    if skip_category not in SKIP_CATEGORIES:
        skip_category = "not_now"

    result = {
        "skip_count": skip_count,
        "resistance_flag": resistance,
        "skip_category": skip_category,
        "dominant_skip_reason": skip_category,
    }

    # Category-specific interventions
    intervention = get_resistance_intervention(item, skip_count, skip_category)
    if intervention:
        result["guidance"] = intervention["type"]
        result["suggestion"] = intervention["message"]
    elif skip_count == 1:
        result["guidance"] = "normal_skip"
        result["suggestion"] = None

    return result


def get_resistance_intervention(
    item: dict, skip_count: int, category: str
) -> Optional[dict]:
    """Return a targeted intervention based on skip category and count."""
    if skip_count < 2:
        return None

    is_thinking = item.get("type") == "thinking"
    content_short = (item.get("content", "")[:40] + "...") if len(item.get("content", "")) > 40 else item.get("content", "")

    interventions = {
        "too_hard": {
            "type": "decompose",
            "message": (
                f"'{content_short}' feels too hard. "
                f"Try: break into a 10-minute starter step, or lower the bar — "
                f"what's the smallest slice you could do right now?"
            ),
        },
        "unclear": {
            "type": "clarify",
            "message": (
                f"'{content_short}' is unclear. "
                f"Try: spend 5 minutes just writing down what you think the first step is. "
                f"Or rephrase it as a question to answer."
            ),
        },
        "boring": {
            "type": "gamify",
            "message": (
                f"'{content_short}' feels boring. "
                f"Try: set a 15-minute timer and race yourself. "
                f"Or pair it with music/a podcast."
            ),
        },
        "anxious": {
            "type": "comfort",
            "message": (
                f"'{content_short}' makes you anxious. "
                f"That's okay. Try: imagine the worst realistic outcome — is it survivable? "
                f"Or just do the first 2 minutes and give yourself permission to stop."
            ),
        },
        "not_now": {
            "type": "reschedule" if skip_count < 3 else "avoidance_detected",
            "message": (
                f"You've deferred '{content_short}' {skip_count} times. "
                f"Is this actually important? If yes, when would be the right time?"
            ),
        },
    }

    if is_thinking and category in ("too_hard", "unclear"):
        return {
            "type": "reduce_scope",
            "message": (
                f"This thinking task has been skipped {skip_count} times. "
                f"Try: 15 min, just 3 bullet points. "
                f"Or convert it to a concrete action step."
            ),
        }

    return interventions.get(category)


def _find_quick_win(regular_tasks: list[dict], exclude: dict) -> Optional[dict]:
    """Find a quick-win task for dopamine sandwich (before a thinking task)."""
    candidates = [
        i for i in regular_tasks
        if i["id"] != exclude["id"]
        and i.get("duration_minutes", 30) <= 15
        and i.get("dopamine_profile") == "quick_reward"
        and i.get("initiation_friction", "medium") == "low"
        and i.get("status") in ("next", "inbox")
    ]
    return candidates[0] if candidates else None


def _find_execution_followup(regular_tasks: list[dict], exclude: dict) -> Optional[dict]:
    """Find a concrete execution task to do after a thinking task (dopamine reward)."""
    candidates = [
        i for i in regular_tasks
        if i["id"] != exclude["id"]
        and i.get("completion_visibility") == "visible"
        and i.get("cognitive_load", "medium") in ("low", "medium")
        and i.get("status") in ("next", "inbox")
    ]
    return candidates[0] if candidates else None
