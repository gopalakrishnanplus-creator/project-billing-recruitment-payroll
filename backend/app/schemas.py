from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ProjectCreate(BaseModel):
    client_company_name: str = Field(min_length=2, max_length=255)
    client_contact_name: str = Field(min_length=2, max_length=160)
    client_contact_email: EmailStr
    client_contact_phone: str | None = None
    client_account_executive_id: int
    msa_reference: str = Field(min_length=2, max_length=120)
    msa_document_name: str | None = None
    sow_title: str = Field(min_length=2, max_length=255)
    sow_description: str | None = None
    sow_document_name: str | None = None
    sow_amount: Decimal = Field(ge=0)
    currency: str = "USD"
    start_date: date
    end_date: date | None = None
    operations_manager_name: str = Field(min_length=2, max_length=160)


class ProjectUpdate(BaseModel):
    client_contact_name: str | None = Field(default=None, min_length=2, max_length=160)
    client_contact_email: EmailStr | None = None
    client_contact_phone: str | None = None
    client_account_executive_id: int | None = None
    msa_reference: str | None = Field(default=None, min_length=2, max_length=120)
    sow_title: str | None = Field(default=None, min_length=2, max_length=255)
    sow_description: str | None = None
    sow_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    operations_manager_name: str | None = Field(default=None, min_length=2, max_length=160)


class SOWCreate(BaseModel):
    sow_title: str = Field(min_length=2, max_length=255)
    sow_description: str | None = None
    sow_amount: Decimal = Field(ge=0)
    currency: str = "USD"
    start_date: date
    end_date: date | None = None
    operations_manager_name: str = Field(min_length=2, max_length=160)


class RecruitmentNeedCreate(BaseModel):
    position_title: str = Field(min_length=2, max_length=180)
    number_of_positions: int = Field(default=1, ge=1)
    employment_type: str
    description: str = Field(min_length=5)
    position_billing_type: str | None = Field(default=None, pattern="^(fixed_fee|periodic)$")
    fee_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = "USD"
    billing_frequency: str | None = Field(default=None, pattern="^(single|weekly|monthly|quarterly)$")
    billing_start_date: date | None = None
    billing_end_date: date | None = None
    target_start_date: date | None = None
    internal_interviewers: str | None = None


class RecruitmentNeedUpdate(BaseModel):
    position_title: str | None = Field(default=None, min_length=2, max_length=180)
    number_of_positions: int | None = Field(default=None, ge=1)
    employment_type: str | None = None
    description: str | None = Field(default=None, min_length=5)
    position_billing_type: str | None = Field(default=None, pattern="^(fixed_fee|periodic)$")
    fee_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    billing_frequency: str | None = Field(default=None, pattern="^(single|weekly|monthly|quarterly)$")
    billing_start_date: date | None = None
    billing_end_date: date | None = None
    target_start_date: date | None = None
    internal_interviewers: str | None = None
    status: str | None = None


class RecruitmentAssetCreate(BaseModel):
    linkedin_ad_url: str | None = None


class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    phone: str | None = None
    linkedin_profile_url: str | None = None
    notes: str | None = None
    candidate_type: str = "job_candidate"


class CandidateStatusUpdate(BaseModel):
    status: str = Field(pattern="^(entered|shortlisted_for_interview|rejected|backup_candidate|interview_scheduled|evaluation_submitted|send_contract|hired)$")


class InterviewCreate(BaseModel):
    interviewer_user_id: int
    calendly_url: str | None = None
    scheduled_at: datetime | None = None


class ScorecardCreate(BaseModel):
    score: int = Field(ge=0, le=100)
    recommendation: str
    notes: str | None = None


class CandidateContractCreate(BaseModel):
    invoice_terms: str | None = None
    invoice_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = "USD"
    invoice_frequency: str | None = Field(default=None, pattern="^(single|weekly|monthly|quarterly)$")
    invoice_start_date: date | None = None
    invoice_end_date: date | None = None
    invoice_date: date | None = None


class InvoiceScheduleCreate(BaseModel):
    label: str = Field(min_length=2, max_length=180)
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    frequency: str = Field(pattern="^(single|monthly|weekly|quarterly)$")
    first_invoice_date: date
    final_invoice_date: date | None = None


class ApprovalCreate(BaseModel):
    approver_name: str = Field(min_length=2, max_length=160)
    notes: str | None = None


class SendInvoiceCreate(BaseModel):
    recipient_email: EmailStr | None = None
    sender_name: str = Field(min_length=2, max_length=160)
    cc_email: EmailStr | None = None


class CancelInvoiceCreate(BaseModel):
    cancelled_by_name: str = Field(min_length=2, max_length=160)
    reason: str = Field(min_length=2)


class PaymentCreate(BaseModel):
    amount_received: Decimal = Field(gt=0)
    received_date: date
    bank_reference: str | None = None
    notes: str | None = None
    recorded_by_name: str = Field(min_length=2, max_length=160)


class RoleSelect(BaseModel):
    role: str


class AppUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    is_active: bool
    roles: list[str]


class AppUserUpsert(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    roles: list[str] = Field(min_length=1)
    is_active: bool = True


class CurrentUserRead(BaseModel):
    authenticated: bool
    id: int | None = None
    full_name: str | None = None
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    active_role: str | None = None


class RecruitmentNeedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    position_title: str
    number_of_positions: int
    employment_type: str
    description: str
    position_billing_type: str | None
    fee_amount: Decimal | None
    currency: str | None
    billing_frequency: str | None
    billing_start_date: date | None
    billing_end_date: date | None
    target_start_date: date | None
    internal_interviewers: str | None
    detail_document_id: int | None
    jd_document_id: int | None
    job_ad_document_id: int | None
    linkedin_ad_url: str | None
    status: str


class RecruitmentNeedDetailRead(RecruitmentNeedRead):
    project_code: str
    project_title: str
    client_company_name: str
    detail_document_name: str | None = None
    jd_document_name: str | None = None
    job_ad_document_name: str | None = None


class InterviewRead(BaseModel):
    id: int
    candidate_id: int
    interviewer_user_id: int | None
    interviewer_name: str
    calendly_url: str | None
    scheduled_at: datetime | None
    status: str
    score: int | None = None
    recommendation: str | None = None
    notes: str | None = None
    evaluation_document_id: int | None = None
    evaluation_document_name: str | None = None


class CandidateContractRead(BaseModel):
    id: int
    candidate_id: int
    contract_document_id: int | None
    contract_document_name: str | None = None
    invoice_terms: str | None
    invoice_amount: Decimal | None
    currency: str | None
    invoice_frequency: str | None
    invoice_start_date: date | None
    invoice_end_date: date | None
    invoice_date: date | None
    signed_at: datetime | None
    status: str


class CandidateRead(BaseModel):
    id: int
    project_id: int
    recruitment_need_id: int | None
    full_name: str
    email: str
    phone: str | None
    linkedin_profile_url: str | None
    notes: str | None
    candidate_type: str
    status: str
    created_at: datetime
    project_code: str
    project_title: str
    client_company_name: str
    position_title: str | None = None
    interviews: list[InterviewRead] = Field(default_factory=list)
    contracts: list[CandidateContractRead] = Field(default_factory=list)


class InvoiceScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    amount: Decimal
    currency: str
    frequency: str
    first_invoice_date: date
    final_invoice_date: date | None
    status: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_type: str
    original_filename: str
    content_type: str | None
    file_size: int | None


class ClientInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    schedule_id: int
    invoice_number: str
    issue_date: date
    due_date: date
    amount: Decimal
    currency: str
    status: str
    sent_at: datetime | None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_code: str
    title: str
    description: str | None
    sow_amount: Decimal
    currency: str
    start_date: date
    end_date: date | None
    operations_manager_name: str
    status: str
    client_company_name: str
    client_contact_name: str
    client_contact_email: str
    client_account_executive_id: int | None
    client_account_executive_name: str | None
    client_account_executive_email: str | None
    msa_reference: str | None
    documents: list[DocumentRead] = Field(default_factory=list)
    recruitment_needs: list[RecruitmentNeedRead] = Field(default_factory=list)
    invoice_schedules: list[InvoiceScheduleRead] = Field(default_factory=list)
    client_invoices: list[ClientInvoiceRead] = Field(default_factory=list)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount_received: Decimal
    received_date: date
    bank_reference: str | None
    notes: str | None
    recorded_by_name: str


class InvoiceDetailRead(ClientInvoiceRead):
    project_code: str
    project_title: str
    client_company_name: str
    client_contact_name: str
    client_contact_email: str
    client_account_executive_email: str | None
    payments: list[PaymentRead] = Field(default_factory=list)
    paid_total: Decimal
    cancelled_amount: Decimal
    balance_due: Decimal


class GenerateInvoicesResult(BaseModel):
    generated_count: int
    invoices: list[ClientInvoiceRead]
