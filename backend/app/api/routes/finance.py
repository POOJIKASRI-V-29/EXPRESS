"""Finance: entries and monthly budgets.

The page and Spider Sense both read `finance.summary`, so a budget warning in
the tray and the bar on screen are computed once, from the same rows.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import FinanceEntry, Budget
from app.schemas.personal import FinanceCreate, BudgetCreate, BudgetUpdate
from app.services import finance as finance_svc, spider_sense
from app.services.timeutils import now

router = APIRouter(prefix="/finance", tags=["finance"])


def _own(db, model, row_id, user):
    row = db.query(model).filter(model.id == row_id, model.user_id == user.id).first()
    if not row:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


@router.get("")
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return finance_svc.summary(db, user)


@router.get("/entries")
def list_entries(limit: int = 100, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = (db.query(FinanceEntry).filter(FinanceEntry.user_id == user.id)
            .order_by(FinanceEntry.date.desc()).limit(max(1, min(limit, 500))).all())
    return [{"id": str(e.id), "amount": float(e.amount or 0), "category": e.category,
             "kind": e.kind, "note": e.note, "date": e.date.isoformat()} for e in rows]


@router.post("/entries", status_code=201)
def create_entry(body: FinanceCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = body.model_dump()
    data["date"] = data.get("date") or now()
    e = FinanceEntry(user_id=user.id, **data)
    db.add(e); db.commit()
    spider_sense.scan(db, user)   # spending can push a budget over its cap
    return finance_svc.summary(db, user)


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = _own(db, FinanceEntry, entry_id, user)
    db.delete(e); db.commit()
    return


@router.post("/budgets", status_code=201)
def create_budget(body: BudgetCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    existing = (db.query(Budget)
                .filter(Budget.user_id == user.id, Budget.category == body.category).first())
    if existing:
        existing.monthly_limit = body.monthly_limit
    else:
        db.add(Budget(user_id=user.id, **body.model_dump()))
    db.commit()
    spider_sense.scan(db, user)
    return finance_svc.summary(db, user)


@router.patch("/budgets/{budget_id}")
def update_budget(budget_id: str, body: BudgetUpdate, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    b = _own(db, Budget, budget_id, user)
    b.monthly_limit = body.monthly_limit
    db.commit()
    spider_sense.scan(db, user)
    return finance_svc.summary(db, user)


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    b = _own(db, Budget, budget_id, user)
    db.delete(b); db.commit()
    return
