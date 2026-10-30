"""FastAPI app with 8 endpoints. Use create_app(engine) in tests to inject a test database."""
import io
from datetime import date

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app import db, generator, pipeline, queries


def create_app(engine=None) -> FastAPI:
    engine = engine or db.get_engine()
    db.init_db(engine)
    app = FastAPI(title="Invoice Reconciliation Platform")
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

    return app
