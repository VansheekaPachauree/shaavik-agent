"""FastAPI wrapper around the Shaavik Legal intake agent."""
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai import errors as genai_errors

# We import run_agent_turn from step5
from step5 import run_agent_turn

app = FastAPI(title="Shaavik Legal Intake Agent")

# Allow the chat widget to call this API.
# In production we'd tighten this to Shaavik's domain only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage: {session_id: conversation_list}
# Resets when the server restarts.
SESSIONS: dict[str, list] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.get("/")
def root():
    return {"status": "ok", "service": "Shaavik Legal Intake Agent"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    conversation = SESSIONS.get(session_id, [])

    try:
        reply, updated_conversation = run_agent_turn(conversation, req.message)
    except genai_errors.ClientError as e:
        # 429 quota / 400 invalid request etc.
        msg = (
            "We've hit our daily limit on the assistant. "
            "This is a free-tier demo — please try again tomorrow when the quota resets, "
            "or clone the repo and run it locally with your own free Gemini key."
        )
        raise HTTPException(status_code=429, detail=msg)
    except genai_errors.ServerError:
        # Gemini overloaded — transient.
        raise HTTPException(
            status_code=503,
            detail="The assistant is busy right now. Please try again in a moment.",
        )
    except Exception as e:
        print(f"[chat] unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Something went wrong. Please try again or call us directly.",
        )

    SESSIONS[session_id] = updated_conversation
    return ChatResponse(session_id=session_id, reply=reply)


# Belt-and-braces: ensure CORS headers are also set on error responses
# (FastAPI's CORSMiddleware sometimes skips them when an HTTPException is raised
# before the middleware completes). This guarantees the browser sees the error
# message instead of a generic "blocked by CORS" wall.
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Access-Control-Allow-Origin": "*"},
    )