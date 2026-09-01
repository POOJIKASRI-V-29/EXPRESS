"""Timetable extraction — one interpreter of an attachment's text.

Reading the file is `services.attachments`; this only turns text into proposed
classes. `parse` reads line by line. Timetable layouts vary enormously; this
handles the common line-oriented shape (a day heading, then rows carrying a
time range and a course) and reports what it could not read rather than
guessing. Nothing here writes: it produces *proposals* that the caller shows
the user before anything reaches the database.

Only fields actually present in the text are populated. A missing room stays
empty; it is never invented.
"""
import re
from dataclasses import asdict, dataclass, field

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_INDEX = {d.lower(): i for i, d in enumerate(DAYS)}
DAY_INDEX.update({d.lower()[:3]: i for i, d in enumerate(DAYS)})

# 10:00-11:00 · 10.00 – 11.00 · 9:00 AM - 10:30 AM · 10-11
TIME_RANGE = re.compile(
    r"(?P<sh>\d{1,2})[:.](?P<sm>\d{2})\s*(?P<sap>am|pm)?\s*[-–—to]{1,3}\s*"
    r"(?P<eh>\d{1,2})[:.](?P<em>\d{2})\s*(?P<eap>am|pm)?",
    re.I)
TIME_RANGE_LOOSE = re.compile(
    r"\b(?P<sh>\d{1,2})\s*(?P<sap>am|pm)?\s*[-–—]\s*(?P<eh>\d{1,2})\s*(?P<eap>am|pm)\b",
    re.I)

DAY_TOKEN = re.compile(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b", re.I)
# A room is claimed *before* a course code, because "Room AB-201" looks exactly
# like a code otherwise — and a mislabelled room becomes a wrong course.
# Room names are often two tokens ("TT 402", "Block C 12"). The second token is
# only taken when it is numeric, so this can't swallow the course name that
# usually follows.
ROOM_LABELLED = re.compile(
    r"\b(?:room|rm|hall|lab|block|venue)\s*[:.]?\s*"
    r"(?P<room>[A-Za-z0-9-]{1,10}(?:\s+\d{1,4}[A-Za-z]?)?)\b", re.I)
ROOM_BARE = re.compile(r"\b(?P<room>[A-Z]{1,3}[- ]\d{2,4}[A-Z]?)\b")

# CS303, AI310, 18CSC303J — an alphanumeric code.
COURSE_CODE_ALNUM = re.compile(r"\b(?=[A-Z0-9-]{4,12}\b)(?=[A-Z-]*\d)[A-Z][A-Z0-9-]{3,11}\b")
# DBMS, OS, DSA — an all-caps abbreviation sitting beside a longer course name.
COURSE_CODE_ALPHA = re.compile(r"\b([A-Z]{2,6})\b")
# Words that are capitalised in timetables but are not course codes.
NOT_A_CODE = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN", "AM", "PM",
              "ROOM", "LAB", "HALL", "TBA", "TBD", "NIL", "AND", "THE"}
SECTION = re.compile(r"\b(?:section|sec|batch|group)\s*[:.]?\s*([A-Za-z0-9-]{1,6})\b", re.I)
FACULTY = re.compile(r"\b(?:prof|dr|mr|ms|mrs)\.?\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)?)")

NOISE = re.compile(
    r"^\s*(page\s*\d+|timetable|time\s*table|semester|academic year|"
    r"generated on|printed on|university|college|department)\b", re.I)


@dataclass
class ProposedClass:
    day_of_week: int
    day: str
    start_time: str          # "HH:MM"
    end_time: str            # "HH:MM"
    course: str
    code: str = ""
    room: str = ""
    faculty: str = ""
    section: str = ""
    source_line: str = ""

    def key(self) -> tuple:
        """Identity for duplicate detection: a slot is the same slot if it is the
        same day, the same start time and the same course."""
        return (self.day_of_week, self.start_time, (self.code or self.course).strip().lower())

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- parsing
def _to_24h(hour: str, minute: str, ampm: str | None, other_ampm: str | None = None) -> str:
    h, m = int(hour), int(minute)
    ap = (ampm or other_ampm or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    elif not ap and h < 8:
        # A college day rarely starts before 8; 1:00-2:00 means the afternoon.
        h += 12
    return f"{h % 24:02d}:{m:02d}"


def _clean_course(line: str, spans: list[tuple[int, int]]) -> str:
    """Whatever is left of a line once the recognised parts are removed."""
    out = list(line)
    for start, end in spans:
        for i in range(start, min(end, len(out))):
            out[i] = " "
    text = "".join(out)
    text = re.sub(r"[|·•\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—:,.")
    return text.strip()


def parse(text: str) -> tuple[list[ProposedClass], list[str]]:
    """Return (proposed classes, lines that looked like entries but didn't parse)."""
    proposals: list[ProposedClass] = []
    skipped: list[str] = []
    current_day: int | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or NOISE.match(line):
            continue

        # A line that is only a day name sets the context for what follows.
        bare_day = DAY_TOKEN.fullmatch(line.strip(" :-–—"))
        if bare_day:
            current_day = DAY_INDEX.get(bare_day.group(1).lower()[:3])
            continue

        spans: list[tuple[int, int]] = []

        # A day named inline overrides the running context for this line only.
        line_day = current_day
        m_day = DAY_TOKEN.search(line)
        if m_day:
            idx = DAY_INDEX.get(m_day.group(1).lower()[:3])
            if idx is not None:
                line_day = idx
                spans.append(m_day.span())

        m_time = TIME_RANGE.search(line) or TIME_RANGE_LOOSE.search(line)
        if not m_time:
            continue
        spans.append(m_time.span())

        g = m_time.groupdict()
        start = _to_24h(g["sh"], g.get("sm") or "00", g.get("sap"), g.get("eap"))
        end = _to_24h(g["eh"], g.get("em") or "00", g.get("eap"), g.get("sap"))

        if line_day is None:
            skipped.append(line)          # a time with no day is unusable
            continue

        # Room first — see ROOM_LABELLED above.
        room = ""
        m_room = ROOM_LABELLED.search(line) or ROOM_BARE.search(line)
        if m_room:
            room = m_room.group("room").strip()
            spans.append(m_room.span())

        code = ""
        m_code = COURSE_CODE_ALNUM.search(line)
        if m_code and m_code.group(0) != room:
            code = m_code.group(0)
            spans.append(m_code.span())
        else:
            # An all-caps abbreviation only counts as a code when the line also
            # carries a longer name — otherwise "DBMS" alone is the course.
            for m_alpha in COURSE_CODE_ALPHA.finditer(line):
                token = m_alpha.group(1)
                if token in NOT_A_CODE or token == room.upper():
                    continue
                rest = (line[:m_alpha.start()] + line[m_alpha.end():])
                if re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{3,}", rest):
                    code = token
                    spans.append(m_alpha.span())
                break

        faculty = ""
        m_fac = FACULTY.search(line)
        if m_fac:
            faculty = m_fac.group(1).strip()
            spans.append(m_fac.span())

        section = ""
        m_sec = SECTION.search(line)
        if m_sec:
            section = m_sec.group(1).strip()
            spans.append(m_sec.span())

        course = _clean_course(line, spans)
        if not course and code:
            course = code
        if not course or len(course) < 2:
            skipped.append(line)
            continue

        proposals.append(ProposedClass(
            day_of_week=line_day, day=DAYS[line_day],
            start_time=start, end_time=end,
            course=course, code=code, room=room,
            faculty=faculty, section=section, source_line=line))

    # The same slot can appear twice in a PDF (e.g. a repeated header block).
    seen, unique = set(), []
    for p in proposals:
        if p.key() in seen:
            continue
        seen.add(p.key())
        unique.append(p)
    return unique, skipped





# ---------------------------------------------------------------- importing
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def match_course(courses, proposal: ProposedClass):
    """Find the user's existing course for a proposed slot.

    Matches on code first (the most reliable signal), then on an exact
    normalised name, then on containment — but only when exactly one course
    matches. An ambiguous match returns nothing, so the caller asks instead of
    attaching a class to the wrong course.
    """
    if proposal.code:
        code = _norm(proposal.code)
        exact = [c for c in courses if _norm(c.code) == code]
        if len(exact) == 1:
            return exact[0]

    name = _norm(proposal.course)
    if not name:
        return None
    exact = [c for c in courses if _norm(c.name) == name]
    if len(exact) == 1:
        return exact[0]

    partial = [c for c in courses
               if _norm(c.name) and (_norm(c.name) in name or name in _norm(c.name))]
    if len(partial) == 1:
        return partial[0]

    # Initials, so "DBMS" can reach "Database Management Systems" only when
    # nothing else competes.
    if proposal.code and len(proposal.code) <= 6:
        code = _norm(proposal.code)
        initials = [c for c in courses
                    if "".join(w[0] for w in _norm(c.name).split() if w) == code]
        if len(initials) == 1:
            return initials[0]
    return None


def plan_import(db, user, proposals: list[ProposedClass], replace: bool = False) -> dict:
    """Work out what an import would actually do. Writes nothing.

    Returns the additions, the entries already present, the entries whose course
    is unknown, and — for a replace — exactly which existing slots would be
    removed, so the user can see the cost before agreeing to it.
    """
    from app.models import Class, Course

    courses = db.query(Course).filter(Course.user_id == user.id).all()
    by_id = {c.id: c for c in courses}
    existing = db.query(Class).filter(Class.user_id == user.id).all()

    def slot_key(cl):
        course = by_id.get(cl.course_id)
        label = (course.code or course.name) if course else ""
        return (cl.day_of_week, cl.start_time, _norm(label))

    existing_keys = {slot_key(c) for c in existing}

    to_add, duplicates, unmatched = [], [], []
    for p in proposals:
        course = match_course(courses, p)
        if not course:
            unmatched.append(p)
            continue
        key = (p.day_of_week, p.start_time, _norm(course.code or course.name))
        row = {**p.as_dict(), "course_id": str(course.id), "matched_course": course.name}
        (duplicates if key in existing_keys else to_add).append(row)

    return {
        "to_add": to_add,
        "duplicates": duplicates,
        "unmatched": [p.as_dict() for p in unmatched],
        "unmatched_names": sorted({p.code or p.course for p in unmatched}),
        "existing_count": len(existing),
        "would_remove": len(existing) if replace else 0,
        "replace": replace,
    }


def apply_import(db, user, proposals: list[ProposedClass], replace: bool = False) -> dict:
    """Create the real Class rows. Only called after the user has confirmed.

    Entries whose course is unknown are skipped rather than inventing a course
    — creating one is a separate, explicit request.
    """
    from app.models import Class, Course

    plan = plan_import(db, user, proposals, replace=replace)
    removed = 0
    if replace:
        for cl in db.query(Class).filter(Class.user_id == user.id).all():
            db.delete(cl)
            removed += 1
        db.flush()

    courses = {str(c.id): c for c in db.query(Course).filter(Course.user_id == user.id).all()}
    added = 0
    # After a replace the slate is empty, so previous duplicates are additions.
    rows = plan["to_add"] + (plan["duplicates"] if replace else [])
    for row in rows:
        course = courses.get(row["course_id"])
        if not course:
            continue
        db.add(Class(user_id=user.id, course_id=course.id,
                     day_of_week=row["day_of_week"],
                     start_time=row["start_time"], end_time=row["end_time"],
                     room=row.get("room") or course.room or ""))
        added += 1
    db.commit()
    return {"added": added, "removed": removed,
            "skipped_duplicates": 0 if replace else len(plan["duplicates"]),
            "skipped_unmatched": len(plan["unmatched"]),
            "unmatched_names": plan["unmatched_names"]}


def summarize(plan: dict, skipped_lines: list[str] | None = None) -> str:
    """What the user reads before deciding."""
    add, dupes, unmatched = plan["to_add"], plan["duplicates"], plan["unmatched_names"]
    lines = []

    if add:
        lines.append(f"I found {len(add)} class(es) to add:")
        for row in add[:12]:
            room = f" · {row['room']}" if row.get("room") else ""
            lines.append(f"  • {row['day']} {row['start_time']}–{row['end_time']} "
                         f"{row['matched_course']}{room}")
        if len(add) > 12:
            lines.append(f"  • …and {len(add) - 12} more")
    else:
        lines.append("Nothing new to add.")

    if dupes and not plan["replace"]:
        lines.append(f"{len(dupes)} already on your timetable — I'll skip those.")
    if unmatched:
        lines.append("No matching course for: " + ", ".join(unmatched[:6])
                     + ". I won't create courses on my own — say the word and I will.")
    if plan["replace"] and plan["existing_count"]:
        lines.append(f"Replacing removes your current {plan['existing_count']} slot(s) first.")
    if skipped_lines:
        lines.append(f"{len(skipped_lines)} line(s) had a time but nothing I could read as a class.")
    return "\n".join(lines)
