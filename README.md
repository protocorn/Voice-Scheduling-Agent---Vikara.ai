# Calendar Voice Agent

A voice-powered AI scheduling assistant that books Google Calendar events through natural conversation.

**Live demo:** https://voice-scheduling-agent-vikara-ai.onrender.com/index.html

---

## How to Test

1. Open the [live URL](https://voice-scheduling-agent-vikara-ai.onrender.com/index.html)
2. Click **Connect Google Calendar** and authorize your account
   - If Google shows a **"Google hasn't verified this app"** warning, click **Advanced** and then **"Go to voice-scheduling-agent-vikara-ai.onrender.com (unsafe)"** to proceed
3. Click **Start Voice Agent**
4. Speak naturally — example prompts:
   - *"Schedule a team sync tomorrow at 3 PM"*
   - *"Book a meeting on Friday at 10 AM called Design Review"*
5. The agent will confirm the details and ask for your approval before creating anything

> The agent handles conflict detection, timezone resolution, and AM/PM clarification automatically.

---

## Demo

[Watch the demo video](https://drive.google.com/file/d/1JAUZGImFq3CBqcnwNFgKzG-kUiKVjHCF/view?usp=sharing)

---

## Calendar Integration

- **OAuth 2.0** — users connect their own Google account; refresh tokens are stored in MongoDB
- **Check availability** — queries Google Calendar's freebusy API before confirming any booking
- **Create event** — uses the Google Calendar Events API with the user's local timezone
- **Server-injected time** — every tool response includes a verified `[SERVER TIME]` so the AI never relies on its training-data clock

---

## Run Locally

**Prerequisites:** Python 3.11+, a Google OAuth app (Web application type), MongoDB URI

```bash
git clone https://github.com/your-username/Calendar_Voice_Agent.git
cd Calendar_Voice_Agent
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
MONGODB_URI=...
VAPI_API_KEY=...
```

Start the server:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.
