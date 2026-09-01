"""Course workspace: attendance arithmetic and derived progress.

Two rules shape this module:

* **Attendance is counted, never typed.** The truth is a pair — classes
  attended and classes held. The percentage is always computed from them, so it
  can be explained ("23 of 28") rather than merely asserted. `Course.attendance`
  is kept as a cached percent so list endpoints stay cheap, and every write path
  here recomputes it; nothing else may set it.

* **Course progress is counted too.** It is completed topics over total topics.
  There is no stored progress field, so it cannot drift.
"""
from app.models import Class, Course, CourseModule, CourseTopic
from app.services.timeutils import now


#: Timetable day names, 0 = Monday (matches Class.day_of_week).
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def pct(attended: int | None, total: int | None) -> int:
    """Attendance percentage, or 0 when no classes have been held.

    0 held classes means "no data", which the UI renders as "—" rather than a
    0% risk the user cannot act on.
    """
    total = total or 0
    if total <= 0:
        return 0
    return round((attended or 0) / total * 100)


def recompute(course: Course) -> Course:
    """Refresh the cached percent. Call after any change to the counters."""
    course.attendance = pct(course.attended_classes, course.total_classes)
    return course


def set_counts(course: Course, attended: int, total: int) -> Course:
    """Manual correction. Clamped so the pair can never be nonsensical."""
    total = max(0, int(total))
    attended = max(0, min(int(attended), total))
    course.total_classes, course.attended_classes = total, attended
    return recompute(course)


def mark(course: Course, attended: bool) -> Course:
    """Record one held class.

    A missed class still counts as held — that is precisely why attendance
    falls. Incrementing only the numerator would make missing a class free.
    """
    course.total_classes = (course.total_classes or 0) + 1
    if attended:
        course.attended_classes = (course.attended_classes or 0) + 1
    return recompute(course)


def unmark(course: Course, attended: bool) -> Course:
    """Undo one held class — the counterpart to `mark`, for mis-taps."""
    course.total_classes = max(0, (course.total_classes or 0) - 1)
    if attended:
        course.attended_classes = max(0, (course.attended_classes or 0) - 1)
    course.attended_classes = min(course.attended_classes or 0, course.total_classes)
    return recompute(course)


def topic_counts(db, user, course_id) -> tuple[int, int]:
    """(completed, total) topics across every module of a course."""
    rows = (db.query(CourseTopic)
            .join(CourseModule, CourseTopic.module_id == CourseModule.id)
            .filter(CourseModule.course_id == course_id,
                    CourseTopic.user_id == user.id).all())
    return len([t for t in rows if t.done]), len(rows)


def progress(db, user, course_id) -> int:
    done, total = topic_counts(db, user, course_id)
    return round(done / total * 100) if total else 0


def next_module(db, user, course_id) -> str:
    """The first module with unfinished topics — "what's next" on the card."""
    mods = (db.query(CourseModule)
            .filter(CourseModule.course_id == course_id, CourseModule.user_id == user.id)
            .order_by(CourseModule.order).all())
    for m in mods:
        topics = (db.query(CourseTopic)
                  .filter(CourseTopic.module_id == m.id,
                          CourseTopic.user_id == user.id).all())
        if topics and any(not t.done for t in topics):
            return m.name
    return ""


def summarize(db, user, course: Course) -> dict:
    """The card shape used by the College list."""
    done, total_topics = topic_counts(db, user, course.id)
    module_count = (db.query(CourseModule)
                    .filter(CourseModule.course_id == course.id,
                            CourseModule.user_id == user.id).count())
    return {
        "id": str(course.id), "name": course.name, "code": course.code,
        "faculty": course.faculty, "room": course.room,
        "attended_classes": course.attended_classes or 0,
        "total_classes": course.total_classes or 0,
        "attendance": pct(course.attended_classes, course.total_classes),
        "has_attendance_data": (course.total_classes or 0) > 0,
        # 0 means "not recorded" rather than "worth nothing", so the UI hides it.
        "credits": course.credits or 0,
        "drive_url": course.drive_url or "",
        "modules": module_count,
        "topics_done": done, "topics_total": total_topics,
        "progress": round(done / total_topics * 100) if total_topics else 0,
        "next_module": next_module(db, user, course.id),
    }


def workspace(db, user, course: Course) -> dict:
    """The full course page: summary plus its modules and their topics."""
    base = summarize(db, user, course)
    mods = (db.query(CourseModule)
            .filter(CourseModule.course_id == course.id, CourseModule.user_id == user.id)
            .order_by(CourseModule.order).all())
    topics_by_module: dict = {}
    if mods:
        rows = (db.query(CourseTopic)
                .filter(CourseTopic.module_id.in_([m.id for m in mods]),
                        CourseTopic.user_id == user.id)
                .order_by(CourseTopic.order).all())
        for t in rows:
            topics_by_module.setdefault(t.module_id, []).append(t)

    base["module_list"] = [{
        "id": str(m.id), "name": m.name, "order": m.order,
        "topics": [{"id": str(t.id), "name": t.name, "done": bool(t.done)}
                   for t in topics_by_module.get(m.id, [])],
        "done": len([t for t in topics_by_module.get(m.id, []) if t.done]),
        "total": len(topics_by_module.get(m.id, [])),
    } for m in mods]

    # The weekly slots for this course, so the course page can manage its own
    # timetable instead of sending the user elsewhere to do it.
    slots = (db.query(Class)
             .filter(Class.course_id == course.id, Class.user_id == user.id)
             .order_by(Class.day_of_week, Class.start_time).all())
    base["classes"] = [{
        "id": str(cl.id), "day_of_week": cl.day_of_week,
        "day_label": DAY_LABELS[cl.day_of_week % 7],
        "start_time": cl.start_time, "end_time": cl.end_time, "room": cl.room or "",
    } for cl in slots]
    return base


def set_topic_done(db, topic: CourseTopic, done: bool) -> CourseTopic:
    topic.done = done
    topic.completed_at = now() if done else None
    return topic
