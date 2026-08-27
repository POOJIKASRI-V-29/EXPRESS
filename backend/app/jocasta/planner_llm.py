"""Optional LLM planner (Anthropic tool-calling).

If ANTHROPIC_API_KEY is set, JOCasta uses the model to choose tools. The model
returns tool_use blocks which we translate into the SAME intent dicts the rule
planner emits, so both paths converge on one validated executor.

The model is given tool *specs only* — no db session, no user rows, no ids it
didn't receive in this turn. Specs are generated from the pydantic argument
schemas in `schemas.py`, so an advertised tool can never drift from the one the
executor actually implements. Any failure falls back to the rule planner
upstream.
"""
from app.core.config import settings
from app.jocasta.tools import REGISTRY
from app.services.timeutils import local_now

# One line per tool, in the user's language rather than the schema's.
DESCRIPTIONS = {
    "create_task": "Create a task. Use for anything the user needs to do that isn't a class, assignment or reminder.",
    "update_task": "Change a task's title, priority or status. Needs the task's id.",
    "complete_task": "Mark a task complete by id.",
    "complete_task_by_name": "Mark a task complete when the user described it in words rather than giving an id.",
    "reschedule_task": "Move a task to a new date/time. Needs the task's id.",
    "find_task": "Look up one open task the user described, to get its id.",
    "create_reminder": "Create a time-based reminder; it also appears on the planner.",
    "save_memory": "Persist something personal and durable the user wants remembered (a preference, a fact, a person).",
    "search_memory": "Search saved memories.",
    "update_memory": "Edit a saved memory by id.",
    "delete_memory": "Delete a saved memory by id.",
    "get_memories": "List every saved memory.",
    "create_note": "Write a longer free-form note. Use for content, not for a preference to remember.",
    "search_notes": "Search notes by text or tag.",
    "create_assignment": "Add a coursework assignment with a due date; optionally name the course.",
    "mark_attendance": "Record that the user attended or missed a course's class.",
    "get_schedule": "Today's class timetable.",
    "get_college": "Attendance across courses, which are at risk, and the next exam.",
    "log_study": "Log study time already spent on a topic.",
    "schedule_study": "Put a future study block for a topic on the planner.",
    "create_topic": "Start tracking a new learning topic.",
    "get_learning": "Topics, their states, and total study time.",
    "create_project_task": "Add a task to a named project.",
    "get_projects": "List projects with status and completion.",
    "log_habit": "Mark a habit done for today.",
    "create_habit": "Start tracking a new habit.",
    "get_habits": "Habits with streaks and whether they're done today.",
    "log_expense": "Record money spent or received.",
    "set_budget": "Set a monthly spending cap for a category.",
    "get_finance": "This month's spending, income and budget status.",
    "create_goal": "Create a goal, optionally with a target date.",
    "update_goal": "Update a goal's progress or status, matched by name.",
    "get_goals": "Goals with progress derived from the work linked to them.",
    "get_career": "Internship applications and their stages.",
    "get_tasks": "All open tasks.",
    "get_deadlines": "Open assignment deadlines.",
    "get_progress": "Overall progress summary.",
    "get_signals": "Active Spider Sense signals.",
    "acknowledge_signal": "Dismiss a Spider Sense signal by id.",
    "get_plan_today": "Everything scheduled for today.",
    "propose_plan": ("Work out a realistic schedule across the next few days from the "
                     "user's real deadlines and free capacity. Use this for any request "
                     "to plan, reorganise, or catch up — it reasons over actual free "
                     "time rather than guessing."),
}


def _spec(name: str) -> dict:
    """Build one Anthropic tool spec from the tool's pydantic argument schema."""
    schema_cls, _fn = REGISTRY[name]
    schema = schema_cls.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {"name": name,
            "description": DESCRIPTIONS.get(name, name.replace("_", " ")),
            "input_schema": schema}


def tool_specs() -> list[dict]:
    return [_spec(name) for name in REGISTRY]


SYSTEM = (
    "You are JOCasta, the assistant inside EXPRESS, a student's life OS.\n\n"
    "You are given a brief describing the user's current state — today's "
    "schedule, upcoming deadlines, overdue work, free capacity, goals, and "
    "anything they asked you to remember. Reason over that brief, then call the "
    "tool(s) that fulfil the request.\n\n"
    "Rules:\n"
    "- If the user is asking a question, call a read-only get_* tool. Never "
    "create something in response to a question.\n"
    "- When the user names an existing thing in words (a task, topic, course, "
    "project, habit, goal), use the tool that accepts a name. Never invent an id.\n"
    "- Resolve relative dates against the current time below; pass absolute "
    "ISO 8601 datetimes.\n"
    "- For a planning request, use the capacity and deadline figures in the "
    "brief to choose realistic times. Schedule work into days that actually "
    "have free hours, and put preparation before the thing it prepares for.\n"
    "- Prefer the fewest calls that genuinely do the job. Several calls are "
    "correct when the user asked for a plan spanning several items.\n\n"
    "You never access data directly. The server validates every argument and "
    "executes tools for the authenticated user, and it will ask the user to "
    "confirm anything destructive before it runs."
)


def available() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def plan(text: str, brief: str = "") -> list[dict]:
    """Propose tool intents for `text`, reasoning over the supplied context brief.

    The brief is the bounded view assembled by `context.py` — never raw rows and
    never another user's data.
    """
    import anthropic  # imported lazily so the dep is optional
    client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.JOCASTA_TIMEOUT_SECONDS,
        max_retries=settings.JOCASTA_MAX_RETRIES,
    )
    now_local = local_now()
    system = (f"{SYSTEM}\n\nCurrent local time: {now_local.isoformat()} "
              f"({now_local.strftime('%A')}). Timezone: {settings.LOCAL_TZ}.")
    if brief:
        system += f"\n\n--- CURRENT STATE ---\n{brief}\n--- END STATE ---"

    resp = client.messages.create(
        model=settings.JOCASTA_MODEL,
        max_tokens=settings.JOCASTA_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": settings.JOCASTA_EFFORT},
        system=system,
        tools=tool_specs(),
        messages=[{"role": "user", "content": text}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("planner declined this request")
    calls = []
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name in REGISTRY:
            calls.append({"tool": block.name, "args": dict(block.input or {})})
    return calls
