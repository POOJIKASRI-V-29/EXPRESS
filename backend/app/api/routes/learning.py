"""Learning: topics, logged study sessions, and skills.

Logging a session is the only thing that moves a topic's recency, and
scheduling a study block routes through `materialize` so the block lands in the
same Task queue Planner and Home read.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import LearningTopic, LearningSession, Skill, Course, Task
from app.schemas.learning import (TopicOut, TopicCreate, TopicUpdate, SessionCreate,
                                  ScheduleStudy, SkillOut, SkillCreate, SkillUpdate)
from app.services import materialize, spider_sense
from app.services.timeutils import now, local_today, start_of_local_day, as_utc

router = APIRouter(prefix="/learning", tags=["learning"])

STATES = ["not_started", "learning", "practicing", "strong", "needs_revision"]


def _own(db, model, row_id, user):
    row = db.query(model).filter(model.id == row_id, model.user_id == user.id).first()
    if not row:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


@router.get("")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    topics = (db.query(LearningTopic).filter(LearningTopic.user_id == user.id)
              .order_by(LearningTopic.area, LearningTopic.name).all())
    skills = db.query(Skill).filter(Skill.user_id == user.id).order_by(Skill.pct.desc()).all()
    sessions = (db.query(LearningSession).filter(LearningSession.user_id == user.id)
                .order_by(LearningSession.started_at.desc()).all())
    courses = {c.id: c.name for c in db.query(Course).filter(Course.user_id == user.id).all()}

    mins_by_topic: dict = {}
    for s in sessions:
        mins_by_topic[s.topic_id] = mins_by_topic.get(s.topic_id, 0) + (s.minutes or 0)

    week_start = start_of_local_day(-6)
    week_minutes = sum(s.minutes or 0 for s in sessions if as_utc(s.started_at) >= week_start)
    scheduled = {t.topic_id for t in db.query(Task).filter(
        Task.user_id == user.id, Task.status == "open", Task.topic_id.isnot(None)).all()}

    return {
        "areas": sorted({t.area for t in topics}),
        "states": STATES,
        "week_minutes": week_minutes,
        "total_minutes": sum(s.minutes or 0 for s in sessions),
        "session_count": len(sessions),
        "topics": [{"id": str(t.id), "name": t.name, "area": t.area, "state": t.state,
                    "progress": t.progress, "minutes": mins_by_topic.get(t.id, 0),
                    "course": courses.get(t.course_id, ""),
                    "scheduled": t.id in scheduled,
                    "last_reviewed_at": t.last_reviewed_at.isoformat() if t.last_reviewed_at else None}
                   for t in topics],
        "skills": [{"id": str(s.id), "name": s.name, "level": s.level, "pct": s.pct} for s in skills],
        "recent_sessions": [{"id": str(s.id), "topic_id": str(s.topic_id), "minutes": s.minutes,
                             "note": s.note, "started_at": s.started_at.isoformat(),
                             "topic": next((t.name for t in topics if t.id == s.topic_id), "")}
                            for s in sessions[:10]],
    }


@router.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(body: TopicCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = LearningTopic(user_id=user.id, **body.model_dump())
    db.add(t); db.commit(); db.refresh(t)
    spider_sense.scan(db, user)
    return t


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: str, body: TopicUpdate, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    t = _own(db, LearningTopic, topic_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    db.commit(); db.refresh(t)
    spider_sense.scan(db, user)
    return t


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = _own(db, LearningTopic, topic_id, user)
    db.delete(t); db.commit()
    return


@router.post("/topics/{topic_id}/sessions", status_code=201)
def log_session(topic_id: str, body: SessionCreate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    """Log study time. Progress advances with time invested and the topic's
    recency updates, which is what clears a stale-revision signal."""
    t = _own(db, LearningTopic, topic_id, user)
    started = body.started_at or now()
    s = LearningSession(user_id=user.id, topic_id=t.id, minutes=body.minutes,
                        note=body.note, started_at=started)
    db.add(s)
    t.last_reviewed_at = started
    t.progress = min(100, (t.progress or 0) + max(1, round(body.minutes / 10)))
    if t.state == "not_started":
        t.state = "learning"
    elif t.state == "needs_revision" and t.progress >= 70:
        t.state = "practicing"
    db.commit(); db.refresh(s)
    spider_sense.scan(db, user)
    return {"id": str(s.id), "topic_id": str(t.id), "minutes": s.minutes,
            "topic_progress": t.progress, "topic_state": t.state,
            "started_at": s.started_at.isoformat()}


@router.post("/topics/{topic_id}/schedule", status_code=201)
def schedule_study(topic_id: str, body: ScheduleStudy, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    """Put a study block for this topic on the Planner."""
    t = _own(db, LearningTopic, topic_id, user)
    task = materialize.task_for_topic(db, t, body.due_at, body.minutes)
    db.commit(); db.refresh(task)
    return {"task_id": str(task.id), "title": task.title, "due_at": task.due_at.isoformat()}


# ---- Skills ----
@router.post("/skills", response_model=SkillOut, status_code=201)
def create_skill(body: SkillCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = Skill(user_id=user.id, **body.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return s


@router.patch("/skills/{skill_id}", response_model=SkillOut)
def update_skill(skill_id: str, body: SkillUpdate, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    s = _own(db, Skill, skill_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    s.level = max(1, min(5, round((s.pct or 0) / 20) or 1))
    db.commit(); db.refresh(s)
    return s


@router.delete("/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = _own(db, Skill, skill_id, user)
    db.delete(s); db.commit()
    return
