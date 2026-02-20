const BACKEND_URL = 'http://localhost:8000';

const stateLoading      = document.getElementById('state-loading');
const stateDisconnected = document.getElementById('state-disconnected');
const stateConnected    = document.getElementById('state-connected');
const connectBtn        = document.getElementById('connect-google-calendar');
const reconnectBtn      = document.getElementById('reconnect-btn');

function showState(name) {
  stateLoading.classList.add('v-hidden');
  stateDisconnected.classList.add('v-hidden');
  stateConnected.classList.add('v-hidden');
  document.getElementById(`state-${name}`).classList.remove('v-hidden');
}

function redirectToGoogle() {
  window.location.href = `${BACKEND_URL}/auth/google`;
}

async function checkAuthStatus() {
  showState('loading');
  try {
    const res  = await fetch(`${BACKEND_URL}/auth/status`);
    const data = await res.json();
    showState(data.connected ? 'connected' : 'disconnected');
  } catch {
    // Backend unreachable – show connect button so user can try
    showState('disconnected');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  connectBtn.addEventListener('click', redirectToGoogle);
  reconnectBtn.addEventListener('click', redirectToGoogle);
  checkAuthStatus();
});
