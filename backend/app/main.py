from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from html import escape
from os import getenv
from pathlib import Path
from uuid import uuid4

from authlib.integrations.starlette_client import OAuth
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, SessionLocal, engine, get_db
from .models import (
    ActivityLog,
    AppUser,
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
    UserRole,
    UserRoleAssignment,
    utcnow,
)
from .schemas import (
    ApprovalCreate,
    AppUserRead,
    AppUserUpsert,
    ClientInvoiceRead,
    CurrentUserRead,
    GenerateInvoicesResult,
    InvoiceDetailRead,
    InvoiceScheduleCreate,
    InvoiceScheduleRead,
    PaymentCreate,
    PaymentRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    RecruitmentNeedCreate,
    RecruitmentNeedRead,
    RoleSelect,
    SendInvoiceCreate,
    SOWCreate,
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
SENDGRID_FROM_EMAIL = getenv("SENDGRID_FROM_EMAIL", "no-reply@flexgcc.com")
SENDGRID_FROM_NAME = getenv("SENDGRID_FROM_NAME", "FlexGCC PBRP")
FINANCE_MANAGER_EMAIL = getenv("FINANCE_MANAGER_EMAIL", "")
INVOICE_CRON_TOKEN = getenv("INVOICE_CRON_TOKEN", "")


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
    with engine.begin() as conn:
        if "project_sows" in tables:
            existing = {column["name"] for column in inspector.get_columns("project_sows")}
            if "client_account_executive_id" not in existing:
                conn.execute(text("ALTER TABLE project_sows ADD COLUMN client_account_executive_id INTEGER"))
        if "uploaded_documents" in tables:
            existing = {column["name"] for column in inspector.get_columns("uploaded_documents")}
            if "stored_filename" not in existing:
                conn.execute(text("ALTER TABLE uploaded_documents ADD COLUMN stored_filename VARCHAR(255)"))
            if "content_type" not in existing:
                conn.execute(text("ALTER TABLE uploaded_documents ADD COLUMN content_type VARCHAR(120)"))
            if "file_size" not in existing:
                conn.execute(text("ALTER TABLE uploaded_documents ADD COLUMN file_size INTEGER"))
        if "email_notifications" in tables:
            existing = {column["name"] for column in inspector.get_columns("email_notifications")}
            if "cc_email" not in existing:
                conn.execute(text("ALTER TABLE email_notifications ADD COLUMN cc_email TEXT"))


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
        client_contact_name=project.client_contact.full_name,
        client_contact_email=project.client_contact.email,
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
        client_account_executive_email=invoice.project.client_account_executive.email if invoice.project.client_account_executive else None,
        payments=[PaymentRead.model_validate(payment) for payment in invoice.payments],
        paid_total=paid_total,
        balance_due=balance_due,
    )


def load_invoice_detail(invoice_id: int, db: Session) -> InvoiceDetailRead:
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
    return serialize_invoice(invoice)


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


def finance_manager_emails(db: Session) -> list[str]:
    emails = [user.email for user in users_with_role(db, UserRole.finance_manager.value)]
    if FINANCE_MANAGER_EMAIL:
        emails.extend(email.strip() for email in FINANCE_MANAGER_EMAIL.split(",") if email.strip())
    return sorted(set(emails))


def invoice_template(invoice: ClientInvoice) -> tuple[str, str, str]:
    approval_link = f"{FRONTEND_URL}/?invoice_id={invoice.id}"
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


def send_sendgrid_email(*, to_email: str, cc_emails: list[str], subject: str, text: str, html: str) -> tuple[str, str | None]:
    if not SENDGRID_API_KEY:
        return "not_configured", None
    personalizations: dict[str, object] = {"to": [{"email": to_email}]}
    if cc_emails:
        personalizations["cc"] = [{"email": email} for email in cc_emails if email != to_email]
    payload = {
        "personalizations": [personalizations],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": SENDGRID_FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }
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
                db.flush()
                generated.append(invoice)
                queue_invoice_approval_email(db, invoice)
                log_event(db, project_id=schedule.project_id, actor_name="System", action="client_invoice_generated", details=invoice.invoice_number)
            if schedule.frequency == "single":
                break
            candidate_date = next_date(candidate_date, schedule.frequency)
    return generated


@app.get("/auth/login")
async def auth_login(request: Request):
    if not GOOGLE_CONFIGURED:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    redirect_uri = getenv("GOOGLE_REDIRECT_URI", f"{API_BASE_URL}/auth/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


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
            "app_users",
            "user_role_assignments",
        ],
        "reserved_later_flow_tables": [
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
async def create_project(request: Request, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> ProjectRead:
    data, files = await request_payload_and_files(request)
    payload: ProjectCreate = parse_model(ProjectCreate, data)
    validate_client_account_executive(db, payload.client_account_executive_id)
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
    if payload.client_account_executive_id is not None:
        validate_client_account_executive(db, payload.client_account_executive_id)
        project.client_account_executive_id = payload.client_account_executive_id
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
def add_recruitment_need(project_id: int, payload: RecruitmentNeedCreate, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> RecruitmentNeedRead:
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
def add_invoice_schedule(project_id: int, payload: InvoiceScheduleCreate, _: AuthContext = Depends(require_role(UserRole.operations_manager.value)), db: Session = Depends(get_db)) -> InvoiceScheduleRead:
    project = db.get(ProjectSOW, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.frequency == "single":
        payload.final_invoice_date = None
    if payload.final_invoice_date and payload.final_invoice_date < payload.first_invoice_date:
        raise HTTPException(status_code=400, detail="Final invoice date cannot be earlier than first invoice date")
    schedule = ClientInvoiceSchedule(project_id=project_id, **payload.model_dump())
    db.add(schedule)
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
def list_invoices(context: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> list[InvoiceDetailRead]:
    query = select(ClientInvoice).order_by(ClientInvoice.issue_date.desc(), ClientInvoice.id.desc())
    if context.active_role == UserRole.client_account_executive.value:
        query = query.join(ProjectSOW, ProjectSOW.id == ClientInvoice.project_id).where(ProjectSOW.client_account_executive_id == context.user.id)
    invoices = db.scalars(
        query.options(
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.company),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_contact),
            selectinload(ClientInvoice.project).selectinload(ProjectSOW.client_account_executive),
            selectinload(ClientInvoice.payments),
        )
    ).all()
    return [serialize_invoice(invoice) for invoice in invoices]

@app.get("/client-invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(invoice_id: int, _: AuthContext = Depends(require_login), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    return load_invoice_detail(invoice_id, db)


@app.post("/client-invoices/{invoice_id}/client-account-approval", response_model=InvoiceDetailRead)
def approve_client_account(invoice_id: int, payload: ApprovalCreate, _: AuthContext = Depends(require_role(UserRole.client_account_executive.value)), db: Session = Depends(get_db)) -> InvoiceDetailRead:
    invoice = db.get(ClientInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
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
