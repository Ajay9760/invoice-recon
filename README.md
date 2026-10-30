<div align="center">

# Invoice Reconciliation Platform

**A data-driven invoice and payment reconciliation system built with Python, FastAPI, Pandas, and PostgreSQL.**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Containerized-Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-80-brightgreen)](#testing)

</div>

---

## Overview

The **Invoice Reconciliation Platform** automates the ingestion, validation, and reconciliation of invoice and payment data. It processes CSV datasets, standardizes and validates records, stores normalized data in a relational database, and applies a collection of reconciliation rules to identify inconsistencies and exceptions.

The project is designed around a reproducible synthetic-data workflow: the data generator creates invoices and payments and injects known anomalies, making it possible to exercise the reconciliation pipeline and compare detected exceptions with the generated test conditions.

> **Data notice:** The included generator produces synthetic data. No real customer, vendor, invoice, or payment information is required to run the project.

## Key capabilities

- **CSV ingestion** — accepts invoice and payment data for processing.
- **Data cleaning and validation** — standardizes text, parses dates and amounts, and accounts for unusable rows rather than silently discarding them.
- **Relational data model** — stores reference and transactional data across six tables.
- **Rule-based reconciliation** — applies 12 vectorized checks covering data quality, invoice/payment consistency, and orphan payments.
- **Exception tracking** — persists detected issues for inspection through the API.
- **Summary and trend endpoints** — exposes reconciliation summaries, exception records, invoice details, and trends.
- **Synthetic data generation** — creates repeatable datasets with injected anomalies for testing and experimentation.
- **Containerized setup** — runs the API, PostgreSQL database, and frontend through Docker Compose.

## Technology stack

| Area | Technologies |
|---|---|
| Language | Python |
| API | FastAPI, Uvicorn |
| Data processing | Pandas, NumPy |
| Persistence | SQLAlchemy |
| Database | PostgreSQL 16; SQLite supported by the backend |
| Validation / file ingestion | Python data-cleaning pipeline, `python-multipart` |
| Testing | Pytest, pytest-cov, HTTPX |
| Deployment | Docker, Docker Compose |
| Frontend | Separate application in `frontend/`, served through the Compose setup |

## Architecture

```text
                   ┌─────────────────────────┐
                   │       CSV inputs        │
                   │  Invoices & Payments    │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │       FastAPI API       │
                   │ Upload / Generate /     │
                   │ Reconcile / Query       │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │    Data preparation     │
                   │ Clean → Validate →      │
                   │ Resolve references      │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │   Relational database   │
                   │ Vendors, Customers,     │
                   │ Tax, Invoices, Payments,│
                   │ Exceptions              │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Reconciliation engine   │
                   │ 12 rule-based checks    │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Exceptions & summaries  │
                   │ API results / trends    │
                   └─────────────────────────┘
```

### Processing flow

1. **Generate or upload data** — create a synthetic dataset or submit invoice and payment CSV files.
2. **Clean input records** — normalize text fields and parse date and monetary values. Unusable rows are counted and reported.
3. **Resolve references** — map incoming records to database entities such as vendors and customers.
4. **Persist records** — load reference and transactional data into the relational schema.
5. **Run reconciliation** — execute the configured validation and invoice/payment matching rules.
6. **Review results** — retrieve summaries, exceptions, invoice details, and trend information through the API.

## Database design

The application uses a six-table relational schema:

| Table | Purpose |
|---|---|
| `vendors` | Vendor reference records |
| `customers` | Customer reference records |
| `tax_rates` | Tax-rate reference data |
| `invoices` | Invoice records and monetary details |
| `payments` | Payment records associated with invoices |
| `exceptions` | Reconciliation and data-quality issues |

When a foreign-key reference cannot be resolved, the corresponding reference is stored as `NULL` and the issue is surfaced for reconciliation rather than being silently discarded.

## Reconciliation rules

The reconciliation engine implements the following 12 checks:

| # | Rule | What it detects |
|---:|---|---|
| 1 | `MISSING_VENDOR` | Invoice records without a valid vendor reference |
| 2 | `DUPLICATE_INVOICE` | Duplicate invoice records |
| 3 | `NON_POSITIVE_AMOUNT` | Invoice amounts that are zero or negative |
| 4 | `TAX_MISMATCH` | Inconsistent tax calculations or values |
| 5 | `TOTAL_MISMATCH` | Differences between expected and recorded invoice totals |
| 6 | `FUTURE_DATED` | Invoice dates later than the current processing date |
| 7 | `DUE_BEFORE_ISSUE` | Due dates earlier than invoice issue dates |
| 8 | `INVALID_CURRENCY` | Unsupported or invalid currency values |
| 9 | `UNPAID_OVERDUE` | Invoices that are overdue and unpaid |
| 10 | `OVERPAID` | Payments exceeding the invoice amount |
| 11 | `PARTIALLY_PAID_OVERDUE` | Overdue invoices with an outstanding partial balance |
| 12 | `ORPHAN_PAYMENT` | Payments that cannot be matched to an invoice |

The rules are implemented as vectorized data checks to process datasets using Pandas.

## Getting started

### Prerequisites

For a local Python setup:

- Python 3.12 or later
- pip

For the containerized setup:

- Docker
- Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/Ajay9760/invoice-recon.git
cd invoice-recon
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Run the test suite

```bash
python -m pytest --cov=app
```

The repository currently documents **80 tests**. The command also reports coverage for the `app` package.

### 5. Start the API

```bash
python -m uvicorn app.main:create_app --factory --reload
```

The API will be available at:

- API base URL: `http://localhost:8000`
- Interactive Swagger documentation: `http://localhost:8000/docs`

## Run with Docker Compose

Docker Compose starts the PostgreSQL database, API, and frontend.

```bash
docker compose up --build
```

Default local endpoints:

| Service | URL |
|---|---|
| Frontend | `http://localhost:4200` |
| Backend API | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5433` |

The Compose configuration maps host port `5433` to PostgreSQL's container port `5432`. Services inside the Compose network connect to the database using its service hostname and container port.

To stop the services:

```bash
docker compose down
```

To stop the services and remove the database volume (this permanently deletes the local database data):

```bash
docker compose down -v
```

## API workflow

The API exposes the following endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Check API health |
| `POST` | `/data/generate?n=100000` | Generate a synthetic dataset |
| `POST` | `/data/upload` | Upload input data |
| `POST` | `/reconcile` | Run reconciliation rules |
| `GET` | `/summary` | Retrieve reconciliation summary |
| `GET` | `/exceptions` | Retrieve detected exceptions |
| `GET` | `/invoices/{id}` | Retrieve invoice details |
| `GET` | `/trends` | Retrieve trend information |

### Example: generate data and reconcile

Start the API, then use the interactive documentation at `http://localhost:8000/docs` or call the endpoints in sequence:

```text
POST /data/generate?n=100000
POST /reconcile
GET  /summary
GET  /exceptions
GET  /trends
```

The generator creates the synthetic invoice/payment data and injects anomalies into defined blocks. This provides a known generated dataset against which the rule results can be inspected.

## Testing

Run the full test suite:

```bash
python -m pytest --cov=app
```

To run tests against PostgreSQL, set `TEST_DATABASE_URL` before invoking pytest.

**Windows PowerShell**

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://recon:recon@localhost:5433/recon"
python -m pytest
```

**macOS / Linux**

```bash
TEST_DATABASE_URL="postgresql+psycopg2://recon:recon@localhost:5433/recon" python -m pytest
```

The PostgreSQL test URL above assumes the repository's default Docker Compose database configuration is running and reachable on host port `5433`.

## Project structure

```text
invoice-recon/
├── app/
│   ├── generator.py       # Synthetic invoice/payment data generation
│   ├── cleaning.py        # Input normalization and validation
│   ├── db.py              # Database schema and persistence
│   ├── rules.py           # Reconciliation rules
│   ├── pipeline.py        # Ingestion and reconciliation workflow
│   └── main.py            # FastAPI application and endpoints
├── frontend/              # Frontend application
├── e2e/                   # End-to-end test assets
├── tests/                 # Automated tests
├── Dockerfile             # API container image
├── docker-compose.yml     # Local multi-service environment
├── requirements.txt       # Python dependencies
└── pytest.ini             # Pytest configuration
```

## Design considerations and current limitations

- **Synthetic data:** the generator creates artificial records and injected anomalies. A reported 100% detection rate against generated anomalies means the rules detected the generator's defined cases; it should not be interpreted as 100% recall on real-world financial data.
- **Monetary precision:** amounts use `NUMERIC(14,2)` and comparisons use a tolerance of `0.02`.
- **No currency conversion:** values are validated, but the system does not convert amounts between currencies.
- **Authentication:** authentication is not currently implemented.
- **CORS:** the configured frontend origin is `http://localhost:4200`.

These constraints describe the current implementation and should be considered before using the project with production financial data.

## Potential future improvements

- Add authentication, authorization, and role-based access control.
- Add currency conversion with explicit exchange-rate sources and effective dates.
- Introduce configurable reconciliation rules and tolerances.
- Add audit history for uploads, reconciliation runs, and exception resolution.
- Add production-oriented observability, structured logging, and operational metrics.
- Expand validation with representative, anonymized real-world datasets.

## Contributing

Contributions and suggestions are welcome.

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/your-change`.
3. Make your changes and add or update tests.
4. Run the test suite: `python -m pytest --cov=app`.
5. Open a pull request with a clear description of the change.

## License

No license is currently specified in the repository. Unless a license is added, the default copyright rules apply; users should not assume the project is available for unrestricted reuse.

---

<div align="center">

**Built to make invoice and payment inconsistencies easier to identify, inspect, and investigate.**

[Repository](https://github.com/Ajay9760/invoice-recon) · [API Documentation](http://localhost:8000/docs)

</div>
