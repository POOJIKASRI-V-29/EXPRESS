"""Progress: the cross-module report."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.services import progress as progress_svc, spider_sense

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("")
def get_progress(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Compact snapshot — kept at this path because JOCasta and Home read it."""
    return progress_svc.snapshot(db, user)


@router.get("/report")
def get_report(db: Session = Depends(get_db), user=Depends(get_current_user)):
    spider_sense.scan(db, user)
    return progress_svc.report(db, user)
