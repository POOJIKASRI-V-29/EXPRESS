from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Task, Assignment
from app.schemas.task import TaskOut, TaskCreate, TaskUpdate, RescheduleIn
from app.services import spider_sense
from app.services import planner as planner_svc
from app.services.timeutils import now

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Task).filter(Task.user_id == user.id).order_by(Task.due_at.is_(None), Task.due_at.asc()).all()


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = body.model_dump()
    data["category"] = planner_svc.normalise(data.get("category"))
    t = Task(user_id=user.id, **data)
    db.add(t); db.commit(); db.refresh(t)
    spider_sense.scan(db, user)
    return t


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, body: TaskUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Edit a planner item in place.

    Distinct from /reschedule: editing a mistyped time is a correction, not a
    postponement, so it does not increment `postpone_count` and does not make
    Spider Sense think the user is avoiding the work.
    """
    t = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    data = body.model_dump(exclude_none=True)
    if "category" in data:
        data["category"] = planner_svc.normalise(data["category"])
    for k, v in data.items():
        setattr(t, k, v)
    db.commit(); db.refresh(t)
    spider_sense.scan(db, user)
    return t


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Remove a planner item.

    A task that mirrors an assignment or project task is only the planner
    entry — deleting it clears the schedule, not the coursework it came from.
    """
    t = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    spider_sense.scan(db, user)
    return


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    t.status = "done"; t.completed_at = now()
    if t.assignment_id:
        asg = db.query(Assignment).filter(Assignment.id == t.assignment_id).first()
        if asg:
            asg.status = "done"
    db.commit(); db.refresh(t)
    return t


@router.post("/{task_id}/reschedule", response_model=TaskOut)
def reschedule_task(task_id: str, body: RescheduleIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    t.due_at = body.due_at
    t.postpone_count = (t.postpone_count or 0) + 1
    if t.assignment_id:
        asg = db.query(Assignment).filter(Assignment.id == t.assignment_id).first()
        if asg:
            asg.due_at = body.due_at
    db.commit()
    spider_sense.scan(db, user)   # deadline change -> Spider Sense re-derives
    db.refresh(t)
    return t
