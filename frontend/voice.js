import Vapi from 'https://esm.sh/@vapi-ai/web';

// ─── Config ────────────────────────────────────────────────────────────────
// Empty string = relative URLs, works on localhost:8000 AND through ngrok
const BACKEND_URL = '';
const VAPI_PUBLIC_KEY = '214915eb-a2c4-4a12-a5ed-25cdf9b7c61a';
const ASSISTANT_ID    = '66c72102-02ea-4c75-98e9-8974555e282b';

// ─── User identity ────────────────────────────────────────────────────────────
// reads the UUID already created when the user
// connected their calendar, so the same key is used throughout.
function getOrCreateUserId() {
  let userId = localStorage.getItem('calendarUserId');
  if (!userId) {
    userId = crypto.randomUUID();
    localStorage.setItem('calendarUserId', userId);
  }
  return userId;
}

// ─── DOM refs ──────────────────────────────────────────────────────────────
const micBtn      = document.getElementById('mic-btn');
const micWrapper  = document.getElementById('mic-wrapper');
const micIcon     = document.getElementById('mic-icon');
const stopIcon    = document.getElementById('stop-icon');
const spinner     = document.getElementById('spinner');
const statusLabel = document.getElementById('status-label');
const statusSub   = document.getElementById('status-sub');
const waveform    = document.getElementById('waveform');
const permCard    = document.getElementById('permission-card');
const retryBtn    = document.getElementById('retry-btn');

// ─── Runtime state ──────────────────────────────────────────────────────────
let vapi         = null;
let isCallActive = false;

// ─── UI helpers ──────────────────────────────────────────────────────────────
function show(el)  { el.classList.remove('v-hidden'); }
function hide(el)  { el.classList.add('v-hidden'); }

function setIcons({ mic = false, stop = false, spin = false } = {}) {
  mic  ? show(micIcon)  : hide(micIcon);
  stop ? show(stopIcon) : hide(stopIcon);
  spin ? show(spinner)  : hide(spinner);
}

function setStatus(label, sub = '') {
  statusLabel.textContent = label;
  statusSub.textContent   = sub;
}

function setWaveform(active, agentMode = false) {
  waveform.classList.toggle('active', active);
  waveform.classList.toggle('agent-mode', agentMode);
}

// ─── State machine ───────────────────────────────────────────────────────────
function applyState(state) {
  // Reset shared classes
  micWrapper.className = 'mic-wrapper';
  micBtn.disabled = false;
  hide(permCard);
  setWaveform(false);

  switch (state) {
    case 'idle':
      setIcons({ mic: true });
      setStatus('Tap to speak', 'Your AI assistant is ready');
      break;

    case 'requesting-mic':
      setIcons({ spin: true });
      setStatus('Checking microphone…', 'Please allow access when prompted');
      micBtn.disabled = true;
      break;

    case 'mic-denied':
      setIcons({ mic: true });
      setStatus('Microphone required', '');
      show(permCard);
      break;

    case 'connecting':
      setIcons({ spin: true });
      setStatus('Connecting…', 'Starting your voice assistant');
      micBtn.disabled = true;
      break;

    case 'listening':
      setIcons({ stop: true });
      setStatus('Listening', 'Speak naturally — tap to end call');
      micWrapper.classList.add('active');
      break;

    case 'user-speaking':
      setIcons({ stop: true });
      setStatus('Listening…', "Go ahead, I'm listening");
      micWrapper.classList.add('active', 'user-speaking');
      setWaveform(true, false);
      break;

    case 'agent-speaking':
      setIcons({ stop: true });
      setStatus('Agent speaking…', 'Tap to end call');
      micWrapper.classList.add('active', 'agent-talking');
      setWaveform(true, true);
      break;

    case 'call-ended':
      setIcons({ mic: true });
      setStatus('Call ended', 'Tap to start a new conversation');
      isCallActive = false;
      break;

    case 'call-error':
      setIcons({ mic: true });
      setStatus('Connection error', 'Tap to try again');
      isCallActive = false;
      break;
  }
}

// ─── Microphone helpers ───────────────────────────────────────────────────────
async function getMicPermissionState() {
  try {
    const result = await navigator.permissions.query({ name: 'microphone' });
    return result.state; // 'granted' | 'denied' | 'prompt'
  } catch {
    return 'prompt';
  }
}

async function requestMic() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(t => t.stop());
    return true;
  } catch {
    return false;
  }
}

// ─── Vapi call ────────────────────────────────────────────────────────────────
async function startCall() {
  applyState('connecting');

  const userId = getOrCreateUserId();

  // Pre-register the userId with our backend BEFORE the Vapi call starts.
  // This guarantees the webhook handler can resolve the userId even if
  // Vapi doesn't forward assistant override values in the webhook payload.
  let sessionToken = null;
  try {
    const res = await fetch(`${BACKEND_URL}/vapi/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId }),
    });
    const data = await res.json();
    sessionToken = data.token;
  } catch (e) {
    console.warn('Could not pre-register session:', e);
  }

  try {
    vapi = new Vapi(VAPI_PUBLIC_KEY);

    vapi.on('call-start', () => {
      isCallActive = true;
      applyState('listening');
    });

    vapi.on('call-end', () => {
      isCallActive = false;
      vapi = null;
      applyState('call-ended');
    });

    vapi.on('speech-start', () => {
      if (isCallActive) applyState('user-speaking');
    });

    vapi.on('speech-end', () => {
      if (isCallActive) applyState('listening');
    });

    vapi.on('message', (msg) => {
      // Track agent speaking state via speech-update events
      if (msg.type === 'speech-update' && isCallActive && msg.role === 'assistant') {
        applyState(msg.status === 'started' ? 'agent-speaking' : 'listening');
      }
    });

    vapi.on('error', (err) => {
      console.error('Vapi error:', err);
      isCallActive = false;
      vapi = null;
      applyState('call-error');
    });

    await vapi.start(ASSISTANT_ID, {
      // variableValues is the correct field for assistantOverrides in the Web SDK.
      // sessionToken ties back to the pre-registered userId on our backend.
      variableValues: {
        userId,
        ...(sessionToken ? { sessionToken } : {}),
      },
    });
  } catch (err) {
    console.error('Failed to start call:', err);
    isCallActive = false;
    vapi = null;
    applyState('call-error');
  }
}

function stopCall() {
  if (vapi) {
    vapi.stop();
  }
}

// ─── Main handler ─────────────────────────────────────────────────────────────
async function handleMicClick() {
  if (isCallActive) {
    stopCall();
    return;
  }

  applyState('requesting-mic');

  const permState = await getMicPermissionState();

  if (permState === 'denied') {
    applyState('mic-denied');
    return;
  }

  if (permState === 'prompt') {
    const granted = await requestMic();
    if (!granted) {
      applyState('mic-denied');
      return;
    }
  }

  await startCall();
}

// ─── Events ───────────────────────────────────────────────────────────────────
micBtn.addEventListener('click', handleMicClick);
retryBtn.addEventListener('click', handleMicClick);

// ─── Auth guard ───────────────────────────────────────────────────────────────
// Verify the user has a connected Google Calendar before letting them call.
// If not, send them back to index.html to connect.
async function guardAuth() {
  const userId = getOrCreateUserId();
  try {
    const res  = await fetch(`${BACKEND_URL}/auth/status?userId=${userId}`);
    const data = await res.json();
    if (!data.connected) {
      window.location.replace('index.html');
    }
  } catch {
    // Backend unreachable — let the user attempt the call; the agent will
    // surface an error if it can't reach the calendar API.
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
applyState('idle');

// Clean up query string if redirected here after OAuth
if (new URLSearchParams(window.location.search).get('connected') === '1') {
  history.replaceState(null, '', window.location.pathname);
}

guardAuth();
