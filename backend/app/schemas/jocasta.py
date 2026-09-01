from typing import Any, Optional
from pydantic import BaseModel


class JocastaIn(BaseModel):
    text: str
    # Signed, short-lived handle for a PDF the user just attached. The file
    # itself is never stored — the token carries the parsed rows.
    attachment_token: Optional[str] = None


class ConfirmIn(BaseModel):
    confirm_token: str


class ToolCallOut(BaseModel):
    tool: str
    ok: bool
    result: Any = None
    error: str | None = None


class PendingAction(BaseModel):
    tool: str
    risk: str
    summary: str


class PendingOut(BaseModel):
    actions: list[PendingAction]
    reason: str
    risk: str


class VerificationOut(BaseModel):
    """What actually happened, rather than what was attempted."""
    attempted: int
    succeeded: int
    failed: int
    failures: list[dict] = []


class JocastaOut(BaseModel):
    reply: str
    calls: list[ToolCallOut] = []
    planner: str                      # "llm" | "rules" | "confirmed"
    modules: list[str] = []           # modules whose data changed, so the UI can refresh
    verification: Optional[VerificationOut] = None
    # Set when the plan needs approval before it runs. `confirm_token` is a
    # short-lived signed bundle; post it back to /jocasta/confirm to proceed.
    pending: Optional[PendingOut] = None
    confirm_token: Optional[str] = None
    context_used: list[str] = []      # which context slices informed the answer
    # What JOCasta decided the message was, and why. Exposed so a surprising
    # answer can be traced to the classification that produced it.
    intent: str = ""
    intent_reason: str = ""
