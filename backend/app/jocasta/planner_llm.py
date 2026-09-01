"""Optional LLM planner (Gemini function-calling).

If GEMINI_API_KEY is set, JOCasta uses the model to choose tools. The model
returns function calls which we translate into the SAME intent dicts the rule
planner emits, so both paths converge on one validated executor:

    Gemini → validated intent dict → safety → confirmation → executor → Postgres

The model is given tool *specs only* — no db session, no user rows, no ids it
didn't receive in this turn. Specs are generated from the pydantic argument
schemas in `schemas.py`, so an advertised tool can never drift from the one the
executor actually implements, and a name the model invents is dropped here
rather than reaching the executor. The SDK's automatic function calling is
switched off, so proposing a call and running one stay separate steps. Any
failure falls back to the rule planner upstream.
"""
from app.core.config import settings
from app.jocasta import llm
from app.jocasta.tools import REGISTRY
from app.services.timeutils import local_now

# One line per tool, in the user's language rather than the schema's.
DESCRIPTIONS = {
    "create_task": ("Create a task — something the user has to DO. Never use this for a "
                    "recurring college class: \"add DBMS class Monday at 9am\" is a timetable "
                    "slot (schedule_class), not a task."),
    "update_task": "Change a task's title, priority or status. Needs the task's id.",
    "complete_task": "Mark a task complete by id.",
    "complete_task_by_name": "Mark a task complete when the user described it in words rather than giving an id.",
    "reschedule_task": "Move a task to a new date/time. Needs the task's id.",
    "delete_task": "Delete a planner item the user named. Refuses when the name is ambiguous.",
    "reschedule_task_by_name": ("Move a planner item the user named to a new time, "
                                "without needing its id."),
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
    "mark_attendance": ("Record ONE class as attended or missed — \"I went to DBMS today\", "
                        "\"missed OS\". Both outcomes count as a class held. For exact totals "
                        "use set_attendance instead."),
    "set_attendance": ("Set a course's attendance to exact figures. Use this whenever the user "
                       "states both numbers — \"set my DBMS attendance to 42 out of 50\", "
                       "\"I've attended 42 of 50\". This writes; it is not a question."),
    "create_course": "Create a college course, optionally with its current attendance figures.",
    "update_course": "Change a course's name, code, faculty, room or credits. Not attendance — use set_attendance for that.",
    "delete_course": "Delete a course the user named, with its modules, concepts and timetable slots.",
    "schedule_class": ("Add a recurring weekly college class to the timetable for a course. "
                       "This is THE tool for \"add <course> class <weekday> at <time>\" — it "
                       "repeats every week and shows on the planner on that day. "
                       "day_of_week is 0=Monday..6=Sunday; times are 24h \"HH:MM\"."),
    "reschedule_class": "Move a course's weekly class to a different day, time or room.",
    "delete_class": "Remove a course's weekly class from the timetable.",
    "get_course": "One course in full: attendance, modules, concepts and progress.",
    "set_course_drive": "Save a Google Drive folder or file link on a course.",
    "complete_topic": "Tick (or untick) a concept inside a course module the user named in words.",
    "get_schedule": "Today's class timetable.",
    "get_college": ("Read-only: attendance across courses, which are at risk, and the next exam. "
                    "Only for questions. Never use it when the user is telling you a figure to set."),
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


#: JSON Schema keywords Gemini acts on. Anything else pydantic emits (titles,
#: defaults) is prompt noise at best and a rejected request at worst, so the
#: schema is reduced to this set rather than passed through raw.
_SCHEMA_KEYS = {"type", "description", "properties", "required", "items",
                "enum", "format", "nullable"}


def _clean(node):
    """Reduce a pydantic JSON schema to the subset Gemini understands.

    The only structural rewrite is optional fields: pydantic renders `X | None`
    as `anyOf: [X, null]`, which Gemini has no equivalent for, so the non-null
    branch is lifted out and marked nullable. Defaults are dropped — pydantic
    applies them when the executor validates the arguments, so advertising them
    would only invite the model to restate them.
    """
    if isinstance(node, list):
        return [_clean(n) for n in node]
    if not isinstance(node, dict):
        return node

    if "anyOf" in node:
        branches = [b for b in node["anyOf"]
                    if not (isinstance(b, dict) and b.get("type") == "null")]
        nullable = len(branches) < len(node["anyOf"])
        merged = _clean(branches[0]) if branches else {"type": "string"}
        if nullable:
            merged["nullable"] = True
        if node.get("description"):
            merged.setdefault("description", node["description"])
        return merged

    out = {}
    for key, value in node.items():
        if key not in _SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            # These keys are argument names, not schema keywords — recurse into
            # the values but keep every name.
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key == "required":
            out[key] = list(value)          # names again, not sub-schemas
        else:
            out[key] = _clean(value)
    return out


def _spec(name: str) -> dict:
    """Build one Gemini function declaration from the tool's argument schema."""
    schema_cls, _fn = REGISTRY[name]
    schema = _clean(schema_cls.model_json_schema())
    schema["type"] = "object"

    spec = {"name": name,
            "description": DESCRIPTIONS.get(name, name.replace("_", " "))}
    # A read-only tool takes no arguments; declaring an empty object as its
    # parameters is rejected, so the field is omitted entirely.
    if schema.get("properties"):
        spec["parameters_json_schema"] = schema
    return spec


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
    return llm.configured()


def plan(text: str, brief: str = "", referent: dict | None = None) -> list[dict]:
    """Propose tool intents for `text`, reasoning over the supplied context brief.

    The brief is the bounded view assembled by `context.py` — never raw rows and
    never another user's data.
    """
    from google.genai import types   # imported lazily so the dep is optional

    now_local = local_now()
    system = (f"{SYSTEM}\n\nCurrent local time: {now_local.isoformat()} "
              f"({now_local.strftime('%A')}). Timezone: {settings.LOCAL_TZ}.")
    if referent and referent.get("id"):
        # What "it"/"that" refers to, resolved from the last thing actually
        # acted on. Given as a fact so the model reschedules the right record
        # instead of guessing or falling back to a listing.
        system += (f"\n\nThe user is referring back to something. \"it\"/\"that\" "
                   f"means the item titled \"{referent.get('title') or 'the last one'}\" "
                   f"with id {referent['id']}. Use that id directly.")
        if referent.get("due_at"):
            # Without this, "move it to 8pm" resolves 8pm against *today* and
            # silently drags a tomorrow item back a day.
            system += (f" It is currently scheduled for {referent['due_at']}. "
                       f"If the user gives only a time and no day, keep that "
                       f"item's existing date and change only the time.")
    if brief:
        system += f"\n\n--- CURRENT STATE ---\n{brief}\n--- END STATE ---"

    try:
        resp = llm.client().models.generate_content(
            model=llm.model(),
            contents=[{"role": "user", "parts": [{"text": text}]}],
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=settings.JOCASTA_MAX_TOKENS,
                tools=[types.Tool(function_declarations=tool_specs())],
                # The SDK must not run anything. It only reports what the model
                # proposed; the executor decides what actually happens.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True),
            ),
        )
    except Exception as exc:
        llm.note_failure(exc, where="planner")
        raise

    declined = llm.refusal_reason(resp)
    if declined:
        raise RuntimeError(f"planner declined this request ({declined})")

    calls = []
    for call in (resp.function_calls or []):
        # A name outside the registry is dropped rather than forwarded: the
        # executor should never be asked to look up a tool the model invented.
        if call.name in REGISTRY:
            calls.append({"tool": call.name, "args": dict(call.args or {})})
    llm.note_ok()
    return calls
