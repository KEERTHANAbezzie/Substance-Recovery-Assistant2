"""
ai_client.py — isolates all Claude API access.

Improvements over the original inline version (fixes: Security, Efficiency):
- Never lets a raw exception or stack trace surface to the UI (avoids leaking
  request internals).
- Explicit request timeout so a hung network call can't freeze the app.
- One retry on transient failures instead of failing immediately.
- API key is only ever read from st.secrets/environment — never hardcoded,
  never logged, never echoed back in any response.
"""

import time

from anthropic import Anthropic, APIError, APITimeoutError

MODEL = "claude-sonnet-5"
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 1

FALLBACK_MESSAGE = (
    "I'm having trouble reaching my thinking right now. "
    "Please try again in a moment — and if this is urgent, "
    "please reach out to a trusted person or emergency services directly."
)


def build_client(api_key):
    if not api_key:
        raise ValueError("Missing API key")
    return Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)


def call_claude(client, system_prompt, user_prompt, max_tokens=1000):
    """Returns the model's raw text response. Never raises outward —
    on any failure, returns None so the caller can show a safe fallback."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(block.text for block in resp.content if block.type == "text")
        except (APITimeoutError, APIError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(0.6)
                continue
        except Exception as e:  # noqa: BLE001 - deliberately broad, never leak internals to UI
            last_error = e
            break
    # Log server-side only; UI gets a generic, safe message.
    print(f"[ai_client] Claude call failed after retries: {last_error}")
    return None
