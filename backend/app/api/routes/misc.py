"""Home and Spider Sense — the two surfaces that read across every module.

Per-module endpoints live in their own routers (college, planner, learning,
projects, career, personal, goals, memory, finance, progress, integrations).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Notification
from app.schemas.system import NotificationOut
from app.services import home as home_svc, spider_sense

router = APIRouter(tags=["core"])


# ---- Home (dynamic, server-derived) ----
@router.get("/home")
def get_home(db: Session = Depends(get_db), user=Depends(get_current_user)):
    spider_sense.scan(db, user)
    return home_svc.build_home(db, user)


# ---- Spider Sense ----
@router.get("/spider-sense", response_model=list[NotificationOut])
def spider_list(db: Session = Depends(get_db), user=Depends(get_current_user)):
    spider_sense.scan(db, user)
    return spider_sense.active(db, user)


@router.post("/spider-sense/{notif_id}/acknowledge", response_model=NotificationOut)
def spider_ack(notif_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = (db.query(Notification)
         .filter(Notification.id == notif_id, Notification.user_id == user.id).first())
    if n:
        n.acknowledged = True
        db.commit(); db.refresh(n)
    return n


@router.post("/spider-sense/acknowledge-all")
def spider_ack_all(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = spider_sense.active(db, user)
    for n in rows:
        n.acknowledged = True
    db.commit()
    return {"acknowledged": len(rows)}
