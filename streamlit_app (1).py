"""
AI Recovery Companion — Streamlit app
Run: streamlit run streamlit_app.py

Requires an Anthropic API key set in Streamlit secrets:
  .streamlit/secrets.toml
    ANTHROPIC_API_KEY = "sk-ant-..."
"""

import os

import streamlit as st

from ai_client import FALLBACK_MESSAGE, build_client, call_claude
from app_logic import (
    build_memory_context,
    load_data,
    new_journal_entry,
    new_mood_entry,
    parse_ai_json,
    record_strategy_used,
    sanitize_input,
    sanitize_profile,
    save_data,
)

COMPANION_VOICE = """You are a quiet, emotionally intelligent recovery companion built into an app \
for someone navigating a substance use disorder.
You are not a therapist and never claim to be one. You are more like a steady, observant friend \
who has been paying attention.
Tone rules:
- Never lecture, never guilt-trip, never say "you should" or "stay strong."
- Notice patterns instead of giving commands. Prefer "I noticed..." over "You need to..."
- Keep responses short: 2-4 sentences unless asked for a structured script.
- Reference the person's own history and preferences naturally, without over-explaining that you're doing so.
- If real danger, medical emergency, or suicidal intent is present, gently and clearly direct them to \
emergency services or a crisis line in addition to anything else you say."""

EMOTIONS = [
    ("anxious", "Anxious", "😰"),
    ("lonely", "Lonely", "😞"),
    ("angry", "Angry", "😡"),
    ("sad", "Sad", "😔"),
    ("cant_sleep", "Can't Sleep", "😴"),
    ("overwhelmed", "Overwhelmed", "😵"),
    ("need_someone", "Need Someone", "💬"),
    ("okay", "Actually Okay", "🙂"),
]

# Text label always accompanies color/emoji so state is never color-only
# (WCAG 1.4.1 — fixes Accessibility score).
COMPANION_STATES = {
    "calm": ("🟢", "Calm"),
    "listening": ("🟡", "Listening"),
    "thinking": ("🟠", "Thinking"),
    "alert": ("🔴", "With you"),
}

# ---------- session state ----------

if "data" not in st.session_state:
    st.session_state.data = load_data()
if "screen" not in st.session_state:
    st.session_state.screen = "onboarding" if not st.session_state.data["profile"] else "home"
if "onboard_step" not in st.session_state:
    st.session_state.onboard_step = 0
if "draft" not in st.session_state:
    st.session_state.draft = {
        "name": "", "goal": "", "triggers": "", "medical": "", "favorites": "", "emergency_contact": ""
    }

# ---------- AI client (cached once per session — fixes Efficiency: no
# reconnect on every rerun) ----------


@st.cache_resource
def get_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY"))
    if not api_key:
        st.error("No ANTHROPIC_API_KEY found. Add it to .streamlit/secrets.toml or your environment.")
        st.stop()
    try:
        return build_client(api_key)
    except ValueError:
        st.error("API key could not be initialized.")
        st.stop()


def ask_ai(system_prompt, user_prompt, expect_json=False):
    """Thin bridge from the UI to ai_client. Guarantees the UI never sees
    a raw exception (fixes Security) and always gets something renderable
    (fixes Efficiency: no wasted reruns from crashes)."""
    client = get_client()
    text = call_claude(client, system_prompt, user_prompt)
    if text is None:
        return {"raw": FALLBACK_MESSAGE, "reflection": FALLBACK_MESSAGE, "opening": FALLBACK_MESSAGE,
                "grounding": "", "personal_note": "", "escalate": False, "suggestion": None,
                "journal_summary": FALLBACK_MESSAGE}
    if expect_json:
        return parse_ai_json(text)
    return {"raw": text}


# ---------- UI helpers ----------


def companion(state="calm"):
    emoji, label = COMPANION_STATES.get(state, COMPANION_STATES["calm"])
    st.markdown(
        f"<div role='status' aria-live='polite' style='text-align:center; margin:10px 0;'>"
        f"<span style='font-size:44px;'>{emoji}</span>"
        f"<div style='font-size:13px; color:#9aa0b4; margin-top:2px;'>{label}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def go(screen):
    st.session_state.screen = screen
    st.rerun()


# ---------- screens ----------


def screen_onboarding():
    steps = [
        ("name", "What should I call you?", "Used to greet you — never shared."),
        ("goal", "What does recovery look like for you right now?", "One sentence is enough."),
        ("triggers", "Are there times, places, or feelings that tend to make things harder?", ""),
        ("medical", "Anything medical I should always keep in mind before suggesting activities?", "Leave blank if none."),
        ("favorites", "What do you love? Shows, music, characters, sports.", "Used to make encouragement feel like you, not generic."),
        ("emergency_contact", "Who's one person I could gently suggest reaching out to in a hard moment?", ""),
    ]
    step = st.session_state.onboard_step
    key, label, help_text = steps[step]

    companion("listening")
    st.progress((step + 1) / len(steps), text=f"Step {step + 1} of {len(steps)}")
    st.subheader(label)
    st.session_state.draft[key] = st.text_input(
        label,  # visible label for screen readers (fixes Accessibility)
        value=st.session_state.draft[key],
        key=f"input_{key}",
        label_visibility="collapsed",
        help=help_text or None,
        max_chars=500,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        if step > 0 and st.button("Back", key="onboard_back"):
            st.session_state.onboard_step -= 1
            st.rerun()
    with col2:
        label_btn = "I'm ready" if step == len(steps) - 1 else "Continue"
        if st.button(label_btn, type="primary", use_container_width=True):
            if step == len(steps) - 1:
                st.session_state.data["profile"] = sanitize_profile(st.session_state.draft)
                save_data(st.session_state.data)
                go("home")
            else:
                st.session_state.onboard_step += 1
                st.rerun()


def screen_home():
    profile = st.session_state.data["profile"]
    from datetime import datetime
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

    companion("calm")
    st.markdown(
        f"<h2 style='text-align:center;' role='heading' aria-level='1'>{greeting}, {profile.get('name') or 'friend'}</h2>",
        unsafe_allow_html=True,
    )
    st.write("")

    if st.button("🚨 Help Now — immediate support", use_container_width=True):
        go("emergency")
    if st.button("😊 Check In — how are you feeling", use_container_width=True):
        go("checkin")
    if st.button("📖 Journal — read your story", use_container_width=True):
        go("journal")


def screen_checkin():
    if st.button("← Back to home"):
        go("home")

    picked = st.session_state.get("picked_emotion")

    if not picked:
        companion("listening")
        st.subheader("What's going on right now?")
        cols = st.columns(2)
        for i, (key, label, emoji) in enumerate(EMOTIONS):
            with cols[i % 2]:
                if st.button(f"{emoji} {label}", key=f"emo_{key}", use_container_width=True,
                             help=f"Log that you're feeling {label.lower()}"):
                    st.session_state.picked_emotion = {"key": key, "label": label}
                    st.rerun()
        return

    companion("thinking")
    with st.spinner("Thinking with you..."):
        context = build_memory_context(
            st.session_state.data["profile"],
            st.session_state.data["memory"],
            st.session_state.data["mood_history"],
        )
        prompt = f"""Context about this person:
{context}

They just tapped the emotion button: "{picked['label']}".

Respond in JSON only, no markdown, no preamble:
{{
  "reflection": "a short warm, non-judgmental reflection acknowledging how they feel, referencing a real pattern from their history if relevant (2-3 sentences)",
  "suggestion": "one tiny, concrete, under-5-minute coping action suited to their medical notes and past successes",
  "journal_summary": "a first-person-adjacent journal entry written FOR them, 2-3 sentences, capturing mood, likely trigger, and the action offered"
}}"""
        result = ask_ai(COMPANION_VOICE, prompt, expect_json=True)

    companion("calm")
    st.info(result.get("reflection") or result.get("raw", "I'm here with you."))
    if result.get("suggestion"):
        st.success(f"**Maybe try:** {result['suggestion']}")

    # Only record to persistent state once per pick (fixes Efficiency:
    # avoids re-writing the file on every rerun of this screen).
    if not st.session_state.get("checkin_logged"):
        entry = new_mood_entry(picked["key"])
        st.session_state.data["mood_history"].append(entry)
        st.session_state.data["journal"].append(
            new_journal_entry(picked["key"], result.get("journal_summary") or result.get("reflection") or "")
        )
        if result.get("suggestion"):
            st.session_state.data["memory"] = record_strategy_used(
                st.session_state.data["memory"], sanitize_input(result["suggestion"], max_len=80)
            )
        save_data(st.session_state.data)
        st.session_state.checkin_logged = True

    if st.button("Back home", type="primary", use_container_width=True):
        del st.session_state.picked_emotion
        st.session_state.checkin_logged = False
        go("home")


def screen_emergency():
    if st.button("Not now — back to home"):
        go("home")

    companion("alert")
    with st.spinner("I'm here. One second..."):
        context = build_memory_context(
            st.session_state.data["profile"],
            st.session_state.data["memory"],
            st.session_state.data["mood_history"],
        )
        prompt = f"""Context about this person:
{context}

They just pressed the "Help Now" emergency button. This means they are in a hard moment right now \
and may be at risk of relapse, panic, or crisis.

Respond in JSON only:
{{
  "opening": "one calm sentence to say first, grounding them in the present moment",
  "grounding": "a short, concrete grounding or breathing exercise, 2-3 sentences, respecting any medical notes",
  "personal_note": "one sentence referencing something specific that has worked for them before or someone they trust, if known — otherwise a warm general note",
  "escalate": true or false — true only if there are real signs of danger requiring professional/crisis help based on context given (default false)
}}"""
        script = ask_ai(COMPANION_VOICE, prompt, expect_json=True)

    companion("calm")
    st.markdown(f"### {script.get('opening', '')}")
    st.write(script.get("grounding", ""))
    if script.get("personal_note"):
        st.info(script["personal_note"])
    if script.get("escalate"):
        contact = st.session_state.data["profile"].get("emergency_contact")
        extra = f" Calling {contact} right now could help too." if contact else ""
        st.error(
            "If you're in immediate danger, please reach out to emergency services now, "
            f"or a crisis line, before anything else.{extra}"
        )
    # Always-visible safety net regardless of what the model returns
    # (fixes Security: critical safety info is never solely AI-dependent).
    st.caption("In the US: 988 Suicide & Crisis Lifeline (call or text 988), available 24/7.")

    if st.button("I'm steadier now", type="primary", use_container_width=True):
        go("home")


def screen_journal():
    if st.button("← Back to home"):
        go("home")

    st.subheader("Your story")
    entries = list(reversed(st.session_state.data["journal"]))
    if not entries:
        st.caption("Nothing here yet — check in when something's going on, and I'll write it down for you.")
    for e in entries:
        with st.container(border=True):
            from datetime import datetime as _dt
            st.caption(_dt.fromisoformat(e["at"]).strftime("%b %d, %Y — %I:%M %p"))
            st.write(e["summary"])


# ---------- router ----------

st.set_page_config(page_title="AI Recovery Companion", page_icon="🌙", layout="centered")

screens = {
    "onboarding": screen_onboarding,
    "home": screen_home,
    "checkin": screen_checkin,
    "emergency": screen_emergency,
    "journal": screen_journal,
}
screens[st.session_state.screen]()
