"""Memory: everything JOCasta has been told to remember, under the user's control.

`save_memory` writes here through the JOCasta tool layer; this router is the
matching human surface — list, filter, search, edit, pin and delete. Memories
saved by the assistant carry `source="jocasta"`, so it is always visible who
wrote a given line.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Memory, JOCastaConversation
from app.schemas.memory import MemoryOut, MemoryCreate, MemoryUpdate

router = APIRouter(prefix="/memory", tags=["memory"])

CATEGORIES = ["Preference", "Project", "Idea", "Note", "Person", "Fact"]


def _own(db, memory_id, user) -> Memory:
    m = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user.id).first()
    if not m:
        raise HTTPException(404, "Memory not found")
    return m


@router.get("")
def overview(q: str | None = None, category: str | None = None,
             db: Session = Depends(get_db), user=Depends(get_current_user)):
    """The Memory page payload: the (optionally filtered) list plus counts that
    always describe the whole store, not the current filter."""
    all_rows = db.query(Memory).filter(Memory.user_id == user.id).all()
    query = db.query(Memory).filter(Memory.user_id == user.id)
    if q:
        query = query.filter(Memory.text.ilike(f"%{q}%"))
    if category and category != "All":
        query = query.filter(Memory.category == category)
    rows = query.order_by(Memory.pinned.desc(), Memory.created_at.desc()).all()

    counts = {c: len([m for m in all_rows if m.category == c]) for c in CATEGORIES}
    for m in all_rows:                      # categories that arrived from elsewhere
        counts.setdefault(m.category, 0)
        if m.category not in CATEGORIES:
            counts[m.category] = len([x for x in all_rows if x.category == m.category])

    return {
        "categories": CATEGORIES,
        "counts": counts,
        "total": len(all_rows),
        "from_jocasta": len([m for m in all_rows if m.source == "jocasta"]),
        "pinned": len([m for m in all_rows if m.pinned]),
        "query": q or "",
        "filter": category or "All",
        "memories": [{"id": str(m.id), "text": m.text, "category": m.category,
                      "source": m.source, "pinned": m.pinned,
                      "created_at": m.created_at.isoformat(),
                      "updated_at": m.updated_at.isoformat()} for m in rows],
    }


@router.get("/list", response_model=list[MemoryOut])
def list_memory(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return (db.query(Memory).filter(Memory.user_id == user.id)
            .order_by(Memory.created_at.desc()).all())


@router.get("/search", response_model=list[MemoryOut])
def search_memory(q: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return (db.query(Memory).filter(Memory.user_id == user.id, Memory.text.ilike(f"%{q}%"))
            .order_by(Memory.created_at.desc()).all())


@router.post("", response_model=MemoryOut, status_code=201)
def add_memory(body: MemoryCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = Memory(user_id=user.id, source="manual", **body.model_dump())
    db.add(m); db.commit(); db.refresh(m)
    return m


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: str, body: MemoryUpdate, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    m = _own(db, memory_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit(); db.refresh(m)
    return m


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = _own(db, memory_id, user)
    db.delete(m); db.commit()
    return


@router.get("/conversations")
def conversations(limit: int = 50, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """JOCasta's transcript — what was said, and which tools ran."""
    rows = (db.query(JOCastaConversation)
            .filter(JOCastaConversation.user_id == user.id)
            .order_by(JOCastaConversation.created_at.desc())
            .limit(max(1, min(limit, 200))).all())
    return [{"id": str(r.id), "role": r.role, "content": r.content,
             "tool_name": r.tool_name, "created_at": r.created_at.isoformat()}
            for r in reversed(rows)]
