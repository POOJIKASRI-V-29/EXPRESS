"""Action safety for JOCasta.

Not every tool call deserves the same trust. Reads are free. Routine capture
("add a task", "log 30 minutes") should feel instant. But deleting a record,
moving a real deadline, changing a budget cap, or rewriting several rows at once
is the kind of thing a user wants to see before it happens.

So each tool carries a risk level, and a proposed plan is gated on the highest
risk it contains — plus a bulk rule, because five individually-harmless edits
applied silently is its own surprise.

The confirmation handshake is stateless. Instead of parking pending actions in a
table, the plan is signed with the app secret and bound to the user and a short
expiry. That means a confirmation token cannot be forged, cannot be replayed by
another user, cannot outlive its window, and leaves nothing to clean up.
"""
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

READ = "read"            # no side effects
WRITE = "write"          # routine capture; runs immediately
SENSITIVE = "sensitive"  # destructive or high-impact; asks first

# Anything not listed is treated as SENSITIVE — an unclassified new tool should
# fail closed, not quietly gain the right to act unannounced.
RISK = {
    # ---- reads ----
    "get_tasks": READ, "get_deadlines": READ, "get_progress": READ, "get_schedule": READ,
    "get_college": READ, "get_learning": READ, "get_projects": READ, "get_habits": READ,
    "get_finance": READ, "get_goals": READ, "get_career": READ, "get_signals": READ,
    "get_plan_today": READ, "get_memories": READ, "search_memory": READ,
    "search_notes": READ, "find_task": READ,
    # Proposes a schedule; the intents it expands into are gated on their own.
    "propose_plan": READ,

    # ---- routine capture ----
    "create_task": WRITE, "create_reminder": WRITE, "create_note": WRITE,
    "save_memory": WRITE, "create_topic": WRITE, "create_habit": WRITE,
    "create_goal": WRITE, "create_assignment": WRITE, "create_project_task": WRITE,
    "log_study": WRITE, "log_habit": WRITE, "log_expense": WRITE,
    "schedule_study": WRITE, "mark_attendance": WRITE,
    "complete_task": WRITE, "complete_task_by_name": WRITE, "update_task": WRITE,
    "acknowledge_signal": WRITE,

    # ---- ask first ----
    "delete_memory": SENSITIVE,     # destroys something the user asked to keep
    "update_memory": SENSITIVE,     # rewrites a stored fact in place
    "reschedule_task": SENSITIVE,   # moves a real deadline
    "set_budget": SENSITIVE,        # redefines what "over budget" means
    "update_goal": SENSITIVE,       # can mark a goal achieved or dropped
}

# Several mutations in one breath is a bulk update, whatever their individual risk.
BULK_THRESHOLD = 3

CONFIRM_TTL_SECONDS = 600
_AUDIENCE = "jocasta-confirm"


def risk_of(tool: str) -> str:
    return RISK.get(tool, SENSITIVE)


def is_mutation(tool: str) -> bool:
    return risk_of(tool) != READ


def classify(intents: list[dict]) -> dict:
    """Decide whether a plan can run immediately, and say why if it cannot."""
    tools = [i.get("tool", "") for i in intents]
    sensitive = [t for t in tools if risk_of(t) == SENSITIVE]
    mutations = [t for t in tools if is_mutation(t)]

    if sensitive:
        reason = ("This would " + _phrase(sensitive[0])
                  + ("" if len(sensitive) == 1 else f", plus {len(sensitive) - 1} more change(s)")
                  + ".")
        return {"needs_confirmation": True, "reason": reason,
                "risk": SENSITIVE, "sensitive_tools": sensitive}

    if len(mutations) >= BULK_THRESHOLD:
        return {"needs_confirmation": True,
                "reason": f"This would make {len(mutations)} changes at once.",
                "risk": WRITE, "sensitive_tools": []}

    return {"needs_confirmation": False, "reason": "",
            "risk": WRITE if mutations else READ, "sensitive_tools": []}


def _phrase(tool: str) -> str:
    return {
        "delete_memory": "permanently delete a saved memory",
        "update_memory": "rewrite a saved memory",
        "reschedule_task": "move a deadline",
        "set_budget": "change a budget limit",
        "update_goal": "change a goal's status or progress",
    }.get(tool, f"run {tool.replace('_', ' ')}")


def _readable(db, user, args: dict) -> str:
    """A human label for what an action targets.

    Ids are resolved to names: asking someone to approve
    "move a deadline: 97f29d96-a801-..." is not asking them anything at all.
    Lookups stay scoped to the user, so this can never disclose another
    user's row.
    """
    for key in ("title", "text", "query", "goal", "topic", "habit", "project",
                "course", "category", "name"):
        if args.get(key):
            return str(args[key])

    if db is not None and user is not None:
        from app.models import Memory, Task
        if args.get("task_id"):
            t = (db.query(Task)
                 .filter(Task.id == args["task_id"], Task.user_id == user.id).first())
            if t:
                when = args.get("due_at")
                return f"“{t.title}”" + (f" → {str(when)[:16].replace('T', ' ')}" if when else "")
        if args.get("memory_id"):
            m = (db.query(Memory)
                 .filter(Memory.id == args["memory_id"], Memory.user_id == user.id).first())
            if m:
                return f"“{m.text[:80]}”"
    return ""


def describe(intents: list[dict], db=None, user=None) -> list[dict]:
    """What the user is being asked to approve, in plain language."""
    out = []
    for i in intents:
        tool = i.get("tool", "")
        args = i.get("args") or {}
        label = _phrase(tool) if risk_of(tool) == SENSITIVE else tool.replace("_", " ")
        detail = _readable(db, user, args)
        out.append({"tool": tool, "risk": risk_of(tool),
                    "summary": f"{label}{f': {detail}' if detail else ''}"[:180]})
    return out


def sign(user_id: str, intents: list[dict]) -> str:
    """Bind a plan to one user for a short window. Not forgeable without SECRET_KEY."""
    nowt = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "aud": _AUDIENCE, "intents": intents,
         "iat": nowt, "exp": nowt + timedelta(seconds=CONFIRM_TTL_SECONDS)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify(user_id: str, token: str) -> list[dict]:
    """Return the approved intents, or raise. Rejects another user's token,
    an expired one, or anything not issued by this endpoint."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM], audience=_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise ValueError("That confirmation expired. Ask me again and I'll re-check.")
    except Exception:
        raise ValueError("That confirmation isn't valid.")
    if str(payload.get("sub")) != str(user_id):
        raise ValueError("That confirmation isn't valid.")
    intents = payload.get("intents")
    if not isinstance(intents, list):
        raise ValueError("That confirmation isn't valid.")
    return intents
