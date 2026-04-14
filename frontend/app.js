/* CES  -  Cognitive Execution System  -  Frontend */

const API = '';  // same origin

// ── State ────────────────────────────────────────────────────────

let currentNow = null;
let mediaRecorder = null;
let isRecording = false;
let _busy = false;  // global guard against double-tap / race conditions

// Timer state
let _timerInterval = null;
let _timerSecondsLeft = 0;
let _timerTotalSeconds = 0;

// Track state
let _tracks = [];
let _activeTrackId = null;
let _timerPaused = false;
let _timerRunning = false;

// ── DOM refs ─────────────────────────────────────────────────────

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ── Busy guard ───────────────────────────────────────────────────

function setBusy(busy) {
    _busy = busy;
    document.body.classList.toggle('app-busy', busy);
}

// ── Nav ──────────────────────────────────────────────────────────

$$('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (_busy) return;
        $$('.nav-btn').forEach(b => b.classList.remove('active'));
        $$('.view').forEach(v => v.classList.remove('active'));
        btn.classList.add('active');
        $(`#view-${btn.dataset.view}`).classList.add('active');

        // Show a dot on the Execute tab if a timer is running and user navigates away
        updateTimerBadge();

        if (btn.dataset.view === 'execute') loadExecution();
        if (btn.dataset.view === 'plan') loadPlan();
        if (btn.dataset.view === 'input') loadPending();
        if (btn.dataset.view === 'wishes') loadWishes();
    });
});

function updateTimerBadge() {
    const execBtn = document.querySelector('.nav-btn[data-view="execute"]');
    if (_timerRunning) {
        execBtn.classList.add('has-timer');
    } else {
        execBtn.classList.remove('has-timer');
    }
}

// ── Track bar ────────────────────────────────────────────────────

async function loadTracks() {
    try {
        const data = await api('/tracks');
        _tracks = data.tracks || [];
        _activeTrackId = data.active_track_id;
        renderTrackBar();
        applyTrackTheme();
    } catch(e) { /* silent */ }
}

function renderTrackBar() {
    const container = $('#track-pills');
    if (!container) return;

    let html = `<button class="track-pill ${!_activeTrackId ? 'track-pill-active' : ''}" data-track-id="" style="--track-color: var(--text-dim)">All</button>`;
    for (const t of _tracks) {
        const isActive = _activeTrackId === t.id;
        html += `<button class="track-pill ${isActive ? 'track-pill-active' : ''}" data-track-id="${t.id}" style="--track-color: ${t.color}">${t.icon} ${esc(t.name)}</button>`;
    }
    container.innerHTML = html;

    container.querySelectorAll('.track-pill').forEach(pill => {
        pill.addEventListener('click', () => switchTrack(pill.dataset.trackId ? parseInt(pill.dataset.trackId) : null));
    });
}

async function switchTrack(trackId) {
    if (_busy) return;
    setBusy(true);
    try {
        await api('/tracks/active', {
            method: 'POST',
            body: JSON.stringify({ track_id: trackId }),
        });
        _activeTrackId = trackId;
        renderTrackBar();
        applyTrackTheme();

        // If on execute view, reload options for the new track
        currentNow = null;
        loadExecution();
    } catch(e) {
        toast('Error switching track');
    } finally {
        setBusy(false);
    }
}

function applyTrackTheme() {
    const track = _tracks.find(t => t.id === _activeTrackId);
    if (track) {
        document.documentElement.style.setProperty('--track-accent', track.color);
        document.body.dataset.track = track.name.toLowerCase();
    } else {
        document.documentElement.style.setProperty('--track-accent', 'var(--accent)');
        delete document.body.dataset.track;
    }
}

// Initialise tracks on load
loadTracks();

// ── Onboarding  -  Conversational Interview ────────────────────

async function checkOnboarding() {
    try {
        const data = await api('/onboarding/status');
        if (data.onboarding_complete) return; // already done
        showOnboarding();
    } catch (e) {
        // API not ready or first load  -  silently skip
    }
}

function showOnboarding() {
    const overlay = $('#onboarding');
    overlay.classList.remove('hidden');
    $('#nav').style.display = 'none';
    $('#track-bar').style.display = 'none';
    $$('.view').forEach(v => v.style.display = 'none');

    const chat = $('#onb-chat');
    const inputArea = $('#onb-input-area');
    const textInput = $('#onb-text');
    const sendBtn = $('#onb-send');
    const micBtn = $('#onb-mic');
    const typingEl = $('#onb-typing');
    let onbBusy = false;

    function addBubble(text, role) {
        const bubble = document.createElement('div');
        bubble.className = `onb-bubble ${role}`;
        bubble.textContent = text;
        chat.appendChild(bubble);
        chat.scrollTop = chat.scrollHeight;
    }

    function showTyping(show) {
        typingEl.classList.toggle('hidden', !show);
        if (show) chat.scrollTop = chat.scrollHeight;
    }

    function finishOnboarding() {
        overlay.classList.add('hidden');
        $('#nav').style.display = '';
        $('#track-bar').style.display = '';
        $$('.view').forEach(v => v.style.display = '');
        toast('Welcome! Capture your first task →');
    }

    async function sendMessage() {
        const text = textInput.value.trim();
        if (!text || onbBusy) return;
        onbBusy = true;
        sendBtn.disabled = true;

        addBubble(text, 'user');
        textInput.value = '';
        showTyping(true);

        try {
            const resp = await api('/onboarding/message', {
                method: 'POST',
                body: JSON.stringify({ message: text }),
            });
            showTyping(false);
            if (resp.message) addBubble(resp.message, 'assistant');
            if (resp.done) {
                setTimeout(finishOnboarding, 1500);
                inputArea.classList.add('hidden');
            }
        } catch (e) {
            showTyping(false);
            addBubble("Sorry, something went wrong. Let's try again.", 'assistant');
        }
        onbBusy = false;
        sendBtn.disabled = false;
        textInput.focus();
    }

    sendBtn.addEventListener('click', sendMessage);
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Voice input for onboarding
    micBtn.addEventListener('click', async () => {
        if (onbBusy) return;
        if (isRecording && mediaRecorder) {
            mediaRecorder.stop();
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const chunks = [];
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(t => t.stop());
                isRecording = false;
                micBtn.textContent = '🎙️';
                if (chunks.length === 0) return;
                const blob = new Blob(chunks, { type: 'audio/webm' });
                const fd = new FormData();
                fd.append('file', blob, 'onb_audio.webm');

                onbBusy = true;
                sendBtn.disabled = true;
                showTyping(true);

                try {
                    const resp = await fetch('/onboarding/audio', { method: 'POST', body: fd });
                    const data = await resp.json();
                    showTyping(false);
                    if (data.transcript) addBubble(data.transcript, 'user');
                    if (data.message) addBubble(data.message, 'assistant');
                    if (data.done) {
                        setTimeout(finishOnboarding, 1500);
                        inputArea.classList.add('hidden');
                    }
                } catch (e) {
                    showTyping(false);
                    addBubble("Couldn't process audio. Try typing instead.", 'assistant');
                }
                onbBusy = false;
                sendBtn.disabled = false;
            };
            mediaRecorder.start();
            isRecording = true;
            micBtn.textContent = '⏹️';
        } catch (e) {
            toast('Microphone access denied');
        }
    });

    // Start the interview  -  fetch first AI question
    (async () => {
        showTyping(true);
        try {
            const resp = await api('/onboarding/start');
            showTyping(false);
            if (resp.message) addBubble(resp.message, 'assistant');
            inputArea.classList.remove('hidden');
            textInput.focus();
        } catch (e) {
            showTyping(false);
            addBubble("Hi! Tell me about yourself  -  what does your typical day look like?", 'assistant');
            inputArea.classList.remove('hidden');
        }
    })();
}

checkOnboarding();

// ── Weekly Stats Popup ───────────────────────────────────────────

async function loadWeeklyStats() {
    try {
        const data = await api('/stats/weekly');
        if (!data.tasks_completed || data.tasks_completed === 0) return;

        const popup = $('#stats-popup');
        const heroNum = $('#stats-hero-number');
        const details = $('#stats-details');
        const personaEl = $('#stats-persona');

        // Show hours if >= 60 min saved
        if (data.time_saved_minutes >= 60) {
            heroNum.textContent = data.time_saved_hours;
            heroNum.nextElementSibling.textContent = 'hours saved this week';
        } else {
            heroNum.textContent = data.time_saved_minutes;
        }

        // Build details
        let html = `<div class="stats-row">
            <span>Tasks completed</span><span class="stats-val">${data.tasks_completed}</span>
        </div>`;
        if (data.all_time_tasks && data.all_time_tasks > data.tasks_completed) {
            html += `<div class="stats-row">
                <span>All-time total</span><span class="stats-val">${data.all_time_tasks}</span>
            </div>`;
        }
        html += `<div class="stats-row">
            <span>Estimated total</span><span class="stats-val">${data.total_estimated_minutes} min</span>
        </div>
        <div class="stats-row">
            <span>Actual total</span><span class="stats-val">${data.total_actual_minutes} min</span>
        </div>`;
        if (data.streak_days > 1) {
            html += `<div class="stats-row stats-streak">
                <span>🔥 Streak</span><span class="stats-val">${data.streak_days} days</span>
            </div>`;
        }

        // Improvement trend
        if (data.improvement_pct !== null && data.improvement_pct !== undefined) {
            const pct = data.improvement_pct;
            const arrow = pct > 0 ? '↑' : pct < 0 ? '↓' : '→';
            const cls = pct > 0 ? 'stats-trend-up' : pct < 0 ? 'stats-trend-down' : '';
            html += `<div class="stats-row ${cls}">
                <span>${arrow} vs last week</span><span class="stats-val">${pct > 0 ? '+' : ''}${pct}%</span>
            </div>`;
        }

        // Complexity distribution
        if (data.complexity && data.complexity.distribution) {
            const d = data.complexity.distribution;
            const total = (d.low || 0) + (d.medium || 0) + (d.high || 0);
            if (total > 0) {
                html += '<div class="stats-section-label">Complexity breakdown</div>';
                html += '<div class="stats-complexity-bar">';
                const pLow = Math.round((d.low / total) * 100);
                const pMed = Math.round((d.medium / total) * 100);
                const pHigh = Math.round((d.high / total) * 100);
                if (d.low) html += `<div class="cx-seg cx-low" style="width:${pLow}%">${d.low}</div>`;
                if (d.medium) html += `<div class="cx-seg cx-med" style="width:${pMed}%">${d.medium}</div>`;
                if (d.high) html += `<div class="cx-seg cx-high" style="width:${pHigh}%">${d.high}</div>`;
                html += '</div>';
                html += `<div class="stats-complexity-legend">
                    <span class="cx-label cx-low-l">Easy ${d.low}</span>
                    <span class="cx-label cx-med-l">Medium ${d.medium}</span>
                    <span class="cx-label cx-high-l">Hard ${d.high}</span>
                </div>`;
                html += `<div class="stats-row">
                    <span>Avg complexity</span><span class="stats-val">${data.complexity.average}/10</span>
                </div>`;
            }
        }

        // Top savings
        if (data.top_savings && data.top_savings.length > 0) {
            html += '<div class="stats-section-label">Biggest wins</div>';
            for (const s of data.top_savings.slice(0, 3)) {
                html += `<div class="stats-saving-row">
                    <span class="stats-saving-task">${esc(s.content)}</span>
                    <span class="stats-saving-diff">-${s.saved_min}min</span>
                </div>`;
            }
        }
        details.innerHTML = html;

        // Persona insights
        if (data.persona && data.persona.total_datapoints >= 5) {
            const p = data.persona;
            let pHtml = '<div class="stats-section-label">Your work profile</div>';
            const ratio = p.global_speed_ratio;
            if (ratio < 0.8) {
                pHtml += `<div class="stats-persona-line">⚡ You're a fast worker  -  finishing at ${Math.round(ratio * 100)}% of estimated time</div>`;
            } else if (ratio > 1.2) {
                pHtml += `<div class="stats-persona-line">🐢 You tend to take longer  -  ${Math.round(ratio * 100)}% of estimates. We're adjusting!</div>`;
            } else {
                pHtml += `<div class="stats-persona-line">✅ Estimates are well-calibrated to your pace</div>`;
            }
            if (p.preferred_duration_bucket) {
                pHtml += `<div class="stats-persona-line">⏱ Sweet spot: ${p.preferred_duration_bucket} sessions</div>`;
            }
            personaEl.innerHTML = pHtml;
            personaEl.classList.remove('hidden');
        }

        popup.classList.remove('hidden');
    } catch (e) {
        // Silently fail  -  don't block the app
    }
}

$('#stats-popup-close').addEventListener('click', () => {
    $('#stats-popup').classList.add('hidden');
});
$('#stats-popup-minimize').addEventListener('click', () => {
    $('#stats-popup').classList.add('hidden');
});

// Show stats on app open
loadWeeklyStats();

// ── Toast ────────────────────────────────────────────────────────

let _toastTimer = null;
function toast(msg, duration = 2500) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.add('hidden'), duration);
}

// ── Settings ─────────────────────────────────────────────────────

$('#btn-settings').addEventListener('click', async () => {
    try {
        const data = await api('/settings');
        $('#settings-model').value = data.model || 'gpt-4o-mini';
        $('#settings-apikey').value = '';
        $('#settings-apikey').placeholder = data.api_key_masked || 'sk-...';
        $('#settings-gemini-apikey').value = '';
        $('#settings-gemini-apikey').placeholder = data.gemini_api_key_masked || 'AIza...';
    } catch (e) {
        // Defaults if API not ready
    }
    $('#settings-modal').classList.remove('hidden');
});

$('#btn-settings-cancel').addEventListener('click', () => {
    $('#settings-modal').classList.add('hidden');
});

$('#settings-modal').addEventListener('click', (e) => {
    if (e.target === $('#settings-modal')) {
        $('#settings-modal').classList.add('hidden');
    }
});

$('#btn-settings-save').addEventListener('click', async () => {
    const btn = $('#btn-settings-save');
    btn.disabled = true;
    try {
        const body = {};
        const model = $('#settings-model').value;
        if (model) body.model = model;
        const apiKey = $('#settings-apikey').value.trim();
        if (apiKey) body.api_key = apiKey;
        const geminiKey = $('#settings-gemini-apikey').value.trim();
        if (geminiKey) body.gemini_api_key = geminiKey;

        if (!body.model && !body.api_key && !body.gemini_api_key) {
            toast('Nothing to save');
            return;
        }

        await api('/settings', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        toast('✓ Settings saved');
        $('#settings-modal').classList.add('hidden');
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        btn.disabled = false;
    }
});

// ── Keyboard visibility handling (iOS/Android) ──────────────────

if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
        document.documentElement.style.setProperty(
            '--vvh', window.visualViewport.height + 'px'
        );
    });
}

// ── API helpers ──────────────────────────────────────────────────

async function api(path, opts = {}) {
    const headers = { ...opts.headers };
    // Only set Content-Type for string bodies (JSON), not FormData
    if (opts.body && typeof opts.body === 'string') {
        headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(API + path, { ...opts, headers });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `API error ${res.status}`);
    }
    // DELETE returns 204 with no body
    if (res.status === 204) return {};
    return res.json();
}

// ── Input: Text Send ─────────────────────────────────────────────

$('#btn-send').addEventListener('click', async () => {
    const text = $('#text-input').value.trim();
    if (!text || _busy) return;

    const btn = $('#btn-send');
    btn.disabled = true;
    setBusy(true);

    try {
        const result = await api('/ingest', {
            method: 'POST',
            body: JSON.stringify({ text }),
        });
        showIngestResult(result);
        $('#text-input').value = '';
        toast(result.status === 'pending_approval' ? '⏳ Needs approval' : `✓ ${result.task_count || 1} task(s) captured`);
        loadPending();
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        btn.disabled = false;
        setBusy(false);
    }
});

// Submit on Enter (Shift+Enter for newline)
$('#text-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        $('#btn-send').click();
    }
});

// ── Input: Voice ─────────────────────────────────────────────────

$('#btn-mic').addEventListener('click', async () => {
    if (_busy && !isRecording) return;
    if (isRecording) {
        stopRecording();
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        startRecording(stream);
    } catch (e) {
        toast('Mic access denied');
    }
});

function startRecording(stream) {
    const chunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMime() });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, { type: mediaRecorder.mimeType });
        await sendAudio(blob);
    };
    mediaRecorder.start();
    isRecording = true;
    $('#btn-mic').classList.add('recording');
    $('#mic-status').textContent = 'Recording... tap to stop';
    $('#mic-status').classList.remove('hidden');
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    $('#btn-mic').classList.remove('recording');
    $('#mic-status').classList.add('hidden');
}

function getSupportedMime() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return types.find(t => MediaRecorder.isTypeSupported(t)) || 'audio/webm';
}

async function sendAudio(blob) {
    setBusy(true);
    $('#mic-status').textContent = 'Processing...';
    $('#mic-status').classList.remove('hidden');

    try {
        const form = new FormData();
        const ext = blob.type.includes('mp4') ? 'mp4' : blob.type.includes('ogg') ? 'ogg' : 'webm';
        form.append('file', blob, `recording.${ext}`);
        const res = await fetch(API + '/ingest/audio', { method: 'POST', body: form });
        if (!res.ok) throw new Error('Audio processing failed');
        const result = await res.json();
        showIngestResult(result);
        toast(result.status === 'pending_approval' ? '⏳ Needs approval' : `✓ ${result.task_count || 1} task(s) captured`);
        loadPending();
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        setBusy(false);
        $('#mic-status').classList.add('hidden');
    }
}

// ── Show ingest result ───────────────────────────────────────────

function showIngestResult(result) {
    const el = $('#ingest-result');
    const p = result.parsed;
    const tasks = p.tasks || [p];
    const goal = result.goal || p.goal || '';
    const count = result.task_count || tasks.length;

    let html = '';
    if (result.status === 'pending_approval') {
        html += `<div class="result-status">⏳ Pending your approval</div>`;
    } else if (count > 1) {
        html += `<div class="result-status">✓ Captured ${count} tasks</div>`;
        if (goal) html += `<div class="result-goal">🎯 ${esc(goal)}</div>`;
        tasks.forEach((t, i) => {
            html += `<div class="result-task-mini">${i + 1}. ${esc(t.content || '')}</div>`;
        });
    } else {
        html += `<div class="result-status">✓ Captured</div>`;
        if (goal) html += `<div class="result-goal">🎯 ${esc(goal)}</div>`;
        html += `<div class="result-task-mini">${esc(tasks[0]?.content || '')}</div>`;
    }
    el.innerHTML = html;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 4000);
}

// ── Pending approvals ────────────────────────────────────────────

async function loadPending() {
    try {
        const data = await api('/inbox');
        const items = data.items || [];
        const section = $('#pending-section');
        const list = $('#pending-list');
        if (items.length === 0) {
            section.classList.add('hidden');
            return;
        }
        section.classList.remove('hidden');
        list.innerHTML = items.map(item => {
            const parsed = JSON.parse(item.parsed_json || '{}');
            const tasks = parsed.tasks || [parsed];
            const goal = parsed.goal || '';
            return `
                <div class="pending-item" data-id="${item.id}">
                    <div class="raw">"${esc(item.raw_input)}"</div>
                    ${goal ? `<div class="pending-goal">🎯 ${esc(goal)}</div>` : ''}
                    <div class="pending-task-count">${tasks.length} task(s)</div>
                    <div class="pending-actions">
                        <button class="btn-approve" data-inbox="${item.id}" data-action="approve">Approve</button>
                        <button class="btn-reject" data-inbox="${item.id}" data-action="reject">Reject</button>
                    </div>
                </div>
            `;
        }).join('');
        // Event delegation for approve/reject
        list.querySelectorAll('button[data-inbox]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                if (_busy) return;
                const inboxId = parseInt(e.target.dataset.inbox);
                const approved = e.target.dataset.action === 'approve';
                setBusy(true);
                e.target.disabled = true;
                try {
                    await api('/approve', {
                        method: 'POST',
                        body: JSON.stringify({ inbox_id: inboxId, approved }),
                    });
                    toast(approved ? '✓ Approved' : '✗ Rejected');
                    loadPending();
                } catch (err) {
                    toast('Error: ' + err.message);
                } finally {
                    setBusy(false);
                }
            });
        });
    } catch (e) { /* silent */ }
}

// ── Execution view ───────────────────────────────────────────────

function showExecState(state) {
    // state: 'empty' | 'choose' | 'ready' | 'timer'
    $('#exec-empty').classList.toggle('hidden', state !== 'empty');
    $('#exec-choose').classList.toggle('hidden', state !== 'choose');
    $('#exec-ready').classList.toggle('hidden', state !== 'ready');
    $('#exec-timer').classList.toggle('hidden', state !== 'timer');
}

$('#btn-whats-next').addEventListener('click', () => {
    if (!_busy) loadExecution();
});

function showBreakScreen(breakInfo) {
    // Reuse empty state area to show break
    showExecState('empty');
    const el = $('#exec-empty');
    el.innerHTML = `
        <div class="break-screen">
            <div class="break-icon">☕</div>
            <p class="break-msg">${esc(breakInfo.message)}</p>
            <p class="break-duration">${breakInfo.duration_minutes} min break</p>
            <button id="btn-break-done" class="btn-primary">I'm Back!</button>
        </div>
    `;
    document.getElementById('btn-break-done').addEventListener('click', () => {
        // Reset empty state and reload
        el.innerHTML = '<p>No active task</p><button id="btn-whats-next" class="btn-primary">What\'s Next?</button>';
        document.getElementById('btn-whats-next').addEventListener('click', () => { if (!_busy) loadExecution(); });
        loadExecution();
    });
}

let _lastOptions = null; // store options so Back button works

async function loadExecution() {
    // If timer is already running, just show it  -  don't refetch
    if (_timerRunning && currentNow) {
        showExecState('timer');
        return;
    }

    // Prompt check-in if no recent one (non-blocking  -  user can skip)
    try {
        const ci = await api('/checkin/latest');
        if (!ci.has_recent) {
            await showCheckinModal();
        }
    } catch (e) { /* non-critical */ }

    setBusy(true);
    try {
        const data = await api('/next');

        // Handle break enforcement
        if (data.break && (!data.options || !data.options.length)) {
            showBreakScreen(data.break);
            return;
        }

        // If there's an active locked task, go straight to ready screen
        if (data.active && data.now) {
            currentNow = data.now;
            _afterData = data.after || [];
            if (data.big_picture) {
                $('#big-picture').textContent = '🎯 ' + data.big_picture;
                $('#big-picture').classList.remove('hidden');
            }
            renderReadyScreen(data);
            showExecState('ready');
            return;
        }

        // Show options for the user to choose from
        if (!data.options || data.options.length === 0) {
            showExecState('empty');
            // Show wishful thinking suggestion if available
            if (data.wishful_suggestion) {
                const el = $('#exec-empty');
                const w = data.wishful_suggestion;
                el.innerHTML = `
                    <p>No active task</p>
                    <div class="wish-suggest-banner">
                        <div class="wish-suggest-label">WISHFUL THINKING</div>
                        <div class="wish-suggest-content">${esc(w.content)}</div>
                        <div class="wish-suggest-actions">
                            <button id="btn-promote-wish" class="btn-primary" style="font-size:0.78rem; padding:8px 16px;">Promote &amp; Do It</button>
                            <button id="btn-whats-next-2" class="btn-secondary" style="font-size:0.78rem; padding:8px 16px;">Skip</button>
                        </div>
                    </div>
                `;
                document.getElementById('btn-promote-wish').addEventListener('click', async () => {
                    await api('/wishlist/promote', { method: 'POST', body: JSON.stringify({ item_id: w.id, to_status: 'next' }) });
                    toast('Promoted to active!');
                    loadExecution();
                });
                document.getElementById('btn-whats-next-2').addEventListener('click', () => { loadExecution(); });
            }
            return;
        }

        _lastOptions = data;
        renderOptionsScreen(data);
        showExecState('choose');
    } catch (e) {
        toast('Error loading tasks');
    } finally {
        setBusy(false);
    }
}

function renderOptionsScreen(data) {
    // Big picture
    const bp = $('#big-picture');
    if (data.big_picture) {
        bp.textContent = '🎯 ' + data.big_picture;
        bp.classList.remove('hidden');
    } else {
        bp.classList.add('hidden');
    }

    // Anti-loop warning
    let loopEl = $('#choose-anti-loop');
    if (data.anti_loop_warning) {
        if (!loopEl) {
            $('#options-list').insertAdjacentHTML('beforebegin', '<div id="choose-anti-loop" class="anti-loop-warning"></div>');
            loopEl = $('#choose-anti-loop');
        }
        loopEl.textContent = `🔄 ${data.anti_loop_warning}`;
        loopEl.classList.remove('hidden');
    } else if (loopEl) {
        loopEl.classList.add('hidden');
    }

    // User state
    if (data.user_state) {
        let stateEl = $('#choose-user-state');
        if (!stateEl) {
            document.querySelector('.choose-label').insertAdjacentHTML('afterend', '<div id="choose-user-state" class="user-state-indicator"></div>');
            stateEl = $('#choose-user-state');
        }
        const us = data.user_state;
        const mEmoji = {none: '⬜', building: '🟨', high: '🟩'}[us.momentum] || '⬜';
        stateEl.innerHTML = `<span class="state-chip">${mEmoji} ${us.momentum}</span> <span class="state-chip">⚡ ${us.energy}</span> <span class="state-chip">🎯 ${us.focus}</span>`;
    }

    const list = $('#options-list');
    list.innerHTML = data.options.map((opt, idx) => {
        const cogEmoji = opt.cognitive_emoji || '🧠';
        const thinkBadge = opt.is_thinking ? '<span class="option-think-badge">🧠 THINK</span>' : '';
        const execBadge = opt.execution_class && opt.execution_class !== 'linear'
            ? `<span class="option-exec-badge">📐 ${esc(opt.execution_class)}</span>` : '';
        const dopBadge = opt.dopamine_label ? `<span class="option-dop-badge">${esc(opt.dopamine_label)}</span>` : '';

        return `
        <button class="option-card${idx === 0 ? ' option-recommended' : ''}" data-id="${opt.id}">
            ${idx === 0 ? '<div class="option-rec-tag">★ RECOMMENDED</div>' : ''}
            <div class="option-content">${esc(opt.content)}</div>
            <div class="option-meta">
                <span>${opt.duration_minutes}m</span>
                <span>${opt.energy_emoji} ${esc(opt.energy_required)}</span>
                <span>${cogEmoji} ${esc(opt.cognitive_load)}</span>
                ${opt.cluster ? `<span>${esc(opt.cluster)}</span>` : ''}
            </div>
            <div class="option-badges">
                ${opt.friction_emoji} ${esc(opt.initiation_friction)} friction
                ${dopBadge} ${thinkBadge} ${execBadge}
            </div>
        </button>`;
    }).join('');

    // Render blocked items (visible but not selectable)
    if (data.blocked_options && data.blocked_options.length > 0) {
        list.insertAdjacentHTML('beforeend', data.blocked_options.map(opt => `
        <div class="option-card option-blocked" title="Blocked by another task">
            <div class="option-blocked-tag">🔒 BLOCKED</div>
            <div class="option-content">${esc(opt.content)}</div>
            <div class="option-meta">
                <span>${opt.duration_minutes}m</span>
                <span>${opt.energy_emoji} ${esc(opt.energy_required)}</span>
                ${opt.cluster ? `<span>${esc(opt.cluster)}</span>` : ''}
            </div>
        </div>`).join(''));
    }

    // Attach click handlers
    list.querySelectorAll('.option-card:not(.option-blocked)').forEach(card => {
        card.addEventListener('click', () => selectOption(parseInt(card.dataset.id)));
    });
}

async function selectOption(itemId) {
    if (_busy) return;
    setBusy(true);
    try {
        const data = await api('/select', {
            method: 'POST',
            body: JSON.stringify({ item_id: itemId }),
        });
        if (data.now) {
            currentNow = data.now;
            _afterData = data.after || [];
            renderReadyScreen(data);
            showExecState('ready');
        } else {
            toast('Could not select task');
            showExecState('empty');
        }
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        setBusy(false);
    }
}

let _afterData = [];

function renderReadyScreen(data) {
    $('#ready-content').textContent = data.now.content;

    // ADHD metadata line
    const friction = data.now.friction_emoji || '🟡';
    const dopamine = data.now.dopamine_label || '';
    const cognitive = data.now.cognitive_load || 'medium';
    const cogEmoji = {low: '🧘', medium: '🧠', high: '🔬'}[cognitive] || '🧠';

    let metaParts = [
        `${data.now.duration_minutes} min`,
        `${data.now.energy_emoji || '🔥'} ${data.now.energy_required}`,
        `${cogEmoji} ${cognitive}`,
    ];
    if (data.now.cluster) metaParts.push(data.now.cluster);
    // Show execution class badge for non-linear tasks
    if (data.now.execution_class && data.now.execution_class !== 'linear') {
        metaParts.push(`📐 ${data.now.execution_class}`);
    }
    $('#ready-meta').textContent = metaParts.join(' · ');

    // Thinking task objective + output format
    let thinkingEl = $('#thinking-meta');
    if (data.now.is_thinking) {
        if (!thinkingEl) {
            $('#ready-content').insertAdjacentHTML('afterend', '<div id="thinking-meta" class="thinking-meta"></div>');
            thinkingEl = $('#thinking-meta');
        }
        thinkingEl.innerHTML = `
            <div class="thinking-label">🧠 THINKING TASK</div>
            ${data.now.thinking_objective ? `<div class="thinking-objective"><strong>Objective:</strong> ${esc(data.now.thinking_objective)}</div>` : ''}
            ${data.now.thinking_output_format ? `<div class="thinking-output-fmt"><strong>Produce:</strong> ${esc(data.now.thinking_output_format)}</div>` : ''}
        `;
        thinkingEl.classList.remove('hidden');
    } else if (thinkingEl) {
        thinkingEl.classList.add('hidden');
    }

    // Dopamine sandwich display
    let sandwichEl = $('#dopamine-sandwich');
    if (data.dopamine_sandwich) {
        if (!sandwichEl) {
            document.querySelector('.ready-card').insertAdjacentHTML('afterend', '<div id="dopamine-sandwich" class="dopamine-sandwich"></div>');
            sandwichEl = $('#dopamine-sandwich');
        }
        let html = '<div class="sandwich-label">🥪 DOPAMINE SANDWICH</div>';
        if (data.dopamine_sandwich.before) {
            html += `<div class="sandwich-item sandwich-before">⚡ Quick win first: ${esc(data.dopamine_sandwich.before.content)} (${data.dopamine_sandwich.before.duration_minutes}m)</div>`;
        }
        if (data.dopamine_sandwich.after) {
            html += `<div class="sandwich-item sandwich-after">🎯 Then do: ${esc(data.dopamine_sandwich.after.content)} (${data.dopamine_sandwich.after.duration_minutes}m)</div>`;
        }
        sandwichEl.innerHTML = html;
        sandwichEl.classList.remove('hidden');
    } else if (sandwichEl) {
        sandwichEl.classList.add('hidden');
    }

    // Anti-loop warning
    let loopEl = $('#anti-loop-warning');
    if (data.anti_loop_warning) {
        if (!loopEl) {
            document.querySelector('.ready-card').insertAdjacentHTML('afterend', '<div id="anti-loop-warning" class="anti-loop-warning"></div>');
            loopEl = $('#anti-loop-warning');
        }
        loopEl.textContent = `🔄 ${data.anti_loop_warning}`;
        loopEl.classList.remove('hidden');
    } else if (loopEl) {
        loopEl.classList.add('hidden');
    }

    // Friction + dopamine badges
    let badgeHtml = `<span class="adhd-badge friction-badge">${friction} ${data.now.initiation_friction || 'medium'} friction</span>`;
    if (dopamine) {
        badgeHtml += ` <span class="adhd-badge dopamine-badge">${dopamine}</span>`;
    }
    // Inject badges (create container if needed)
    let badgeEl = $('#ready-badges');
    if (!badgeEl) {
        $('#ready-meta').insertAdjacentHTML('afterend', '<div id="ready-badges" class="ready-badges"></div>');
        badgeEl = $('#ready-badges');
    }
    badgeEl.innerHTML = badgeHtml;

    $('#ready-why').textContent = data.now.why || '';

    // User state indicator
    if (data.user_state) {
        let stateEl = $('#user-state-indicator');
        if (!stateEl) {
            $('#ready-why').insertAdjacentHTML('afterend', '<div id="user-state-indicator" class="user-state-indicator"></div>');
            stateEl = $('#user-state-indicator');
        }
        const us = data.user_state;
        const momentumEmoji = {none: '⬜', building: '🟨', high: '🟩'}[us.momentum] || '⬜';
        stateEl.innerHTML = `<span class="state-chip">${momentumEmoji} ${us.momentum}</span> <span class="state-chip">⚡ ${us.energy}</span> <span class="state-chip">🎯 ${us.focus}</span>`;
    }

    // Break suggestion banner
    let breakEl = $('#break-banner');
    if (data.break_suggestion) {
        if (!breakEl) {
            document.querySelector('.ready-card').insertAdjacentHTML('beforebegin', '<div id="break-banner" class="break-banner"></div>');
            breakEl = $('#break-banner');
        }
        breakEl.textContent = `☕ ${data.break_suggestion.message}`;
        breakEl.classList.remove('hidden');
    } else if (breakEl) {
        breakEl.classList.add('hidden');
    }

    // Recovery task
    let recoveryEl = $('#recovery-section');
    if (data.recovery) {
        if (!recoveryEl) {
            document.querySelector('.after-section').insertAdjacentHTML('afterend',
                '<div id="recovery-section" class="recovery-section"><div class="after-label">RECOVERY</div><div id="recovery-content"></div></div>');
            recoveryEl = $('#recovery-section');
        }
        $('#recovery-content').innerHTML = `<div class="after-item recovery-item"><div>${esc(data.recovery.content)}</div><div class="after-meta">${data.recovery.duration_minutes} min · low effort</div></div>`;
        recoveryEl.classList.remove('hidden');
    } else if (recoveryEl) {
        recoveryEl.classList.add('hidden');
    }

    // Avoidance warning
    let avoidEl = $('#avoidance-warning');
    if (data.avoidance_warning) {
        if (!avoidEl) {
            document.querySelector('.ready-card').insertAdjacentHTML('afterend', '<div id="avoidance-warning" class="avoidance-warning"></div>');
            avoidEl = $('#avoidance-warning');
        }
        avoidEl.textContent = `⚠️ ${data.avoidance_warning}`;
        avoidEl.classList.remove('hidden');
    } else if (avoidEl) {
        avoidEl.classList.add('hidden');
    }

    const afterList = $('#after-list');
    afterList.innerHTML = (data.after || []).map(item => `
        <div class="after-item">
            <div>${esc(item.content)}</div>
            <div class="after-meta">${item.duration_minutes} min · ${item.energy_required}${item.dopamine_label ? ' · ' + item.dopamine_label : ''}</div>
        </div>
    `).join('') || '<div class="after-item" style="color:var(--text-dim)">Queue empty</div>';
}

// ── Start Timer ──────────────────────────────────────────────────

$('#btn-start-timer').addEventListener('click', () => {
    if (!currentNow || _busy) return;
    startTimer(currentNow);
});

$('#btn-back-to-choose').addEventListener('click', async () => {
    if (_busy) return;
    // Unlock the current task and go back to options
    if (currentNow) {
        setBusy(true);
        try {
            // Reset task status from 'doing' back to 'next'
            await api(`/items/${currentNow.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ status: 'next' }),
            });
        } catch(e) { /* best effort */ }
        setBusy(false);
    }
    currentNow = null;
    loadExecution();
});

function startTimer(task) {
    _timerTotalSeconds = (task.duration_minutes || 30) * 60;
    _timerSecondsLeft = _timerTotalSeconds;
    _timerPaused = false;
    _timerRunning = true;

    $('#timer-content').textContent = task.content;

    // Show thinking task context in timer
    let timerThinkEl = $('#timer-thinking-meta');
    if (task.is_thinking) {
        if (!timerThinkEl) {
            $('#timer-content').insertAdjacentHTML('afterend', '<div id="timer-thinking-meta" class="timer-thinking-meta"></div>');
            timerThinkEl = $('#timer-thinking-meta');
        }
        timerThinkEl.innerHTML = `
            ${task.thinking_objective ? `<div class="tt-obj">🎯 ${esc(task.thinking_objective)}</div>` : ''}
            ${task.thinking_output_format ? `<div class="tt-fmt">📝 Produce: ${esc(task.thinking_output_format)}</div>` : ''}
        `;
        timerThinkEl.classList.remove('hidden');

        // Change timer label
        $('.timer-task-label').textContent = 'THINK';
    } else {
        if (timerThinkEl) timerThinkEl.classList.add('hidden');
        $('.timer-task-label').textContent = 'FOCUS';
    }

    updateTimerDisplay();
    showExecState('timer');

    // Update ring circumference
    const circle = $('#timer-ring-progress');
    const circumference = 2 * Math.PI * 90;
    circle.style.strokeDasharray = circumference;
    circle.style.strokeDashoffset = '0';

    clearInterval(_timerInterval);
    _timerInterval = setInterval(() => {
        if (_timerPaused) return;

        _timerSecondsLeft--;
        updateTimerDisplay();

        // Update ring
        const progress = 1 - (_timerSecondsLeft / _timerTotalSeconds);
        circle.style.strokeDashoffset = circumference * progress;

        if (_timerSecondsLeft <= 0) {
            clearInterval(_timerInterval);
            _timerInterval = null;
            onTimerComplete();
        }
    }, 1000);

    // Update pause button state
    const pauseBtn = $('#btn-timer-pause');
    pauseBtn.textContent = '⏸';
    pauseBtn.classList.remove('is-paused');
}

function updateTimerDisplay() {
    const abs = Math.abs(_timerSecondsLeft);
    const mins = Math.floor(abs / 60);
    const secs = abs % 60;
    const prefix = _timerSecondsLeft < 0 ? '+' : '';
    $('#timer-digits').textContent = `${prefix}${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    const phase = $('#timer-phase');
    if (_timerSecondsLeft <= 0) {
        phase.textContent = 'Time\'s up! Finish or mark done.';
        $('#timer-digits').classList.add('overtime');
    } else if (_timerPaused) {
        phase.textContent = 'Paused';
    } else {
        phase.textContent = '';
        $('#timer-digits').classList.remove('overtime');
    }
}

function onTimerComplete() {
    // Keep counting into overtime so user sees +00:xx
    _timerInterval = setInterval(() => {
        if (_timerPaused) return;
        _timerSecondsLeft--;
        updateTimerDisplay();
    }, 1000);

    // Gentle vibration if available
    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    toast('⏰ Timer done!', 4000);
}

function stopTimerCleanly() {
    clearInterval(_timerInterval);
    _timerInterval = null;
    _timerRunning = false;
    _timerPaused = false;
    _timerSecondsLeft = 0;
    updateTimerBadge();
}

// ── Pause / Resume ───────────────────────────────────────────────

$('#btn-timer-pause').addEventListener('click', () => {
    _timerPaused = !_timerPaused;
    const btn = $('#btn-timer-pause');
    if (_timerPaused) {
        btn.textContent = '▶';
        btn.classList.add('is-paused');
    } else {
        btn.textContent = '⏸';
        btn.classList.remove('is-paused');
    }
    updateTimerDisplay();
});

// ── Complete (from timer) ────────────────────────────────────────

$('#btn-timer-done').addEventListener('click', async () => {
    if (!currentNow || _busy) return;
    const btn = $('#btn-timer-done');
    btn.disabled = true;
    setBusy(true);
    try {
        // Calculate actual elapsed seconds
        const elapsed = _timerTotalSeconds - _timerSecondsLeft;
        const data = await api('/complete', {
            method: 'POST',
            body: JSON.stringify({ item_id: currentNow.id, elapsed_seconds: Math.max(0, elapsed) }),
        });
        stopTimerCleanly();

        // Handle thinking task completion → show expansion UI
        if (data.thinking_complete) {
            toast('🧠 Thinking done!');
            showExpansionScreen(data);
            return;
        }

        toast('✓ Completed!');

        // Handle break enforcement
        if (data.break && (!data.options || !data.options.length)) {
            showBreakScreen(data.break);
            return;
        }

        // /complete now returns options for next pick
        if (data.options && data.options.length > 0) {
            _lastOptions = data;
            currentNow = null;
            renderOptionsScreen(data);
            showExecState('choose');
        } else {
            currentNow = null;
            showExecState('empty');
        }
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        btn.disabled = false;
        setBusy(false);
    }
});

// ── Skip  -  Categorized ───────────────────────────────────────────

let _skipCategory = 'not_now';
let _skipCategories = null;

async function loadSkipCategories() {
    if (_skipCategories) return;
    try {
        const data = await api('/skip-categories');
        _skipCategories = data.categories || [];
    } catch (e) {
        _skipCategories = [
            {key: 'not_now', label: 'Not right now', emoji: '⏰'},
            {key: 'too_hard', label: 'Feels too hard', emoji: '🧱'},
            {key: 'unclear', label: 'Not sure what to do', emoji: '❓'},
            {key: 'boring', label: 'Too boring', emoji: '😴'},
            {key: 'anxious', label: 'Makes me anxious', emoji: '😰'},
        ];
    }
}

function renderSkipCategories() {
    const container = $('#skip-categories');
    if (!container || !_skipCategories) return;
    container.innerHTML = _skipCategories.map(c =>
        `<button class="skip-cat-btn ${c.key === _skipCategory ? 'skip-cat-active' : ''}" data-cat="${c.key}">${c.emoji} ${c.label}</button>`
    ).join('');
    container.querySelectorAll('.skip-cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            _skipCategory = btn.dataset.cat;
            container.querySelectorAll('.skip-cat-btn').forEach(b => b.classList.remove('skip-cat-active'));
            btn.classList.add('skip-cat-active');
        });
    });
}

$('#btn-skip').addEventListener('click', async () => {
    if (_busy) return;
    await loadSkipCategories();
    _skipCategory = 'not_now';
    renderSkipCategories();
    $('#skip-reason').value = '';
    $('#skip-intervention').classList.add('hidden');
    $('#skip-modal').classList.remove('hidden');
});

$('#btn-skip-cancel').addEventListener('click', () => {
    $('#skip-modal').classList.add('hidden');
});

$('#skip-modal').addEventListener('click', (e) => {
    if (e.target === $('#skip-modal')) {
        $('#skip-modal').classList.add('hidden');
    }
});

$('#btn-skip-confirm').addEventListener('click', async () => {
    const reason = $('#skip-reason').value.trim() || _skipCategory;
    if (!currentNow || _busy) return;

    const btn = $('#btn-skip-confirm');
    btn.disabled = true;
    setBusy(true);

    try {
        const data = await api('/override', {
            method: 'POST',
            body: JSON.stringify({
                item_id: currentNow.id,
                reason,
                skip_category: _skipCategory,
            }),
        });

        // Show intervention if returned
        if (data.avoidance_warning) {
            const intEl = $('#skip-intervention');
            intEl.textContent = data.avoidance_warning;
            intEl.classList.remove('hidden');
            // Keep modal open for 2s so user sees the intervention
            await new Promise(r => setTimeout(r, 2000));
        }

        $('#skip-modal').classList.add('hidden');
        stopTimerCleanly();
        toast('Skipped');
        if (data.options && data.options.length > 0) {
            _lastOptions = data;
            currentNow = null;
            renderOptionsScreen(data);
            showExecState('choose');
        } else if (data.now) {
            currentNow = data.now;
            _afterData = data.after || [];
            renderReadyScreen(data);
            showExecState('ready');
        } else {
            currentNow = null;
            showExecState('empty');
        }
    } catch (e) {
        toast('Error: ' + e.message);
    } finally {
        btn.disabled = false;
        setBusy(false);
    }
});

// ── Check-in Modal ───────────────────────────────────────────────

let _checkinResolve = null;

function showCheckinModal() {
    return new Promise(resolve => {
        _checkinResolve = resolve;
        $('#checkin-energy').value = 3;
        $('#checkin-focus').value = 3;
        $('#checkin-modal').classList.remove('hidden');
    });
}

$('#btn-checkin-submit').addEventListener('click', async () => {
    const energy = parseInt($('#checkin-energy').value, 10);
    const focus = parseInt($('#checkin-focus').value, 10);
    $('#checkin-modal').classList.add('hidden');
    try {
        await api('/checkin', {
            method: 'POST',
            body: JSON.stringify({ energy, focus }),
        });
    } catch (e) { /* non-critical */ }
    if (_checkinResolve) { _checkinResolve(true); _checkinResolve = null; }
});

$('#btn-checkin-skip').addEventListener('click', () => {
    $('#checkin-modal').classList.add('hidden');
    if (_checkinResolve) { _checkinResolve(false); _checkinResolve = null; }
});

$('#checkin-modal').addEventListener('click', (e) => {
    if (e.target === $('#checkin-modal')) {
        $('#checkin-modal').classList.add('hidden');
        if (_checkinResolve) { _checkinResolve(false); _checkinResolve = null; }
    }
});

// ── Thinking Task Expansion ──────────────────────────────────────

function showExpansionScreen(data) {
    showExecState('empty');
    const el = $('#exec-empty');
    el.innerHTML = `
        <div class="expansion-screen">
            <div class="expansion-icon">🧠</div>
            <h3 class="expansion-title">Thinking Session Complete</h3>
            ${data.thinking_objective ? `<p class="expansion-objective">Objective: ${esc(data.thinking_objective)}</p>` : ''}
            ${data.thinking_output_format ? `<p class="expansion-fmt">Expected: ${esc(data.thinking_output_format)}</p>` : ''}
            <textarea id="expansion-notes" class="expansion-notes" placeholder="Paste your thinking output / notes here...\n\nWhat did you decide? What are the next steps?" rows="6"></textarea>
            <div class="expansion-actions">
                <button id="btn-expand" class="btn-primary">🚀 Generate Tasks</button>
                <button id="btn-skip-expand" class="btn-secondary">Skip → Next Task</button>
            </div>
            <div id="expansion-result" class="expansion-result hidden"></div>
        </div>
    `;
    const itemId = data.item_id;
    document.getElementById('btn-expand').addEventListener('click', () => submitExpansion(itemId));
    document.getElementById('btn-skip-expand').addEventListener('click', async () => {
        currentNow = null;
        loadExecution();
    });
    setTimeout(() => document.getElementById('expansion-notes')?.focus(), 100);
}

async function submitExpansion(itemId) {
    const notes = document.getElementById('expansion-notes')?.value?.trim();
    if (!notes) { toast('Write your notes first'); return; }
    if (_busy) return;

    const btn = document.getElementById('btn-expand');
    btn.disabled = true;
    btn.textContent = '⏳ Expanding...';
    setBusy(true);

    try {
        const data = await api('/expand', {
            method: 'POST',
            body: JSON.stringify({ item_id: itemId, notes }),
        });

        const resultEl = document.getElementById('expansion-result');
        if (data.status === 'no_tasks') {
            resultEl.innerHTML = `<div class="expansion-empty">No tasks could be generated. ${data.gaps?.length ? 'Gaps: ' + data.gaps.map(g => esc(g)).join(', ') : 'Try adding more detail.'}</div>`;
            resultEl.classList.remove('hidden');
            btn.disabled = false;
            btn.textContent = '🚀 Generate Tasks';
            return;
        }

        let html = `<div class="expansion-success">✅ ${data.task_count} task(s) created:</div>`;
        (data.tasks || []).forEach((t, i) => {
            html += `<div class="expansion-task">
                <span class="task-num">${i + 1}</span>
                <span>${esc(t.content)}</span>
                <span class="expansion-task-meta">${t.duration_minutes}m · ${t.energy_required}</span>
            </div>`;
        });
        if (data.gaps?.length) {
            html += `<div class="expansion-gaps">⚠️ Gaps: ${data.gaps.map(g => esc(g)).join(', ')}</div>`;
        }
        html += `<button id="btn-expansion-done" class="btn-primary" style="margin-top:16px">Continue → Next Task</button>`;
        resultEl.innerHTML = html;
        resultEl.classList.remove('hidden');

        document.getElementById('btn-expansion-done').addEventListener('click', () => {
            currentNow = null;
            loadExecution();
        });

        toast(`✅ ${data.task_count} tasks generated`);
    } catch (e) {
        toast('Error: ' + e.message);
        btn.disabled = false;
        btn.textContent = '🚀 Generate Tasks';
    } finally {
        setBusy(false);
    }
}

// ── Plan view ────────────────────────────────────────────────────

async function loadPlan() {
    // Load goals, intention, review in parallel with plan data
    loadGoals();
    loadDailyIntention();
    loadWeeklyReview();

    try {
        const data = await api('/plan');
        const el = $('#plan-content');
        let html = '';

        const byTrack = data.by_track || {};
        for (const [trackName, trackData] of Object.entries(byTrack)) {
            const tColor = trackData.track_color || 'var(--text-dim)';
            const tIcon = trackData.track_icon || '📁';
            html += `<div class="plan-track-group" style="--plan-track-color: ${tColor}">
                <div class="plan-track-header">
                    <span class="plan-track-icon">${tIcon}</span>
                    <span class="plan-track-name">${esc(trackName)}</span>
                </div>`;

            const clusters = trackData.clusters || {};
            for (const [name, items] of Object.entries(clusters)) {
                html += `<div class="cluster-group">
                    <div class="cluster-name">${esc(name)} <span class="cluster-count">${items.length}</span></div>`;
                for (const item of items) {
                    html += renderPlanItem(item, tColor);
                }
                html += '</div>';
            }
            html += '</div>';
        }

        if (data.pending_inbox && data.pending_inbox.length > 0) {
            html += `<div class="plan-pending"><h3>Pending Inbox (${data.pending_inbox.length})</h3>`;
            for (const item of data.pending_inbox) {
                html += `<div class="plan-item"><div class="status-dot status-inbox"></div><div class="pi-body"><div class="pi-content">${esc(item.raw_input)}</div></div></div>`;
            }
            html += '</div>';
        }

        if (!html) html = '<div class="empty-state"><p>No items yet. Capture something first!</p></div>';
        el.innerHTML = html;
        bindPlanItems();
    } catch (e) {
        toast('Error loading plan');
    }
}

function renderPlanItem(item, trackColor) {
    const statusLabels = { doing: 'Doing', next: 'Next', inbox: 'Inbox', backlog: 'Backlog', done: 'Done', wishful: 'Wish' };
    const isDone = item.status === 'done';
    const isThinking = item.type === 'thinking';
    const isExpanding = item.execution_class === 'expanding';
    const hasDep = item.depends_on != null;
    const borderStyle = trackColor ? `border-left: 3px solid ${trackColor}` : '';
    return `
        <div class="plan-item ${isDone ? 'plan-item-done' : ''} ${isThinking ? 'plan-item-thinking' : ''}" data-item-id="${item.id}" style="${borderStyle}">
            <div class="status-dot status-${item.status}"></div>
            <div class="pi-body">
                <div class="pi-content">
                    ${hasDep ? '<span class="pi-dep-badge" title="Depends on another task">🔗</span> ' : ''}
                    ${isThinking ? '<span class="pi-thinking-badge">🧠</span> ' : ''}
                    ${isExpanding && !isThinking ? '<span class="pi-expanding-badge">📐</span> ' : ''}
                    ${esc(item.content)}
                </div>
                <div class="pi-meta">
                    <span>${item.duration_minutes || '?'}m</span>
                    <span>· ${item.layer}</span>
                    <span>· ${item.energy_required || 'medium'}</span>
                    ${isThinking ? '<span>· thinking</span>' : ''}
                    ${hasDep ? `<span>· depends on #${item.depends_on}</span>` : ''}
                    <span class="pi-status-label status-label-${item.status}">${statusLabels[item.status] || item.status}</span>
                </div>
            </div>
            <div class="pi-actions">
                ${isDone ? '' : `<button class="pi-btn pi-btn-edit" data-id="${item.id}" title="Edit">✏️</button>`}
                <button class="pi-btn pi-btn-status" data-id="${item.id}" data-status="${item.status}" title="Cycle status">⟳</button>
                <button class="pi-btn pi-btn-delete" data-id="${item.id}" title="Delete">🗑</button>
            </div>
        </div>`;
}

function bindPlanItems() {
    // Edit
    document.querySelectorAll('.pi-btn-edit').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (_busy) return;
            const id = parseInt(btn.dataset.id);
            const itemEl = btn.closest('.plan-item');
            const content = itemEl.querySelector('.pi-content').textContent;
            openEditModal(id, content);
        });
    });
    // Status cycle
    document.querySelectorAll('.pi-btn-status').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (_busy) return;
            const id = parseInt(btn.dataset.id);
            const current = btn.dataset.status;
            const cycle = ['inbox', 'next', 'doing', 'done', 'backlog'];
            const nextStatus = cycle[(cycle.indexOf(current) + 1) % cycle.length];
            setBusy(true);
            btn.disabled = true;
            try {
                await api(`/items/${id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) });
                toast(`→ ${nextStatus}`);
                loadPlan();
            } catch (err) {
                toast('Error: ' + err.message);
            } finally {
                setBusy(false);
            }
        });
    });
    // Delete
    document.querySelectorAll('.pi-btn-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (_busy) return;
            openDeleteConfirm(parseInt(btn.dataset.id));
        });
    });
}

// ── Goals ─────────────────────────────────────────────────────────

async function loadGoals() {
    const el = $('#goals-list');
    if (!el) return;
    try {
        const data = await api('/goals');
        const goals = data.goals || [];
        if (!goals.length) {
            el.innerHTML = '<p class="text-dim" style="font-size:0.85rem;">No goals yet. Add one to anchor your work.</p>';
            return;
        }
        el.innerHTML = goals.map(g => `
            <div class="goal-card" data-goal-id="${g.id}">
                <div class="goal-info">
                    <div class="goal-title">${esc(g.summary)}</div>
                    <div class="goal-meta">${g.done_tasks || 0} done · ${g.pending_tasks || 0} remaining</div>
                </div>
                <button class="goal-archive-btn" data-goal-id="${g.id}" title="Archive">&times;</button>
            </div>
        `).join('');
        el.querySelectorAll('.goal-archive-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await api('/goals/' + btn.dataset.goalId, { method: 'DELETE' });
                toast('Goal archived');
                loadGoals();
            });
        });
    } catch (e) { /* fail silently */ }
}

$('#btn-add-goal').addEventListener('click', () => {
    $('#goal-form').classList.remove('hidden');
    $('#goal-input').focus();
});

$('#btn-goal-cancel').addEventListener('click', () => {
    $('#goal-form').classList.add('hidden');
    $('#goal-input').value = '';
});

$('#btn-goal-save').addEventListener('click', async () => {
    const summary = $('#goal-input').value.trim();
    if (!summary) return;
    try {
        await api('/goals', { method: 'POST', body: JSON.stringify({ summary }) });
        toast('Goal added');
        $('#goal-form').classList.add('hidden');
        $('#goal-input').value = '';
        loadGoals();
    } catch (e) {
        toast('Error adding goal');
    }
});

$('#goal-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        $('#btn-goal-save').click();
    }
});

// ── Daily Intention ──────────────────────────────────────────────

async function loadDailyIntention() {
    const el = $('#intention-content');
    if (!el) return;
    try {
        const data = await api('/daily/intention');
        if (data.intention) {
            const text = data.intention.focus_text || '';
            el.innerHTML = `<div class="intention-set"><span class="intention-text">${esc(text)}</span>
                <button id="btn-reset-intention" class="btn-sm" style="margin-left:8px;font-size:0.75rem">Change</button></div>`;
            $('#btn-reset-intention').addEventListener('click', () => renderIntentionForm(data.top_goals));
        } else {
            renderIntentionForm(data.top_goals || []);
        }
    } catch (e) { /* fail silently */ }
}

function renderIntentionForm(topGoals) {
    const el = $('#intention-content');
    let goalsHtml = '';
    if (topGoals.length) {
        goalsHtml = '<div class="intention-goals">' + topGoals.map(g =>
            `<button class="intention-goal-btn" data-gid="${g.id}" data-text="${esc(g.summary)}">${esc(g.summary)} (${g.pending} left)</button>`
        ).join('') + '</div>';
    }
    el.innerHTML = `
        ${goalsHtml}
        <div class="intention-custom">
            <input id="intention-text" type="text" placeholder="What's your main focus today?" class="goal-input">
            <button id="btn-set-intention" class="btn-primary" style="font-size:0.82rem;padding:8px 14px;margin-top:6px">Set Focus</button>
        </div>`;
    el.querySelectorAll('.intention-goal-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            $('#intention-text').value = btn.dataset.text;
        });
    });
    $('#btn-set-intention').addEventListener('click', async () => {
        const text = $('#intention-text').value.trim();
        if (!text) return;
        await api('/daily/intention', { method: 'POST', body: JSON.stringify({ focus_text: text }) });
        toast('Focus set!');
        loadDailyIntention();
    });
}

// ── Weekly Review ────────────────────────────────────────────────

async function loadWeeklyReview() {
    const el = $('#review-content');
    if (!el) return;
    try {
        const data = await api('/review/weekly');
        let html = `<div class="review-stats">
            <div class="review-stat"><span class="review-num">${data.completed_count}</span> completed</div>
            <div class="review-stat"><span class="review-num">${data.skipped_count}</span> skipped</div>
            <div class="review-stat"><span class="review-num">${data.goal_task_count}</span> goal-aligned</div>
        </div>`;

        if (data.productivity_trap) {
            html += `<div class="review-trap">${esc(data.trap_message)}</div>`;
        }

        const skipCats = data.skip_categories || {};
        if (Object.keys(skipCats).length) {
            html += '<div class="review-skips"><strong>Skip patterns:</strong> ' +
                Object.entries(skipCats).map(([k,v]) => `${k}: ${v}`).join(', ') + '</div>';
        }

        el.innerHTML = html;
    } catch (e) {
        el.innerHTML = '<p class="text-dim" style="font-size:0.85rem;">Could not load review.</p>';
    }
}

// ── Edit Modal ───────────────────────────────────────────────────

function openEditModal(itemId, currentContent) {
    let modal = $('#edit-modal');
    if (!modal) {
        document.getElementById('app').insertAdjacentHTML('beforeend', `
            <div id="edit-modal" class="modal hidden">
                <div class="modal-content">
                    <h3>Edit Task</h3>
                    <textarea id="edit-content" rows="3"></textarea>
                    <div class="edit-fields">
                        <label>Duration (min)
                            <input id="edit-duration" type="number" min="5" max="120" value="30">
                        </label>
                        <label>Energy
                            <select id="edit-energy">
                                <option value="low">Low</option>
                                <option value="medium" selected>Medium</option>
                                <option value="high">High</option>
                            </select>
                        </label>
                        <label>Status
                            <select id="edit-status">
                                <option value="inbox">Inbox</option>
                                <option value="next">Next</option>
                                <option value="doing">Doing</option>
                                <option value="backlog">Backlog</option>
                                <option value="done">Done</option>
                                <option value="wishful">Wishful</option>
                            </select>
                        </label>
                    </div>
                    <div class="modal-actions">
                        <button id="btn-edit-save" class="btn-primary">Save</button>
                        <button id="btn-edit-cancel" class="btn-secondary">Cancel</button>
                    </div>
                </div>
            </div>
        `);
        modal = $('#edit-modal');
        modal.addEventListener('click', (e) => { if (e.target === modal) closeEditModal(); });
        $('#btn-edit-cancel').addEventListener('click', closeEditModal);
    }
    $('#edit-content').value = currentContent;
    modal.dataset.itemId = itemId;
    modal.classList.remove('hidden');
    setTimeout(() => $('#edit-content').focus(), 100);

    // Clone save button to remove old listeners
    const saveBtn = $('#btn-edit-save');
    const newSave = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSave, saveBtn);
    newSave.addEventListener('click', async () => {
        if (_busy) return;
        setBusy(true);
        newSave.disabled = true;
        const body = {};
        const newContent = $('#edit-content').value.trim();
        if (newContent && newContent !== currentContent) body.content = newContent;
        const dur = parseInt($('#edit-duration').value);
        if (dur && dur >= 5) body.duration_minutes = dur;
        body.energy_required = $('#edit-energy').value;
        body.status = $('#edit-status').value;
        try {
            await api(`/items/${modal.dataset.itemId}`, { method: 'PATCH', body: JSON.stringify(body) });
            toast('✓ Updated');
            closeEditModal();
            loadPlan();
        } catch (err) {
            toast('Error: ' + err.message);
        } finally {
            newSave.disabled = false;
            setBusy(false);
        }
    });
}

function closeEditModal() {
    const m = $('#edit-modal');
    if (m) m.classList.add('hidden');
}

// ── Delete Confirm ───────────────────────────────────────────────

function openDeleteConfirm(itemId) {
    let modal = $('#delete-modal');
    if (!modal) {
        document.getElementById('app').insertAdjacentHTML('beforeend', `
            <div id="delete-modal" class="modal hidden">
                <div class="modal-content modal-sm">
                    <h3>Delete this task?</h3>
                    <p style="color:var(--text-dim);font-size:14px;margin-bottom:16px">This cannot be undone.</p>
                    <div class="modal-actions">
                        <button id="btn-delete-confirm" class="btn-danger">Delete</button>
                        <button id="btn-delete-cancel" class="btn-secondary">Cancel</button>
                    </div>
                </div>
            </div>
        `);
        modal = $('#delete-modal');
        modal.addEventListener('click', (e) => { if (e.target === modal) closeDeleteModal(); });
        $('#btn-delete-cancel').addEventListener('click', closeDeleteModal);
    }
    modal.dataset.itemId = itemId;
    modal.classList.remove('hidden');

    const btn = $('#btn-delete-confirm');
    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);
    newBtn.addEventListener('click', async () => {
        if (_busy) return;
        setBusy(true);
        newBtn.disabled = true;
        try {
            await api(`/items/${modal.dataset.itemId}`, { method: 'DELETE' });
            toast('🗑 Deleted');
            closeDeleteModal();
            loadPlan();
        } catch (err) {
            toast('Error: ' + err.message);
        } finally {
            newBtn.disabled = false;
            setBusy(false);
        }
    });
}

function closeDeleteModal() {
    const m = $('#delete-modal');
    if (m) m.classList.add('hidden');
}

// ── Wishes view ──────────────────────────────────────────────────

async function loadWishes() {
    const container = $('#wishes-content');
    if (!container) return;
    container.innerHTML = '<p style="text-align:center; color:var(--text-dim);">Loading...</p>';

    try {
        const data = await api('/wishlist');
        const items = data.items || [];

        if (items.length === 0) {
            container.innerHTML = `
                <div class="wishes-empty">
                    <p>🌈</p>
                    <p>No wishes yet</p>
                    <p class="wishes-hint">Capture a dream or bucket list idea in the Capture tab.<br>Wishful items are detected automatically.</p>
                </div>
            `;
            return;
        }

        let html = '';
        for (const item of items) {
            const cluster = item.cluster ? `<span>${esc(item.cluster)}</span>` : '';
            const track = item.track_name ? `<span>${esc(item.track_icon || '')} ${esc(item.track_name)}</span>` : '';
            const created = item.created_at ? `<span>${new Date(item.created_at + 'Z').toLocaleDateString()}</span>` : '';
            html += `
                <div class="wish-card" data-id="${item.id}">
                    <div class="wish-icon">🌟</div>
                    <div class="wish-body">
                        <div class="wish-content">${esc(item.content)}</div>
                        <div class="wish-meta">${cluster}${track}${created}</div>
                    </div>
                    <div class="wish-actions">
                        <button class="wish-btn wish-btn-promote" onclick="promoteWish(${item.id})">Activate</button>
                        <button class="pi-btn pi-btn-delete" onclick="deleteWish(${item.id})">🗑</button>
                    </div>
                </div>
            `;
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="text-align:center; color:var(--red);">Failed to load wishes</p>';
    }
}

async function promoteWish(itemId) {
    if (_busy) return;
    setBusy(true);
    try {
        await api('/wishlist/promote', { method: 'POST', body: JSON.stringify({ item_id: itemId, to_status: 'inbox' }) });
        toast('Wish promoted to inbox!');
        loadWishes();
    } catch (e) {
        toast('Failed to promote');
    } finally {
        setBusy(false);
    }
}

async function deleteWish(itemId) {
    if (_busy) return;
    setBusy(true);
    try {
        await api(`/items/${itemId}`, { method: 'DELETE' });
        toast('Wish removed');
        loadWishes();
    } catch (e) {
        toast('Failed to delete');
    } finally {
        setBusy(false);
    }
}

// ── Util ─────────────────────────────────────────────────────────

function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ── Init ─────────────────────────────────────────────────────────

loadPending();

// ── Service Worker ───────────────────────────────────────────────

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
}
