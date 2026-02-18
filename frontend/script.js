// Backend API URL - update this to match your backend
const BACKEND_URL = "http://localhost:8000";

document.addEventListener("DOMContentLoaded", () => {
  const connectButton = document.getElementById("connect-google-calendar");
  
  if (connectButton) {
    connectButton.addEventListener("click", () => {
      // Redirect to backend OAuth endpoint
      window.location.href = `${BACKEND_URL}/auth/google`;
    });
  }
});
