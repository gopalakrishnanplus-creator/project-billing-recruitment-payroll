from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    system_admin = "system_admin"
    operations_manager = "operations_manager"
    hr_manager = "hr_manager"
    internal_interviewer = "internal_interviewer"
    finance_manager = "finance_manager"
    client_account_executive = "client_account_executive"
    job_candidate = "job_candidate"


class InvoiceStatus(str, Enum):
    draft = "draft"
    due_for_client_approval = "due_for_client_approval"
    approved_by_client_account = "approved_by_client_account"
    approved_for_sending = "approved_for_sending"
    sent_to_client = "sent_to_client"
    partially_paid = "partially_paid"
    partially_paid_remainder_cancelled = "partially_paid_remainder_cancelled"
    paid = "paid"
    cancelled = "cancelled"


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role_assignments: Mapped[list["UserRoleAssignment"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_role_assignments_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_by_name: Mapped[str | None] = mapped_column(String(160))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[AppUser] = relationship(back_populates="role_assignments")


class ClientCompany(Base):
    __tablename__ = "client_companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    billing_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contacts: Mapped[list["ClientContact"]] = relationship(back_populates="company")
    msas: Mapped[list["MasterServiceAgreement"]] = relationship(back_populates="company")


class ClientContact(Base):
    __tablename__ = "client_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80))
    role_title: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[ClientCompany] = relationship(back_populates="contacts")


class MasterServiceAgreement(Base):
    __tablename__ = "master_service_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    signed_date: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[ClientCompany] = relationship(back_populates="msas")
    projects: Mapped[list["ProjectSOW"]] = relationship(back_populates="msa")


class ProjectSOW(Base):
    __tablename__ = "project_sows"
    __table_args__ = (UniqueConstraint("project_code", name="uq_project_sows_project_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_code: Mapped[str] = mapped_column(String(40), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id"), nullable=False)
    client_contact_id: Mapped[int] = mapped_column(ForeignKey("client_contacts.id"), nullable=False)
    msa_id: Mapped[int | None] = mapped_column(ForeignKey("master_service_agreements.id"))
    client_account_executive_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sow_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(12), default="USD")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    operations_manager_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[ClientCompany] = relationship()
    client_contact: Mapped[ClientContact] = relationship()
    client_account_executive: Mapped[AppUser | None] = relationship()
    msa: Mapped[MasterServiceAgreement] = relationship(back_populates="projects")
    recruitment_needs: Mapped[list["RecruitmentNeed"]] = relationship(back_populates="project")
    invoice_schedules: Mapped[list["ClientInvoiceSchedule"]] = relationship(back_populates="project")
    client_invoices: Mapped[list["ClientInvoice"]] = relationship(back_populates="project")
    documents: Mapped[list["UploadedDocument"]] = relationship(back_populates="project")


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project_sows.id"))
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(500))
    stored_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int | None] = mapped_column()
    content_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    uploaded_by_name: Mapped[str | None] = mapped_column(String(160))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[ProjectSOW | None] = relationship(back_populates="documents")


class RecruitmentNeed(Base):
    __tablename__ = "recruitment_needs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_sows.id"), nullable=False)
    position_title: Mapped[str] = mapped_column(String(180), nullable=False)
    number_of_positions: Mapped[int] = mapped_column(default=1)
    employment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    position_billing_type: Mapped[str | None] = mapped_column(String(40))
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(12))
    billing_frequency: Mapped[str | None] = mapped_column(String(40))
    billing_start_date: Mapped[date | None] = mapped_column(Date)
    billing_end_date: Mapped[date | None] = mapped_column(Date)
    target_start_date: Mapped[date | None] = mapped_column(Date)
    internal_interviewers: Mapped[str | None] = mapped_column(Text)
    detail_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    jd_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    job_ad_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    linkedin_ad_url: Mapped[str | None] = mapped_column(String(500))
    jd_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(80), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[ProjectSOW] = relationship(back_populates="recruitment_needs")


class ClientInvoiceSchedule(Base):
    __tablename__ = "client_invoice_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_sows.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    item_description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), default="USD")
    frequency: Mapped[str] = mapped_column(String(40), nullable=False)
    first_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    final_invoice_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(60), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[ProjectSOW] = relationship(back_populates="invoice_schedules")
    invoices: Mapped[list["ClientInvoice"]] = relationship(back_populates="schedule")


class ClientInvoice(Base):
    __tablename__ = "client_invoices"
    __table_args__ = (UniqueConstraint("invoice_number", name="uq_client_invoices_invoice_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("client_invoice_schedules.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_sows.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), default="USD")
    status: Mapped[str] = mapped_column(String(80), default=InvoiceStatus.due_for_client_approval.value)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[ProjectSOW] = relationship(back_populates="client_invoices")
    schedule: Mapped[ClientInvoiceSchedule] = relationship(back_populates="invoices")
    approvals: Mapped[list["ClientInvoiceApproval"]] = relationship(back_populates="invoice")
    payments: Mapped[list["ClientPayment"]] = relationship(back_populates="invoice")


class ClientInvoiceApproval(Base):
    __tablename__ = "client_invoice_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("client_invoices.id"), nullable=False)
    approval_type: Mapped[str] = mapped_column(String(80), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[ClientInvoice] = relationship(back_populates="approvals")


class ClientPayment(Base):
    __tablename__ = "client_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("client_invoices.id"), nullable=False)
    amount_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    bank_reference: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by_name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[ClientInvoice] = relationship(back_populates="payments")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_sows.id"), nullable=False)
    recruitment_need_id: Mapped[int | None] = mapped_column(ForeignKey("recruitment_needs.id"))
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80))
    linkedin_profile_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    candidate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="entered")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateScreeningForm(Base):
    __tablename__ = "candidate_screening_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    form_url: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_payload: Mapped[str | None] = mapped_column(Text)


class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[int | None] = mapped_column()
    recommendation: Mapped[str | None] = mapped_column(String(80))
    evaluation_payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    interviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    interviewer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    calendly_url: Mapped[str | None] = mapped_column(String(500))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(80), default="pending")


class InterviewScorecard(Base):
    __tablename__ = "interview_scorecards"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    interviewer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[int] = mapped_column()
    recommendation: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    evaluation_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateContract(Base):
    __tablename__ = "candidate_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    contract_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    invoice_terms: Mapped[str | None] = mapped_column(Text)
    invoice_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(12))
    invoice_frequency: Mapped[str | None] = mapped_column(String(40))
    invoice_start_date: Mapped[date | None] = mapped_column(Date)
    invoice_end_date: Mapped[date | None] = mapped_column(Date)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(80), default="draft")


class CandidateVendorInvoice(Base):
    __tablename__ = "candidate_vendor_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    invoice_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), default="USD")
    status: Mapped[str] = mapped_column(String(80), default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateInvoiceApproval(Base):
    __tablename__ = "candidate_invoice_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_invoice_id: Mapped[int] = mapped_column(ForeignKey("candidate_vendor_invoices.id"), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidatePayment(Base):
    __tablename__ = "candidate_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_invoice_id: Mapped[int] = mapped_column(ForeignKey("candidate_vendor_invoices.id"), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_date: Mapped[date] = mapped_column(Date, nullable=False)
    bank_reference: Mapped[str | None] = mapped_column(String(180))
    recorded_by_name: Mapped[str] = mapped_column(String(160), nullable=False)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project_sows.id"))
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="queued")
    input_payload: Mapped[str | None] = mapped_column(Text)
    output_payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailNotification(Base):
    __tablename__ = "email_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project_sows.id"))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("client_invoices.id"))
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    cc_email: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project_sows.id"))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("client_invoices.id"))
    actor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
