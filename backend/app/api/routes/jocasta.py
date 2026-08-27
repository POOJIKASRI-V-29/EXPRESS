"""JOCasta endpoints.

`/message` reasons and either acts or asks. `/confirm` runs a plan the user
approved. `/context` exposes the exact brief JOCasta reasoned over, so an answer
is always explainable.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.jocasta import context as ctx_mod, orchestrator, safety
from app.schemas.jocasta import ConfirmIn, JocastaIn, JocastaOut

router = APIRouter(prefix="/jocasta", tags=["jocasta"])


@router.post("/message", response_model=JocastaOut)
def message(body: JocastaIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return orchestrator.run(db, user, body.text)


@router.post("/confirm", response_model=JocastaOut)
def confirm(body: ConfirmIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Execute a plan the user approved. The token is re-verified server-side."""
    try:
        return orchestrator.confirm(db, user, body.confirm_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/context")
def get_context(q: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    """The bounded brief JOCasta would reason over for `q`.

    Exposed deliberately: if JOCasta says something surprising, this shows
    exactly what it knew — and confirms what it was never given.
    """
    ctx = ctx_mod.build(db, user, q)
    return {"included_slices": ctx["included_slices"], "brief": ctx_mod.summarize(ctx),
            "context": ctx}


@router.get("/tools")
def list_tools(user=Depends(get_current_user)):
    """The full authorized surface, with each tool's risk level."""
    from app.jocasta.tools import REGISTRY
    from app.jocasta.planner_llm import DESCRIPTIONS
    rows = [{"name": name, "risk": safety.risk_of(name),
             "description": DESCRIPTIONS.get(name, ""),
             "confirms_first": safety.risk_of(name) == safety.SENSITIVE}
            for name in sorted(REGISTRY)]
    return {"tools": rows, "count": len(rows),
            "by_risk": {r: len([x for x in rows if x["risk"] == r])
                        for r in (safety.READ, safety.WRITE, safety.SENSITIVE)},
            "bulk_threshold": safety.BULK_THRESHOLD}
