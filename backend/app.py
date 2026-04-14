import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()

logger = logging.getLogger(__name__)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from backend.database import init_db, get_db
from backend.ai import parse_input, transcribe_audio, expand_thinking_output, onboarding_interview_step, get_onboarding_first_question
from backend.priority import compute_priority
from backend.planner import (
    needs_approval,
    determine_replan_action,
    run_full_replan,
    run_partial_replan,
)
from backend.scheduler import (
    infer_user_state,
    needs_break,
    select_next_task,
    handle_skip,
    get_system_maturity,
    SKIP_CATEGORIES,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Cognitive Execution System", lifespan=lifespan)


# ── Pydantic models ──────────────────────────────────────────────


class TextInput(BaseModel):
    text: str


class ApproveInput(BaseModel):
    inbox_id: int
    approved: bool


class CompleteInput(BaseModel):
    item_id: int
    elapsed_seconds: Optional[int] = None


class OverrideInput(BaseModel):
    item_id: int
    reason: str
    skip_category: Optional[str] = "not_now"


class UpdateItemInput(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None
    cluster: Optional[str] = None
    energy_required: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: Optional[float] = None
    track_id: Optional[int] = None


class ExpandInput(BaseModel):
    item_id: int
    notes: str


class SelectInput(BaseModel):
    item_id: int


class TrackInput(BaseModel):
    name: str
    color: Optional[str] = "#4f9eff"
    icon: Optional[str] = "📁"
    time_available: Optional[str] = None
    allow_cross_track: Optional[bool] = False


class TrackUpdateInput(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    time_available: Optional[str] = None
    allow_cross_track: Optional[bool] = None


class SetActiveTrackInput(BaseModel):
    track_id: Optional[int] = None


class OnboardingInput(BaseModel):
    message: str


class OnboardingAudioInput(BaseModel):
    pass  # Audio handled via UploadFile


class CheckinInput(BaseModel):
    energy: int  # 1-5
    focus: int   # 1-5
    mood: Optional[str] = None


class SettingsInput(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


# ── Onboarding ───────────────────────────────────────────────────


@app.get("/onboarding/status")
async def onboarding_status():
    """Check if onboarding has been completed."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'onboarding_complete'"
        )
        complete = row and row[0]["value"] == "1"
        routine = None
        if complete:
            persona_row = await db.execute_fetchall(
                "SELECT value FROM user_persona WHERE key = 'routine'"
            )
            if persona_row:
                routine = json.loads(persona_row[0]["value"])
        return {"onboarding_complete": complete, "routine": routine}
    finally:
        await db.close()


@app.get("/onboarding/start")
async def onboarding_start():
    """Start the adaptive onboarding interview. Returns the first question."""
    db = await get_db()
    try:
        # Clear any previous onboarding messages (restart)
        await db.execute("DELETE FROM onboarding_messages")
        await db.commit()

        result = await get_onboarding_first_question()
        message = result.get("message", "Tell me a bit about yourself — what does a typical day look like for you?")

        # Store the assistant's first message
        await db.execute(
            "INSERT INTO onboarding_messages (role, content) VALUES (?, ?)",
            ("assistant", message),
        )
        await db.commit()

        return {"message": message, "done": False}
    finally:
        await db.close()


@app.post("/onboarding/message")
async def onboarding_message(body: OnboardingInput):
    """Send a message in the onboarding interview. Returns AI response with extracted data."""
    user_msg = body.message.strip()
    if not user_msg:
        raise HTTPException(400, "Empty message")

    db = await get_db()
    try:
        # Store user message
        await db.execute(
            "INSERT INTO onboarding_messages (role, content) VALUES (?, ?)",
            ("user", user_msg),
        )

        # Load conversation history
        rows = await db.execute_fetchall(
            "SELECT role, content FROM onboarding_messages ORDER BY id ASC"
        )
        history = [{"role": r["role"], "content": r["content"]} for r in rows]

        # Run AI interview step
        try:
            result = await onboarding_interview_step(history[:-1], user_msg)
        except RuntimeError as e:
            raise HTTPException(502, str(e))

        ai_message = result.get("message", "")
        extracted = result.get("extracted", {})
        done = result.get("done", False)

        # Store AI response
        await db.execute(
            "INSERT INTO onboarding_messages (role, content, extracted_data) VALUES (?, ?, ?)",
            ("assistant", ai_message, json.dumps(extracted)),
        )

        # Process extracted data incrementally
        await _process_onboarding_extraction(db, extracted)

        # If interview is done, finalize onboarding
        if done:
            await _finalize_onboarding(db)

        await db.commit()

        return {
            "message": ai_message,
            "done": done,
            "extracted": extracted,
        }
    finally:
        await db.close()


@app.post("/onboarding/audio")
async def onboarding_audio(file: UploadFile = File(...)):
    """Send a voice message in the onboarding interview."""
    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio")

    try:
        text = await transcribe_audio(audio_bytes, file.filename or "audio.webm")
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not text.strip():
        raise HTTPException(400, "Could not transcribe audio")

    # Delegate to the text message handler
    body = OnboardingInput(message=text)
    result = await onboarding_message(body)
    result["transcript"] = text
    return result


async def _process_onboarding_extraction(db, extracted: dict):
    """Process incrementally extracted onboarding data into user_persona."""
    if not extracted:
        return

    # Routine
    routine = extracted.get("routine")
    if routine and isinstance(routine, dict) and any(v for k, v in routine.items() if k != "has_routine"):
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("routine", json.dumps(routine)),
        )

    # Role / user context
    role = extracted.get("role")
    if role:
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("user_context", json.dumps({"role": role, "description": extracted.get("user_context", "")})),
        )

    # Energy hints
    hints = extracted.get("energy_hints")
    if hints and isinstance(hints, list) and len(hints) > 0:
        # Merge with existing hints
        existing = await db.execute_fetchall(
            "SELECT value FROM user_persona WHERE key = 'energy_overrides'"
        )
        current = []
        if existing and existing[0]["value"]:
            try:
                current = json.loads(existing[0]["value"])
            except (json.JSONDecodeError, TypeError):
                current = []
        current.extend(hints)
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("energy_overrides", json.dumps(current)),
        )

    # Challenge profile
    challenges = extracted.get("challenge_profile")
    if challenges and isinstance(challenges, list) and len(challenges) > 0:
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("challenge_profile", json.dumps(challenges)),
        )

    # Avoidance patterns
    avoidance = extracted.get("avoidance_patterns")
    if avoidance and isinstance(avoidance, list) and len(avoidance) > 0:
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("avoidance_domains", json.dumps(avoidance)),
        )

    # Goals
    goals = extracted.get("goals")
    if goals and isinstance(goals, list):
        for g in goals:
            title = g.get("title", "").strip()
            if not title:
                continue
            # Avoid duplicate goals
            existing_goal = await db.execute_fetchall(
                "SELECT id FROM goals WHERE summary = ?", (title,)
            )
            if not existing_goal:
                await db.execute(
                    "INSERT INTO goals (summary, status, priority_rank) VALUES (?, 'active', ?)",
                    (title, 1 if g.get("urgency") == "this_week" else 0),
                )

    # Tasks — pre-seed into the task database
    tasks = extracted.get("tasks")
    if tasks and isinstance(tasks, list):
        for t in tasks:
            content = t.get("content", "").strip()
            if not content or len(content) < 3:
                continue
            cluster = t.get("cluster", "general")
            priority_val = {"high": 8.0, "medium": 5.0, "low": 2.0}.get(
                t.get("estimated_priority", "medium"), 5.0
            )
            # Run through full AI parser for proper ADHD metadata
            try:
                parsed = await parse_input(content)
                parsed_tasks = parsed.get("tasks", [])
                goal_text = parsed.get("goal", "")
                if parsed_tasks:
                    await _insert_task_batch(db, parsed_tasks, goal_text)
            except Exception:
                # Fallback: insert directly with minimal metadata
                await db.execute(
                    """INSERT INTO items (content, layer, type, scope, cluster, status, priority,
                                          energy_required, duration_minutes, cognitive_load,
                                          dopamine_profile, initiation_friction, completion_visibility,
                                          execution_class, complexity_score, sort_order)
                       VALUES (?, 'operational', 'task', 'local', ?, 'inbox', ?, 'medium', 20,
                               'medium', 'neutral', 'medium', 'visible', 'linear', 5.0, 0)""",
                    (content, cluster, priority_val),
                )


async def _finalize_onboarding(db):
    """Mark onboarding as complete and store the full transcript."""
    await db.execute(
        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
        ("onboarding_complete", "1"),
    )

    # Store the full transcript for future AI context
    rows = await db.execute_fetchall(
        "SELECT role, content FROM onboarding_messages ORDER BY id ASC"
    )
    transcript = "\n".join(f"{r['role']}: {r['content']}" for r in rows)
    await db.execute(
        "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        ("onboarding_transcript", json.dumps(transcript)),
    )

    # Ensure routine exists (fallback to defaults if not extracted)
    routine_row = await db.execute_fetchall(
        "SELECT value FROM user_persona WHERE key = 'routine'"
    )
    if not routine_row:
        await db.execute(
            "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("routine", json.dumps({"has_routine": False})),
        )


# ── Check-in ─────────────────────────────────────────────────────


@app.post("/checkin")
async def submit_checkin(body: CheckinInput):
    """Record a quick energy/focus check-in. Used for state inference."""
    energy = max(1, min(5, body.energy))
    focus = max(1, min(5, body.focus))

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO checkins (energy, focus, mood) VALUES (?, ?, ?)",
            (energy, focus, body.mood),
        )
        await db.commit()
        energy_label = "low" if energy <= 2 else ("high" if energy >= 4 else "medium")
        focus_label = "scattered" if focus <= 2 else ("locked_in" if focus >= 4 else "normal")
        return {
            "status": "ok",
            "energy": energy_label,
            "focus": focus_label,
        }
    finally:
        await db.close()


@app.get("/checkin/latest")
async def get_latest_checkin():
    """Get the most recent check-in if within 2 hours."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            """SELECT energy, focus, mood, created_at
               FROM checkins
               WHERE created_at > datetime('now', '-2 hours')
               ORDER BY created_at DESC LIMIT 1"""
        )
        if row:
            r = dict(row[0])
            return {"has_recent": True, **r}
        return {"has_recent": False}
    finally:
        await db.close()


@app.get("/skip-categories")
async def get_skip_categories():
    """Return available skip reason categories for the frontend."""
    return {"categories": [
        {"key": k, **v} for k, v in SKIP_CATEGORIES.items()
    ]}


# ── Goals CRUD ───────────────────────────────────────────────────


class GoalInput(BaseModel):
    summary: str
    description: Optional[str] = None
    cluster: Optional[str] = None
    target_date: Optional[str] = None
    priority_rank: Optional[int] = 0


class GoalUpdateInput(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority_rank: Optional[int] = None
    target_date: Optional[str] = None


@app.get("/goals")
async def get_goals():
    """Return all active goals with linked task counts."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT g.*,
                      (SELECT COUNT(*) FROM items WHERE goal_id = g.id AND status != 'done') AS pending_tasks,
                      (SELECT COUNT(*) FROM items WHERE goal_id = g.id AND status = 'done') AS done_tasks
               FROM goals g
               WHERE g.status = 'active'
               ORDER BY g.priority_rank DESC, g.created_at ASC"""
        )
        return {"goals": [dict(r) for r in rows]}
    finally:
        await db.close()


@app.post("/goals")
async def create_goal(body: GoalInput):
    """Create a new goal."""
    if not body.summary.strip():
        raise HTTPException(400, "Goal summary is required")
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO goals (summary, description, cluster, target_date, status, priority_rank)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (body.summary.strip(), body.description, body.cluster, body.target_date, body.priority_rank or 0),
        )
        await db.commit()
        return {"status": "created", "goal_id": cursor.lastrowid}
    finally:
        await db.close()


@app.patch("/goals/{goal_id}")
async def update_goal(goal_id: int, body: GoalUpdateInput):
    """Update a goal."""
    db = await get_db()
    try:
        row = await db.execute_fetchall("SELECT * FROM goals WHERE id = ?", (goal_id,))
        if not row:
            raise HTTPException(404, "Goal not found")

        updates = {}
        if body.summary is not None:
            updates["summary"] = body.summary.strip()
        if body.description is not None:
            updates["description"] = body.description
        if body.status is not None:
            if body.status not in ("active", "achieved", "archived"):
                raise HTTPException(400, "Invalid goal status")
            updates["status"] = body.status
        if body.priority_rank is not None:
            updates["priority_rank"] = body.priority_rank
        if body.target_date is not None:
            updates["target_date"] = body.target_date

        if not updates:
            raise HTTPException(400, "No fields to update")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [goal_id]
        await db.execute(f"UPDATE goals SET {set_clause} WHERE id = ?", values)
        await db.commit()
        return {"status": "updated", "goal_id": goal_id}
    finally:
        await db.close()


@app.delete("/goals/{goal_id}")
async def delete_goal(goal_id: int):
    """Archive a goal (soft delete)."""
    db = await get_db()
    try:
        row = await db.execute_fetchall("SELECT * FROM goals WHERE id = ?", (goal_id,))
        if not row:
            raise HTTPException(404, "Goal not found")
        await db.execute("UPDATE goals SET status = 'archived' WHERE id = ?", (goal_id,))
        await db.commit()
        return {"status": "archived", "goal_id": goal_id}
    finally:
        await db.close()


# ── Daily Intention + Weekly Review ──────────────────────────────


@app.get("/daily/intention")
async def get_daily_intention():
    """Return today's intended focus goal and suggested first task."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'daily_intention_date'"
        )
        today = datetime.now().strftime("%Y-%m-%d")

        intention = None
        if row and row[0]["value"] == today:
            intent_row = await db.execute_fetchall(
                "SELECT value FROM system_state WHERE key = 'daily_intention'"
            )
            if intent_row:
                intention = json.loads(intent_row[0]["value"])

        goals = await db.execute_fetchall(
            """SELECT g.id, g.summary,
                      (SELECT COUNT(*) FROM items WHERE goal_id = g.id AND status != 'done') AS pending
               FROM goals g
               WHERE g.status = 'active'
               ORDER BY g.priority_rank DESC LIMIT 3"""
        )

        return {
            "date": today,
            "intention": intention,
            "top_goals": [dict(g) for g in goals],
        }
    finally:
        await db.close()


class IntentionInput(BaseModel):
    goal_id: Optional[int] = None
    focus_text: Optional[str] = None


@app.post("/daily/intention")
async def set_daily_intention(body: IntentionInput):
    """Set today's focus intention."""
    db = await get_db()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        intention = {
            "goal_id": body.goal_id,
            "focus_text": body.focus_text,
        }
        await db.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            ("daily_intention", json.dumps(intention)),
        )
        await db.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            ("daily_intention_date", today),
        )
        await db.commit()
        return {"status": "ok", "intention": intention}
    finally:
        await db.close()


@app.get("/review/weekly")
async def get_weekly_review():
    """Return a comprehensive weekly review with goal progress and patterns."""
    db = await get_db()
    try:
        completed = await db.execute_fetchall(
            """SELECT i.content, i.cluster, i.goal_id, i.duration_minutes, i.cognitive_load,
                      th.elapsed_seconds, g.summary as goal_summary
               FROM task_history th
               JOIN items i ON th.item_id = i.id
               LEFT JOIN goals g ON i.goal_id = g.id
               WHERE th.event = 'completed'
                 AND th.created_at >= date('now', 'weekday 0', '-6 days')
               ORDER BY th.created_at DESC"""
        )

        skipped = await db.execute_fetchall(
            """SELECT i.content, i.cluster, th.skip_reason_category
               FROM task_history th
               JOIN items i ON th.item_id = i.id
               WHERE th.event = 'skipped'
                 AND th.created_at >= date('now', 'weekday 0', '-6 days')
               ORDER BY th.created_at DESC"""
        )

        goals = await db.execute_fetchall(
            """SELECT g.id, g.summary, g.status, g.priority_rank,
                      (SELECT COUNT(*) FROM items WHERE goal_id = g.id AND status = 'done') AS done_tasks,
                      (SELECT COUNT(*) FROM items WHERE goal_id = g.id AND status != 'done') AS pending_tasks
               FROM goals g
               WHERE g.status = 'active'
               ORDER BY g.priority_rank DESC"""
        )

        skip_categories = {}
        for s in skipped:
            cat = dict(s).get("skip_reason_category", "unknown")
            skip_categories[cat] = skip_categories.get(cat, 0) + 1

        completed_list = [dict(c) for c in completed]
        goal_tasks = [c for c in completed_list if c.get("goal_id")]
        non_goal_tasks = [c for c in completed_list if not c.get("goal_id")]

        productivity_trap = False
        trap_message = None
        if len(completed_list) >= 5 and len(goal_tasks) < 2:
            productivity_trap = True
            trap_message = (
                f"You completed {len(completed_list)} tasks this week, but only "
                f"{len(goal_tasks)} were linked to your goals. Consider focusing "
                f"more on goal-aligned work."
            )

        return {
            "completed": completed_list,
            "completed_count": len(completed_list),
            "skipped_count": len(skipped),
            "skip_categories": skip_categories,
            "goals": [dict(g) for g in goals],
            "goal_task_count": len(goal_tasks),
            "non_goal_task_count": len(non_goal_tasks),
            "productivity_trap": productivity_trap,
            "trap_message": trap_message,
        }
    finally:
        await db.close()


# ── Settings ─────────────────────────────────────────────────────

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Allowed models (whitelist to prevent injection)
_ALLOWED_MODELS = {
    # OpenAI models
    "gpt-5.3", "gpt-5.3-mini",
    "o4-mini", "o3",
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-4o", "gpt-4o-mini",
    # Gemini models
    "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-2.0-flash", "gemini-2.0-flash-lite",
}


@app.get("/settings")
async def get_settings():
    """Return current model and masked API keys."""
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    # Mask API key: show first 5 and last 4 chars
    if len(api_key) > 12:
        masked = api_key[:5] + "..." + api_key[-4:]
    elif api_key:
        masked = api_key[:3] + "..."
    else:
        masked = ""
    # Mask Gemini key
    if len(gemini_key) > 12:
        gemini_masked = gemini_key[:5] + "..." + gemini_key[-4:]
    elif gemini_key:
        gemini_masked = gemini_key[:3] + "..."
    else:
        gemini_masked = ""
    return {"model": model, "api_key_masked": masked, "gemini_api_key_masked": gemini_masked}


@app.post("/settings")
async def update_settings(body: SettingsInput):
    """Update model and/or API keys in .env and live environment."""
    if body.model is not None:
        if body.model not in _ALLOWED_MODELS:
            raise HTTPException(400, f"Invalid model. Allowed: {', '.join(sorted(_ALLOWED_MODELS))}")
        os.environ["OPENAI_MODEL"] = body.model
        set_key(str(_ENV_PATH), "OPENAI_MODEL", body.model)

    if body.api_key is not None:
        key = body.api_key.strip()
        if not key:
            raise HTTPException(400, "API key cannot be empty")
        # Basic format validation for OpenAI keys
        if not re.match(r'^sk-[A-Za-z0-9_-]{20,}$', key):
            raise HTTPException(400, "Invalid OpenAI API key format")
        os.environ["OPENAI_API_KEY"] = key
        set_key(str(_ENV_PATH), "OPENAI_API_KEY", key)

    if body.gemini_api_key is not None:
        key = body.gemini_api_key.strip()
        if not key:
            raise HTTPException(400, "Gemini API key cannot be empty")
        if not re.match(r'^[A-Za-z0-9_-]{20,}$', key):
            raise HTTPException(400, "Invalid Gemini API key format")
        os.environ["GEMINI_API_KEY"] = key
        set_key(str(_ENV_PATH), "GEMINI_API_KEY", key)

    return {"status": "ok", "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini")}


# ── POST /ingest ─────────────────────────────────────────────────


@app.post("/ingest")
async def ingest_text(body: TextInput):
    """Ingest raw text, decompose into atomic tasks, route through approval gate."""
    raw = body.text.strip()
    if not raw:
        raise HTTPException(400, "Empty input")

    # Get existing context for smarter decomposition
    context = await _get_context_summary()
    try:
        parsed = await parse_input(raw, existing_context=context)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    parsed_json = json.dumps(parsed)

    tasks = parsed.get("tasks", [])
    goal_text = parsed.get("goal", "")
    existing_goal_id = parsed.get("existing_goal_id")

    # Check if any task needs approval
    needs_approval_flag = any(needs_approval(t) for t in tasks)

    db = await get_db()
    try:
        # Raw input dedup: reject if identical text was just submitted
        recent_dup = await _check_raw_input_duplicate(db, raw)
        if recent_dup:
            return {
                "status": "duplicate",
                "message": "This input was already submitted recently.",
            }

        if needs_approval_flag:
            cursor = await db.execute(
                "INSERT INTO inbox (raw_input, parsed_json, approved) VALUES (?, ?, 0)",
                (raw, parsed_json),
            )
            await db.commit()
            return {
                "status": "pending_approval",
                "inbox_id": cursor.lastrowid,
                "parsed": parsed,
                "task_count": len(tasks),
                "goal": goal_text,
            }

        # Auto-approved → insert all tasks (with per-task dedup)
        item_ids, skipped_dupes = await _insert_task_batch(db, tasks, goal_text, existing_goal_id=existing_goal_id)

        # Determine replan action from highest-scope task
        replan = "none"
        for t in tasks:
            r = determine_replan_action(t)
            if r == "full":
                replan = "full"
                break
            if r == "partial":
                replan = "partial"

        plan_result = None
        if replan == "full":
            try:
                plan_result = await run_full_replan()
            except Exception as e:
                logger.error("Full replan failed after ingest: %s", e)
        elif replan == "partial":
            clusters = set(t.get("cluster", "general") for t in tasks)
            for c in clusters:
                try:
                    plan_result = await run_partial_replan(c)
                except Exception as e:
                    logger.error("Partial replan failed (cluster=%s): %s", c, e)

        result = {
            "status": "accepted",
            "item_ids": item_ids,
            "parsed": parsed,
            "task_count": len(tasks),
            "goal": goal_text,
            "replan": replan,
            "plan": plan_result,
        }
        if skipped_dupes:
            result["duplicates_skipped"] = skipped_dupes
        return result
    finally:
        await db.close()


@app.post("/ingest/audio")
async def ingest_audio(file: UploadFile = File(...)):
    """Ingest audio → Whisper → decompose → route."""
    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(400, "Empty audio")

    try:
        text = await transcribe_audio(audio_bytes, file.filename or "audio.webm")
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not text.strip():
        raise HTTPException(400, "Could not transcribe audio")

    context = await _get_context_summary()
    try:
        parsed = await parse_input(text, existing_context=context)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    parsed_json = json.dumps(parsed)

    tasks = parsed.get("tasks", [])
    goal_text = parsed.get("goal", "")
    existing_goal_id = parsed.get("existing_goal_id")
    needs_approval_flag = any(needs_approval(t) for t in tasks)

    db = await get_db()
    try:
        if needs_approval_flag:
            cursor = await db.execute(
                "INSERT INTO inbox (raw_input, parsed_json, approved) VALUES (?, ?, 0)",
                (text, parsed_json),
            )
            await db.commit()
            return {
                "status": "pending_approval",
                "inbox_id": cursor.lastrowid,
                "parsed": parsed,
                "transcript": text,
                "task_count": len(tasks),
                "goal": goal_text,
            }

        item_ids, skipped_dupes = await _insert_task_batch(db, tasks, goal_text, existing_goal_id=existing_goal_id)

        replan = "none"
        for t in tasks:
            r = determine_replan_action(t)
            if r == "full":
                replan = "full"
                break
            if r == "partial":
                replan = "partial"

        plan_result = None
        if replan == "full":
            try:
                plan_result = await run_full_replan()
            except Exception as e:
                logger.error("Full replan failed after audio ingest: %s", e)
        elif replan == "partial":
            clusters = set(t.get("cluster", "general") for t in tasks)
            for c in clusters:
                try:
                    plan_result = await run_partial_replan(c)
                except Exception as e:
                    logger.error("Partial replan failed (cluster=%s): %s", c, e)

        result = {
            "status": "accepted",
            "item_ids": item_ids,
            "parsed": parsed,
            "transcript": text,
            "task_count": len(tasks),
            "goal": goal_text,
            "replan": replan,
            "plan": plan_result,
        }
        if skipped_dupes:
            result["duplicates_skipped"] = skipped_dupes
        return result
    finally:
        await db.close()


# ── POST /approve ────────────────────────────────────────────────


@app.post("/approve")
async def approve_item(body: ApproveInput):
    """Approve or reject an inbox item."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM inbox WHERE id = ?", (body.inbox_id,)
        )
        if not row:
            raise HTTPException(404, "Inbox item not found")

        inbox_item = dict(row[0])

        if not body.approved:
            await db.execute("DELETE FROM inbox WHERE id = ?", (body.inbox_id,))
            await db.commit()
            return {"status": "rejected", "inbox_id": body.inbox_id}

        parsed = json.loads(inbox_item["parsed_json"])
        tasks = parsed.get("tasks", [parsed])  # handle both old and new format
        goal_text = parsed.get("goal", "")
        existing_goal_id = parsed.get("existing_goal_id")

        item_ids, _ = await _insert_task_batch(db, tasks, goal_text, existing_goal_id=existing_goal_id)

        await db.execute(
            "UPDATE inbox SET approved = 1 WHERE id = ?", (body.inbox_id,)
        )
        await db.commit()

        replan = "none"
        for t in tasks:
            r = determine_replan_action(t)
            if r == "full":
                replan = "full"
                break
            if r == "partial":
                replan = "partial"

        plan_result = None
        if replan == "full":
            try:
                plan_result = await run_full_replan()
            except Exception as e:
                logger.error("Full replan failed after approve: %s", e)
        elif replan == "partial":
            clusters = set(t.get("cluster", "general") for t in tasks)
            for c in clusters:
                try:
                    plan_result = await run_partial_replan(c)
                except Exception as e:
                    logger.error("Partial replan failed (cluster=%s): %s", c, e)

        return {
            "status": "approved",
            "item_ids": item_ids,
            "task_count": len(item_ids),
            "replan": replan,
            "plan": plan_result,
        }
    finally:
        await db.close()


# ── GET /next ────────────────────────────────────────────────────


@app.get("/next")
async def get_next():
    """Return top 3 task options (or the active task if one is locked)."""
    db = await get_db()
    try:
        # Determine active track
        track_state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'active_track_id'"
        )
        active_track_id = None
        active_track = None
        if track_state and track_state[0]["value"]:
            active_track_id = int(track_state[0]["value"])
            track_row = await db.execute_fetchall(
                "SELECT * FROM tracks WHERE id = ?", (active_track_id,)
            )
            if track_row:
                active_track = dict(track_row[0])

        # Check active task lock — if a task is already "doing", return it directly
        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'current_active_task_id'"
        )
        active_id = state[0]["value"] if state and state[0]["value"] else None

        if active_id:
            active_row = await db.execute_fetchall(
                "SELECT * FROM items WHERE id = ?", (int(active_id),)
            )
            if active_row and dict(active_row[0])["status"] == "doing":
                now_item = dict(active_row[0])
                after = await _get_next_items(db, exclude_id=int(active_id), limit=2)
                result = {"active": True, **_format_execution_block(now_item, after)}
                if active_track:
                    result["active_track"] = {"id": active_track["id"], "name": active_track["name"], "color": active_track["color"], "icon": active_track["icon"]}
                return result

        # Build track filter clause
        # If a track is active, prioritize tasks from that track.
        # If the track allows cross-track, also include untracked tasks.
        track_filter = ""
        track_params: list = []
        if active_track_id and active_track:
            if active_track.get("allow_cross_track"):
                track_filter = "AND (track_id = ? OR track_id IS NULL)"
                track_params = [active_track_id]
            else:
                track_filter = "AND track_id = ?"
                track_params = [active_track_id]

        # Fetch candidate items with ADHD fields
        rows = await db.execute_fetchall(
            f"""SELECT id, content, layer, type, scope, cluster, status,
                      priority, energy_required, duration_minutes, sort_order,
                      cognitive_load, dopamine_profile, initiation_friction,
                      completion_visibility, skip_count, resistance_flag,
                      execution_class, expanded, source_idea_id,
                      thinking_objective, thinking_output_format, revisit_count,
                      track_id
               FROM items
               WHERE status IN ('next', 'inbox', 'backlog') {track_filter}
               ORDER BY priority DESC, sort_order ASC, created_at ASC
               LIMIT 30""",
            track_params,
        )
        items = [dict(r) for r in rows]
        if not items:
            # Check if there are wishful items to suggest
            wish_rows = await db.execute_fetchall(
                "SELECT id, content, cluster, duration_minutes FROM items WHERE status = 'wishful' ORDER BY RANDOM() LIMIT 1"
            )
            wishful_suggestion = None
            if wish_rows:
                w = dict(wish_rows[0])
                wishful_suggestion = {"id": w["id"], "content": w["content"], "cluster": w.get("cluster"), "duration_minutes": w.get("duration_minutes")}
            return {
                "options": [],
                "message": "No tasks in this track. Capture something or switch tracks!",
                "wishful_suggestion": wishful_suggestion,
                "active_track": {"id": active_track["id"], "name": active_track["name"], "color": active_track["color"], "icon": active_track["icon"]} if active_track else None,
            }

        # Get recent history for user state inference
        history_rows = await db.execute_fetchall(
            """SELECT event, elapsed_seconds, user_energy, user_focus, user_momentum
               FROM task_history
               WHERE created_at > datetime('now', '-2 hours')
               ORDER BY created_at DESC
               LIMIT 20"""
        )
        history_events = [dict(r) for r in history_rows]

        completed_recently = await _get_recently_completed(db)
        goal_context = await _get_goal_context(db)

        # Load routine for circadian energy mapping
        routine = None
        routine_row = await db.execute_fetchall(
            "SELECT value FROM user_persona WHERE key = 'routine'"
        )
        if routine_row and routine_row[0]["value"]:
            try:
                routine = json.loads(routine_row[0]["value"])
            except Exception:
                routine = None

        # Load recent check-in for state inference
        checkin = None
        checkin_row = await db.execute_fetchall(
            """SELECT energy, focus, mood, created_at
               FROM checkins
               WHERE created_at > datetime('now', '-2 hours')
               ORDER BY created_at DESC LIMIT 1"""
        )
        if checkin_row:
            checkin = {"has_recent": True, **dict(checkin_row[0])}

        # Infer user state (two-tier: check-in or behavioral)
        user_state = infer_user_state(
            completed_recently, history_events, routine=routine, checkin=checkin
        )

        # System maturity gates features progressively
        maturity = await get_system_maturity(db)

        # Active goal IDs for goal-aligned scoring
        goal_rows = await db.execute_fetchall(
            "SELECT id FROM goals WHERE status = 'active'"
        )
        active_goal_ids = {r["id"] for r in goal_rows} if goal_rows else set()

        # Check if break is needed
        break_info = needs_break(user_state)
        if break_info and break_info["type"] == "enforced":
            return {
                "options": [],
                "break": break_info,
                "message": break_info["message"],
                "user_state": user_state,
            }

        # Run scheduling engine — returns scored sequence
        result = select_next_task(
            items, user_state,
            maturity_level=maturity["level"],
            active_goal_ids=active_goal_ids,
        )
        sequence = result.get("sequence", [])

        if not sequence:
            return {
                "options": [],
                "message": "No suitable task right now.",
            }

        # Format top 3 as selectable options (no locking yet)
        # Scheduler sequence may be short due to aggressive filtering;
        # pad with remaining candidates so user always has up to 3 choices.
        seen_ids = set()
        option_items = []
        for item in sequence:
            if item["id"] not in seen_ids:
                option_items.append(item)
                seen_ids.add(item["id"])
            if len(option_items) >= 3:
                break
        if len(option_items) < 3:
            for item in items:
                if item["id"] not in seen_ids:
                    option_items.append(item)
                    seen_ids.add(item["id"])
                if len(option_items) >= 3:
                    break

        options = [_format_option(item, user_state) for item in option_items]

        resp = {
            "options": options,
            "big_picture": goal_context,
            "user_state": user_state,
            "maturity": maturity,
        }

        if active_track:
            resp["active_track"] = {"id": active_track["id"], "name": active_track["name"], "color": active_track["color"], "icon": active_track["icon"]}

        if break_info:
            resp["break_suggestion"] = break_info

        if result.get("anti_loop_warning"):
            resp["anti_loop_warning"] = result["anti_loop_warning"]

        return resp
    finally:
        await db.close()


@app.post("/select")
async def select_task(body: SelectInput):
    """Lock a chosen task as 'doing' and return the full execution block."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (body.item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")
        selected = dict(row[0])

        # Lock as active
        await db.execute(
            "UPDATE items SET status = 'doing' WHERE id = ?", (selected["id"],)
        )
        await db.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            ("current_active_task_id", str(selected["id"])),
        )
        await db.commit()
        selected["status"] = "doing"

        # Get after items & context
        after = await _get_next_items(db, exclude_id=selected["id"], limit=2)
        goal_context = await _get_goal_context(db)

        # History for user state
        history_rows = await db.execute_fetchall(
            """SELECT event, elapsed_seconds, user_energy, user_focus, user_momentum
               FROM task_history
               WHERE created_at > datetime('now', '-2 hours')
               ORDER BY created_at DESC LIMIT 20"""
        )
        history_events = [dict(r) for r in history_rows]
        completed_recently = await _get_recently_completed(db)
        user_state = infer_user_state(completed_recently, history_events)

        # Build reasoning
        sched_result = select_next_task([selected] + after, user_state)
        reasoning = sched_result.get("reasoning", "")
        recovery = sched_result.get("recovery")

        block = _format_execution_block(
            selected, after,
            reasoning=reasoning,
            big_picture=goal_context,
            recovery=recovery,
            user_state=user_state,
        )

        # Include dopamine sandwich for thinking tasks
        if sched_result.get("dopamine_sandwich"):
            ds = sched_result["dopamine_sandwich"]
            block["dopamine_sandwich"] = {
                "before": {"id": ds["before"]["id"], "content": ds["before"]["content"], "duration_minutes": ds["before"].get("duration_minutes", 15)} if ds.get("before") else None,
                "after": {"id": ds["after"]["id"], "content": ds["after"]["content"], "duration_minutes": ds["after"].get("duration_minutes", 20)} if ds.get("after") else None,
            }

        return block
    finally:
        await db.close()


# ── POST /complete ───────────────────────────────────────────────


@app.post("/complete")
async def complete_task(body: CompleteInput):
    """Mark a task as complete, log to history, update work patterns, surface next tasks."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (body.item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")

        item = dict(row[0])
        is_thinking = item.get("type") == "thinking"

        # Guard against double-completion
        if item.get("status") == "done":
            return await get_next()

        await db.execute(
            "UPDATE items SET status = 'done' WHERE id = ?", (body.item_id,)
        )

        # Track thinking time budget for convergence
        if is_thinking and body.elapsed_seconds:
            current_spent = item.get("thinking_time_spent", 0) or 0
            new_spent = current_spent + (body.elapsed_seconds // 60)
            await db.execute(
                "UPDATE items SET thinking_time_spent = ? WHERE id = ?",
                (new_spent, body.item_id),
            )

        # Log completion to task_history
        from backend.scheduler import infer_time_of_day
        tod = infer_time_of_day()
        await db.execute(
            """INSERT INTO task_history (item_id, event, elapsed_seconds, time_of_day)
               VALUES (?, 'completed', ?, ?)""",
            (body.item_id, body.elapsed_seconds, tod),
        )

        # ── Update work patterns (speed map) ──
        if body.elapsed_seconds and body.elapsed_seconds > 0:
            try:
                await _update_work_pattern(db, item, body.elapsed_seconds, tod)
            except Exception as e:
                logger.error("Failed to update work pattern: %s", e)

        # Clear active lock if this was the active task
        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'current_active_task_id'"
        )
        if state and state[0]["value"] == str(body.item_id):
            await db.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("current_active_task_id", None),
            )
        await db.commit()
    finally:
        await db.close()

    # If thinking task, prompt for expansion instead of auto-loading next
    if is_thinking:
        return {
            "thinking_complete": True,
            "item_id": body.item_id,
            "thinking_objective": item.get("thinking_objective", ""),
            "thinking_output_format": item.get("thinking_output_format", ""),
            "message": "Thinking session complete! Share your notes to generate action tasks.",
        }

    # Momentum: auto-surface next
    return await get_next()


# ── POST /override ───────────────────────────────────────────────


@app.post("/override")
async def override_task(body: OverrideInput):
    """Skip the current task with a categorized reason. Tracks avoidance patterns."""
    if not body.reason.strip():
        raise HTTPException(400, "Reason is required to skip a task")

    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (body.item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")

        existing = dict(row[0])

        # Process skip through categorized avoidance handler
        skip_category = body.skip_category or "not_now"
        skip_result = handle_skip(existing, skip_category=skip_category)

        # Update item with skip tracking — DO NOT mutate content
        await db.execute(
            """UPDATE items SET status = 'backlog',
               skip_count = ?, resistance_flag = ?, dominant_skip_reason = ?
               WHERE id = ?""",
            (skip_result["skip_count"],
             skip_result["resistance_flag"],
             skip_result.get("dominant_skip_reason", skip_category),
             body.item_id),
        )

        # Log skip to task_history with category
        from backend.scheduler import infer_time_of_day
        tod = infer_time_of_day()
        await db.execute(
            """INSERT INTO task_history (item_id, event, time_of_day, skip_reason_category)
               VALUES (?, 'skipped', ?, ?)""",
            (body.item_id, tod, skip_category),
        )

        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'current_active_task_id'"
        )
        if state and state[0]["value"] == str(body.item_id):
            await db.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("current_active_task_id", None),
            )
        await db.commit()
    finally:
        await db.close()

    next_data = await get_next()

    # Attach intervention if relevant
    if skip_result.get("suggestion"):
        next_data["avoidance_warning"] = skip_result["suggestion"]
        next_data["intervention_type"] = skip_result.get("guidance", "avoidance_detected")

    return next_data


# ── POST /expand ─────────────────────────────────────────────────


@app.post("/expand")
async def expand_task(body: ExpandInput):
    """Expand a completed thinking task's notes into concrete action tasks."""
    if not body.notes.strip():
        raise HTTPException(400, "Notes are required for expansion")

    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (body.item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")

        original = dict(row[0])

        # Increment revisit count
        revisit_count = original.get("revisit_count", 0) + 1
        await db.execute(
            "UPDATE items SET thinking_output = ?, revisit_count = ?, expanded = 1 WHERE id = ?",
            (body.notes, revisit_count, body.item_id),
        )

        # Get context for expansion
        context = await _get_context_summary()

        # Run AI expansion pipeline
        try:
            expansion = await expand_thinking_output(original, body.notes, existing_context=context)
        except RuntimeError as e:
            raise HTTPException(502, str(e))

        tasks = expansion.get("tasks", [])
        gaps = expansion.get("gaps", [])

        if not tasks:
            await db.commit()
            return {
                "status": "no_tasks",
                "message": "Could not generate tasks from the notes. Try adding more detail.",
                "gaps": gaps,
            }

        # Insert expanded tasks linked to the source idea
        goal_text = original.get("content", "")
        item_ids, _ = await _insert_task_batch(
            db, tasks, goal_text, source_idea_id=body.item_id
        )

        await db.commit()

        return {
            "status": "expanded",
            "item_ids": item_ids,
            "task_count": len(item_ids),
            "tasks": tasks,
            "gaps": gaps,
            "source_id": body.item_id,
        }
    finally:
        await db.close()


# ── GET /plan ────────────────────────────────────────────────────


@app.get("/plan")
async def get_plan():
    """Return full plan view — all items grouped by track, then cluster."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT i.*, t.name as track_name, t.color as track_color, t.icon as track_icon
               FROM items i
               LEFT JOIN tracks t ON i.track_id = t.id
               ORDER BY CASE i.status WHEN 'done' THEN 1 ELSE 0 END,
                        i.priority DESC, i.created_at ASC"""
        )
        items = [dict(r) for r in rows]

        # Group by track, then by cluster
        by_track: dict[str, dict] = {}
        for item in items:
            tname = item.get("track_name") or "Untracked"
            c = item.get("cluster") or "uncategorized"
            if tname not in by_track:
                by_track[tname] = {
                    "track_color": item.get("track_color"),
                    "track_icon": item.get("track_icon"),
                    "clusters": {},
                }
            by_track[tname]["clusters"].setdefault(c, []).append(item)

        # Pending inbox items
        inbox_rows = await db.execute_fetchall(
            "SELECT * FROM inbox WHERE approved = 0 ORDER BY created_at DESC"
        )
        pending = [dict(r) for r in inbox_rows]

        # All tracks for plan filter
        track_rows = await db.execute_fetchall(
            "SELECT * FROM tracks ORDER BY sort_order ASC"
        )
        tracks = [dict(r) for r in track_rows]

        return {
            "by_track": by_track,
            "tracks": tracks,
            "pending_inbox": pending,
            "total_items": len(items),
        }
    finally:
        await db.close()


# ── GET /inbox ───────────────────────────────────────────────────


@app.get("/inbox")
async def get_inbox():
    """Return pending inbox items that need approval."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM inbox WHERE approved = 0 ORDER BY created_at DESC"
        )
        return {"items": [dict(r) for r in rows]}
    finally:
        await db.close()


# ── GET /wishlist ────────────────────────────────────────────────


@app.get("/wishlist")
async def get_wishlist():
    """Return all wishful thinking items."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT i.*, t.name as track_name, t.color as track_color, t.icon as track_icon
               FROM items i
               LEFT JOIN tracks t ON i.track_id = t.id
               WHERE i.status = 'wishful'
               ORDER BY i.created_at DESC"""
        )
        return {"items": [dict(r) for r in rows]}
    finally:
        await db.close()


class PromoteWishInput(BaseModel):
    item_id: int
    to_status: Optional[str] = "inbox"


@app.post("/wishlist/promote")
async def promote_wish(body: PromoteWishInput):
    """Promote a wishful item to an actionable status (inbox or next)."""
    if body.to_status not in ("inbox", "next"):
        raise HTTPException(400, "Can only promote to inbox or next")

    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ? AND status = 'wishful'",
            (body.item_id,),
        )
        if not row:
            raise HTTPException(404, "Wishful item not found")

        await db.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (body.to_status, body.item_id),
        )
        await db.commit()
        return {"status": "promoted", "item_id": body.item_id, "new_status": body.to_status}
    finally:
        await db.close()


# ── CRUD: Items ──────────────────────────────────────────────────


@app.patch("/items/{item_id}")
async def update_item(item_id: int, body: UpdateItemInput):
    """Update fields on an existing item."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")

        updates = {}
        if body.content is not None:
            updates["content"] = body.content
        if body.status is not None:
            if body.status not in ("inbox", "next", "doing", "done", "backlog", "wishful"):
                raise HTTPException(400, "Invalid status")
            updates["status"] = body.status
        if body.cluster is not None:
            updates["cluster"] = body.cluster
        if body.energy_required is not None:
            if body.energy_required not in ("low", "medium", "high"):
                raise HTTPException(400, "Invalid energy_required")
            updates["energy_required"] = body.energy_required
        if body.duration_minutes is not None:
            updates["duration_minutes"] = min(body.duration_minutes, 45)
        if body.priority is not None:
            updates["priority"] = body.priority
        if body.track_id is not None:
            updates["track_id"] = body.track_id

        if not updates:
            raise HTTPException(400, "No fields to update")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]
        await db.execute(f"UPDATE items SET {set_clause} WHERE id = ?", values)

        # If marking as done or changing away from doing, clear active lock
        if updates.get("status") in ("done", "backlog", "inbox", "next"):
            state = await db.execute_fetchall(
                "SELECT value FROM system_state WHERE key = 'current_active_task_id'"
            )
            if state and state[0]["value"] == str(item_id):
                await db.execute(
                    "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                    ("current_active_task_id", None),
                )

        await db.commit()

        updated = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        )
        return {"status": "updated", "item": dict(updated[0])}
    finally:
        await db.close()


@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    """Delete an item permanently."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        )
        if not row:
            raise HTTPException(404, "Item not found")

        # Clear active lock if needed
        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'current_active_task_id'"
        )
        if state and state[0]["value"] == str(item_id):
            await db.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("current_active_task_id", None),
            )

        await db.execute("DELETE FROM plan_items WHERE item_id = ?", (item_id,))
        await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        await db.commit()
        return {"status": "deleted", "item_id": item_id}
    finally:
        await db.close()


# ── Helpers ──────────────────────────────────────────────────────


async def _update_work_pattern(db, item: dict, elapsed_seconds: int, time_of_day: str):
    """Update the work-speed map with this completion datapoint."""
    from backend.database import get_duration_bucket

    cluster = item.get("cluster", "general")
    layer = item.get("layer", "operational")
    cog_load = item.get("cognitive_load", "medium")
    energy = item.get("energy_required", "medium")
    estimated_seconds = (item.get("duration_minutes") or 30) * 60
    bucket = get_duration_bucket(elapsed_seconds)

    # Check if a matching pattern row exists
    existing = await db.execute_fetchall(
        """SELECT id, sample_count, avg_elapsed_seconds, avg_estimated_seconds
           FROM work_patterns
           WHERE cluster = ? AND layer = ? AND cognitive_load = ?
             AND energy_required = ? AND time_of_day = ? AND duration_bucket = ?""",
        (cluster, layer, cog_load, energy, time_of_day, bucket),
    )

    if existing:
        row = dict(existing[0])
        n = row["sample_count"]
        new_n = n + 1
        # Running average
        new_avg_elapsed = (row["avg_elapsed_seconds"] * n + elapsed_seconds) / new_n
        new_avg_estimated = (row["avg_estimated_seconds"] * n + estimated_seconds) / new_n
        speed_ratio = new_avg_elapsed / new_avg_estimated if new_avg_estimated > 0 else 1.0
        await db.execute(
            """UPDATE work_patterns
               SET sample_count = ?, avg_elapsed_seconds = ?, avg_estimated_seconds = ?,
                   speed_ratio = ?, last_updated = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (new_n, new_avg_elapsed, new_avg_estimated, speed_ratio, row["id"]),
        )
    else:
        speed_ratio = elapsed_seconds / estimated_seconds if estimated_seconds > 0 else 1.0
        await db.execute(
            """INSERT INTO work_patterns
               (cluster, layer, cognitive_load, energy_required, time_of_day,
                duration_bucket, sample_count, avg_elapsed_seconds, avg_estimated_seconds, speed_ratio)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (cluster, layer, cog_load, energy, time_of_day, bucket,
             elapsed_seconds, estimated_seconds, speed_ratio),
        )

    # Rebuild persona summary periodically (every 5 completions)
    total_row = await db.execute_fetchall(
        "SELECT SUM(sample_count) as total FROM work_patterns"
    )
    total = total_row[0]["total"] if total_row and total_row[0]["total"] else 0
    if total % 5 == 0:
        await _rebuild_persona(db)


async def _rebuild_persona(db):
    """Compute aggregate persona insights from work_patterns."""
    import json as _json

    # Overall speed tendency
    speed_rows = await db.execute_fetchall(
        """SELECT cluster, layer, cognitive_load, time_of_day, duration_bucket,
                  sample_count, speed_ratio, avg_elapsed_seconds
           FROM work_patterns
           WHERE sample_count >= 2
           ORDER BY sample_count DESC"""
    )
    patterns = [dict(r) for r in speed_rows]

    # Global average speed ratio (weighted by sample count)
    total_samples = sum(p["sample_count"] for p in patterns) if patterns else 0
    if total_samples > 0:
        weighted_ratio = sum(p["speed_ratio"] * p["sample_count"] for p in patterns) / total_samples
    else:
        weighted_ratio = 1.0

    # Speed by cognitive load
    speed_by_cog = {}
    for p in patterns:
        cog = p["cognitive_load"]
        speed_by_cog.setdefault(cog, {"total_w": 0, "total_s": 0})
        speed_by_cog[cog]["total_w"] += p["speed_ratio"] * p["sample_count"]
        speed_by_cog[cog]["total_s"] += p["sample_count"]
    cog_ratios = {k: round(v["total_w"] / v["total_s"], 2) for k, v in speed_by_cog.items() if v["total_s"] > 0}

    # Speed by time of day
    speed_by_tod = {}
    for p in patterns:
        tod = p["time_of_day"]
        speed_by_tod.setdefault(tod, {"total_w": 0, "total_s": 0})
        speed_by_tod[tod]["total_w"] += p["speed_ratio"] * p["sample_count"]
        speed_by_tod[tod]["total_s"] += p["sample_count"]
    tod_ratios = {k: round(v["total_w"] / v["total_s"], 2) for k, v in speed_by_tod.items() if v["total_s"] > 0}

    # Preferred duration bucket (where they complete most tasks)
    bucket_counts = {}
    for p in patterns:
        b = p["duration_bucket"]
        bucket_counts[b] = bucket_counts.get(b, 0) + p["sample_count"]
    preferred_bucket = max(bucket_counts, key=bucket_counts.get) if bucket_counts else "15-20min"

    # Speed by cluster (top domains)
    speed_by_cluster = {}
    for p in patterns:
        c = p["cluster"]
        speed_by_cluster.setdefault(c, {"total_w": 0, "total_s": 0})
        speed_by_cluster[c]["total_w"] += p["speed_ratio"] * p["sample_count"]
        speed_by_cluster[c]["total_s"] += p["sample_count"]
    cluster_ratios = {k: round(v["total_w"] / v["total_s"], 2) for k, v in speed_by_cluster.items() if v["total_s"] > 0}

    persona = {
        "global_speed_ratio": round(weighted_ratio, 2),
        "speed_by_cognitive_load": cog_ratios,
        "speed_by_time_of_day": tod_ratios,
        "speed_by_cluster": cluster_ratios,
        "preferred_duration_bucket": preferred_bucket,
        "total_datapoints": total_samples,
    }

    await db.execute(
        "INSERT OR REPLACE INTO user_persona (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        ("work_speed_profile", _json.dumps(persona)),
    )


async def _get_user_persona_context(db) -> str:
    """Build a user persona string for the AI parser to use for better time estimates."""
    import json as _json

    rows = await db.execute_fetchall(
        "SELECT key, value FROM user_persona"
    )
    if not rows:
        return ""

    parts = ["USER WORK-SPEED PROFILE (learned from their task history):"]
    for r in rows:
        key = r["key"]
        try:
            val = _json.loads(r["value"])
        except (ValueError, TypeError):
            val = r["value"]

        if key == "work_speed_profile" and isinstance(val, dict):
            ratio = val.get("global_speed_ratio", 1.0)
            if ratio < 0.8:
                parts.append(f"  - This user is FAST — they complete tasks in ~{int(ratio*100)}% of estimated time. REDUCE your estimates.")
            elif ratio > 1.3:
                parts.append(f"  - This user takes LONGER than estimates — ~{int(ratio*100)}% of estimated time. Be generous with time.")
            else:
                parts.append(f"  - This user's speed is close to estimates (~{int(ratio*100)}%).")

            cog = val.get("speed_by_cognitive_load", {})
            if cog:
                for load, r2 in cog.items():
                    if r2 < 0.7:
                        parts.append(f"  - Very fast at {load}-cognitive tasks ({int(r2*100)}% of estimate)")
                    elif r2 > 1.4:
                        parts.append(f"  - Slower at {load}-cognitive tasks ({int(r2*100)}% of estimate)")

            tod = val.get("speed_by_time_of_day", {})
            if tod:
                fastest_tod = min(tod, key=tod.get) if tod else None
                slowest_tod = max(tod, key=tod.get) if tod else None
                if fastest_tod and tod[fastest_tod] < 0.85:
                    parts.append(f"  - Most productive time: {fastest_tod}")
                if slowest_tod and tod[slowest_tod] > 1.2:
                    parts.append(f"  - Slowest time: {slowest_tod}")

            cluster_ratios = val.get("speed_by_cluster", {})
            if cluster_ratios:
                fast_clusters = [c for c, r2 in cluster_ratios.items() if r2 < 0.75]
                slow_clusters = [c for c, r2 in cluster_ratios.items() if r2 > 1.3]
                if fast_clusters:
                    parts.append(f"  - Fast domains: {', '.join(fast_clusters)}")
                if slow_clusters:
                    parts.append(f"  - Slower domains: {', '.join(slow_clusters)}")

            pref = val.get("preferred_duration_bucket", "")
            if pref:
                parts.append(f"  - Preferred work session length: {pref}")

    return "\n".join(parts) if len(parts) > 1 else ""


def _normalize_content(text: str) -> str:
    """Normalize task content for dedup comparison: lowercase, collapse whitespace, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


async def _find_duplicate_item(db, content: str) -> int | None:
    """Check if a non-done item with essentially the same content already exists.
    Returns the existing item id if duplicate, None otherwise."""
    normalized = _normalize_content(content)
    if not normalized:
        return None
    rows = await db.execute_fetchall(
        "SELECT id, content FROM items WHERE status NOT IN ('done') ORDER BY created_at DESC LIMIT 200"
    )
    for row in rows:
        if _normalize_content(row["content"]) == normalized:
            return row["id"]
    return None


async def _check_raw_input_duplicate(db, raw: str) -> dict | None:
    """Check if the same raw input was submitted recently (within 5 minutes).
    Uses an in-memory cache of recent submissions."""
    import time
    normalized = _normalize_content(raw)
    now = time.time()
    # Clean old entries (older than 5 minutes)
    cutoff = now - 300
    expired = [k for k, ts in _recent_submissions.items() if ts < cutoff]
    for k in expired:
        del _recent_submissions[k]
    # Check for duplicate
    if normalized in _recent_submissions:
        return {"raw_input": raw}
    # Record this submission
    _recent_submissions[normalized] = now
    return None


# In-memory cache: normalized_text → timestamp
_recent_submissions: dict[str, float] = {}


async def _insert_task_batch(
    db, tasks: list[dict], goal_text: str = "",
    source_idea_id: int = None, existing_goal_id: int = None,
) -> list[int]:
    """Insert a batch of decomposed tasks, linked to a goal.

    If existing_goal_id is set (AI matched to an existing goal), use that
    instead of creating a new goal row.
    """
    goal_id = existing_goal_id
    if not goal_id and goal_text:
        cluster = tasks[0].get("cluster", "general") if tasks else "general"
        cursor = await db.execute(
            "INSERT INTO goals (summary, cluster) VALUES (?, ?)",
            (goal_text, cluster),
        )
        goal_id = cursor.lastrowid

    item_ids = []
    skipped_dupes = 0
    for i, task in enumerate(tasks):
        # Deduplication: skip tasks whose content matches an existing active item
        existing_id = await _find_duplicate_item(db, task.get("content", ""))
        if existing_id is not None:
            item_ids.append(existing_id)  # return existing id for reference
            skipped_dupes += 1
            continue

        priority = compute_priority(task)

        # Resolve parent_item_id from AI (link to existing item)
        parent_id = task.get("parent_item_id")
        if parent_id is not None:
            # Validate the parent actually exists
            check = await db.execute_fetchall(
                "SELECT id FROM items WHERE id = ?", (parent_id,)
            )
            if not check:
                parent_id = None

        # Per-task goal override: AI may link individual tasks to different goals
        task_goal_id = goal_id

        # Respect AI-suggested status (e.g. 'wishful' for bucket list items)
        suggested_status = task.get("suggested_status", "inbox")
        if suggested_status not in ("inbox", "next", "backlog", "wishful"):
            suggested_status = "inbox"

        cursor = await db.execute(
            """INSERT INTO items (content, layer, type, scope, cluster, status,
                                  priority, energy_required, duration_minutes,
                                  cognitive_load, dopamine_profile,
                                  initiation_friction, completion_visibility,
                                  execution_class, source_idea_id, parent_id,
                                  thinking_objective, thinking_output_format,
                                  goal_id, track_id, complexity_score, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.get("content", ""),
                task.get("layer", "operational"),
                task.get("type", "task"),
                task.get("scope", "local"),
                task.get("cluster", "general"),
                suggested_status,
                priority,
                task.get("energy_required", "medium"),
                min(task.get("duration_minutes", 30), 45),
                task.get("cognitive_load", "medium"),
                task.get("dopamine_profile", "neutral"),
                task.get("initiation_friction", "medium"),
                task.get("completion_visibility", "visible"),
                task.get("execution_class", "linear"),
                source_idea_id,
                parent_id,
                task.get("thinking_objective"),
                task.get("thinking_output_format"),
                task_goal_id,
                task.get("track_id"),
                min(max(task.get("complexity_score", 5.0), 0), 10),
                i,
            ),
        )
        item_ids.append(cursor.lastrowid)

    await db.commit()
    return item_ids, skipped_dupes


async def _get_context_summary() -> str:
    """Build a rich hierarchical context of goals, clusters, tracks, and tasks for the parser."""
    db = await get_db()
    try:
        # ── Tracks ──
        track_rows = await db.execute_fetchall(
            "SELECT id, name, icon, time_available, allow_cross_track FROM tracks ORDER BY sort_order ASC"
        )
        tracks = [dict(r) for r in track_rows]

        # ── Goals ──
        goal_rows = await db.execute_fetchall(
            "SELECT id, summary, cluster FROM goals ORDER BY created_at DESC LIMIT 10"
        )
        goals = [dict(r) for r in goal_rows]

        # ── All non-done items with hierarchy info ──
        item_rows = await db.execute_fetchall(
            """SELECT i.id, i.content, i.layer, i.type, i.cluster, i.status,
                      i.parent_id, i.goal_id, i.execution_class, i.track_id,
                      t.name as track_name
               FROM items i
               LEFT JOIN tracks t ON i.track_id = t.id
               WHERE i.status != 'done'
               ORDER BY i.cluster, i.layer DESC, i.priority DESC, i.created_at ASC
               LIMIT 50"""
        )
        items = [dict(r) for r in item_rows]

        # ── Recently completed (for continuity awareness) ──
        done_rows = await db.execute_fetchall(
            """SELECT id, content, cluster, layer FROM items
               WHERE status = 'done'
               ORDER BY created_at DESC LIMIT 5"""
        )
        done = [dict(r) for r in done_rows]

        # ── Build structured context string ──
        parts = []

        if tracks:
            parts.append("TRACKS (id | name | constraints):")
            for t in tracks:
                time_note = f" [available: {t['time_available']}]" if t.get('time_available') else ""
                cross_note = " [cross-track OK]" if t.get('allow_cross_track') else ""
                parts.append(f"  track#{t['id']} {t['icon']} {t['name']}{time_note}{cross_note}")

        if goals:
            parts.append("\nGOALS (id | cluster | summary):")
            for g in goals:
                parts.append(f"  goal#{g['id']} [{g.get('cluster','general')}] {g['summary']}")

        if items:
            # Group by cluster for readability
            clusters: dict[str, list] = {}
            for it in items:
                c = it.get("cluster") or "uncategorized"
                clusters.setdefault(c, []).append(it)

            parts.append("\nACTIVE TASKS (id | layer | status | content):")
            for cluster_name, cluster_items in clusters.items():
                parts.append(f"  [{cluster_name}]")
                for it in cluster_items:
                    parent_note = f" (child of item#{it['parent_id']})" if it.get("parent_id") else ""
                    goal_note = f" (goal#{it['goal_id']})" if it.get("goal_id") else ""
                    track_note = f" [track: {it['track_name']}]" if it.get("track_name") else ""
                    parts.append(
                        f"    item#{it['id']} {it['layer']} [{it['status']}] "
                        f"{it['content']}{parent_note}{goal_note}{track_note}"
                    )

        if done:
            parts.append("\nRECENTLY COMPLETED:")
            for d in done:
                parts.append(f"  item#{d['id']} [{d.get('cluster','?')}] {d['content']}")

        # Include user persona / work-speed profile
        persona_ctx = await _get_user_persona_context(db)
        if persona_ctx:
            parts.append(f"\n{persona_ctx}")

        return "\n".join(parts)
    finally:
        await db.close()


async def _get_goal_context(db) -> str:
    """Get goal summaries for planner context."""
    rows = await db.execute_fetchall(
        "SELECT summary FROM goals ORDER BY created_at DESC LIMIT 5"
    )
    return "; ".join(dict(r)["summary"] for r in rows) if rows else ""


async def _get_recently_completed(db) -> list[dict]:
    """Get recently completed tasks for momentum-aware planning."""
    rows = await db.execute_fetchall(
        """SELECT id, content, cluster FROM items
           WHERE status = 'done'
           ORDER BY created_at DESC LIMIT 3"""
    )
    return [dict(r) for r in rows]


async def _get_next_items(db, exclude_id: int, limit: int = 2) -> list[dict]:
    rows = await db.execute_fetchall(
        """SELECT * FROM items
           WHERE id != ? AND status IN ('next', 'inbox', 'backlog')
           ORDER BY priority DESC, sort_order ASC, created_at ASC
           LIMIT ?""",
        (exclude_id, limit),
    )
    return [dict(r) for r in rows]


def _format_execution_block(now_item: dict, after: list[dict],
                             reasoning: str = "", big_picture: str = "",
                             recovery: dict = None, user_state: dict = None,
                             break_suggestion: dict = None) -> dict:
    energy_emoji = {"low": "⚡", "medium": "🔥", "high": "💪"}.get(
        now_item.get("energy_required", "medium"), "🔥"
    )
    friction_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
        now_item.get("initiation_friction", "medium"), "🟡"
    )
    dopamine_label = {"quick_reward": "Quick win", "delayed_reward": "Long game", "neutral": ""}.get(
        now_item.get("dopamine_profile", "neutral"), ""
    )

    result = {
        "now": {
            "id": now_item["id"],
            "content": now_item["content"],
            "duration_minutes": now_item.get("duration_minutes", 30),
            "energy_required": now_item.get("energy_required", "medium"),
            "energy_emoji": energy_emoji,
            "cluster": now_item.get("cluster"),
            "layer": now_item.get("layer"),
            "type": now_item.get("type", "task"),
            "cognitive_load": now_item.get("cognitive_load", "medium"),
            "dopamine_profile": now_item.get("dopamine_profile", "neutral"),
            "dopamine_label": dopamine_label,
            "initiation_friction": now_item.get("initiation_friction", "medium"),
            "friction_emoji": friction_emoji,
            "completion_visibility": now_item.get("completion_visibility", "visible"),
            "execution_class": now_item.get("execution_class", "linear"),
            "why": reasoning or f"Highest priority in {now_item.get('cluster', 'your queue')}",
        },
        "after": [
            {
                "id": item["id"],
                "content": item["content"],
                "duration_minutes": item.get("duration_minutes", 30),
                "energy_required": item.get("energy_required", "medium"),
                "dopamine_label": {"quick_reward": "Quick win", "delayed_reward": "Long game", "neutral": ""}.get(
                    item.get("dopamine_profile", "neutral"), ""
                ),
            }
            for item in after
        ],
        "big_picture": big_picture,
    }

    if recovery:
        result["recovery"] = {
            "id": recovery["id"],
            "content": recovery["content"],
            "duration_minutes": recovery.get("duration_minutes", 15),
        }

    if user_state:
        result["user_state"] = user_state

    if break_suggestion:
        result["break_suggestion"] = break_suggestion

    # Include thinking task metadata if applicable
    if now_item.get("type") == "thinking":
        result["now"]["thinking_objective"] = now_item.get("thinking_objective", "")
        result["now"]["thinking_output_format"] = now_item.get("thinking_output_format", "")
        result["now"]["is_thinking"] = True

    return result


def _format_option(item: dict, user_state: dict = None) -> dict:
    """Format a task as a selectable option card."""
    energy_emoji = {"low": "⚡", "medium": "🔥", "high": "💪"}.get(
        item.get("energy_required", "medium"), "🔥"
    )
    friction_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
        item.get("initiation_friction", "medium"), "🟡"
    )
    dopamine_label = {"quick_reward": "Quick win", "delayed_reward": "Long game", "neutral": ""}.get(
        item.get("dopamine_profile", "neutral"), ""
    )
    cog_emoji = {"low": "🧘", "medium": "🧠", "high": "🔬"}.get(
        item.get("cognitive_load", "medium"), "🧠"
    )
    opt = {
        "id": item["id"],
        "content": item["content"],
        "duration_minutes": item.get("duration_minutes", 30),
        "energy_required": item.get("energy_required", "medium"),
        "energy_emoji": energy_emoji,
        "cluster": item.get("cluster"),
        "layer": item.get("layer"),
        "type": item.get("type", "task"),
        "cognitive_load": item.get("cognitive_load", "medium"),
        "cognitive_emoji": cog_emoji,
        "dopamine_profile": item.get("dopamine_profile", "neutral"),
        "dopamine_label": dopamine_label,
        "initiation_friction": item.get("initiation_friction", "medium"),
        "friction_emoji": friction_emoji,
        "execution_class": item.get("execution_class", "linear"),
        "is_thinking": item.get("type") == "thinking",
        "track_id": item.get("track_id"),
    }
    if item.get("type") == "thinking":
        opt["thinking_objective"] = item.get("thinking_objective", "")
    return opt


# ── Stats endpoints ──────────────────────────────────────────────


@app.get("/stats/weekly")
async def get_weekly_stats():
    """Return time-saved stats for the current week and persona summary."""
    db = await get_db()
    try:
        # Get completions from this week, deduplicated (first completion per item)
        rows = await db.execute_fetchall(
            """SELECT th.elapsed_seconds, th.time_of_day, th.created_at,
                      i.duration_minutes, i.content, i.cluster, i.cognitive_load,
                      i.complexity_score
               FROM task_history th
               JOIN items i ON th.item_id = i.id
               WHERE th.event = 'completed'
                 AND th.created_at >= date('now', 'weekday 0', '-6 days')
                 AND th.id = (SELECT MIN(th2.id) FROM task_history th2
                              WHERE th2.item_id = th.item_id AND th2.event = 'completed')
               ORDER BY th.created_at DESC"""
        )
        completions = [dict(r) for r in rows]

        total_estimated_seconds = 0
        total_actual_seconds = 0
        tasks_completed = len(completions)
        time_saved_details = []
        complexity_sum = 0.0
        complexity_weighted_sum = 0.0
        complexity_count = 0
        complexity_buckets = {"low": 0, "medium": 0, "high": 0}  # 0-3, 4-6, 7-10

        for c in completions:
            est = (c.get("duration_minutes") or 30) * 60
            actual = c.get("elapsed_seconds") or est
            total_estimated_seconds += est
            total_actual_seconds += actual
            diff = est - actual
            if diff > 0:
                time_saved_details.append({
                    "content": c["content"],
                    "estimated_min": round(est / 60),
                    "actual_min": round(actual / 60),
                    "saved_min": round(diff / 60),
                })

            # Complexity tracking
            cs = c.get("complexity_score") or 5.0
            complexity_sum += cs
            complexity_count += 1
            speed_ratio = (actual / est) if est > 0 else 1.0
            complexity_weighted_sum += cs * speed_ratio
            if cs <= 3:
                complexity_buckets["low"] += 1
            elif cs <= 6:
                complexity_buckets["medium"] += 1
            else:
                complexity_buckets["high"] += 1

        time_saved_seconds = max(0, total_estimated_seconds - total_actual_seconds)

        # Complexity stats
        avg_complexity = round(complexity_sum / complexity_count, 1) if complexity_count else 0
        weighted_score = round(complexity_weighted_sum / complexity_count, 2) if complexity_count else 0

        # Get persona
        persona_row = await db.execute_fetchall(
            "SELECT value FROM user_persona WHERE key = 'work_speed_profile'"
        )
        persona = None
        if persona_row:
            import json as _json
            try:
                persona = _json.loads(persona_row[0]["value"])
            except (ValueError, TypeError):
                pass

        # Streak: consecutive days with at least 1 completion
        streak_rows = await db.execute_fetchall(
            """SELECT DISTINCT date(created_at) as d
               FROM task_history
               WHERE event = 'completed'
               ORDER BY d DESC
               LIMIT 30"""
        )
        streak = 0
        if streak_rows:
            from datetime import date, timedelta
            today = date.today()
            for r in streak_rows:
                expected = today - timedelta(days=streak)
                if r["d"] == str(expected):
                    streak += 1
                else:
                    break

        # Total tasks completed all-time
        all_time_row = await db.execute_fetchall(
            """SELECT COUNT(DISTINCT item_id) as cnt
               FROM task_history WHERE event = 'completed'"""
        )
        all_time_tasks = all_time_row[0]["cnt"] if all_time_row else 0

        # Improvement trend: compare this week vs last week
        last_week_rows = await db.execute_fetchall(
            """SELECT COUNT(DISTINCT th.item_id) as cnt
               FROM task_history th
               WHERE th.event = 'completed'
                 AND th.created_at >= date('now', 'weekday 0', '-13 days')
                 AND th.created_at < date('now', 'weekday 0', '-6 days')
                 AND th.id = (SELECT MIN(th2.id) FROM task_history th2
                              WHERE th2.item_id = th.item_id AND th2.event = 'completed')"""
        )
        last_week_tasks = last_week_rows[0]["cnt"] if last_week_rows else 0
        if last_week_tasks > 0:
            improvement_pct = round(((tasks_completed - last_week_tasks) / last_week_tasks) * 100)
        else:
            improvement_pct = None  # no prior data

        return {
            "tasks_completed": tasks_completed,
            "total_estimated_minutes": round(total_estimated_seconds / 60),
            "total_actual_minutes": round(total_actual_seconds / 60),
            "time_saved_minutes": round(time_saved_seconds / 60),
            "time_saved_hours": round(time_saved_seconds / 3600, 1),
            "top_savings": sorted(time_saved_details, key=lambda x: x["saved_min"], reverse=True)[:5],
            "streak_days": streak,
            "all_time_tasks": all_time_tasks,
            "improvement_pct": improvement_pct,
            "last_week_tasks": last_week_tasks,
            "complexity": {
                "average": avg_complexity,
                "weighted_score": weighted_score,
                "distribution": complexity_buckets,
            },
            "persona": persona,
        }
    finally:
        await db.close()


# ── Track endpoints ─────────────────────────────────────────────


@app.get("/tracks")
async def get_tracks():
    """Return all tracks plus the currently active track ID."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM tracks ORDER BY sort_order ASC, created_at ASC"
        )
        tracks = [dict(r) for r in rows]
        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'active_track_id'"
        )
        active_id = None
        if state and state[0]["value"]:
            active_id = int(state[0]["value"])
        return {"tracks": tracks, "active_track_id": active_id}
    finally:
        await db.close()


@app.post("/tracks")
async def create_track(body: TrackInput):
    """Create a new track."""
    db = await get_db()
    try:
        import sqlite3
        try:
            cursor = await db.execute(
                "INSERT INTO tracks (name, color, icon, time_available, allow_cross_track) VALUES (?, ?, ?, ?, ?)",
                (body.name.strip(), body.color, body.icon, body.time_available, body.allow_cross_track),
            )
            await db.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Track with that name already exists")
        return {"id": cursor.lastrowid, "name": body.name.strip()}
    finally:
        await db.close()


@app.patch("/tracks/{track_id}")
async def update_track(track_id: int, body: TrackUpdateInput):
    """Update a track's properties."""
    db = await get_db()
    try:
        row = await db.execute_fetchall("SELECT * FROM tracks WHERE id = ?", (track_id,))
        if not row:
            raise HTTPException(404, "Track not found")

        updates = {}
        if body.name is not None:
            updates["name"] = body.name.strip()
        if body.color is not None:
            updates["color"] = body.color
        if body.icon is not None:
            updates["icon"] = body.icon
        if body.time_available is not None:
            updates["time_available"] = body.time_available
        if body.allow_cross_track is not None:
            updates["allow_cross_track"] = body.allow_cross_track
        if not updates:
            raise HTTPException(400, "No fields to update")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [track_id]
        await db.execute(f"UPDATE tracks SET {set_clause} WHERE id = ?", values)
        await db.commit()
        updated = await db.execute_fetchall("SELECT * FROM tracks WHERE id = ?", (track_id,))
        return dict(updated[0])
    finally:
        await db.close()


@app.delete("/tracks/{track_id}")
async def delete_track(track_id: int):
    """Delete a track. Tasks in it become untracked."""
    db = await get_db()
    try:
        await db.execute("UPDATE items SET track_id = NULL WHERE track_id = ?", (track_id,))
        await db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        # Clear active track if it was this one
        state = await db.execute_fetchall(
            "SELECT value FROM system_state WHERE key = 'active_track_id'"
        )
        if state and state[0]["value"] == str(track_id):
            await db.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("active_track_id", None),
            )
        await db.commit()
        return {"deleted": True}
    finally:
        await db.close()


@app.post("/tracks/active")
async def set_active_track(body: SetActiveTrackInput):
    """Set or clear the active track filter."""
    db = await get_db()
    try:
        val = str(body.track_id) if body.track_id is not None else None
        if val:
            row = await db.execute_fetchall("SELECT * FROM tracks WHERE id = ?", (int(val),))
            if not row:
                raise HTTPException(404, "Track not found")
        await db.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            ("active_track_id", val),
        )
        await db.commit()
        return {"active_track_id": body.track_id}
    finally:
        await db.close()


# ── Static files (PWA) ──────────────────────────────────────────
# Mount static assets at /static, serve index.html for root

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("frontend/manifest.json")


@app.get("/sw.js")
async def serve_sw():
    return FileResponse("frontend/sw.js", media_type="application/javascript")


@app.get("/style.css")
async def serve_css():
    return FileResponse("frontend/style.css", media_type="text/css")


@app.get("/app.js")
async def serve_js():
    return FileResponse("frontend/app.js", media_type="application/javascript")


@app.get("/icon-192.png")
async def serve_icon_192():
    return FileResponse("frontend/icon-192.png", media_type="image/png")


@app.get("/icon-512.png")
async def serve_icon_512():
    return FileResponse("frontend/icon-512.png", media_type="image/png")
