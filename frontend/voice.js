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
const textInput   = document.getElementById('text-input');
const sendBtn     = document.getElementById('send-btn');
const textSection = document.getElementById('text-input-section');

// ─── Runtime state ──────────────────────────────────────────────────────────
let vapi                = null;
let isCallActive        = false;
let pendingText         = null;   // text queued before the call is live
let agentSpeakingTimer  = null;   // debounce timer for agent-speaking → listening

// ─── UI helpers ──────────────────────────────────────────────────────────────
function show(el)  { el.classList.remove('v-hidden'); }
function hide(el)  { el.classList.add('v-hidden'); }

function setTextSection(visible, enabled = true) {
  visible ? show(textSection) : hide(textSection);
  textInput.disabled = !enabled;
  sendBtn.disabled   = !enabled;
}

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
      setTextSection(false);
      break;

    case 'requesting-mic':
      setIcons({ spin: true });
      setStatus('Checking microphone…', 'Please allow access when prompted');
      micBtn.disabled = true;
      setTextSection(false);
      break;

    case 'mic-denied':
      setIcons({ mic: true });
      setStatus('Microphone blocked', '');
      show(permCard);
      // Mic is blocked — surface text input as a fallback so the user
      // can still interact with the agent by typing.
      setTextSection(true, true);
      break;

    case 'connecting':
      setIcons({ spin: true });
      setStatus('Connecting…', 'Starting your voice assistant');
      micBtn.disabled = true;
      setTextSection(false);
      break;

    case 'listening':
      setIcons({ stop: true });
      setStatus('Listening', 'Speak or type — tap ■ to end');
      micWrapper.classList.add('active');
      setTextSection(true, true);
      break;

    case 'user-speaking':
      setIcons({ stop: true });
      setStatus('Listening…', "Go ahead, I'm listening");
      micWrapper.classList.add('active', 'user-speaking');
      setWaveform(true, false);
      // Mic is capturing — keep text input available for simultaneous use.
      setTextSection(true, true);
      break;

    case 'agent-speaking':
      setIcons({ stop: true });
      setStatus('Agent speaking…', 'Tap to end call');
      micWrapper.classList.add('active', 'agent-talking');
      setWaveform(true, true);
      // Lock input while agent is mid-response.
      setTextSection(true, false);
      break;

    case 'call-ended':
      setIcons({ mic: true });
      setStatus('Call ended', 'Tap to start a new conversation');
      isCallActive = false;
      setTextSection(false);
      break;

    case 'call-error':
      setIcons({ mic: true });
      setStatus('Connection error', 'Tap to try again');
      isCallActive = false;
      setTextSection(false);
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
      // If the call was triggered by a text submission, send the queued message now.
      if (pendingText) {
        const textToSend = pendingText;
        pendingText = null;
        // Small delay so the assistant has time to fully initialise.
        setTimeout(() => sendTextToVapi(textToSend), 600);
      }
    });

    vapi.on('call-end', () => {
      isCallActive = false;
      vapi = null;
      if (agentSpeakingTimer) {
        clearTimeout(agentSpeakingTimer);
        agentSpeakingTimer = null;
      }
      applyState('call-ended');
    });

    vapi.on('speech-start', () => {
      if (isCallActive) applyState('user-speaking');
    });

    vapi.on('speech-end', () => {
      if (isCallActive) applyState('listening');
    });

    vapi.on('message', (msg) => {
      if (msg.type === 'speech-update' && isCallActive && msg.role === 'assistant') {
        if (msg.status === 'started') {
          // Cancel any pending "return to listening" so mid-chunk pauses
          // don't briefly flash the wrong state.
          if (agentSpeakingTimer) {
            clearTimeout(agentSpeakingTimer);
            agentSpeakingTimer = null;
          }
          applyState('agent-speaking');
        } else {
          // Debounce: only switch back after 800 ms of silence.
          // If a new chunk starts before then, the timer is cancelled above.
          agentSpeakingTimer = setTimeout(() => {
            agentSpeakingTimer = null;
            if (isCallActive) applyState('listening');
          }, 800);
        }
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

// ─── Text input ───────────────────────────────────────────────────────────────
function sendTextToVapi(text) {
  if (!vapi || !isCallActive) return;
  vapi.send({
    type: 'add-message',
    message: { role: 'user', content: text },
  });
}

async function handleTextSend() {
  const text = textInput.value.trim();
  if (!text) return;

  textInput.value = '';

  if (isCallActive) {
    // Call already live — inject immediately.
    sendTextToVapi(text);
    return;
  }

  // No active call: queue the text and start one.
  // We skip the mic-permission gate since the user is typing, not speaking.
  // Vapi still opens an audio output channel (for TTS) which doesn't need mic.
  pendingText = text;
  await startCall();
}

// ─── Events ───────────────────────────────────────────────────────────────────
micBtn.addEventListener('click', handleMicClick);
retryBtn.addEventListener('click', handleMicClick);

textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleTextSend();
  }
});
sendBtn.addEventListener('click', handleTextSend);

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
