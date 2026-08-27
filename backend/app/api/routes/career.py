"""Career: internships and their applications.

An application with a deadline materialises into a dated Task, so interview
prep and OA deadlines compete for time in the Planner alongside coursework
instead of living in a separate list nobody looks at.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Internship, Application, Task, Note
from app.schemas.career import (InternshipOut, InternshipCreate, InternshipUpdate,
                                ApplicationCreate, ApplicationUpdate)
from app.services import materialize, spider_sense

router = APIRouter(prefix="/career", tags=["career"])

STAGES = ["applied", "oa", "interview", "result"]
STAGE_TO_STATUS = {"applied": "Applied", "oa": "In Progress",
                   "interview": "Interviewing", "result": "Result"}


def _own(db, model, row_id, user):
    row = db.query(model).filter(model.id == row_id, model.user_id == user.id).first()
    if not row:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


@router.get("")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    internships = (db.query(Internship).filter(Internship.user_id == user.id)
                   .order_by(Internship.created_at).all())
    apps = db.query(Application).filter(Application.user_id == user.id).all()
    by_intern: dict = {}
    for a in apps:
        by_intern.setdefault(a.internship_id, []).append(a)

    return {
        "stages": STAGES,
        "pipeline": {s: len([a for a in apps if a.stage == s]) for s in STAGES},
        "internships": [{
            "id": str(i.id), "company": i.company, "role": i.role, "status": i.status,
            "location": i.location, "link": i.link,
            "applications": [{"id": str(a.id), "stage": a.stage, "notes": a.notes,
                              "deadline": a.deadline.isoformat() if a.deadline else None}
                             for a in sorted(by_intern.get(i.id, []),
                                             key=lambda x: STAGES.index(x.stage)
                                             if x.stage in STAGES else 9)],
        } for i in internships],
    }


@router.post("/internships", response_model=InternshipOut, status_code=201)
def create_internship(body: InternshipCreate, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    i = Internship(user_id=user.id, **body.model_dump())
    db.add(i); db.commit(); db.refresh(i)
    return i


@router.patch("/internships/{internship_id}", response_model=InternshipOut)
def update_internship(internship_id: str, body: InternshipUpdate, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    i = _own(db, Internship, internship_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(i, k, v)
    db.commit(); db.refresh(i)
    return i


@router.delete("/internships/{internship_id}", status_code=204)
def delete_internship(internship_id: str, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    i = _own(db, Internship, internship_id, user)
    db.delete(i); db.commit()
    return


@router.post("/applications", status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    it = _own(db, Internship, body.internship_id, user)
    a = Application(user_id=user.id, **body.model_dump())
    db.add(a); db.flush()
    it.status = STAGE_TO_STATUS.get(a.stage, it.status)
    materialize.task_for_application(db, a, it)
    db.commit(); db.refresh(a)
    spider_sense.scan(db, user)
    return {"id": str(a.id), "internship_id": str(a.internship_id), "stage": a.stage,
            "deadline": a.deadline.isoformat() if a.deadline else None, "notes": a.notes}


@router.patch("/applications/{application_id}")
def update_application(application_id: str, body: ApplicationUpdate, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    """Advancing a stage moves the internship's headline status and re-dates the
    mirrored Task, so Career and Planner never disagree about what's next."""
    a = _own(db, Application, application_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(a, k, v)
    it = db.query(Internship).filter(Internship.id == a.internship_id).first()
    if it and body.stage:
        it.status = STAGE_TO_STATUS.get(a.stage, it.status)
    if it:
        materialize.task_for_application(db, a, it)
    if a.stage == "result":
        stale = db.query(Task).filter(Task.application_id == a.id, Task.status == "open").first()
        if stale:
            stale.status = "done"
    db.commit(); db.refresh(a)
    spider_sense.scan(db, user)
    return {"id": str(a.id), "stage": a.stage,
            "deadline": a.deadline.isoformat() if a.deadline else None, "notes": a.notes}


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: str, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    a = _own(db, Application, application_id, user)
    db.delete(a); db.commit()
    return
