"""JOCasta endpoints.

`/message` reasons and either acts or asks. `/confirm` runs a plan the user
approved. `/context` exposes the exact brief JOCasta reasoned over, so an answer
is always explainable.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.jocasta import attachment as attachment_flow, context as ctx_mod, orchestrator, safety
from app.services import attachments

#: How much extracted text rides in the signed handle. Comfortably covers a
#: timetable or a syllabus without making the request body unwieldy.
TOKEN_TEXT_LIMIT = 20_000
from app.schemas.jocasta import ConfirmIn, JocastaIn, JocastaOut

router = APIRouter(prefix="/jocasta", tags=["jocasta"])


@router.post("/message", response_model=JocastaOut)
def message(body: JocastaIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return orchestrator.run(db, user, body.text, attachment_token=body.attachment_token)


@router.post("/attachments")
async def upload_attachment(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Read an attachment and hand back a short-lived handle for it.

    Reading only — this endpoint decides nothing. What the file is *for* is
    worked out when the user sends their instruction, because the same PDF can
    mean "add these classes", "build this course" or "what does this say".

    The file itself is never stored: the extracted text travels back in a
    signed, user-bound token that expires in 30 minutes.
    """
    data = await file.read()
    try:
        att = attachments.read(data, file.filename or "attachment",
                               file.content_type or "")
    except attachments.UnreadableAttachment as exc:
        # A reason the user can act on, not a generic failure.
        raise HTTPException(422, str(exc))

    signals, _classes, _outline = attachment_flow.analyse(att)

    return {
        "filename": att.filename,
        "kind": att.kind,
        "pages": att.pages,
        "chars": att.chars,
        "preview": att.preview(240),
        # What was recognised, so the UI can hint at what is possible.
        "found": {"classes": signals.classes, "modules": signals.modules,
                  "concepts": signals.concepts},
        "attachment_token": safety.sign_payload(
            user.id,
            {"kind": "attachment", "filename": att.filename, "type": att.kind,
             "pages": att.pages, "text": att.text[:TOKEN_TEXT_LIMIT],
             "truncated": att.chars > TOKEN_TEXT_LIMIT}),
    }


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
