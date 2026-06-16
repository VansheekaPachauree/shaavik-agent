"""FastAPI wrapper around the Shaavik Legal intake agent."""
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# We import run_agent_turn from step5
from step5 import run_agent_turn

app = FastAPI(title="Shaavik Legal Intake Agent")

# Allow the chat widget
# to call this API. In production we'd tighten this to Shaavik's domain only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage: {session_id: conversation_list}
# The conversation contains Gemini-specific Content objects that don't
# JSON-serialise cleanly, so we keep them server-side and just hand the
# client a short session_id to identify their conversation on each turn.
# Resets when the server restarts
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
    # If no session_id sent, mint a new one (first message of a conversation)
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    conversation = SESSIONS.get(session_id, [])
    
    reply, updated_conversation = run_agent_turn(conversation, req.message)
    
    # Save the updated conversation for the next turn
    SESSIONS[session_id] = updated_conversation
    
    return ChatResponse(session_id=session_id, reply=reply)