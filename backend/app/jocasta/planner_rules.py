"""Deterministic fallback planner.

Turns free text into ToolCall intents WITHOUT an LLM, so JOCasta stays useful
with no API key and no network. Returns a list of {"tool": name, "args": {...}}
dicts — intents only, never execution. Every intent still passes through the
same pydantic gate and the same authorized executor as an LLM-planned one.
"""
import re
from datetime import timedelta
from app.services.timeutils import now, local_now

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}

# Wall-clock defaults, expressed in the user's zone then converted to UTC.
DEFAULT_HOUR = 9
EVENING_HOUR = 21


def _next_weekday(name: str, hour=DEFAULT_HOUR):
    target = WEEKDAYS[name]
    d = local_now()
    ahead = (target - d.weekday()) % 7 or 7
    return _utc((d + timedelta(days=ahead)).replace(hour=hour, minute=0, second=0, microsecond=0))


def _utc(dt):
    from datetime import timezone
    return dt.astimezone(timezone.utc)


def _at_local(days=0, hour=DEFAULT_HOUR, minute=0):
    d = local_now() + timedelta(days=days)
    return _utc(d.replace(hour=hour, minute=minute, second=0, microsecond=0))


def parse_when(text: str, default_hour=DEFAULT_HOUR):
    """Best-effort date/time out of everyday phrasing. Returns (datetime, matched_span)
    so the caller can strip the time words out of the title."""
    t = text.lower()
    span = ""
    hour, minute = None, None

    m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3) == "pm":
            hour += 12
        minute = int(m.group(2) or 0)
        span = m.group(0)
    else:
        m = re.search(r"\bat\s+(\d{1,2}):(\d{2})\b", t)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            span = m.group(0)

    m = re.search(r"\bin\s+(\d+)\s*(hour|hr|minute|min)s?\b", t)
    if m:
        n = int(m.group(1))
        delta = timedelta(hours=n) if m.group(2).startswith(("hour", "hr")) else timedelta(minutes=n)
        return _utc(local_now() + delta), m.group(0)

    day_offset = None
    if re.search(r"\bday after tomorrow\b", t):
        day_offset, span = 2, (span + " day after tomorrow").strip()
    elif re.search(r"\btomorrow\b", t):
        day_offset, span = 1, (span + " tomorrow").strip()
    elif re.search(r"\b(tonight|this evening)\b", t):
        day_offset = 0
        hour = hour if hour is not None else EVENING_HOUR
        span = (span + " tonight").strip()
    elif re.search(r"\btoday\b", t):
        day_offset, span = 0, (span + " today").strip()
    elif re.search(r"\bnext week\b", t):
        day_offset, span = 7, (span + " next week").strip()
    else:
        for name in WEEKDAYS:
            if re.search(rf"\b(next\s+)?{name}\b", t):
                return _next_weekday(name, hour if hour is not None else default_hour), name

    if day_offset is None and hour is None:
        return None, ""
    if day_offset is None:
        # a bare time means today if it hasn't passed, otherwise tomorrow
        candidate = _at_local(0, hour, minute or 0)
        return (candidate if candidate > now() else _at_local(1, hour, minute or 0)), span
    return _at_local(day_offset, hour if hour is not None else default_hour, minute or 0), span


def _strip(text: str, *fragments) -> str:
    out = text
    for f in fragments:
        if f:
            out = re.sub(re.escape(f), "", out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip(" ,.-—:")


def _amount(t: str):
    m = re.search(r"(?:₹|rs\.?|inr|\$)?\s*(\d+(?:\.\d{1,2})?)", t)
    return m.group(1) if m else None


# Asking for a plan is not one more CRUD verb — it routes to the allocator in
# `planning.py`, which the orchestrator expands into concrete intents.
PLAN_REQUEST = re.compile(
    r"\b(help me plan|plan my (day|week|schedule)|fix my day|sort my (day|week)|"
    r"organi[sz]e my (day|week)|what should i (do|work on)|"
    r"how do i fit|make me a (plan|schedule)|reschedule everything|"
    r"catch up on|i'?m behind)\b")


def plan(text: str) -> list[dict]:
    t = text.lower().strip()

    # ---- planning: reason over real capacity rather than create a task ----
    if PLAN_REQUEST.search(t):
        days = 7
        m = re.search(r"\b(\d{1,2})\s*days?\b", t)
        if m:
            days = max(1, min(int(m.group(1)), 14))
        elif "today" in t or "my day" in t:
            days = 2
        return [{"tool": "propose_plan", "args": {"horizon_days": days}}]

    # ---- read-only questions come first: a question should never write ----
    if re.search(r"\b(how am i doing|my progress|overall progress)\b", t):
        return [{"tool": "get_progress", "args": {}}]
    if re.search(r"\b(what'?s due|deadlines?|due soon|what is due)\b", t):
        return [{"tool": "get_deadlines", "args": {}}]
    if re.search(r"\b(my plan|plan for today|today'?s plan|what'?s on today|agenda)\b", t):
        return [{"tool": "get_plan_today", "args": {}}]
    if re.search(r"\b(classes today|timetable|class schedule|my schedule)\b", t):
        return [{"tool": "get_schedule", "args": {}}]
    if re.search(r"\b(attendance|am i short|college status)\b", t) and not re.search(r"\b(mark|attended|missed|skipped)\b", t):
        return [{"tool": "get_college", "args": {}}]
    if re.search(r"\b(what should i worry|signals?|spider ?sense|anything urgent)\b", t):
        return [{"tool": "get_signals", "args": {}}]
    if re.search(r"\bhow much (?:have i |did i |i )?(?:spent|spend)\b|"
                 r"\b(?:my spending|budget status|my finances|finances)\b", t):
        return [{"tool": "get_finance", "args": {}}]
    if re.search(r"\b(my goals|goal progress|show (?:me )?(?:my )?goals)\b", t):
        return [{"tool": "get_goals", "args": {}}]
    if re.search(r"\b(my habits?|streaks?)\b", t) and not re.search(r"\b(did|done|completed|log)\b", t):
        return [{"tool": "get_habits", "args": {}}]
    if re.search(r"\b(my projects?|project status)\b", t):
        return [{"tool": "get_projects", "args": {}}]
    if re.search(r"\b(my applications?|internships?|career status)\b", t):
        return [{"tool": "get_career", "args": {}}]
    if re.search(r"\b(what am i learning|learning status|my topics?)\b", t):
        return [{"tool": "get_learning", "args": {}}]
    if re.search(r"\b(what do you remember|recall|remember about|search memory)\b", t):
        q = re.sub(r".*(remember about|recall|search memory( for)?)\s*", "", t).strip() or t
        return [{"tool": "search_memory", "args": {"query": q}}]
    if re.search(r"\b(my (tasks|todos)|what'?s on my list)\b", t):
        return [{"tool": "get_tasks", "args": {}}]

    # ---- notes ----
    m = re.search(r"\b(?:make a note|take a note|note down|jot down)\s*(?:that|:)?\s*(.+)", t)
    if m:
        return [{"tool": "create_note", "args": {"body": m.group(1).strip().capitalize()}}]

    # ---- memory ----
    if re.search(r"\b(remember that|remember|note that|i prefer|keep in mind)\b", t):
        cat = ("Preference" if re.search(r"\b(prefer|like|hate|always|never)\b", t)
               else "Idea" if "idea" in t
               else "Person" if re.search(r"\b(teammates?|friend|professor|prof\.?)\b", t)
               else "Note")
        cleaned = re.sub(r"^(jocasta[, ]*)?(please\s+)?(remember that|remember|note that|keep in mind that|keep in mind)\s*",
                         "", t).strip()
        return [{"tool": "save_memory",
                 "args": {"text": (cleaned[:1].upper() + cleaned[1:]) if cleaned else text, "category": cat}}]

    # ---- completion by name ----
    m = re.search(r"\b(?:i )?(?:just )?(?:finished|completed|done with|mark(?:ed)? (?:as )?done)\s+(.+)", t)
    if m:
        return [{"tool": "complete_task_by_name", "args": {"query": _strip(m.group(1), "the", "my")}}]

    # ---- habits ----
    m = re.search(r"\b(?:did|log(?:ged)?|completed)\s+(?:my\s+)?(.+?)\s*(?:habit|streak|today)\b", t)
    if m:
        return [{"tool": "log_habit", "args": {"habit": m.group(1).strip()}}]

    # ---- finance ----
    m = re.search(r"\b(spent|paid|bought .* for|expense of)\b", t)
    if m and _amount(t):
        amount = _amount(t)
        cat = "General"
        cm = re.search(r"\bon\s+([a-z ]+?)(?:\s+(?:today|yesterday|for)\b|$)", t)
        if cm:
            cat = cm.group(1).strip().title()
        when, span = parse_when(t)
        return [{"tool": "log_expense",
                 "args": {"amount": amount, "category": cat, "kind": "expense",
                          "note": _strip(text, span)[:120],
                          **({"date": when.isoformat()} if when else {})}}]
    m = re.search(r"\b(?:received|earned|got paid|income of)\b", t)
    if m and _amount(t):
        return [{"tool": "log_expense",
                 "args": {"amount": _amount(t), "category": "Income", "kind": "income",
                          "note": text[:120]}}]
    m = re.search(r"\bset (?:a )?budget (?:of |for )?(.+)", t)
    if m and _amount(t):
        cat_m = re.search(r"\bfor\s+([a-z ]+)", m.group(1))
        return [{"tool": "set_budget",
                 "args": {"category": (cat_m.group(1).strip().title() if cat_m else "General"),
                          "monthly_limit": _amount(t)}}]

    # ---- learning ----
    m = re.search(r"\b(?:studied|revised|practiced)\s+(.+)", t)
    if m:
        mins = re.search(r"(\d+)\s*(?:min|minute|hour|hr)", t)
        minutes = int(mins.group(1)) if mins else 30
        if mins and "hour" in mins.group(0) or (mins and "hr" in mins.group(0)):
            minutes *= 60
        topic = _strip(m.group(1), mins.group(0) if mins else "", "for", "about")
        return [{"tool": "log_study", "args": {"topic": topic, "minutes": minutes}}]
    m = re.search(r"\b(?:revise|study|review)\s+(.+)", t)
    if m:
        when, span = parse_when(t, default_hour=EVENING_HOUR)
        topic = _strip(m.group(1), span)
        if when:
            return [{"tool": "schedule_study", "args": {"topic": topic, "due_at": when.isoformat()}}]

    # ---- college ----
    m = re.search(r"\b(attended|went to|missed|skipped)\s+(.+)", t)
    if m:
        return [{"tool": "mark_attendance",
                 "args": {"course": _strip(m.group(2), "class", "lecture", "today"),
                          "attended": m.group(1) in ("attended", "went to")}}]
    m = re.search(r"\b(?:add|new|create)\s+(?:an?\s+)?assignment\s+(.+)", t)
    if m:
        when, span = parse_when(t, default_hour=23)
        course_m = re.search(r"\bfor\s+([a-z ]+?)(?:\s+due\b|$)", m.group(1))
        title = _strip(m.group(1), span, "due", course_m.group(0) if course_m else "")
        return [{"tool": "create_assignment",
                 "args": {"title": title[:1].upper() + title[1:],
                          "due_at": (when or _at_local(1, 23, 59)).isoformat(),
                          **({"course": course_m.group(1).strip()} if course_m else {})}}]

    # ---- goals ----
    m = re.search(r"\b(?:my goal is to|goal:|i want to)\s+(.+)", t)
    if m:
        when, span = parse_when(t)
        title = _strip(m.group(1), span)
        return [{"tool": "create_goal",
                 "args": {"title": title[:1].upper() + title[1:],
                          "horizon": "long" if re.search(r"\b(year|long ?term|eventually)\b", t) else "short",
                          **({"target_date": when.isoformat()} if when else {})}}]

    # ---- projects ----
    m = re.search(r"\badd\s+(.+?)\s+to\s+(?:the\s+)?(.+?)\s+project\b", t)
    if m:
        when, span = parse_when(t)
        return [{"tool": "create_project_task",
                 "args": {"project": m.group(2).strip(), "title": m.group(1).strip().capitalize(),
                          **({"due_at": when.isoformat()} if when else {})}}]

    # ---- reminders ----
    m = re.search(r"remind me to (.+)", t)
    if m or "don't forget" in t or "dont forget" in t:
        body = (m.group(1) if m else re.sub(r".*don'?t forget( to)?\s*", "", t)).strip()
        when, span = parse_when(body)
        if not when:
            when, span = parse_when(t)
        body = _strip(body, span, "on", "at")
        return [{"tool": "create_reminder",
                 "args": {"title": body[:1].upper() + body[1:],
                          "remind_at": (when or _at_local(1)).isoformat()}}]

    # ---- generic task, with whatever time we can find ----
    when, span = parse_when(t)
    title = _strip(text, span) or text.strip()
    title = title[:1].upper() + title[1:]
    if re.search(r"\b(buy|order|shampoo|grocery|groceries|shop)\b", t):
        return [{"tool": "create_task",
                 "args": {"title": title, "category": "Personal", "icon": "plus",
                          "meta": "Shopping", "due_at": (when or _at_local(0)).isoformat()}}]
    if re.search(r"\b(dsa|leetcode|practice|assignment|homework)\b", t):
        return [{"tool": "create_task",
                 "args": {"title": title, "category": "Learning", "icon": "learning",
                          "meta": "Learning Hub", "due_at": (when or _at_local(0, EVENING_HOUR)).isoformat()}}]
    if re.search(r"\b(gym|workout|run|walk|meditate)\b", t):
        return [{"tool": "create_task",
                 "args": {"title": title, "category": "Routine", "icon": "dumb",
                          "meta": "Routine", "due_at": (when or _at_local(0, 18)).isoformat()}}]
    return [{"tool": "create_task",
             "args": {"title": title, "category": "Personal",
                      "due_at": (when or _at_local(0)).isoformat()}}]
