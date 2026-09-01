"""Planner categories.

Planner shows five kinds of thing. Four of them are Tasks — the existing model
stays authoritative, so nothing is duplicated — and the fifth, Class, comes
from the timetable rather than the task queue.

Legacy `Task.category` values predate this vocabulary, so they are mapped
rather than migrated: rewriting historical rows to fit a newer label would be
a destructive change for a purely cosmetic gain.
"""
TASK = "Task"
STUDY = "Study"
PROJECT = "Project"
GOAL = "Goal"
PERSONAL = "Personal"
CLASS = "Class"          # from the timetable, never stored as a Task

#: What the Planner offers when creating something. Class is absent on purpose:
#: a class comes from the timetable, so it is scheduled against a course rather
#: than typed in here.
CATEGORIES = [TASK, STUDY, PROJECT, GOAL, PERSONAL]

#: Older values -> the current vocabulary.
LEGACY = {
    "college": TASK, "coursework": TASK, "task": TASK, "career": TASK,
    "learning": STUDY, "study": STUDY, "revision": STUDY,
    "project": PROJECT,
    "goal": GOAL,
    "personal": PERSONAL, "routine": PERSONAL, "habit": PERSONAL,
}

#: The source that materialised a task wins over its stored category — a task
#: created from a project is project work whatever its category says.
BY_SOURCE = {"project": PROJECT, "learning": STUDY, "assignment": TASK,
             "career": TASK, "goal": GOAL}


def canonical(category: str | None, source: str | None = None) -> str:
    if source and source in BY_SOURCE:
        return BY_SOURCE[source]
    return LEGACY.get((category or "").strip().lower(), TASK)


def normalise(category: str | None) -> str:
    """What to store when the client sends a category."""
    c = (category or "").strip()
    for known in CATEGORIES:
        if c.lower() == known.lower():
            return known
    return LEGACY.get(c.lower(), TASK)
