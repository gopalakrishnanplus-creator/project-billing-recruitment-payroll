from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from os import getenv

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_db
from .models import (
    ActivityLog,
    ClientCompany,
    ClientContact,
    ClientInvoice,
    ClientInvoiceApproval,
    ClientInvoiceSchedule,
    ClientPayment,
    EmailNotification,
    InvoiceStatus,
    MasterServiceAgreement,
    ProjectSOW,
    RecruitmentNeed,
    UploadedDocument,
    utcnow,
)
from .schemas import (
    ApprovalCreate,
    ClientInvoiceRead,
    GenerateInvoicesResult,
    InvoiceDetailRead,
    InvoiceScheduleCreate,
    InvoiceScheduleRead,
    PaymentCreate,
    PaymentRead,
    ProjectCreate,
    ProjectRead,
    RecruitmentNeedCreate,
    RecruitmentNeedRead,
    SendInvoiceCreate,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Project Billing Recruitment Payroll API", version="0.1.0", lifespan=lifespan)

origins = [origin.strip() for origin in getenv("CORS_ORIGINS", "http://127.0.0.1:5174,http://localhost:5174").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def project_code(db: Session) -> str:
    year = date.today().year
    count = db.scalar(select(func.count(ProjectSOW.id))) or 0
    return f"PBRP-{year}-{count + 1:04d}"


def log_event(db: Session, *, project_id: int | None, invoice_id: int | None = None, actor_name: str, action: str, details: str | None = None) -> None:
    db.add(ActivityLog(project_id=project_id, invoice_id=invoice_id, actor_name=actor_name, action=action, details=details))


def serialize_project(project: ProjectSOW) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        project_code=project.project_code,
        title=project.title,
        description=project.description,
        sow_amount=project.sow_amount,
        currency=project.currency,
        start_date=project.start_date,
        end_date=project.end_date,
        operations_manager_name=project.operations_manager_name,
        status=project.status,
        client_company_name=project.company.name,
        client_contact_name=project.client_contact.full_name,
        client_contact_email=project.client_contact.email,
        msa_reference=project.msa.reference if project.msa else None,
        recruitment_needs=[RecruitmentNeedRead.model_validate(need) for need in project.recruitment_needs],
        invoice_schedules=[InvoiceScheduleRead.model_validate(schedule) for schedule in project.invoice_schedules],
        client_invoices=[ClientInvoiceRead.model_validate(invoice) for invoice in project.client_invoices],
    )


def serialize_invoice(invoice: ClientInvoice) -> InvoiceDetailRead:
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00"))
    balance_due = max(invoice.amount - paid_total, Decimal("0.00"))
    return InvoiceDetailRead(
        id=invoice.id,
        project_id=invoice.project_id,
        schedule_id=invoice.schedule_id,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        amount=invoice.amount,
        currency=invoice.currency,
        status=invoice.status,
        sent_at=invoice.sent_at,
        project_code=invoice.project.project_code,
        project_title=invoice.project.title,
        client_company_name=invoice.project.company.name,
        client_contact_name=invoice.project.client_contact.full_name,
        client_contact_email=invoice.project.client_contact.email,
        payments=[PaymentRead.model_validate(payment) for payment in invoice.payments],
        paid_total=paid_total,
        balance_due=balance_due,
    )


def next_date(current: date, frequency: str) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "quarterly":
        return add_months(current, 3)
    if frequency == "monthly":
        return add_months(current, 1)
    return current


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    month_end = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(value.day, month_end))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/schema/overview")
def schema_overview() -> dict[str, list[str]]:
    return {
        "implemented_flow_tables": [
            "client_companies",
            "client_contacts",
            "master_service_agreements",
            "project_sows",
            "uploaded_documents",
            "recruitment_needs",
            "client_invoice_schedules",
            "client_invoices",
            "client_invoice_approvals",
            "client_payments",
            "email_notifications",
            "activity_logs",
        ],
        "reserved_later_flow_tables": [
            "app_users",
            "candidates",
            "candidate_screening_forms",
            "candidate_evaluations",
            "interviews",
            "interview_scorecards",
            "candidate_contracts",
            "candidate_vendor_invoices",
            "candidate_invoice_approvals",
            "candidate_payments",
            "agent_tasks",
        ],
    }


@app.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    company = db.scalar(select(ClientCompany).where(ClientCompany.name == payload.client_company_name))
    if company is None:
        company = ClientCompany(name=payload.client_company_name)
        db.add(company)
        db.flush()

    contact = ClientContact(
        company_id=company.id,
        full_name=payload.client_contact_name,
        email=str(payload.client_contact_email),
        phone=payload.client_contact_phone,
    )
    db.add(contact)
    db.flush()

    msa_document = None
    if payload.msa_document_name:
        msa_document = UploadedDocument(document_type="msa", original_filename=payload.msa_document_name, uploaded_by_name=payload.operations_manager_name)
        db.add(msa_document)
        db.flush()

    msa = MasterServiceAgreement(company_id=company.id, reference=payload.msa_reference, document_id=msa_document.id if msa_document else None)
    db.add(msa)
    db.flush()

    project = ProjectSOW(
        project_code=project_code(db),
        company_id=company.id,
        client_contact_id=contact.id,
        msa_id=msa.id,
        title=payload.sow_title,
        description=payload.sow_description,
        sow_amount=payload.sow_amount,
        currency=payload.currency.upper(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        operations_manager_name=payload.operations_manager_name,
    )
    db.add(project)
    db.flush()

    if msa_document:
        msa_document.project_id = project.id
    if payload.sow_document_name:
        db.add(UploadedDocument(project_id=project.id, document_type="sow", original_filename=payload.sow_document_name, uploaded_by_name=payload.operations_manager_name))

    log_event(db, project_id=project.id, actor_name=payload.operations_manager_name, action="project_created", details=f"Created {project.project_code}")
    db.commit()
    db.refresh(project)
    project = db.scalar(
        select(ProjectSOW)
        .where(ProjectSOW.id == project.id)
        .options(
            selectinload(ProjectSOW.company),
            selectinload(ProjectSOW.client_contact),
            selectinload(ProjectSOW.msa),
            selectinload(ProjectSOW.recruitment_needs),
            selectinload(ProjectSOW.invoice_schedules),
            selectinload(ProjectSOW.client_invoices),
        )
    )
    assert project is not None
    return serialize_project(project)


@app.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.scalars(
        select(ProjectSOW)
        .order_by(ProjectSOW.created_at.desc())
        .options(
            selectinload(ProjectSOW.company),
            selectinload(ProjectSOW.client_contact),
            selectinload(ProjectSOW.msa),
            selectinload(ProjectSOW.recruitment_needs),
            selectinload(ProjectSOW.invoice_schedules),
            selectinload(ProjectSOW.client_invoices),
        )
    ).all()
    return [serialize_project(project) for project in projects]


@app.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = db.scalar(
        select(ProjectSOW)
        .where(ProjectSOW.id == project_id)
        .options(
            selectinload(ProjectSOW.company),
            selectinload(ProjectSOW.client_contact),
            selectinload(ProjectSOW.msa),
            selectinload(ProjectSOW.recruitment_needs),
            selectinload(ProjectSOW.invoice_schedules),
            selectinload(ProjectSOW.client_invoices),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_project(project)


@app.post("/projects/{project_id}/recruitment-needs", response_model=RecruitmentNeedRead, status_code=201)
def add_recruitment_need(project_id: int, payload: RecruitmentNeedCreate, db: Session = Depends(get_db)) -> RecruitmentNeedRead:
    project = db.get(ProjectSOW, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    need = RecruitmentNeed(project_id=project_id, **payload.model_dump())
    db.add(need)
    log_event(db, project_id=project_id, actor_name=project.operations_manager_name, action="recruitment_need_added", details=payload.position_title)
    db.commit()
    db.refresh(need)
    return RecruitmentNeedRead.model_validate(need)


@app.post("/projects/{project_id}/invoice-schedules", response_model=InvoiceScheduleRead, status_code=201)
def add_invoice_schedule(project_id: int, payload: InvoiceScheduleCreate, db: Session = Depends(get_db)) -> InvoiceScheduleRead:
    project = db.get(ProjectSOW, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.final_invoice_date and payload.final_invoice_date < payload.first_invoice_date:
        raise HTTPException(status_code=400, detail="Final invoice date cannot be earlier than first invoice date")
    schedule = ClientInvoiceSchedule(project_id=project_id, **payload.model_dump())
    db.add(schedule)
    log_event(db, project_id=project_id, actor_name=project.operations_manager_name, action="invoice_schedule_added", details=payload.label)
    db.commit()
    db.refresh(schedule)
    return InvoiceScheduleRead.model_validate(schedule)


@app.post("/invoices/generate", response_model=GenerateInvoicesResult)
def generate_due_invoices(as_of: date = Query(default_factory=date.today), db: Session = Depends(get_db)) -> GenerateInvoicesResult:
    schedules = db.scalars(select(ClientInvoiceSchedule).where(ClientInvoiceSchedule.status == "active")).all()
    generated: list[ClientInvoice] = []

    for schedule in schedules:
        candidate_date = schedule.first_invoice_date
        while candidate_date <= as_of:
            if schedule.final_invoice_date and candidate_date > schedule.final_invoice_date:
                break
            exists = db.scalar(
                select(ClientInvoice).where(
                    ClientInvoice.schedule_id == schedule.id,
                    ClientInvoice.issue_date == candidate_date,
                )
            )
            if exists is None:
                invoice = ClientInvoice(
                    schedule_id=schedule.id,
                    project_id=schedule.project_id,
                    invoice_number=f"INV-{schedule.project_id:04d}-{schedule.id:04d}-{candidate_date.strftime('%Y%m%d')}",
                    issue_date=candidate_date,
                    due_date=candidate_date + timedelta(days=7),
                    amount=schedule.amount,
                    currency=schedule.currency,
                    status=InvoiceStatus.due_for_client_approval.value,
                )
                db.add(invoice)
                generated.append(invoice)
                log_event(db, project_id=schedule.project_id, actor_name="System", action="client_invoice_generated", details=invoice.invoice_number)
            if schedule.frequency == "single":
                break
            candidate_date = next_date(candidate_date, schedule.frequency)

    db.commit()
    for invoice in generated:
        db.refresh(invoice)
    return GenerateInvoicesResult(generated_count=len(generated), invoices=[ClientInvoiceRead.model_validate(invoice) for invoice in generated])


@app.get("/client-invoices", response_model=list[InvoiceDetailRead])
def list_invoices(db: Session = Depends(get_db)) -> list[InvoiceDetailRead]:
    invoices = db.scalars(
        select(ClientInvoice)
        .order_by(ClientInvoice.issue_date.desc(), ClientInvoice.id.desc())
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.payments),
        )
    ).all()
    return [serialize_invoice(invoice) for invoice in invoices]


@app.get("/client-invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.payments),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_invoice(invoice)


@app.post("/client-invoices/{invoice_id}/client-account-approval", response_model=InvoiceDetailRead)
def approve_client_account(invoice_id: int, payload: ApprovalCreate, db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.get(ClientInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in {InvoiceStatus.due_for_client_approval.value, InvoiceStatus.draft.value}:
        raise HTTPException(status_code=400, detail=f"Invoice is not ready for client account approval: {invoice.status}")
    invoice.status = InvoiceStatus.approved_by_client_account.value
    db.add(ClientInvoiceApproval(invoice_id=invoice_id, approval_type="client_account_executive", approver_name=payload.approver_name, decision="approved", notes=payload.notes))
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.approver_name, action="client_account_approved_invoice")
    db.commit()
    return get_invoice(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/finance-approval", response_model=InvoiceDetailRead)
def approve_finance(invoice_id: int, payload: ApprovalCreate, db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.get(ClientInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.approved_by_client_account.value:
        raise HTTPException(status_code=400, detail=f"Invoice must be client-account approved before finance approval: {invoice.status}")
    invoice.status = InvoiceStatus.approved_for_sending.value
    db.add(ClientInvoiceApproval(invoice_id=invoice_id, approval_type="finance_manager", approver_name=payload.approver_name, decision="approved", notes=payload.notes))
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.approver_name, action="finance_approved_invoice")
    db.commit()
    return get_invoice(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/send", response_model=InvoiceDetailRead)
def send_invoice(invoice_id: int, payload: SendInvoiceCreate, db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact))
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.approved_for_sending.value:
        raise HTTPException(status_code=400, detail=f"Invoice must be finance-approved before sending: {invoice.status}")
    recipient = str(payload.recipient_email) if payload.recipient_email else invoice.project.client_contact.email
    invoice.status = InvoiceStatus.sent_to_client.value
    invoice.sent_at = utcnow()
    db.add(
        EmailNotification(
            project_id=invoice.project_id,
            invoice_id=invoice.id,
            recipient_email=recipient,
            subject=f"Invoice {invoice.invoice_number}",
            body=f"Invoice {invoice.invoice_number} for {invoice.currency} {invoice.amount} is ready for payment.",
            status="sent",
        )
    )
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.sender_name, action="invoice_sent_to_client", details=recipient)
    db.commit()
    return get_invoice(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/payments", response_model=InvoiceDetailRead, status_code=201)
def record_payment(invoice_id: int, payload: PaymentCreate, db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(select(ClientInvoice).where(ClientInvoice.id == invoice_id).options(selectinload(ClientInvoice.payments)))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in {InvoiceStatus.sent_to_client.value, InvoiceStatus.partially_paid.value, InvoiceStatus.paid.value}:
        raise HTTPException(status_code=400, detail=f"Invoice must be sent before payment can be recorded: {invoice.status}")
    payment = ClientPayment(invoice_id=invoice_id, **payload.model_dump())
    db.add(payment)
    db.flush()
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00")) + payload.amount_received
    invoice.status = InvoiceStatus.paid.value if paid_total >= invoice.amount else InvoiceStatus.partially_paid.value
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.recorded_by_name, action="client_payment_recorded", details=str(payload.amount_received))
    db.commit()
    return get_invoice(invoice_id, db)
