// Empty string = relative URLs, works on localhost:8000 AND through ngrok
const BACKEND_URL = '';

const stateLoading      = document.getElementById('state-loading');
const stateDisconnected = document.getElementById('state-disconnected');
const stateConnected    = document.getElementById('state-connected');
const connectBtn        = document.getElementById('connect-google-calendar');
const reconnectBtn      = document.getElementById('reconnect-btn');

// ─── User identity ─────────────────────────────────────────────────────────
function getOrCreateUserId() {
  let userId = localStorage.getItem('calendarUserId');
  if (!userId) {
    userId = crypto.randomUUID();
    localStorage.setItem('calendarUserId', userId);
  }
  return userId;
}

// ─── UI states ─────────────────────────────────────────────────────────────
function showState(name) {
  stateLoading.classList.add('v-hidden');
  stateDisconnected.classList.add('v-hidden');
  stateConnected.classList.add('v-hidden');
  document.getElementById(`state-${name}`).classList.remove('v-hidden');
}

function redirectToGoogle() {
  const userId = getOrCreateUserId();
  window.location.href = `${BACKEND_URL}/auth/google?userId=${userId}`;
}

async function checkAuthStatus() {
  showState('loading');
  try {
    const userId = getOrCreateUserId();
    const res    = await fetch(`${BACKEND_URL}/auth/status?userId=${userId}`);
    const data   = await res.json();

    if (data.connected) {
      // Skip the index page entirely unless the user explicitly wants to reconnect.
      const isReconnect = new URLSearchParams(window.location.search).has('reconnect');
      if (!isReconnect) {
        window.location.replace('voice.html');
        return;
      }
      showState('connected');
    } else {
      showState('disconnected');
    }
  } catch {
    showState('disconnected');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  connectBtn.addEventListener('click', redirectToGoogle);
  reconnectBtn.addEventListener('click', redirectToGoogle);
  checkAuthStatus();
});
