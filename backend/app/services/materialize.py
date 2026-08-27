"""Connected data flow: domain entities generate a canonical Task.

Assignment -> Task, ProjectTask -> Task, LearningTopic -> Task, Application ->
Task. The Task is what surfaces in Planner / Home / Up Next, so scheduling
logic lives in exactly one place and every module reaches the same queue.
"""
from app.models import Task, Assignment, ProjectTask, LearningTopic, Application, Internship


def task_for_assignment(db, assignment: Assignment) -> Task:
    existing = db.query(Task).filter(Task.assignment_id == assignment.id).first()
    if existing:
        existing.title = assignment.title
        existing.due_at = assignment.due_at
        existing.est_minutes = assignment.est_minutes
        existing.priority = assignment.priority
        existing.status = assignment.status
        return existing
    t = Task(
        user_id=assignment.user_id, title=assignment.title, category="College",
        due_at=assignment.due_at, est_minutes=assignment.est_minutes,
        priority=assignment.priority, status=assignment.status, icon="college",
        meta="Assignment", source="assignment", assignment_id=assignment.id,
    )
    db.add(t)
    return t


def task_for_project_task(db, pt: ProjectTask) -> Task:
    existing = db.query(Task).filter(Task.project_task_id == pt.id).first()
    if existing:
        existing.title = pt.title
        existing.due_at = pt.due_at
        existing.status = pt.status
        return existing
    t = Task(
        user_id=pt.user_id, title=pt.title, category="Project", due_at=pt.due_at,
        priority="med", status=pt.status, icon="projects", meta="Project task",
        source="project", project_task_id=pt.id,
    )
    db.add(t)
    return t


def task_for_topic(db, topic: LearningTopic, due_at, minutes: int = 45) -> Task:
    """Scheduling a study block for a topic puts it in the same queue as
    everything else, so Planner and Home see it without knowing about Learning."""
    existing = (db.query(Task)
                .filter(Task.topic_id == topic.id, Task.status == "open").first())
    if existing:
        existing.due_at = due_at
        existing.est_minutes = minutes
        return existing
    t = Task(
        user_id=topic.user_id, title=f"Study: {topic.name}", category="Learning",
        due_at=due_at, est_minutes=minutes, priority="med", icon="learning",
        meta=topic.area, source="learning", topic_id=topic.id,
    )
    db.add(t)
    return t


def task_for_application(db, app_row: Application, internship: Internship) -> Task | None:
    """An application with a deadline becomes a dated task; without one there is
    nothing to schedule, so nothing is invented."""
    if not app_row.deadline:
        return None
    existing = db.query(Task).filter(Task.application_id == app_row.id).first()
    label = f"{app_row.stage.upper()} — {internship.company}"
    if existing:
        existing.title = label
        existing.due_at = app_row.deadline
        return existing
    t = Task(
        user_id=app_row.user_id, title=label, category="Career", due_at=app_row.deadline,
        est_minutes=60, priority="high", icon="career", meta=internship.role,
        source="career", application_id=app_row.id,
    )
    db.add(t)
    return t
