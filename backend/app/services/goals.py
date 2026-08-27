"""Goal progress is derived from linked work, not typed in.

A goal linked to tasks reports the share completed; linked to projects it
reports their completion; linked to topics it reports topic progress. The
manual `progress` field acts as a floor for goals with nothing linked yet, so a
freshly created goal isn't stuck at 0%.

`listing` resolves every goal's links with a fixed number of queries — one per
referenced type — rather than one per link. Goals appear on their own page, in
JOCasta's context and inside a Spider Sense detector, so the per-link version
multiplied across all three.
"""
from app.models import Goal, GoalLink, Task, Project, LearningTopic, Skill, Habit
from app.services import habits as habits_svc

# ref_type -> (model, label attribute, progress resolver)
LINK_KINDS = {
    "task": (Task, "title", lambda row, _ctx: 100 if row.status == "done" else 0),
    "project": (Project, "name", lambda row, _ctx: row.completion or 0),
    "topic": (LearningTopic, "name", lambda row, _ctx: row.progress or 0),
    "skill": (Skill, "name", lambda row, _ctx: row.pct or 0),
    "habit": (Habit, "title", lambda row, ctx: ctx.get(str(row.id), 0)),
}


def _habit_progress(db, user) -> dict:
    """Share of this week's target met, per habit."""
    out = {}
    for h in habits_svc.summary(db, user):
        target = max(h.get("target_per_week") or 7, 1)
        out[h["id"]] = min(100, round(h["done_this_week"] / target * 100))
    return out


def _resolve(db, user, links: list[GoalLink]) -> dict:
    """Bulk-load every referenced row, keyed by (ref_type, ref_id)."""
    wanted: dict[str, set] = {}
    for l in links:
        wanted.setdefault(l.ref_type, set()).add(l.ref_id)

    resolved: dict = {}
    habit_ctx = _habit_progress(db, user) if "habit" in wanted else {}
    for ref_type, ids in wanted.items():
        spec = LINK_KINDS.get(ref_type)
        if not spec:
            continue
        model, label_attr, progress_fn = spec
        rows = (db.query(model)
                .filter(model.user_id == user.id, model.id.in_(list(ids))).all())
        for row in rows:
            resolved[(ref_type, row.id)] = {
                "label": getattr(row, label_attr, "") or "",
                "progress": progress_fn(row, habit_ctx),
            }
    return resolved


def _assemble(goal: Goal, links: list[GoalLink], resolved: dict) -> dict:
    parts, out_links = [], []
    for l in links:
        got = resolved.get((l.ref_type, l.ref_id))
        if got is None:
            continue          # the linked row was deleted; ignore rather than fail
        parts.append(got["progress"])
        out_links.append({"id": str(l.id), "ref_type": l.ref_type, "ref_id": str(l.ref_id),
                          "label": got["label"], "progress": got["progress"]})

    derived = round(sum(parts) / len(parts)) if parts else None
    progress = derived if derived is not None else (goal.progress or 0)
    return {
        "id": str(goal.id), "title": goal.title, "detail": goal.detail,
        "horizon": goal.horizon, "category": goal.category, "status": goal.status,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "progress": progress,
        "progress_source": "linked work" if derived is not None else "manual",
        "links": out_links,
    }


def detail(db, user, goal: Goal) -> dict:
    links = db.query(GoalLink).filter(GoalLink.goal_id == goal.id,
                                      GoalLink.user_id == user.id).all()
    return _assemble(goal, links, _resolve(db, user, links))


def listing(db, user) -> list[dict]:
    goals = (db.query(Goal).filter(Goal.user_id == user.id)
             .order_by(Goal.status.asc(), Goal.created_at.asc()).all())
    if not goals:
        return []
    all_links = db.query(GoalLink).filter(GoalLink.user_id == user.id).all()
    resolved = _resolve(db, user, all_links)

    by_goal: dict = {}
    for l in all_links:
        by_goal.setdefault(l.goal_id, []).append(l)
    return [_assemble(g, by_goal.get(g.id, []), resolved) for g in goals]
