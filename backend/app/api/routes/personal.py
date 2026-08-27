"""Personal: notes and habits.

Notes can anchor to another module's row (`ref_type`/`ref_id`), which is how a
project or course carries its own written context. Habit streaks are derived
from logs by the habits service — this router never trusts a stored counter.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Note, Habit, HabitLog, Course, Project, LearningTopic, Goal
from app.schemas.personal import NoteOut, NoteCreate, NoteUpdate, HabitCreate, HabitUpdate
from app.services import habits as habits_svc
from app.services.timeutils import local_today

router = APIRouter(prefix="/personal", tags=["personal"])

REF_MODELS = {"course": Course, "project": Project, "topic": LearningTopic, "goal": Goal}


def _own(db, model, row_id, user):
    row = db.query(model).filter(model.id == row_id, model.user_id == user.id).first()
    if not row:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


def _ref_label(db, user, note: Note) -> str:
    model = REF_MODELS.get(note.ref_type)
    if not model or not note.ref_id:
        return ""
    row = db.query(model).filter(model.id == note.ref_id, model.user_id == user.id).first()
    if not row:
        return ""
    return getattr(row, "name", None) or getattr(row, "title", "")


@router.get("")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    notes = (db.query(Note).filter(Note.user_id == user.id)
             .order_by(Note.pinned.desc(), Note.updated_at.desc()).all())
    habit_rows = habits_svc.summary(db, user)
    tags = sorted({t.strip() for n in notes for t in (n.tags or "").split(",") if t.strip()})
    return {
        "notes": [{"id": str(n.id), "title": n.title, "body": n.body, "tags": n.tags,
                   "pinned": n.pinned, "ref_type": n.ref_type,
                   "ref_id": str(n.ref_id) if n.ref_id else None,
                   "ref_label": _ref_label(db, user, n),
                   "updated_at": n.updated_at.isoformat()} for n in notes],
        "tags": tags,
        "habits": habit_rows,
        "habits_done_today": len([h for h in habit_rows if h["done_today"]]),
        "today": local_today().isoformat(),
    }


# ---- Notes ----
@router.get("/notes", response_model=list[NoteOut])
def list_notes(q: str | None = None, ref_type: str | None = None,
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Note).filter(Note.user_id == user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(Note.title.ilike(like) | Note.body.ilike(like) | Note.tags.ilike(like))
    if ref_type:
        query = query.filter(Note.ref_type == ref_type)
    return query.order_by(Note.pinned.desc(), Note.updated_at.desc()).all()


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(body: NoteCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = body.model_dump()
    if data.get("ref_type") and data["ref_type"] not in REF_MODELS:
        raise HTTPException(422, f"ref_type must be one of {sorted(REF_MODELS)}")
    if data.get("ref_id") and data.get("ref_type"):
        _own(db, REF_MODELS[data["ref_type"]], data["ref_id"], user)   # no cross-user anchors
    n = Note(user_id=user.id, **data)
    db.add(n); db.commit(); db.refresh(n)
    return n


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: str, body: NoteUpdate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    n = _own(db, Note, note_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(n, k, v)
    db.commit(); db.refresh(n)
    return n


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = _own(db, Note, note_id, user)
    db.delete(n); db.commit()
    return


# ---- Habits ----
@router.get("/habits")
def list_habits(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return habits_svc.summary(db, user)


@router.post("/habits", status_code=201)
def create_habit(body: HabitCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    h = Habit(user_id=user.id, **body.model_dump())
    db.add(h); db.commit()
    return habits_svc.summary(db, user)


@router.patch("/habits/{habit_id}")
def update_habit(habit_id: str, body: HabitUpdate, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    h = _own(db, Habit, habit_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(h, k, v)
    db.commit()
    return habits_svc.summary(db, user)


@router.post("/habits/{habit_id}/toggle")
def toggle_habit(habit_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Mark today done or undo it. The streak is recomputed from the logs, so
    un-ticking genuinely rolls the streak back instead of leaving a stale count."""
    h = _own(db, Habit, habit_id, user)
    today = local_today()
    existing = (db.query(HabitLog)
                .filter(HabitLog.user_id == user.id, HabitLog.habit_id == h.id,
                        HabitLog.on_date == today).first())
    if existing:
        db.delete(existing)
    else:
        db.add(HabitLog(user_id=user.id, habit_id=h.id, on_date=today))
    db.flush()
    habits_svc.recompute(db, user, h)
    db.commit()
    return habits_svc.summary(db, user)


@router.delete("/habits/{habit_id}", status_code=204)
def delete_habit(habit_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    h = _own(db, Habit, habit_id, user)
    db.delete(h); db.commit()
    return
