import Vapi from 'https://esm.sh/@vapi-ai/web';

// ─── Config ────────────────────────────────────────────────────────────────
const VAPI_PUBLIC_KEY = '214915eb-a2c4-4a12-a5ed-25cdf9b7c61a';
const ASSISTANT_ID    = '66c72102-02ea-4c75-98e9-8974555e282b';

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

    await vapi.start(ASSISTANT_ID);
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

// ─── Init ─────────────────────────────────────────────────────────────────────
applyState('idle');

// Clean up query string if redirected here after OAuth
if (new URLSearchParams(window.location.search).get('connected') === '1') {
  history.replaceState(null, '', window.location.pathname);
}
