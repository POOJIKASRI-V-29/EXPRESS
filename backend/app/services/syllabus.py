"""Course structure extraction — a second interpreter of attachment text.

Turns a syllabus into proposed modules and their concepts. Like the timetable
extractor it only proposes; the caller previews and the user confirms before
anything is written.

Deliberately conservative: a line becomes a module only when it looks like a
unit heading, and a concept only when it sits under one. Anything ambiguous is
left out and reported, because a syllabus imported with invented structure is
worse than one imported partially.
"""
import re

# "Unit I", "Unit 1 — Fundamentals", "Module 3:", "Chapter 2 -", "UNIT-IV"
MODULE = re.compile(
    r"^\s*(?:unit|module|chapter|part|section)\s*[-–—:.]?\s*"
    r"(?P<num>[IVXLC]+|\d{1,2})\s*[-–—:.)]?\s*(?P<title>.*)$",
    re.I)

# A bulleted or numbered concept line.
BULLET = re.compile(r"^\s*(?:[-•*·–—]|\(?[a-z0-9]{1,3}[.)])\s+(?P<text>.{2,120})$", re.I)

# Headings and furniture that are not course content.
NOISE = re.compile(
    r"^\s*(page\s*\d+|syllabus|course\s+(outline|plan|code|title)|credits?|"
    r"prerequisite|text\s*books?|references?|outcomes?|objectives?|"
    r"total\s+hours|l\s*t\s*p\s*c|semester|university|department)\b", re.I)

COURSE_TITLE = re.compile(
    r"^\s*(?:course\s*(?:title|name)\s*[:.-]\s*)(?P<name>.{3,80})$", re.I)
COURSE_CODE = re.compile(
    r"^\s*(?:course\s*code\s*[:.-]\s*)(?P<code>[A-Z0-9-]{3,12})\s*$", re.I)

SPLIT = re.compile(r"\s*[;,]\s+|\s+[-–—]\s+")


def _clean(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text or "").strip(" -–—:.,;")
    return text


def parse(text: str) -> dict:
    """Return {course_name, course_code, modules:[{name, topics:[…]}], skipped}."""
    modules: list[dict] = []
    skipped: list[str] = []
    course_name = ""
    course_code = ""
    current: dict | None = None

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        m = COURSE_TITLE.match(line)
        if m and not course_name:
            course_name = _clean(m.group("name"))
            continue
        m = COURSE_CODE.match(line)
        if m and not course_code:
            course_code = _clean(m.group("code"))
            continue

        m = MODULE.match(line)
        if m:
            title = _clean(m.group("title"))
            label = f"Unit {m.group('num').upper()}" if not title else \
                f"Unit {m.group('num').upper()} — {title}"
            current = {"name": label, "topics": []}
            modules.append(current)
            continue

        if NOISE.match(line):
            continue

        if current is None:
            continue      # content before any unit heading is not a concept

        m = BULLET.match(line)
        body = _clean(m.group("text")) if m else _clean(line)
        if not body or len(body) < 3:
            continue
        # A long prose line is a description, not a concept list.
        if not m and len(body) > 120:
            skipped.append(line)
            continue

        # Syllabus lines often pack several concepts onto one line.
        parts = [p for p in (_clean(x) for x in SPLIT.split(body)) if len(p) >= 3]
        for part in (parts if len(parts) > 1 else [body]):
            if len(part) <= 90:
                current["topics"].append(part)
            else:
                skipped.append(part)

    modules = [m for m in modules if m["topics"] or len(modules) <= 12]
    return {"course_name": course_name, "course_code": course_code,
            "modules": modules, "skipped": skipped[:20]}


def summarize(parsed: dict, course_label: str = "") -> str:
    modules = parsed["modules"]
    total = sum(len(m["topics"]) for m in modules)
    head = f"I found {len(modules)} module(s) and {total} concept(s)"
    head += f" for {course_label}." if course_label else "."
    lines = [head]
    for m in modules[:8]:
        preview = ", ".join(m["topics"][:4])
        more = f" +{len(m['topics']) - 4} more" if len(m["topics"]) > 4 else ""
        lines.append(f"  • {m['name']}" + (f": {preview}{more}" if preview else " (no concepts)"))
    if len(modules) > 8:
        lines.append(f"  • …and {len(modules) - 8} more module(s)")
    if parsed["skipped"]:
        lines.append(f"{len(parsed['skipped'])} line(s) were too long or unclear to use.")
    return "\n".join(lines)
