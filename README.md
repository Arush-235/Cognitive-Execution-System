# CES - Cognitive Execution System

**Made with <3 for myself, added more <3 to make it useful for every creative & passionate soul out there who can do wonders but is distracted by every butterfly that flies around.**

## Complete Technical & Psychological Documentation

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [AI Pipelines](#5-ai-pipelines)
6. [The ADHD Scheduling Engine](#6-the-adhd-scheduling-engine)
7. [Circadian & Routine-Aware Energy Model](#7-circadian--routine-aware-energy-model)
8. [Priority & Planning System](#8-priority--planning-system)
9. [Work-Speed Personalization](#9-work-speed-personalization)
10. [The Thinking Task & Expansion Pipeline](#10-the-thinking-task--expansion-pipeline)
11. [Track System (Focus Lanes)](#11-track-system-focus-lanes)
12. [Adaptive Onboarding (Conversational Interview)](#12-adaptive-onboarding-conversational-interview)
13. [Check-in System & Two-Tier State Inference](#13-check-in-system--two-tier-state-inference)
14. [Goal Management & Alignment](#14-goal-management--alignment)
15. [Task Dependency DAG](#15-task-dependency-dag)
16. [Skip Taxonomy & Emotional Resistance](#16-skip-taxonomy--emotional-resistance)
17. [System Maturity Gates](#17-system-maturity-gates)
18. [API Reference](#18-api-reference)
19. [Frontend Architecture](#19-frontend-architecture)
20. [Psychological Foundations](#20-psychological-foundations)
21. [Data Flows & Lifecycle Diagrams](#21-data-flows--lifecycle-diagrams)
22. [Statistics & Analytics](#22-statistics--analytics)
23. [Wishful Thinking (Bucket List)](#23-wishful-thinking-bucket-list)
24. [Design System (LADDERS Theme)](#24-design-system-ladders-theme)
25. [PWA & Offline Support](#25-pwa--offline-support)
26. [Configuration & Deployment](#26-configuration--deployment)

---

## 1. Overview

CES (Cognitive Execution System) is a **Progressive Web App designed specifically for ADHD task management**. Unlike conventional to-do apps that assume executive function is working normally, CES is built around the neuropsychology of ADHD — accounting for initiation friction, dopamine-driven motivation, variable energy states, avoidance patterns, and the need for external cognitive scaffolding.

### Core Philosophy

Traditional productivity systems fail people with ADHD because they rely on:
- Self-generated motivation (ADHD brains are interest-driven, not importance-driven)
- Time estimation skills (ADHD causes time blindness)
- Sustained willpower for task switching (executive function is the core deficit)
- Linear planning (ADHD thinking is associative, not sequential)

CES addresses each of these by:
- **Externalizing executive function**: The system decides what to do next, not the user
- **Dopamine-aware sequencing**: Quick wins build momentum before tackling harder tasks
- **Friction-aware routing**: Low-friction tasks are surfaced when energy is low
- **Time calibration**: Learning actual work speed and adjusting estimates to the individual
- **Avoidance detection**: Tracking skip patterns and intervening before procrastination spirals
- **Circadian alignment**: Matching task cognitive demands to the user's energy curve

### What It Does

1. **Onboard** — On first launch, an AI-driven conversational interview (4-6 exchanges) learns the user's schedule, responsibilities, challenges, and priorities. This bootstraps the personalization engine from day one instead of starting cold.
2. **Capture** — The user dumps thoughts via text or voice. AI decomposes them into atomic, executable tasks with ADHD metadata, infers chronological dependencies between tasks, and links them to existing goals. Aspirational/bucket-list items are auto-detected and routed to Wishful Thinking.
3. **Check In** — Quick energy/focus self-reports (1-5 scales) ground the state inference in direct observation rather than behavioral proxies alone. When a recent check-in exists, it overrides circadian guesses with high confidence.
4. **Execute** — The system picks the best task for *right now* based on the user's cognitive state, energy, momentum, goal alignment, and time of day. Blocked tasks (whose dependencies aren't done) are shown but made non-selectable. The user chooses from the top 3 unblocked options.
5. **Plan** — A full view of all tasks organized by track (life domain) and cluster (topic), with dependency-aware ordering (prerequisites before dependents), status cycling, editing, and deletion.
6. **Goals** — Explicit big-picture objectives with status tracking (active/achieved/archived), target dates, priority ranking, and linked task counts. Goals feed into scheduling via alignment scoring.
7. **Wishes** — A passive bucket list for dreams, aspirations, and someday-maybe ideas. Items can be promoted to actionable status when the user is ready.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   PWA Frontend                       │
│  (Vanilla JS · HTML · CSS · Service Worker)          │
│                                                      │
│  ┌────────┐ ┌─────────┐ ┌──────┐ ┌──────────────┐  │
│  │Capture │ │ Execute │ │ Plan │ │   Wishes     │  │
│  │ Screen │ │  Screen │ │Screen│ │   Screen     │  │
│  └───┬────┘ └────┬────┘ └──┬───┘ └──────┬───────┘  │
│      │           │         │            │           │
└───────┼──────────────┼───────────────┼───────────────┘
        │              │               │
        ▼              ▼               ▼
┌─────────────────────────────────────────────────────┐
│                 FastAPI Backend                       │
│                                                      │
│  ┌────────┐  ┌──────────┐  ┌─────────┐  ┌────────┐  │
│  │ Ingest │  │Scheduler │  │ Planner │  │ Stats  │  │
│  │Pipeline│  │ Engine   │  │ Engine  │  │ Engine │  │
│  └───┬────┘  └────┬─────┘  └────┬────┘  └───┬────┘  │
│      │            │             │            │       │
│  ┌───▼────┐  ┌────▼─────┐  ┌───▼────┐       │       │
│  │ AI     │  │ Priority │  │  AI    │       │       │
│  │ Parser │  │ Scorer   │  │Planner │       │       │
│  └───┬────┘  └──────────┘  └────────┘       │       │
│      │                                       │       │
│  ┌───▼───────────────────────────────────────▼────┐  │
│  │               SQLite Database                   │  │
│  │  (items · task_history · work_patterns ·        │  │
│  │   user_persona · tracks · goals · plans)        │  │
│  └─────────────────────────────────────────────────┘  │
│                                                      │
│  ┌─────────────────────────────────────────────────┐  │
│  │     OpenAI API (configurable model, default      │  │
│  │              GPT-4o-mini)                        │  │
│  │  - Task decomposition & classification          │  │
│  │  - Execution planning                           │  │
│  │  - Thinking task expansion                      │  │
│  │  - Audio transcription (Whisper)                │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### File Structure

```
CES/
├── run.py                 # Uvicorn server entry point
├── requirements.txt       # Python dependencies
├── .env                   # API keys (OPENAI_API_KEY, GEMINI_API_KEY) + OPENAI_MODEL
├── backend/
│   ├── __init__.py
│   ├── app.py             # FastAPI app - all API endpoints + helpers
│   ├── ai.py              # AI integration - parser, planner, expansion, onboarding prompts
│   ├── scheduler.py       # ADHD-aware psychological scheduling engine
│   ├── planner.py         # Planning engine - full/partial replanning
│   ├── priority.py        # Priority scoring (lightweight + full ADHD-aware)
│   └── database.py        # SQLite schema, connection management, migrations, seed data
├── frontend/
│   ├── index.html         # Single-page app shell
│   ├── app.js             # All frontend logic (~1800 lines)
│   ├── style.css          # Complete styling (~1500 lines)
│   ├── sw.js              # Service worker for offline caching
│   ├── manifest.json      # PWA manifest
│   ├── icon-192.png       # App icon
│   └── icon-512.png       # Large app icon
└── ces.db                 # SQLite database (auto-created)
```

---

## 3. Technology Stack

| Component | Technology | Why |
|---|---|---|
| **Backend** | Python 3.11+ / FastAPI | Async, fast, typed, minimal boilerplate |
| **Database** | SQLite + aiosqlite | Zero config, WAL mode for concurrent reads, portable |
| **AI** | OpenAI + Google Gemini (configurable) | Multi-provider: OpenAI models (GPT-4o-mini default, reasoning models) and Gemini models (2.5-pro, 2.5-flash, etc.); selectable via Settings or `.env` |
| **Speech** | OpenAI Whisper | Accurate audio transcription for voice capture |
| **Frontend** | Vanilla JS/HTML/CSS | No build step, instant load, PWA-ready |
| **Server** | Uvicorn | ASGI server with hot reload |
| **PWA** | Service Worker + Manifest | Installable, offline-capable for static assets |

### Dependencies (`requirements.txt`)

```
fastapi>=0.100
uvicorn>=0.25
python-multipart>=0.0.6
openai>=1.0
aiosqlite>=0.19
python-dotenv>=1.0
google-genai>=1.0
```

---

## 4. Database Schema

The database (`ces.db`) uses SQLite in WAL (Write-Ahead Logging) mode with foreign keys enabled. It is auto-created on first server start via `init_db()`.

### Tables

#### `tracks` — Focus Lanes
```sql
id              INTEGER PRIMARY KEY
name            TEXT NOT NULL UNIQUE        -- "Work", "Personal", "Errands"
color           TEXT DEFAULT '#BF2020'      -- Hex color for UI theming
icon            TEXT DEFAULT '📁'           -- Emoji icon
time_available  TEXT                        -- e.g. "09:00-17:00"
allow_cross_track BOOLEAN DEFAULT 0        -- Show untracked tasks too?
sort_order      INTEGER DEFAULT 0
created_at      TIMESTAMP
```

Default tracks seeded: **Work** (💼 red #BF2020), **Personal** (🏠 purple #a78bfa), **Errands** (🛒 amber #f59e0b).

#### `items` — The Central Task Table
```sql
id                    INTEGER PRIMARY KEY
content               TEXT NOT NULL            -- Task description
layer                 TEXT                     -- strategic|tactical|operational|technical
type                  TEXT                     -- task|idea|problem|hypothesis|instruction|thinking
scope                 TEXT                     -- local|cluster|global
cluster               TEXT                     -- Domain label ("fundraising", "health", etc.)
track_id              INTEGER → tracks(id)     -- Which focus lane
status                TEXT DEFAULT 'inbox'     -- inbox|next|doing|done|backlog|wishful
priority              REAL DEFAULT 0.0         -- Computed score
energy_required       TEXT DEFAULT 'medium'    -- low|medium|high
duration_minutes      INTEGER DEFAULT 30       -- AI-estimated (capped at 45)
parent_id             INTEGER → items(id)      -- Hierarchical parent
goal_id               INTEGER                  -- Linked goal
sort_order            INTEGER DEFAULT 0

-- ADHD Scheduling Fields
cognitive_load        TEXT DEFAULT 'medium'    -- low|medium|high
dopamine_profile      TEXT DEFAULT 'neutral'   -- quick_reward|delayed_reward|neutral
initiation_friction   TEXT DEFAULT 'medium'    -- low|medium|high
completion_visibility TEXT DEFAULT 'visible'   -- visible|invisible
skip_count            INTEGER DEFAULT 0        -- Avoidance tracker
resistance_flag       BOOLEAN DEFAULT 0        -- Set when skip_count ≥ 2
dominant_skip_reason  TEXT                     -- Most frequent skip category for this task

-- Thinking/Expanding Fields
execution_class       TEXT DEFAULT 'linear'    -- linear|modular|expanding
expanded              BOOLEAN DEFAULT 0
source_idea_id        INTEGER → items(id)      -- Parent thinking task
thinking_objective    TEXT                      -- Goal of thinking session
thinking_output_format TEXT                     -- Expected deliverable
thinking_output       TEXT                      -- User's notes from session
revisit_count         INTEGER DEFAULT 0
thinking_time_budget_minutes  INTEGER DEFAULT 60  -- Max time for thinking sessions
thinking_time_spent   INTEGER DEFAULT 0        -- Actual cumulative time spent thinking

-- Complexity & Dependencies
complexity_score      REAL DEFAULT 5.0         -- 0.0–10.0 AI-assigned
depends_on            INTEGER → items(id)      -- Dependency DAG: blocked until depends_on is done

created_at            TIMESTAMP
```

#### `task_history` — Event Log
```sql
id                    INTEGER PRIMARY KEY
item_id               INTEGER → items(id)
event                 TEXT       -- started|completed|skipped|paused|resumed
elapsed_seconds       INTEGER    -- Actual time spent
user_energy           TEXT       -- Self-reported at event time
user_focus            TEXT
user_momentum         TEXT
time_of_day           TEXT       -- morning|afternoon|evening|night
skip_reason_category  TEXT       -- Categorized skip reason (not_now|too_hard|unclear|boring|anxious)
created_at            TIMESTAMP
```

#### `goals` — Big-Picture Objectives
```sql
id             INTEGER PRIMARY KEY
summary        TEXT NOT NULL          -- "Launch the Android app"
description    TEXT                   -- Optional longer description
cluster        TEXT                   -- Domain alignment
target_date    TEXT                   -- Optional deadline ("2024-06-01")
status         TEXT DEFAULT 'active'  -- active|achieved|archived
priority_rank  INTEGER DEFAULT 0     -- Higher = more important
created_at     TIMESTAMP
```

#### `plans` / `plan_items` — Execution Plans
```sql
plans:
  id       INTEGER PRIMARY KEY
  summary  TEXT
  created_at TIMESTAMP

plan_items:
  plan_id  INTEGER → plans(id)
  item_id  INTEGER → items(id)
  role     TEXT    -- now|next|later
```

#### `inbox` — Approval Queue
```sql
id          INTEGER PRIMARY KEY
raw_input   TEXT NOT NULL          -- Original user text
parsed_json TEXT                   -- AI decomposition result
approved    BOOLEAN DEFAULT 0
created_at  TIMESTAMP
```

#### `work_patterns` — Speed Learning Map
```sql
id                    INTEGER PRIMARY KEY
cluster               TEXT NOT NULL
layer                 TEXT NOT NULL
cognitive_load        TEXT NOT NULL
energy_required       TEXT NOT NULL
time_of_day           TEXT NOT NULL
duration_bucket       TEXT NOT NULL          -- "5-10min", "15-20min", etc.
sample_count          INTEGER DEFAULT 1
avg_elapsed_seconds   REAL NOT NULL
avg_estimated_seconds REAL NOT NULL
speed_ratio           REAL DEFAULT 1.0      -- actual/estimated
last_updated          TIMESTAMP
```

#### `user_persona` — Personalization Store
```sql
key        TEXT PRIMARY KEY        -- "work_speed_profile", "routine"
value      TEXT NOT NULL           -- JSON blob
updated_at TIMESTAMP
```

#### `system_state` — Global App State
```sql
key    TEXT PRIMARY KEY
value  TEXT
```
Keys: `current_active_task_id`, `last_plan_version`, `last_cluster_updated`, `active_track_id`, `onboarding_complete`.

#### `checkins` — Quick Energy/Focus Self-Reports
```sql
id          INTEGER PRIMARY KEY
energy      INTEGER NOT NULL       -- 1-5 scale (CHECK BETWEEN 1 AND 5)
focus       INTEGER NOT NULL       -- 1-5 scale (CHECK BETWEEN 1 AND 5)
mood        TEXT                   -- Optional mood descriptor
created_at  TIMESTAMP
```

Check-ins within the last 2 hours override behavioral state inference with high confidence (0.9). See §13.

#### `onboarding_messages` — Conversational Interview Log
```sql
id              INTEGER PRIMARY KEY
role            TEXT NOT NULL       -- 'assistant' or 'user'
content         TEXT NOT NULL       -- The message text
extracted_data  TEXT                -- JSON blob of data the AI extracted from this exchange
created_at      TIMESTAMP
```

Stores the full conversation history of the adaptive onboarding interview so context is preserved across exchanges. See §12.

---

## 5. AI Pipelines

CES uses three distinct AI pipelines, powered by a **configurable model** (default GPT-4o-mini, selectable via Settings or `OPENAI_MODEL` in `.env`). Supports both **OpenAI** and **Google Gemini** providers — the provider is auto-detected from the model name prefix (`gemini-*` → Gemini, everything else → OpenAI). OpenAI reasoning models (o3, o4-mini, o3-mini, o1, o1-mini) are automatically handled with adjusted API parameters.

### 5.1 Task Decomposition & Classification (Parser)

**File**: `backend/ai.py` — `parse_input()`  
**Model**: Configurable (default GPT-4o-mini), temperature 0.2  
**Input**: Raw user text + existing context (goals, tasks, tracks, persona)  
**Output**: Structured JSON with goal + array of classified tasks

#### What the Parser Does

1. **Receives raw brain dump** — could be "pack up my android app and then buy groceries and maybe figure out the quarterly budget"
2. **Decomposes into atomic tasks** — each completable in ≤ 45 minutes
3. **Classifies each task** with 15+ metadata fields for ADHD scheduling
4. **Links to existing context** — matches to existing goals, parent tasks, clusters, and tracks
5. **Detects ambiguity** — vague inputs become "thinking tasks" instead of forced decomposition
6. **Detects wishful thinking** — aspirational, non-urgent, bucket-list items ("go paragliding", "visit Japan") are tagged with `suggested_status: "wishful"` and routed to the Wishful Thinking list

#### Key Classification Fields

| Field | Purpose | Values |
|---|---|---|
| `layer` | Abstraction level | strategic, tactical, operational, technical |
| `cognitive_load` | Mental demand | low, medium, high |
| `dopamine_profile` | Reward timing | quick_reward, delayed_reward, neutral |
| `initiation_friction` | How hard to start | low, medium, high |
| `completion_visibility` | Is output tangible? | visible, invisible |
| `execution_class` | Task structure | linear, modular, expanding |
| `complexity_score` | Overall difficulty | 0.0–10.0 |
| `duration_minutes` | Time estimate | 5–45 min |
| `energy_required` | Physical/mental energy | low, medium, high |
| `suggested_status` | Initial routing | inbox (default), wishful (bucket list) |
| `depends_on_index` | Intra-batch dependency | 0-based index of prerequisite task in the same batch, or null |
| `depends_on_item_id` | Cross-batch dependency | ID of an existing item that must complete first, or null |

#### ADHD Classification Logic in the Prompt

- **No clear starting point** → `initiation_friction: high` → must decompose further
- **Duration > 45 min** → split into smaller chunks
- **Admin tasks** (emails, filing) → `cognitive_load: low`, `dopamine_profile: quick_reward`, `duration: 5-10min`
- **Creative work** → `cognitive_load: high`, `initiation_friction: medium-high`
- **Research/reading** → `cognitive_load: medium-high`, `completion_visibility: invisible`
- **Writing/coding** → `completion_visibility: visible`, `dopamine_profile: quick_reward`
- **Vague/strategic input** → `execution_class: expanding` → generates a **thinking task**
- **Aspirational/bucket-list input** ("I wanna...", "someday I'd like to...", experiences, far-off dreams) → `suggested_status: "wishful"` → routed to Wishful Thinking list

#### Dependency Extraction Rules

The parser enforces dependency detection and chronological ordering on every batch:

1. **Chronological sequencing** — Tasks are ordered in practical chronological sequence. The AI asks: "What must physically/logically happen first before the next step can begin?" For example, you must build an app before you can beta-test it, and beta-test before submitting to a store.

2. **Intra-batch dependencies** (`depends_on_index`) — When multiple tasks are produced from a single input, the parser evaluates whether they form a dependency chain. If task B literally cannot start until task A is finished, B's `depends_on_index` points to A's 0-based position in the batch. Example: `[build app (0), run beta test (1, depends_on_index=0), submit to store (2, depends_on_index=1)]`.

3. **Cross-batch dependencies** (`depends_on_item_id`) — When a new task depends on an existing item already in the system (injected via context), the parser sets `depends_on_item_id` to that item's ID.

4. **No over-depending** — Tasks that *can* be done in parallel must not have `depends_on` set. Only true sequential prerequisites get linked.

At insert time, `depends_on_index` is resolved to the actual database ID of the prerequisite task. If both `depends_on_item_id` and `depends_on_index` are set, the cross-batch link takes precedence.

#### Duration Estimation Calibration

The AI prompt includes strict duration guidelines to prevent overestimation (a common AI problem):

| Task Type | Duration |
|---|---|
| Quick admin (reply, update, file) | 5–10 min |
| Moderate (draft, review, organize) | 10–20 min |
| Deep work (code, write, research) | 20–40 min |

If a **user work-speed profile** exists (from completed tasks), it's injected into the prompt so the AI calibrates estimates to the individual. A user who finishes at 60% of estimated time gets lower estimates.

#### Context Injection

Before parsing, the system builds a rich context string containing:
- All available tracks (id, name, icon, `time_available`, `allow_cross_track` constraints)
- Active goals (id, cluster, summary)
- All non-done items grouped by cluster (with parent/goal links)
- Recently completed items (for continuity)
- User persona / work-speed profile

This lets the AI:
- Reuse existing cluster names instead of inventing new ones
- Set `parent_item_id` to link sub-tasks to existing items
- Set `existing_goal_id` to avoid creating duplicate goals
- Assign the correct `track_id` based on domain matching

#### Multilingual Input Support

All three AI prompts (parser, planner, expansion) accept input in **English, Hindi, or Hinglish** (Hindi-English mix). Output is always in **English** regardless of input language. Technical terms, proper nouns, and brand names are preserved as-is.

#### Model Compatibility Layer

`_chat_completion()` in `ai.py` is a unified async function that routes to the correct provider:

**OpenAI path** (via `_chat_kwargs()`):
- **Standard models** (GPT-4o, GPT-4o-mini, etc.): Uses `temperature` + `max_tokens`
- **Reasoning models** (o3, o4-mini, o3-mini, o1, o1-mini): Uses `max_completion_tokens` only (no temperature)
- All calls include `response_format: {"type": "json_object"}` to enforce structured output

**Gemini path** (via `_gemini_config()`):
- Uses `google.genai` SDK with async client (`client.aio.models.generate_content`)
- System instructions passed via `systemInstruction` config field
- JSON output enforced via `responseMimeType: "application/json"`
- OpenAI-style messages are automatically converted to Gemini's `Content`/`Part` format

**Audio transcription** always uses OpenAI Whisper (requires `OPENAI_API_KEY` regardless of AI model choice).

### 5.2 Execution Planning (Planner)

**File**: `backend/ai.py` — `generate_plan()`  
**Model**: Configurable (default GPT-4o-mini), temperature 0.3  
**Input**: Active items + completed recently + goal context  
**Output**: `{now, next, later, reasoning, big_picture}`

The planner decides what to work on RIGHT NOW by evaluating:
1. **Dependencies** — Task B depends on Task A? A comes first
2. **Strategic alignment** — Does this move the needle?
3. **Momentum** — After completing something, pick a natural continuation
4. **Energy match** — Don't stack 3 high-energy tasks
5. **Quick wins** — For equal priority, prefer faster tasks
6. **Friction minimization** — Pick what's easiest to START

### 5.3 Thinking Task Expansion

**File**: `backend/ai.py` — `expand_thinking_output()`  
**Model**: Configurable (default GPT-4o-mini), temperature 0.2  
**Input**: Original thinking task + user's notes + existing context  
**Output**: Array of concrete action tasks + gaps

This pipeline converts the output of a completed "thinking session" into executable tasks. It explicitly **never generates another expanding task** (anti-loop rule).

### 5.4 Audio Transcription

**File**: `backend/ai.py` — `transcribe_audio()`  
**Model**: Whisper-1  
**Input**: Audio blob (webm/ogg/mp4)  
**Output**: Transcribed text → fed into the parser pipeline

### 5.5 Task Deduplication (Two-Layer)

CES implements a **two-layer deduplication system** to prevent accidental duplicate task creation:

**Layer 1 — Raw Input Dedup (5-minute cache)**
- Normalizes raw input text (lowercase, collapse whitespace, strip punctuation)
- Maintains an in-memory cache mapping normalized text → timestamp
- Rejects identical submissions within a 5-minute window
- Cache entries auto-expire after 5 minutes

**Layer 2 — Per-Task Content Dedup (database check)**
- Before inserting each parsed task, normalizes its content
- Compares against all active (non-done, non-wishful) items in the database
- If a match is found, the duplicate task is silently skipped
- Prevents duplicates even when the same task appears across different brain dumps

Both layers use the same `_normalize_content()` function: lowercase, collapse whitespace, strip punctuation.

### 5.6 Error Handling Strategy

All AI calls are wrapped in try/except blocks with graceful degradation:

| Layer | Error Handling |
|---|---|
| `ai.py` — `generate_plan()` | Returns empty plan on failure, logs error |
| `ai.py` — `expand_thinking_output()` | Returns empty tasks array on failure |
| `ai.py` — `transcribe_audio()` | Returns empty string on failure |
| `ai.py` — JSON parsing | Falls back to `{}` on `JSONDecodeError` |
| `planner.py` — replan calls | Guarded; failures don't block ingestion |
| `app.py` — all endpoints | AI/replan failures logged, non-fatal to user flow |

The design principle: **AI failures should never crash the user's flow**. If the planner fails, tasks are still ingested. If expansion fails, the user keeps their thinking output.

### 5.7 Planner Context Enrichment

The planner (`backend/planner.py`) enriches `generate_plan()` calls with full context:

- **`completed_recently`**: Tasks completed in the last 48 hours (id, content, cluster, track_id) — gives the AI continuity about recent work
- **`goal_context`**: Active goals formatted as "id: summary (cluster)" — aligns planning with big-picture objectives

Both `run_full_replan()` and `run_partial_replan()` fetch this context via helper functions `_get_recently_completed()` and `_get_goal_context()` before calling the AI planner.

### 5.8 Onboarding Interview AI

**File**: `backend/ai.py` — `onboarding_interview_step()`, `get_onboarding_first_question()`  
**Model**: Configurable, temperature 0.4  
**Input**: Full conversation history + latest user message  
**Output**: Response message + extracted data + next question indicator

A dedicated AI pipeline powers the [Adaptive Onboarding](#12-adaptive-onboarding-conversational-interview) flow. It conducts a 4–6 exchange conversational interview, adapting its questions based on what the user has already revealed:

| Question | Trigger | Extracts |
|---|---|---|
| Q1 — "Tell me about a typical day" | Always first | Schedule signals, role, energy hints |
| Q2a — "What time do you wake up/wind down?" | Schedule unclear from Q1 | Routine times |
| Q2b — "What keeps you busy most days?" | Role unclear from Q1 | Role (student, employee, freelancer, etc.) |
| Q3 — "What's on your plate right now?" | Always | Task list with clusters & priorities |
| Q4 — "What do you keep avoiding?" | Always | Challenge profile, friction tasks, avoidance patterns |
| Q5 — "2–3 things that'd make the biggest difference this week?" | Always (adapted to context) | Goals with urgency levels |
| Q6 — "Anything else about how you work best?" | Only if user gives brief responses (<20 words avg) | Edge cases, preferences |

Each response is a JSON object containing the conversational `message`, an `extracted` data block, and a `next_question` pointer (or `done: true`). Extraction happens incrementally — each exchange's data is processed and stored immediately, so even an abandoned interview captures what was discussed.

---

## 6. The ADHD Scheduling Engine

**File**: `backend/scheduler.py` (~640 lines)

This is the psychological core of CES. It implements an ADHD-aware task scoring and selection system that accounts for the user's real-time cognitive state.

### 6.1 User State Inference (Two-Tier)

**Function**: `infer_user_state(completed_recently, history_events, routine, checkin)`

Infers the user's current cognitive state using a **two-tier** system. If the user has submitted a recent check-in (within 2 hours), that direct self-report takes precedence over behavioral guesses. Otherwise the system falls back to pattern-based inference.

**Tier 1 — Check-in (confidence 0.9)**

When a recent check-in exists, energy and focus are derived directly from the user's self-reported 1–5 scales:
- Energy: ≤2 → low, ≥4 → high, else medium
- Focus: ≤2 → scattered, ≥4 → locked_in, else normal

**Tier 2 — Behavioral inference (confidence 0.4–0.65)**

When no check-in is available, the system infers state from observable signals, starting at confidence 0.4 and accumulating evidence:
- **Energy**: Routine-aware circadian model (+0.1 confidence), or time-of-day default. If last completion included `user_energy`, use that (+0.15).
- **Focus**: ≥2 skips or ≥3 pauses → scattered (+0.1). ≥2 completions & 0 skips → locked_in (+0.15). Else normal.

**Both tiers** share the remaining dimensions:

| State Dimension | How It's Inferred | Values |
|---|---|---|
| **Energy** | Check-in scale, circadian model, or last self-report | low, medium, high |
| **Momentum** | Count of recent completions in last 2 hours | none (0), building (1-2), high (3+) |
| **Focus** | Check-in scale, or skip/pause patterns in history | scattered, locked_in, normal |
| **Time of Day** | Clock-based | morning (6-12), afternoon (12-17), evening (17-21), night (21-6) |
| **Work Minutes** | Sum of elapsed_seconds from recent history | Integer minutes |
| **Confidence** | Check-in path 0.9, behavioral 0.4–0.65 | Float 0.0–1.0 |

**Energy decay** applies regardless of tier: after 45 continuous work minutes, high → medium. After 75 minutes, medium → low.

Confidence **dampens** scoring extremes — low-confidence states pull task scores toward the mean (3.0), preventing wild swings when the system is guessing.

### 6.2 Circadian Strategy Map

```python
CIRCADIAN_MAP = {
    "morning":   ideal_cognitive=high,   ideal_friction=medium, strategy=planning_deep_work
    "afternoon": ideal_cognitive=medium,  ideal_friction=low,    strategy=execution_structured
    "evening":   ideal_cognitive=low,     ideal_friction=low,    strategy=light_admin_review
    "night":     ideal_cognitive=medium,  ideal_friction=low,    strategy=creative_low_stakes
}
```

### 6.3 Task Scoring Formula

**Function**: `score_task(item, user_state, goal_ids)`

```
score = priority_weight
      + energy_match
      + dopamine_alignment
      - friction_penalty
      + momentum_bonus
      + avoidance_adjustment
      + goal_alignment
      + thinking_convergence
```

Then: `damped_score = 3.0 + (raw_score - 3.0) × confidence`

#### Component Breakdown

| # | Component | Range | Detail |
|---|---|---|---|
| 1 | `priority_weight` | 0–5.5 | Layer weight (strategic=4, tactical=3, operational=2, technical=1) + status bonus (doing +1.5, next +0.5) |
| 2 | `energy_match` | -3 to +1.5 | Perfect match=+1.5, demand ≤ energy=+1.0, over-demand=diff × 1.5 (negative) |
| 3 | `dopamine_alignment` | -0.5 to +2.0 | Varies by momentum × profile (see below) |
| 4 | `-friction_penalty` | 0 to ~5.85 | `friction_level × 0.5 × momentum_mult × focus_mult` |
| 5 | `momentum_bonus` | 0–1.5 | Short task +0.5, visible completion +0.5, high momentum +0.5 |
| 6 | `avoidance_adjustment` | -2.0 to 0 | Based on `dominant_skip_reason` category weight × skip count (see [Skip Taxonomy](#16-skip-taxonomy--emotional-resistance)) |
| 7 | `goal_alignment` | 0 or +1.0 | +1.0 if the task's `goal_id` matches any active goal |
| 8 | `thinking_convergence` | -3.0 to 0 | Thinking tasks that have consumed ≥75% of their time budget get penalized (-1.0 at 75%, -3.0 at 100%) to encourage convergence |

**Dopamine Alignment Matrix**

| Momentum | quick_reward | neutral | delayed_reward |
|---|---|---|---|
| none | +2.0 | +0.5 | -0.5 |
| building | +1.5 | +1.0 | +0.5 |
| high | +0.8 | +1.0 | +1.5 |

*Psychological basis*: ADHD brains need immediate dopamine hits to overcome inertia. Once momentum builds, they can sustain effort on delayed-reward tasks.

**Friction Penalty Multipliers**

- Momentum: none=1.5×, building=1.0×, high=0.6×
- Focus: scattered=1.3×

*Psychological basis*: Initiation friction is the #1 barrier for ADHD. When momentum is zero, high-friction tasks are nearly impossible to start.

**Confidence Damping**

The final score is pulled toward the mean (3.0) by the state confidence factor. With a check-in (confidence=0.9), scores stay close to their raw values. With behavioral-only inference (confidence=0.4–0.65), extreme scores are moderated, preventing the system from over-committing to uncertain state reads.

### 6.4 Selection Rules (Maturity-Gated)

**Function**: `select_next_task(items, user_state, completed_clusters, maturity_level, active_goal_ids)`

Rules are progressively unlocked as the system matures (see [System Maturity Gates](#17-system-maturity-gates)):

**Always active (cold+)**:
1. **Dependency Blocking** — Before scoring, blocked tasks (whose prerequisites aren't done) are removed from the candidate pool entirely. They appear in the response as `blocked_options` but cannot be selected. Blocking is transitive — if A blocks B and B blocks C, C is also blocked.
2. **Start Bias** — When momentum=none, filter to: `friction ≤ medium`, `duration ≤ 25min`, `no resistance_flag`. This ensures the user starts with something achievable.
3. **Energy Matching** — When energy=low, cap cognitive demand to ≤ medium.

**Warming (3+ completions)**:
4. **Momentum Mode** — After completions, gradually allow harder tasks.
5. **Dopamine Sequencing** — The scoring naturally sequences: quick win → meaningful → optional reward.

**Stable (10+ completions)**:
6. **Anti-Avoidance** — Resistance-flagged tasks are deferred unless they score 2+ points above the next option.
7. **Thinking Task Rules**:
   - Only eligible when: energy=high, morning/afternoon, momentum ≠ none, focus ≠ scattered
   - Max 1 thinking task active at a time
   - Peak conditions (morning + high energy): +1.5 bonus
   - Anti-loop: revisit_count ≥ 2 → `-0.5 × revisits` penalty

**Mature (25+ completions)**:
8. **Goal Alignment** — Tasks linked to active goals get a +1.0 scoring boost.
9. **Resistance Interventions** — Category-specific strategies surface when skip patterns emerge (see [Skip Taxonomy](#16-skip-taxonomy--emotional-resistance)).
10. **Strategic Scoring** — Full layer weighting kicks in.

**Dopamine Sandwich** (stable+) — When a thinking task is selected, the engine wraps it:
- **Before**: Quick-win task (≤15min, quick_reward, low friction)
- **After**: Concrete execution task (visible completion, low-medium cognitive)

*This creates a dopamine → effort → dopamine pattern that makes deep thinking sustainable.*

### 6.5 Break Enforcement

**Function**: `needs_break(user_state)`

| Work Duration | Action |
|---|---|
| ≥ 60 min | **Enforced break** — 10 min, blocks task selection |
| ≥ 45 min | **Suggested break** — 5 min, shown as banner |
| < 45 min | No break |

### 6.6 Avoidance Detection & Intervention

**Function**: `handle_skip(item, skip_category)`

Each skip is now tagged with a **category** from the [Skip Taxonomy](#16-skip-taxonomy--emotional-resistance) (not_now, too_hard, unclear, boring, anxious). The category is stored on the item as `dominant_skip_reason` and drives both scoring adjustments and targeted interventions.

| Skip Count | Response |
|---|---|
| 1 | Normal skip, category recorded, no intervention |
| 2+ | Sets `resistance_flag`; triggers `get_resistance_intervention()` with category-specific strategies |
| 3+ | Strong scoring penalty via category weight; for `not_now`, surfaces "You've deferred this N times — is it actually important?" |

For thinking tasks specifically, skips with `too_hard` or `unclear` trigger a **scope reduction** intervention: "Just 15 minutes, write 3 bullet points." This converts an amorphous blob into a concrete micro-task.

*Psychological basis*: Repeated avoidance signals that the task representation is wrong — it's either too big, too vague, or emotionally loaded. Categorized skips let the system intervene with the right strategy instead of applying a one-size-fits-all nudge.*

---

## 7. Circadian & Routine-Aware Energy Model

### 7.1 Default Model (No Routine)

When no routine is configured:
```
morning   → energy: high
afternoon → energy: medium
evening   → energy: low
night     → energy: low
```

### 7.2 Routine-Aware Model

When the user provides their schedule during onboarding (wake, work start, work end, sleep times), the system uses a personalized circadian curve:

**Function**: `_routine_energy(current_hour, routine)` in `scheduler.py`

```
      Energy
  high │     ┌──────┐
       │    ╱│first  │  ← work hours first half
  med  │───╱ │half   ├──────────────┐ ← evening second wind
       │  ╱  └──┬────┘              │
  low  │─╱     │    ↓post-lunch    └──────┐
       │╱wake  │    dip                   │sleep
       └───────┴──────────────────────────┴──→ Time
```

| Time Window | Energy | Reasoning |
|---|---|---|
| Before wake / after sleep | low | Not awake |
| Wake to wake+1h | medium | Warming up, cortisol rising |
| Wake+1h to wake+2h | high | Peak cortisol / alertness |
| Work start to midpoint | high | Focused work window |
| Work midpoint to work end | medium | Post-lunch circadian dip |
| Work end to work end+1h | low | Decompression period |
| 2h before sleep | low | Winding down |
| Evening (after decompression, before wind-down) | medium | ADHD "second wind" phenomenon |

This model accounts for the **ADHD second wind** — a well-documented phenomenon where ADHD individuals often experience a burst of productive energy in the evening after the daytime executive function demands subside.

---

## 8. Priority & Planning System

### 8.1 Ingestion-Time Priority

**File**: `backend/priority.py` — `compute_priority(item)`

When no user state is available (during task ingestion), a lightweight formula is used:

```
priority = layer_weight + urgency + dopamine - friction + 0.5
```

| Factor | Values |
|---|---|
| Layer weight | strategic=4, tactical=3, operational=2, technical=1 |
| Urgency | +1 if status is next/doing |
| Dopamine | quick_reward=+0.5, neutral=0, delayed_reward=-0.3 |
| Friction | low=0, medium=-0.5, high=-1.5 |

### 8.2 Full ADHD-Aware Priority

When user state is available (at execution time), the full `score_task()` from the scheduler is used. See §6.3.

### 8.3 Approval Gate

**File**: `backend/planner.py` — `needs_approval(parsed)`

Tasks require manual approval if:
- `layer == strategic AND scope == global` (big organizational changes)
- `confidence < 0.75` (AI is uncertain about decomposition)

### 8.4 Replanning Logic

**File**: `backend/planner.py` — `determine_replan_action(parsed)`

| Condition | Action |
|---|---|
| `scope=local + layer=technical` | No replan |
| `scope=cluster OR layer=tactical` | Partial replan (cluster only) |
| `scope=global + layer=strategic` | Full replan (all items) |
| Default operational/technical | No replan |

**Full Replan**: Fetches all non-done items (limit 50), recomputes priorities, sends to AI planner for now/next/later assignment.

**Partial Replan**: Same but scoped to a single cluster.

---

## 9. Work-Speed Personalization

CES learns the user's actual work speed over time and uses this to improve time estimates.

### 9.1 Data Collection

On every task completion, `_update_work_pattern()` records:
- Cluster, layer, cognitive load, energy level, time of day
- Duration bucket (0-5min, 5-10min, 10-15min, ..., 60min+)
- Actual elapsed seconds vs estimated seconds
- Running average speed ratio (actual/estimated)

### 9.2 Persona Rebuilding

Every 5 completions, `_rebuild_persona()` aggregates patterns into a profile:

```json
{
  "global_speed_ratio": 0.72,       // User finishes at 72% of estimated time
  "speed_by_cognitive_load": {
    "low": 0.55,                     // Very fast at low-cog tasks
    "medium": 0.75,
    "high": 0.92                     // Closer to estimate for hard tasks
  },
  "speed_by_time_of_day": {
    "morning": 0.65,                 // Fastest in morning
    "afternoon": 0.80,
    "evening": 0.95                  // Slowest in evening
  },
  "speed_by_cluster": {
    "coding": 0.60,                  // Very fast at coding
    "admin": 0.70,
    "writing": 1.10                  // Slower at writing
  },
  "preferred_duration_bucket": "10-15min",
  "total_datapoints": 47
}
```

### 9.3 Feedback Loop

The persona is injected into the AI parser context as natural language:
```
USER WORK-SPEED PROFILE:
  - This user is FAST — they complete tasks in ~72% of estimated time. REDUCE your estimates.
  - Very fast at low-cognitive tasks (55% of estimate)
  - Most productive time: morning
  - Slowest time: evening
  - Fast domains: coding, admin
  - Slower domains: writing
  - Preferred work session length: 10-15min
```

This creates a continuous learning loop:
```
Complete task → Record speed → Update persona → Inject into AI → Better estimates → Complete task
```

---

## 10. The Thinking Task & Expansion Pipeline

### 10.1 The Problem

ADHD brains often receive vague, strategic ideas — "figure out the fundraising strategy" or "decide on the tech stack". Traditional apps either:
- Force decomposition (producing meaningless sub-steps)
- Leave it as a single giant task (paralyzing to start)

### 10.2 The Solution: Two-Phase Tasks

**Phase 1: Thinking Session**
1. AI detects vague/strategic input → sets `execution_class: expanding`
2. Generates a THINKING task with:
   - `thinking_objective`: "Decide which 3 features to build for MVP"
   - `thinking_output_format`: "A ranked list of 3 features with 1-line justification each"
3. User works in a time-boxed session (20-30 min) and writes their notes
4. Timer tracks elapsed time like any other task

**Phase 2: Expansion**
1. Upon completion, user sees an expansion UI instead of auto-loading next task
2. User pastes their thinking notes
3. AI expansion pipeline (`EXPANSION_SYSTEM`) converts notes into concrete action tasks
4. Generated tasks are linked to the source thinking task via `source_idea_id`
5. Gaps are flagged — areas where the notes were unclear

### 10.3 Anti-Loop Safeguard

The expansion pipeline is explicitly forbidden from generating new `expanding` tasks. If a thinking session produces output that's still too vague, the pipeline flags it as a gap rather than creating an infinite decomposition loop.

The scheduler tracks `revisit_count` for thinking tasks. After 3 revisits:
- A warning is shown: "This has been revisited 3 times. Consider: force a decision, discard it, or archive."
- Scoring penalty: `-0.5 × revisit_count`

### 10.4 Dopamine Sandwich for Thinking Tasks

Because thinking tasks are high cognitive load and have delayed rewards, the scheduler wraps them in a **dopamine sandwich**:

```
1. Quick Win (5-15 min, quick_reward, low friction)  ← Dopamine boost
2. Thinking Task (20-30 min)                         ← Hard work, sustained by momentum
3. Execution Task (visible completion)               ← Reward + concrete progress
```

The UI displays this sandwich structure explicitly so the user understands the plan.

---

## 11. Track System (Focus Lanes)

### 11.1 Concept

Tracks are **focus lanes** — life domains that help the user compartmentalize their attention. This is critical for ADHD because:
- Context-switching between life domains is cognitively expensive
- Seeing work tasks while trying to handle personal errands creates overwhelm
- Time-of-day filtering (e.g., errands only 8am-9pm) prevents inappropriate scheduling

### 11.2 Default Tracks

| Track | Color | Icon | Cross-Track | Time |
|---|---|---|---|---|
| Work | #BF2020 (red) | 💼 | No | 09:00-17:00 |
| Personal | #a78bfa (purple) | 🏠 | Yes (shows untracked) | — |
| Errands | #f59e0b (amber) | 🛒 | No | 08:00-21:00 |

#### Track Assignment Rules (from AI prompt)

The parser uses explicit rules to assign tasks to tracks:
- **Errands**: Physical-world tasks — shopping, organizing desk, cleaning, watering plants, picking up items, running errands
- **Work**: Job/professional tasks — coding, meetings, emails, invoicing, client work
- **Personal**: Digital projects, hobbies, personal growth, learning, creative pursuits
- The key distinction: if a task requires **physically going somewhere or handling physical objects** in a non-work context, it's Errands — otherwise, hobby/growth/digital tasks are Personal

### 11.3 How Tracks Work

1. **AI Assignment**: During ingestion, the parser assigns `track_id` based on task domain
2. **Track Bar**: The UI shows a pill bar for track switching
3. **Filtered Scheduling**: `/next` filters candidates by active track
4. **Cross-Track**: If a track has `allow_cross_track=True`, untracked tasks are included
5. **Plan View**: Groups tasks by track → cluster hierarchy
6. **CSS Theming**: Each track applies `--track-accent` for color-coordinated UI

---

## 12. Adaptive Onboarding (Conversational Interview)

### 12.1 Purpose

On first launch (when `system_state.onboarding_complete` is not set), CES presents a full-screen conversational interface. Instead of a static form, an AI-driven interview (4–6 exchanges) learns the user's schedule, responsibilities, challenges, and priorities through natural conversation. This bootstraps personalization from day one rather than requiring weeks of usage data.

### 12.2 Interview Flow

The onboarding AI (see [Section 5.8](#58-onboarding-interview-ai)) conducts an adaptive conversation that branches based on the user's responses:

```
GET /onboarding/start
  → AI generates first question ("Tell me about a typical day")
  → User responds (text or voice)
    → POST /onboarding/message (or /onboarding/audio)
      → AI extracts structured data from each response
      → _process_onboarding_extraction() stores data incrementally
      → AI decides next question based on what's been covered
  → ... repeat 3-5 more exchanges ...
  → AI signals done=true
    → _finalize_onboarding()
      → Seeds goals table from extracted goals
      → Runs extracted tasks through full parse_input() for ADHD metadata
      → Stores routine, challenge profile, avoidance patterns to user_persona
      → Sets system_state.onboarding_complete = "1"
  → Dismiss overlay, show main app
```

### 12.3 What Gets Extracted

| Data | Stored In | Purpose |
|---|---|---|
| Wake/work/sleep times | `user_persona.routine` | Circadian energy model |
| Role (student, employee, etc.) | `user_persona.user_context` | Context for AI prompts |
| Energy hints ("I crash after lunch") | `user_persona.energy_overrides` | Refines energy predictions |
| Task list with priorities | `items` table (via parser) | Pre-loads the task queue |
| Challenge profile | `user_persona.challenge_profile` | Guides intervention selection |
| Avoidance patterns | `user_persona.avoidance_domains` | Seeds resistance detection |
| Goals with urgency | `goals` table | Activates goal-aligned scheduling |
| Full transcript | `user_persona.onboarding_transcript` | Available for future re-analysis |

Each exchange is stored in the `onboarding_messages` table with any extracted data, so the conversation can be reviewed or re-processed if needed. Even a partially completed interview captures whatever was discussed — the system doesn't lose data if the user abandons mid-flow.

### 12.4 Seeding Logic

- **Goals**: Inserted into the `goals` table with deduplication by summary. Goals with `this_week` urgency get `priority_rank = 1`.
- **Tasks**: Each extracted task is run through the full `parse_input()` AI pipeline to get proper ADHD metadata (layer, cognitive load, friction, etc.). If the AI parser fails, tasks are inserted directly with sensible defaults (`layer='operational'`, `duration_minutes=20`).
- **Routine**: If the user describes a schedule, it's stored as `{has_routine: true, wake_time, work_start, work_end, sleep_time}`. If no schedule emerges, defaults to `{has_routine: false}`.

---

## 13. Check-in System & Two-Tier State Inference

### 13.1 Purpose

Check-ins are quick self-reports that let CES ground its state inference in direct observation rather than behavioral guesswork. A single check-in takes 5 seconds and dramatically improves task selection accuracy.

### 13.2 How It Works

When the user opens the Execute screen and no recent check-in exists (within 2 hours), a modal prompts for:

| Field | Type | Scale | Default |
|---|---|---|---|
| Energy | Slider | 1 (depleted) – 5 (wired) | 3 |
| Focus | Slider | 1 (scattered) – 5 (locked in) | 3 |
| Mood | Text | Free-form (optional) | null |

The check-in is stored in the `checkins` table and immediately influences task selection for the current session.

### 13.3 Two-Tier Integration

The scheduling engine's `infer_user_state()` accepts an optional `checkin` parameter. When present and recent:

- Energy and focus are derived from the check-in scales (not circadian guesses)
- State confidence jumps to **0.9** (vs 0.4–0.65 for behavioral inference)
- Higher confidence means scoring extremes are preserved, giving the scheduler a clearer signal

Without a check-in, the system falls back to behavioral inference — circadian models, skip patterns, completion history — at lower confidence. See [Section 6.1](#61-user-state-inference-two-tier) for the full inference logic.

### 13.4 Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `POST /checkin` | Submit | Clamps energy/focus to [1,5], stores check-in, returns mapped state labels |
| `GET /checkin/latest` | Query | Returns the most recent check-in within 2 hours, or `{has_recent: false}` |

---

## 14. Goal Management & Alignment

### 14.1 Purpose

Goals are explicit big-picture objectives that anchor task scheduling. Without goals, the system optimizes locally (easiest task for current state). With goals, it balances ease against strategic alignment — tasks that move the needle on an active goal get a scoring boost.

### 14.2 Goal Lifecycle

```
Create (POST /goals)
  → Active (default)
    → Achieved (manual, via PATCH)
    → Archived (soft-delete via DELETE, or manual via PATCH)
```

Each goal has:

| Field | Purpose |
|---|---|
| `summary` | Short title |
| `description` | Optional detail |
| `cluster` | Domain grouping (matches task clusters) |
| `target_date` | Optional deadline |
| `status` | active, achieved, or archived |
| `priority_rank` | Integer for ordering (higher = more important) |

### 14.3 Linked Task Counts

The `GET /goals` endpoint returns each active goal with `pending_tasks` and `done_tasks` counts — showing progress at a glance. These counts are derived from items whose `goal_id` matches the goal.

### 14.4 Scheduling Integration

In the scoring formula ([Section 6.3](#63-task-scoring-formula)), `goal_alignment` contributes **+1.0** to any task whose `goal_id` matches an active goal. This is gated behind `mature` system maturity (25+ completions) to avoid premature optimization before the system has enough data to score well.

### 14.5 Onboarding Seeding

During onboarding, extracted goals are automatically inserted with deduplication. This means goal-aligned scheduling can activate as soon as the user completes enough tasks, without requiring manual goal entry.

### 14.6 Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /goals` | List | Active goals ordered by priority_rank DESC, with task counts |
| `POST /goals` | Create | Creates a new active goal |
| `PATCH /goals/{id}` | Update | Updates summary, description, status, target_date, or priority_rank |
| `DELETE /goals/{id}` | Archive | Soft-deletes by setting status to "archived" |

---

## 15. Task Dependency DAG

### 15.1 Purpose

Many real-world tasks have natural prerequisites: you can't submit a store listing before building the app, or send a review before writing the draft. CES detects these dependencies automatically during parsing and enforces them at scheduling time — blocked tasks are visible in the UI but non-selectable, preventing the user from starting something before its prerequisites are complete.

### 15.2 How Dependencies Are Created

**AI extraction** — The parser evaluates every batch for dependency chains (see [Dependency Extraction Rules](#dependency-extraction-rules)):
- **Intra-batch**: `depends_on_index` links tasks within the same input (resolved to real IDs at insert time)
- **Cross-batch**: `depends_on_item_id` links new tasks to existing items in the system

Each item stores a single `depends_on` column pointing to its prerequisite's ID. This forms a directed acyclic graph (DAG) across the task set.

### 15.3 Transitive Blocking

The `/next` endpoint computes the full set of blocked task IDs before scoring:

1. Build a dependency map from all active items with `depends_on` set
2. Chase chains up to **10 levels deep** to find all transitive dependencies (if A → B → C, and A isn't done, both B and C are blocked)
3. For each item, recursively check if any ancestor in its chain is not done — if so, it's blocked
4. Cycle guard prevents infinite loops in malformed dependency graphs

Blocked items are excluded from the scoring pool. Up to 2 blocked items are returned in the response as `blocked_options` for visibility.

### 15.4 Plan View Ordering

In the Plan screen, tasks within each cluster are topologically sorted: prerequisites appear before their dependents. Items with no dependencies come first, followed by items whose dependencies are already placed. If cycles exist (from manual edits), remaining items are appended in original order.

Each task with a dependency shows a 🔗 badge and "depends on #X" in its metadata, so the user can see the chain.

### 15.5 Schema

Each item has a single `depends_on INTEGER` column referencing another item's ID. This is a simple single-parent model — a task can depend on at most one prerequisite. For multi-step chains, dependencies are chained (A → B → C).

---

## 16. Skip Taxonomy & Emotional Resistance

### 16.1 Purpose

Not all skips are equal. "Not right now" is fundamentally different from "makes me anxious." CES categorizes every skip so it can apply the right intervention strategy instead of a generic nudge.

### 16.2 Categories

| Key | Label | Emoji | Scoring Weight |
|---|---|---|---|
| `not_now` | Not right now | ⏰ | 0.0 (no penalty) |
| `too_hard` | Feels too hard | 🧱 | -0.5 |
| `unclear` | Not sure what to do | ❓ | -0.3 |
| `boring` | Too boring | 😴 | -0.2 |
| `anxious` | Makes me anxious | 😰 | -1.0 |

The weight influences the `avoidance_adjustment` scoring component. Higher-weight categories (anxiety) suppress the task more aggressively, directing the user to easier alternatives while the intervention is offered.

### 16.3 Category-Specific Interventions

**Function**: `get_resistance_intervention(item, skip_count, category)`

Interventions activate when `skip_count >= 2`:

| Category | Intervention Type | Strategy |
|---|---|---|
| `too_hard` | `decompose` | "Break this into a 10-minute starter step, or lower the bar" |
| `unclear` | `clarify` | "Spend 5 minutes writing down what you think the first step is" |
| `boring` | `gamify` | "Set a 15-minute timer and race yourself, pair with music" |
| `anxious` | `comfort` | "Imagine the worst realistic outcome; just do the first 2 minutes" |
| `not_now` (count < 3) | `reschedule` | Normal deferral |
| `not_now` (count >= 3) | `avoidance_detected` | "You've deferred this N times. Is this actually important?" |

For **thinking tasks** specifically, `too_hard` or `unclear` skips trigger a scope reduction: "Just 15 minutes, write 3 bullet points." This converts an open-ended thinking session into a concrete micro-deliverable.

### 16.4 Tracking

Each item accumulates a `dominant_skip_reason` — the most recent skip category — which feeds into the `avoidance_adjustment` scoring component. The `task_history` table records each skip event's `skip_reason_category` for analytics.

The frontend presents the categories as a selection modal during skip, one tap each with emoji labels.

---

## 17. System Maturity Gates

### 17.1 Purpose

A fresh CES instance has no data about the user. Applying the full scoring algorithm — goal alignment, resistance interventions, strategic layer weighting — would produce noisy, unhelpful results. Maturity gates progressively unlock scheduling features as the system accumulates completion data.

### 17.2 Levels

| Level | Completions | What's Active |
|---|---|---|
| **Cold** | 0–2 | Start Bias, Energy Matching, Dependency Blocking |
| **Warming** | 3–9 | + Momentum Mode, Dopamine Sequencing |
| **Stable** | 10–24 | + Anti-Avoidance, Thinking Task Rules, Dopamine Sandwich |
| **Mature** | 25+ | + Goal Alignment, Resistance Interventions, Strategic Scoring |

### 17.3 How It Works

`get_system_maturity(db)` counts completed tasks (`status='done'`) and returns the current level. This is checked at the start of each `/next` request and passed to `select_next_task()`, which gates its rule application accordingly.

The progression is automatic and irreversible within a session — once the user has 25 completions, all features are active. The thresholds are based on having enough behavioral data for each feature to be useful rather than noisy.

---

## 18. API Reference

### Ingestion

| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Ingest text → decompose → store |
| `/ingest/audio` | POST | Ingest audio file → Whisper → decompose → store |
| `/approve` | POST | Approve/reject an inbox item |

**POST /ingest**
```json
// Request
{ "text": "pack up my android app and buy groceries" }

// Response
{
  "status": "accepted",
  "item_ids": [1, 2],
  "parsed": { "goal": "...", "tasks": [...] },
  "task_count": 2,
  "goal": "Complete app packaging and grocery shopping",
  "replan": "none"
}
```

### Execution

| Endpoint | Method | Description |
|---|---|---|
| `/next` | GET | Get top 3 task options (ADHD-scored) + up to 2 blocked options |
| `/select` | POST | Lock a chosen task as "doing" |
| `/complete` | POST | Mark task done, log history, surface next |
| `/override` | POST | Skip task with reason + skip category, track avoidance |
| `/expand` | POST | Expand thinking task notes → concrete tasks |

**GET /next**
```json
{
  "options": [
    {
      "id": 3,
      "content": "Reply to client email",
      "duration_minutes": 10,
      "energy_required": "low",
      "energy_emoji": "⚡",
      "cognitive_load": "low",
      "cognitive_emoji": "🧘",
      "dopamine_profile": "quick_reward",
      "dopamine_label": "Quick win",
      "initiation_friction": "low",
      "friction_emoji": "🟢",
      "execution_class": "linear",
      "is_thinking": false,
      "cluster": "admin",
      "track_id": 1,
      "blocked": false
    }
  ],
  "blocked_options": [
    {
      "id": 7,
      "content": "Submit to Play Store",
      "blocked": true,
      "blocked_by": 5,
      "duration_minutes": 15,
      "energy_required": "low",
      "energy_emoji": "⚡",
      "cluster": "android-app"
    }
  ],
  "big_picture": "Launch product by Q3",
  "user_state": {
    "energy": "high",
    "focus": "normal",
    "momentum": "none",
    "time_of_day": "morning",
    "work_minutes_since_break": 0,
    "confidence": 0.9
  }
}
```

**POST /override** (skip)
```json
// Request
{ "item_id": 3, "reason": "not feeling it", "skip_category": "not_now" }
```

### Plan & Items

| Endpoint | Method | Description |
|---|---|---|
| `/plan` | GET | Full plan view grouped by track → cluster |
| `/items/{id}` | PATCH | Update item fields |
| `/items/{id}` | DELETE | Delete item |
| `/inbox` | GET | List pending inbox items |

### Wishful Thinking

| Endpoint | Method | Description |
|---|---|---|
| `/wishlist` | GET | List all items with status `wishful` |
| `/wishlist/promote` | POST | Promote a wishful item to `inbox` or `next` |

**POST /wishlist/promote**
```json
// Request
{ "item_id": 42, "to_status": "inbox" }

// Response
{ "status": "promoted", "item_id": 42, "new_status": "inbox" }
```

### Tracks

| Endpoint | Method | Description |
|---|---|---|
| `/tracks` | GET | List all tracks + active track ID |
| `/tracks` | POST | Create new track |
| `/tracks/{id}` | PATCH | Update track properties |
| `/tracks/{id}` | DELETE | Delete track (tasks become untracked) |
| `/tracks/active` | POST | Set/clear active track filter |

### Onboarding

| Endpoint | Method | Description |
|---|---|---|
| `/onboarding/status` | GET | Check if onboarding is complete + routine |
| `/onboarding/start` | GET | Begin conversational interview, returns first AI question |
| `/onboarding/message` | POST | Send user response, get next AI question + extracted data |
| `/onboarding/audio` | POST | Voice message → Whisper transcription → same as /message |

**GET /onboarding/start**
```json
// Response
{ "message": "Hey! Tell me about a typical day...", "done": false }
```

**POST /onboarding/message**
```json
// Request
{ "message": "I usually wake up around 8, work from home as a freelancer..." }

// Response
{
  "message": "Got it! What are the main things on your plate right now?",
  "done": false,
  "extracted": {
    "routine": { "has_routine": true, "wake_time": "08:00" },
    "role": "freelancer"
  }
}
```

### Check-in

| Endpoint | Method | Description |
|---|---|---|
| `/checkin` | POST | Submit energy/focus self-report |
| `/checkin/latest` | GET | Get most recent check-in (within 2h) |

**POST /checkin**
```json
// Request
{ "energy": 4, "focus": 2, "mood": "tired but wired" }

// Response
{ "status": "ok", "energy": "high", "focus": "scattered" }
```

### Goals

| Endpoint | Method | Description |
|---|---|---|
| `/goals` | GET | List active goals with pending/done task counts |
| `/goals` | POST | Create a new goal |
| `/goals/{id}` | PATCH | Update goal fields (summary, status, target_date, etc.) |
| `/goals/{id}` | DELETE | Archive goal (soft-delete) |

### Skip Categories

| Endpoint | Method | Description |
|---|---|---|
| `/skip-categories` | GET | List all skip categories with labels, emoji, and weights |

### Daily Intention & Weekly Review

| Endpoint | Method | Description |
|---|---|---|
| `/daily/intention` | GET | Get today's intention + top 3 active goals |
| `/daily/intention` | POST | Set today's focus goal and/or free-text intention |
| `/review/weekly` | GET | Weekly stats: completed, skipped, skip categories, goal progress, productivity trap detection |

### Stats

| Endpoint | Method | Description |
|---|---|---|
| `/stats/weekly` | GET | Weekly stats, complexity, improvement, persona |

### Settings

| Endpoint | Method | Description |
|---|---|---|
| `/settings` | GET | Get current model name + masked API keys |
| `/settings` | POST | Update model and/or API keys (persisted to `.env`) |

**GET /settings**
```json
{
  "model": "gpt-4o-mini",
  "api_key_masked": "sk-ab...xYz1",
  "gemini_api_key_masked": "AIza...xYz1"
}
```

**POST /settings**
```json
// Request (all fields optional)
{ "model": "gemini-2.5-flash", "api_key": "sk-...", "gemini_api_key": "AIza..." }

// Response
{ "status": "ok", "model": "gemini-2.5-flash" }
```

Allowed models:
- **OpenAI**: `gpt-5.3`, `gpt-5.3-mini`, `o4-mini`, `o3`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini`
- **Gemini**: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-lite`

Invalid models return HTTP 400. OpenAI key format validated (`sk-` prefix), Gemini key format validated (20+ alphanumeric chars). Changes are written to `.env` and applied immediately.

**GET /stats/weekly**
```json
{
  "tasks_completed": 12,
  "total_estimated_minutes": 240,
  "total_actual_minutes": 168,
  "time_saved_minutes": 72,
  "time_saved_hours": 1.2,
  "top_savings": [
    { "content": "Draft proposal", "estimated_min": 30, "actual_min": 15, "saved_min": 15 }
  ],
  "streak_days": 5,
  "all_time_tasks": 47,
  "improvement_pct": 20,
  "last_week_tasks": 10,
  "complexity": {
    "average": 4.8,
    "weighted_score": 3.92,
    "distribution": { "low": 4, "medium": 5, "high": 3 }
  },
  "persona": { ... }
}
```

---

## 19. Frontend Architecture

### 19.1 Five-Screen Navigation

The app has five main screens accessible via the bottom navigation bar:

**Capture Screen** (`#view-input`)
- Text input area (Enter to submit, Shift+Enter for newline)
- Voice recording button (MediaRecorder API → Whisper)
- Ingest result card (auto-hides after 4s)
- Pending approvals section
- **Settings gear icon** (⚙️ in header) — opens a popup to configure AI model (OpenAI or Gemini), OpenAI API key, and Gemini API key

**Execute Screen** (`#view-execute`) — Five sub-states:
1. **Check-in** — If no recent check-in exists, a modal prompts for energy (1–5 slider) and focus (1–5 slider). Can be skipped. Posted to `/checkin`.
2. **Empty** — No tasks queued. "What's Next?" button. If wishful items exist, a random one is suggested with a "Promote & Do It" button
3. **Choose** — Top 3 unblocked task options as cards with full ADHD metadata. Recommended task starred. Below the options, up to 2 **blocked tasks** appear with a `🔒 BLOCKED` tag, dashed border, dimmed styling, and no click handler (non-selectable). Skip modal shows categorized skip reasons (emoji buttons for each category).
4. **Ready** — Selected task detail view with reasoning, badges, after queue, recovery suggestion, break banner, avoidance warning, resistance intervention (if applicable)
5. **Timer** — Countdown ring (SVG), pause/resume, overtime tracking (+XX:XX), vibration on completion

**Plan Screen** (`#view-plan`)
- All tasks grouped by Track → Cluster, topologically sorted by dependencies within each cluster
- Track-colored left borders
- Tasks with dependencies show a 🔗 badge and "depends on #X" in metadata
- Status cycling (⟳ button), edit modal, delete modal
- **Goals section** at the top — lists active goals with pending/done counts, add/archive controls
- Pending inbox items at bottom
- Wishful items visible with purple status labels

**Wishes Screen** (`#view-wishes`)
- Dedicated view for all wishful/bucket-list items
- Each wish displayed as a card with purple left border and 🌟 icon
- "Activate" button promotes a wish to inbox status
- Delete button removes the wish
- Empty state guides user to capture dreams via the Capture tab

### 19.2 UI Indicators

| Indicator | Meaning |
|---|---|
| ⚡ / 🔥 / 💪 | Energy: low / medium / high |
| 🧘 / 🧠 / 🔬 | Cognitive load: low / medium / high |
| 🟢 / 🟡 / 🔴 | Initiation friction: low / medium / high |
| ⬜ / 🟨 / 🟩 | Momentum: none / building / high |
| 🧠 THINK | Thinking task badge |
| 📐 modular/expanding | Non-linear execution class |
| ★ RECOMMENDED | Top-scored option |
| 🌟 WISH | Wishful/bucket-list item |
| 🔒 BLOCKED | Task whose dependency isn't done yet |
| 🔗 | Task has a dependency (shown in plan view) |

### 19.3 Timer System

- Countdown from `duration_minutes × 60` seconds
- SVG ring visualization (stroke-dashoffset animation)
- Pause/resume toggle
- **Overtime mode**: After reaching 0, continues counting as +MM:SS with visual indicator
- On completion: vibration (if available), elapsed time sent to `/complete`
- For thinking tasks: timer label changes to "THINK", shows objective and expected output format

### 19.4 Weekly Stats Popup

Shown automatically on app open if `tasks_completed > 0`. Contains:
- Hero number (minutes/hours saved)
- Tasks completed this week
- All-time total tasks
- Estimated vs actual time
- Streak days
- Improvement trend vs last week (↑/↓ %)
- Complexity distribution bar (green/yellow/red stacked bar)
- Average complexity score
- Biggest time-saving wins
- Work profile insights (from persona)

### 19.5 Track Bar

Horizontal pill bar below nav. Each track pill shows icon + name, styled with track color. Active track has solid fill; inactive tracks are outlined. User taps to switch. "All" option clears the filter.

---

## 20. Psychological Foundations

### 20.1 ADHD Executive Function Model

CES is designed around the **Barkley Model of ADHD** which identifies the core deficit as impaired executive function, specifically:

| Executive Function | How CES Compensates |
|---|---|
| **Working Memory** | Externalizes all tasks into the database. The user never has to remember what's next. |
| **Time Management** | Timer with visual countdown. Duration estimates calibrated to actual speed. Overtime tracking prevents unbounded time sinks. |
| **Self-Regulation** | Break enforcement. Skip tracking. Avoidance detection with gentle interventions. |
| **Self-Motivation** | Dopamine-aware task sequencing. Quick wins build momentum. Visible completion boosts. Stats showing progress. |
| **Task Initiation** | Friction-aware routing. Low-friction starters when momentum is zero. System picks the task, reducing decision paralysis. |

### 20.2 Dopamine Economics

ADHD brains have dysregulated dopamine signaling, making them **interest-driven rather than importance-driven**. CES accounts for this:

- **Quick Reward** tasks produce immediate dopamine (seeing a visible output, crossing something off)
- **Momentum None → Building → High** maps to the dopamine ramp-up needed for sustained focus
- The **Dopamine Sandwich** around thinking tasks ensures dopamine supply before and after cognitively demanding work
- **Completion visibility** matters: tasks with tangible outputs (`visible`) are scored higher because they produce rewarding feedback
- **Stats and streaks** provide meta-level dopamine rewards for consistent effort

### 20.3 Initiation Friction & The Activation Energy Problem

Starting a task requires "activation energy" — for ADHD brains, this threshold is pathologically high. CES addresses this:

1. **Friction scoring**: Every task has an `initiation_friction` rating (low/medium/high)
2. **Start Bias rule**: When momentum=none, ONLY low/medium friction, ≤25min tasks are offered
3. **Gradual escalation**: As momentum builds, harder tasks become available
4. **Decomposition suggestion**: When a task is repeatedly skipped (avoidance detected), the system suggests breaking it into a smaller first step

### 20.4 Avoidance Patterns & Procrastination Loops

ADHD procrastination isn't laziness — it's an emotional regulation failure. The task triggers anxiety/overwhelm → avoidance → guilt → more avoidance. CES breaks this loop:

- **Skip tracking**: Every skip is logged with a reason
- **Resistance flag**: Set after 2 skips, changes scheduling behavior
- **Scope reduction**: For thinking tasks, suggests "just 15 min, 3 bullet points"
- **Decomposition prompt**: "Break it into a 10-min starter step"
- **No shame**: The skip modal asks "Why skip?" not "Why are you avoiding this?"

### 20.5 Circadian Rhythm & ADHD

ADHD individuals often have **delayed circadian rhythms** (Delayed Sleep Phase Syndrome is comorbid in ~75% of ADHD adults). The routine-aware energy model accounts for:

- **Slow morning ramp-up**: First hour after wake = medium, not high
- **Peak window**: 1-2 hours after wake and first half of work hours
- **Post-lunch dip**: Universal circadian trough, worse for ADHD
- **Decompression**: Transition period after work where executive function drops
- **Second wind**: The paradoxical evening energy burst common in ADHD
- **Wind-down**: 2 hours before sleep, energy should be low to support sleep hygiene

### 20.6 Context Switching & Tracks

ADHD brains have impaired **set-shifting** (the ability to switch between mental contexts). The track system:

- Reduces cognitive load by filtering to one domain at a time
- Prevents the overwhelm of seeing all life tasks simultaneously
- Allows time-bounded availability (errands only during business hours)
- Uses visual theming (colors, icons) to reinforce the current context

### 20.7 Decision Fatigue & The "Choose From 3" Design

ADHD is associated with **decision paralysis** — too many options leads to no action. CES mitigates this:

- Only 3 options presented (not the full task list)
- System pre-scores and recommends the top option
- Each option shows rich metadata so the decision is informed
- One-tap selection → immediate start

### 20.8 Time Blindness & The Timer

ADHD involves fundamentally impaired time perception. The timer addresses this:

- **Visual countdown ring**: Externalizes time passage
- **Overtime tracking**: Prevents hyperfocus time sinks by making overrun visible
- **Work-speed learning**: System learns the user's actual pace and adjusts
- **Break enforcement**: Prevents burnout from unnoticed continuous work

### 20.9 Complexity Scoring & Growth Tracking

The `complexity_score` (0-10) serves two purposes:

1. **Scheduling**: Higher complexity tasks are only surfaced when energy and focus are sufficient
2. **Growth feedback**: Weekly stats show complexity distribution (low/medium/high) and weighted completion scores, letting users see they're tackling increasingly challenging work over time

---

## 21. Data Flows & Lifecycle Diagrams

### 21.1 Task Ingestion Flow

```
User Input (text or voice)
    │
    ▼
[Voice?] ──yes──▶ Whisper Transcription ──▶ Raw Text
    │ no                                       │
    ▼                                          ▼
Build Context Summary                  Build Context Summary
(goals, items, tracks, persona)       (goals, items, tracks, persona)
    │                                          │
    ▼                                          ▼
GPT-4o-mini Parser ◀─────────────────────────────
(or configured model)
    │
    ▼
{goal, tasks[{content, layer, type, cognitive_load, dopamine_profile,
              initiation_friction, complexity_score, track_id,
              depends_on_index, depends_on_item_id, ...}]}
    │
    ▼
Approval Gate ──needs approval──▶ Inbox (pending)
    │ auto-approved                     │
    ▼                             [User approves]
Dedup Check (per-task content)         │
    │                                  ▼
    ▼                           Dedup Check
Insert Tasks to DB (batch)             │
    │                                  ▼
    ▼                           Insert Tasks to DB
Resolve depends_on_index → actual IDs (second pass)
    │
    ▼
Validate depends_on_item_id → existing DB IDs
    │
    ▼
Compute Priorities
    │
    ▼
Determine Replan Action
    │
    ├─ none ── return
    ├─ partial ── Replan Cluster
    └─ full ── Replan All
```

### 21.2 Task Execution Flow

```
GET /next
    │
    ▼
Check Active Track Filter
    │
    ▼
Active Task Lock? ──yes──▶ Return Locked Task
    │ no
    ▼
Fetch Candidates (≤30, filtered by track, status in next/inbox/backlog)
    │
    ▼
Load Latest Check-in (within 2h)
    │
    ▼
Load Routine ─────────────────────────▶ _routine_energy()
    │                                         │
    ▼                                         ▼
Infer User State (Two-Tier) ◀──────── Energy Level
  ├── Check-in exists? → Tier 1 (confidence 0.9)
  └── No check-in? → Tier 2 behavioral (confidence 0.4-0.65)
    │
    ▼
Break Check ──enforced──▶ Return Break Screen
    │ ok
    ▼
Build Dependency Map (depends_on → item_id)
    │
    ▼
Chase Transitive Chains (up to 10 levels)
    │
    ▼
Compute Blocked Set (_is_blocked with cycle guard)
    │
    ▼
Separate: schedulable_items | blocked_items
    │
    ▼
Get System Maturity Level (cold/warming/stable/mature)
    │
    ▼
Score Schedulable Tasks (ADHD formula × confidence damping)
    │
    ▼
Apply Selection Rules (maturity-gated)
    │
    ▼
Top 3 Options + up to 2 Blocked ──▶ Frontend Choose Screen
    │
    │ [User selects unblocked option]
    ▼
POST /select
    │
    ▼
Lock Task (status=doing, system_state=active_task_id)
    │
    ▼
Frontend Ready Screen + Timer
    │
    │ [User completes]
    ▼
POST /complete
    │
    ├──▶ Log to task_history
    ├──▶ Update work_patterns
    ├──▶ Rebuild persona (every 5 completions)
    ├──▶ Clear active lock
    ├──▶ Unblock dependents (now eligible for scheduling)
    │
    ├── [Thinking task?] ──▶ Show Expansion UI ──▶ POST /expand ──▶ Generate sub-tasks
    │
    └── [Regular task?] ──▶ GET /next (momentum continues)
```

### 21.3 Skip & Avoidance Flow

```
User clicks Skip
    │
    ▼
Skip Category Modal → Select reason
  ⏰ Not right now | 🧱 Too hard | ❓ Unclear | 😴 Boring | 😰 Anxious
    │
    ▼
POST /override (item_id, reason, skip_category)
    │
    ▼
handle_skip(item, skip_category)
    │
    ├── skip_count += 1
    ├── dominant_skip_reason = skip_category
    ├── if skip_count ≥ 2: resistance_flag = true
    │
    ▼
get_resistance_intervention(item, skip_count, category)
    │
    ├── too_hard → decompose: "Break into 10-min starter step"
    ├── unclear → clarify: "5 min writing first step"
    ├── boring → gamify: "15-min timer, race yourself"
    ├── anxious → comfort: "Worst realistic outcome? Just 2 min"
    ├── not_now (≥3) → avoidance_detected: "Deferred N times — important?"
    │
    ▼
Log skip to task_history (with skip_reason_category)
    │
    ▼
Move task to backlog
    │
    ▼
GET /next (fresh options, avoidance_adjustment applied in scoring)
```

### 21.4 Personalization Learning Loop

```
Task Completed
    │
    ▼
_update_work_pattern()
    │
    ├── Match against (cluster, layer, cognitive_load, energy, tod, bucket)
    ├── Update running average: avg_elapsed, avg_estimated, speed_ratio
    │
    ▼
Every 5 completions → _rebuild_persona()
    │
    ├── Compute global_speed_ratio (weighted)
    ├── Speed by cognitive_load
    ├── Speed by time_of_day
    ├── Speed by cluster
    ├── Preferred duration bucket
    │
    ▼
Store in user_persona(key="work_speed_profile")
    │
    ▼
Next ingestion → _get_context_summary()
    │
    ├── Reads persona
    ├── Generates natural language speed profile
    ├── Injects into AI parser context
    │
    ▼
AI calibrates duration estimates to user's proven pace
```

---

## 22. Statistics & Analytics

### 22.1 Weekly Stats (`/stats/weekly`)

**Task Metrics**:
- `tasks_completed`: Count this week (deduplicated by first completion per item)
- `all_time_tasks`: Lifetime completion count
- `last_week_tasks`: Prior week for comparison
- `improvement_pct`: Percentage change week-over-week (null if no prior data)
- `streak_days`: Consecutive days with at least 1 completion (max look-back: 30 days)

**Time Metrics**:
- `total_estimated_minutes`: Sum of AI-estimated durations
- `total_actual_minutes`: Sum of elapsed seconds at completion
- `time_saved_minutes`: max(0, estimated - actual)
- `top_savings`: Top 5 tasks with largest time savings

**Complexity Metrics**:
- `complexity.average`: Mean complexity score of completed tasks
- `complexity.weighted_score`: Weighted by speed_ratio (actual/estimated), higher = tackled hard tasks efficiently
- `complexity.distribution`: `{low: count(0-3), medium: count(4-6), high: count(7-10)}`

**Persona**: Full work-speed profile if 5+ datapoints exist.

### 22.2 Streak Calculation

Streaks count backward from today, checking each date has at least one completion:
```
Today (completion?) → Yes → Yesterday (completion?) → Yes → 2 days ago → No → Streak = 2
```

### 22.3 Improvement Trend

Compares deduplicated task completion count between current week and previous week:
```
improvement_pct = ((this_week - last_week) / last_week) * 100
```

---

## 23. Wishful Thinking (Bucket List)

The Wishful Thinking system provides a passive, deprioritized space for dreams, aspirations, and someday-maybe ideas — tasks that aren't urgent, aren't definitive, and shouldn't clutter the active task pipeline.

### 23.1 How Items Become Wishful

1. **AI Auto-Detection**: The parser prompt includes heuristics for wishful items:
   - Language patterns: "I wanna...", "would be cool to...", "bucket list:", "someday I'd like to..."
   - Nature: life experiences, adventures, non-urgent aspirations, far-off goals
   - The AI sets `suggested_status: "wishful"` and the item is inserted with that status
2. **Manual Assignment**: Users can change any item's status to "wishful" via the edit modal in Plan view

### 23.2 How Wishful Items Surface

- **Execute empty state**: When the task queue is empty and the user has nothing to do, `/next` returns a random wishful item as a suggestion. The user can promote it with one tap or skip it.
- **Wishes screen**: Dedicated view showing all wishful items with promote and delete actions.

### 23.3 Promotion Flow

```
Wishful Item
    │
    ├── "Activate" (Wishes screen) ──▶ POST /wishlist/promote {to_status: "inbox"}
    │                                       │
    │                                       ▼
    │                                  Item moves to inbox → enters normal scheduling
    │
    └── "Promote & Do It" (Execute empty) ──▶ POST /wishlist/promote {to_status: "next"}
                                                    │
                                                    ▼
                                               Item moves to next → available immediately
```

### 23.4 Database

- Status `'wishful'` added to the items CHECK constraint
- Wishful items are excluded from the `/next` candidate query (status IN `next/inbox/backlog`)
- They appear in `/plan` view with a purple status label
- Dedicated `/wishlist` endpoint queries `WHERE status = 'wishful'`

### 23.5 ADHD Psychology

The Wishful Thinking system addresses a specific ADHD pattern: **brain dump guilt**. ADHD brains constantly generate ideas, but mixing aspirational dreams with actionable tasks creates overwhelm and unrealistic expectations. By providing a guilt-free "someday" space:
- Users can capture without committing
- Dreams don't pollute the active queue
- When the user has unexpected free time, a wish surfaces as a low-pressure suggestion
- Promoting a wish is an intentional act, not an accident

---

## 24. Design System (LADDERS Theme)

CES uses the **LADDERS Design System** — a clean, light-mode-first design language with red as the primary brand color.

### 24.1 Color Palette

| Token | Value | Usage |
|---|---|---|
| `--brand-red` | `#C61919` | Brand identity, theme-color meta |
| `--accent` | `#BF2020` | Primary actions, active states, links |
| `--accent-light` | `#d42525` | Hover states |
| `--accent-dark` | `#a01515` | Pressed states, borders |
| `--accent-bg` | `rgba(191,32,32,0.08)` | Subtle accent backgrounds |
| `--bg` | `#ffffff` | Page background |
| `--surface` | `#f5f5f7` | Card/container backgrounds |
| `--surface2` | `#eaeaef` | Secondary surfaces, inputs |
| `--border` | `#d5d5dc` | Borders, dividers |
| `--text` | `#1a1a2e` | Primary text |
| `--text-dim` | `#6b6b80` | Secondary/muted text |
| `--green` | `#1a7f37` | Success, completion, streaks |
| `--orange` | `#f59e0b` | Warnings, friction indicators |
| `--red` | `#dc2626` | Danger, errors, delete |
| `--info` | `#3b82f6` | Informational, break banners |

### 24.2 Typography

System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`

No custom web fonts loaded — ensures instant text rendering and matches OS conventions.

### 24.3 Spacing & Radii

| Token | Value |
|---|---|
| `--radius` | `12px` (cards, modals) |
| `--radius-sm` | `8px` (buttons, inputs) |
| Pill radius | `20px` (badges, track pills) |
| Max width | `480px` (mobile-first single column) |

### 24.4 Design Principles

- **Surface layering over shadows**: Cards use background color differentiation (`--surface`, `--surface2`) and subtle borders rather than drop shadows
- **Light overlays with blur**: Modals use `rgba(0,0,0,0.35)` backdrop with `blur(4px)`
- **Red-dominant brand identity**: Primary actions, active nav, recommended cards all use accent red
- **Semantic color coding**: Status dots and labels use a consistent color language (green=doing/done, red=accent/next, amber=inbox, gray=backlog, purple=wishful)
- **Optimistic & animated**: Fade-in animations, scale transitions, pulse effects for active states

---

## 25. PWA & Offline Support

### 25.1 Manifest

```json
{
  "name": "CES",
  "short_name": "CES",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#C61919"
}
```

Installable as a standalone app on mobile and desktop. White background with red brand theme for the status bar. App icons feature a **red (#C61919) circle with a brain emoji (🧠)** extracted from the Apple Color Emoji font.

### 25.2 Service Worker Strategy

**File**: `frontend/sw.js`

- **Install**: Caches core assets (`/`, `/style.css`, `/app.js`, `/manifest.json`)
- **Fetch**: Cache-first for static assets, network-only for API calls
- **Activate**: Cleans up old cache versions

API paths that bypass the cache: `/ingest`, `/approve`, `/next`, `/complete`, `/override`, `/plan`, `/inbox`, `/wishlist`.

---

## 26. Configuration & Deployment

### 26.1 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes* | OpenAI API key — required for OpenAI models + Whisper audio transcription |
| `GEMINI_API_KEY` | Yes* | Google Gemini API key — required only when using `gemini-*` models. Get one at https://aistudio.google.com/apikey |
| `OPENAI_MODEL` | No | AI model to use (default: `gpt-4o-mini`). OpenAI: `gpt-5.3`, `gpt-5.3-mini`, `o4-mini`, `o3`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini`. Gemini: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-lite` |
| `CES_DB_PATH` | No | SQLite database path (default: `ces.db`) |

\* At minimum one API key is required. `OPENAI_API_KEY` is always needed for voice transcription (Whisper). If using a Gemini model, `GEMINI_API_KEY` is also required.

Set in `.env` file (loaded by `python-dotenv`).

### 26.2 Running the Server

```bash
# setup the virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY (and optionally OPENAI_MODEL, GEMINI_API_KEY)

# Run
python run.py
# Server starts at http://0.0.0.0:8000
```

The server uses Uvicorn with `reload=True` for development (auto-restarts on file changes).

### 26.3 Database

SQLite database is auto-created on first server start. To reset:
```bash
rm ces.db
python run.py   # Fresh database with seeded tracks and default state
```

### 26.4 Static Files

The FastAPI app serves the frontend directly:
- `/` → `frontend/index.html`
- `/style.css` → `frontend/style.css`
- `/app.js` → `frontend/app.js`
- `/manifest.json`, `/sw.js`, icons → corresponding files in `frontend/`

No build step required. The frontend is production-ready as-is.

---

## Appendix: The Psychological Scoring Example

To illustrate how the scheduling engine works in practice, consider this scenario:

**User State**: Morning, just opened app, no tasks completed yet.
```
energy: high, momentum: none, focus: normal, tod: morning
```

**Task A**: "Reply to client email" — low cognitive, quick_reward, low friction, 10min
```
priority_weight = 2.0 (operational)
energy_match    = +1.0 (user energy high, demand low — overshoot but ok)
dopamine_align  = +2.0 (quick_reward + momentum=none → max boost)
friction_penalty= -0.75 (low friction × 1.5 momentum multiplier)
momentum_bonus  = +1.0 (short + visible)
────────────────────────
SCORE = 5.25
```

**Task B**: "Architect new database schema" — high cognitive, delayed_reward, high friction, 40min
```
priority_weight = 1.0 (technical)
energy_match    = +1.5 (perfect match: high energy, high demand)
dopamine_align  = -0.5 (delayed_reward + momentum=none → penalty)
friction_penalty= -2.25 (high friction × 1.5 momentum multiplier)
momentum_bonus  = +0.0 (long, but visible)
────────────────────────
SCORE = -0.25
```

**Task C**: "Review PR comments" — medium cognitive, neutral, medium friction, 15min
```
priority_weight = 1.0 (technical)
energy_match    = +1.0 (high energy, medium demand — ok)
dopamine_align  = +0.5 (neutral + momentum=none)
friction_penalty= -1.5 (medium friction × 1.5 momentum multiplier)
momentum_bonus  = +1.0 (short + visible)
────────────────────────
SCORE = 2.0
```

**Result**: Task A (5.25) > Task C (2.0) > Task B (-0.25)

The system correctly identifies that replying to the email is the ideal starter — it's quick, easy to begin, and produces immediate dopamine. The database architecture task, despite being a good energy match, is deprioritized because starting from zero momentum on a high-friction, delayed-reward task is psychologically unrealistic for ADHD.

After completing Task A and building momentum, Task B's score would improve significantly:
- Dopamine alignment: -0.5 → +0.5 (momentum=building allows delayed_reward)
- Friction penalty: -2.25 → -1.0 (momentum=building reduces multiplier to 1.0×)
- New score: ~2.5 — now competitive with other options

This is the **momentum escalation** the system is designed to produce.
