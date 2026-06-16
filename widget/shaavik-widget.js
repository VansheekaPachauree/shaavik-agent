/**
 * Shaavik Legal Intake Widget
 * Drop into any page with:
 *   <script src="https://.../shaavik-widget.js"></script>
 *
 * Override the backend URL by setting window.SHAAVIK_AGENT_URL before load:
 *   <script>window.SHAAVIK_AGENT_URL = "https://your-backend.onrender.com/chat";</script>
 *   <script src="https://.../shaavik-widget.js"></script>
 *
 * Defaults to http://localhost:8000/chat for development.
 */
(function () {
  if (window.__shaavikWidgetLoaded) return;
  window.__shaavikWidgetLoaded = true;

  const API_URL = window.SHAAVIK_AGENT_URL || "https://shaavik-agent.onrender.com/chat";

  const css = `
    #shaavik-bubble {
      position: fixed; bottom: 24px; right: 24px;
      width: 60px; height: 60px; border-radius: 50%;
      background: #1a3a5c; color: white; border: none;
      cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      font-size: 28px; display: flex; align-items: center; justify-content: center;
      z-index: 2147483646; transition: transform 0.2s;
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    }
    #shaavik-bubble:hover { transform: scale(1.05); }

    #shaavik-panel {
      position: fixed; bottom: 100px; right: 24px;
      width: 380px; height: 540px; max-height: calc(100vh - 140px);
      background: white; border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.2);
      display: none; flex-direction: column; overflow: hidden;
      z-index: 2147483647;
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
      color: #2a2a2a;
    }
    #shaavik-panel.shaavik-open { display: flex; }

    #shaavik-panel .shaavik-header {
      background: #1a3a5c; color: white; padding: 14px 18px; font-weight: 500;
    }
    #shaavik-panel .shaavik-header small {
      display: block; font-weight: 300; opacity: 0.85;
      font-size: 11px; margin-top: 2px;
    }

    #shaavik-panel .shaavik-messages {
      flex: 1; overflow-y: auto; padding: 16px;
      display: flex; flex-direction: column; gap: 10px; background: #fafaf7;
    }
    #shaavik-panel .shaavik-msg {
      max-width: 80%; padding: 10px 14px; border-radius: 14px;
      font-size: 14px; line-height: 1.4; white-space: pre-wrap;
    }
    #shaavik-panel .shaavik-msg.user {
      background: #1a3a5c; color: white; align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    #shaavik-panel .shaavik-msg.agent {
      background: white; color: #2a2a2a; align-self: flex-start;
      border: 1px solid #e0e0d8; border-bottom-left-radius: 4px;
    }
    #shaavik-panel .shaavik-msg.system {
      align-self: center; font-size: 12px; color: #888; font-style: italic;
    }

    #shaavik-panel .shaavik-input-row {
      display: flex; padding: 12px; gap: 8px;
      border-top: 1px solid #e0e0d8; background: white;
    }
    #shaavik-panel .shaavik-input-row input {
      flex: 1; border: 1px solid #d0d0c8; border-radius: 20px;
      padding: 10px 14px; font-size: 14px; outline: none;
      font-family: inherit; color: #2a2a2a;
    }
    #shaavik-panel .shaavik-input-row input:focus { border-color: #1a3a5c; }
    #shaavik-panel .shaavik-input-row button {
      border: none; background: #1a3a5c; color: white;
      padding: 0 16px; border-radius: 20px; cursor: pointer; font-size: 14px;
    }
    #shaavik-panel .shaavik-input-row button:disabled {
      opacity: 0.5; cursor: not-allowed;
    }
    #shaavik-panel .shaavik-disclaimer {
      font-size: 11px; color: #888; padding: 6px 12px 10px;
      text-align: center; background: white;
    }

    @media (max-width: 480px) {
      #shaavik-panel {
        width: calc(100vw - 24px); height: calc(100vh - 120px);
        right: 12px; bottom: 90px;
      }
    }
  `;
  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  const html = `
    <button id="shaavik-bubble" aria-label="Open Shaavik Legal chat">💬</button>
    <div id="shaavik-panel" role="dialog" aria-label="Shaavik Legal Assistant">
      <div class="shaavik-header">
        Shaavik Legal Assistant
        <small>AI intake assistant · not a solicitor · won't give legal advice</small>
      </div>
      <div class="shaavik-messages" id="shaavik-messages"></div>
      <div class="shaavik-input-row">
        <input
          type="text"
          id="shaavik-input"
          placeholder="Tell us about your matter..."
          autocomplete="off"
        />
        <button id="shaavik-send">Send</button>
      </div>
      <div class="shaavik-disclaimer">
        AI assistant. For information only. Not legal advice.
      </div>
    </div>
  `;
  const container = document.createElement("div");
  container.innerHTML = html;
  document.body.appendChild(container);

  const bubble = document.getElementById("shaavik-bubble");
  const panel = document.getElementById("shaavik-panel");
  const messages = document.getElementById("shaavik-messages");
  const input = document.getElementById("shaavik-input");
  const sendBtn = document.getElementById("shaavik-send");

  let sessionId = null;
  let busy = false;

  function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = `shaavik-msg ${role}`;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  async function send() {
    const text = input.value.trim();
    if (!text || busy) return;
    addMessage("user", text);
    input.value = "";
    busy = true;
    sendBtn.disabled = true;

    const typing = document.createElement("div");
    typing.className = "shaavik-msg agent";
    typing.textContent = "...";
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      typing.remove();
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addMessage("system", err.detail || `Error ${res.status}. Please try again.`);
        return;
      }
      const data = await res.json();
      sessionId = data.session_id;
      addMessage("agent", data.reply);
    } catch (e) {
      typing.remove();
      addMessage("system", "Couldn't reach the assistant. Check your connection.");
      console.error(e);
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  bubble.addEventListener("click", () => {
    panel.classList.toggle("shaavik-open");
    if (panel.classList.contains("shaavik-open") && messages.children.length === 0) {
      addMessage(
        "agent",
        "Hi, I'm Shaavik Legal's intake assistant. Tell me briefly what you need help with and I'll point you to the right service or book you in."
      );
      addMessage(
        "system",
        "First response after a quiet period can take ~50 seconds while the demo server wakes up. Subsequent replies are fast."
      );
    }
    input.focus();
  });
  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
})();