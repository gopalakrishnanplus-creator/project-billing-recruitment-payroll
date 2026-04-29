# Project Billing Recruitment Payroll

Standalone application for recruitment operations, client billing, consultant/candidate invoicing, and payroll workflows.

This repository is intentionally separate from the FlexGCC execution system:

- separate local checkout
- separate GitHub repository
- separate Render services
- separate app users and roles
- separate database schema and production database
- separate URLs

## Local Development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Open `http://127.0.0.1:5174`.

The default backend database is `backend/project_billing.db`. Production uses the Render PostgreSQL database provisioned by `render.yaml`.

## Implemented Flow

The first implemented flow is:

1. operations manager enters client, contact, MSA, SOW, and contract metadata
2. operations manager adds recruitment needs
3. operations manager adds client invoicing schedules
4. system generates due client invoices from the schedules
5. client account executive approves the invoice
6. finance manager approves and sends the invoice
7. finance manager records client payment collection

The remaining recruitment candidate, consultant invoice, and payroll workflows are represented in the schema for later implementation.
