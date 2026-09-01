"""JOCasta orchestrator: plan -> validate -> execute -> reply.

Flow:
  1. A planner (LLM if configured, else rules) proposes tool intents.
  2. Each intent's args are validated against a strict pydantic schema.
  3. The authorized executor runs the tool scoped to the authenticated user.
The planner never receives the db session or user rows. Only step 3 can write.
"""
import logging
import re
import time
from datetime import datetime

from app.core.config import settings
from app.core.logging import log
from app.models import JOCastaConversation, Task
from app.jocasta.tools import REGISTRY
from app.jocasta import (planner_rules, planner_llm, context as ctx_mod, safety,
                          planning, conversation, brain, intent as intent_mod)
from app.jocasta import attachment as attachment_flow
from app.services import syllabus as syllabus_svc, timetable as timetable_svc
from app.services.attachments import Attachment
from app.services.timeutils import as_utc, to_local
from app.jocasta.intent import Intent

logger = logging.getLogger("express.jocasta")

# Which module a tool touched, so the UI can refresh the right screen.
TOOL_MODULE = {
    "create_task": "tasks", "update_task": "tasks", "complete_task": "tasks",
    "complete_task_by_name": "tasks", "reschedule_task": "tasks", "find_task": "tasks",
    "reschedule_task_by_name": "planner", "delete_task": "planner",
    "update_course": "college", "delete_course": "college",
    "schedule_class": "college", "reschedule_class": "college",
    "delete_class": "college",
    "create_reminder": "planner", "get_plan_today": "planner",
    "save_memory": "memory", "search_memory": "memory", "update_memory": "memory",
    "delete_memory": "memory", "get_memories": "memory",
    "create_note": "personal", "search_notes": "personal",
    "log_habit": "personal", "create_habit": "personal", "get_habits": "personal",
    "create_assignment": "college", "mark_attendance": "college",
    "set_attendance": "college", "create_course": "college", "get_course": "college",
    "set_course_drive": "college", "complete_topic": "college",
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


def _plan(text: str, brief: str = "", referent: dict | None = None):
    """Choose a planner. The LLM is preferred when configured; any failure falls
    back to the deterministic rules planner.

    The fallback is logged rather than silent: without this, a wrong model id, a
    revoked key or a network outage would look exactly like normal operation
    while quietly degrading every reply.
    """
    if planner_llm.available():
        started = time.perf_counter()
        try:
            calls = planner_llm.plan(text, brief, referent)
            ms = round((time.perf_counter() - started) * 1000, 1)
            if calls:
                log(logger, logging.INFO, "planner: llm",
                    tools=[c["tool"] for c in calls], ms=ms)
                return calls, "llm"
            log(logger, logging.INFO, "planner: llm proposed nothing, using rules", ms=ms)
        except Exception as exc:
            log(logger, logging.ERROR, "planner: llm failed, falling back to rules",
                error=type(exc).__name__, detail=str(exc)[:300],
                model=settings.GEMINI_MODEL)   # the model actually called
    calls = planner_rules.plan(text)
    log(logger, logging.INFO, "planner: rules", tools=[c["tool"] for c in calls])
    return calls, "rules"


_FREE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b")


def _stated_free_minutes(text: str) -> int | None:
    """"I have two hours free" -> 120. Returns None when no figure was given."""
    words = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
             "half an": 0.5, "couple of": 2}
    t = (text or "").lower()
    m = _FREE_RE.search(t)
    if m:
        n = float(m.group(1))
        return int(n * 60) if m.group(2).startswith(("h", "hr")) else int(n)
    for word, n in words.items():
        if re.search(rf"\b{word}\s+hours?\b", t):
            return int(n * 60)
    return None


def _when_words(iso: str | None) -> str:
    """"tomorrow at 8:00 AM" — how a person says a time, not an ISO string."""
    if not iso:
        return ""
    from datetime import datetime, timedelta
    from app.services.timeutils import as_utc, to_local, local_today
    try:
        when = to_local(as_utc(datetime.fromisoformat(str(iso).replace("Z", "+00:00"))))
    except Exception:
        return ""
    if when is None:
        return ""
    delta = (when.date() - local_today()).days
    day = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(delta)
    if day is None:
        # No leading preposition — callers supply the one that fits their sentence.
        day = when.strftime("%a %d %b") if abs(delta) < 300 else when.strftime("%d %b %Y")
    clock = when.strftime("%-I:%M %p") if hasattr(when, "strftime") else ""
    return f"{day} at {clock}" if clock else day


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
        when = _when_words(res.get("due_at"))
        return (f"Done — I added {res['title']} for {when}." if when
                else f"Done — I added {res['title']}. It's unscheduled for now.")
    if tool in ("complete_task", "complete_task_by_name"):
        title = (res or {}).get("title")
        if (res or {}).get("kind") == "concept":
            course = res.get("course")
            tail = f" {course} is now {res.get('course_progress', 0)}% covered." if course else ""
            return f"Ticked off “{title}”.{tail}"
        return f"Marked “{title}” complete." if title else "Marked it complete."
    if tool == "complete_topic":
        tail = (f" {res['course']} is now {res['course_progress']}% covered."
                if res.get("course") else "")
        return f"{'Ticked off' if res['done'] else 'Un-ticked'} “{res['topic']}”.{tail}"
    if tool == "create_course":
        held = res.get("total_classes") or 0
        tail = f" Attendance starts at {res['attendance']}%." if held else \
               " No classes recorded yet — add attendance as you go."
        return f"Added {res['name']}.{tail}"
    if tool == "set_attendance":
        return (f"{res['course']} attendance set to {res['attendance']}% "
                f"({res['attended_classes']} of {res['total_classes']}).")
    if tool == "set_course_drive":
        return f"Saved the Drive link on {res['course']}."
    if tool == "get_course":
        return (f"{res['name']}: attendance {res['attendance']}% "
                f"({res['attended_classes']}/{res['total_classes']}), "
                f"{res['topics_done']}/{res['topics_total']} concepts covered"
                + (f", next up {res['next_module']}." if res.get("next_module") else "."))
    if tool in ("reschedule_task", "reschedule_task_by_name"):
        title = (res or {}).get("title")
        when = _when_words((res or {}).get("due_at"))
        if title and when:
            return f"Done — {title} is now {when}."
        return "Done — moved it." if not title else f"Done — moved {title}."
    if tool == "create_reminder":
        when = _when_words(res.get("remind_at"))
        return (f"Done — I'll nudge you about {res['title']} {when}." if when
                else f"Done — reminder set for {res['title']}.")
    if tool == "create_assignment":
        where = f" for {res['course']}" if res.get("course") else ""
        return f"Added the assignment “{res['title']}”{where} — it's on your planner now."
    if tool == "mark_attendance":
        verb = "Marked present" if res["attended"] else "Marked absent"
        return (f"{verb} for {res['course']} — now {res['attendance']}% "
                f"({res['attended_classes']} of {res['total_classes']}).")
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
    if tool == "delete_task":
        return f"Done — {res['title']} is off your planner."

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
        day = (res or {}).get("day", "today")
        rows = (res or {}).get("classes", [])
        if not rows:
            return f"Nothing on your timetable {day}."
        listed = ", ".join(f"{c['course']} at {c['start']}"
                           + (f" in {c['room']}" if c.get("room") else "")
                           for c in rows)
        return f"{day.capitalize()}: {listed}."
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

    # A tool without its own sentence still must not leak its internal name.
    return "Done."


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
           "context_used": [], "intent": "", "intent_reason": ""}
    out.update(extra or {})
    return out


def _history(db, user, limit: int = brain.HISTORY_TURNS) -> list[dict]:
    """Recent user/assistant turns, oldest first.

    Tool rows are left out: they are internal bookkeeping, and feeding them to
    the conversational layer would invite it to narrate machinery.
    """
    rows = (db.query(JOCastaConversation)
            .filter(JOCastaConversation.user_id == user.id,
                    JOCastaConversation.role.in_(("user", "assistant")))
            .order_by(JOCastaConversation.created_at.desc())
            .limit(limit).all())
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _say(db, user, text: str, fallback: str, intent: Intent, why: str,
         brief: str = "", note: str = "") -> dict:
    """Answer conversationally.

    The language model writes the sentence when one is configured; the
    deterministic reply is used otherwise, and whenever the model fails. Either
    way this path runs no tools, so nothing it says can change anything.
    """
    reply = None
    if brain.available():
        # The session does not autoflush, so this turn's own user message is
        # normally still pending and absent here — but drop it defensively if a
        # flush has happened, so it isn't sent twice.
        history = _history(db, user)
        if history and history[-1]["role"] == "user" \
                and history[-1]["content"].strip() == (text or "").strip():
            history = history[:-1]
        reply = brain.converse(text, brief=brief, history=history, note=note)
    return _talk(db, user, text, reply or fallback, intent, why,
                 source="llm" if reply else "rules")


def _talk(db, user, text: str, reply: str, intent: Intent, why: str,
          source: str = "rules") -> dict:
    """A turn that deliberately runs no tools."""
    db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
    db.commit()
    log(logger, logging.INFO, "jocasta turn (no tools)",
        user_id=str(user.id), intent=intent.value, reason=why, voice=source)
    return {"reply": reply, "calls": [], "planner": source, "modules": [],
            "verification": {"attempted": 0, "succeeded": 0, "failed": 0, "failures": []},
            "pending": None, "confirm_token": None, "context_used": [],
            "intent": intent.value, "intent_reason": why}


#: Words that mean the user actually named a day. Anything else is time-only.
_NAMED_A_DAY = re.compile(
    r"\b(today|tonight|this evening|tomorrow|tmrw|day after tomorrow|next week|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"\d{1,2}\s*(st|nd|rd|th)\b|\d{4}-\d{2}-\d{2})\b", re.I)


def _keep_referent_day(args: dict, referent: dict | None, text: str) -> None:
    """"Move it to 8pm" keeps the item on its own day.

    A bare time is resolved by the rules planner to today-if-it-hasn't-passed,
    which is right when creating something new and wrong when moving an item
    that already has a date: a session booked for tomorrow silently jumped back
    to today. Only re-anchors when the user named no day at all.
    """
    new_iso, old_iso = args.get("due_at"), (referent or {}).get("due_at")
    if not new_iso or not old_iso or _NAMED_A_DAY.search(text or ""):
        return
    try:
        new_local = to_local(as_utc(datetime.fromisoformat(str(new_iso))))
        old_local = to_local(as_utc(datetime.fromisoformat(str(old_iso))))
    except (TypeError, ValueError):
        return
    if not new_local or not old_local or new_local.date() == old_local.date():
        return
    args["due_at"] = as_utc(new_local.replace(
        year=old_local.year, month=old_local.month, day=old_local.day)).isoformat()


def _recent_referent(db, user) -> dict | None:
    """What "it" / "that" most plausibly refers to.

    Taken from the last successful tool result in this user's transcript, so a
    follow-up like "move it to 8" resolves to the thing just created rather
    than to a fresh guess. Returns None when there is nothing recent — in which
    case the caller asks instead of assuming.
    """
    rows = (db.query(JOCastaConversation)
            .filter(JOCastaConversation.user_id == user.id,
                    JOCastaConversation.role == "tool")
            .order_by(JOCastaConversation.created_at.desc())
            .limit(4).all())
    for row in rows:
        blob = row.content or ""
        # Tool results are stored as the repr of a dict. Accept `task_id` as
        # well as `id`: tools that act through another record (schedule_study
        # materialises a task) report the subject under its own name, and
        # missing that made "move it to 8" resolve to nothing.
        ids = re.findall(r"'(?:task_)?id':\s*'([0-9a-fA-F-]{36})'", blob)
        # A listing is not a referent. get_tasks returns every open task, and
        # taking the first would silently point "delete that" at an unrelated
        # one — a single subject is the only safe answer.
        if len(ids) != 1:
            continue
        m_title = re.search(r"'(?:title|topic|name)':\s*'([^']{1,120})'", blob)
        m_due = re.search(r"'due_at':\s*'([0-9T:+\-.]{10,40})'", blob)
        ref = {"tool": row.tool_name, "id": ids[0],
               "title": m_title.group(1) if m_title else "",
               "due_at": m_due.group(1) if m_due else ""}
        # The stored blob is a snapshot from when the tool ran. Anything decided
        # from it — "keep this item's day" especially — has to use where the
        # record is *now*, or a second move re-anchors to a stale time.
        live = (db.query(Task)
                .filter(Task.user_id == user.id, Task.id == ids[0]).first())
        if live is not None:
            ref["title"] = live.title or ref["title"]
            ref["due_at"] = live.due_at.isoformat() if live.due_at else ref["due_at"]
        return ref
    return None


def _attachment_turn(db, user, text: str, attachment_token: str,
                     intent: Intent, why: str) -> dict:
    """The user attached a file and said something.

    Interpretation happens here rather than at upload time, because the same
    document means different things depending on what was asked. Anything that
    would write returns a preview and a confirmation token instead.
    """
    try:
        payload = safety.verify_payload(user.id, attachment_token)
    except ValueError as exc:
        return _talk(db, user, text, str(exc), Intent.CLARIFY, "invalid attachment")

    att = Attachment(filename=payload.get("filename", "attachment"),
                     kind=payload.get("type", "text"),
                     text=payload.get("text", ""),
                     pages=int(payload.get("pages") or 1))

    outcome = attachment_flow.build(db, user, text, att)

    if outcome["kind"] == "talk":
        return _talk(db, user, text, outcome["reply"], intent, why)

    token = safety.sign_payload(user.id, outcome["payload"], audience="jocasta-confirm")
    db.add(JOCastaConversation(user_id=user.id, role="assistant", content=outcome["reply"]))
    db.commit()
    log(logger, logging.INFO, "attachment awaiting confirmation",
        user_id=str(user.id), file=att.filename,
        payload_kind=outcome["payload"].get("kind"))
    return {"reply": outcome["reply"], "calls": [], "planner": "attachment",
            "modules": [],
            "verification": {"attempted": 0, "succeeded": 0, "failed": 0, "failures": []},
            "pending": {"actions": outcome["actions"], "reason": outcome["reason"],
                        "risk": outcome["risk"]},
            "confirm_token": token, "context_used": ["attachment"],
            "intent": intent.value, "intent_reason": why}


def run(db, user, text: str, attachment_token: str | None = None) -> dict:
    """Classify -> (talk | ask) or -> context -> reason -> gate -> execute -> explain.

    The classification step is what stops an ordinary sentence becoming a
    database record: only intents in `WRITE_INTENTS` are allowed to reach a
    mutating tool, and an unrecognised message asks rather than acts.
    """
    started = time.perf_counter()
    db.add(JOCastaConversation(user_id=user.id, role="user", content=text))

    intent, why = intent_mod.classify(text)

    # An attachment changes what the message means, so it is handled first —
    # whatever the instruction alone would have been classified as.
    if attachment_token:
        return _attachment_turn(db, user, text, attachment_token, intent, why)

    if intent is Intent.TIMETABLE:
        return _talk(db, user, text,
                     "Attach your timetable PDF and I'll read it — then I'll show you "
                     "what I found before adding anything.", Intent.CLARIFY,
                     "timetable request with no attachment")

    # --- paths that never write -------------------------------------------
    if intent is Intent.CONVERSATION:
        # A sign-off or a thank-you needs no context; being handed a to-do list
        # at "good night" is exactly the over-contextualising to avoid.
        light = conversation.is_light_turn(text)
        return _say(db, user, text,
                    conversation.conversation_reply(db, user, text), intent, why,
                    brief="" if light else conversation.state_brief(db, user),
                    note=("The user is signing off or just acknowledging you. Keep it "
                          "to a short, warm line. Do not mention tasks, deadlines or "
                          "anything outstanding." if light else
                          "Only mention their state if it genuinely helps. A greeting "
                          "usually needs none of it."))

    if intent is Intent.SUGGESTION:
        minutes = _stated_free_minutes(text)
        # "What should I study tonight" is a different question from "what
        # should I do" — it should be answered with study, not the nearest chore.
        focus = "study" if re.search(
            r"\b(study|studying|revise|revision|learn|learning|read up|practice|practise)\b",
            (text or "").lower()) else ""
        deterministic = conversation.suggestion_reply(db, user, minutes, focus=focus)
        return _say(db, user, text, deterministic, intent, why,
                    brief=conversation.state_brief(db, user, focus=focus or "plan"),
                    note=("Give one clear recommendation with the reason, in a sentence "
                          "or two. Only name things that appear in the state block. "
                          "If there is nothing meaningful, say so rather than inventing "
                          "an errand."))

    if intent is Intent.CLARIFY:
        return _say(db, user, text, conversation.clarify_reply(intent, text), intent, why,
                    brief=conversation.state_brief(db, user),
                    note=("They've asked for something but not said enough to act on. "
                          "Ask the one question you need, naturally. Do not guess and "
                          "do not claim to have done anything."))

    if intent is Intent.UNKNOWN:
        return _say(db, user, text, conversation.unknown_reply(text), intent, why,
                    brief=conversation.state_brief(db, user),
                    note=("You're not sure what they want. Reply naturally — answer if "
                          "it's just conversation, or ask what they'd like. Never "
                          "assume it was an instruction to create something."))

    # 1-2. Targeted, bounded, user-scoped context.
    ctx = ctx_mod.build(db, user, text)
    brief = ctx_mod.summarize(ctx)

    # 3. Reason -> propose tool intents.
    # The referent is resolved *before* planning, not just patched afterwards:
    # the rule planner proposes a tool that can be patched, but a model given no
    # subject for "it" proposes something unrelated (a read, typically) and
    # there is then nothing to correct.
    referent = _recent_referent(db, user) if intent_mod.is_referential(text) else None
    intents, planner = _plan(text, brief, referent)

    # 3a. Resolve "it" / "that" against the last thing acted on. Without a
    # referent, ask — a follow-up aimed at nothing must not act on a guess.
    if intent_mod.is_referential(text):
        if referent and referent.get("id"):
            for i in intents:
                args = i.setdefault("args", {})
                if i["tool"] in ("reschedule_task", "update_task", "complete_task") \
                        and not args.get("task_id"):
                    args["task_id"] = referent["id"]
                if i["tool"] in ("reschedule_task", "reschedule_task_by_name"):
                    _keep_referent_day(args, referent, text)
                if i["tool"] in ("delete_task", "reschedule_task_by_name") \
                        and not args.get("query"):
                    args["query"] = referent.get("title") or ""
        elif any(i.get("tool") in ("reschedule_task", "update_task", "complete_task",
                                   "delete_task", "reschedule_task_by_name")
                 for i in intents):
            return _talk(db, user, text,
                         "I'm not sure which one you mean — say the name and I'll do it.",
                         Intent.CLARIFY, "referential with no recent subject")

    # 3b. Hard guarantee: a message that was not an instruction to change
    # something cannot reach a mutating tool, whatever the planner proposed.
    # This is what stops "how are you" ever becoming a task again.
    if not intent_mod.may_write(intent) and intent is not Intent.PLANNING:
        blocked = [i["tool"] for i in intents if safety.is_mutation(i.get("tool", ""))]
        if blocked:
            log(logger, logging.WARNING, "blocked write on a non-write intent",
                intent=intent.value, tools=blocked, user_id=str(user.id))
            intents = [i for i in intents if not safety.is_mutation(i.get("tool", ""))]
        if not intents:
            # Nothing read-only left to run — answer rather than act.
            return _say(db, user, text, conversation.unknown_reply(text),
                        Intent.UNKNOWN, "no read-only tool matched",
                        brief=conversation.state_brief(db, user))

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
                    "context_used": ctx["included_slices"], "plan": proposal["plan"],
                    "intent": intent.value, "intent_reason": why}

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
        # Prefer a reason that names the actual item over the generic one.
        specific = safety.reason_for(intents, db, user)
        reply = ((narration + "\n\n") if narration else "") + \
            (specific or verdict["reason"]) + " Want me to go ahead?"
        db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
        db.commit()
        log(logger, logging.INFO, "awaiting confirmation", user_id=str(user.id),
            tools=[i.get("tool") for i in intents], risk=verdict["risk"])
        return {"reply": reply, "calls": [], "planner": planner, "modules": [],
                "verification": {"attempted": 0, "succeeded": 0, "failed": 0, "failures": []},
                "pending": {"actions": actions, "reason": verdict["reason"],
                            "risk": verdict["risk"]},
                "confirm_token": token,
                "context_used": ctx["included_slices"],
                "intent": intent.value, "intent_reason": why}

    # 5-7. Execute, verify, explain.
    results = _execute(db, user, intents)
    log(logger, logging.INFO, "jocasta turn", user_id=str(user.id), planner=planner,
        slices=ctx["included_slices"], tools=[r["tool"] for r in results],
        ms=round((time.perf_counter() - started) * 1000, 1))
    return _finish(db, user, text, intents, results, planner,
                   {"context_used": ctx["included_slices"],
                    "intent": intent.value, "intent_reason": why})


def confirm(db, user, token: str) -> dict:
    """Run a plan the user explicitly approved.

    The token is re-verified here rather than trusted from the client: it must
    still be unexpired and must belong to this user.
    """
    # A confirmation carries either a bundle of tool intents or a timetable
    # import. Both are signed and user-bound; try the timetable shape first.
    try:
        payload = safety.verify_payload(user.id, token, audience="jocasta-confirm")
    except ValueError:
        payload = None
    if payload and payload.get("kind") == "course_structure":
        from app.models import Course, CourseModule, CourseTopic
        course = (db.query(Course)
                  .filter(Course.id == payload["course_id"], Course.user_id == user.id)
                  .first())
        if not course:
            raise ValueError("That course no longer exists.")
        base = (db.query(CourseModule)
                .filter(CourseModule.course_id == course.id,
                        CourseModule.user_id == user.id).count())
        modules = payload.get("modules", [])
        concepts = 0
        for i, mod in enumerate(modules):
            m = CourseModule(user_id=user.id, course_id=course.id,
                             name=mod["name"], order=base + i)
            db.add(m); db.flush()
            for j, topic in enumerate(mod.get("topics", [])):
                db.add(CourseTopic(user_id=user.id, module_id=m.id, name=topic, order=j))
                concepts += 1
        reply = (f"Added {len(modules)} module(s) and {concepts} concept(s) "
                 f"to {course.name}.")
        db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
        db.commit()
        log(logger, logging.INFO, "course structure applied", user_id=str(user.id),
            course=course.name, modules=len(modules), concepts=concepts)
        return {"reply": reply, "calls": [], "planner": "attachment",
                "modules": ["college"],
                "verification": {"attempted": len(modules), "succeeded": len(modules),
                                 "failed": 0, "failures": []},
                "pending": None, "confirm_token": None, "context_used": [],
                "intent": "attachment", "intent_reason": "confirmed course structure"}

    if payload and payload.get("kind") == "timetable_apply":
        proposals = [timetable_svc.ProposedClass(**e) for e in payload.get("entries", [])]
        result = timetable_svc.apply_import(db, user, proposals,
                                            replace=bool(payload.get("replace")))
        bits = [f"Added {result['added']} class(es) to your Planner."]
        if result["removed"]:
            bits.insert(0, f"Removed your previous {result['removed']} slot(s).")
        if result["skipped_duplicates"]:
            bits.append(f"Skipped {result['skipped_duplicates']} already there.")
        if result["skipped_unmatched"]:
            bits.append("Skipped " + str(result["skipped_unmatched"])
                        + " with no matching course ("
                        + ", ".join(result["unmatched_names"][:4]) + ").")
        reply = " ".join(bits)
        db.add(JOCastaConversation(user_id=user.id, role="assistant", content=reply))
        db.commit()
        log(logger, logging.INFO, "timetable applied", user_id=str(user.id), **{
            k: v for k, v in result.items() if isinstance(v, int)})
        return {"reply": reply, "calls": [], "planner": "timetable",
                "modules": ["planner", "college"],
                "verification": {"attempted": result["added"], "succeeded": result["added"],
                                 "failed": 0, "failures": []},
                "pending": None, "confirm_token": None, "context_used": [],
                "intent": "timetable", "intent_reason": "confirmed import"}

    intents = safety.verify(user.id, token)   # raises on tampering/expiry/wrong user
    db.add(JOCastaConversation(user_id=user.id, role="user", content="[confirmed]"))
    results = _execute(db, user, intents)
    log(logger, logging.INFO, "confirmed plan executed", user_id=str(user.id),
        tools=[r["tool"] for r in results])
    return _finish(db, user, "[confirmed]", intents, results, "confirmed")
