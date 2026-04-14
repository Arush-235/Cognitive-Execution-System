import json
import os
from openai import AsyncOpenAI
from google import genai
from google.genai import types as gemini_types


def _get_provider() -> str:
    """Return 'gemini' or 'openai' based on the configured model."""
    model = _get_model()
    if model.startswith("gemini-"):
        return "gemini"
    return "openai"


def _get_client() -> AsyncOpenAI:
    """Return an OpenAI client using the current API key from env."""
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _get_gemini_client() -> genai.Client:
    """Return a Google GenAI client using the current Gemini API key from env."""
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))


def _get_model() -> str:
    """Return the configured model name from env, defaulting to gpt-4o-mini."""
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# Reasoning models use different API parameters (no temperature, max_completion_tokens instead of max_tokens)
_REASONING_MODELS = {"o3", "o4-mini", "o3-mini", "o1", "o1-mini"}


def _chat_kwargs(temperature: float = 0.2, max_tokens: int = 2000) -> dict:
    """Build model-appropriate kwargs for chat.completions.create (OpenAI only)."""
    model = _get_model()
    kwargs: dict = {"model": model}
    if any(model.startswith(prefix) for prefix in _REASONING_MODELS):
        # Reasoning models: no temperature, use max_completion_tokens
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["temperature"] = temperature
        kwargs["max_tokens"] = max_tokens
    # Force JSON output on all models that support it
    kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _gemini_config(temperature: float = 0.2, max_tokens: int = 2000) -> gemini_types.GenerateContentConfig:
    """Build a Gemini GenerateContentConfig."""
    return gemini_types.GenerateContentConfig(
        temperature=temperature,
        maxOutputTokens=max_tokens,
        responseMimeType="application/json",
    )


async def _chat_completion(messages: list[dict], temperature: float = 0.2, max_tokens: int = 2000) -> str:
    """Unified chat completion across OpenAI and Gemini. Returns raw text."""
    model = _get_model()
    provider = _get_provider()

    if provider == "gemini":
        client = _get_gemini_client()
        # Convert OpenAI-style messages to Gemini format
        system_instruction = None
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                contents.append(gemini_types.Content(role="user", parts=[gemini_types.Part(text=msg["content"])]))
            elif msg["role"] == "assistant":
                contents.append(gemini_types.Content(role="model", parts=[gemini_types.Part(text=msg["content"])]))

        config = _gemini_config(temperature=temperature, max_tokens=max_tokens)
        if system_instruction:
            config.systemInstruction = system_instruction

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return response.text or ""
    else:
        # OpenAI path
        client = _get_client()
        response = await client.chat.completions.create(
            messages=messages,
            **_chat_kwargs(temperature=temperature, max_tokens=max_tokens),
        )
        return response.choices[0].message.content or ""

PARSER_SYSTEM = """You are a task decomposition and classification engine optimized for ADHD execution.

Your job is to take raw user input — which may be a brain dump, a set of instructions, a complex goal, or a stream of consciousness — and break it down into ATOMIC, EXECUTABLE tasks with ADHD-aware metadata.

LANGUAGE HANDLING:
- The user may input in English, Hindi, or Hinglish (mix of Hindi and English).
- You MUST ALWAYS output in English regardless of input language.
- Translate the user's intent accurately into clear English task descriptions.
- Preserve technical terms, proper nouns, and brand names as-is.

CRITICAL RULES:
1. PRESERVE the user's INTENT. Do NOT rewrite what they said into generic how-to instructions.
2. If the input is a SINGLE, CLEAR action the user already knows how to do (e.g. "pack up my android app", "send invoice to client", "book flight"), return it as ONE task using their own words. Do NOT break it into sub-steps — the user knows the steps, they just need the reminder.
3. Only DECOMPOSE when the input genuinely contains MULTIPLE distinct tasks or is a large project/goal that spans days.
4. NEVER generate tutorial-style steps ("open X", "click Y", "navigate to Z"). The user is an expert in their own work. Your job is to capture WHAT they want to do, not teach them HOW.
5. Each task MUST be completable in ≤ 45 minutes. But DO NOT default to 30-45 minutes for everything. Most everyday tasks take 5-15 minutes. Only deep work, research, or creative sessions warrant 25-45 minutes.
6. Each task must have a CLEAR start and end — someone should know exactly when they're done.
7. Order tasks in a logical SEQUENCE — what needs to happen first?
8. If the user's input is ambiguous or you don't have enough context to know the concrete steps, use execution_class="expanding" and generate a THINKING task instead of guessing.

DURATION ESTIMATION — CRITICAL:
- Do NOT overestimate. Most single actions take 5-15 minutes, not 30.
- "Send an email" = 5-10 min. "Buy groceries" = 15-25 min. "Write a report" = 25-40 min.
- Quick admin (reply to message, update a doc, file something) = 5-10 min.
- Moderate tasks (draft something, review a document, organize files) = 10-20 min.
- Deep work (coding a feature, writing from scratch, research + analysis) = 20-40 min.
- If a USER WORK-SPEED PROFILE is provided, calibrate estimates to their proven pace. A user who finishes tasks in 60% of estimated time needs LOWER estimates.
- Prefer underestimating slightly over overestimating — finishing early feels rewarding for ADHD brains.

For EACH task, extract:
- content: a clear, specific, actionable task statement (start with a verb). Must describe a visible output.
- layer: strategic | tactical | operational | technical
- type: task | idea | problem | hypothesis | instruction
- scope: local | cluster | global
- cluster: short domain label (e.g. fundraising, product, growth, health, admin)
- duration_minutes: realistic estimate (5-45 range). Most tasks are 5-15 min. Only deep work hits 25-45. Do NOT default everything to 30.
- energy_required: low | medium | high
- cognitive_load: low (trivial/admin) | medium (structured thinking) | high (deep work/ambiguity)
- dopamine_profile: quick_reward (immediate visible progress) | delayed_reward (long-term payoff) | neutral
- initiation_friction: low (easy to start) | medium | high (ambiguous/complex/avoidance-prone)
- completion_visibility: visible (clear output like a list, doc, code) | invisible (abstract thinking)
- depends_on_index: index (0-based) of another task in this batch that must complete first, or null
- complexity_score: 0.0-10.0 (overall task difficulty: 0=trivial like "check email", 3=routine like "file a report", 5=moderate like "write a draft", 7=hard like "debug a tricky bug", 10=extremely complex like "architect a new system"). Factor in cognitive load, ambiguity, required expertise, and number of decisions needed.
- confidence: 0.0-1.0

ADHD CLASSIFICATION GUIDE:
- If a task has no clear starting point → initiation_friction = high → MUST decompose further
- If duration > 45 min → split into smaller chunks
- administrative tasks (emails, filing, cleanup) → cognitive_load=low, dopamine_profile=quick_reward, initiation_friction=low, duration=5-10min
- creative/design work → cognitive_load=high, initiation_friction=medium-high
- research/reading → cognitive_load=medium-high, completion_visibility=invisible
- writing/coding with output → completion_visibility=visible, dopamine_profile=quick_reward
- planning/strategy → cognitive_load=high, dopamine_profile=delayed_reward

EXECUTION CLASS DETECTION:
- execution_class: "linear" (clear sequential steps) | "modular" (independent subtasks) | "expanding" (vague/strategic, needs thinking first)
- Default is "linear". Use "modular" when subtasks are independent. Use "expanding" when:
  - The input is vague, ambiguous, or strategic ("figure out X", "plan Y", "decide on Z", "explore options for...")
  - There's no clear action path — the user needs to THINK before they can ACT
  - The idea is big/abstract and can't be directly decomposed into concrete tasks

THINKING TASK GENERATION (for expanding items):
When execution_class is "expanding", generate ONE thinking task instead of trying to force concrete action tasks.
A thinking task has:
- type: "thinking"
- execution_class: "expanding"
- thinking_objective: clear 1-sentence goal for the thinking session (e.g., "Decide which 3 features to build for MVP")
- thinking_output_format: what the user should produce (e.g., "A ranked list of 3 features with 1-line justification each")
- cognitive_load: always "high"
- initiation_friction: "high"
- completion_visibility: "visible" (because the output format is defined)
- dopamine_profile: "delayed_reward"
- duration_minutes: 20-30 (thinking sessions should be time-boxed)

CONTEXT LINKING — CRITICAL:
You will receive the user's existing goals and tasks with their IDs, layers, clusters, and hierarchy.
When a new input RELATES to something already in the system, you MUST link it:
- parent_item_id: the ID (integer) of an existing item this new task is a sub-task of (e.g. if item#12 is "Launch Android app" and the user says "generate signed APK", set parent_item_id=12).
- existing_goal_id: the ID (integer) of an existing goal this new task contributes to.
- cluster: REUSE the same cluster name as the existing related tasks. Do NOT invent a new cluster when one already fits.

Hierarchy rules:
- strategic items are top-level (big goals / themes)
- tactical items break down strategic items (plans, milestones)
- operational items are concrete actions within tactical items
- technical items are implementation details within operational items
- If the user adds a low-level action that clearly belongs under an existing higher-level item, set parent_item_id to that item's ID.
- If no existing item matches, leave parent_item_id as null.
- If the input matches an existing goal, set existing_goal_id to that goal's ID instead of creating a new goal.

TRACK ASSIGNMENT:
The user has defined "tracks" — focus lanes that group tasks by life domain.
You will receive a list of available tracks (id, name, icon). Assign each task to the most fitting track.
- "track_id": the integer ID of the track this task belongs to
- Match by domain using these rules:
  - **Errands track**: ANY physical-world task — household chores (clean, organize, tidy, declutter), maintenance (water plants, fix something, laundry), shopping (buy groceries, pick up package), appointments (doctor, salon, bank), cooking, running errands. If it involves your body moving to do something in the physical world, it's an Errand.
  - **Work track**: Professional/job tasks — meetings, reports, emails to colleagues, coding for work, deadlines, client work, office admin.
  - **Personal track**: Digital side projects, hobbies, learning, personal development, creative pursuits, relationship planning, self-improvement goals. Things you CHOOSE to do for growth or fun, not obligations.
- Rule of thumb: "Would I need to get up from my desk to do this?" → Errands. "Is this for my job?" → Work. "Is this a personal project/hobby/growth?" → Personal.
- If no track fits well, set track_id to null (the user can reassign later).
- A single input may produce tasks across MULTIPLE tracks (e.g., "pack android app and buy milk" → app task in Personal/Work, milk task in Errands).

WISHFUL THINKING DETECTION:
Some inputs are NOT actionable tasks — they are dreams, bucket-list ideas, aspirational desires, or vague "someday" wishes.
Indicators: "I wanna...", "would be cool to...", "someday I'd like to...", "bucket list:", "dream:", or any input that is:
  - Not urgent or time-bound
  - Not a concrete task the user plans to do soon
  - More of a life aspiration, experience, or far-off goal (e.g. "go paragliding", "visit Japan", "learn to sail", "slaughter a goat")
  - Vague desires without a clear next step

For wishful items, set: "suggested_status": "wishful"
For normal actionable tasks, set: "suggested_status": "inbox" (default)

Also extract the big picture:
- goal: one sentence describing what the user is ultimately trying to achieve (set to null if this input clearly belongs under an existing goal — use existing_goal_id instead)
- requires_replan: true if this changes priorities significantly

Return ONLY valid JSON in this format:
{
  "goal": "what the user is trying to achieve (or null if linking to existing goal)",
  "existing_goal_id": null,
  "requires_replan": true/false,
  "tasks": [
    { "content": "...", "layer": "...", "type": "...", "scope": "...", "cluster": "...", "duration_minutes": 25, "energy_required": "medium", "cognitive_load": "medium", "dopamine_profile": "quick_reward", "initiation_friction": "low", "completion_visibility": "visible", "execution_class": "linear", "thinking_objective": null, "thinking_output_format": null, "depends_on_index": null, "parent_item_id": null, "track_id": null, "complexity_score": 5.0, "suggested_status": "inbox", "confidence": 0.9 },
    ...
  ]
}"""

PLANNER_SYSTEM = """You are a cognitive execution coach. You decide what someone should work on RIGHT NOW and why.

LANGUAGE: Always output in English, regardless of input language.

You will receive:
1. All active tasks with their properties (layer, cluster, duration, energy, dependencies)
2. The user's big-picture goals (stored as context)
3. Recently completed tasks (for momentum)

Your job:
- Pick the ONE best task to do NOW
- Pick up to 2 tasks for AFTER
- Provide CLEAR REASONING for your choices

DECISION FRAMEWORK (in priority order):
1. DEPENDENCIES: If task B depends on task A, A must come first
2. STRATEGIC ALIGNMENT: Does this move the needle on the big picture?
3. MOMENTUM: After completing a task, the next one should feel like a natural continuation
4. ENERGY MATCH: Consider task energy requirements (don't stack 3 high-energy tasks)
5. QUICK WINS: If two tasks are equal priority, prefer the shorter one to build momentum
6. FRICTION MINIMIZATION: Pick what's easiest to START right now

Output valid JSON only:
{
  "now": [{"item_id": <int>, "content": "<string>"}],
  "next": [{"item_id": <int>, "content": "<string>"}, ...],
  "later": [{"item_id": <int>, "content": "<string>"}, ...],
  "reasoning": "2-3 sentences: WHY this task now, HOW it connects to the big picture, and WHAT completing it unlocks",
  "big_picture": "one sentence summary of what the user is working toward"
}"""


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


async def parse_input(raw_text: str, existing_context: str = "") -> dict:
    """Parse raw input into decomposed atomic tasks.
    Returns: {goal, requires_replan, tasks: [...]}
    """
    messages = [
        {"role": "system", "content": PARSER_SYSTEM},
    ]
    if existing_context:
        messages.append({"role": "user", "content": f"Context of what the user is already working on:\n{existing_context}"})
        messages.append({"role": "assistant", "content": "Understood. I'll factor in the existing context when decomposing the new input."})
    messages.append({"role": "user", "content": raw_text})

    try:
        raw_content = await _chat_completion(messages, temperature=0.2, max_tokens=2000)
    except Exception as e:
        raise RuntimeError(f"AI API error ({_get_model()}): {e}") from e

    text = _strip_code_fences(raw_content)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Model {_get_model()} returned invalid JSON. Raw response: {raw_content[:500]}"
        )

    # Normalize: if old single-item format, wrap it
    if "tasks" not in result:
        result = {
            "goal": result.get("content", ""),
            "requires_replan": result.get("requires_replan", False),
            "tasks": [result],
        }
    return result


async def generate_plan(items: list[dict], completed_recently: list[dict] = None, goal_context: str = "") -> dict:
    """Generate an execution plan with reasoning."""
    user_parts = []
    if goal_context:
        user_parts.append(f"Big picture context: {goal_context}")
    if completed_recently:
        user_parts.append(f"Recently completed (for momentum): {json.dumps(completed_recently)}")
    user_parts.append(f"Active items to plan:\n{json.dumps(items, indent=2)}")

    try:
        raw_content = await _chat_completion(
            [
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            temperature=0.3, max_tokens=1500,
        )
    except Exception as e:
        raise RuntimeError(f"AI API error ({_get_model()}): {e}") from e

    text = _strip_code_fences(raw_content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Model {_get_model()} returned invalid JSON in planner. Raw: {raw_content[:500]}"
        )


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    import tempfile, os as _os

    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        client = _get_client()
        with open(tmp_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1", file=f
            )
        return transcript.text
    except Exception as e:
        raise RuntimeError(f"Whisper transcription error: {e}") from e
    finally:
        _os.unlink(tmp_path)



# ── Onboarding Interview Pipeline ───────────────────────────────

ONBOARDING_INTERVIEW_SYSTEM = """You are a warm, ADHD-aware onboarding assistant for a Cognitive Execution System (CES).

Your job is to have a short, natural conversation (4-6 exchanges) to understand the user's life, work, current obligations, and challenges — so the system can help them from day one. You are NOT a therapist. You are practical and efficient.

LANGUAGE: The user may respond in English, Hindi, or Hinglish. Always output JSON in English. Be conversational and friendly but concise.

CONVERSATION FLOW:
You drive the conversation. After each user response, you:
1. Extract structured data from what they said (into "extracted" field)
2. Decide if you need to ask another question (into "next_question" field)
3. Set "done" to true when you have enough information

QUESTION SEQUENCE (adapt based on responses):

Q1 (ALWAYS first): "Tell me a bit about yourself — what does a typical day look like for you?"
- Extract: schedule signals (wake/work/sleep times), role (student/employee/freelancer/etc), energy hints, existing habits/time blocks
- If schedule is clear AND role is clear → skip to Q3
- If schedule is vague → ask Q2a
- If role is unclear → ask Q2b

Q2a (conditional — schedule unclear): "Got it. Roughly what time do you usually wake up, start working, and wind down for the day?"
- Extract: routine times → then proceed to Q3

Q2b (conditional — role unclear): "What keeps you busy most days — work, school, freelancing, something else?"
- Extract: role context → then decide if schedule still needed (→ Q2a) or proceed to Q3

Q3 (ALWAYS): "What are the main things on your plate right now? Projects, errands, responsibilities — anything you're juggling."
- Extract: current tasks/projects (as a list), clusters/domains, load sense
- This is HIGH VALUE — extract as many concrete tasks as possible

Q4 (ALWAYS): "What's the stuff you keep avoiding or struggling to start?"
- Extract: challenge_profile (starting/focusing/finishing/deciding), known friction tasks, avoidance patterns by domain

Q5 (ALWAYS — adapt wording based on Q3): "If you could get 2-3 things done this week, what would make the biggest difference?"
- If Q3 mentioned specific projects, reference them: "You mentioned X and Y — which matter most this week?"
- Extract: goals, urgency signals, weekly priorities

Q6 (ONLY if responses have been very brief — under 20 words per answer on average): "Anything else you want me to know about how you work best — or what usually goes wrong?"
- Extract: edge cases, medication schedule, sensory needs, preferences

EXTRACTION RULES:
- For schedule: Extract wake_time, work_start, work_end, sleep_time as "HH:MM" strings. If user says "around 7" → "07:00". If vague → null.
- For role: One of: student, employee, freelancer, business_owner, between_jobs, homemaker, other.
- For energy hints: Look for phrases like "I'm useless after lunch", "night owl", "morning person" → store as energy_overrides {time_description, energy_level}.
- For tasks: Extract as a list of {content, cluster, estimated_priority} objects. Be specific — use the user's own words.
- For challenge_profile: One or more of: starting_tasks, staying_focused, finishing_things, choosing_priorities.
- For goals: Extract as {title, urgency} objects.
- For avoidance_patterns: clusters/task types they avoid.

RESPONSE FORMAT — return ONLY valid JSON:
{
  "message": "Your conversational response to the user (the next question or a closing message)",
  "extracted": {
    "routine": {"has_routine": bool, "wake_time": "HH:MM"|null, "work_start": "HH:MM"|null, "work_end": "HH:MM"|null, "sleep_time": "HH:MM"|null} | null,
    "role": "string"|null,
    "energy_hints": [{"time_description": "after lunch", "energy": "low"}],
    "tasks": [{"content": "string", "cluster": "string", "estimated_priority": "high|medium|low"}],
    "challenge_profile": ["starting_tasks"],
    "avoidance_patterns": [{"domain": "string", "reason": "string"}],
    "goals": [{"title": "string", "urgency": "this_week|this_month|ongoing"}],
    "user_context": "string"|null
  },
  "next_question": "Q2a"|"Q2b"|"Q3"|"Q4"|"Q5"|"Q6"|null,
  "done": false
}

IMPORTANT:
- Only include data you actually extracted from THIS message. Use null/[] for fields not yet known.
- "message" should be warm and natural — not robotic. Use their name if they gave it.
- When done=true, the "message" should be an encouraging closing like "Great, I've got a good picture! Let me set things up for you."
- Keep questions short. ADHD users don't want walls of text.
- Don't ask more than 6 questions total. If you have enough after 4, stop.
"""


async def onboarding_interview_step(
    conversation_history: list[dict], user_message: str
) -> dict:
    """Process one step of the adaptive onboarding interview.

    Args:
        conversation_history: List of {role, content} from previous exchanges
        user_message: The user's latest response

    Returns: Parsed JSON with message, extracted data, next_question, done flag
    """
    messages = [
        {"role": "system", "content": ONBOARDING_INTERVIEW_SYSTEM},
    ]

    # Add conversation history
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the new user message
    messages.append({"role": "user", "content": user_message})

    try:
        raw_content = await _chat_completion(messages, temperature=0.4, max_tokens=1500)
    except Exception as e:
        raise RuntimeError(f"AI API error during onboarding ({_get_model()}): {e}") from e

    text = _strip_code_fences(raw_content)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Model {_get_model()} returned invalid JSON in onboarding. Raw: {raw_content[:500]}"
        )

    return result


async def get_onboarding_first_question() -> dict:
    """Generate the first onboarding question (no user input yet)."""
    messages = [
        {"role": "system", "content": ONBOARDING_INTERVIEW_SYSTEM},
        {"role": "user", "content": "START_ONBOARDING"},
    ]

    try:
        raw_content = await _chat_completion(messages, temperature=0.4, max_tokens=500)
    except Exception as e:
        # Fallback if AI is unavailable
        return {
            "message": "Hey! Tell me a bit about yourself \u2014 what does a typical day look like for you?",
            "extracted": {},
            "next_question": "Q1",
            "done": False,
        }

    text = _strip_code_fences(raw_content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "message": "Hey! Tell me a bit about yourself \u2014 what does a typical day look like for you?",
            "extracted": {},
            "next_question": "Q1",
            "done": False,
        }


# ── Expansion Pipeline ────────────────────────────────────────────

EXPANSION_SYSTEM = """You are an ADHD-aware task expansion engine.

LANGUAGE: Always output in English, regardless of input language (user may write in Hindi or Hinglish).

You receive a THINKING TASK and the user's NOTES from completing that thinking session.
Your job is to convert the thinking output into CONCRETE, ATOMIC, EXECUTABLE tasks.

RULES:
1. Each generated task MUST be ≤ 45 minutes, ideally 15-30 minutes.
2. Tasks must be SPECIFIC — start with a verb, have a clear deliverable.
3. Respect the user's decisions from their notes. Don't second-guess their choices.
4. Order tasks logically — what depends on what?
5. Include ADHD metadata for each task (same fields as the parser).
6. If the notes are unclear or incomplete, generate what you can and flag gaps.
7. Mark tasks as execution_class="linear" or "modular" — NEVER generate another "expanding" task from expansion (anti-loop).

Return ONLY valid JSON:
{
  "tasks": [
    { "content": "...", "layer": "...", "type": "task", "scope": "...", "cluster": "...", "duration_minutes": 25, "energy_required": "medium", "cognitive_load": "medium", "dopamine_profile": "quick_reward", "initiation_friction": "low", "completion_visibility": "visible", "execution_class": "linear", "depends_on_index": null, "confidence": 0.9 },
    ...
  ],
  "gaps": ["any unclear areas from the notes that need follow-up"]
}"""


async def expand_thinking_output(
    original_task: dict, notes: str, existing_context: str = ""
) -> dict:
    """Take a completed thinking task's notes and expand into concrete tasks."""
    user_content = f"""ORIGINAL THINKING TASK:
- Content: {original_task.get('content', '')}
- Objective: {original_task.get('thinking_objective', '')}
- Expected output format: {original_task.get('thinking_output_format', '')}
- Cluster: {original_task.get('cluster', '')}

USER'S THINKING OUTPUT / NOTES:
{notes}"""

    messages = [
        {"role": "system", "content": EXPANSION_SYSTEM},
    ]
    if existing_context:
        messages.append(
            {"role": "user", "content": f"Context of current work:\n{existing_context}"}
        )
        messages.append(
            {"role": "assistant", "content": "Understood. I'll factor in the context."}
        )
    messages.append({"role": "user", "content": user_content})

    try:
        raw_content = await _chat_completion(messages, temperature=0.2, max_tokens=2000)
    except Exception as e:
        raise RuntimeError(f"AI API error ({_get_model()}): {e}") from e

    text = _strip_code_fences(raw_content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Model {_get_model()} returned invalid JSON in expansion. Raw: {raw_content[:500]}"
        )
