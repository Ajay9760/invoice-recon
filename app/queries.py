"""Read-side queries used by the API (summary, paging, drill-down, monthly trends)."""
import pandas as pd
from sqlalchemy import func, select

from app import db

E = db.exceptions


def summary(engine) -> dict:
    with engine.connect() as conn:
        n_inv = conn.execute(select(func.count()).select_from(db.invoices)).scalar_one()
        n_pay = conn.execute(select(func.count()).select_from(db.payments)).scalar_one()
        by_rule = conn.execute(select(E.c.rule_code, E.c.severity, func.count())
                               .group_by(E.c.rule_code, E.c.severity)
                               .order_by(func.count().desc())).all()
    by_sev: dict[str, int] = {}
    for _, sev, c in by_rule:
        by_sev[sev] = by_sev.get(sev, 0) + c
    return {"invoices": n_inv, "payments": n_pay, "exceptions": sum(by_sev.values()),
            "by_severity": by_sev,
            "by_rule": [{"rule_code": r, "severity": s, "count": c} for r, s, c in by_rule]}


def list_exceptions(engine, rule=None, severity=None, limit=50, offset=0) -> dict:
    q = select(E)
    cnt = select(func.count()).select_from(E)
    for col, val in ((E.c.rule_code, rule), (E.c.severity, severity)):
        if val:
            q, cnt = q.where(col == val), cnt.where(col == val)
    with engine.connect() as conn:
        total = conn.execute(cnt).scalar_one()
        rows = conn.execute(q.order_by(E.c.id).limit(limit).offset(offset)).mappings().all()
    items = [{**r, "run_at": r["run_at"].isoformat()} for r in rows]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def invoice_detail(engine, invoice_id: int):
    with engine.connect() as conn:
        inv = conn.execute(select(db.invoices).where(db.invoices.c.id == invoice_id)).mappings().first()
        if inv is None:
            return None
        pays = conn.execute(select(db.payments).where(db.payments.c.invoice_id == invoice_id)).mappings().all()
        excs = conn.execute(select(E).where(E.c.invoice_id == invoice_id)).mappings().all()
    iso = lambda r: {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
    return {"invoice": iso(inv), "payments": [iso(p) for p in pays], "exceptions": [iso(e) for e in excs],
            "paid_total": round(sum(p["amount"] for p in pays), 2)}


def trends(engine) -> list[dict]:
    """Exception counts per month (invoice month, or payment month for payment exceptions)."""
    with engine.connect() as conn:
        a = pd.read_sql(select(E.c.rule_code, db.invoices.c.invoice_date.label("d"))
                        .join(db.invoices, E.c.invoice_id == db.invoices.c.id), conn)
        b = pd.read_sql(select(E.c.rule_code, db.payments.c.payment_date.label("d"))
                        .join(db.payments, E.c.payment_id == db.payments.c.id), conn)
    df = pd.concat([a, b], ignore_index=True)
    if df.empty:
        return []
    df["month"] = pd.to_datetime(df["d"]).dt.strftime("%Y-%m")
    out = df.groupby(["month", "rule_code"]).size().reset_index(name="count")
    return out.to_dict("records")
