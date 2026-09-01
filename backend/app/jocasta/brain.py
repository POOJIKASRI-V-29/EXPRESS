"""JOCasta's conversational layer.

This generates *language*. It does not decide what is true and it cannot change
anything: it never receives a database session, it is never asked to pick a
tool, and every fact it is allowed to mention is handed to it as text that the
deterministic layer already read from the database.

The split matters. Tool selection, validation, ownership and confirmation stay
where they were — in `intent`, `planner_rules`/`planner_llm`, `safety` and the
executor. If this module returns nothing (no key, network failure, refusal, a
malformed reply), the caller falls back to the deterministic templates and the
assistant carries on. Conversation degrades; it never breaks.

Nothing here is faked. With no `GEMINI_API_KEY` the module reports itself
unavailable and is never called. The provider seam lives in `llm.py`.
"""
import logging
import time

from app.jocasta import llm
from app.core.logging import log

logger = logging.getLogger("express.jocasta.brain")

#: A chat reply should be short. Reasoning tokens come out of this budget on
#: thinking-capable models, so it sits well above the visible length — a reply
#: truncated to nothing would only show up as an unexplained fallback.
MAX_TOKENS = 4096

#: How much of the transcript to carry. Enough for "make that 8 instead" to
#: resolve, small enough to stay cheap.
HISTORY_TURNS = 8

SYSTEM = """You are JOCasta, the assistant inside EXPRESS — a student's personal \
operating system. You are talking to its owner.

HOW YOU SOUND
- Calm, warm, concise. Two or three sentences is usually plenty.
- Conversational, not a status readout. Never bullet-point ordinary chat.
- Lightly witty when it fits. Never chirpy, never a cheerleader.
- You are not a productivity coach. If someone says they're tired, be a person \
about it — don't pivot to their task list unless it genuinely helps.

WHAT YOU KNOW
- The CURRENT STATE block below is the only source of facts about this user. It \
was read from their real records a moment ago.
- If something isn't in it, you don't know it. Say so plainly. Never guess at a \
course, deadline, task, grade or time, and never invent a number.
- Don't recite the whole state back. Mention only what makes your answer better. \
A greeting rarely needs any of it.

WHAT YOU MUST NOT DO
- Never claim you did something. You cannot create, change or delete anything — \
another part of the system does that, and it will tell the user itself. If they \
ask for an action, acknowledge it naturally and let it happen; don't say "done".
- Never state a fact that isn't in the state block.
- Don't mention tools, intents, context slices or how you work."""


def available() -> bool:
    """A key is configured. Says nothing about whether it works — see status()."""
    return llm.configured()


def status() -> dict:
    """Provider health, for readiness. Makes no API call."""
    return llm.status()


def _contents(history: list[dict], message: str) -> list[dict]:
    """Recent turns plus the new one, in Gemini's `contents` shape.

    Gemini names the assistant role "model", and expects turns to alternate, so
    consecutive same-role turns are merged — the transcript can hold several
    assistant lines in a row.
    """
    out: list[dict] = []
    for turn in history[-HISTORY_TURNS:]:
        role = "user" if turn.get("role") == "user" else "model"
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["parts"][0]["text"] += "\n" + content
        else:
            out.append({"role": role, "parts": [{"text": content}]})

    if out and out[-1]["role"] == "user":
        out[-1]["parts"][0]["text"] += "\n" + message
    else:
        out.append({"role": "user", "parts": [{"text": message}]})

    # The conversation has to start with a user turn.
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out or [{"role": "user", "parts": [{"text": message}]}]


def converse(message: str, brief: str = "", history: list[dict] | None = None,
             note: str = "") -> str | None:
    """Generate a reply, or None if the caller should use its fallback.

    `brief` is the bounded context assembled by `context.py` — never raw rows.
    `note` is an optional instruction for this turn (for example, that the user
    is signing off and should not be handed a to-do list).
    """
    if not available():
        return None

    from google.genai import types      # imported lazily so the dep is optional

    system = SYSTEM
    if brief:
        system += f"\n\n--- CURRENT STATE ---\n{brief}\n--- END STATE ---"
    else:
        system += ("\n\n--- CURRENT STATE ---\n(nothing loaded for this turn — "
                   "answer conversationally and don't assert any facts)\n--- END STATE ---")
    if note:
        system += f"\n\nFOR THIS REPLY: {note}"

    started = time.perf_counter()
    try:
        resp = llm.client().models.generate_content(
            model=llm.model(),
            contents=_contents(history or [], message),
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_TOKENS,
                # No tools are offered on this path at all, so the conversational
                # layer has nothing it could call even in principle.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True),
            ),
        )
    except Exception as exc:
        # A conversational failure must never break the turn.
        llm.note_failure(exc, where="brain")
        return None

    declined = llm.refusal_reason(resp)
    if declined:
        log(logger, logging.INFO, "brain declined this turn", reason=declined)
        return None

    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        # Usually the reply budget went entirely on reasoning. Recorded rather
        # than swallowed, so it is visible in /ready instead of looking like the
        # deterministic layer simply chose to answer.
        llm.note_failure(RuntimeError("model returned no text"), where="brain")
        return None

    llm.note_ok()
    log(logger, logging.INFO, "brain replied",
        chars=len(text), ms=round((time.perf_counter() - started) * 1000, 1))
    return text
