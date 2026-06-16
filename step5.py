import os
import re
import json
import uuid
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Load services from the JSON file
SERVICES_PATH = Path(__file__).parent / "data" / "services.json"
with open(SERVICES_PATH) as f:
    SERVICES = json.load(f)
    
VALID_SERVICE_IDS = list(SERVICES.keys())

# In-memory store for bookings (resets when script ends — fine for now)
BOOKINGS = []
ESCALATIONS = []

# ---------- THE FOUR TOOLS ----------
def get_service_info(service_id: str) -> dict:
    """Look up details about a Shaavik Legal service.

    Args:
        service_id: One of commercial_contracts, business_disputes,
            payment_recovery, commercial_leases, negotiation_support,
            copyright_trademark, immigration_support, family_personal.
    """
    if service_id not in SERVICES:
        return {"error": f"Unknown service_id '{service_id}'. Valid IDs: {VALID_SERVICE_IDS}"}
    return SERVICES[service_id]

def check_availability(service_id: str) -> dict:
    """Return the next available consultation slots for a service.

    Args:
        service_id: One of the Shaavik Legal service IDs.
    """
    # Mock slots — same for all services for now. Swap to a real calendar later.
    slots = [
        "Mon 16 Jun 2026 10:00",
        "Mon 16 Jun 2026 14:30",
        "Tue 17 Jun 2026 09:30",
        "Wed 18 Jun 2026 11:00",
        "Thu 19 Jun 2026 15:00",
    ]
    if service_id not in SERVICES:
        return {"error": f"Unknown service_id '{service_id}'"}
    return {"service_id": service_id, "available_slots": slots}

def book_consultation(name: str, email: str, service_id: str, slot: str, matter_summary: str, urgency: str = "standard") -> dict:
    """Book a consultation. Only call this once you have ALL required fields.

    Args:
        name: Visitor's full name (must be non-empty).
        email: Visitor's email address (must contain '@').
        service_id: The Shaavik Legal service.
        slot: One of the slots returned by check_availability.
        matter_summary: One- or two-sentence description of the visitor's matter.
        urgency: 'urgent' if action is needed within 7 days, otherwise 'standard'.
            Urgent bookings are flagged for priority handling.
    """
    missing = []
    if not name or not name.strip():
        missing.append("name")
    if not email or "@" not in email:
        missing.append("a valid email address")
    if not slot or not slot.strip():
        missing.append("chosen slot")
    if not matter_summary or not matter_summary.strip():
        missing.append("matter_summary")
    if service_id not in SERVICES:
        return {"error": f"Unknown service_id '{service_id}'. Valid IDs: {VALID_SERVICE_IDS}"}
    if missing:
        return {"error": f"Cannot book — missing: {', '.join(missing)}. Ask the visitor for the missing details, then call this tool again."}
    if urgency not in ("urgent", "standard"):
        urgency = "standard"

    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    booking = {
        "booking_id": booking_id,
        "name": name.strip(),
        "email": email.strip(),
        "service_id": service_id,
        "slot": slot,
        "matter_summary": matter_summary,
        "urgency": urgency,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    BOOKINGS.append(booking)
    return {
        "status": "confirmed",
        "booking_id": booking_id,
        "urgency": urgency,
        "next_step": f"We've emailed confirmation to {email}" + (" — this booking is flagged URGENT and will be prioritised." if urgency == "urgent" else ""),
    }

def escalate_to_human(matter_summary: str, urgency: str, contact_info: str) -> dict:
    """Flag a matter for direct human callback. Use for urgent matters (court
    deadline within 7 days, eviction, immigration removal) or anything outside
    Shaavik's services.

    Args:
        matter_summary: Brief description of what the visitor needs.
        urgency: One of 'urgent' (action needed within 7 days) or 'standard'.
        contact_info: Visitor's phone or email so the team can call back.
            MUST be a real value provided by the visitor — never empty.
    """
    if not contact_info or not contact_info.strip():
        return {
            "error": "Cannot escalate without contact_info. Ask the visitor explicitly: 'What's the best phone number or email to reach you on?' Then pass exactly what they reply."
        }
    # Require either a phone-like pattern (7+ digits) or an email
    has_email = "@" in contact_info and "." in contact_info.split("@")[-1]
    digits = re.sub(r"\D", "", contact_info)
    has_phone = len(digits) >= 7
    if not (has_email or has_phone):
        return {
            "error": f"contact_info '{contact_info}' doesn't look like a phone number or email. Ask the visitor for a real phone number or email address."
        }
    case_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
    ESCALATIONS.append({
        "case_id": case_id,
        "matter_summary": matter_summary,
        "urgency": urgency,
        "contact_info": contact_info,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    return {"status": "escalated", "case_id": case_id, "callback_within": "2 hours" if urgency == "urgent" else "1 working day"}

TOOLS = [get_service_info, check_availability, book_consultation, escalate_to_human]
TOOL_FUNCTIONS = {fn.__name__: fn for fn in TOOLS}

# ---------- SYSTEM PROMPT (the agent's personality + rules) ----------

SYSTEM_PROMPT = f"""You are the AI intake assistant for Shaavik Legal, a UK legal services firm.

YOUR JOB, IN ORDER:
1. Understand the visitor's situation in 1-2 sentences.
2. Match it to one of Shaavik's services (or escalate if outside scope or urgent).
3. Gather the four required pieces of info for a booking: name, email, chosen slot, and a brief matter summary.
4. Confirm the details back to the visitor before calling book_consultation.

HARD RULES (do not break these):
- You are NOT a solicitor and you do NOT give legal advice, opinions, or outcome predictions.
- Before calling escalate_to_human, you MUST have the visitor's contact_info (phone number or email). If you don't have it, ask for it FIRST, then call the tool.
- The contact_info value must be EXACTLY what the visitor typed — a real phone number or email they provided. Never invent, infer, or guess a phone number. If they haven't given one, ask: "What's the best phone number or email to reach you on?"
- Escalation vs booking are two different paths for two different needs:
  * escalate_to_human = the visitor wants a callback (faster, but unscheduled).
  * book_consultation = the visitor wants a scheduled meeting (slower, but they come prepared and it's on the calendar).
  Both can apply to urgent matters. Always present both options for urgent matters and let the visitor choose.
- Never silently refuse a visitor's explicit request. If you think an action is redundant or unwise (e.g. they want to book when already escalated), say so, explain why in one sentence, and ASK whether they still want it. The visitor decides — not you.
- Before calling book_consultation, you MUST have all four fields. If any are missing, ask for the missing one(s) — one focused question at a time. Never invent values.
- Remember context across turns. If the visitor described their matter earlier (e.g. eviction), you already know it's commercial_leases — don't ask them to pick from a list. Propose the service yourself and confirm: "Based on what you described, this sounds like our Commercial Leases service — does that sound right?"
- Never read the internal service_id values aloud to the visitor (e.g. say "Commercial Leases & Tenancy Matters", not "commercial_leases"). The IDs are for your tool calls only.

URGENCY HANDLING — this is important:
When you detect urgency (deadline within 7 days, eviction notice served, immigration removal, imminent court date):
1. Acknowledge the urgency in one sentence so the visitor knows you heard them.
2. Offer BOTH paths and let them choose:
   "Because this is time-sensitive, you have two options:
    (a) Urgent callback — a solicitor calls you back within 2 hours.
    (b) Priority consultation — we book you the earliest available slot and you come in prepared with your documents.
    Which would you prefer?"
3. Then follow whichever path they pick:
   - Callback chosen → ask for phone/email, then call escalate_to_human with urgency='urgent'.
   - Booking chosen → proceed with the normal booking flow, but call book_consultation with urgency='urgent' so it's flagged for priority handling.
4. Never make this decision for the visitor. Offer, ask, follow their choice.

OUT OF SCOPE: if the matter isn't one Shaavik covers (criminal defence, personal injury, wills/probate, etc.), say so honestly and offer to escalate so a human can suggest where to look.

STYLE: warm, professional, concise. One question at a time. Mirror the visitor's language. No legalese.

Available service IDs (for your tool calls): {", ".join(VALID_SERVICE_IDS)}"""

# ---------- THE AGENT LOOP (same shape as step 4) ----------
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=TOOLS,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)

def run_agent_turn(conversation: list, user_message: str, max_iterations: int = 8) -> tuple[str, list]:
    """Run one user turn through the agent loop. Returns (reply, updated_conversation)."""
    conversation.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    
    for iteration in range(max_iterations):
        response = client.models.generate_content(
            model = "gemini-2.5-flash",
            contents = conversation,
            config = config,
        )
        conversation.append(response.candidates[0].content)
        
        parts = response.candidates[0].content.parts
        function_calls = [p.function_call for p in parts if p.function_call]
        
        if not function_calls:
            return response.text, conversation
        
        tool_response_parts =[]
        for fc in function_calls:
            args = dict(fc.args)
            print(f" [tool] {fc.name}({args})")
            result = TOOL_FUNCTIONS[fc.name](**args)
            print(f" [tool] -> {result}")
            tool_response_parts.append(
                types.Part.from_function_response(name=fc.name, response=result)
            )
        
        conversation.append(types.Content(role="user", parts=tool_response_parts))
        
    return "[Sorry, I'm having trouble, please email us directly.]", conversation

# ---------- INTERACTIVE CHAT ----------

def main():
    print("Shaavik Legal Intake Assistant")
    print("Type 'quit' to exit. Type 'bookings' to see what's been booked.\n")
    conversation = []
    
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "bookings":
            print(f"\nBookings so far: {json.dumps(BOOKINGS, indent=2)}")
            print(f"\nEscalations: {json.dumps(ESCALATIONS, indent=2)}\n")
            continue
        
        reply, conversation = run_agent_turn(conversation, user_input)
        print(f"\nAgent: {reply}\n")
        
if __name__ == "__main__":
    main()
        
