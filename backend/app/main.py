from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.auth.router import router as auth_router
from app.vapi.router import router as vapi_router

app = FastAPI(title="Voice Scheduling Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes (must be registered BEFORE the static files mount)
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(vapi_router, prefix="/vapi", tags=["vapi"])


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the frontend — this is a catch-all fallback for everything not matched
# above, so index.html loads at "/" and voice.html at "/voice.html".
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
