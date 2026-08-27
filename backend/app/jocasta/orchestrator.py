"""JOCasta orchestrator: plan -> validate -> execute -> reply.

Flow:
  1. A planner (LLM if configured, else rules) proposes tool intents.
  2. Each intent's args are validated against a strict pydantic schema.
  3. The authorized executor runs the tool scoped to the authenticated user.
The planner never receives the db session or user rows. Only step 3 can write.
"""
import logging
import time

from app.core.config import settings
from app.core.logging import log
from app.models import JOCastaConversation
from app.jocasta.tools import REGISTRY
from app.jocasta import (planner_rules, planner_llm, context as ctx_mod, safety,
                          planning)

logger = logging.getLogger("express.jocasta")

# Which module a tool touched, so the UI can refresh the right screen.
TOOL_MODULE = {
    "create_task": "tasks", "update_task": "tasks", "complete_task": "tasks",
    "complete_task_by_name": "tasks", "reschedule_task": "tasks", "find_task": "tasks",
    "create_reminder": "planner", "get_plan_today": "planner",
    "save_memory": "memory", "search_memory": "memory", "update_memory": "memory",
    "delete_memory": "memory", "get_memories": "memory",
    "create_note": "personal", "search_notes": "personal",
    "log_habit": "personal", "create_habit": "personal", "get_habits": "personal",
    "create_assignment": "college", "mark_attendance": "college",
    "get_schedule": "college", "get_college": "college", "get_deadlines": "college",
    "log_study": "learning", "schedule_study": "learning",
    "create_topic": "learning", "get_learning": "learning",
    "create_project_task": "projects", "get_projects": "projects",
    "log_expense": "finance", "set_budget": "finance", "get_finance": "finance",
    "create_goal": "goals", "update_goal": "goals", "get_goals": "goals",
    "get_career": "career",
    "get_progress": "progress",
    "get_signals": "spider-sense", "acknowledge_signal": "spider-sense",
    "get_tasks": "tasks",
}


def _plan(text: str, brief: str = ""):
    """Choose a planner. The LLM is preferred when configured; any failure falls
    back to the deterministic rules planner.

    The fallback is logged rather than silent: without this, a wrong model id, a
    revoked key or a network outage would look exactly like normal operation
    while quietly degrading every reply.
    """
    if planner_llm.available():
        started = time.perf_counter()
        try:
            calls = planner_llm.plan(text, brief)
            ms = round((time.perf_counter() - started) * 1000, 1)
            if calls:
                log(logger, logging.INFO, "planner: llm",
                    tools=[c["tool"] for c in calls], ms=ms)
                return calls, "llm"
            log(logger, logging.INFO, "planner: llm proposed nothing, using rules", ms=ms)
        except Exception as exc:
            log(logger, logging.ERROR, "planner: llm failed, falling back to rules",
                error=type(exc).__name__, detail=str(exc)[:300],
                model=settings.JOCASTA_MODEL)
    calls = planner_rules.plan(text)
    log(logger, logging.INFO, "planner: rules", tools=[c["tool"] for c in calls])
    return calls, "rules"


def _money(n) -> str:
    return f"{float(n):,.2f}"


def _one(tool: str, res, ok: bool, error) -> str:
    if not ok:
        return f"I couldn't {tool.replace('_', ' ')}: {error}"

    # ---- writes ----
    if tool == "save_memory":
        return "Saved to memory."
    if tool == "update_memory":
        return "Updated that memory."
    if tool == "delete_memory":
        return "Deleted that memory."
    if tool == "create_note":
        return f"Noted — “{res['title']}”."
    if tool == "create_task":
        return f"Got it — added “{res['title']}”."
    if tool in ("complete_task", "complete_task_by_name"):
        title = (res or {}).get("title")
        return f"Marked “{title}” complete." if title else "Marked it complete."
    if tool == "reschedule_task":
        return "Rescheduled — your planner and Spider Sense are updated."
    if tool == "create_reminder":
        return f"Reminder set: {res['title']}."
    if tool == "create_assignment":
        where = f" for {res['course']}" if res.get("course") else ""
        return f"Added the assignment “{res['title']}”{where} — it's on your planner now."
    if tool == "mark_attendance":
        verb = "Marked present" if res["attended"] else "Marked absent"
        return f"{verb} for {res['course']} — attendance is now {res['attendance']}%."
    if tool == "log_study":
        return f"Logged {res['minutes']} min on {res['topic']} — it's at {res['progress']}%."
    if tool == "schedule_study":
        return f"Study block for {res['topic']} is on your planner."
    if tool == "create_topic":
        return f"Tracking {res['name']} under {res['area']}."
    if tool == "create_project_task":
        return f"Added “{res['title']}” to {res['project']}."
    if tool == "log_habit":
        if res.get("already_done"):
            return f"{res['habit']} was already done today — streak {res['streak']}."
        return f"Logged {res['habit']} — {res['streak']} day streak."
    if tool == "create_habit":
        return f"Now tracking “{res['title']}”."
    if tool == "log_expense":
        b = res.get("budget")
        tail = f" That's {b['pct']}% of your {b['category']} budget." if b else ""
        word = "Recorded" if res["kind"] == "expense" else "Recorded income of"
        return f"{word} {_money(res['amount'])} under {res['category']}.{tail}"
    if tool == "set_budget":
        return f"{res['category']} budget set to {_money(res['monthly_limit'])} a month."
    if tool == "create_goal":
        return f"Goal set: “{res['title']}”. Link it to some work and I'll track it for you."
    if tool == "update_goal":
        return f"“{res['title']}” is at {res['progress']}% ({res['progress_source']})."
    if tool == "acknowledge_signal":
        return "Dismissed that signal."

    # ---- reads ----
    if tool == "search_memory":
        n = len(res or [])
        if not n:
            return "I don't have anything saved about that."
        head = "; ".join(m["text"] for m in res[:3])
        return f"I found {n} matching " + ("memory" if n == 1 else "memories") + f": {head}"
    if tool == "get_memories":
        return f"I'm holding {len(res or [])} memories for you."
    if tool == "search_notes":
        n = len(res or [])
        return f"{n} note(s) matched." if n else "No notes matched that."
    if tool == "get_progress":
        return (f"You've completed {res['tasks_done']}/{res['tasks_total']} items; "
                f"attendance {res['attendance']}%.")
    if tool == "get_deadlines":
        if not res:
            return "Nothing is due — you're clear."
        nxt = res[0]
        return f"You have {len(res)} open deadline(s); next up is {nxt['title']}."
    if tool == "get_schedule":
        if not res:
            return "No classes on your timetable today."
        return "Today: " + ", ".join(f"{c['course']} at {c['start']}" for c in res) + "."
    if tool == "get_college":
        risk = res.get("at_risk") or []
        tail = f" {', '.join(risk)} below the floor." if risk else " Nothing at risk."
        return f"Attendance is averaging {res['attendance']}%.{tail}"
    if tool == "get_learning":
        rev = res.get("needs_revision") or []
        tail = f" Needs revision: {', '.join(rev)}." if rev else ""
        return (f"{len(res['topics'])} topic(s), {res['total_minutes']} min logged."
                f"{tail}")
    if tool == "get_projects":
        if not res:
            return "No projects yet."
        return "Projects: " + ", ".join(f"{p['name']} at {p['completion']}%" for p in res) + "."
    if tool == "get_habits":
        done = len([h for h in res if h["done_today"]])
        return f"{done}/{len(res)} habits done today." if res else "No habits tracked yet."
    if tool == "get_finance":
        return (f"This month: {_money(res['month_spent'])} out, "
                f"{_money(res['month_income'])} in, net {_money(res['net'])}.")
    if tool == "get_goals":
        if not res:
            return "No goals set yet."
        active = [g for g in res if g["status"] == "active"]
        avg = round(sum(g["progress"] for g in active) / len(active)) if active else 0
        return f"{len(active)} active goal(s), averaging {avg}%."
    if tool == "get_career":
        if not res:
            return "No applications tracked yet."
        live = [a for a in res if a["stage"] != "result"]
        return f"{len(res)} application(s), {len(live)} still live."
    if tool == "get_signals":
        if not res:
            return "Nothing is flagged — you're clear."
        return f"{len(res)} active signal(s). Top one: {res[0]['title']}"
    if tool == "get_tasks":
        return f"{len(res or [])} task(s) open."
    if tool == "get_plan_today":
        items = res.get("items", [])
        if not items:
            return "Nothing scheduled today."
        return (f"{len(items)} thing(s) today, starting with {items[0]['title']} "
                f"at {items[0]['time']}.")
    if tool == "find_task":
        return f"That's “{res['title']}”."

    return f"Done: {tool.replace('_', ' ')}."


def _summarise(results: list[dict]) -> str:
    if not results:
        return "I couldn't work out an action for that yet."
    return " ".join(_one(r["tool"], r.get("result"), r["ok"], r.get("error")) for r in results)


def _execute(db, user, intents: list[dict]) -> list[dict]:
    """Validate then run each intent. This is the only code path that writes."""
    results = []
    for intent in intents:
        name = intent.get("tool")
        entry = REGISTRY.get(name)
        if not entry:
            results.append({"tool": name, "ok": False, "error": "unknown tool"})
            log(logger, logging.WARNING, "unknown tool proposed", tool=name)
            continue
        schema, fn = entry
        started = time.perf_counter()
        try:
            args = schema(**(intent.get("args") or {}))   # validation gate
            res = fn(db, user, args)                        # authorized execution
            results.append({"tool": name, "ok": True, "result": res})
            db.add(JOCastaConversation(user_id=user.id, role="tool",
                                       content=str(res), tool_name=name))
            log(logger, logging.INFO, "tool ok", tool=name, user_id=str(user.id),
                risk=safety.risk_of(name),
                ms=round((time.perf_counter() - started) * 1000, 1))
        except Exception as e:
            results.append({"tool": name, "ok": False, "error": str(e)})
            log(logger, logging.WARNING, "tool failed", tool=name, user_id=str(user.id),
                error=type(e).__name__, detail=str(e)[:200],
                ms=round((time.perf_counter() - started) * 1000, 1))
    return results


def _verify(results: list[dict]) -> dict:
    """Report honestly on what actually happened, rather than assuming success."""
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    return {"attempted": len(results), "succeeded": len(ok), "failed": len(failed),
            "failures": [{"tool": r["tool"], "error": r.get("error")} for r in failed]}


def _finish(db, user, text: str, intents, results, planner, extra=None) -> dict:
    reply = _summarise(results)
    db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
    db.commit()
    touched = sorted({TOOL_MODULE.get(r["tool"], "") for r in results if r["ok"]} - {""})
    out = {"reply": reply, "calls": results, "planner": planner, "modules": touched,
           "verification": _verify(results), "pending": None, "confirm_token": None,
           "context_used": []}
    out.update(extra or {})
    return out


def run(db, user, text: str) -> dict:
    """Understand -> retrieve context -> reason -> gate -> execute -> verify -> explain."""
    started = time.perf_counter()
    db.add(JOCastaConversation(user_id=user.id, role="user", content=text))

    # 1-2. Targeted, bounded, user-scoped context.
    ctx = ctx_mod.build(db, user, text)
    brief = ctx_mod.summarize(ctx)

    # 3. Reason -> propose tool intents.
    intents, planner = _plan(text, brief)

    # 3b. `propose_plan` is not an ordinary tool: it runs the allocator and
    # expands into the concrete intents that would carry the plan out. Both
    # planners can emit it, so the reasoning lives in one place.
    narration = ""
    if any(i.get("tool") == "propose_plan" for i in intents):
        horizon = next((int((i.get("args") or {}).get("horizon_days", 7))
                        for i in intents if i.get("tool") == "propose_plan"), 7)
        proposal = planning.propose(db, user, horizon_days=horizon)
        narration = planning.narrate(proposal)
        intents = [i for i in intents if i.get("tool") != "propose_plan"] + proposal["intents"]
        log(logger, logging.INFO, "planner: allocator",
            proposed=len(proposal["intents"]), unplaceable=len(proposal["unplaceable"]))
        if not intents:
            db.add(JOCastaConversation(user_id=user.id, role="assistant", content=narration))
            db.commit()
            return {"reply": narration, "calls": [], "planner": planner, "modules": [],
                    "verification": {"attempted": 0, "succeeded": 0, "failed": 0,
                                     "failures": []},
                    "pending": None, "confirm_token": None,
                    "context_used": ctx["included_slices"], "plan": proposal["plan"]}

    # 4. Gate. A risky or bulk plan is described, not performed.
    verdict = safety.classify(intents)
    if narration and intents:
        # A schedule is a proposal, however small. Showing it before applying it
        # is the whole point — the user gets to disagree with the reasoning.
        verdict = {**verdict, "needs_confirmation": True,
                   "reason": verdict["reason"] or
                             f"That's {len(intents)} change(s) to your schedule."}
    if verdict["needs_confirmation"]:
        token = safety.sign(user.id, intents)
        actions = safety.describe(intents, db, user)
        reply = ((narration + "\n\n") if narration else "") + \
            verdict["reason"] + " Want me to go ahead?"
        db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
        db.commit()
        log(logger, logging.INFO, "awaiting confirmation", user_id=str(user.id),
            tools=[i.get("tool") for i in intents], risk=verdict["risk"])
        return {"reply": reply, "calls": [], "planner": planner, "modules": [],
                "verification": {"attempted": 0, "succeeded": 0, "failed": 0, "failures": []},
                "pending": {"actions": actions, "reason": verdict["reason"],
                            "risk": verdict["risk"]},
                "confirm_token": token,
                "context_used": ctx["included_slices"]}

    # 5-7. Execute, verify, explain.
    results = _execute(db, user, intents)
    log(logger, logging.INFO, "jocasta turn", user_id=str(user.id), planner=planner,
        slices=ctx["included_slices"], tools=[r["tool"] for r in results],
        ms=round((time.perf_counter() - started) * 1000, 1))
    return _finish(db, user, text, intents, results, planner,
                   {"context_used": ctx["included_slices"]})


def confirm(db, user, token: str) -> dict:
    """Run a plan the user explicitly approved.

    The token is re-verified here rather than trusted from the client: it must
    still be unexpired and must belong to this user.
    """
    intents = safety.verify(user.id, token)   # raises on tampering/expiry/wrong user
    db.add(JOCastaConversation(user_id=user.id, role="user", content="[confirmed]"))
    results = _execute(db, user, intents)
    log(logger, logging.INFO, "confirmed plan executed", user_id=str(user.id),
        tools=[r["tool"] for r in results])
    return _finish(db, user, "[confirmed]", intents, results, "confirmed")
