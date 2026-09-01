"""Deciding what an attachment is for.

The user attaches a file and says something. Neither half is sufficient on its
own: "add this to my planner" could mean a timetable or a list of deadlines,
and a syllabus PDF sent with no instruction could mean "read it" or "build the
course". So the decision uses both — what the instruction asks for, and what
the content actually looks like — and when the two don't settle it, JOCasta
asks rather than picking.

Nothing here writes. Every operation that would change the database returns a
preview plus a signed confirmation token; the write happens only in `confirm`.
"""
import logging
import re
from dataclasses import dataclass

from app.core.logging import log
from app.jocasta import safety
from app.services import syllabus as syllabus_svc, timetable as timetable_svc
from app.services.attachments import Attachment

logger = logging.getLogger("express.jocasta.attachment")

# ---- what the instruction asks for ---------------------------------------
WANT_TIMETABLE = re.compile(
    r"\b(time ?table|class(es)? schedule|my classes|these classes|lecture schedule)\b")
WANT_COURSE = re.compile(
    r"\b(syllabus|course (structure|outline|from|modules?)|create .*course|"
    r"build .*course|modules?|units?|concepts?|topics?)\b")
WANT_PLANNER = re.compile(
    r"\b(planner|schedule this|add .*(deadlines?|dates?)|to my (planner|calendar))\b")
WANT_ANSWER = re.compile(
    r"\b(what does|what'?s in|summar[iy]|explain|tell me about|read (this|it)|"
    r"any(thing)? (in|about)|when is|does (this|it) say)\b")
WANT_ACTION = re.compile(
    r"\b(add|import|create|update|replace|build|set up|put)\b")


@dataclass
class Signals:
    """What the content looks like, independent of what was asked."""
    classes: int
    modules: int
    concepts: int
    course_name: str
    course_code: str

    @property
    def looks_like_timetable(self) -> bool:
        return self.classes >= 3

    @property
    def looks_like_syllabus(self) -> bool:
        return self.modules >= 2 and self.concepts >= 3


def analyse(attachment: Attachment) -> tuple[Signals, list, dict]:
    """Run every extractor once and report what each found."""
    classes, _skipped = timetable_svc.parse(attachment.text)
    outline = syllabus_svc.parse(attachment.text)
    concepts = sum(len(m["topics"]) for m in outline["modules"])
    return (
        Signals(classes=len(classes), modules=len(outline["modules"]),
                concepts=concepts, course_name=outline["course_name"],
                course_code=outline["course_code"]),
        classes, outline,
    )


def decide(instruction: str, signals: Signals) -> str:
    """Pick the operation: timetable | course | answer | ask.

    The instruction leads. Content only decides when the instruction is silent
    about what to do, and only when it is clearly one thing rather than the
    other — otherwise the answer is to ask.
    """
    t = (instruction or "").strip().lower()

    if WANT_TIMETABLE.search(t):
        return "timetable" if signals.classes else "empty_timetable"
    if WANT_COURSE.search(t):
        return "course" if signals.modules else "empty_course"
    if WANT_ANSWER.search(t) and not WANT_ACTION.search(t):
        return "answer"

    wants_action = bool(WANT_ACTION.search(t) or WANT_PLANNER.search(t))
    if wants_action:
        if signals.looks_like_timetable and not signals.looks_like_syllabus:
            return "timetable"
        if signals.looks_like_syllabus and not signals.looks_like_timetable:
            return "course"
        if signals.looks_like_timetable and signals.looks_like_syllabus:
            return "ask"          # genuinely could be either
        return "ask" if (signals.classes or signals.modules) else "answer"

    # No action asked for: describe what is there and offer the options.
    return "answer"


# ---------------------------------------------------------------- previews
def _describe(attachment: Attachment, signals: Signals) -> str:
    bits = [f"I read {attachment.filename} ({attachment.pages} page(s))."]
    found = []
    if signals.classes:
        found.append(f"{signals.classes} class slot(s)")
    if signals.modules:
        found.append(f"{signals.modules} module(s) with {signals.concepts} concept(s)")
    if found:
        bits.append("It looks like it contains " + " and ".join(found) + ".")
    else:
        bits.append("I couldn't recognise a timetable or a syllabus structure in it.")
    return " ".join(bits)


def answer(attachment: Attachment, signals: Signals) -> str:
    """Read-only. Says what is in the file and what can be done with it.

    Without a language model configured JOCasta cannot answer arbitrary
    questions about a document, so it does not pretend to — it reports what it
    recognised and offers the operations it can actually perform.
    """
    lines = [_describe(attachment, signals)]
    offers = []
    if signals.classes:
        offers.append('say "add this timetable" and I\'ll put the classes on your Planner')
    if signals.modules:
        offers.append('say "create the course from this" and I\'ll build the modules')
    if offers:
        lines.append("If you want, " + "; or ".join(offers) + ".")
    else:
        lines.append("Here's the start of it: " + attachment.preview(280))
    return "\n".join(lines)


def build(db, user, instruction: str, attachment: Attachment) -> dict:
    """Interpret instruction + content. Returns an orchestrator-shaped turn."""
    signals, classes, outline = analyse(attachment)
    op = decide(instruction, signals)
    log(logger, logging.INFO, "attachment interpreted", user_id=str(user.id),
        filename=attachment.filename, op=op, classes=signals.classes,
        modules=signals.modules)

    if op == "answer":
        return {"kind": "talk", "reply": answer(attachment, signals)}

    if op == "empty_timetable":
        return {"kind": "talk", "reply":
                _describe(attachment, signals) + "\nI look for lines with a day and a "
                "time range — if yours is a grid or an image, I can't read it."}

    if op == "empty_course":
        return {"kind": "talk", "reply":
                _describe(attachment, signals) + "\nI look for unit or module headings "
                "with concepts listed under them."}

    if op == "ask":
        return {"kind": "talk", "reply":
                _describe(attachment, signals) + "\nWhich would you like — add the "
                "classes to your Planner, or build the course modules?"}

    if op == "timetable":
        replace = bool(re.search(r"\b(replace|overwrite|wipe|start over|clear)\b",
                                 (instruction or "").lower()))
        plan = timetable_svc.plan_import(db, user, classes, replace=replace)
        summary = timetable_svc.summarize(plan)
        if not plan["to_add"] and not replace:
            return {"kind": "talk", "reply": summary + "\n\nSo there's nothing to add."}

        count = len(plan["to_add"]) if not replace else len(classes)
        actions = [{"tool": "import_timetable",
                    "risk": safety.SENSITIVE if replace else safety.WRITE,
                    "summary": (f"{r['day']} {r['start_time']}–{r['end_time']} "
                                f"{r['matched_course']}"
                                + (f" · {r['room']}" if r.get("room") else ""))}
                   for r in (plan["to_add"] or plan["duplicates"])[:12]]
        if replace and plan["existing_count"]:
            actions.insert(0, {"tool": "import_timetable", "risk": safety.SENSITIVE,
                               "summary": f"remove your current {plan['existing_count']} slot(s)"})
        return {
            "kind": "confirm",
            "reply": summary + "\n\n" + (
                f"Replace your timetable with these {count} class(es)?" if replace
                else f"Add {count} class(es) to your Planner?"),
            "actions": actions,
            "reason": ("Replacing removes what's there first." if replace
                       else "These will be added to your Planner."),
            "risk": safety.SENSITIVE if replace else safety.WRITE,
            "payload": {"kind": "timetable_apply",
                        "entries": [c.as_dict() for c in classes], "replace": replace},
            "modules": ["planner", "college"],
        }

    if op == "course":
        from app.models import Course
        courses = db.query(Course).filter(Course.user_id == user.id).all()
        label = outline["course_name"] or outline["course_code"]
        target = None
        if label:
            norm = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
            hits = [c for c in courses
                    if norm and (norm in (c.name or "").lower()
                                 or (c.code or "").lower() == outline["course_code"].lower())]
            target = hits[0] if len(hits) == 1 else None
        # An instruction naming a course wins over whatever the file says.
        for c in courses:
            if c.name and c.name.lower() in (instruction or "").lower():
                target = c
                break
            if c.code and re.search(rf"\b{re.escape(c.code.lower())}\b",
                                    (instruction or "").lower()):
                target = c
                break

        if not target:
            names = ", ".join(c.name for c in courses[:6]) or "none yet"
            return {"kind": "talk", "reply":
                    syllabus_svc.summarize(outline, label) +
                    f"\n\nWhich course should these go on? You have: {names}. "
                    "I won't create a course on my own — say the name and I will."}

        total = sum(len(m["topics"]) for m in outline["modules"])
        return {
            "kind": "confirm",
            "reply": syllabus_svc.summarize(outline, target.name) +
                     f"\n\nAdd these to {target.name}?",
            "actions": [{"tool": "create_structure", "risk": safety.WRITE,
                         "summary": f"{m['name']} — {len(m['topics'])} concept(s)"}
                        for m in outline["modules"][:12]],
            "reason": f"{len(outline['modules'])} module(s) and {total} concept(s) "
                      f"will be added to {target.name}.",
            "risk": safety.WRITE,
            "payload": {"kind": "course_structure", "course_id": str(target.id),
                        "modules": outline["modules"]},
            "modules": ["college"],
        }

    return {"kind": "talk", "reply": answer(attachment, signals)}
