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
        // Ping for latency
        setInterval(sendPing, 5000);
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
    } else {
        micBtn.classList.remove('active');
        micLabel.textContent = 'PRESS TO SPEAK';
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

// ── Microphone Recording ───────────────────────────
async function startRecording() {
    if (isRecording) return;
    if (!ws || ws.readyState !== 1) return;

    try {
        // Resume audio context (browser policy)
        if (audioCtx) await audioCtx.resume();

        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
        });

        isRecording = true;

        // Signal server: recording start
        const startMarker = new Uint8Array([0x02]);
        ws.send(startMarker.buffer);

        // Create ScriptProcessor for raw PCM
        if (!audioCtx) audioCtx = new AudioContext({ sampleRate: 16000 });
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);

        audioChunks = [];

        processor.onaudioprocess = (e) => {
            if (!isRecording) return;
            const float32 = e.inputBuffer.getChannelData(0);

            // Convert to int16
            const int16 = new Int16Array(float32.length);
            for (let i = 0; i < float32.length; i++) {
                int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
            }

            // Send with 0x01 marker
            const packet = new Uint8Array(1 + int16.byteLength);
            packet[0] = 0x01;
            packet.set(new Uint8Array(int16.buffer), 1);
            ws.send(packet.buffer);

            audioChunks.push(int16);
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);

        // Store for cleanup
        window._micStream = stream;
        window._micSource = source;
        window._micProcessor = processor;

    } catch (err) {
        console.error('Mic access error:', err);
        addSystemMsg('Microphone access denied', true);
        isRecording = false;
    }
}

function stopRecording() {
    if (!isRecording) return;
    isRecording = false;

    // Cleanup
    if (window._micProcessor) {
        window._micProcessor.disconnect();
        window._micProcessor = null;
    }
    if (window._micSource) {
        window._micSource.disconnect();
        window._micSource = null;
    }
    if (window._micStream) {
        window._micStream.getTracks().forEach(t => t.stop());
        window._micStream = null;
    }

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
// Mic button: press and hold
micBtn.addEventListener('mousedown', (e) => {
    e.preventDefault();
    startRecording();
});

micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('mouseleave', stopRecording);

// Touch support
micBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    startRecording();
});

micBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    stopRecording();
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

// Keyboard shortcut: Space to record
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && document.activeElement !== textInput && !isRecording) {
        e.preventDefault();
        startRecording();
    }
});

document.addEventListener('keyup', (e) => {
    if (e.code === 'Space' && document.activeElement !== textInput) {
        e.preventDefault();
        stopRecording();
    }
});

// ── Boot ───────────────────────────────────────────
setState('disconnected');
connect();
