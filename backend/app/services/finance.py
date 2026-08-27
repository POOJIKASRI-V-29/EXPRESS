"""Finance rollups. Budgets are per-category monthly caps; Spider Sense reads
the same `budget_status` this module serves to the UI, so a warning on screen
and a signal in the tray can never disagree.
"""
from decimal import Decimal
from app.models import FinanceEntry, Budget
from app.services.timeutils import local_month_bounds


def _f(x) -> float:
    return float(x or 0)


def month_entries(db, user):
    start, end = local_month_bounds()
    return (db.query(FinanceEntry)
            .filter(FinanceEntry.user_id == user.id,
                    FinanceEntry.date >= start, FinanceEntry.date < end)
            .order_by(FinanceEntry.date.desc()).all())


def budget_status(db, user) -> list[dict]:
    entries = month_entries(db, user)
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    spent_by_cat: dict[str, float] = {}
    for e in entries:
        if e.kind == "expense":
            spent_by_cat[e.category] = spent_by_cat.get(e.category, 0.0) + _f(e.amount)
    out = []
    for b in budgets:
        limit = _f(b.monthly_limit)
        spent = spent_by_cat.get(b.category, 0.0)
        pct = round(spent / limit * 100) if limit else 0
        out.append({"id": str(b.id), "category": b.category, "limit": limit,
                    "spent": round(spent, 2), "pct": pct,
                    "state": "over" if pct >= 100 else ("near" if pct >= 80 else "ok")})
    out.sort(key=lambda x: -x["pct"])
    return out


def summary(db, user) -> dict:
    entries = month_entries(db, user)
    spent = sum(_f(e.amount) for e in entries if e.kind == "expense")
    earned = sum(_f(e.amount) for e in entries if e.kind == "income")
    by_cat: dict[str, float] = {}
    for e in entries:
        if e.kind == "expense":
            by_cat[e.category] = by_cat.get(e.category, 0.0) + _f(e.amount)
    return {
        "month_spent": round(spent, 2),
        "month_income": round(earned, 2),
        "net": round(earned - spent, 2),
        "entry_count": len(entries),
        "by_category": sorted(
            [{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()],
            key=lambda x: -x["amount"]),
        "budgets": budget_status(db, user),
        "recent": [{"id": str(e.id), "amount": _f(e.amount), "category": e.category,
                    "kind": e.kind, "note": e.note, "date": e.date.isoformat()}
                   for e in entries[:12]],
    }
