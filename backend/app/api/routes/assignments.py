from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Assignment, Task
from app.schemas.assignment import AssignmentOut, AssignmentCreate
from app.services import materialize, spider_sense

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("", response_model=list[AssignmentOut])
def list_assignments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Assignment).filter(Assignment.user_id == user.id).order_by(Assignment.due_at.asc()).all()


@router.post("", response_model=AssignmentOut, status_code=201)
def create_assignment(body: AssignmentCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = Assignment(user_id=user.id, **body.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    materialize.task_for_assignment(db, a)   # Assignment -> Task (surfaces in Planner/Home)
    db.commit()
    spider_sense.scan(db, user)              # Deadline -> Spider Sense -> Notification
    return a


@router.post("/{assignment_id}/complete", response_model=AssignmentOut)
def complete_assignment(assignment_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.user_id == user.id).first()
    if not a:
        raise HTTPException(404, "Assignment not found")
    a.status = "done"
    t = db.query(Task).filter(Task.assignment_id == a.id).first()
    if t:
        t.status = "done"
    db.commit(); db.refresh(a)
    return a
