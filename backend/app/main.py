from contextlib import asynccontextmanager
import base64
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
from os import getenv
from pathlib import Path
import re
from urllib.parse import urlencode
from uuid import uuid4

from authlib.integrations.starlette_client import OAuth
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .database import Base, SessionLocal, engine, get_db
from .models import (
    ActivityLog,
    AppUser,
    Candidate,
    CandidateContract,
    ClientCompany,
    ClientContact,
    ClientInvoice,
    ClientInvoiceApproval,
    ClientInvoiceSchedule,
    ClientPayment,
    EmailNotification,
    Interview,
    InterviewScorecard,
    InvoiceStatus,
    MasterServiceAgreement,
    ProjectSOW,
    RecruitmentNeed,
    UploadedDocument,
    UserRole,
    UserRoleAssignment,
    utcnow,
)
from .schemas import (
    ApprovalCreate,
    AppUserRead,
    AppUserUpsert,
    CancelInvoiceCreate,
    CandidateContractCreate,
    CandidateContractRead,
    CandidateCreate,
    CandidateRead,
    CandidateStatusUpdate,
    ClientInvoiceRead,
    CurrentUserRead,
    GenerateInvoicesResult,
    HistoricalHireCreate,
    InvoiceDetailRead,
    InvoiceScheduleCreate,
    InvoiceScheduleRead,
    PaymentCreate,
    PaymentRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    RecruitmentAssetCreate,
    RecruitmentNeedCreate,
    RecruitmentNeedDetailRead,
    RecruitmentNeedRead,
    RecruitmentNeedUpdate,
    RoleSelect,
    ScorecardCreate,
    SendInvoiceCreate,
    InterviewCreate,
    InterviewRead,
    SOWCreate,
    UpcomingInvoiceRead,
)


VALID_ROLES = {role.value for role in UserRole}
SYSTEM_ADMIN_EMAIL = getenv("SYSTEM_ADMIN_EMAIL", "Gopala.Krishnan@flexgcc.com").lower()
FRONTEND_URL = getenv("FRONTEND_URL", "http://127.0.0.1:5174")
API_BASE_URL = getenv("API_BASE_URL", "http://127.0.0.1:8001")
SESSION_SECRET = getenv("SESSION_SECRET", "local-dev-session-secret")
ALLOW_TEST_AUTH = getenv("ALLOW_TEST_AUTH", "false").lower() == "true"
GOOGLE_CONFIGURED = bool(getenv("GOOGLE_CLIENT_ID") and getenv("GOOGLE_CLIENT_SECRET"))
UPLOAD_DIR = Path(getenv("UPLOAD_DIR", "uploaded_files"))
SENDGRID_API_KEY = getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = getenv("SENDGRID_FROM_EMAIL", "finance@flexGCC.com")
SENDGRID_REPLY_TO_EMAIL = getenv("SENDGRID_REPLY_TO_EMAIL", "finance@flexGCC.com")
SENDGRID_FROM_NAME = getenv("SENDGRID_FROM_NAME", "FlexGCC PBRP")
FINANCE_MANAGER_EMAIL = getenv("FINANCE_MANAGER_EMAIL", "")
INVOICE_CRON_TOKEN = getenv("INVOICE_CRON_TOKEN", "")
INVOICE_SERIAL_START = int(getenv("INVOICE_SERIAL_START", "15"))
INVOICE_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "invoice_logo.png"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_auth_columns()
    ensure_workflow_columns()
    with SessionLocal() as db:
        seed_system_admin(db)
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
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site=getenv("SESSION_SAME_SITE", "none"),
    https_only=getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
)

oauth = OAuth()
if GOOGLE_CONFIGURED:
    oauth.register(
        name="google",
        client_id=getenv("GOOGLE_CLIENT_ID"),
        client_secret=getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@dataclass
class AuthContext:
    user: AppUser
    roles: list[str]
    active_role: str | None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def ensure_auth_columns() -> None:
    inspector = inspect(engine)
    if "app_users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("app_users")}
    with engine.begin() as conn:
        if "google_sub" not in existing:
            conn.execute(text("ALTER TABLE app_users ADD COLUMN google_sub VARCHAR(255)"))
        if "last_login_at" not in existing:
            conn.execute(text("ALTER TABLE app_users ADD COLUMN last_login_at TIMESTAMP"))


def ensure_workflow_columns() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    def add_column(conn, table: str, existing_columns: set[str], name: str, definition: str) -> None:
        if name not in existing_columns:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
            existing_columns.add(name)

    with engine.begin() as conn:
        if "project_sows" in tables:
            existing = {column["name"] for column in inspector.get_columns("project_sows")}
            add_column(conn, "project_sows", existing, "client_account_executive_id", "INTEGER")
        if "client_companies" in tables:
            existing = {column["name"] for column in inspector.get_columns("client_companies")}
            add_column(conn, "client_companies", existing, "billing_address", "TEXT")
        if "client_invoice_schedules" in tables:
            existing = {column["name"] for column in inspector.get_columns("client_invoice_schedules")}
            add_column(conn, "client_invoice_schedules", existing, "item_description", "TEXT")
            add_column(conn, "client_invoice_schedules", existing, "historical_backfill", "BOOLEAN DEFAULT FALSE")
            add_column(conn, "client_invoice_schedules", existing, "next_invoice_generation_date", "DATE")
        if "client_invoices" in tables:
            existing = {column["name"] for column in inspector.get_columns("client_invoices")}
            add_column(conn, "client_invoices", existing, "item_description", "TEXT")
        if "uploaded_documents" in tables:
            existing = {column["name"] for column in inspector.get_columns("uploaded_documents")}
            add_column(conn, "uploaded_documents", existing, "stored_filename", "VARCHAR(255)")
            add_column(conn, "uploaded_documents", existing, "content_type", "VARCHAR(120)")
            add_column(conn, "uploaded_documents", existing, "file_size", "INTEGER")
            column_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
            add_column(conn, "uploaded_documents", existing, "content_bytes", column_type)
        if "recruitment_needs" in tables:
            existing = {column["name"] for column in inspector.get_columns("recruitment_needs")}
            for name, definition in {
                "position_billing_type": "VARCHAR(40)",
                "fee_amount": "NUMERIC(12, 2)",
                "currency": "VARCHAR(12)",
                "billing_frequency": "VARCHAR(40)",
                "billing_start_date": "DATE",
                "billing_end_date": "DATE",
                "detail_document_id": "INTEGER",
                "jd_document_id": "INTEGER",
                "job_ad_document_id": "INTEGER",
                "linkedin_ad_url": "VARCHAR(500)",
                "jd_uploaded_at": "TIMESTAMP",
            }.items():
                add_column(conn, "recruitment_needs", existing, name, definition)
        if "candidates" in tables:
            existing = {column["name"] for column in inspector.get_columns("candidates")}
            add_column(conn, "candidates", existing, "linkedin_profile_url", "VARCHAR(500)")
            add_column(conn, "candidates", existing, "notes", "TEXT")
        if "interviews" in tables:
            existing = {column["name"] for column in inspector.get_columns("interviews")}
            add_column(conn, "interviews", existing, "interviewer_user_id", "INTEGER")
        if "interview_scorecards" in tables:
            existing = {column["name"] for column in inspector.get_columns("interview_scorecards")}
            add_column(conn, "interview_scorecards", existing, "evaluation_document_id", "INTEGER")
        if "candidate_contracts" in tables:
            existing = {column["name"] for column in inspector.get_columns("candidate_contracts")}
            for name, definition in {
                "invoice_amount": "NUMERIC(12, 2)",
                "currency": "VARCHAR(12)",
                "invoice_frequency": "VARCHAR(40)",
                "invoice_start_date": "DATE",
                "invoice_end_date": "DATE",
                "invoice_date": "DATE",
            }.items():
                add_column(conn, "candidate_contracts", existing, name, definition)
        if "email_notifications" in tables:
            existing = {column["name"] for column in inspector.get_columns("email_notifications")}
            add_column(conn, "email_notifications", existing, "cc_email", "TEXT")


def seed_system_admin(db: Session) -> None:
    admin = db.scalar(select(AppUser).where(func.lower(AppUser.email) == SYSTEM_ADMIN_EMAIL))
    if admin is None:
        admin = AppUser(full_name="Gopala Krishnan", email=SYSTEM_ADMIN_EMAIL, role=UserRole.system_admin.value, is_active=True)
        db.add(admin)
        db.flush()
    admin.is_active = True
    admin.role = UserRole.system_admin.value
    db.flush()
    backfill_primary_roles(db)
    db.commit()


def backfill_primary_roles(db: Session) -> None:
    users = db.scalars(select(AppUser).options(selectinload(AppUser.role_assignments))).all()
    for user in users:
        if user.role in VALID_ROLES and not any(assignment.role == user.role for assignment in user.role_assignments):
            ensure_role_assignment(db, user, user.role, "System")


def ensure_role_assignment(db: Session, user: AppUser, role: str, assigned_by_name: str | None) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    exists = db.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role == role))
    if exists is None:
        db.add(UserRoleAssignment(user_id=user.id, role=role, assigned_by_name=assigned_by_name))


def user_roles(user: AppUser) -> list[str]:
    roles = sorted({assignment.role for assignment in user.role_assignments if assignment.role in VALID_ROLES})
    if not roles and user.role in VALID_ROLES:
        roles = [user.role]
    return roles


def serialize_user(user: AppUser) -> AppUserRead:
    return AppUserRead(id=user.id, full_name=user.full_name, email=user.email, is_active=user.is_active, roles=user_roles(user))


def users_with_role(db: Session, role: str) -> list[AppUser]:
    return db.scalars(
        select(AppUser)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == AppUser.id)
        .where(AppUser.is_active.is_(True), UserRoleAssignment.role == role)
        .order_by(AppUser.full_name)
        .options(selectinload(AppUser.role_assignments))
    ).all()


def validate_client_account_executive(db: Session, user_id: int | None) -> AppUser | None:
    if user_id is None:
        return None
    user = db.scalar(select(AppUser).where(AppUser.id == user_id, AppUser.is_active.is_(True)).options(selectinload(AppUser.role_assignments)))
    if user is None or UserRole.client_account_executive.value not in user_roles(user):
        raise HTTPException(status_code=400, detail="Select an active Client Account Executive")
    return user


def auth_context_from_session(request: Request, db: Session) -> AuthContext:
    test_email = request.headers.get("x-test-email")
    test_role = request.headers.get("x-test-role")
    if ALLOW_TEST_AUTH and test_email and test_role:
        email = normalize_email(test_email)
        user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email).options(selectinload(AppUser.role_assignments)))
        if user is None:
            user = AppUser(full_name="Test User", email=email, role=test_role, is_active=True)
            db.add(user)
            db.flush()
        ensure_role_assignment(db, user, test_role, "Test")
        db.commit()
        db.refresh(user)
        return AuthContext(user=user, roles=user_roles(user), active_role=test_role)

    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    user = db.scalar(select(AppUser).where(AppUser.id == user_id).options(selectinload(AppUser.role_assignments)))
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=403, detail="User is not active")
    roles = user_roles(user)
    if not roles:
        raise HTTPException(status_code=403, detail="No roles assigned")
    active_role = request.session.get("active_role")
    if active_role and active_role not in roles:
        request.session.pop("active_role", None)
        active_role = None
    return AuthContext(user=user, roles=roles, active_role=active_role)


def require_login(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    return auth_context_from_session(request, db)


def require_role(*allowed_roles: str):
    def dependency(request: Request, db: Session = Depends(get_db)) -> AuthContext:
        context = auth_context_from_session(request, db)
        if context.active_role is None:
            raise HTTPException(status_code=403, detail="Select a role before continuing")
        if context.active_role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Active role cannot perform this action: {context.active_role}")
        return context

    return dependency


def project_code(db: Session) -> str:
    year = date.today().year
    count = db.scalar(select(func.count(ProjectSOW.id))) or 0
    return f"PBRP-{year}-{count + 1:04d}"


def next_invoice_number(db: Session, invoice_date: date) -> str:
    prefix = f"{invoice_date.year}/"
    invoice_numbers = db.scalars(select(ClientInvoice.invoice_number).where(ClientInvoice.invoice_number.like(f"{prefix}%"))).all()
    max_serial = INVOICE_SERIAL_START - 1
    for invoice_number in invoice_numbers:
        match = re.fullmatch(rf"{invoice_date.year}/(\d+)", invoice_number or "")
        if match:
            max_serial = max(max_serial, int(match.group(1)))
    return f"{invoice_date.year}/{max_serial + 1:03d}"


def log_event(db: Session, *, project_id: int | None, invoice_id: int | None = None, actor_name: str, action: str, details: str | None = None) -> None:
    db.add(ActivityLog(project_id=project_id, invoice_id=invoice_id, actor_name=actor_name, action=action, details=details))


def parse_model(model_class, data: dict[str, object]):
    try:
        return model_class(**data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


async def request_payload_and_files(request: Request) -> tuple[dict[str, object], dict[str, UploadFile]]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        data: dict[str, object] = {}
        files: dict[str, UploadFile] = {}
        for key, value in form.multi_items():
            if isinstance(value, UploadFile) or (hasattr(value, "filename") and hasattr(value, "read")):
                if value.filename:
                    files[key] = value
            elif value != "":
                data[key] = value
        return data, files
    return await request.json(), {}


async def save_uploaded_document(
    db: Session,
    *,
    file: UploadFile | None,
    project_id: int | None,
    document_type: str,
    uploaded_by_name: str | None,
) -> UploadedDocument | None:
    if file is None or not file.filename:
        return None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_filename = Path(file.filename).name
    stored_filename = f"{uuid4().hex}-{original_filename}"
    target = UPLOAD_DIR / stored_filename
    content = await file.read()
    target.write_bytes(content)
    document = UploadedDocument(
        project_id=project_id,
        document_type=document_type,
        original_filename=original_filename,
        storage_uri=str(target),
        stored_filename=stored_filename,
        content_type=file.content_type,
        file_size=len(content),
        content_bytes=content,
        uploaded_by_name=uploaded_by_name,
    )
    db.add(document)
    db.flush()
    return document


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
        client_billing_address=project.company.billing_address,
        client_contact_name=project.client_contact.full_name,
        client_contact_email=project.client_contact.email,
        client_contact_phone=project.client_contact.phone,
        client_account_executive_id=project.client_account_executive_id,
        client_account_executive_name=project.client_account_executive.full_name if project.client_account_executive else None,
        client_account_executive_email=project.client_account_executive.email if project.client_account_executive else None,
        msa_reference=project.msa.reference if project.msa else None,
        documents=project.documents,
        recruitment_needs=[RecruitmentNeedRead.model_validate(need) for need in project.recruitment_needs],
        invoice_schedules=[InvoiceScheduleRead.model_validate(schedule) for schedule in project.invoice_schedules],
        client_invoices=[ClientInvoiceRead.model_validate(invoice) for invoice in project.client_invoices],
    )


def serialize_invoice(invoice: ClientInvoice) -> InvoiceDetailRead:
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00"))
    open_balance = max(invoice.amount - paid_total, Decimal("0.00"))
    cancelled_amount = open_balance if invoice.status in {InvoiceStatus.cancelled.value, InvoiceStatus.partially_paid_remainder_cancelled.value} else Decimal("0.00")
    balance_due = Decimal("0.00") if cancelled_amount else open_balance
    return InvoiceDetailRead(
        id=invoice.id,
        project_id=invoice.project_id,
        schedule_id=invoice.schedule_id,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        item_description=invoice.item_description,
        amount=invoice.amount,
        currency=invoice.currency,
        status=invoice.status,
        sent_at=invoice.sent_at,
        project_code=invoice.project.project_code,
        project_title=invoice.project.title,
        client_company_name=invoice.project.company.name,
        client_billing_address=invoice.project.company.billing_address,
        client_contact_name=invoice.project.client_contact.full_name,
        client_contact_email=invoice.project.client_contact.email,
        client_account_executive_email=invoice.project.client_account_executive.email if invoice.project.client_account_executive else None,
        payments=[PaymentRead.model_validate(payment) for payment in invoice.payments],
        paid_total=paid_total,
        cancelled_amount=cancelled_amount,
        balance_due=balance_due,
    )


def serialize_upcoming_invoice(schedule: ClientInvoiceSchedule, next_invoice_date: date) -> UpcomingInvoiceRead:
    return UpcomingInvoiceRead(
        schedule_id=schedule.id,
        project_id=schedule.project_id,
        project_code=schedule.project.project_code,
        project_title=schedule.project.title,
        client_company_name=schedule.project.company.name,
        client_account_executive_email=schedule.project.client_account_executive.email if schedule.project.client_account_executive else None,
        label=schedule.label,
        item_description=schedule.item_description,
        amount=schedule.amount,
        currency=schedule.currency,
        frequency=schedule.frequency,
        next_invoice_date=next_invoice_date,
        final_invoice_date=schedule.final_invoice_date,
    )


def authorize_invoice_visibility(invoice: ClientInvoice, context: AuthContext) -> None:
    if (
        context.active_role == UserRole.client_account_executive.value
        and invoice.project.client_account_executive_id != context.user.id
    ):
        raise HTTPException(status_code=404, detail="Invoice not found")


def authorize_client_account_invoice_approval(invoice: ClientInvoice, context: AuthContext) -> None:
    if (
        UserRole.client_account_executive.value not in context.roles
        or invoice.project.client_account_executive_id != context.user.id
    ):
        raise HTTPException(status_code=404, detail="Invoice not found")


def load_invoice_detail(invoice_id: int, db: Session, context: AuthContext | None = None) -> InvoiceDetailRead:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoice.payments),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if context is not None:
        authorize_invoice_visibility(invoice, context)
    return serialize_invoice(invoice)


def next_date(current: date, frequency: str) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "quarterly":
        return add_months(current, 3)
    if frequency == "monthly":
        return add_months(current, 1)
    return current


def next_unraised_invoice_date(schedule: ClientInvoiceSchedule) -> date | None:
    issued_dates = {invoice.issue_date for invoice in schedule.invoices}
    candidate_date = schedule.next_invoice_generation_date or schedule.first_invoice_date
    for _ in range(600):
        if schedule.final_invoice_date and candidate_date > schedule.final_invoice_date:
            return None
        if candidate_date not in issued_dates:
            return candidate_date
        if schedule.frequency == "single":
            return None
        candidate_date = next_date(candidate_date, schedule.frequency)
    return None


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    month_end = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(value.day, month_end))


def project_options():
    return (
        selectinload(ProjectSOW.company),
        selectinload(ProjectSOW.client_contact),
        selectinload(ProjectSOW.client_account_executive),
        selectinload(ProjectSOW.msa),
        selectinload(ProjectSOW.documents),
        selectinload(ProjectSOW.recruitment_needs),
        selectinload(ProjectSOW.invoice_schedules),
        selectinload(ProjectSOW.client_invoices),
    )


def load_project_for_read(project_id: int, db: Session) -> ProjectSOW:
    project = db.scalar(select(ProjectSOW).where(ProjectSOW.id == project_id).options(*project_options()))
    if project is None:
        raise HTTPException(status_code=404, detail="Project/SOW not found")
    return project


def document_name(db: Session, document_id: int | None) -> str | None:
    if document_id is None:
        return None
    document = db.get(UploadedDocument, document_id)
    return document.original_filename if document else None


def serialize_recruitment_need_detail(need: RecruitmentNeed, db: Session) -> RecruitmentNeedDetailRead:
    project = load_project_for_read(need.project_id, db)
    return RecruitmentNeedDetailRead(
        **RecruitmentNeedRead.model_validate(need).model_dump(),
        project_code=project.project_code,
        project_title=project.title,
        client_company_name=project.company.name,
        detail_document_name=document_name(db, need.detail_document_id),
        jd_document_name=document_name(db, need.jd_document_id),
        job_ad_document_name=document_name(db, need.job_ad_document_id),
    )


def serialize_interview(interview: Interview, db: Session) -> InterviewRead:
    scorecard = db.scalar(
        select(InterviewScorecard)
        .where(InterviewScorecard.interview_id == interview.id)
        .order_by(InterviewScorecard.submitted_at.desc(), InterviewScorecard.id.desc())
    )
    return InterviewRead(
        id=interview.id,
        candidate_id=interview.candidate_id,
        interviewer_user_id=interview.interviewer_user_id,
        interviewer_name=interview.interviewer_name,
        calendly_url=interview.calendly_url,
        scheduled_at=interview.scheduled_at,
        status=interview.status,
        score=scorecard.score if scorecard else None,
        recommendation=scorecard.recommendation if scorecard else None,
        notes=scorecard.notes if scorecard else None,
        evaluation_document_id=scorecard.evaluation_document_id if scorecard else None,
        evaluation_document_name=document_name(db, scorecard.evaluation_document_id if scorecard else None),
    )


def serialize_candidate_contract(contract: CandidateContract, db: Session) -> CandidateContractRead:
    return CandidateContractRead(
        id=contract.id,
        candidate_id=contract.candidate_id,
        contract_document_id=contract.contract_document_id,
        contract_document_name=document_name(db, contract.contract_document_id),
        invoice_terms=contract.invoice_terms,
        invoice_amount=contract.invoice_amount,
        currency=contract.currency,
        invoice_frequency=contract.invoice_frequency,
        invoice_start_date=contract.invoice_start_date,
        invoice_end_date=contract.invoice_end_date,
        invoice_date=contract.invoice_date,
        signed_at=contract.signed_at,
        status=contract.status,
    )


def serialize_candidate(candidate: Candidate, db: Session) -> CandidateRead:
    project = load_project_for_read(candidate.project_id, db)
    need = db.get(RecruitmentNeed, candidate.recruitment_need_id) if candidate.recruitment_need_id else None
    interviews = db.scalars(select(Interview).where(Interview.candidate_id == candidate.id).order_by(Interview.id.desc())).all()
    contracts = db.scalars(select(CandidateContract).where(CandidateContract.candidate_id == candidate.id).order_by(CandidateContract.id.desc())).all()
    return CandidateRead(
        id=candidate.id,
        project_id=candidate.project_id,
        recruitment_need_id=candidate.recruitment_need_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        linkedin_profile_url=candidate.linkedin_profile_url,
        notes=candidate.notes,
        candidate_type=candidate.candidate_type,
        status=candidate.status,
        created_at=candidate.created_at,
        project_code=project.project_code,
        project_title=project.title,
        client_company_name=project.company.name,
        position_title=need.position_title if need else None,
        interviews=[serialize_interview(interview, db) for interview in interviews],
        contracts=[serialize_candidate_contract(contract, db) for contract in contracts],
    )


def load_candidate(candidate_id: int, db: Session) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def validate_internal_interviewer(db: Session, user_id: int) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.id == user_id, AppUser.is_active.is_(True)).options(selectinload(AppUser.role_assignments)))
    if user is None or UserRole.internal_interviewer.value not in user_roles(user):
        raise HTTPException(status_code=400, detail="Select an active Internal Interviewer")
    return user


def hr_manager_emails(db: Session) -> list[str]:
    return sorted({user.email for user in users_with_role(db, UserRole.hr_manager.value)})


def finance_manager_emails(db: Session) -> list[str]:
    emails = [user.email for user in users_with_role(db, UserRole.finance_manager.value)]
    if FINANCE_MANAGER_EMAIL:
        emails.extend(email.strip() for email in FINANCE_MANAGER_EMAIL.split(",") if email.strip())
    return sorted(set(emails))


def recruitment_need_email_template(project: ProjectSOW, need: RecruitmentNeed) -> tuple[str, str, str]:
    recruitment_link = f"{FRONTEND_URL}/?{urlencode({'view': 'recruitment', 'need_id': need.id})}"
    subject = f"New recruitment position: {need.position_title}"
    text = "\n".join(
        [
            "A new recruitment position has been added.",
            "",
            f"Client: {project.company.name}",
            f"SOW: {project.title} ({project.project_code})",
            f"Position: {need.position_title}",
            f"Number of hires: {need.number_of_positions}",
            f"Type: {need.employment_type}",
            f"Billing: {need.position_billing_type or 'not set'} / {need.billing_frequency or 'not set'}",
            f"Target start: {need.target_start_date or 'not set'}",
            f"Description: {need.description}",
            "",
            f"Log in to work on this position: {recruitment_link}",
        ]
    )
    html = f"""
    <h2>New recruitment position</h2>
    <p>A new position has been added for recruitment.</p>
    <table cellpadding="6" cellspacing="0" border="0">
      <tr><td><strong>Client</strong></td><td>{escape(project.company.name)}</td></tr>
      <tr><td><strong>SOW</strong></td><td>{escape(project.title)} ({escape(project.project_code)})</td></tr>
      <tr><td><strong>Position</strong></td><td>{escape(need.position_title)}</td></tr>
      <tr><td><strong>Number of hires</strong></td><td>{need.number_of_positions}</td></tr>
      <tr><td><strong>Type</strong></td><td>{escape(need.employment_type)}</td></tr>
      <tr><td><strong>Billing</strong></td><td>{escape(need.position_billing_type or 'not set')} / {escape(need.billing_frequency or 'not set')}</td></tr>
      <tr><td><strong>Target start</strong></td><td>{escape(str(need.target_start_date or 'not set'))}</td></tr>
      <tr><td><strong>Description</strong></td><td>{escape(need.description)}</td></tr>
    </table>
    <p><a href="{escape(recruitment_link)}">Log in to work on this position</a></p>
    """
    return subject, text, html


def notify_hr_for_recruitment_need(db: Session, project: ProjectSOW, need: RecruitmentNeed, operations_manager_email: str | None) -> None:
    subject, text, html = recruitment_need_email_template(project, need)
    cc_emails = [operations_manager_email] if operations_manager_email else []
    for recipient in hr_manager_emails(db):
        status, detail = send_sendgrid_email(to_email=recipient, cc_emails=cc_emails, subject=subject, text=text, html=html)
        db.add(
            EmailNotification(
                project_id=project.id,
                recipient_email=recipient,
                cc_email=",".join(email for email in cc_emails if email and email != recipient) or None,
                subject=subject,
                body=html if detail is None else f"{html}\n\nSendGrid detail: {detail}",
                status=status,
            )
        )


def invoice_template(invoice: ClientInvoice) -> tuple[str, str, str]:
    approval_link = f"{API_BASE_URL}/auth/login?{urlencode({'approval_invoice_id': invoice.id})}"
    subject = f"Invoice {invoice.invoice_number} ready for approval"
    text = "\n".join(
        [
            f"Invoice {invoice.invoice_number} is ready for client account approval.",
            "",
            f"Client: {invoice.project.company.name}",
            f"SOW: {invoice.project.title} ({invoice.project.project_code})",
            f"Amount: {invoice.currency} {invoice.amount}",
            f"Issue date: {invoice.issue_date}",
            f"Due date: {invoice.due_date}",
            "",
            f"Log in to review and approve: {approval_link}",
        ]
    )
    html = f"""
    <h2>Invoice {escape(invoice.invoice_number)}</h2>
    <p>This invoice is ready for client account approval.</p>
    <table cellpadding="6" cellspacing="0" border="0">
      <tr><td><strong>Client</strong></td><td>{escape(invoice.project.company.name)}</td></tr>
      <tr><td><strong>SOW</strong></td><td>{escape(invoice.project.title)} ({escape(invoice.project.project_code)})</td></tr>
      <tr><td><strong>Amount</strong></td><td>{escape(invoice.currency)} {escape(str(invoice.amount))}</td></tr>
      <tr><td><strong>Issue date</strong></td><td>{escape(str(invoice.issue_date))}</td></tr>
      <tr><td><strong>Due date</strong></td><td>{escape(str(invoice.due_date))}</td></tr>
    </table>
    <p><a href="{escape(approval_link)}">Log in to review and approve this invoice</a></p>
    """
    return subject, text, html


def client_invoice_email_template(invoice: ClientInvoice) -> tuple[str, str, str]:
    subject = f"Invoice {invoice.invoice_number} from FlexGCC"
    text = "\n".join(
        [
            f"Please find attached invoice {invoice.invoice_number} for {invoice.project.company.name}.",
            "",
            f"SOW: {invoice.project.title} ({invoice.project.project_code})",
            f"Amount: {invoice.currency} {invoice.amount}",
            f"Invoice date: {invoice.issue_date}",
            f"Due date: {invoice.due_date}",
            "",
            "Please process payment as per the agreed terms.",
        ]
    )
    html = f"""
    <h2>Invoice {escape(invoice.invoice_number)}</h2>
    <p>Please find the invoice attached as a PDF. Please process payment as per the agreed terms.</p>
    <table cellpadding="6" cellspacing="0" border="0">
      <tr><td><strong>Client</strong></td><td>{escape(invoice.project.company.name)}</td></tr>
      <tr><td><strong>SOW</strong></td><td>{escape(invoice.project.title)} ({escape(invoice.project.project_code)})</td></tr>
      <tr><td><strong>Amount</strong></td><td>{escape(invoice.currency)} {escape(str(invoice.amount))}</td></tr>
      <tr><td><strong>Invoice date</strong></td><td>{escape(str(invoice.issue_date))}</td></tr>
      <tr><td><strong>Due date</strong></td><td>{escape(str(invoice.due_date))}</td></tr>
    </table>
    """
    return subject, text, html


def ordinal_day(value: date) -> str:
    if 11 <= value.day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value.day % 10, "th")
    return f"{value.day}{suffix} {value.strftime('%b')}, {value.year}"


ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words_under_1000(number: int) -> str:
    if number < 20:
        return ONES[number]
    if number < 100:
        tens, remainder = divmod(number, 10)
        return TENS[tens] if remainder == 0 else f"{TENS[tens]}-{ONES[remainder]}"
    hundreds, remainder = divmod(number, 100)
    return f"{ONES[hundreds]}-hundred" if remainder == 0 else f"{ONES[hundreds]}-hundred {words_under_1000(remainder)}"


def amount_in_words(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    whole = int(quantized)
    cents = int((quantized - Decimal(whole)) * 100)
    if whole == 0:
        words = "zero"
    else:
        parts: list[str] = []
        millions, remainder = divmod(whole, 1_000_000)
        thousands, remainder = divmod(remainder, 1000)
        if millions:
            parts.append(f"{words_under_1000(millions)}-million")
        if thousands:
            parts.append(f"{words_under_1000(thousands)}-thousand")
        if remainder:
            parts.append(words_under_1000(remainder))
        words = " ".join(parts)
    return f"{words[:1].upper()}{words[1:]} & {cents:02d}/100"


def invoice_pdf_bytes(invoice: ClientInvoice) -> bytes:
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00"))
    open_balance = max(invoice.amount - paid_total, Decimal("0.00"))
    cancelled_amount = open_balance if invoice.status in {InvoiceStatus.cancelled.value, InvoiceStatus.partially_paid_remainder_cancelled.value} else Decimal("0.00")
    net_due = Decimal("0.00") if cancelled_amount else open_balance
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )
    blue = colors.HexColor("#376092")
    header_blue = colors.HexColor("#c6d9f1")
    styles = {
        "normal": ParagraphStyle("normal", fontName="Helvetica", fontSize=10.5, leading=13, textColor=colors.black),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=9.5, leading=12, textColor=colors.black),
        "bold": ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.black),
        "company": ParagraphStyle("company", fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=blue),
        "invoice": ParagraphStyle("invoice", fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=blue, alignment=TA_RIGHT),
        "center_bold": ParagraphStyle("center_bold", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_CENTER),
        "right_bold": ParagraphStyle("right_bold", fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=TA_RIGHT),
        "right": ParagraphStyle("right", fontName="Helvetica", fontSize=10, leading=13, alignment=TA_RIGHT),
    }
    logo = Image(str(INVOICE_LOGO_PATH), width=0.62 * inch, height=0.62 * inch) if INVOICE_LOGO_PATH.exists() else Paragraph("", styles["normal"])
    header = Table(
        [
            [Paragraph("", styles["normal"]), logo],
            [Paragraph("<b>FlexGCC, LLC</b>", styles["company"]), Paragraph("<b>INVOICE</b>", styles["invoice"])],
        ],
        colWidths=[5.7 * inch, 1.25 * inch],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    billing_lines = [escape(line) for line in (invoice.project.company.billing_address or "Billing address not entered").splitlines() if line.strip()]
    client_block = "<br/>".join([f"<b>{escape(invoice.project.company.name)}</b>", *billing_lines, f"<b>Contact:</b> {escape(invoice.project.client_contact.full_name)}"])
    description = invoice.item_description or (invoice.schedule.item_description if invoice.schedule else None) or (invoice.schedule.label if invoice.schedule else invoice.project.title)
    money = f"${net_due:,.0f}" if invoice.currency.upper() == "USD" else f"{escape(invoice.currency)} {net_due:,.2f}"
    line_total = f"${invoice.amount:,.0f}" if invoice.currency.upper() == "USD" else f"{escape(invoice.currency)} {invoice.amount:,.2f}"
    story = [
        header,
        Spacer(1, 0.08 * inch),
        Paragraph("2412 Irwin Street, Suite 386,<br/>Melbourne, FL 32901", styles["normal"]),
        Spacer(1, 0.15 * inch),
        Paragraph("Phone:  +1 650 302 4988", styles["normal"]),
        Spacer(1, 0.12 * inch),
        Paragraph("Email:  contact@outcomepods.com", styles["normal"]),
        Spacer(1, 0.16 * inch),
        Paragraph(f"<b>Invoice #:</b> <font color='red'>{escape(invoice.invoice_number)}</font>", styles["normal"]),
        Paragraph(f"<b>Date:</b> {ordinal_day(invoice.issue_date)}", styles["normal"]),
        Spacer(1, 0.16 * inch),
        Paragraph(client_block, styles["normal"]),
        Spacer(1, 0.18 * inch),
    ]
    item_table = Table(
        [
            [Paragraph("<b>Description</b>", styles["bold"]), Paragraph("<b>Line Total</b>", styles["bold"])],
            [Paragraph(f"<b>{escape(description)}</b>", styles["bold"]), Paragraph(line_total, styles["normal"])],
            [Paragraph("<b>Net Due:</b>", styles["right_bold"]), Paragraph(f"<b>{money}</b>", styles["bold"])],
        ],
        colWidths=[5.75 * inch, 1.05 * inch],
        rowHeights=[0.42 * inch, 0.55 * inch, 0.36 * inch],
    )
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_blue),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#a6a6a6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ]
        )
    )
    story.extend(
        [
            item_table,
            Spacer(1, 0.18 * inch),
            Paragraph(f"<b>US Dollars: {amount_in_words(net_due)}</b>", styles["bold"]),
            Spacer(1, 0.14 * inch),
            Paragraph("<b>Payment due: Within 7 days of this Invoice</b>", styles["bold"]),
            Spacer(1, 0.16 * inch),
            Paragraph("<b>Account information for Electronic Transfers:</b>", styles["bold"]),
            Paragraph("&#9642;&nbsp;&nbsp; Company name: FlexGCC, LLC<br/>&#9642;&nbsp;&nbsp; Bank name: Bank of America<br/>&#9642;&nbsp;&nbsp; Account Number: 898160948065<br/>&#9642;&nbsp;&nbsp; Routing Numbers:<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;o&nbsp;&nbsp; ABA: 063000047 (paper and electronic)<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;o&nbsp;&nbsp; 026009593 (wires)<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;o&nbsp;&nbsp; SWIFT Code for US Dollars: BOFAUS3N", styles["small"]),
            Spacer(1, 0.3 * inch),
            Paragraph("<b>Thank you for your business!</b>", styles["center_bold"]),
            Spacer(1, 0.42 * inch),
            Paragraph("FlexGCC Private and Confidential", ParagraphStyle("footer", parent=styles["small"], alignment=TA_CENTER)),
        ]
    )
    doc.build(story)
    return buffer.getvalue()


def invoice_download_html(invoice: ClientInvoice) -> str:
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00"))
    open_balance = max(invoice.amount - paid_total, Decimal("0.00"))
    cancelled_amount = open_balance if invoice.status in {InvoiceStatus.cancelled.value, InvoiceStatus.partially_paid_remainder_cancelled.value} else Decimal("0.00")
    balance_due = Decimal("0.00") if cancelled_amount else open_balance
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Invoice {escape(invoice.invoice_number)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #172033; margin: 40px; }}
    h1 {{ margin-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 24px; }}
    td, th {{ border: 1px solid #ccd3dd; padding: 10px; text-align: left; }}
    .total {{ font-weight: bold; }}
  </style>
</head>
<body>
  <h1>FlexGCC Invoice</h1>
  <p>Invoice number: <strong>{escape(invoice.invoice_number)}</strong></p>
  <p>Status: <strong>{escape(invoice.status.replace("_", " "))}</strong></p>
  <table>
    <tr><th>Client</th><td>{escape(invoice.project.company.name)}</td></tr>
    <tr><th>Client contact</th><td>{escape(invoice.project.client_contact.full_name)} ({escape(invoice.project.client_contact.email)})</td></tr>
    <tr><th>SOW</th><td>{escape(invoice.project.title)} ({escape(invoice.project.project_code)})</td></tr>
    <tr><th>Invoice date</th><td>{escape(str(invoice.issue_date))}</td></tr>
    <tr><th>Due date</th><td>{escape(str(invoice.due_date))}</td></tr>
    <tr><th>Amount</th><td>{escape(invoice.currency)} {escape(str(invoice.amount))}</td></tr>
    <tr><th>Paid</th><td>{escape(invoice.currency)} {escape(str(paid_total))}</td></tr>
    <tr><th>Cancelled amount</th><td>{escape(invoice.currency)} {escape(str(cancelled_amount))}</td></tr>
    <tr class="total"><th>Balance due</th><td>{escape(invoice.currency)} {escape(str(balance_due))}</td></tr>
  </table>
</body>
</html>"""


def send_sendgrid_email(
    *,
    to_email: str,
    cc_emails: list[str],
    subject: str,
    text: str,
    html: str,
    attachments: list[dict[str, str]] | None = None,
) -> tuple[str, str | None]:
    if not SENDGRID_API_KEY:
        return "not_configured", None
    personalizations: dict[str, object] = {"to": [{"email": to_email}]}
    if cc_emails:
        personalizations["cc"] = [{"email": email} for email in cc_emails if email != to_email]
    payload = {
        "personalizations": [personalizations],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": SENDGRID_FROM_NAME},
        "reply_to": {"email": SENDGRID_REPLY_TO_EMAIL},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }
    if attachments:
        payload["attachments"] = attachments
    response = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if response.status_code >= 400:
        return "failed", response.text[:500]
    return "sent", response.headers.get("X-Message-Id")


def queue_invoice_approval_email(db: Session, invoice: ClientInvoice) -> None:
    recipient = invoice.project.client_account_executive.email if invoice.project.client_account_executive else ""
    if not recipient:
        db.add(
            EmailNotification(
                project_id=invoice.project_id,
                invoice_id=invoice.id,
                recipient_email="",
                subject=f"Invoice {invoice.invoice_number} ready for approval",
                body="No Client Account Executive is assigned to this SOW.",
                status="failed",
            )
        )
        return
    cc_emails = finance_manager_emails(db)
    subject, text, html = invoice_template(invoice)
    status, detail = send_sendgrid_email(to_email=recipient, cc_emails=cc_emails, subject=subject, text=text, html=html)
    body = html if detail is None else f"{html}\n\nSendGrid detail: {detail}"
    db.add(
        EmailNotification(
            project_id=invoice.project_id,
            invoice_id=invoice.id,
            recipient_email=recipient,
            cc_email=",".join(cc_emails) if cc_emails else None,
            subject=subject,
            body=body,
            status=status,
        )
    )


def create_due_invoices(db: Session, as_of: date) -> list[ClientInvoice]:
    schedules = db.scalars(
        select(ClientInvoiceSchedule)
        .where(ClientInvoiceSchedule.status == "active")
        .options(
            selectinload(ClientInvoiceSchedule.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoiceSchedule.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoiceSchedule.project).selectinload(ProjectSOW.client_account_executive),
        )
    ).all()
    generated: list[ClientInvoice] = []

    for schedule in schedules:
        candidate_date = schedule.next_invoice_generation_date or schedule.first_invoice_date
        while candidate_date - timedelta(days=2) <= as_of:
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
                    invoice_number=next_invoice_number(db, candidate_date),
                    issue_date=candidate_date,
                    due_date=candidate_date + timedelta(days=7),
                    item_description=schedule.item_description or schedule.label,
                    amount=schedule.amount,
                    currency=schedule.currency,
                    status=InvoiceStatus.due_for_client_approval.value,
                )
                db.add(invoice)
                db.flush()
                generated.append(invoice)
                queue_invoice_approval_email(db, invoice)
                log_event(db, project_id=schedule.project_id, actor_name="System", action="client_invoice_generated", details=invoice.invoice_number)
            if schedule.frequency == "single":
                break
            candidate_date = next_date(candidate_date, schedule.frequency)
    return generated


@app.get("/auth/login")
async def auth_login(request: Request, approval_invoice_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    if not GOOGLE_CONFIGURED:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if approval_invoice_id is not None:
        invoice = db.get(ClientInvoice, approval_invoice_id)
        if invoice is None:
            return RedirectResponse(f"{FRONTEND_URL}/?auth_error=invoice_not_found")
        request.session.clear()
        request.session["pending_approval_invoice_id"] = approval_invoice_id
    redirect_uri = getenv("GOOGLE_REDIRECT_URI", f"{API_BASE_URL}/auth/callback")
    kwargs = {"prompt": "select_account"} if approval_invoice_id is not None else {}
    return await oauth.google.authorize_redirect(request, redirect_uri, **kwargs)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    if not GOOGLE_CONFIGURED:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    token = await oauth.google.authorize_access_token(request)
    profile = token.get("userinfo") or await oauth.google.userinfo(token=token)
    email = normalize_email(profile.get("email", ""))
    if not email:
        raise HTTPException(status_code=400, detail="Google account did not return an email address")
    user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email).options(selectinload(AppUser.role_assignments)))
    if user is None or not user.is_active:
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error=not_provisioned")
    roles = user_roles(user)
    if not roles:
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error=no_roles")
    user.google_sub = profile.get("sub")
    user.full_name = profile.get("name") or user.full_name
    user.last_login_at = utcnow()
    db.commit()
    request.session["user_id"] = user.id
    request.session.pop("active_role", None)
    pending_approval_invoice_id = request.session.pop("pending_approval_invoice_id", None)
    if pending_approval_invoice_id is not None:
        invoice = db.scalar(
            select(ClientInvoice)
            .where(ClientInvoice.id == pending_approval_invoice_id)
            .options(selectinload(ClientInvoice.project))
        )
        if (
            invoice is None
            or UserRole.client_account_executive.value not in roles
            or invoice.project.client_account_executive_id != user.id
        ):
            return RedirectResponse(f"{FRONTEND_URL}/?approval_invoice_id={pending_approval_invoice_id}&approval_error=not_authorized")
        request.session["active_role"] = UserRole.client_account_executive.value
        return RedirectResponse(f"{FRONTEND_URL}/?approval_invoice_id={pending_approval_invoice_id}")
    if len(roles) == 1:
        request.session["active_role"] = roles[0]
    return RedirectResponse(FRONTEND_URL)


@app.get("/auth/me", response_model=CurrentUserRead)
def auth_me(request: Request, db: Session = Depends(get_db)) -> CurrentUserRead:
    try:
        context = auth_context_from_session(request, db)
    except HTTPException as exc:
        if exc.status_code == 401:
            return CurrentUserRead(authenticated=False)
        raise
    return CurrentUserRead(
        authenticated=True,
        id=context.user.id,
        full_name=context.user.full_name,
        email=context.user.email,
        roles=context.roles,
        active_role=context.active_role,
    )


@app.post("/auth/select-role", response_model=CurrentUserRead)
def select_role(payload: RoleSelect, request: Request, db: Session = Depends(get_db)) -> CurrentUserRead:
    context = auth_context_from_session(request, db)
    if payload.role not in context.roles:
        raise HTTPException(status_code=403, detail="Role is not assigned to this user")
    request.session["active_role"] = payload.role
    return CurrentUserRead(
        authenticated=True,
        id=context.user.id,
        full_name=context.user.full_name,
        email=context.user.email,
        roles=context.roles,
        active_role=payload.role,
    )


@app.post("/auth/logout")
def auth_logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "logged_out"}


@app.get("/users", response_model=list[AppUserRead])
def list_users(_: AuthContext = Depends(require_role(UserRole.system_admin.value)), db: Session = Depends(get_db)) -> list[AppUserRead]:
    users = db.scalars(select(AppUser).order_by(AppUser.full_name).options(selectinload(AppUser.role_assignments))).all()
    return [serialize_user(user) for user in users]


@app.get("/users/by-role/{role}", response_model=list[AppUserRead])
def list_users_by_role(role: str, _: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> list[AppUserRead]:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=404, detail="Role not found")
    return [serialize_user(user) for user in users_with_role(db, role)]


@app.post("/users", response_model=AppUserRead)
def upsert_user(payload: AppUserUpsert, context: AuthContext = Depends(require_role(UserRole.system_admin.value)), db: Session = Depends(get_db)) -> AppUserRead:
    roles = sorted(set(payload.roles))
    invalid_roles = [role for role in roles if role not in VALID_ROLES]
    if invalid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid roles: {', '.join(invalid_roles)}")
    email = normalize_email(str(payload.email))
    user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email).options(selectinload(AppUser.role_assignments)))
    if user is None:
        user = AppUser(full_name=payload.full_name, email=email, role=roles[0], is_active=payload.is_active)
        db.add(user)
        db.flush()
    user.full_name = payload.full_name
    user.email = email
    user.role = roles[0]
    user.is_active = payload.is_active
    db.execute(delete(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id))
    db.flush()
    for role in roles:
        ensure_role_assignment(db, user, role, context.user.full_name)
    db.commit()
    db.refresh(user)
    user = db.scalar(select(AppUser).where(AppUser.id == user.id).options(selectinload(AppUser.role_assignments)))
    assert user is not None
    return serialize_user(user)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": engine.url.get_backend_name(), "database_name": str(engine.url.database or "")}


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
            "app_users",
            "user_role_assignments",
            "candidates",
            "interviews",
            "interview_scorecards",
            "candidate_contracts",
        ],
        "reserved_later_flow_tables": [
            "candidate_screening_forms",
            "candidate_evaluations",
            "candidate_vendor_invoices",
            "candidate_invoice_approvals",
            "candidate_payments",
            "agent_tasks",
        ],
    }


@app.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(request: Request, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> ProjectRead:
    data, files = await request_payload_and_files(request)
    payload: ProjectCreate = parse_model(ProjectCreate, data)
    validate_client_account_executive(db, payload.client_account_executive_id)
    company = db.scalar(select(ClientCompany).where(ClientCompany.name == payload.client_company_name))
    if company is None:
        company = ClientCompany(name=payload.client_company_name)
        db.add(company)
        db.flush()
    if payload.client_billing_address is not None:
        company.billing_address = payload.client_billing_address

    contact = ClientContact(
        company_id=company.id,
        full_name=payload.client_contact_name,
        email=str(payload.client_contact_email),
        phone=payload.client_contact_phone,
    )
    db.add(contact)
    db.flush()

    msa = db.scalar(
        select(MasterServiceAgreement).where(
            MasterServiceAgreement.company_id == company.id,
            MasterServiceAgreement.reference == payload.msa_reference,
        )
    )
    if msa is None:
        msa = MasterServiceAgreement(company_id=company.id, reference=payload.msa_reference)
        db.add(msa)
        db.flush()

    project = ProjectSOW(
        project_code=project_code(db),
        company_id=company.id,
        client_contact_id=contact.id,
        msa_id=msa.id,
        client_account_executive_id=payload.client_account_executive_id,
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

    msa_document = await save_uploaded_document(
        db,
        file=files.get("msa_document"),
        project_id=project.id,
        document_type="msa",
        uploaded_by_name=payload.operations_manager_name,
    )
    if msa_document:
        msa.document_id = msa_document.id
    await save_uploaded_document(
        db,
        file=files.get("sow_document"),
        project_id=project.id,
        document_type="sow",
        uploaded_by_name=payload.operations_manager_name,
    )

    log_event(db, project_id=project.id, actor_name=payload.operations_manager_name, action="project_created", details=f"Created {project.project_code}")
    db.commit()
    db.refresh(project)
    return serialize_project(load_project_for_read(project.id, db))


@app.post("/projects/{project_id}/sows", response_model=ProjectRead, status_code=201)
async def add_sow_to_msa(project_id: int, request: Request, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> ProjectRead:
    source = load_project_for_read(project_id, db)
    data, files = await request_payload_and_files(request)
    payload: SOWCreate = parse_model(SOWCreate, data)
    project = ProjectSOW(
        project_code=project_code(db),
        company_id=source.company_id,
        client_contact_id=source.client_contact_id,
        msa_id=source.msa_id,
        client_account_executive_id=source.client_account_executive_id,
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
    await save_uploaded_document(
        db,
        file=files.get("sow_document"),
        project_id=project.id,
        document_type="sow",
        uploaded_by_name=payload.operations_manager_name,
    )
    log_event(db, project_id=project.id, actor_name=payload.operations_manager_name, action="sow_added", details=f"Added {project.project_code} under {source.msa.reference if source.msa else 'MSA'}")
    db.commit()
    return serialize_project(load_project_for_read(project.id, db))


@app.put("/projects/{project_id}", response_model=ProjectRead)
async def update_project(project_id: int, request: Request, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> ProjectRead:
    project = load_project_for_read(project_id, db)
    data, files = await request_payload_and_files(request)
    payload: ProjectUpdate = parse_model(ProjectUpdate, data)
    if payload.client_company_name is not None:
        project.company.name = payload.client_company_name
    if payload.client_account_executive_id is not None:
        validate_client_account_executive(db, payload.client_account_executive_id)
        project.client_account_executive_id = payload.client_account_executive_id
    if payload.client_billing_address is not None:
        project.company.billing_address = payload.client_billing_address
    if payload.client_contact_name is not None:
        project.client_contact.full_name = payload.client_contact_name
    if payload.client_contact_email is not None:
        project.client_contact.email = str(payload.client_contact_email)
    if payload.client_contact_phone is not None:
        project.client_contact.phone = payload.client_contact_phone
    if payload.msa_reference is not None and project.msa is not None:
        project.msa.reference = payload.msa_reference
    if payload.sow_title is not None:
        project.title = payload.sow_title
    if payload.sow_description is not None:
        project.description = payload.sow_description
    if payload.sow_amount is not None:
        project.sow_amount = payload.sow_amount
    if payload.currency is not None:
        project.currency = payload.currency.upper()
    if payload.start_date is not None:
        project.start_date = payload.start_date
    if payload.end_date is not None:
        project.end_date = payload.end_date
    if payload.operations_manager_name is not None:
        project.operations_manager_name = payload.operations_manager_name
    msa_document = await save_uploaded_document(
        db,
        file=files.get("msa_document"),
        project_id=project.id,
        document_type="msa",
        uploaded_by_name=payload.operations_manager_name or project.operations_manager_name,
    )
    if msa_document and project.msa:
        project.msa.document_id = msa_document.id
    await save_uploaded_document(
        db,
        file=files.get("sow_document"),
        project_id=project.id,
        document_type="sow",
        uploaded_by_name=payload.operations_manager_name or project.operations_manager_name,
    )
    log_event(db, project_id=project.id, actor_name=project.operations_manager_name, action="project_updated", details=project.project_code)
    db.commit()
    return serialize_project(load_project_for_read(project.id, db))


@app.get("/projects", response_model=list[ProjectRead])
def list_projects(_: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.scalars(
        select(ProjectSOW)
        .order_by(ProjectSOW.created_at.desc())
        .options(*project_options())
    ).all()
    return [serialize_project(project) for project in projects]


@app.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, _: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> ProjectRead:
    return serialize_project(load_project_for_read(project_id, db))


@app.post("/projects/{project_id}/recruitment-needs", response_model=RecruitmentNeedRead, status_code=201)
async def add_recruitment_need(project_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> RecruitmentNeedRead:
    project = load_project_for_read(project_id, db)
    data, files = await request_payload_and_files(request)
    payload: RecruitmentNeedCreate = parse_model(RecruitmentNeedCreate, data)
    payload_data = payload.model_dump()
    historical_completed = bool(payload_data.pop("historical_completed", False))
    need = RecruitmentNeed(project_id=project_id, **payload_data)
    if historical_completed:
        need.status = "closed"
    db.add(need)
    db.flush()
    detail_document = await save_uploaded_document(
        db,
        file=files.get("detail_document"),
        project_id=project_id,
        document_type="position_detail",
        uploaded_by_name=context.user.full_name,
    )
    if detail_document:
        need.detail_document_id = detail_document.id
    log_event(db, project_id=project_id, actor_name=project.operations_manager_name, action="recruitment_need_added", details=payload.position_title)
    if not historical_completed:
        notify_hr_for_recruitment_need(db, project, need, context.user.email)
    db.commit()
    db.refresh(need)
    return RecruitmentNeedRead.model_validate(need)


@app.put("/recruitment-needs/{need_id}", response_model=RecruitmentNeedRead)
async def update_recruitment_need(need_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> RecruitmentNeedRead:
    need = db.get(RecruitmentNeed, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Recruitment need not found")
    project = load_project_for_read(need.project_id, db)
    data, files = await request_payload_and_files(request)
    payload: RecruitmentNeedUpdate = parse_model(RecruitmentNeedUpdate, data)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "currency" and value:
            value = str(value).upper()
        setattr(need, field, value)
    detail_document = await save_uploaded_document(
        db,
        file=files.get("detail_document"),
        project_id=need.project_id,
        document_type="position_detail",
        uploaded_by_name=context.user.full_name,
    )
    if detail_document:
        need.detail_document_id = detail_document.id
    log_event(db, project_id=need.project_id, actor_name=project.operations_manager_name, action="recruitment_need_updated", details=need.position_title)
    db.commit()
    db.refresh(need)
    return RecruitmentNeedRead.model_validate(need)


@app.delete("/recruitment-needs/{need_id}")
def delete_recruitment_need(need_id: int, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> dict[str, str]:
    need = db.get(RecruitmentNeed, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Recruitment need not found")
    need.status = "deleted"
    log_event(db, project_id=need.project_id, actor_name="Operations Manager", action="recruitment_need_deleted", details=need.position_title)
    db.commit()
    return {"status": "deleted"}


@app.get("/recruitment/needs", response_model=list[RecruitmentNeedDetailRead])
def list_recruitment_needs(_: AuthContext = Depends(require_role(UserRole.operations_manager.value, UserRole.hr_manager.value, UserRole.system_admin.value)), db: Session = Depends(get_db)) -> list[RecruitmentNeedDetailRead]:
    needs = db.scalars(select(RecruitmentNeed).order_by(RecruitmentNeed.created_at.desc(), RecruitmentNeed.id.desc())).all()
    return [serialize_recruitment_need_detail(need, db) for need in needs]


@app.post("/recruitment-needs/{need_id}/assets", response_model=RecruitmentNeedDetailRead)
async def upload_recruitment_assets(need_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.hr_manager.value)), db: Session = Depends(get_db)) -> RecruitmentNeedDetailRead:
    need = db.get(RecruitmentNeed, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Recruitment need not found")
    data, files = await request_payload_and_files(request)
    payload: RecruitmentAssetCreate = parse_model(RecruitmentAssetCreate, data)
    jd_document = await save_uploaded_document(db, file=files.get("jd_document"), project_id=need.project_id, document_type="job_description", uploaded_by_name=context.user.full_name)
    job_ad_document = await save_uploaded_document(db, file=files.get("job_ad_document"), project_id=need.project_id, document_type="job_ad", uploaded_by_name=context.user.full_name)
    if jd_document:
        need.jd_document_id = jd_document.id
        need.jd_uploaded_at = utcnow()
    if job_ad_document:
        need.job_ad_document_id = job_ad_document.id
    if payload.linkedin_ad_url is not None:
        need.linkedin_ad_url = payload.linkedin_ad_url
    if need.status == "open":
        need.status = "sourcing"
    log_event(db, project_id=need.project_id, actor_name=context.user.full_name, action="recruitment_assets_uploaded", details=need.position_title)
    db.commit()
    db.refresh(need)
    return serialize_recruitment_need_detail(need, db)


@app.post("/recruitment-needs/{need_id}/candidates", response_model=CandidateRead, status_code=201)
def add_candidate(need_id: int, payload: CandidateCreate, context: AuthContext = Depends(require_role(UserRole.hr_manager.value)), db: Session = Depends(get_db)) -> CandidateRead:
    need = db.get(RecruitmentNeed, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Recruitment need not found")
    candidate = Candidate(
        project_id=need.project_id,
        recruitment_need_id=need.id,
        full_name=payload.full_name,
        email=str(payload.email),
        phone=payload.phone,
        linkedin_profile_url=payload.linkedin_profile_url,
        notes=payload.notes,
        candidate_type=payload.candidate_type,
        status="entered",
    )
    db.add(candidate)
    db.flush()
    log_event(db, project_id=need.project_id, actor_name=context.user.full_name, action="candidate_added", details=candidate.full_name)
    db.commit()
    db.refresh(candidate)
    return serialize_candidate(candidate, db)


@app.post("/recruitment-needs/{need_id}/historical-hires", response_model=CandidateRead, status_code=201)
async def add_historical_hire(need_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.hr_manager.value, UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> CandidateRead:
    need = db.get(RecruitmentNeed, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Recruitment need not found")
    data, files = await request_payload_and_files(request)
    payload: HistoricalHireCreate = parse_model(HistoricalHireCreate, data)
    next_candidate_invoice_date = payload.invoice_date if payload.invoice_frequency == "single" else payload.invoice_start_date
    if next_candidate_invoice_date and next_candidate_invoice_date < date.today():
        raise HTTPException(status_code=400, detail="Historical hires should use the next future candidate invoice/reminder date, not a completed past date")
    candidate = Candidate(
        project_id=need.project_id,
        recruitment_need_id=need.id,
        full_name=payload.full_name,
        email=str(payload.email),
        phone=payload.phone,
        linkedin_profile_url=payload.linkedin_profile_url,
        notes=payload.notes,
        candidate_type=payload.candidate_type,
        status="hired",
    )
    db.add(candidate)
    db.flush()
    document = await save_uploaded_document(db, file=files.get("signed_contract"), project_id=need.project_id, document_type="signed_candidate_contract", uploaded_by_name=context.user.full_name)
    contract = CandidateContract(
        candidate_id=candidate.id,
        contract_document_id=document.id if document else None,
        invoice_terms=payload.invoice_terms,
        invoice_amount=payload.invoice_amount,
        currency=payload.currency.upper() if payload.currency else None,
        invoice_frequency=payload.invoice_frequency,
        invoice_start_date=payload.invoice_start_date,
        invoice_end_date=payload.invoice_end_date,
        invoice_date=payload.invoice_date,
        signed_at=utcnow() if document else None,
        status="signed" if document else "draft",
    )
    need.status = "closed"
    db.add(contract)
    log_event(db, project_id=need.project_id, actor_name=context.user.full_name, action="historical_hire_added", details=candidate.full_name)
    db.commit()
    db.refresh(candidate)
    return serialize_candidate(candidate, db)


@app.get("/recruitment/candidates", response_model=list[CandidateRead])
def list_candidates(_: AuthContext = Depends(require_role(UserRole.hr_manager.value, UserRole.operations_manager.value, UserRole.system_admin.value)), db: Session = Depends(get_db)) -> list[CandidateRead]:
    candidates = db.scalars(select(Candidate).order_by(Candidate.created_at.desc(), Candidate.id.desc())).all()
    return [serialize_candidate(candidate, db) for candidate in candidates]


@app.patch("/candidates/{candidate_id}/status", response_model=CandidateRead)
def update_candidate_status(candidate_id: int, payload: CandidateStatusUpdate, context: AuthContext = Depends(require_role(UserRole.hr_manager.value)), db: Session = Depends(get_db)) -> CandidateRead:
    candidate = load_candidate(candidate_id, db)
    candidate.status = payload.status
    log_event(db, project_id=candidate.project_id, actor_name=context.user.full_name, action="candidate_status_updated", details=f"{candidate.full_name}: {payload.status}")
    db.commit()
    db.refresh(candidate)
    return serialize_candidate(candidate, db)


@app.post("/candidates/{candidate_id}/interviews", response_model=InterviewRead, status_code=201)
def assign_interview(candidate_id: int, payload: InterviewCreate, context: AuthContext = Depends(require_role(UserRole.hr_manager.value)), db: Session = Depends(get_db)) -> InterviewRead:
    candidate = load_candidate(candidate_id, db)
    interviewer = validate_internal_interviewer(db, payload.interviewer_user_id)
    interview = Interview(
        candidate_id=candidate.id,
        interviewer_user_id=interviewer.id,
        interviewer_name=interviewer.full_name,
        calendly_url=payload.calendly_url,
        scheduled_at=payload.scheduled_at,
        status="pending",
    )
    candidate.status = "interview_scheduled"
    db.add(interview)
    db.flush()
    log_event(db, project_id=candidate.project_id, actor_name=context.user.full_name, action="interview_assigned", details=f"{candidate.full_name}: {interviewer.full_name}")
    db.commit()
    db.refresh(interview)
    return serialize_interview(interview, db)


@app.get("/interviews", response_model=list[InterviewRead])
def list_interviews(context: AuthContext = Depends(require_role(UserRole.hr_manager.value, UserRole.internal_interviewer.value, UserRole.system_admin.value)), db: Session = Depends(get_db)) -> list[InterviewRead]:
    query = select(Interview).order_by(Interview.id.desc())
    if context.active_role == UserRole.internal_interviewer.value:
        query = query.where(Interview.interviewer_user_id == context.user.id)
    interviews = db.scalars(query).all()
    return [serialize_interview(interview, db) for interview in interviews]


@app.post("/interviews/{interview_id}/scorecard", response_model=InterviewRead)
async def submit_scorecard(interview_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.internal_interviewer.value)), db: Session = Depends(get_db)) -> InterviewRead:
    interview = db.get(Interview, interview_id)
    if interview is None or interview.interviewer_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    candidate = load_candidate(interview.candidate_id, db)
    data, files = await request_payload_and_files(request)
    payload: ScorecardCreate = parse_model(ScorecardCreate, data)
    document = await save_uploaded_document(db, file=files.get("evaluation_checklist"), project_id=candidate.project_id, document_type="evaluation_checklist", uploaded_by_name=context.user.full_name)
    scorecard = InterviewScorecard(
        interview_id=interview.id,
        interviewer_name=context.user.full_name,
        score=payload.score,
        recommendation=payload.recommendation,
        notes=payload.notes,
        evaluation_document_id=document.id if document else None,
    )
    interview.status = "completed"
    candidate.status = "evaluation_submitted"
    db.add(scorecard)
    log_event(db, project_id=candidate.project_id, actor_name=context.user.full_name, action="scorecard_submitted", details=candidate.full_name)
    db.commit()
    db.refresh(interview)
    return serialize_interview(interview, db)


@app.post("/candidates/{candidate_id}/contract", response_model=CandidateRead)
async def upload_candidate_contract(candidate_id: int, request: Request, context: AuthContext = Depends(require_role(UserRole.hr_manager.value)), db: Session = Depends(get_db)) -> CandidateRead:
    candidate = load_candidate(candidate_id, db)
    data, files = await request_payload_and_files(request)
    payload: CandidateContractCreate = parse_model(CandidateContractCreate, data)
    document = await save_uploaded_document(db, file=files.get("signed_contract"), project_id=candidate.project_id, document_type="signed_candidate_contract", uploaded_by_name=context.user.full_name)
    contract = CandidateContract(
        candidate_id=candidate.id,
        contract_document_id=document.id if document else None,
        invoice_terms=payload.invoice_terms,
        invoice_amount=payload.invoice_amount,
        currency=payload.currency.upper() if payload.currency else None,
        invoice_frequency=payload.invoice_frequency,
        invoice_start_date=payload.invoice_start_date,
        invoice_end_date=payload.invoice_end_date,
        invoice_date=payload.invoice_date,
        signed_at=utcnow() if document else None,
        status="signed" if document else "draft",
    )
    candidate.status = "hired"
    db.add(contract)
    log_event(db, project_id=candidate.project_id, actor_name=context.user.full_name, action="candidate_contract_uploaded", details=candidate.full_name)
    db.commit()
    db.refresh(candidate)
    return serialize_candidate(candidate, db)


@app.post("/projects/{project_id}/invoice-schedules", response_model=InvoiceScheduleRead, status_code=201)
def add_invoice_schedule(project_id: int, payload: InvoiceScheduleCreate, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> InvoiceScheduleRead:
    project = db.get(ProjectSOW, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.frequency == "single":
        payload.final_invoice_date = None
    if payload.final_invoice_date and payload.final_invoice_date < payload.first_invoice_date:
        raise HTTPException(status_code=400, detail="Final invoice date cannot be earlier than first invoice date")
    if payload.historical_backfill:
        if payload.next_invoice_generation_date is None:
            raise HTTPException(status_code=400, detail="Next invoice/reminder date is required for historical backfill schedules")
        if payload.next_invoice_generation_date < date.today():
            raise HTTPException(status_code=400, detail="Historical backfill schedules should start reminders from the next current/future cycle")
        if payload.final_invoice_date and payload.next_invoice_generation_date > payload.final_invoice_date:
            raise HTTPException(status_code=400, detail="Next invoice/reminder date cannot be after the final invoice date")
    else:
        payload.next_invoice_generation_date = None
    if not payload.item_description:
        payload.item_description = payload.label
    schedule = ClientInvoiceSchedule(project_id=project_id, **payload.model_dump())
    db.add(schedule)
    db.flush()
    log_event(db, project_id=project_id, actor_name=project.operations_manager_name, action="invoice_schedule_added", details=payload.label)
    create_due_invoices(db, date.today())
    db.commit()
    db.refresh(schedule)
    return InvoiceScheduleRead.model_validate(schedule)


@app.post("/invoices/generate", response_model=GenerateInvoicesResult)
def generate_due_invoices(as_of: date = Query(default_factory=date.today), _: AuthContext = Depends(require_role(UserRole.system_admin.value)), db: Session = Depends(get_db)) -> GenerateInvoicesResult:
    generated = create_due_invoices(db, as_of)
    db.commit()
    for invoice in generated:
        db.refresh(invoice)
    return GenerateInvoicesResult(generated_count=len(generated), invoices=[ClientInvoiceRead.model_validate(invoice) for invoice in generated])


@app.post("/system/invoices/generate", response_model=GenerateInvoicesResult)
def generate_due_invoices_system(request: Request, as_of: date = Query(default_factory=date.today), db: Session = Depends(get_db)) -> GenerateInvoicesResult:
    if not INVOICE_CRON_TOKEN or request.headers.get("x-system-token") != INVOICE_CRON_TOKEN:
        raise HTTPException(status_code=401, detail="System token required")
    generated = create_due_invoices(db, as_of)
    db.commit()
    for invoice in generated:
        db.refresh(invoice)
    return GenerateInvoicesResult(generated_count=len(generated), invoices=[ClientInvoiceRead.model_validate(invoice) for invoice in generated])


@app.get("/client-invoices", response_model=list[InvoiceDetailRead])
def list_invoices(
    context: AuthContext = Depends(require_login),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[InvoiceDetailRead]:
    query = select(ClientInvoice).order_by(ClientInvoice.issue_date.asc(), ClientInvoice.id.asc())
    if context.active_role == UserRole.client_account_executive.value:
        query = query.join(ProjectSOW, ProjectSOW.id == ClientInvoice.project_id).where(ProjectSOW.client_account_executive_id == context.user.id)
    if status:
        query = query.where(ClientInvoice.status == status)
    if date_from:
        query = query.where(ClientInvoice.issue_date >= date_from)
    if date_to:
        query = query.where(ClientInvoice.issue_date <= date_to)
    query = query.offset((page - 1) * page_size).limit(page_size)
    invoices = db.scalars(
        query.options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoice.payments),
        )
    ).all()
    return [serialize_invoice(invoice) for invoice in invoices]


@app.get("/upcoming-invoices", response_model=list[UpcomingInvoiceRead])
def list_upcoming_invoices(
    context: AuthContext = Depends(require_login),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[UpcomingInvoiceRead]:
    query = select(ClientInvoiceSchedule).where(ClientInvoiceSchedule.status == "active")
    if context.active_role == UserRole.client_account_executive.value:
        query = query.join(ProjectSOW, ProjectSOW.id == ClientInvoiceSchedule.project_id).where(ProjectSOW.client_account_executive_id == context.user.id)

    schedules = db.scalars(
        query.options(
            selectinload(ClientInvoiceSchedule.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoiceSchedule.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoiceSchedule.invoices),
        )
    ).all()

    upcoming_by_project: dict[int, UpcomingInvoiceRead] = {}
    for schedule in schedules:
        next_invoice_date = next_unraised_invoice_date(schedule)
        if next_invoice_date is None:
            continue
        if date_from and next_invoice_date < date_from:
            continue
        if date_to and next_invoice_date > date_to:
            continue
        upcoming = serialize_upcoming_invoice(schedule, next_invoice_date)
        existing = upcoming_by_project.get(schedule.project_id)
        if existing is None or (upcoming.next_invoice_date, upcoming.schedule_id) < (existing.next_invoice_date, existing.schedule_id):
            upcoming_by_project[schedule.project_id] = upcoming

    upcoming_invoices = sorted(upcoming_by_project.values(), key=lambda invoice: (invoice.next_invoice_date, invoice.project_code, invoice.schedule_id))
    start = (page - 1) * page_size
    return upcoming_invoices[start:start + page_size]

@app.get("/client-invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(invoice_id: int, context: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    return load_invoice_detail(invoice_id, db, context)


@app.get("/client-invoices/{invoice_id}/client-account-approval-view", response_model=InvoiceDetailRead)
def get_client_account_approval_invoice(invoice_id: int, context: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoice.payments),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    authorize_client_account_invoice_approval(invoice, context)
    return serialize_invoice(invoice)


@app.get("/client-invoices/{invoice_id}/download")
def download_invoice(invoice_id: int, context: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> Response:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.schedule),
            selectinload(ClientInvoice.payments),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    authorize_invoice_visibility(invoice, context)
    filename = invoice.invoice_number.replace("/", "-")
    return Response(
        content=invoice_pdf_bytes(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@app.post("/client-invoices/{invoice_id}/client-account-approval", response_model=InvoiceDetailRead)
def approve_client_account(invoice_id: int, payload: ApprovalCreate, context: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(select(ClientInvoice).where(ClientInvoice.id == invoice_id).options(selectinload(ClientInvoice.project)))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    authorize_client_account_invoice_approval(invoice, context)
    if invoice.status not in {InvoiceStatus.due_for_client_approval.value, InvoiceStatus.draft.value}:
        raise HTTPException(status_code=400, detail=f"Invoice is not ready for client account approval: {invoice.status}")
    invoice.status = InvoiceStatus.approved_by_client_account.value
    db.add(ClientInvoiceApproval(invoice_id=invoice_id, approval_type="client_account_executive", approver_name=payload.approver_name, decision="approved", notes=payload.notes))
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.approver_name, action="client_account_approved_invoice")
    db.commit()
    return load_invoice_detail(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/finance-approval", response_model=InvoiceDetailRead)
def approve_finance(invoice_id: int, payload: ApprovalCreate, _: AuthContext = Depends(require_role(UserRole.finance_manager.value)), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.get(ClientInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.approved_by_client_account.value:
        raise HTTPException(status_code=400, detail=f"Invoice must be client-account approved before finance approval: {invoice.status}")
    invoice.status = InvoiceStatus.approved_for_sending.value
    db.add(ClientInvoiceApproval(invoice_id=invoice_id, approval_type="finance_manager", approver_name=payload.approver_name, decision="approved", notes=payload.notes))
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.approver_name, action="finance_approved_invoice")
    db.commit()
    return load_invoice_detail(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/send", response_model=InvoiceDetailRead)
def send_invoice(invoice_id: int, payload: SendInvoiceCreate, _: AuthContext = Depends(require_role(UserRole.finance_manager.value)), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(
        select(ClientInvoice)
        .where(ClientInvoice.id == invoice_id)
        .options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoice.schedule),
            selectinload(ClientInvoice.payments),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.approved_for_sending.value:
        raise HTTPException(status_code=400, detail=f"Invoice must be finance-approved before sending: {invoice.status}")
    recipient = str(payload.recipient_email) if payload.recipient_email else invoice.project.client_contact.email
    cc_emails = finance_manager_emails(db)
    if invoice.project.client_account_executive:
        cc_emails.append(invoice.project.client_account_executive.email)
    if payload.cc_email:
        cc_emails.append(str(payload.cc_email))
    cc_emails = sorted(set(email for email in cc_emails if email and email != recipient))
    subject, text, html = client_invoice_email_template(invoice)
    pdf = invoice_pdf_bytes(invoice)
    filename = invoice.invoice_number.replace("/", "-")
    status, detail = send_sendgrid_email(
        to_email=recipient,
        cc_emails=cc_emails,
        subject=subject,
        text=text,
        html=html,
        attachments=[
            {
                "content": base64.b64encode(pdf).decode("ascii"),
                "filename": f"{filename}.pdf",
                "type": "application/pdf",
                "disposition": "attachment",
            }
        ],
    )
    invoice.status = InvoiceStatus.sent_to_client.value
    invoice.sent_at = utcnow()
    db.add(
        EmailNotification(
            project_id=invoice.project_id,
            invoice_id=invoice.id,
            recipient_email=recipient,
            cc_email=",".join(cc_emails) if cc_emails else None,
            subject=subject,
            body=html if detail is None else f"{html}\n\nSendGrid detail: {detail}",
            status=status,
        )
    )
    log_event(db, project_id=invoice.project_id, invoice_id=invoice.id, actor_name=payload.sender_name, action="invoice_sent_to_client", details=recipient)
    db.commit()
    return load_invoice_detail(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/cancel", response_model=InvoiceDetailRead)
def cancel_invoice(invoice_id: int, payload: CancelInvoiceCreate, _: AuthContext = Depends(require_role(UserRole.finance_manager.value)), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.scalar(select(ClientInvoice).where(ClientInvoice.id == invoice_id).options(selectinload(ClientInvoice.payments)))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.paid.value:
        raise HTTPException(status_code=400, detail="Paid invoices cannot be cancelled")
    if invoice.status in {InvoiceStatus.cancelled.value, InvoiceStatus.partially_paid_remainder_cancelled.value}:
        raise HTTPException(status_code=400, detail=f"Invoice is already cancelled: {invoice.status}")
    paid_total = sum((payment.amount_received for payment in invoice.payments), Decimal("0.00"))
    invoice.status = InvoiceStatus.partially_paid_remainder_cancelled.value if paid_total > 0 else InvoiceStatus.cancelled.value
    invoice.cancelled_reason = payload.reason
    cancelled_amount = max(invoice.amount - paid_total, Decimal("0.00"))
    log_event(
        db,
        project_id=invoice.project_id,
        invoice_id=invoice.id,
        actor_name=payload.cancelled_by_name,
        action="invoice_cancelled",
        details=f"{payload.reason}; cancelled_amount={cancelled_amount}; paid_total={paid_total}",
    )
    db.commit()
    return load_invoice_detail(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/payments", response_model=InvoiceDetailRead, status_code=201)
def record_payment(invoice_id: int, payload: PaymentCreate, _: AuthContext = Depends(require_role(UserRole.finance_manager.value)), db: Session = Depends(get_db)) -> InvoiceDetailRead:
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
    return load_invoice_detail(invoice_id, db)
