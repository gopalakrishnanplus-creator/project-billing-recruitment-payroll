from datetime import date
import os

os.environ["ALLOW_TEST_AUTH"] = "true"

from app.database import Base, engine
from app.main import app
from fastapi.testclient import TestClient


OPS_HEADERS = {"x-test-email": "ops@example.com", "x-test-role": "operations_manager"}
CAE_HEADERS = {"x-test-email": "cae@example.com", "x-test-role": "client_account_executive"}
FINANCE_HEADERS = {"x-test-email": "finance@example.com", "x-test-role": "finance_manager"}
ADMIN_HEADERS = {"x-test-email": "Gopala.Krishnan@flexgcc.com", "x-test-role": "system_admin"}


PROJECT_PAYLOAD = {
    "client_company_name": "Acme Operations",
    "client_contact_name": "Anita Shah",
    "client_contact_email": "anita@example.com",
    "client_contact_phone": "+1-555-0101",
    "msa_reference": "MSA-ACME-2026",
    "msa_document_name": "acme-msa.pdf",
    "sow_title": "Plant recruitment sprint",
    "sow_description": "Recruitment support for operations roles.",
    "sow_document_name": "plant-sprint-sow.pdf",
    "sow_amount": "12000.00",
    "currency": "USD",
    "start_date": "2026-04-01",
    "end_date": "2026-06-30",
    "operations_manager_name": "Ops Manager",
}


def test_project_to_client_collection_flow():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        project_response = client.post(
            "/projects",
            headers=OPS_HEADERS,
            json=PROJECT_PAYLOAD,
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()

        need_response = client.post(
            f"/projects/{project['id']}/recruitment-needs",
            headers=OPS_HEADERS,
            json={
                "position_title": "Operations Analyst",
                "number_of_positions": 2,
                "employment_type": "FTE",
                "description": "Analysts for daily plant reporting and process control.",
                "target_start_date": "2026-05-01",
                "internal_interviewers": "Plant Head; HR Manager",
            },
        )
        assert need_response.status_code == 201, need_response.text

        schedule_response = client.post(
            f"/projects/{project['id']}/invoice-schedules",
            headers=OPS_HEADERS,
            json={
                "label": "Monthly client billing",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "monthly",
                "first_invoice_date": "2026-04-15",
                "final_invoice_date": "2026-06-15",
            },
        )
        assert schedule_response.status_code == 201, schedule_response.text

        generated_response = client.post("/invoices/generate?as_of=2026-04-29", headers=OPS_HEADERS)
        assert generated_response.status_code == 200, generated_response.text
        generated = generated_response.json()
        assert generated["generated_count"] >= 1
        invoice_id = generated["invoices"][0]["id"]

        client_account_response = client.post(
            f"/client-invoices/{invoice_id}/client-account-approval",
            headers=CAE_HEADERS,
            json={"approver_name": "Client Account Executive", "notes": "Matches SOW schedule."},
        )
        assert client_account_response.status_code == 200, client_account_response.text
        assert client_account_response.json()["status"] == "approved_by_client_account"

        finance_response = client.post(
            f"/client-invoices/{invoice_id}/finance-approval",
            headers=FINANCE_HEADERS,
            json={"approver_name": "Finance Manager", "notes": "Ready to send."},
        )
        assert finance_response.status_code == 200, finance_response.text
        assert finance_response.json()["status"] == "approved_for_sending"

        send_response = client.post(
            f"/client-invoices/{invoice_id}/send",
            headers=FINANCE_HEADERS,
            json={"sender_name": "Finance Manager", "recipient_email": "anita@example.com"},
        )
        assert send_response.status_code == 200, send_response.text
        assert send_response.json()["status"] == "sent_to_client"

        payment_response = client.post(
            f"/client-invoices/{invoice_id}/payments",
            headers=FINANCE_HEADERS,
            json={
                "amount_received": "4000.00",
                "received_date": str(date(2026, 4, 29)),
                "bank_reference": "WIRE-123",
                "recorded_by_name": "Finance Manager",
            },
        )
        assert payment_response.status_code == 201, payment_response.text
        assert payment_response.json()["status"] == "paid"
        assert payment_response.json()["balance_due"] == "0.00"


def test_role_separated_permissions_and_admin_user_provisioning():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        unauthenticated_response = client.get("/projects")
        assert unauthenticated_response.status_code == 401

        finance_project_response = client.post("/projects", headers=FINANCE_HEADERS, json=PROJECT_PAYLOAD)
        assert finance_project_response.status_code == 403

        admin_user_response = client.post(
            "/users",
            headers=ADMIN_HEADERS,
            json={
                "full_name": "Dual Role User",
                "email": "dual@example.com",
                "is_active": True,
                "roles": ["finance_manager", "operations_manager"],
            },
        )
        assert admin_user_response.status_code == 200, admin_user_response.text
        assert admin_user_response.json()["roles"] == ["finance_manager", "operations_manager"]
