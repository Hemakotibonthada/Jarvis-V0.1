/* ═══════════════════════════════════════════════════════
   J.A.R.V.I.S — Control Board Application
   WebSocket client, UI logic, audio handling
   ═══════════════════════════════════════════════════════ */

const WS_URL = `ws://${location.hostname || 'localhost'}:8765`;

// ── State ──────────────────────────────────────────
let ws = null;
let state = 'disconnected';
let audioCtx = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let pingStart = 0;
let frameCount = 0;
let lastFpsTime = 0;

// ── Always-on listening state ──────────────────────
let monitorStream = null;
let monitorSource = null;
let monitorAnalyser = null;
let monitorProcessor = null;
let monitorActive = false;
let wakeAudioChunks = [];
let wakeBufferDuration = 0;
const WAKE_CHECK_INTERVAL = 3.0;  // seconds
const WAKE_ENERGY_GATE = 0.008;   // min RMS to consider as speech
let wakeSpeechDetected = false;    // only send check if speech was heard
const CLAP_THRESHOLD = 0.35;      // RMS for clap
const CLAP_CREST_MIN = 3.0;       // peak/RMS ratio
const CLAP_GAP_MIN = 0.1;
const CLAP_GAP_MAX = 0.7;
let clapFirstTime = 0;
let clapWaiting = false;
let clapCooldown = 0;

// ── DOM refs ───────────────────────────────────────
const $ = id => document.getElementById(id);
const statusText   = $('statusText');
const reactorLabel = $('reactorLabel');
const connStatus   = $('connStatus');
const latencyEl    = $('latency');
const fpsEl        = $('fpsDisplay');
const micBtn       = $('micBtn');
const micLabel     = $('micLabel');
const textInput    = $('textInput');
const sendBtn      = $('sendBtn');
const convEl       = $('conversation');
const diagEl       = $('diagnostics');
const clockEl      = $('clock');
const dateEl       = $('dateDisplay');

// ── Animation instances ────────────────────────────
const particles = new ParticleField($('particles'));
const reactor   = new ArcReactor($('reactor'));
const waveform  = new WaveformVis($('waveform'));

// ── Clock ──────────────────────────────────────────
function updateClock() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
    dateEl.textContent = now.toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric'
    });
}
setInterval(updateClock, 1000);
updateClock();

// ── Animation Loop ─────────────────────────────────
function animate(timestamp) {
    particles.draw();
    reactor.draw();
    waveform.draw();

    // FPS counter
    frameCount++;
    if (timestamp - lastFpsTime > 1000) {
        fpsEl.textContent = `${frameCount} fps`;
        frameCount = 0;
        lastFpsTime = timestamp;
    }

    requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ── WebSocket Connection ───────────────────────────
function connect() {
    if (ws && ws.readyState <= 1) return;

    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        setConnected(true);
        addSystemMsg('Connected to Jarvis server');
        setInterval(sendPing, 5000);
        // Auto-request mic permission early (user gesture may be needed)
        navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
            monitorStream = stream;
            console.log('Mic permission granted');
        }).catch(err => console.warn('Mic not available:', err));
    };

    ws.onclose = () => {
        setConnected(false);
        addSystemMsg('Disconnected — reconnecting...');
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        setConnected(false);
    };

    ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
            handleBinary(event.data);
        } else {
            handleJSON(event.data);
        }
    };
}

function setConnected(connected) {
    connStatus.textContent = connected ? '● CONNECTED' : '● DISCONNECTED';
    connStatus.className = 'conn-status' + (connected ? ' connected' : '');
    if (!connected) {
        setState('disconnected');
    }
}

function sendPing() {
    if (ws && ws.readyState === 1) {
        pingStart = performance.now();
        ws.send(JSON.stringify({ type: 'ping' }));
    }
}

// ── Message Handlers ───────────────────────────────
function handleJSON(raw) {
    let data;
    try { data = JSON.parse(raw); } catch { return; }

    switch (data.type) {
        case 'welcome':
            addSystemMsg(data.message || 'Jarvis online');
            break;

        case 'state':
            setState(data.state, data.message);
            break;

        case 'diagnostics':
            renderDiagnostics(data);
            break;

        case 'transcript':
            addUserMsg(data.text);
            break;

        case 'response_text':
            if (data.done) {
                finalizeJarvisMsg(data.text);
            } else {
                appendJarvisStream(data.text);
            }
            break;

        case 'action':
            addSystemMsg(`Action: ${data.action}`);
            break;

        case 'error':
            addSystemMsg(`Error: ${data.message}`, true);
            break;

        case 'wake_detected':
            addSystemMsg(`Wake word: "${data.text}"`);
            // Server already set state to listening, start recording
            startRecording();
            break;

        case 'pong':
            latencyEl.textContent = `${Math.round(performance.now() - pingStart)} ms`;
            break;
    }
}

function handleBinary(buffer) {
    const view = new DataView(buffer);
    if (view.getUint8(0) !== 0x01 || buffer.byteLength < 6) return;

    const sampleRate = view.getUint32(1, true);  // little-endian
    const pcmData = new Int16Array(buffer, 5);

    playAudio(pcmData, sampleRate);
}

// ── State Machine ──────────────────────────────────
function setState(newState, message) {
    state = newState || 'idle';

    // Update body class
    document.body.className = `state-${state}`;

    // Status text
    const labels = {
        idle: 'READY',
        listening: 'LISTENING',
        processing: 'PROCESSING',
        speaking: 'SPEAKING',
        error: 'ERROR',
        disconnected: 'OFFLINE',
    };
    statusText.textContent = labels[state] || state.toUpperCase();

    // Reactor
    reactor.setState(state);
    reactorLabel.textContent = labels[state] || state.toUpperCase();

    // Waveform
    waveform.setActive(state === 'listening' || state === 'speaking');

    // Mic button
    if (state === 'listening') {
        micBtn.classList.add('active');
        micLabel.textContent = 'LISTENING...';
        stopMonitor();  // Stop wake detection while actively recording
    } else {
        micBtn.classList.remove('active');
        micLabel.textContent = 'SAY "JARVIS" OR CLAP';
    }

    // Restart always-on monitor when idle
    if (state === 'idle') {
        setTimeout(() => startMonitor(), 500);
    } else if (state !== 'idle' && state !== 'disconnected') {
        stopMonitor();
    }
}

// ── Diagnostics Renderer ───────────────────────────
function renderDiagnostics(data) {
    const services = data.services || [];
    diagEl.innerHTML = '';

    const icons = { online: '✓', fallback: '~', offline: '✗' };

    services.forEach((svc, i) => {
        const div = document.createElement('div');
        div.className = `diag-item ${svc.status}`;
        div.style.animationDelay = `${i * 0.08}s`;

        const name = svc.service.replace('feature_', '').replace(/_/g, ' ');

        div.innerHTML = `
            <div class="diag-icon">${icons[svc.status] || '?'}</div>
            <div class="diag-info">
                <span class="diag-name">${name.toUpperCase()}</span>
                <span class="diag-status">${svc.status.toUpperCase()} — ${svc.detail}</span>
            </div>
        `;

        diagEl.appendChild(div);
    });

    // Summary footer
    const summary = document.createElement('div');
    summary.className = 'diag-item online';
    summary.style.animationDelay = `${services.length * 0.08}s`;
    summary.innerHTML = `
        <div class="diag-icon" style="font-size:12px">Σ</div>
        <div class="diag-info">
            <span class="diag-name">${data.ok}/${data.total} SYSTEMS OK</span>
            <span class="diag-status">SELF-CHECK COMPLETE</span>
        </div>
    `;
    diagEl.appendChild(summary);
}

// ── Conversation ───────────────────────────────────
let streamingEl = null;

function clearEmpty() {
    const empty = convEl.querySelector('.conv-empty');
    if (empty) empty.remove();
}

function addUserMsg(text) {
    clearEmpty();
    const div = document.createElement('div');
    div.className = 'conv-msg user';
    div.innerHTML = `<div class="conv-sender">YOU</div><div>${escapeHtml(text)}</div>`;
    convEl.appendChild(div);
    convEl.scrollTop = convEl.scrollHeight;
}

function appendJarvisStream(text) {
    clearEmpty();
    if (!streamingEl) {
        streamingEl = document.createElement('div');
        streamingEl.className = 'conv-msg jarvis';
        streamingEl.innerHTML = `<div class="conv-sender">JARVIS</div><div class="conv-body"></div>`;
        convEl.appendChild(streamingEl);
    }
    const body = streamingEl.querySelector('.conv-body');
    body.textContent += text;
    convEl.scrollTop = convEl.scrollHeight;
}

function finalizeJarvisMsg(text) {
    clearEmpty();
    if (streamingEl) {
        const body = streamingEl.querySelector('.conv-body');
        if (text) body.textContent = text;
        streamingEl = null;
    } else if (text) {
        const div = document.createElement('div');
        div.className = 'conv-msg jarvis';
        div.innerHTML = `<div class="conv-sender">JARVIS</div><div>${escapeHtml(text)}</div>`;
        convEl.appendChild(div);
    }
    convEl.scrollTop = convEl.scrollHeight;
}

function addSystemMsg(text, isError = false) {
    clearEmpty();
    const div = document.createElement('div');
    div.className = 'conv-msg system';
    if (isError) div.style.borderColor = 'rgba(255, 59, 59, 0.3)';
    div.textContent = text;
    convEl.appendChild(div);
    convEl.scrollTop = convEl.scrollHeight;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Audio Playback ─────────────────────────────────
function playAudio(int16Data, sampleRate) {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }

    const float32 = new Float32Array(int16Data.length);
    for (let i = 0; i < int16Data.length; i++) {
        float32[i] = int16Data[i] / 32768;
    }

    const buffer = audioCtx.createBuffer(1, float32.length, sampleRate);
    buffer.getChannelData(0).set(float32);

    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(audioCtx.destination);
    source.start();
}

// ── Microphone Recording (with auto-silence detection) ─
let silenceStart = 0;
let speechDetected = false;
let recordStart = 0;
const SILENCE_THRESHOLD = 0.012;
const SILENCE_TIMEOUT = 1500;    // ms of silence to auto-stop
const MAX_RECORD_MS = 15000;     // hard cap

async function startRecording() {
    if (isRecording) return;
    if (!ws || ws.readyState !== 1) return;

    stopMonitor();

    try {
        if (audioCtx) await audioCtx.resume();

        const stream = monitorStream || await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
        });

        isRecording = true;
        speechDetected = false;
        silenceStart = performance.now();
        recordStart = performance.now();

        // Signal server: recording start
        const startMarker = new Uint8Array([0x02]);
        ws.send(startMarker.buffer);

        if (!audioCtx) audioCtx = new AudioContext({ sampleRate: 16000 });
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);

        audioChunks = [];

        processor.onaudioprocess = (e) => {
            if (!isRecording) return;
            const float32 = e.inputBuffer.getChannelData(0);

            // RMS for silence detection
            let sum = 0;
            for (let i = 0; i < float32.length; i++) sum += float32[i] * float32[i];
            const rms = Math.sqrt(sum / float32.length);

            if (rms > SILENCE_THRESHOLD) {
                speechDetected = true;
                silenceStart = performance.now();
            } else if (speechDetected && (performance.now() - silenceStart > SILENCE_TIMEOUT)) {
                // Auto-stop on silence after speech
                stopRecording();
                return;
            }

            // Hard cap
            if (performance.now() - recordStart > MAX_RECORD_MS) {
                stopRecording();
                return;
            }

            // Convert to int16 and send
            const int16 = new Int16Array(float32.length);
            for (let i = 0; i < float32.length; i++) {
                int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
            }

            const packet = new Uint8Array(1 + int16.byteLength);
            packet[0] = 0x01;
            packet.set(new Uint8Array(int16.buffer), 1);
            ws.send(packet.buffer);

            audioChunks.push(int16);
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);

        window._micStream = stream;
        window._micSource = source;
        window._micProcessor = processor;

        setState('listening');

    } catch (err) {
        console.error('Mic access error:', err);
        addSystemMsg('Microphone access denied', true);
        isRecording = false;
    }
}

function stopRecording() {
    if (!isRecording) return;

    // Minimum 0.3s of recording to avoid empty sends
    if (recordStart && (performance.now() - recordStart) < 300) {
        return;
    }

    isRecording = false;

    // Cleanup processor (keep mic stream for monitor reuse)
    if (window._micProcessor) {
        window._micProcessor.disconnect();
        window._micProcessor = null;
    }
    if (window._micSource) {
        window._micSource.disconnect();
        window._micSource = null;
    }
    // Don't close monitorStream — reuse it for always-on listening

    // Signal server: recording end
    if (ws && ws.readyState === 1) {
        const endMarker = new Uint8Array([0x03]);
        ws.send(endMarker.buffer);
    }
}

// ── Quick Action Commands ──────────────────────────
const QUICK_COMMANDS = {
    time:   'What time is it?',
    timer:  'Set a timer for 5 minutes',
    note:   'Save a note: remember to check the system',
    lights: 'Turn on the lights',
    music:  'Play music',
    clear:  'Clear conversation history',
};

// ── Event Listeners ────────────────────────────────
// Mic button: click to toggle (auto-stops on silence)
micBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
});

// Touch support
micBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
});

// Text input
textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        sendTextCommand();
    }
});

sendBtn.addEventListener('click', sendTextCommand);

function sendTextCommand() {
    const text = textInput.value.trim();
    if (!text || !ws || ws.readyState !== 1) return;

    ws.send(JSON.stringify({ type: 'text_input', text }));
    addUserMsg(text);
    textInput.value = '';
}

// Quick action buttons
document.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const cmd = QUICK_COMMANDS[action];
        if (cmd && ws && ws.readyState === 1) {
            ws.send(JSON.stringify({ type: 'text_input', text: cmd }));
            addUserMsg(cmd);

            // Button pulse effect
            btn.style.transform = 'scale(0.95)';
            setTimeout(() => btn.style.transform = '', 150);
        }
    });
});

// Keyboard shortcut: Space to toggle record
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && document.activeElement !== textInput) {
        e.preventDefault();
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    }
});

// ── Boot ───────────────────────────────────────────
setState('disconnected');
connect();

// ═══════════════════════════════════════════════════════
// Always-On Mic Monitor — Clap Detection + Wake Word
// ═══════════════════════════════════════════════════════

async function startMonitor() {
    if (monitorActive || isRecording) return;
    if (!ws || ws.readyState !== 1) return;
    if (state !== 'idle') return;

    try {
        // Request mic once, reuse
        if (!monitorStream) {
            monitorStream = await navigator.mediaDevices.getUserMedia({
                audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
            });
        }

        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        }

        monitorSource = audioCtx.createMediaStreamSource(monitorStream);
        monitorAnalyser = audioCtx.createAnalyser();
        monitorAnalyser.fftSize = 2048;

        // ScriptProcessor for raw audio access
        monitorProcessor = audioCtx.createScriptProcessor(2048, 1, 1);
        wakeAudioChunks = [];
        wakeBufferDuration = 0;
        monitorActive = true;

        monitorProcessor.onaudioprocess = (e) => {
            if (!monitorActive || state !== 'idle') return;

            const f32 = e.inputBuffer.getChannelData(0);

            // ── Clap Detection ──
            if (detectClap(f32)) {
                console.log('DOUBLE CLAP detected!');
                addSystemMsg('Double-clap detected!');
                triggerWake();
                return;
            }

            // ── Energy gate: only accumulate if there's speech ──
            let sum = 0;
            for (let i = 0; i < f32.length; i++) sum += f32[i] * f32[i];
            const rms = Math.sqrt(sum / f32.length);

            if (rms > WAKE_ENERGY_GATE) {
                wakeSpeechDetected = true;
                wakeAudioChunks.push(new Float32Array(f32));
            }
            wakeBufferDuration += f32.length / 16000;

            // Only send to Whisper if speech was detected in this window
            if (wakeBufferDuration >= WAKE_CHECK_INTERVAL) {
                if (wakeSpeechDetected && wakeAudioChunks.length > 0) {
                    sendWakeCheck();
                } else {
                    // Silent window — just reset, don't waste server CPU
                    wakeAudioChunks = [];
                    wakeBufferDuration = 0;
                }
                wakeSpeechDetected = false;
            }
        };

        monitorSource.connect(monitorAnalyser);
        monitorAnalyser.connect(monitorProcessor);
        monitorProcessor.connect(audioCtx.destination);

        micLabel.textContent = 'SAY "JARVIS" OR CLAP';
        console.log('Always-on monitor started');

    } catch (err) {
        console.error('Monitor start error:', err);
        monitorActive = false;
    }
}

function stopMonitor() {
    monitorActive = false;

    if (monitorProcessor) {
        try { monitorProcessor.disconnect(); } catch {}
        monitorProcessor = null;
    }
    if (monitorAnalyser) {
        try { monitorAnalyser.disconnect(); } catch {}
        monitorAnalyser = null;
    }
    if (monitorSource) {
        try { monitorSource.disconnect(); } catch {}
        monitorSource = null;
    }
    // Keep monitorStream alive (don't close mic) for fast restart

    wakeAudioChunks = [];
    wakeBufferDuration = 0;
    wakeSpeechDetected = false;
}

function detectClap(f32) {
    const now = performance.now() / 1000;
    if (now < clapCooldown) return false;

    // Compute RMS and peak
    let sum = 0, peak = 0;
    for (let i = 0; i < f32.length; i++) {
        const v = Math.abs(f32[i]);
        sum += v * v;
        if (v > peak) peak = v;
    }
    const rms = Math.sqrt(sum / f32.length);
    if (rms < 0.001) return false;
    const crest = peak / rms;

    const isClap = rms > CLAP_THRESHOLD && crest > CLAP_CREST_MIN;

    if (isClap) {
        if (clapWaiting) {
            const gap = now - clapFirstTime;
            if (gap >= CLAP_GAP_MIN && gap <= CLAP_GAP_MAX) {
                clapWaiting = false;
                clapCooldown = now + 2.0;
                return true;  // Double clap!
            }
            if (gap > CLAP_GAP_MAX) {
                clapFirstTime = now;
            }
        } else {
            clapFirstTime = now;
            clapWaiting = true;
        }
    }

    if (clapWaiting && (now - clapFirstTime) > CLAP_GAP_MAX) {
        clapWaiting = false;
    }

    return false;
}

function sendWakeCheck() {
    if (!ws || ws.readyState !== 1) return;
    if (wakeAudioChunks.length === 0) return;

    // Concatenate accumulated audio
    let totalLen = 0;
    for (const c of wakeAudioChunks) totalLen += c.length;
    const combined = new Float32Array(totalLen);
    let offset = 0;
    for (const c of wakeAudioChunks) {
        combined.set(c, offset);
        offset += c.length;
    }

    // Convert float32 to int16
    const int16 = new Int16Array(combined.length);
    for (let i = 0; i < combined.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(combined[i] * 32767)));
    }

    // Base64 encode and send to server for Whisper check
    const bytes = new Uint8Array(int16.buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    const b64 = btoa(binary);

    ws.send(JSON.stringify({
        type: 'wake_check',
        audio: b64,
    }));

    // Keep last 0.3s for overlap, reset buffer
    const keepSamples = Math.floor(0.3 * 16000);
    if (combined.length > keepSamples) {
        wakeAudioChunks = [combined.slice(-keepSamples)];
        wakeBufferDuration = 0.3;
    } else {
        wakeAudioChunks = [];
        wakeBufferDuration = 0;
    }
}

function triggerWake() {
    stopMonitor();
    // Send wake word signal to server and start recording
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ type: 'wake_word' }));
    }
    startRecording();
}
