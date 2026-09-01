"""Talking, suggesting, and asking for clarification — the non-writing paths.

Three things happen here, none of which touch the database except to read:

* **Conversation.** Greetings and acknowledgements get a short, human reply.
  JOCasta does not perform a personality; it answers and, where genuinely
  useful, offers the one thing worth doing next — taken from real data.
* **Suggestion.** "What should I do?" is answered by looking at actual free
  capacity, real deadlines and unfinished concepts, and naming the single most
  defensible option with the reason attached. If there is nothing to recommend,
  it says so rather than inventing an errand.
* **Clarification.** When a message plausibly asks for a change but names
  nothing to change, JOCasta asks. Guessing costs the user a junk record;
  asking costs one sentence.
"""
from datetime import timedelta

import re

from app.jocasta import context as ctx_mod
from app.jocasta.intent import Intent
from app.models import Course, CourseModule, CourseTopic, Goal, LearningTopic
from app.services.timeutils import hours_until, local_now, now

# ---------------------------------------------------------------- junk filter
# Titles that read as a message *to* an assistant rather than a thing to do.
# These exist because an earlier bug filed ordinary conversation as tasks, and
# recommending "Hi how are you" as tonight's priority is worse than saying
# nothing. Deliberately conservative: it only skips a row for a *suggestion*,
# never deletes anything, and anything that might be real work is kept.
_JUNK_EXACT = {"hello", "hi", "hey", "yo", "hiya", "ok", "okay", "cool", "nice",
               "thanks", "thank you", "test", "testing", "asdf", "qwerty", "x", "n/a"}
_JUNK_SIGNALS = re.compile(
    r"\bjocasta\b"                                  # addressed to the assistant
    r"|^(hi|hey|hello|yo|hiya)\b"                     # opens like a greeting
    r"|^(can|could|would|will)\s+you\b"              # phrased as a request to it
    r"|^(how|what|why|when|who)\s+(are|is|do|can)\b" # phrased as a question
    r"|\btest task\b|\bdummy\b|\bplaceholder\b",
    re.I)


def looks_like_junk(title: str) -> bool:
    """Would recommending this embarrass the assistant?"""
    t = (title or "").strip()
    if not t or len(t) < 3:
        return True
    if t.lower().rstrip("?!. ") in _JUNK_EXACT:
        return True
    if t.rstrip().endswith("?"):          # a question is not a piece of work
        return True
    return bool(_JUNK_SIGNALS.search(t))


def _first_name(user) -> str:
    return (user.name or "").split(" ")[0] or "there"


def _time_of_day() -> str:
    h = local_now().hour
    if h < 5:
        return "late"
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    if h < 22:
        return "evening"
    return "late"


# ---------------------------------------------------------------- suggestion
def _incomplete_concepts_for(db, user, course_id, limit=3) -> list[str]:
    rows = (db.query(CourseTopic)
            .join(CourseModule, CourseTopic.module_id == CourseModule.id)
            .filter(CourseModule.course_id == course_id,
                    CourseTopic.user_id == user.id,
                    CourseTopic.done == False)  # noqa: E712
            .order_by(CourseTopic.order).limit(limit).all())
    return [t.name for t in rows]


def _study_options(db, user) -> list[dict]:
    """Real things worth studying, most defensible first.

    Course concepts outrank loose topics because they attach to a course the
    user is actually graded on; a topic explicitly flagged for revision
    outranks one that is merely unfinished.
    """
    out = []
    courses = {c.id: c for c in db.query(Course).filter(Course.user_id == user.id).all()}
    if courses:
        rows = (db.query(CourseTopic, CourseModule)
                .join(CourseModule, CourseTopic.module_id == CourseModule.id)
                .filter(CourseTopic.user_id == user.id,
                        CourseTopic.done == False)  # noqa: E712
                .order_by(CourseModule.order, CourseTopic.order).limit(20).all())
        for topic, module in rows:
            course = courses.get(module.course_id)
            out.append({"what": topic.name, "where": course.name if course else module.name,
                        "kind": "concept"})

    for tp in (db.query(LearningTopic)
               .filter(LearningTopic.user_id == user.id,
                       LearningTopic.state == "needs_revision").limit(6).all()):
        out.insert(0, {"what": tp.name, "where": tp.area, "kind": "revision"})

    for tp in (db.query(LearningTopic)
               .filter(LearningTopic.user_id == user.id,
                       LearningTopic.state.in_(("learning", "practicing"))).limit(6).all()):
        out.append({"what": tp.name, "where": tp.area, "kind": "topic"})
    return out


def _active_goals(db, user) -> list[str]:
    return [g.title for g in db.query(Goal)
            .filter(Goal.user_id == user.id, Goal.status == "active").limit(5).all()]


def _due_phrase(hours: float) -> str:
    """How far off something is, in words that stay true when it has passed.

    `hours_until` is negative for anything overdue, so formatting it directly
    produced "due in about -66h".
    """
    if hours < 0:
        late = abs(hours)
        return ("it was due about " + (f"{round(late)}h ago" if late < 48
                                       else f"{round(late / 24)} days ago"))
    if hours < 48:
        return f"it's due in about {round(hours)}h"
    return f"it's due in {round(hours / 24)} days"


def recommend(db, user, minutes_free: int | None = None, focus: str = "") -> dict:
    """The single most defensible thing to do next, with its reason.

    Everything cited is a real record. Malformed rows are skipped rather than
    recommended, and when nothing meaningful exists the honest answer is to say
    so — an assistant that always finds something urgent is just noise.
    """
    ctx = ctx_mod.build(db, user, "what should i do now",
                        slices=["today", "deadlines", "overdue", "capacity", "signals"])
    deadlines = ctx.get("deadlines", {})
    overdue = ctx.get("overdue", {})
    capacity = (ctx.get("capacity", {}).get("days") or [{}])[0]
    free = minutes_free if minutes_free is not None else capacity.get("free_minutes", 0)
    base = {"free": free, "concepts": [], "goals": []}

    assignments = [a for a in (deadlines.get("assignments") or [])
                   if not looks_like_junk(a.get("title", ""))]
    exams = deadlines.get("exams") or []

    def concepts_for(title: str) -> list[str]:
        for c in db.query(Course).filter(Course.user_id == user.id).all():
            hay = (title or "").lower()
            if c.name.lower().split()[0] in hay or (c.code or "").lower() in hay:
                rows = (db.query(CourseTopic)
                        .join(CourseModule, CourseTopic.module_id == CourseModule.id)
                        .filter(CourseModule.course_id == c.id,
                                CourseTopic.user_id == user.id,
                                CourseTopic.done == False)  # noqa: E712
                        .order_by(CourseTopic.order).limit(3).all())
                return [t.name for t in rows]
        return []

    # A study question is answered with study, not with the nearest chore.
    if focus == "study":
        soonest = None
        if assignments:
            soonest = ("assignment", assignments[0], assignments[0]["hours_away"])
        if exams and (not soonest or exams[0]["hours_away"] < soonest[2]):
            soonest = ("exam", exams[0], exams[0]["hours_away"])
        if soonest:
            kind, item, hours = soonest
            return {**base, "kind": kind, "headline": item["title"],
                    "why": _due_phrase(hours),
                    "minutes": item.get("minutes_of_work"),
                    "concepts": concepts_for(item["title"])}

        options = _study_options(db, user)
        if options:
            top = options[0]
            why = ("you flagged it for revision" if top["kind"] == "revision"
                   else f"it's still unticked in {top['where']}" if top["kind"] == "concept"
                   else f"it's an active {top['where']} topic")
            return {**base, "kind": "study", "headline": top["what"], "why": why,
                    "minutes": None,
                    "concepts": [o["what"] for o in options[1:3]]}

        return {**base, "kind": "no_study", "headline": None, "why": "",
                "minutes": None, "goals": _active_goals(db, user)}

    # General "what should I do" — overdue work first, but never junk.
    late = [t for t in (overdue.get("tasks") or []) if not looks_like_junk(t.get("title", ""))]
    if late:
        item = late[0]
        return {**base, "kind": "overdue", "headline": item["title"],
                "why": f"it was due {item['days_late']} day(s) ago", "minutes": None}

    soonest = None
    if assignments:
        soonest = ("assignment", assignments[0], assignments[0]["hours_away"])
    if exams and (not soonest or exams[0]["hours_away"] < soonest[2]):
        soonest = ("exam", exams[0], exams[0]["hours_away"])
    if soonest:
        kind, item, hours = soonest
        return {**base, "kind": kind, "headline": item["title"],
                "why": _due_phrase(hours),
                "minutes": item.get("minutes_of_work"),
                "concepts": concepts_for(item["title"])}

    today_tasks = [t for t in (ctx.get("today", {}).get("tasks") or [])
                   if not looks_like_junk(t.get("title", ""))]
    if today_tasks:
        t = today_tasks[0]
        return {**base, "kind": "task", "headline": t["title"],
                "why": "it's next on today's plan", "minutes": t.get("minutes")}

    return {**base, "kind": "clear", "headline": None, "why": "", "minutes": None,
            "goals": _active_goals(db, user)}


def suggestion_reply(db, user, minutes_free: int | None = None,
                     focus: str = "") -> str:
    r = recommend(db, user, minutes_free, focus=focus)
    free_txt = (f"You've got about {round(r['free'] / 60, 1)}h free"
                if r["free"] and r["free"] > 30 else "")

    if r["kind"] == "no_study":
        goals = r.get("goals") or []
        if goals:
            listed = ", ".join(goals[:3])
            return (f"Nothing's scheduled to study tonight. Your active goals are "
                    f"{listed} — pick one and I'll help you plan it.")
        return ("Nothing's scheduled to study and I don't have any learning goals or "
                "course concepts to go on yet. Add a goal or some course concepts and "
                "I'll have something to suggest.")

    if not r["headline"]:
        goals = r.get("goals") or []
        tail = (f" Your active goals are {', '.join(goals[:3])} if you want to get ahead."
                if goals else "")
        return (((free_txt + " and ") if free_txt else "")
                + "nothing is pressing — no deadlines close and nothing overdue." + tail)

    bits = []
    if free_txt:
        bits.append(free_txt + ".")
    if r["kind"] == "study":
        bits.append(f"I'd spend it on {r['headline']} — {r['why']}.")
    elif r["kind"] == "overdue":
        bits.append(f"I'd clear {r['headline']} — {r['why']}.")
    else:
        sentence = f"I'd start with {r['headline']} — {r['why']}"
        if r["minutes"]:
            sentence += f", about {r['minutes']} minutes of work"
        bits.append(sentence + ".")

    if r["concepts"]:
        listed = ", ".join(r["concepts"][:2])
        verb = "are" if len(r["concepts"]) > 1 else "is"
        tail = ("still unticked on it." if r["kind"] != "study"
                else f"{verb} worth a look after.")
        bits.append(f"{listed} {tail}" if r["kind"] != "study"
                    else f"{listed} {verb} next after that.")
    return " ".join(bits)


# ---------------------------------------------------------------- conversation
#: Said on the way out, not on the way in — these get a send-off, not a nag.
_FAREWELL = re.compile(r"\b(good ?night|night night|goodnight|nighty|bye|goodbye|"
                       r"see you|see ya|later|i'?m off|signing off|that'?s me)\b")


def conversation_reply(db, user, text: str) -> str:
    """A short human reply. Offers the next useful thing only when there is one."""
    t = (text or "").strip().lower()
    name = _first_name(user)

    if _FAREWELL.search(t):
        # Ending the day is the wrong moment to list what is outstanding.
        return "Night, " + name + ". I'll keep an eye on things."

    if re.search(r"^(thanks?|thank you|ta|cheers|nice|great|cool|perfect|awesome|"
                 r"ok|okay|sure|yep|yeah|alright|got it|never ?mind|nvm)\b", t):
        return "Any time."

    if re.search(r"\b(tired|exhausted|knackered|shattered|burnt ?out|burned ?out)\b", t):
        r = recommend(db, user)
        if r["kind"] == "clear":
            return ("Then rest — nothing's pressing and nothing's overdue. "
                    "It'll all still be here tomorrow.")
        return (f"Fair enough. If you do one thing, make it {r['headline']} — {r['why']}. "
                "Otherwise it can wait.")

    if re.search(r"\b(stressed|anxious|overwhelmed|lost|stuck|behind)\b", t):
        r = recommend(db, user)
        if r["kind"] == "clear":
            return "Nothing's actually overdue or close — you're in better shape than it feels."
        return (f"Let's make it smaller: just {r['headline']} — {r['why']}. "
                "Ignore the rest for now.")

    if re.search(r"\b(who are you|what are you|what can you do)\b", t):
        return ("I'm JOCasta. I can see your planner, courses, learning, projects and "
                "goals — so ask me what's on, what's urgent, or what to do next, and "
                "tell me when things change and I'll keep them up to date.")

    if re.search(r"\b(how are you|how are u|how'?s it going|what'?s up|whats up|sup)\b", t):
        r = recommend(db, user)
        if r["kind"] == "clear":
            return "Good — and so are you, by the look of it. Nothing pressing right now."
        return f"All running. {r['headline']} is the thing I'd keep an eye on — {r['why']}."

    # Greeting.
    part = _time_of_day()
    opener = {"morning": "Morning", "afternoon": "Afternoon",
              "evening": "Evening", "late": "Still up"}[part]
    r = recommend(db, user)
    if r["kind"] == "clear":
        return f"{opener}, {name}. Nothing urgent on the board — what do you need?"
    return f"{opener}, {name}. {r['headline']} is the one I'd watch — {r['why']}. What do you need?"


# ---------------------------------------------------------------- clarification
CLARIFY_PROMPTS = {
    Intent.CREATE: "What would you like me to add, and when?",
    Intent.DELETE: "Which one should I delete?",
    Intent.RESCHEDULE: "Which one should I move, and to when?",
    Intent.EDIT: "Which one do you want changed, and what should it say?",
    Intent.COMPLETE: "Which one have you finished?",
    Intent.CLARIFY: "What would you like me to do?",
}


def clarify_reply(intent: Intent, text: str = "") -> str:
    return CLARIFY_PROMPTS.get(intent, "I'm not sure what you'd like me to do — "
                                       "could you say a bit more?")


def unknown_reply(text: str) -> str:
    """Deliberately does not act.

    An unrecognised statement is far more often conversation than a silent
    instruction to file a record, so JOCasta asks instead of guessing.
    """
    return ("I'm not sure what to do with that. You can ask me what's on, what's "
            "urgent or what to work on next — or tell me to add, move or finish "
            "something and I'll take care of it.")


# ---------------------------------------------------------------- context brief
#: Turns that need no context at all. Handing someone their outstanding work at
#: "good night" or "thanks" is the over-contextualising this guards against.
_LIGHT = re.compile(
    r"^\s*(thanks|thank you|ta|cheers|ok|okay|k|cool|nice|great|perfect|awesome|"
    r"got it|sure|yes|yeah|yep|no|nope|alright|never ?mind|nvm|"
    r"good ?night|night|bye|goodbye|see (you|ya)|later|i'?m off)\b")


def is_light_turn(text: str) -> bool:
    """Should this turn be answered with no context at all?"""
    return bool(_LIGHT.match((text or "").strip().lower())) or bool(
        _FAREWELL.search((text or "").strip().lower()))


def state_brief(db, user, focus: str = "") -> str:
    """A compact, factual snapshot for the conversational layer.

    Deliberately small. It is the *only* thing JOCasta is allowed to state as
    fact, so it must be accurate — every line is read from real records — but
    it must not be the whole database, or replies start reciting inventory.
    """
    slices = ["today", "deadlines", "overdue", "signals", "memory"]
    if focus in ("plan", "study"):
        slices.append("capacity")
    if focus == "study":
        slices += ["learning", "goals"]

    ctx = ctx_mod.build(db, user, "", slices=slices)
    lines = [ctx_mod.summarize(ctx)]

    if focus == "study":
        options = _study_options(db, user)[:5]
        if options:
            lines.append("COULD STUDY: " + "; ".join(
                f"{o['what']} ({o['where']})" for o in options))
        goals = _active_goals(db, user)
        if goals:
            lines.append("ACTIVE GOALS: " + ", ".join(goals))

    return "\n".join(l for l in lines if l.strip())
