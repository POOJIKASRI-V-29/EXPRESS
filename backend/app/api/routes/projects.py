"""Projects: projects, their phases, and project tasks.

Completion is derived from phases when a project has them, so ticking a phase
moves the bar without anyone typing a percentage. Project tasks materialise
into the shared Task queue.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Project, ProjectPhase, ProjectTask, Task, Note
from app.schemas.projects import ProjectCreate, ProjectUpdate, PhaseCreate, ProjectTaskCreate
from app.services import materialize, spider_sense
from app.services.timeutils import now

router = APIRouter(prefix="/projects", tags=["projects"])


def _own_project(db, project_id, user):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _recompute_completion(db, project: Project) -> Project:
    phases = db.query(ProjectPhase).filter(ProjectPhase.project_id == project.id).all()
    if phases:
        project.completion = round(len([p for p in phases if p.done]) / len(phases) * 100)
        nxt = next((p for p in sorted(phases, key=lambda x: x.order) if not p.done), None)
        project.phase = nxt.name if nxt else "Complete"
    return project


def _serialize(db, user, p: Project) -> dict:
    phases = (db.query(ProjectPhase).filter(ProjectPhase.project_id == p.id)
              .order_by(ProjectPhase.order).all())
    ptasks = (db.query(ProjectTask)
              .filter(ProjectTask.project_id == p.id, ProjectTask.user_id == user.id)
              .order_by(ProjectTask.due_at.is_(None), ProjectTask.due_at).all())
    notes = db.query(Note).filter(Note.user_id == user.id, Note.ref_type == "project",
                                  Note.ref_id == p.id).count()
    return {
        "id": str(p.id), "name": p.name, "description": p.description, "phase": p.phase,
        "commits": p.commits, "stack": p.stack, "status": p.status,
        "completion": p.completion, "priority": p.priority, "repo_url": p.repo_url,
        "due_at": p.due_at.isoformat() if p.due_at else None,
        "note_count": notes,
        "phases": [{"id": str(ph.id), "name": ph.name, "order": ph.order, "done": ph.done}
                   for ph in phases],
        "tasks": [{"id": str(t.id), "title": t.title, "status": t.status,
                   "due_at": t.due_at.isoformat() if t.due_at else None} for t in ptasks],
        "open_tasks": len([t for t in ptasks if t.status == "open"]),
    }


@router.get("")
def list_projects(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = (db.query(Project).filter(Project.user_id == user.id)
            .order_by(Project.priority, Project.created_at).all())
    return {"projects": [_serialize(db, user, p) for p in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _serialize(db, user, _own_project(db, project_id, user))


@router.post("", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = Project(user_id=user.id, **body.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    spider_sense.scan(db, user)
    return _serialize(db, user, p)


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit(); db.refresh(p)
    spider_sense.scan(db, user)
    return _serialize(db, user, p)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    db.delete(p); db.commit()
    return


# ---- Phases ----
@router.post("/{project_id}/phases", status_code=201)
def add_phase(project_id: str, body: PhaseCreate, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    count = db.query(ProjectPhase).filter(ProjectPhase.project_id == p.id).count()
    ph = ProjectPhase(project_id=p.id, name=body.name,
                      order=body.order or count, done=body.done)
    db.add(ph); db.flush()
    _recompute_completion(db, p)
    db.commit()
    return _serialize(db, user, p)


@router.post("/{project_id}/phases/{phase_id}/toggle")
def toggle_phase(project_id: str, phase_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    ph = db.query(ProjectPhase).filter(ProjectPhase.id == phase_id,
                                       ProjectPhase.project_id == p.id).first()
    if not ph:
        raise HTTPException(404, "Phase not found")
    ph.done = not ph.done
    _recompute_completion(db, p)
    db.commit()
    spider_sense.scan(db, user)
    return _serialize(db, user, p)


@router.delete("/{project_id}/phases/{phase_id}", status_code=204)
def delete_phase(project_id: str, phase_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    ph = db.query(ProjectPhase).filter(ProjectPhase.id == phase_id,
                                       ProjectPhase.project_id == p.id).first()
    if ph:
        db.delete(ph); db.flush()
        _recompute_completion(db, p)
        db.commit()
    return


# ---- Project tasks (materialise into the shared queue) ----
@router.post("/{project_id}/tasks", status_code=201)
def add_project_task(project_id: str, body: ProjectTaskCreate, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    pt = ProjectTask(user_id=user.id, project_id=p.id, title=body.title, due_at=body.due_at)
    db.add(pt); db.flush()
    materialize.task_for_project_task(db, pt)
    db.commit()
    spider_sense.scan(db, user)
    return _serialize(db, user, p)


@router.post("/{project_id}/tasks/{ptask_id}/toggle")
def toggle_project_task(project_id: str, ptask_id: str, db: Session = Depends(get_db),
                        user=Depends(get_current_user)):
    p = _own_project(db, project_id, user)
    pt = db.query(ProjectTask).filter(ProjectTask.id == ptask_id,
                                      ProjectTask.user_id == user.id).first()
    if not pt:
        raise HTTPException(404, "Project task not found")
    pt.status = "open" if pt.status == "done" else "done"
    mirror = db.query(Task).filter(Task.project_task_id == pt.id).first()
    if mirror:
        mirror.status = pt.status
        mirror.completed_at = now() if pt.status == "done" else None
    db.commit()
    return _serialize(db, user, p)
