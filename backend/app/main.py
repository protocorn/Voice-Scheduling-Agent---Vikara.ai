from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.auth.router import router as auth_router

app = FastAPI(title="Voice Scheduling Agent API")

# CORS middleware to allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth routes
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(voice_router, prefix="/vapi", tags=["vapi"])


@app.get("/")
async def root():
    return {"message": "Voice Scheduling Agent API"}


@app.get("/health")
async def health():
    return {"status": "ok"}
