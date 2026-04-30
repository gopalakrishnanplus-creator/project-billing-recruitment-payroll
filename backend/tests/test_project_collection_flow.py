from datetime import date, timedelta
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
        invoices_response = client.get("/client-invoices", headers=FINANCE_HEADERS)
        assert invoices_response.status_code == 200, invoices_response.text
        invoice_id = invoices_response.json()[0]["id"]
        cancel_response = client.post(
            f"/client-invoices/{invoice_id}/cancel",
            headers=FINANCE_HEADERS,
            json={"cancelled_by_name": "Finance Manager", "reason": "Client requested cancellation"},
        )
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "cancelled"
        assert cancel_response.json()["cancelled_amount"] == "4000.00"
        assert cancel_response.json()["balance_due"] == "0.00"


def test_partially_paid_invoice_cancels_only_unpaid_remainder():
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
                "label": "Partial billing",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "single",
                "first_invoice_date": str(date.today()),
            },
        )
        assert schedule_response.status_code == 201, schedule_response.text
        invoice_id = client.get("/client-invoices", headers=FINANCE_HEADERS).json()[0]["id"]
        assert client.post(
            f"/client-invoices/{invoice_id}/client-account-approval",
            headers=CAE_HEADERS,
            json={"approver_name": "Client Account Executive"},
        ).status_code == 200
        assert client.post(
            f"/client-invoices/{invoice_id}/finance-approval",
            headers=FINANCE_HEADERS,
            json={"approver_name": "Finance Manager"},
        ).status_code == 200
        assert client.post(
            f"/client-invoices/{invoice_id}/send",
            headers=FINANCE_HEADERS,
            json={"sender_name": "Finance Manager", "recipient_email": "anita@example.com"},
        ).status_code == 200
        payment_response = client.post(
            f"/client-invoices/{invoice_id}/payments",
            headers=FINANCE_HEADERS,
            json={
                "amount_received": "1000.00",
                "received_date": str(date.today()),
                "recorded_by_name": "Finance Manager",
            },
        )
        assert payment_response.status_code == 201, payment_response.text
        assert payment_response.json()["status"] == "partially_paid"
        cancel_response = client.post(
            f"/client-invoices/{invoice_id}/cancel",
            headers=FINANCE_HEADERS,
            json={"cancelled_by_name": "Finance Manager", "reason": "Client accepted partial close"},
        )
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "partially_paid_remainder_cancelled"
        assert cancel_response.json()["paid_total"] == "1000.00"
        assert cancel_response.json()["cancelled_amount"] == "3000.00"
        assert cancel_response.json()["balance_due"] == "0.00"


def test_due_or_past_invoice_schedule_generates_approval_email_immediately():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="Finance Manager", email="finance@example.com", roles=["finance_manager"])
        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"], "start_date": str(date.today())}
        project_response = client.post("/projects", headers=OPS_HEADERS, json=payload)
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()

        schedule_response = client.post(
            f"/projects/{project['id']}/invoice-schedules",
            headers=OPS_HEADERS,
            json={
                "label": "Immediate billing",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "single",
                "first_invoice_date": str(date.today()),
            },
        )
        assert schedule_response.status_code == 201, schedule_response.text

        invoices_response = client.get("/client-invoices", headers=FINANCE_HEADERS)
        assert invoices_response.status_code == 200, invoices_response.text
        invoices = invoices_response.json()
        assert len(invoices) == 1
        assert invoices[0]["issue_date"] == str(date.today())

        with SessionLocal() as db:
            notification = db.query(EmailNotification).filter(EmailNotification.invoice_id == invoices[0]["id"]).one()
            assert notification.recipient_email == "cae@example.com"
            assert notification.cc_email == "finance@example.com"


def test_invoice_visibility_filters_sorting_and_pagination_by_role():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_one = provision_user(client, full_name="Client Account Executive One", email="cae1@example.com", roles=["client_account_executive"])
        cae_two = provision_user(client, full_name="Client Account Executive Two", email="cae2@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="Finance Manager", email="finance@example.com", roles=["finance_manager"])
        yesterday = date.today() - timedelta(days=1)
        today_value = date.today()

        payload_one = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_one["id"], "client_company_name": "Acme One", "start_date": str(yesterday)}
        payload_two = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_two["id"], "client_company_name": "Acme Two", "start_date": str(today_value)}
        project_one_response = client.post("/projects", headers=OPS_HEADERS, json=payload_one)
        project_two_response = client.post("/projects", headers=OPS_HEADERS, json=payload_two)
        assert project_one_response.status_code == 201, project_one_response.text
        assert project_two_response.status_code == 201, project_two_response.text
        project_one = project_one_response.json()
        project_two = project_two_response.json()

        for project, invoice_date in ((project_one, yesterday), (project_two, today_value)):
            response = client.post(
                f"/projects/{project['id']}/invoice-schedules",
                headers=OPS_HEADERS,
                json={
                    "label": "Single billing",
                    "amount": "4000.00",
                    "currency": "USD",
                    "frequency": "single",
                    "first_invoice_date": str(invoice_date),
                },
            )
            assert response.status_code == 201, response.text

        finance_response = client.get("/client-invoices", headers=FINANCE_HEADERS)
        ops_response = client.get("/client-invoices", headers=OPS_HEADERS)
        cae_one_headers = {"x-test-email": "cae1@example.com", "x-test-role": "client_account_executive"}
        cae_two_headers = {"x-test-email": "cae2@example.com", "x-test-role": "client_account_executive"}
        cae_one_response = client.get("/client-invoices", headers=cae_one_headers)
        assert finance_response.status_code == 200, finance_response.text
        assert ops_response.status_code == 200, ops_response.text
        assert cae_one_response.status_code == 200, cae_one_response.text
        finance_invoices = finance_response.json()
        ops_invoices = ops_response.json()
        cae_one_invoices = cae_one_response.json()

        assert len(finance_invoices) == 2
        assert len(ops_invoices) == 2
        assert {invoice["status"] for invoice in finance_invoices} == {"due_for_client_approval"}
        assert {invoice["status"] for invoice in ops_invoices} == {"due_for_client_approval"}
        assert len(cae_one_invoices) == 1
        assert cae_one_invoices[0]["client_company_name"] == "Acme One"
        assert cae_one_invoices[0]["status"] == "due_for_client_approval"

        cae_one_invoice_id = cae_one_invoices[0]["id"]
        cae_two_invoice_id = next(invoice["id"] for invoice in finance_invoices if invoice["client_company_name"] == "Acme Two")
        assert client.get(f"/client-invoices/{cae_one_invoice_id}", headers=cae_one_headers).status_code == 200
        assert client.get(f"/client-invoices/{cae_two_invoice_id}", headers=cae_one_headers).status_code == 404
        assert client.get(f"/client-invoices/{cae_one_invoice_id}/download", headers=cae_one_headers).status_code == 200
        assert client.get(f"/client-invoices/{cae_two_invoice_id}/download", headers=cae_one_headers).status_code == 404
        wrong_cae_approval = client.post(
            f"/client-invoices/{cae_two_invoice_id}/client-account-approval",
            headers=cae_one_headers,
            json={"approver_name": "Client Account Executive One"},
        )
        assert wrong_cae_approval.status_code == 404
        right_cae_approval = client.post(
            f"/client-invoices/{cae_two_invoice_id}/client-account-approval",
            headers=cae_two_headers,
            json={"approver_name": "Client Account Executive Two"},
        )
        assert right_cae_approval.status_code == 200, right_cae_approval.text

        first_page = client.get("/client-invoices?page_size=1&page=1", headers=FINANCE_HEADERS).json()
        second_page = client.get("/client-invoices?page_size=1&page=2", headers=FINANCE_HEADERS).json()
        assert first_page[0]["issue_date"] == str(yesterday)
        assert second_page[0]["issue_date"] == str(today_value)

        status_filtered = client.get("/client-invoices?status=due_for_client_approval", headers=FINANCE_HEADERS).json()
        approved_filtered = client.get("/client-invoices?status=approved_by_client_account", headers=FINANCE_HEADERS).json()
        date_filtered = client.get(f"/client-invoices?date_from={today_value}&date_to={today_value}", headers=FINANCE_HEADERS).json()
        assert len(status_filtered) == 1
        assert len(approved_filtered) == 1
        assert len(date_filtered) == 1
        assert date_filtered[0]["issue_date"] == str(today_value)
