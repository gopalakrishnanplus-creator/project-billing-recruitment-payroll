from datetime import date, timedelta
import os

os.environ["ALLOW_TEST_AUTH"] = "true"

from app.database import Base, engine
from app import main as app_main
from app.main import app
from app.models import EmailNotification
from app.database import SessionLocal
from fastapi.testclient import TestClient


OPS_HEADERS = {"x-test-email": "ops@example.com", "x-test-role": "operations_manager"}
CAE_HEADERS = {"x-test-email": "cae@example.com", "x-test-role": "client_account_executive"}
FINANCE_HEADERS = {"x-test-email": "finance@example.com", "x-test-role": "finance_manager"}
ADMIN_HEADERS = {"x-test-email": "Gopala.Krishnan@flexgcc.com", "x-test-role": "system_admin"}
HR_HEADERS = {"x-test-email": "hr@example.com", "x-test-role": "hr_manager"}
INTERVIEWER_HEADERS = {"x-test-email": "interviewer@example.com", "x-test-role": "internal_interviewer"}


PROJECT_PAYLOAD = {
    "client_company_name": "Acme Operations",
    "client_billing_address": "2385 NW Executive Center Drive, Suite 240\nBoca Raton, FL 33431",
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


def test_system_admin_can_remove_all_roles_from_provisioned_user():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        user = provision_user(client, full_name="Temporary User", email="temp@example.com", roles=["hr_manager", "finance_manager"])
        assert user["roles"] == ["finance_manager", "hr_manager"]

        remove_one_response = client.post(
            "/users",
            headers=ADMIN_HEADERS,
            json={"full_name": "Temporary User", "email": "temp@example.com", "is_active": True, "roles": ["hr_manager"]},
        )
        assert remove_one_response.status_code == 200, remove_one_response.text
        assert remove_one_response.json()["roles"] == ["hr_manager"]

        remove_final_response = client.post(
            "/users",
            headers=ADMIN_HEADERS,
            json={"full_name": "Temporary User", "email": "temp@example.com", "is_active": True, "roles": []},
        )
        assert remove_final_response.status_code == 200, remove_final_response.text
        assert remove_final_response.json()["roles"] == []

        login_response = client.get("/auth/me", headers={"x-test-email": "temp@example.com", "x-test-role": "hr_manager"})
        assert login_response.status_code == 403
        assert "No roles assigned" in login_response.text


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
        assert "Boca Raton" in project["client_billing_address"]

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
                "item_description": "Monthly outcome pod member X 1",
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
        assert invoices[0]["invoice_number"] == "2026/015"
        assert invoices[0]["item_description"] == "Monthly outcome pod member X 1"

        with SessionLocal() as db:
            notification = db.query(EmailNotification).filter(EmailNotification.invoice_id == invoice_id).one()
            assert notification.recipient_email == "cae@example.com"
            assert notification.cc_email == "finance@example.com"
            assert "Log in to review and approve this invoice" in notification.body
            assert f"/auth/login?approval_invoice_id={invoice_id}" in notification.body

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
        assert download_response.headers["content-type"] == "application/pdf"
        assert download_response.content.startswith(b"%PDF")

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
            data={
                "client_company_name": "Updated Client Company",
                "client_billing_address": "10 Updated Street\nMelbourne, FL 32901",
                "client_contact_name": "Updated Contact",
                "client_contact_email": "updated-contact@example.com",
                "client_contact_phone": "+1-555-9999",
                "sow_title": "Updated SOW",
                "sow_amount": "15000.00",
            },
        )
        assert update_response.status_code == 200, update_response.text
        updated_project = update_response.json()
        assert updated_project["client_company_name"] == "Updated Client Company"
        assert "Updated Street" in updated_project["client_billing_address"]
        assert updated_project["client_contact_name"] == "Updated Contact"
        assert updated_project["client_contact_email"] == "updated-contact@example.com"
        assert updated_project["client_contact_phone"] == "+1-555-9999"
        assert updated_project["title"] == "Updated SOW"
        assert updated_project["sow_amount"] == "15000.00"

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
                "item_description": "Fixed client recruitment fee",
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
                "item_description": "Partial billing line item",
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
                "item_description": "Immediate billing line item",
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
        future_one = today_value + timedelta(days=10)
        future_two = today_value + timedelta(days=20)

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
                    "item_description": f"Single billing for {project['project_code']}",
                    "amount": "4000.00",
                    "currency": "USD",
                    "frequency": "single",
                    "first_invoice_date": str(invoice_date),
                },
            )
            assert response.status_code == 201, response.text
        for project, invoice_date, amount in ((project_one, future_one, "5100.00"), (project_two, future_two, "6200.00")):
            response = client.post(
                f"/projects/{project['id']}/invoice-schedules",
                headers=OPS_HEADERS,
                json={
                    "label": "Upcoming monthly billing",
                    "item_description": f"Upcoming monthly billing for {project['project_code']}",
                    "amount": amount,
                    "currency": "USD",
                    "frequency": "monthly",
                    "first_invoice_date": str(invoice_date),
                    "final_invoice_date": str(invoice_date + timedelta(days=90)),
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

        finance_upcoming = client.get("/upcoming-invoices", headers=FINANCE_HEADERS)
        cae_one_upcoming = client.get("/upcoming-invoices", headers=cae_one_headers)
        assert finance_upcoming.status_code == 200, finance_upcoming.text
        assert cae_one_upcoming.status_code == 200, cae_one_upcoming.text
        assert [invoice["next_invoice_date"] for invoice in finance_upcoming.json()] == [str(future_one), str(future_two)]
        assert finance_upcoming.json()[0]["amount"] == "5100.00"
        assert len(cae_one_upcoming.json()) == 1
        assert cae_one_upcoming.json()[0]["client_company_name"] == "Acme One"

        upcoming_date_filtered = client.get(f"/upcoming-invoices?date_from={future_two}&date_to={future_two}", headers=FINANCE_HEADERS)
        assert upcoming_date_filtered.status_code == 200, upcoming_date_filtered.text
        assert len(upcoming_date_filtered.json()) == 1
        assert upcoming_date_filtered.json()[0]["next_invoice_date"] == str(future_two)

        cae_one_invoice_id = cae_one_invoices[0]["id"]
        cae_two_invoice_id = next(invoice["id"] for invoice in finance_invoices if invoice["client_company_name"] == "Acme Two")
        assert client.get(f"/client-invoices/{cae_one_invoice_id}", headers=cae_one_headers).status_code == 200
        assert client.get(f"/client-invoices/{cae_two_invoice_id}", headers=cae_one_headers).status_code == 404
        assert client.get(f"/client-invoices/{cae_one_invoice_id}/client-account-approval-view", headers=cae_one_headers).status_code == 200
        assert client.get(f"/client-invoices/{cae_two_invoice_id}/client-account-approval-view", headers=cae_one_headers).status_code == 404
        assert client.get(f"/client-invoices/{cae_one_invoice_id}/client-account-approval-view", headers=FINANCE_HEADERS).status_code == 404
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


def test_historical_client_invoice_schedule_starts_from_next_cycle():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="Finance Manager", email="finance@example.com", roles=["finance_manager"])
        project_response = client.post("/projects", headers=OPS_HEADERS, json={**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]})
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        historical_first_invoice = date.today() - timedelta(days=60)
        next_cycle_invoice = date.today() + timedelta(days=29)

        schedule_response = client.post(
            f"/projects/{project['id']}/invoice-schedules",
            headers=OPS_HEADERS,
            json={
                "label": "Historical client billing",
                "item_description": "Historical backfill, next cycle only",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "monthly",
                "first_invoice_date": str(historical_first_invoice),
                "final_invoice_date": str(next_cycle_invoice + timedelta(days=120)),
                "historical_backfill": True,
                "next_invoice_generation_date": str(next_cycle_invoice),
            },
        )
        assert schedule_response.status_code == 201, schedule_response.text
        schedule = schedule_response.json()
        assert schedule["first_invoice_date"] == str(historical_first_invoice)
        assert schedule["historical_backfill"] is True
        assert schedule["next_invoice_generation_date"] == str(next_cycle_invoice)

        invoices_response = client.get("/client-invoices", headers=FINANCE_HEADERS)
        assert invoices_response.status_code == 200, invoices_response.text
        assert invoices_response.json() == []

        upcoming_response = client.get("/upcoming-invoices", headers=FINANCE_HEADERS)
        assert upcoming_response.status_code == 200, upcoming_response.text
        assert len(upcoming_response.json()) == 1
        assert upcoming_response.json()[0]["next_invoice_date"] == str(next_cycle_invoice)

        past_next_cycle_response = client.post(
            f"/projects/{project['id']}/invoice-schedules",
            headers=OPS_HEADERS,
            json={
                "label": "Invalid historical billing",
                "amount": "4000.00",
                "currency": "USD",
                "frequency": "monthly",
                "first_invoice_date": str(historical_first_invoice),
                "historical_backfill": True,
                "next_invoice_generation_date": str(date.today() - timedelta(days=1)),
            },
        )
        assert past_next_cycle_response.status_code == 400
        assert "next current/future cycle" in past_next_cycle_response.text


def test_recruitment_flow_from_position_to_hired_candidate():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="HR Manager", email="hr@example.com", roles=["hr_manager"])
        interviewer = provision_user(client, full_name="Internal Interviewer", email="interviewer@example.com", roles=["internal_interviewer"])
        other_interviewer = provision_user(client, full_name="Other Interviewer", email="other-interviewer@example.com", roles=["internal_interviewer"])

        payload = {**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]}
        project_response = client.post("/projects", headers=OPS_HEADERS, json=payload)
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()

        need_response = client.post(
            f"/projects/{project['id']}/recruitment-needs",
            headers=OPS_HEADERS,
            data={
                "position_title": "Recruitment Analyst",
                "number_of_positions": "2",
                "employment_type": "FTE",
                "description": "Recruitment analyst for client delivery.",
                "position_billing_type": "periodic",
                "fee_amount": "3000.00",
                "currency": "USD",
                "billing_frequency": "monthly",
                "billing_start_date": str(date.today()),
                "billing_end_date": str(date.today() + timedelta(days=90)),
                "target_start_date": str(date.today() + timedelta(days=20)),
                "internal_interviewers": "Internal Interviewer",
            },
            files={"detail_document": ("position.pdf", b"position details", "application/pdf")},
        )
        assert need_response.status_code == 201, need_response.text
        need = need_response.json()
        assert need["detail_document_id"] is not None
        assert need["position_billing_type"] == "periodic"
        assert need["billing_frequency"] == "monthly"

        with SessionLocal() as db:
            notification = db.query(EmailNotification).filter(EmailNotification.project_id == project["id"]).one()
            assert notification.recipient_email == "hr@example.com"
            assert notification.cc_email == "ops@example.com"
            assert "New recruitment position" in notification.subject
            assert f"view=recruitment" in notification.body
            assert f"need_id={need['id']}" in notification.body
            assert "Recruitment Analyst" in notification.body

        update_response = client.put(
            f"/recruitment-needs/{need['id']}",
            headers=OPS_HEADERS,
            data={"position_title": "Senior Recruitment Analyst", "description": "Updated detailed position description."},
        )
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["position_title"] == "Senior Recruitment Analyst"

        needs_response = client.get("/recruitment/needs", headers=HR_HEADERS)
        assert needs_response.status_code == 200, needs_response.text
        assert needs_response.json()[0]["project_code"] == project["project_code"]

        assets_response = client.post(
            f"/recruitment-needs/{need['id']}/assets",
            headers=HR_HEADERS,
            data={"linkedin_ad_url": "https://linkedin.com/jobs/view/123"},
            files={
                "jd_document": ("jd.pdf", b"jd", "application/pdf"),
                "job_ad_document": ("job-ad.pdf", b"ad", "application/pdf"),
            },
        )
        assert assets_response.status_code == 200, assets_response.text
        assert assets_response.json()["jd_document_name"] == "jd.pdf"
        assert assets_response.json()["job_ad_document_name"] == "job-ad.pdf"
        assert assets_response.json()["linkedin_ad_url"] == "https://linkedin.com/jobs/view/123"

        candidate_response = client.post(
            f"/recruitment-needs/{need['id']}/candidates",
            headers=HR_HEADERS,
            json={
                "full_name": "Priya Candidate",
                "email": "priya@example.com",
                "linkedin_profile_url": "https://linkedin.com/in/priya",
            },
        )
        assert candidate_response.status_code == 201, candidate_response.text
        candidate = candidate_response.json()

        status_response = client.patch(
            f"/candidates/{candidate['id']}/status",
            headers=HR_HEADERS,
            json={"status": "shortlisted_for_interview"},
        )
        assert status_response.status_code == 200, status_response.text
        assert status_response.json()["status"] == "shortlisted_for_interview"

        interview_response = client.post(
            f"/candidates/{candidate['id']}/interviews",
            headers=HR_HEADERS,
            json={"interviewer_user_id": interviewer["id"], "calendly_url": "https://calendly.com/internal/priya"},
        )
        assert interview_response.status_code == 201, interview_response.text
        interview = interview_response.json()
        assert interview["interviewer_name"] == "Internal Interviewer"

        with SessionLocal() as db:
            interview_notifications = (
                db.query(EmailNotification)
                .filter(EmailNotification.project_id == project["id"], EmailNotification.subject.like("%interview%"))
                .order_by(EmailNotification.id)
                .all()
            )
            assert [notification.recipient_email for notification in interview_notifications] == ["priya@example.com", "interviewer@example.com"]
            assert all(notification.cc_email == "hr@example.com" for notification in interview_notifications)
            assert "https://calendly.com/internal/priya" in interview_notifications[0].body
            assert f"interview_id={interview['id']}" in interview_notifications[1].body

        own_interviews = client.get("/interviews", headers=INTERVIEWER_HEADERS)
        other_interviews = client.get("/interviews", headers={"x-test-email": "other-interviewer@example.com", "x-test-role": "internal_interviewer"})
        assert own_interviews.status_code == 200, own_interviews.text
        assert len(own_interviews.json()) == 1
        assert other_interviews.status_code == 200, other_interviews.text
        assert other_interviews.json() == []

        scorecard_response = client.post(
            f"/interviews/{interview['id']}/scorecard",
            headers=INTERVIEWER_HEADERS,
            data={"score": "88", "recommendation": "hire", "notes": "Strong candidate."},
            files={"evaluation_checklist": ("scorecard.pdf", b"scorecard", "application/pdf")},
        )
        assert scorecard_response.status_code == 200, scorecard_response.text
        assert scorecard_response.json()["status"] == "completed"
        assert scorecard_response.json()["evaluation_document_name"] == "scorecard.pdf"
        scorecard_document_id = scorecard_response.json()["evaluation_document_id"]

        hr_document_response = client.get(f"/documents/{scorecard_document_id}/download", headers=HR_HEADERS)
        interviewer_document_response = client.get(f"/documents/{scorecard_document_id}/download", headers=INTERVIEWER_HEADERS)
        other_interviewer_document_response = client.get(
            f"/documents/{scorecard_document_id}/download",
            headers={"x-test-email": "other-interviewer@example.com", "x-test-role": "internal_interviewer"},
        )
        assert hr_document_response.status_code == 200, hr_document_response.text
        assert hr_document_response.content == b"scorecard"
        assert hr_document_response.headers["content-type"] == "application/pdf"
        assert interviewer_document_response.status_code == 200, interviewer_document_response.text
        assert other_interviewer_document_response.status_code == 404

        send_contract_response = client.patch(
            f"/candidates/{candidate['id']}/status",
            headers=HR_HEADERS,
            json={"status": "send_contract"},
        )
        assert send_contract_response.status_code == 200, send_contract_response.text
        assert send_contract_response.json()["status"] == "send_contract"

        contract_response = client.post(
            f"/candidates/{candidate['id']}/contract",
            headers=HR_HEADERS,
            data={
                "invoice_terms": "Monthly consultant invoice after client approval.",
                "invoice_amount": "2500.00",
                "currency": "USD",
                "invoice_frequency": "monthly",
                "invoice_start_date": str(date.today()),
                "invoice_end_date": str(date.today() + timedelta(days=90)),
            },
            files={"signed_contract": ("signed-contract.pdf", b"signed", "application/pdf")},
        )
        assert contract_response.status_code == 200, contract_response.text
        hired_candidate = contract_response.json()
        assert hired_candidate["status"] == "hired"
        assert hired_candidate["contracts"][0]["contract_document_name"] == "signed-contract.pdf"
        assert hired_candidate["contracts"][0]["invoice_amount"] == "2500.00"

        candidates_response = client.get("/recruitment/candidates", headers=HR_HEADERS)
        assert candidates_response.status_code == 200, candidates_response.text
        assert candidates_response.json()[0]["interviews"][0]["recommendation"] == "hire"


def test_historical_completed_recruitment_backfill_without_hr_notification():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        cae_user = provision_user(client, full_name="Client Account Executive", email="cae@example.com", roles=["client_account_executive"])
        provision_user(client, full_name="HR Manager", email="hr@example.com", roles=["hr_manager"])
        project_response = client.post("/projects", headers=OPS_HEADERS, json={**PROJECT_PAYLOAD, "client_account_executive_id": cae_user["id"]})
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()

        need_response = client.post(
            f"/projects/{project['id']}/recruitment-needs",
            headers=OPS_HEADERS,
            data={
                "position_title": "Already Recruited Consultant",
                "number_of_positions": "1",
                "employment_type": "Fractional Consultant",
                "description": "Historical backfill for a completed recruitment.",
                "position_billing_type": "periodic",
                "fee_amount": "2500.00",
                "currency": "USD",
                "billing_frequency": "monthly",
                "billing_start_date": "2026-01-01",
                "historical_completed": "on",
            },
        )
        assert need_response.status_code == 201, need_response.text
        need = need_response.json()
        assert need["status"] == "closed"

        with SessionLocal() as db:
            assert db.query(EmailNotification).filter(EmailNotification.project_id == project["id"]).count() == 0

        hire_response = client.post(
            f"/recruitment-needs/{need['id']}/historical-hires",
            headers=OPS_HEADERS,
            data={
                "full_name": "Historical Hire",
                "email": "historical@example.com",
                "phone": "+1-555-7777",
                "invoice_terms": "Monthly candidate invoice.",
                "invoice_amount": "2500.00",
                "currency": "USD",
                "invoice_frequency": "monthly",
                "invoice_start_date": str(date.today() + timedelta(days=29)),
                "invoice_end_date": str(date.today() + timedelta(days=120)),
            },
            files={"signed_contract": ("historical-contract.pdf", b"signed", "application/pdf")},
        )
        assert hire_response.status_code == 201, hire_response.text
        candidate = hire_response.json()
        assert candidate["status"] == "hired"
        assert candidate["position_title"] == "Already Recruited Consultant"
        assert candidate["contracts"][0]["contract_document_name"] == "historical-contract.pdf"
        assert candidate["contracts"][0]["invoice_amount"] == "2500.00"

        past_hire_response = client.post(
            f"/recruitment-needs/{need['id']}/historical-hires",
            headers=OPS_HEADERS,
            data={
                "full_name": "Past Reminder Hire",
                "email": "past-reminder@example.com",
                "invoice_frequency": "monthly",
                "invoice_start_date": str(date.today() - timedelta(days=1)),
            },
        )
        assert past_hire_response.status_code == 400
        assert "next future candidate invoice" in past_hire_response.text


def test_sendgrid_uses_finance_sender_reply_to_and_pdf_attachment(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 202
        text = ""
        headers = {"X-Message-Id": "message-123"}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(app_main, "SENDGRID_API_KEY", "test-key")
    monkeypatch.setattr(app_main, "SENDGRID_FROM_EMAIL", "finance@flexGCC.com")
    monkeypatch.setattr(app_main, "SENDGRID_REPLY_TO_EMAIL", "finance@flexGCC.com")
    monkeypatch.setattr(app_main.httpx, "post", fake_post)

    status, detail = app_main.send_sendgrid_email(
        to_email="client@example.com",
        cc_emails=["finance@example.com"],
        subject="Invoice 2026/015 from FlexGCC",
        text="Invoice attached.",
        html="<p>Invoice attached.</p>",
        attachments=[
            {
                "content": "JVBERi0xLjQ=",
                "filename": "2026-015.pdf",
                "type": "application/pdf",
                "disposition": "attachment",
            }
        ],
    )

    assert status == "sent"
    assert detail == "message-123"
    assert captured["json"]["from"]["email"] == "finance@flexGCC.com"
    assert captured["json"]["reply_to"]["email"] == "finance@flexGCC.com"
    assert captured["json"]["attachments"][0]["filename"] == "2026-015.pdf"
    assert captured["json"]["attachments"][0]["type"] == "application/pdf"


def test_sendgrid_omits_empty_duplicate_cc(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 202
        text = ""
        headers = {}

    def fake_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(app_main, "SENDGRID_API_KEY", "test-key")
    monkeypatch.setattr(app_main.httpx, "post", fake_post)

    status, _ = app_main.send_sendgrid_email(
        to_email="hr@example.com",
        cc_emails=["", "hr@example.com", "hr@example.com"],
        subject="New recruitment position",
        text="Body",
        html="<p>Body</p>",
    )

    assert status == "sent"
    assert "cc" not in captured["json"]["personalizations"][0]
