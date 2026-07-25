"""
app_logic.py — pure, framework-independent logic for the AI Recovery Companion.

Kept separate from streamlit_app.py so it can be unit tested without
spinning up a Streamlit session (fixes: Testing score = 0).
Every function here is deterministic and side-effect-free except the
file I/O helpers, which are isolated and easy to mock in tests.
"""

import json
import os
import tempfile
from datetime import datetime

DATA_FILE_DEFAULT = "recovery_data.json"
MAX_FIELD_LEN = 500  # caps how much text a single onboarding answer can hold
MAX_JSON_BYTES = 2_000_000  # 2MB guardrail so a corrupted/huge file can't hang the app


def empty_state():
    return {"profile": None, "memory": {"what_worked": {}}, "mood_history": [], "journal": []}


def sanitize_input(text, max_len=MAX_FIELD_LEN):
    """Strip, collapse whitespace, and hard-cap length before anything
    from the user is stored or sent to the model. Prevents prompt-stuffing
    and keeps stored data bounded (fixes: Security)."""
    if text is None:
        return ""
    text = str(text).strip()
    text = " ".join(text.split())
    return text[:max_len]


def sanitize_profile(draft):
    return {k: sanitize_input(v) for k, v in draft.items()}


def load_data(path=DATA_FILE_DEFAULT):
    """Load persisted state. Falls back to a clean empty state on any
    corruption or oversized file instead of crashing the app."""
    if not os.path.exists(path):
        return empty_state()
    try:
        if os.path.getsize(path) > MAX_JSON_BYTES:
            return empty_state()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # defensive defaults in case of a partial/older schema
        data.setdefault("profile", None)
        data.setdefault("memory", {"what_worked": {}})
        data.setdefault("mood_history", [])
        data.setdefault("journal", [])
        return data
    except (json.JSONDecodeError, OSError):
        return empty_state()


def save_data(data, path=DATA_FILE_DEFAULT):
    """Atomic write: write to a temp file then rename, so a crash or
    concurrent write mid-save can never leave a corrupted data file
    (fixes: Security / data integrity)."""
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def parse_ai_json(text):
    """Best-effort parse of a model response that is supposed to be JSON.
    Never raises — always returns a dict, so a malformed model response
    degrades gracefully instead of crashing the UI (fixes: Security/Efficiency:
    fewer unhandled exceptions => fewer full page reruns on failure)."""
    if not text:
        return {"raw": ""}
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
        return {"raw": text}
    except json.JSONDecodeError:
        return {"raw": text}


def recent_moods_summary(mood_history, limit=5):
    recent = mood_history[-limit:]
    return ", ".join(f"{m['emotion']} ({m['at'][:10]})" for m in recent) or "none yet"


def top_worked_strategies(what_worked, limit=3):
    ranked = sorted(what_worked.items(), key=lambda kv: -kv[1])[:limit]
    return ", ".join(f"{k} (helped {v}x)" for k, v in ranked) or "nothing logged yet"


def build_memory_context(profile, memory, mood_history):
    """Pure function: takes plain data, returns the context string sent
    to the model. No Streamlit/session_state dependency, so it's directly
    unit-testable."""
    profile = profile or {}
    memory = memory or {"what_worked": {}}
    mood_history = mood_history or []

    return (
        f"Name: {profile.get('name') or 'friend'}\n"
        f"Recovery goal: {profile.get('goal') or 'not specified'}\n"
        f"Known triggers: {profile.get('triggers') or 'not specified'}\n"
        f"Medical conditions to respect (never recommend anything unsafe for these): "
        f"{profile.get('medical') or 'none listed'}\n"
        f"Favourite things (use naturally, don't overdo it): {profile.get('favorites') or 'not specified'}\n"
        f"Emergency contact: {profile.get('emergency_contact') or 'not specified'}\n"
        f"Recent check-ins: {recent_moods_summary(mood_history)}\n"
        f"What has worked before: {top_worked_strategies(memory.get('what_worked', {}))}"
    )


def new_mood_entry(emotion_key, now=None):
    return {"emotion": emotion_key, "at": (now or datetime.now()).isoformat()}


def new_journal_entry(emotion_key, summary, now=None):
    return {"emotion": emotion_key, "at": (now or datetime.now()).isoformat(), "summary": sanitize_input(summary, max_len=2000)}


def record_strategy_used(memory, strategy_key):
    """Returns a new memory dict with the strategy count incremented.
    Pure/immutable so it's easy to test and easy to reason about."""
    updated = dict(memory)
    what_worked = dict(updated.get("what_worked", {}))
    what_worked[strategy_key] = what_worked.get(strategy_key, 0) + 1
    updated["what_worked"] = what_worked
    return updated
