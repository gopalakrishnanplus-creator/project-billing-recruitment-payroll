from datetime import date
import os

os.environ["ALLOW_TEST_AUTH"] = "true"

from app.database import Base, engine
from app.main import app
from app.models import EmailNotification
from app.database import SessionLocal
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
    "client_account_executive_id": 0,
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


def provision_user(client: TestClient, *, full_name: str, email: str, roles: list[str]) -> dict:
    response = client.post(
        "/users",
        headers=ADMIN_HEADERS,
        json={"full_name": full_name, "email": email, "is_active": True, "roles": roles},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_project_to_client_collection_flow():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="Finance Manager", email="finance@example.com", roles=["finance_manager"])
        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]}
        project_response = client.post(
            "/projects",
            headers=OPS_HEADERS,
            json=payload,
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        assert project["client_account_executive_email"] == "cae@example.com"

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

        ops_generate_response = client.post("/invoices/generate?as_of=2026-04-29", headers=OPS_HEADERS)
        assert ops_generate_response.status_code == 403

        generated_response = client.post("/invoices/generate?as_of=2026-04-29", headers=ADMIN_HEADERS)
        assert generated_response.status_code == 200, generated_response.text

        invoices_response = client.get("/client-invoices", headers=FINANCE_HEADERS)
        assert invoices_response.status_code == 200, invoices_response.text
        invoices = invoices_response.json()
        assert len(invoices) >= 1
        invoice_id = invoices[0]["id"]

        with SessionLocal() as db:
            notification = db.query(EmailNotification).filter(EmailNotification.invoice_id == invoice_id).one()
            assert notification.recipient_email == "cae@example.com"
            assert notification.cc_email == "finance@example.com"
            assert "Log in to review and approve this invoice" in notification.body

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
        with SessionLocal() as db:
            notifications = db.query(EmailNotification).filter(EmailNotification.invoice_id == invoice_id).order_by(EmailNotification.id).all()
            assert notifications[-1].recipient_email == "anita@example.com"
            assert notifications[-1].cc_email == "cae@example.com,finance@example.com"

        download_response = client.get(f"/client-invoices/{invoice_id}/download", headers=FINANCE_HEADERS)
        assert download_response.status_code == 200, download_response.text
        assert "FlexGCC Invoice" in download_response.text

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

        cancel_paid_response = client.post(
            f"/client-invoices/{invoice_id}/cancel",
            headers=FINANCE_HEADERS,
            json={"cancelled_by_name": "Finance Manager", "reason": "Incorrect billing"},
        )
        assert cancel_paid_response.status_code == 400


def test_role_separated_permissions_and_admin_user_provisioning():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]}
        unauthenticated_response = client.get("/projects")
        assert unauthenticated_response.status_code == 401

        finance_project_response = client.post("/projects", headers=FINANCE_HEADERS, json=payload)
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


def test_project_file_upload_update_and_additional_sow():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": str(cae_user["id"])}
        response = client.post(
            "/projects",
            headers=OPS_HEADERS,
            data=payload,
            files={
                "msa_document": ("msa.pdf", b"msa", "application/pdf"),
                "sow_document": ("sow.pdf", b"sow", "application/pdf"),
            },
        )
        assert response.status_code == 201, response.text
        project = response.json()
        assert sorted(document["document_type"] for document in project["documents"]) == ["msa", "sow"]

        update_response = client.put(
            f"/projects/{project['id']}",
            headers=OPS_HEADERS,
            data={"sow_title": "Updated SOW", "sow_amount": "15000.00"},
        )
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["title"] == "Updated SOW"
        assert update_response.json()["sow_amount"] == "15000.00"

        sow_response = client.post(
            f"/projects/{project['id']}/sows",
            headers=OPS_HEADERS,
            data={
                "sow_title": "Second SOW",
                "sow_amount": "5000.00",
                "currency": "USD",
                "start_date": "2026-05-01",
                "operations_manager_name": "Ops Manager",
            },
            files={"sow_document": ("second-sow.pdf", b"sow2", "application/pdf")},
        )
        assert sow_response.status_code == 201, sow_response.text
        assert sow_response.json()["msa_reference"] == PROJECT_PAYLOAD["msa_reference"]


def test_finance_can_cancel_unpaid_invoice():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="Finance Manager", email="finance@example.com", roles=["finance_manager"])
        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]}
        project_response = client.post("/projects", headers=OPS_HEADERS, json=payload)
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        schedule_response = client.post(
            f"/projects/{project['id']}/invoice-schedules",
            headers=OPS_HEADERS,
            json={
                "label": "Single billing",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "single",
                "first_invoice_date": "2026-04-30",
            },
        )
        assert schedule_response.status_code == 201, schedule_response.text
        generated_response = client.post("/invoices/generate?as_of=2026-04-28", headers=ADMIN_HEADERS)
        assert generated_response.status_code == 200, generated_response.text
        invoice_id = generated_response.json()["invoices"][0]["id"]
        cancel_response = client.post(
            f"/client-invoices/{invoice_id}/cancel",
            headers=FINANCE_HEADERS,
            json={"cancelled_by_name": "Finance Manager", "reason": "Client requested cancellation"},
        )
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "cancelled"
