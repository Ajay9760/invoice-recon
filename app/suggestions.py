"""Suggestion workflow: create (AI proposes), list, decide (human approves or rejects)."""
import logging
from datetime import datetime

from sqlalchemy import func, select, update

from app import db
from app.llm import RuleBasedSuggester, Suggester, SuggestionError
from app.observability import DECISIONS, SUGGESTIONS

log = logging.getLogger("recon.suggestions")
S = db.suggestions
E = db.exceptions


class NotFound(Exception):
    pass


class AlreadyDecided(Exception):
    pass


def _row(r) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()}


def create(engine, suggester: Suggester, exception_id: int) -> dict:
    """Ask the suggester for a remediation. Falls back to the rule-based one on any failure."""
    with engine.connect() as conn:
        exc = conn.execute(select(E).where(E.c.id == exception_id)).mappings().first()
    if exc is None:
        raise NotFound(f"exception {exception_id} not found")

    try:
        s = suggester.suggest(exc["rule_code"], exc["severity"], exc["detail"])
        source = s.source
    except SuggestionError as err:
        log.warning("suggestion fallback", extra={"exception_id": exception_id, "reason": str(err)})
        s = RuleBasedSuggester().suggest(exc["rule_code"], exc["severity"], exc["detail"])
        source = "fallback"
    SUGGESTIONS.labels(source=source).inc()

    with engine.begin() as conn:
        new_id = conn.execute(S.insert().values(
            exception_id=exception_id, action=s.action, rationale=s.rationale, source=source,
            model=s.model, status="PENDING", created_at=datetime.now())).inserted_primary_key[0]
        row = conn.execute(select(S).where(S.c.id == new_id)).mappings().one()
    log.info("suggestion created", extra={"suggestion_id": new_id, "source": source, "action": s.action})
    return _row(row)


def list_suggestions(engine, status=None, limit=50, offset=0) -> dict:
    q, cnt = select(S), select(func.count()).select_from(S)
    if status:
        q, cnt = q.where(S.c.status == status), cnt.where(S.c.status == status)
    with engine.connect() as conn:
        total = conn.execute(cnt).scalar_one()
        rows = conn.execute(q.order_by(S.c.id).limit(limit).offset(offset)).mappings().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_row(r) for r in rows]}


def decide(engine, suggestion_id: int, decision: str, note: str | None) -> dict:
    """Record a human decision. Only a PENDING suggestion can be decided, exactly once."""
    status = "APPROVED" if decision == "approve" else "REJECTED"
    with engine.begin() as conn:
        # Conditional update: two reviewers racing cannot both win.
        res = conn.execute(update(S).where(S.c.id == suggestion_id, S.c.status == "PENDING")
                           .values(status=status, reviewer_note=note, decided_at=datetime.now()))
        if res.rowcount == 0:
            exists = conn.execute(select(S.c.id).where(S.c.id == suggestion_id)).first()
            raise AlreadyDecided("suggestion already decided") if exists else NotFound("suggestion not found")
        row = conn.execute(select(S).where(S.c.id == suggestion_id)).mappings().one()
    DECISIONS.labels(decision=status).inc()
    log.info("suggestion decided", extra={"suggestion_id": suggestion_id, "status": status})
    return _row(row)
