# Shaavik Legal Intake Agent

An agentic AI intake assistant for Shaavik Legal, a UK legal services firm. It helps visitors identify which service fits their situation, gathers consultation requirements, books appointments, and escalates urgent matters to a human — without ever giving legal advice.

## Live demo

**Try it:** [shaavik-agent.onrender.com](https://shaavik-agent.onrender.com/docs) (API) — or open `widget/test.html` after cloning to see the chat UI.

> ⚠️ **Cold start:** the backend is on Render's free tier and spins down after 15 minutes of inactivity. First request after idle takes ~50 seconds; subsequent ones are fast. This is a deployment tier choice, not a code limitation.

A working prototype, runnable locally. See "Scope and what's next" below for what's done vs. what isn't.

## Stack

- **Backend:** Python · FastAPI · Pydantic
- **Agent:** Google Gemini 2.5 Flash with tool calling (manual loop, `automatic_function_calling` disabled for explicit control)
- **Frontend:** Vanilla HTML/CSS/JS embeddable widget — drop into any host page with one `<script>` tag

## Architecture

    Browser  ────►  shaavik-widget.js  (self-injecting, namespaced)
                           │
                           │  POST /chat (JSON)
                           ▼
                     FastAPI app.py
                           │  session-keyed lookup
                           ▼
                     Agent loop (step5.py)
                           │
            ┌──────────────┼──────────────┬────────────────┐
            ▼              ▼              ▼                ▼
       get_service    check_         book_           escalate_
       _info          availability   consultation    to_human
                           │
                           ▼
                     Gemini API

The agent loop sends the user's message plus tool definitions to Gemini, executes any requested function calls locally, feeds results back, and iterates until Gemini produces a plain-text reply. Capped at 8 iterations to prevent runaway loops.

## Tools

| Tool | Purpose |
|---|---|
| `get_service_info` | Look up one of 8 Shaavik services (business + individual matters) |
| `check_availability` | Return next available consultation slots |
| `book_consultation` | Create a booking, with `urgency` flag for priority handling |
| `escalate_to_human` | Flag urgent matters for direct callback within 2 hours |

## Design decisions

**Layered guardrails.** First version relied on the system prompt alone to enforce rules like "never escalate without contact info." Testing showed the LLM violated this — it once hallucinated a plausible-looking phone number to satisfy the requirement. Fixed by adding runtime validation in the tool implementation, which returns a structured error that *instructs the model how to recover*. Three layers now defend against bad tool calls: prompt rules, schema descriptions, runtime validation. The principle: never trust the prompt alone for anything safety-relevant.

**Urgency: offer, don't decide.** First version auto-escalated on urgency detection. Testing showed this was paternalistic — some visitors prefer a scheduled meeting where they arrive prepared with documents, even for urgent matters. Rewrote the rule: the agent presents both paths (callback within 2h vs priority consultation within 24-48h), lets the visitor choose, and tags either action with `urgency='urgent'` for downstream priority handling.

**Hard scope on legal advice.** System prompt explicitly forbids giving legal advice, predicting outcomes, or speculating on costs. Out-of-scope matters get escalated rather than refused. The widget carries a visible disclaimer.

**Graceful degradation.** FastAPI layer catches Gemini-specific exceptions (`ServerError` → 503, `ClientError` → 429) and returns human-readable messages rather than leaking stack traces — so a Gemini outage shows "the assistant is busy, please try again" instead of an Internal Server Error.

## Run locally

Clone and set up:

```bash
git clone https://github.com/<your-username>/shaavik-agent.git
cd shaavik-agent

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux, use `source .venv/bin/activate` instead of `.venv\Scripts\activate`.

Add your Gemini key:

```bash
cp .env.example .env
```

Then edit `.env` and paste a free Gemini key from [aistudio.google.com](https://aistudio.google.com/).

Run the backend:

```bash
uvicorn app:app --reload --port 8000
```

Then open `widget/test.html` in a browser (via Live Server or any static server).

Or run the agent in a terminal chat loop without FastAPI:

```bash
python step5.py
```

## Scope and what's next

Working prototype. What isn't done:

- **Deployed on free tier.** Backend on Render free tier (cold-start delays). Production would use an always-on instance with CORS locked to Shaavik's domain.
- **Mock data.** Services come from `data/services.json`; availability is a fixed list. Production would integrate Calendly for real slots and write bookings to a database or Shaavik's CMS.
- **In-memory sessions.** Conversations live in a Python dict that resets on server restart. Production would use Redis or a database with TTL.
- **No streaming.** Replies arrive as a single chunk. Streaming would improve perceived latency.
- **No analytics.** A live deployment would log which services visitors ask about, drop-off points, and escalation rates — useful for both ops and refining the prompt.

## Files

    shaavik-agent/
    ├── app.py                  # FastAPI wrapper, exception handling, session store
    ├── step5.py                # Agent loop, tools, system prompt
    ├── requirements.txt
    ├── .env.example
    ├── data/
    │   └── services.json       # Shaavik's 8 services
    └── widget/
        ├── shaavik-widget.js   # Embeddable script
        └── test.html           # Test host page
