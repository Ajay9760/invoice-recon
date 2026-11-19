"""FastAPI app (11 endpoints plus /metrics). Use create_app(engine) in tests to inject a test database."""
import hmac
import io
import os
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import db, generator, llm, observability, pipeline, queries, suggestions


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=255)


def require_reviewer(x_api_key: str | None = Header(default=None)) -> None:
    """Only a reviewer holding REVIEWER_API_KEY may approve or reject. Fails closed if unset."""
    expected = os.getenv("REVIEWER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="reviewer authentication is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def create_app(engine=None, suggester: llm.Suggester | None = None) -> FastAPI:
    engine = engine or db.get_engine()
    db.init_db(engine)
    observability.configure_logging()
    suggester = suggester or llm.get_suggester()
    app = FastAPI(title="Invoice Reconciliation Platform")
    observability.install(app)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4200"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")
    
    
    @app.get("/health")                                                    # 1
    def health():
        return {"status": "ok"}


    @app.post("/data/generate")                                            # 2
    def generate_data(n: int = Query(10_000, ge=500, le=200_000), seed: int = 42):
        data = generator.generate(n=n, seed=seed, as_of=date.today())
        pipeline.load_reference(engine, data["vendors"], data["customers"], data["tax_rates"])
        return pipeline.ingest(engine, data["invoices"], data["payments"])

    @app.post("/data/upload")                                              # 3
    async def upload(invoices: UploadFile = File(...), payments: UploadFile = File(...)):
        try:
            inv = pd.read_csv(io.BytesIO(await invoices.read()), dtype=str, keep_default_na=False)
            pay = pd.read_csv(io.BytesIO(await payments.read()), dtype=str, keep_default_na=False)
            return pipeline.ingest(engine, inv, pay)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/reconcile")                                                # 4
    def reconcile(as_of: date | None = None):
        return pipeline.reconcile(engine, as_of)

    @app.get("/summary")                                                   # 5
    def summary():
        return queries.summary(engine)

    @app.get("/exceptions")                                                # 6
    def exceptions(rule: str | None = None, severity: str | None = None,
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        return queries.list_exceptions(engine, rule, severity, limit, offset)

    @app.get("/invoices/{invoice_id}")                                     # 7
    def invoice(invoice_id: int):
        out = queries.invoice_detail(engine, invoice_id)
        if out is None:
            raise HTTPException(status_code=404, detail="invoice not found")
        return out

    @app.get("/trends")                                                    # 8
    def trends():
        return queries.trends(engine)

    @app.post("/exceptions/{exception_id}/suggestion", status_code=201)   # 9
    def suggest(exception_id: int):
        try:
            return suggestions.create(engine, suggester, exception_id)
        except suggestions.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/suggestions")                                               # 10
    def list_suggestions(status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None,
                         limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        return suggestions.list_suggestions(engine, status, limit, offset)

    @app.post("/suggestions/{suggestion_id}/decision",                     # 11
              dependencies=[Depends(require_reviewer)])
    def decide(suggestion_id: int, body: Decision):
        try:
            return suggestions.decide(engine, suggestion_id, body.decision, body.note)
        except suggestions.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except suggestions.AlreadyDecided as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    return app
