"""Goals: intent, linked to the work that actually delivers it.

A goal's progress is derived from whatever it's linked to — tasks, a project, a
topic, a skill, a habit. Linking is what makes a goal more than a wish, so the
`progress` field is only used as a fallback for goals with nothing linked yet.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Goal, GoalLink, Task, Project, LearningTopic, Skill, Habit
from app.schemas.goals import GoalCreate, GoalUpdate, GoalLinkCreate
from app.services import goals as goals_svc, spider_sense

router = APIRouter(prefix="/goals", tags=["goals"])

LINKABLE = {"task": Task, "project": Project, "topic": LearningTopic,
            "skill": Skill, "habit": Habit}


def _own_goal(db, goal_id, user) -> Goal:
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    return g


@router.get("")
def list_goals(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Goals plus everything that can be linked to one, so the UI can offer
    real choices instead of a free-text box."""
    linkable = {}
    for kind, model in LINKABLE.items():
        rows = db.query(model).filter(model.user_id == user.id).all()
        if kind == "task":
            rows = [r for r in rows if r.status == "open"]
        linkable[kind] = [{"id": str(r.id),
                           "label": getattr(r, "name", None) or getattr(r, "title", "")}
                          for r in rows]
    return {"goals": goals_svc.listing(db, user), "linkable": linkable}


@router.post("", status_code=201)
def create_goal(body: GoalCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    g = Goal(user_id=user.id, **body.model_dump())
    db.add(g); db.commit(); db.refresh(g)
    spider_sense.scan(db, user)
    return goals_svc.detail(db, user, g)


@router.patch("/{goal_id}")
def update_goal(goal_id: str, body: GoalUpdate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    g = _own_goal(db, goal_id, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(g, k, v)
    db.commit(); db.refresh(g)
    spider_sense.scan(db, user)
    return goals_svc.detail(db, user, g)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    g = _own_goal(db, goal_id, user)
    db.query(GoalLink).filter(GoalLink.goal_id == g.id).delete()
    db.delete(g); db.commit()
    return


@router.post("/{goal_id}/links", status_code=201)
def add_link(goal_id: str, body: GoalLinkCreate, db: Session = Depends(get_db),
             user=Depends(get_current_user)):
    g = _own_goal(db, goal_id, user)
    model = LINKABLE.get(body.ref_type)
    if not model:
        raise HTTPException(422, f"ref_type must be one of {sorted(LINKABLE)}")
    target = db.query(model).filter(model.id == body.ref_id, model.user_id == user.id).first()
    if not target:
        raise HTTPException(404, f"No {body.ref_type} with that id")
    dupe = (db.query(GoalLink)
            .filter(GoalLink.goal_id == g.id, GoalLink.ref_type == body.ref_type,
                    GoalLink.ref_id == body.ref_id).first())
    if not dupe:
        db.add(GoalLink(user_id=user.id, goal_id=g.id,
                        ref_type=body.ref_type, ref_id=body.ref_id))
        db.commit()
    db.refresh(g)
    return goals_svc.detail(db, user, g)


@router.delete("/{goal_id}/links/{link_id}")
def remove_link(goal_id: str, link_id: str, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    g = _own_goal(db, goal_id, user)
    l = db.query(GoalLink).filter(GoalLink.id == link_id, GoalLink.goal_id == g.id,
                                  GoalLink.user_id == user.id).first()
    if l:
        db.delete(l); db.commit()
    db.refresh(g)
    return goals_svc.detail(db, user, g)
