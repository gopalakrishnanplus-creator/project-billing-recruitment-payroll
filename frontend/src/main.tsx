import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import BadgeCheck from 'lucide-react/dist/esm/icons/badge-check.mjs';
import Banknote from 'lucide-react/dist/esm/icons/banknote.mjs';
import CalendarPlus from 'lucide-react/dist/esm/icons/calendar-plus.mjs';
import ClipboardList from 'lucide-react/dist/esm/icons/clipboard-list.mjs';
import Download from 'lucide-react/dist/esm/icons/download.mjs';
import FileCheck2 from 'lucide-react/dist/esm/icons/file-check-2.mjs';
import FilePlus2 from 'lucide-react/dist/esm/icons/file-plus-2.mjs';
import FileText from 'lucide-react/dist/esm/icons/file-text.mjs';
import LogOut from 'lucide-react/dist/esm/icons/log-out.mjs';
import Pencil from 'lucide-react/dist/esm/icons/pencil.mjs';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw.mjs';
import Send from 'lucide-react/dist/esm/icons/send.mjs';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check.mjs';
import Upload from 'lucide-react/dist/esm/icons/upload.mjs';
import UserCheck from 'lucide-react/dist/esm/icons/user-check.mjs';
import UserCog from 'lucide-react/dist/esm/icons/user-cog.mjs';
import Users from 'lucide-react/dist/esm/icons/users.mjs';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001';

const ROLE_LABELS: Record<string, string> = {
  system_admin: 'System Admin',
  operations_manager: 'Operations Manager',
  hr_manager: 'HR Manager',
  internal_interviewer: 'Internal Interviewer',
  finance_manager: 'Finance Manager',
  client_account_executive: 'Client Account Executive',
  job_candidate: 'Job Candidate',
};

const ALL_ROLES = Object.keys(ROLE_LABELS);

const INVOICE_STATUSES = [
  'due_for_client_approval',
  'approved_by_client_account',
  'approved_for_sending',
  'sent_to_client',
  'partially_paid',
  'partially_paid_remainder_cancelled',
  'paid',
  'cancelled',
];
const UPCOMING_INVOICES_FILTER = 'upcoming_invoices';
const CANDIDATE_INVOICE_STATUSES = ['submitted', 'on-hold', 'rejected', 'approved', 'paid', 'partially_paid'];

type Project = {
  id: number;
  project_code: string;
  title: string;
  description: string | null;
  sow_amount: string;
  currency: string;
  start_date: string;
  end_date: string | null;
  operations_manager_name: string;
  status: string;
  client_company_name: string;
  client_billing_address: string | null;
  client_contact_name: string;
  client_contact_email: string;
  client_contact_phone: string | null;
  client_account_executive_id: number | null;
  client_account_executive_name: string | null;
  client_account_executive_email: string | null;
  msa_reference: string | null;
  documents: UploadedDocument[];
  recruitment_needs: RecruitmentNeed[];
  invoice_schedules: InvoiceSchedule[];
  client_invoices: ClientInvoice[];
};

type RecruitmentNeed = {
  id: number;
  project_id: number;
  position_title: string;
  number_of_positions: number;
  employment_type: string;
  description: string;
  position_billing_type: string | null;
  fee_amount: string | null;
  currency: string | null;
  billing_frequency: string | null;
  billing_start_date: string | null;
  billing_end_date: string | null;
  target_start_date: string | null;
  internal_interviewers: string | null;
  detail_document_id: number | null;
  jd_document_id: number | null;
  job_ad_document_id: number | null;
  linkedin_ad_url: string | null;
  status: string;
};

type RecruitmentNeedDetail = RecruitmentNeed & {
  project_code: string;
  project_title: string;
  client_company_name: string;
  detail_document_name: string | null;
  jd_document_name: string | null;
  job_ad_document_name: string | null;
};

type InvoiceSchedule = {
  id: number;
  label: string;
  item_description: string | null;
  amount: string;
  currency: string;
  frequency: string;
  first_invoice_date: string;
  final_invoice_date: string | null;
  historical_backfill: boolean;
  next_invoice_generation_date: string | null;
};

type UploadedDocument = {
  id: number;
  document_type: string;
  original_filename: string;
  content_type: string | null;
  file_size: number | null;
};

type ClientInvoice = {
  id: number;
  project_id: number;
  invoice_number: string;
  issue_date: string;
  due_date: string;
  item_description: string | null;
  amount: string;
  currency: string;
  status: string;
  project_code?: string;
  project_title?: string;
  client_company_name?: string;
  client_billing_address?: string | null;
  client_contact_name?: string;
  client_contact_email?: string;
  paid_total?: string;
  cancelled_amount?: string;
  balance_due?: string;
};

type UpcomingInvoice = {
  schedule_id: number;
  project_id: number;
  project_code: string;
  project_title: string;
  client_company_name: string;
  client_account_executive_email: string | null;
  label: string;
  item_description: string | null;
  amount: string;
  currency: string;
  frequency: string;
  next_invoice_date: string;
  final_invoice_date: string | null;
};

type Interview = {
  id: number;
  candidate_id: number;
  interviewer_user_id: number | null;
  interviewer_name: string;
  calendly_url: string | null;
  scheduled_at: string | null;
  status: string;
  score: number | null;
  recommendation: string | null;
  notes: string | null;
  evaluation_document_id: number | null;
  evaluation_document_name: string | null;
};

type CandidateContract = {
  id: number;
  candidate_id: number;
  contract_document_id: number | null;
  contract_document_name: string | null;
  invoice_terms: string | null;
  invoice_amount: string | null;
  currency: string | null;
  invoice_frequency: string | null;
  invoice_start_date: string | null;
  invoice_end_date: string | null;
  invoice_date: string | null;
  signed_at: string | null;
  status: string;
};

type Candidate = {
  id: number;
  project_id: number;
  recruitment_need_id: number | null;
  full_name: string;
  email: string;
  phone: string | null;
  linkedin_profile_url: string | null;
  notes: string | null;
  candidate_type: string;
  status: string;
  created_at: string;
  project_code: string;
  project_title: string;
  client_company_name: string;
  position_title: string | null;
  interviews: Interview[];
  contracts: CandidateContract[];
};

type CandidateInvoiceUpload = {
  candidate_name: string;
  candidate_email: string;
  project_code: string;
  project_title: string;
  client_company_name: string;
  position_title: string | null;
  invoice_due_date: string | null;
  amount: string;
  currency: string;
  status: string;
  token_used: boolean;
};

type CandidateInvoice = {
  id: number;
  candidate_id: number;
  contract_id: number | null;
  project_id: number | null;
  invoice_document_id: number | null;
  invoice_document_name: string | null;
  candidate_name: string;
  candidate_email: string;
  project_code: string;
  project_title: string;
  client_company_name: string;
  client_account_executive_email: string | null;
  position_title: string | null;
  invoice_due_date: string | null;
  amount: string;
  currency: string;
  status: string;
  submitted_at: string;
  approval_comments: string | null;
  paid_total: string;
  balance_due: string;
};

type CurrentUser = {
  authenticated: boolean;
  id: number | null;
  full_name: string | null;
  email: string | null;
  roles: string[];
  active_role: string | null;
};

type AppUser = {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
  roles: string[];
};

type Notice = { tone: 'ok' | 'error'; message: string } | null;

const ANONYMOUS_USER: CurrentUser = {
  authenticated: false,
  id: null,
  full_name: null,
  email: null,
  roles: [],
  active_role: null,
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(formatApiErrorDetail(body.detail ?? `Request failed with ${response.status}`));
  }
  return response.json() as Promise<T>;
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object') {
          const record = item as { loc?: unknown; msg?: unknown; detail?: unknown };
          const location = Array.isArray(record.loc) ? record.loc.join('.') : '';
          const message =
            typeof record.msg === 'string'
              ? record.msg
              : typeof record.detail === 'string'
                ? record.detail
                : JSON.stringify(record);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    return JSON.stringify(detail);
  }
  return 'Request failed';
}

function today(): string {
  return formatLocalDate(new Date());
}

function endOfCurrentMonth(): string {
  const now = new Date();
  return formatLocalDate(new Date(now.getFullYear(), now.getMonth() + 1, 0));
}

function formatLocalDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formPayload(form: HTMLFormElement): Record<string, FormDataEntryValue> {
  return Object.fromEntries(Array.from(new FormData(form).entries()).filter(([, value]) => value !== ''));
}

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role.replaceAll('_', ' ');
}

function latestContract(candidate: Candidate): CandidateContract | undefined {
  return candidate.contracts[0];
}

function contractInvoiceSummary(contract: CandidateContract | undefined): string {
  if (!contract) return 'Not set';
  const currency = contract.currency ?? 'USD';
  const amount = contract.invoice_amount ?? 'Not set';
  const frequency = contract.invoice_frequency ?? 'not set';
  return `${currency} ${amount} · ${frequency}`;
}

function contractInvoiceDates(contract: CandidateContract | undefined): string {
  if (!contract) return 'Not set';
  const start = contract.invoice_date ?? contract.invoice_start_date ?? 'Not set';
  return contract.invoice_end_date ? `${start} to ${contract.invoice_end_date}` : start;
}

function App() {
  const urlParams = new URLSearchParams(window.location.search);
  const approvalInvoiceId = urlParams.get('approval_invoice_id');
  const approvalError = urlParams.get('approval_error');
  const candidateInvoiceToken = urlParams.get('candidate_invoice_token');
  const candidateInvoiceId = urlParams.get('candidate_invoice_id');
  const candidateInvoiceError = urlParams.get('candidate_invoice_error');
  const requestedView = urlParams.get('view');
  const requestedNeedId = Number(urlParams.get('need_id') ?? '');
  const requestedInterviewId = Number(urlParams.get('interview_id') ?? '');
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [clientAccountExecutives, setClientAccountExecutives] = useState<AppUser[]>([]);
  const [internalInterviewers, setInternalInterviewers] = useState<AppUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [invoices, setInvoices] = useState<ClientInvoice[]>([]);
  const [upcomingInvoices, setUpcomingInvoices] = useState<UpcomingInvoice[]>([]);
  const [approvalInvoice, setApprovalInvoice] = useState<ClientInvoice | null>(null);
  const [candidateInvoices, setCandidateInvoices] = useState<CandidateInvoice[]>([]);
  const [candidateInvoiceUpload, setCandidateInvoiceUpload] = useState<CandidateInvoiceUpload | null>(null);
  const [candidateApprovalInvoice, setCandidateApprovalInvoice] = useState<CandidateInvoice | null>(null);
  const [recruitmentNeeds, setRecruitmentNeeds] = useState<RecruitmentNeedDetail[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(null);
  const [selectedCandidateInvoiceId, setSelectedCandidateInvoiceId] = useState<number | null>(null);
  const [selectedNeedId, setSelectedNeedId] = useState<number | null>(Number.isFinite(requestedNeedId) && requestedNeedId > 0 ? requestedNeedId : null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [selectedInterviewId, setSelectedInterviewId] = useState<number | null>(Number.isFinite(requestedInterviewId) && requestedInterviewId > 0 ? requestedInterviewId : null);
  const [editingProject, setEditingProject] = useState(false);
  const [scheduleFrequency, setScheduleFrequency] = useState('monthly');
  const [scheduleBackfill, setScheduleBackfill] = useState(false);
  const [needBillingType, setNeedBillingType] = useState('periodic');
  const [internalRecruitmentProject, setInternalRecruitmentProject] = useState(false);
  const [contractInvoiceFrequency, setContractInvoiceFrequency] = useState('monthly');
  const [activeView, setActiveView] = useState<'workflow' | 'invoices' | 'recruitment'>(requestedView === 'recruitment' ? 'recruitment' : requestedView === 'invoices' ? 'invoices' : 'workflow');
  const [invoiceStatusFilter, setInvoiceStatusFilter] = useState('');
  const [invoiceDateFrom, setInvoiceDateFrom] = useState('');
  const [invoiceDateTo, setInvoiceDateTo] = useState('');
  const [invoicePage, setInvoicePage] = useState(1);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? projects[0],
    [projects, selectedProjectId],
  );
  const selectedInvoice = useMemo(
    () => invoices.find((invoice) => invoice.id === selectedInvoiceId) ?? invoices[0],
    [invoices, selectedInvoiceId],
  );
  const selectedCandidateInvoice = useMemo(
    () => candidateInvoices.find((invoice) => invoice.id === selectedCandidateInvoiceId) ?? candidateInvoices[0],
    [candidateInvoices, selectedCandidateInvoiceId],
  );
  const selectedNeed = useMemo(
    () => recruitmentNeeds.find((need) => need.id === selectedNeedId) ?? recruitmentNeeds[0],
    [recruitmentNeeds, selectedNeedId],
  );
  const candidatesForNeed = useMemo(
    () => candidates.filter((candidate) => !selectedNeed || candidate.recruitment_need_id === selectedNeed.id),
    [candidates, selectedNeed],
  );
  const hiredCandidates = useMemo(
    () => candidates.filter((candidate) => candidate.status === 'hired'),
    [candidates],
  );
  const selectedCandidate = useMemo(
    () => candidates.find((candidate) => candidate.id === selectedCandidateId) ?? candidatesForNeed[0] ?? candidates[0],
    [candidates, candidatesForNeed, selectedCandidateId],
  );
  const selectedCandidateContract = useMemo(
    () => (selectedCandidate ? latestContract(selectedCandidate) : undefined),
    [selectedCandidate],
  );
  const flexGccSalesSupportProjects = useMemo(
    () => projects.filter((project) => project.client_company_name.toLowerCase() === 'flexgcc' && project.title.toLowerCase() === 'flexgcc sales support'),
    [projects],
  );
  const selectedInterview = useMemo(
    () => interviews.find((interview) => interview.id === selectedInterviewId) ?? interviews[0],
    [interviews, selectedInterviewId],
  );

  const activeRole = me?.active_role;
  const canAdmin = activeRole === 'system_admin';
  const canOperate = activeRole === 'operations_manager';
  const canHrManage = activeRole === 'hr_manager';
  const canInterview = activeRole === 'internal_interviewer';
  const canFinance = activeRole === 'finance_manager';
  const canClientApprove = activeRole === 'client_account_executive';
  const canViewWorkflow = Boolean(activeRole && activeRole !== 'system_admin');
  const canRecruitment = Boolean(activeRole && ['operations_manager', 'hr_manager', 'internal_interviewer', 'system_admin'].includes(activeRole));
  const showingUpcomingInvoices = invoiceStatusFilter === UPCOMING_INVOICES_FILTER;
  const invoiceListCount = showingUpcomingInvoices ? upcomingInvoices.length : invoices.length;
  const invoicePageSize = 20;

  async function refreshMe() {
    const current = await api<CurrentUser>('/auth/me');
    setMe(current);
    return current;
  }

  async function refreshData(current = me, pageOverride = invoicePage) {
    if (!current?.authenticated || !current.active_role) return;
    setLoading(true);
    try {
      const invoiceParams = new URLSearchParams({ page: String(pageOverride), page_size: String(invoicePageSize) });
      if (invoiceStatusFilter && !showingUpcomingInvoices) invoiceParams.set('status', invoiceStatusFilter);
      if (invoiceDateFrom) invoiceParams.set('date_from', invoiceDateFrom);
      if (invoiceDateTo) invoiceParams.set('date_to', invoiceDateTo);
      const invoiceRequest = showingUpcomingInvoices
        ? api<UpcomingInvoice[]>(`/upcoming-invoices?${invoiceParams.toString()}`)
        : api<ClientInvoice[]>(`/client-invoices?${invoiceParams.toString()}`);
      const [projectData, invoiceData] = await Promise.all([
        api<Project[]>('/projects'),
        invoiceRequest,
      ]);
      setProjects(projectData);
      if (showingUpcomingInvoices) {
        setUpcomingInvoices(invoiceData as UpcomingInvoice[]);
        setInvoices([]);
      } else {
        setInvoices(invoiceData as ClientInvoice[]);
        setUpcomingInvoices([]);
      }
      if (current.active_role === 'operations_manager') {
        setClientAccountExecutives(await api<AppUser[]>('/users/by-role/client_account_executive'));
      }
      if (current.active_role === 'system_admin') {
        setClientAccountExecutives(await api<AppUser[]>('/users/by-role/client_account_executive'));
      }
      if (['operations_manager', 'hr_manager', 'system_admin'].includes(current.active_role)) {
        const needData = await api<RecruitmentNeedDetail[]>('/recruitment/needs');
        setRecruitmentNeeds(needData);
        if (!selectedNeedId && needData[0]) setSelectedNeedId(needData[0].id);
      }
      if (['operations_manager', 'hr_manager', 'system_admin'].includes(current.active_role)) {
        const candidateData = await api<Candidate[]>('/recruitment/candidates');
        setCandidates(candidateData);
        if (!selectedCandidateId && candidateData[0]) setSelectedCandidateId(candidateData[0].id);
      }
      if (['hr_manager', 'internal_interviewer', 'system_admin'].includes(current.active_role)) {
        const interviewData = await api<Interview[]>('/interviews');
        setInterviews(interviewData);
        if (!selectedInterviewId && interviewData[0]) setSelectedInterviewId(interviewData[0].id);
      }
      if (current.active_role === 'hr_manager') {
        setInternalInterviewers(await api<AppUser[]>('/users/by-role/internal_interviewer'));
      }
      if (!selectedProjectId && projectData[0]) setSelectedProjectId(projectData[0].id);
      if (!showingUpcomingInvoices && !selectedInvoiceId && invoiceData[0]) setSelectedInvoiceId((invoiceData[0] as ClientInvoice).id);
      if (['finance_manager', 'operations_manager', 'hr_manager', 'client_account_executive', 'system_admin'].includes(current.active_role)) {
        const candidateInvoiceData = await api<CandidateInvoice[]>('/candidate-invoices');
        setCandidateInvoices(candidateInvoiceData);
        if (!selectedCandidateInvoiceId && candidateInvoiceData[0]) setSelectedCandidateInvoiceId(candidateInvoiceData[0].id);
      }
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Unable to load data' });
    } finally {
      setLoading(false);
    }
  }

  async function refreshUsers() {
    if (me?.active_role !== 'system_admin') return;
    setUsers(await api<AppUser[]>('/users'));
  }

  async function refreshAll() {
    setLoading(true);
    try {
      const current = await refreshMe();
      if (current.authenticated && current.active_role === 'system_admin') {
        setUsers(await api<AppUser[]>('/users'));
      }
      if (current.authenticated && current.active_role) {
        await refreshData(current);
      }
    } catch (error) {
      setMe(ANONYMOUS_USER);
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Unable to load app state' });
    } finally {
      setLoading(false);
    }
  }

  async function loadApprovalInvoice() {
    if (!approvalInvoiceId) return;
    setLoading(true);
    try {
      const invoice = await api<ClientInvoice>(`/client-invoices/${approvalInvoiceId}/client-account-approval-view`);
      setApprovalInvoice(invoice);
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'This invoice approval link is not available for this account.' });
    } finally {
      setLoading(false);
    }
  }

  async function loadCandidateInvoiceUpload() {
    if (!candidateInvoiceToken) return;
    setLoading(true);
    try {
      const invoice = await api<CandidateInvoiceUpload>(`/candidate-invoices/upload/${encodeURIComponent(candidateInvoiceToken)}`);
      setCandidateInvoiceUpload(invoice);
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'This candidate invoice upload link is not available.' });
    } finally {
      setLoading(false);
    }
  }

  async function loadCandidateApprovalInvoice() {
    if (!candidateInvoiceId) return;
    setLoading(true);
    try {
      const invoice = await api<CandidateInvoice>(`/candidate-invoices/${candidateInvoiceId}/client-account-approval-view`);
      setCandidateApprovalInvoice(invoice);
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'This candidate invoice approval link is not available for this account.' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const error = new URLSearchParams(window.location.search).get('auth_error');
    if (error) {
      setNotice({ tone: 'error', message: error === 'not_provisioned' ? 'This Google account has not been added by the system admin.' : 'No roles are assigned to this account.' });
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (candidateInvoiceToken) {
      void loadCandidateInvoiceUpload();
      return;
    }
    void refreshAll();
  }, []);

  useEffect(() => {
    if (approvalInvoiceId && me?.authenticated) void loadApprovalInvoice();
  }, [approvalInvoiceId, me?.authenticated]);

  useEffect(() => {
    if (candidateInvoiceId && me?.authenticated) void loadCandidateApprovalInvoice();
  }, [candidateInvoiceId, me?.authenticated]);

  useEffect(() => {
    if (me?.active_role === 'system_admin') void refreshUsers();
    if (me?.active_role) void refreshData(me);
  }, [me?.active_role, invoicePage]);

  useEffect(() => {
    setEditingProject(false);
  }, [selectedProjectId]);

  useEffect(() => {
    setContractInvoiceFrequency(selectedCandidateContract?.invoice_frequency ?? 'monthly');
  }, [selectedCandidateContract?.id, selectedCandidateContract?.invoice_frequency]);

  async function chooseRole(role: string) {
    await mutate(async () => {
      const current = await api<CurrentUser>('/auth/select-role', {
        method: 'POST',
        body: JSON.stringify({ role }),
      });
      setMe(current);
      return `Started ${roleLabel(role)} session`;
    });
  }

  async function logout() {
    await api('/auth/logout', { method: 'POST' });
    setMe({ authenticated: false, id: null, full_name: null, email: null, roles: [], active_role: null });
    setProjects([]);
    setInvoices([]);
    setUsers([]);
      setClientAccountExecutives([]);
      setInternalInterviewers([]);
      setRecruitmentNeeds([]);
      setCandidates([]);
      setInterviews([]);
      setUpcomingInvoices([]);
      setCandidateInvoices([]);
  }

  async function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    if (internalRecruitmentProject) {
      payload.set('internal_recruitment_project', 'true');
      payload.set('client_company_name', 'FlexGCC');
      payload.set('client_contact_name', 'FlexGCC Sales Support');
      payload.set('client_contact_email', 'finance@flexGCC.com');
      payload.set('sow_title', 'FlexGCC sales support');
      payload.set('sow_amount', '0');
      payload.delete('client_account_executive_id');
      payload.delete('msa_reference');
      payload.delete('msa_document');
      payload.delete('sow_document');
    }
    await mutate(async () => {
      const project = await api<Project>('/projects', {
        method: 'POST',
        body: payload,
      });
      setSelectedProjectId(project.id);
      formElement.reset();
      setInternalRecruitmentProject(false);
      return `Created ${project.project_code}`;
    });
  }

  async function submitProjectUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      const project = await api<Project>(`/projects/${selectedProject.id}`, {
        method: 'PUT',
        body: payload,
      });
      setSelectedProjectId(project.id);
      setEditingProject(false);
      return `Updated ${project.project_code}`;
    });
  }

  async function submitAdditionalSow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      const project = await api<Project>(`/projects/${selectedProject.id}/sows`, {
        method: 'POST',
        body: payload,
      });
      setSelectedProjectId(project.id);
      formElement.reset();
      return `Added ${project.project_code}`;
    });
  }

  async function submitNeed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    const historicalCompleted = payload.get('historical_completed') === 'on';
    const projectId = Number(payload.get('project_id') || selectedProject?.id);
    payload.delete('project_id');
    if (!projectId) return;
    await mutate(async () => {
      const need = await api<RecruitmentNeed>(`/projects/${projectId}/recruitment-needs`, {
        method: 'POST',
        body: payload,
      });
      setSelectedNeedId(need.id);
      formElement.reset();
      return historicalCompleted ? 'Historical recruitment position added as closed' : 'Recruitment position added and HR notified';
    });
  }

  async function submitHistoricalHire(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNeed) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      const candidate = await api<Candidate>(`/recruitment-needs/${selectedNeed.id}/historical-hires`, {
        method: 'POST',
        body: payload,
      });
      setSelectedCandidateId(candidate.id);
      formElement.reset();
      return 'Historical hired candidate saved';
    });
  }

  async function submitNeedUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNeed) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      await api<RecruitmentNeed>(`/recruitment-needs/${selectedNeed.id}`, {
        method: 'PUT',
        body: payload,
      });
      return 'Recruitment need updated';
    });
  }

  async function deleteSelectedNeed() {
    if (!selectedNeed) return;
    await mutate(async () => {
      await api(`/recruitment-needs/${selectedNeed.id}`, { method: 'DELETE' });
      return 'Recruitment need deleted';
    });
  }

  async function submitRecruitmentAssets(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNeed) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      await api<RecruitmentNeedDetail>(`/recruitment-needs/${selectedNeed.id}/assets`, {
        method: 'POST',
        body: payload,
      });
      formElement.reset();
      return 'Recruitment assets saved';
    });
  }

  async function submitCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNeed) return;
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    await mutate(async () => {
      const candidate = await api<Candidate>(`/recruitment-needs/${selectedNeed.id}/candidates`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setSelectedCandidateId(candidate.id);
      formElement.reset();
      return 'Candidate added';
    });
  }

  async function updateCandidateStatus(status: string) {
    if (!selectedCandidate) return;
    await mutate(async () => {
      const candidate = await api<Candidate>(`/candidates/${selectedCandidate.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      setSelectedCandidateId(candidate.id);
      return 'Candidate status updated';
    });
  }

  async function submitInterview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCandidate) return;
    const formElement = event.currentTarget;
    const formData = new FormData(formElement);
    const interviewer_emails = ['interviewer_email_1', 'interviewer_email_2', 'interviewer_email_3']
      .map((name) => String(formData.get(name) ?? '').trim())
      .filter(Boolean);
    await mutate(async () => {
      const interviews = await api<Interview[]>(`/candidates/${selectedCandidate.id}/interviews`, {
        method: 'POST',
        body: JSON.stringify({ interviewer_emails }),
      });
      if (interviews[0]) setSelectedInterviewId(interviews[0].id);
      formElement.reset();
      return 'Interview assigned';
    });
  }

  async function submitScorecard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedInterview) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      await api<Interview>(`/interviews/${selectedInterview.id}/scorecard`, {
        method: 'POST',
        body: payload,
      });
      formElement.reset();
      return 'Evaluation checklist uploaded';
    });
  }

  async function submitContract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCandidate) return;
    const formElement = event.currentTarget;
    const payload = new FormData(formElement);
    await mutate(async () => {
      const existingContract = latestContract(selectedCandidate);
      const candidate = await api<Candidate>(existingContract ? `/candidate-contracts/${existingContract.id}` : `/candidates/${selectedCandidate.id}/contract`, {
        method: existingContract ? 'PUT' : 'POST',
        body: payload,
      });
      setSelectedCandidateId(candidate.id);
      formElement.reset();
      return existingContract ? 'Candidate invoice terms updated' : 'Candidate contract and invoice terms saved';
    });
  }

  function editCandidateInvoiceTerms(candidate: Candidate) {
    setSelectedCandidateId(candidate.id);
    if (candidate.recruitment_need_id) setSelectedNeedId(candidate.recruitment_need_id);
  }

  async function submitSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    payload.historical_backfill = scheduleBackfill ? 'true' : 'false';
    await mutate(async () => {
      await api<InvoiceSchedule>(`/projects/${selectedProject.id}/invoice-schedules`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      formElement.reset();
      setScheduleBackfill(false);
      return 'Invoice schedule added';
    });
  }

  async function submitUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    const roles = new FormData(formElement).getAll('roles').map(String);
    await mutate(async () => {
      await api<AppUser>('/users', {
        method: 'POST',
        body: JSON.stringify({
          full_name: payload.full_name,
          email: payload.email,
          is_active: payload.is_active === 'on',
          roles,
        }),
      });
      formElement.reset();
      return 'User saved';
    });
    await refreshUsers();
  }

  async function removeUserRole(user: AppUser, roleToRemove: string) {
    const nextRoles = user.roles.filter((role) => role !== roleToRemove);
    await mutate(async () => {
      await api<AppUser>('/users', {
        method: 'POST',
        body: JSON.stringify({
          full_name: user.full_name,
          email: user.email,
          is_active: user.is_active,
          roles: nextRoles,
        }),
      });
      return `${roleLabel(roleToRemove)} removed from ${user.full_name}`;
    });
    await refreshUsers();
  }

  async function submitInternalProjectClientAccountExecutive(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    const payload = formPayload(event.currentTarget);
    await mutate(async () => {
      const updatedProject = await api<Project>(`/projects/${project.id}/client-account-executive`, {
        method: 'PUT',
        body: JSON.stringify({ client_account_executive_id: Number(payload.client_account_executive_id) }),
      });
      setSelectedProjectId(updatedProject.id);
      return `Assigned Client Account Executive to ${updatedProject.project_code}`;
    });
  }

  async function invoiceAction(path: string, body: Record<string, unknown>, message: string) {
    if (!selectedInvoice) return;
    await mutate(async () => {
      const invoice = await api<ClientInvoice>(`/client-invoices/${selectedInvoice.id}${path}`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setSelectedInvoiceId(invoice.id);
      return message;
    });
  }

  async function approvalInvoiceAction() {
    if (!approvalInvoice) return;
    setLoading(true);
    setNotice(null);
    try {
      const invoice = await api<ClientInvoice>(`/client-invoices/${approvalInvoice.id}/client-account-approval`, {
        method: 'POST',
        body: JSON.stringify({ approver_name: me?.full_name ?? 'Client Account Executive' }),
      });
      setApprovalInvoice(invoice);
      setNotice({ tone: 'ok', message: 'Invoice approved for finance review' });
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Approval failed' });
    } finally {
      setLoading(false);
    }
  }

  async function submitCandidateInvoiceUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidateInvoiceToken) return;
    const formElement = event.currentTarget;
    await mutate(async () => {
      const invoice = await api<CandidateInvoiceUpload>(`/candidate-invoices/upload/${encodeURIComponent(candidateInvoiceToken)}`, {
        method: 'POST',
        body: new FormData(formElement),
      });
      setCandidateInvoiceUpload(invoice);
      return 'Candidate invoice uploaded. The approval request has been sent.';
    });
  }

  async function candidateApprovalInvoiceAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidateApprovalInvoice) return;
    const payload = formPayload(event.currentTarget);
    await mutate(async () => {
      const invoice = await api<CandidateInvoice>(`/candidate-invoices/${candidateApprovalInvoice.id}/client-account-approval`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setCandidateApprovalInvoice(invoice);
      return `Candidate invoice marked ${invoice.status}`;
    });
  }

  async function candidateInvoicePaymentAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCandidateInvoice) return;
    const formElement = event.currentTarget;
    await mutate(async () => {
      const invoice = await api<CandidateInvoice>(`/candidate-invoices/${selectedCandidateInvoice.id}/payments`, {
        method: 'POST',
        body: JSON.stringify(formPayload(formElement)),
      });
      setSelectedCandidateInvoiceId(invoice.id);
      formElement.reset();
      return 'Candidate invoice payment recorded';
    });
  }

  function downloadInvoice() {
    if (!selectedInvoice) return;
    window.open(`${API_BASE}/client-invoices/${selectedInvoice.id}/download`, '_blank', 'noopener,noreferrer');
  }

  function downloadCandidateInvoice(invoiceId: number | undefined) {
    if (!invoiceId) return;
    window.open(`${API_BASE}/candidate-invoices/${invoiceId}/download`, '_blank', 'noopener,noreferrer');
  }

  function downloadDocument(documentId: number | null) {
    if (!documentId) return;
    window.open(`${API_BASE}/documents/${documentId}/download`, '_blank', 'noopener,noreferrer');
  }

  async function submitInvoiceFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInvoicePage(1);
    await refreshData(me, 1);
  }

  async function mutate(work: () => Promise<string>) {
    setLoading(true);
    setNotice(null);
    try {
      const message = await work();
      if (me?.active_role === 'system_admin') await refreshUsers();
      if (me?.active_role) await refreshData(me);
      setNotice({ tone: 'ok', message });
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Action failed' });
    } finally {
      setLoading(false);
    }
  }

  if (candidateInvoiceToken) {
    return (
      <CandidateInvoiceUploadShell
        loading={loading}
        notice={notice}
        invoice={candidateInvoiceUpload}
        onSubmit={(event) => void submitCandidateInvoiceUpload(event)}
      />
    );
  }

  if (me === null) {
    if (approvalInvoiceId) return <ApprovalShell loading={loading} notice={notice} />;
    if (candidateInvoiceId) return <CandidateApprovalShell loading={loading} notice={notice} />;
    return (
      <main>
        <ShellHeader loading={loading} onRefresh={() => void refreshAll()} />
        {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Checking Login</h2>
          <p>Confirming whether a valid Google session is available.</p>
        </section>
      </main>
    );
  }

  if (approvalInvoiceId) {
    return (
      <ApprovalShell
        loading={loading}
        notice={notice}
        me={me}
        approvalInvoiceId={approvalInvoiceId}
        approvalError={approvalError}
        approvalInvoice={approvalInvoice}
        onApprove={() => void approvalInvoiceAction()}
      />
    );
  }

  if (candidateInvoiceId) {
    return (
      <CandidateApprovalShell
        loading={loading}
        notice={notice}
        me={me}
        candidateInvoiceId={candidateInvoiceId}
        candidateInvoiceError={candidateInvoiceError}
        invoice={candidateApprovalInvoice}
        onSubmit={(event) => void candidateApprovalInvoiceAction(event)}
        onDownload={() => downloadCandidateInvoice(candidateApprovalInvoice?.id)}
      />
    );
  }

  if (!me.authenticated) {
    return (
      <main>
        <ShellHeader loading={loading} onRefresh={() => void refreshAll()} />
        {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Login Required</h2>
          <p>Use your FlexGCC Google account. Access is available only after the system admin assigns roles.</p>
          <a className="primary linkButton" href={`${API_BASE}/auth/login`}>Continue with Google</a>
        </section>
      </main>
    );
  }

  if (!me.active_role) {
    return (
      <main>
        <ShellHeader loading={loading} onRefresh={() => void refreshAll()} me={me} onLogout={() => void logout()} />
        {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
        <section className="authGate roleGate">
          <UserCog size={42} />
          <h2>Choose Role</h2>
          <p>{me.email}</p>
          <div className="roleChoices">
            {me.roles.map((role) => (
              <button key={role} className="primary" onClick={() => void chooseRole(role)} disabled={loading}>
                {roleLabel(role)}
              </button>
            ))}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main>
      <ShellHeader loading={loading} onRefresh={() => void refreshAll()} me={me} onLogout={() => void logout()} onRoleChange={() => setMe({ ...me, active_role: null })} />

      {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}

      {me.active_role && (
        <nav className="viewSwitch">
          <button className={activeView === 'workflow' ? 'primary' : 'secondary'} onClick={() => setActiveView('workflow')}>Workflow</button>
          {canRecruitment && <button className={activeView === 'recruitment' ? 'primary' : 'secondary'} onClick={() => setActiveView('recruitment')}>Recruitment</button>}
          <button className={activeView === 'invoices' ? 'primary' : 'secondary'} onClick={() => setActiveView('invoices')}>All Invoices</button>
        </nav>
      )}

      {canAdmin && activeView === 'workflow' && (
        <section className="workspace adminWorkspace">
          <form className="panel" onSubmit={(event) => void submitUser(event)}>
            <PanelTitle icon={<UserCog size={18} />} title="App Users" />
            <Field label="Full name" name="full_name" required />
            <Field label="Google email" name="email" type="email" required />
            <label className="checkField">
              <input name="is_active" type="checkbox" defaultChecked />
              <span>Active user</span>
            </label>
            <div className="roleGrid">
              {ALL_ROLES.map((role) => (
                <label key={role} className="checkField">
                  <input name="roles" value={role} type="checkbox" />
                  <span>{roleLabel(role)}</span>
                </label>
              ))}
            </div>
            <button className="primary" disabled={loading}>
              <BadgeCheck size={18} />
              <span>Save User</span>
            </button>
          </form>

          <section className="panel wide">
            <PanelTitle icon={<UserCheck size={18} />} title="FlexGCC Sales Support Client Account Executive" />
            {flexGccSalesSupportProjects.length > 0 ? (
              <div className="userList">
                {flexGccSalesSupportProjects.map((project) => (
                  <form className="userRow" key={project.id} onSubmit={(event) => void submitInternalProjectClientAccountExecutive(event, project)}>
                    <div>
                      <strong>{project.project_code} · {project.title}</strong>
                      <span>Current: {project.client_account_executive_name ?? 'Not assigned'}</span>
                    </div>
                    <div className="horizontalActions">
                      <select name="client_account_executive_id" required defaultValue={project.client_account_executive_id ?? ''}>
                        <option value="" disabled>Select Client Account Executive</option>
                        {clientAccountExecutives.map((user) => (
                          <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>
                        ))}
                      </select>
                      <button className="primary" disabled={loading || clientAccountExecutives.length === 0}>
                        <BadgeCheck size={18} />
                        <span>Assign</span>
                      </button>
                    </div>
                  </form>
                ))}
              </div>
            ) : (
              <p className="empty">No FlexGCC sales support project exists yet.</p>
            )}
          </section>

          <section className="panel wide">
            <PanelTitle icon={<ShieldCheck size={18} />} title="Provisioned Users" />
            <div className="userList">
              {users.map((user) => (
                <div className="userRow" key={user.id}>
                  <div>
                    <strong>{user.full_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <div className="rolePills">
                    {user.roles.map((role) => (
                      <span className="rolePill" key={role}>
                        <span>{roleLabel(role)}</span>
                        <button type="button" onClick={() => void removeUserRole(user, role)} disabled={loading} aria-label={`Remove ${roleLabel(role)} from ${user.full_name}`}>
                          Remove
                        </button>
                      </span>
                    ))}
                    {user.roles.length === 0 && <span className="status">no roles</span>}
                    {!user.is_active && <span className="status cancelled">inactive</span>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </section>
      )}

      {activeView === 'recruitment' && canRecruitment && (
        <section className="workspace recruitmentWorkspace">
          {canOperate && (
            <form className="panel wide" onSubmit={(event) => void submitNeed(event)}>
              <PanelTitle icon={<FilePlus2 size={18} />} title="Add Recruitment Position" />
              <label className="field">
                <span>SOW</span>
                <select name="project_id" required value={selectedProject?.id ?? ''} onChange={(event) => setSelectedProjectId(Number(event.target.value))}>
                  <option value="" disabled>Select SOW</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.project_code} · {project.client_company_name} · {project.title}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid four">
                <Field label="Position" name="position_title" required />
                <Field label="Number" name="number_of_positions" type="number" defaultValue="1" required />
                <label className="field">
                  <span>Type</span>
                  <select name="employment_type" defaultValue="FTE">
                    <option>FE</option>
                    <option>FTE</option>
                    <option>Fractional Consultant</option>
                  </select>
                </label>
                <label className="field">
                  <span>Billing type</span>
                  <select name="position_billing_type" value={needBillingType} onChange={(event) => setNeedBillingType(event.target.value)}>
                    <option value="fixed_fee">Fixed fee</option>
                    <option value="periodic">Periodic</option>
                  </select>
                </label>
                <Field label="Fee amount" name="fee_amount" type="number" step="0.01" />
                <Field label="Currency" name="currency" defaultValue={selectedProject?.currency ?? 'USD'} />
                <label className="field">
                  <span>Billing frequency</span>
                  <select name="billing_frequency" defaultValue={needBillingType === 'fixed_fee' ? 'single' : 'monthly'}>
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                <Field label={needBillingType === 'fixed_fee' ? 'Billing date' : 'Billing start'} name="billing_start_date" type="date" />
                {needBillingType !== 'fixed_fee' && <Field label="Billing end" name="billing_end_date" type="date" />}
                <Field label="Target start" name="target_start_date" type="date" />
                <Field label="Internal interviewers" name="internal_interviewers" placeholder="Names separated by semicolons" />
                <Field label="Detailed position upload" name="detail_document" type="file" />
              </div>
              <label className="field full">
                <span>Description</span>
                <textarea name="description" rows={4} required minLength={5} />
              </label>
              <label className="checkField">
                <input name="historical_completed" type="checkbox" />
                <span>Historical completed recruitment - mark closed and do not notify HR</span>
              </label>
              <button className="primary" disabled={projects.length === 0 || loading}>
                <BadgeCheck size={18} />
                <span>Add Position</span>
              </button>
            </form>
          )}

          <section className="panel wide">
            <PanelTitle icon={<ClipboardList size={18} />} title="Recruitment Positions" />
            <label className="field">
              <span>Position</span>
              <select value={selectedNeed?.id ?? ''} onChange={(event) => setSelectedNeedId(Number(event.target.value))}>
                {recruitmentNeeds.map((need) => (
                  <option key={need.id} value={need.id}>
                    {need.project_code} · {need.position_title} · {need.status}
                  </option>
                ))}
              </select>
            </label>
            {selectedNeed ? (
              <>
                <dl className="facts">
                  <div><dt>Client</dt><dd>{selectedNeed.client_company_name}</dd></div>
                  <div><dt>SOW</dt><dd>{selectedNeed.project_title}</dd></div>
                  <div><dt>Position</dt><dd>{selectedNeed.position_title}</dd></div>
                  <div><dt>Openings</dt><dd>{selectedNeed.number_of_positions}</dd></div>
                  <div><dt>Type</dt><dd>{selectedNeed.employment_type}</dd></div>
                  <div><dt>Status</dt><dd><Status value={selectedNeed.status} /></dd></div>
                  <div><dt>Fee</dt><dd>{selectedNeed.currency ?? 'USD'} {selectedNeed.fee_amount ?? '0.00'}</dd></div>
                  <div><dt>Billing</dt><dd>{selectedNeed.position_billing_type ?? 'not set'} · {selectedNeed.billing_frequency ?? 'not set'}</dd></div>
                </dl>
                <div className="documentList">
                  {selectedNeed.detail_document_name && <span className="status">Position: {selectedNeed.detail_document_name}</span>}
                  {selectedNeed.jd_document_name && <span className="status">JD: {selectedNeed.jd_document_name}</span>}
                  {selectedNeed.job_ad_document_name && <span className="status">Ad: {selectedNeed.job_ad_document_name}</span>}
                  {selectedNeed.linkedin_ad_url && <a className="status" href={selectedNeed.linkedin_ad_url} target="_blank" rel="noreferrer">LinkedIn ad</a>}
                </div>
              </>
            ) : (
              <p className="empty">No recruitment positions yet.</p>
            )}
          </section>

          {canOperate && selectedNeed && (
            <form className="panel wide" key={selectedNeed.id} onSubmit={(event) => void submitNeedUpdate(event)}>
              <PanelTitle icon={<Pencil size={18} />} title="Edit Selected Position" />
              <div className="grid four">
                <Field label="Position" name="position_title" defaultValue={selectedNeed.position_title} />
                <Field label="Number" name="number_of_positions" type="number" defaultValue={selectedNeed.number_of_positions} />
                <label className="field">
                  <span>Type</span>
                  <select name="employment_type" defaultValue={selectedNeed.employment_type}>
                    <option>FE</option>
                    <option>FTE</option>
                    <option>Fractional Consultant</option>
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select name="status" defaultValue={selectedNeed.status}>
                    <option value="open">Open</option>
                    <option value="sourcing">Sourcing</option>
                    <option value="closed">Closed</option>
                    <option value="deleted">Deleted</option>
                  </select>
                </label>
                <label className="field">
                  <span>Billing type</span>
                  <select name="position_billing_type" defaultValue={selectedNeed.position_billing_type ?? 'periodic'}>
                    <option value="fixed_fee">Fixed fee</option>
                    <option value="periodic">Periodic</option>
                  </select>
                </label>
                <Field label="Fee amount" name="fee_amount" type="number" step="0.01" defaultValue={selectedNeed.fee_amount ?? ''} />
                <Field label="Currency" name="currency" defaultValue={selectedNeed.currency ?? 'USD'} />
                <label className="field">
                  <span>Billing frequency</span>
                  <select name="billing_frequency" defaultValue={selectedNeed.billing_frequency ?? 'monthly'}>
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                <Field label="Billing start" name="billing_start_date" type="date" defaultValue={selectedNeed.billing_start_date ?? ''} />
                <Field label="Billing end" name="billing_end_date" type="date" defaultValue={selectedNeed.billing_end_date ?? ''} />
                <Field label="Target start" name="target_start_date" type="date" defaultValue={selectedNeed.target_start_date ?? ''} />
                <Field label="Detail upload" name="detail_document" type="file" />
              </div>
              <Field label="Internal interviewers" name="internal_interviewers" defaultValue={selectedNeed.internal_interviewers ?? ''} />
              <label className="field">
                <span>Description</span>
                <textarea name="description" rows={4} defaultValue={selectedNeed.description} minLength={5} />
              </label>
              <div className="toolbar">
                <button className="primary" disabled={loading}>
                  <FileCheck2 size={18} />
                  <span>Save Position</span>
                </button>
                <button className="secondary danger" type="button" disabled={loading} onClick={() => void deleteSelectedNeed()}>
                  <span>Delete Position</span>
                </button>
              </div>
            </form>
          )}

          {(canHrManage || canOperate) && selectedNeed && (
            <form className="panel" onSubmit={(event) => void submitHistoricalHire(event)}>
              <PanelTitle icon={<BadgeCheck size={18} />} title="Historical Hired Candidate" />
              <p className="contextLine">{selectedNeed.project_code} · {selectedNeed.position_title}</p>
              <Field label="Candidate name" name="full_name" required />
              <Field label="Candidate email" name="email" type="email" required />
              <Field label="Phone" name="phone" />
              <Field label="LinkedIn profile URL" name="linkedin_profile_url" />
              <label className="field">
                <span>Notes</span>
                <textarea name="notes" rows={3} />
              </label>
              <Field label="Signed contract upload" name="signed_contract" type="file" />
              <Field label="Next candidate invoice amount" name="invoice_amount" type="number" step="0.01" />
              <Field label="Currency" name="currency" defaultValue="USD" />
              <label className="field">
                <span>Invoice frequency</span>
                <select name="invoice_frequency" value={contractInvoiceFrequency} onChange={(event) => setContractInvoiceFrequency(event.target.value)}>
                  <option value="single">Single</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                </select>
              </label>
              {contractInvoiceFrequency === 'single' ? (
                <Field label="Next candidate invoice date" name="invoice_date" type="date" defaultValue={endOfCurrentMonth()} />
              ) : (
                <>
                  <Field label="Next candidate invoice reminder date" name="invoice_start_date" type="date" defaultValue={endOfCurrentMonth()} />
                  <Field label="Reminder end date" name="invoice_end_date" type="date" />
                </>
              )}
              <label className="field">
                <span>Invoice terms</span>
                <textarea name="invoice_terms" rows={3} />
              </label>
              <button className="secondary" disabled={loading}>
                <FileCheck2 size={18} />
                <span>Save Historical Hire</span>
              </button>
            </form>
          )}

          {canHrManage && (
            <>
              <form className="panel" onSubmit={(event) => void submitRecruitmentAssets(event)}>
                <PanelTitle icon={<Upload size={18} />} title="JD And Job Ad" />
                <p className="contextLine">{selectedNeed ? `${selectedNeed.project_code} · ${selectedNeed.position_title}` : 'Select a position first'}</p>
                <Field label="JD upload" name="jd_document" type="file" />
                <Field label="Job ad upload" name="job_ad_document" type="file" />
                <Field label="LinkedIn ad URL" name="linkedin_ad_url" defaultValue={selectedNeed?.linkedin_ad_url ?? ''} />
                <button className="secondary" disabled={!selectedNeed || loading}>
                  <FileText size={18} />
                  <span>Save Assets</span>
                </button>
              </form>

              <form className="panel" onSubmit={(event) => void submitCandidate(event)}>
                <PanelTitle icon={<Users size={18} />} title="Evaluation Shortlist" />
                <p className="contextLine">{selectedNeed ? selectedNeed.position_title : 'Select a position first'}</p>
                <Field label="Candidate name" name="full_name" required />
                <Field label="Candidate email" name="email" type="email" required />
                <Field label="Phone" name="phone" />
                <Field label="LinkedIn profile URL" name="linkedin_profile_url" />
                <label className="field">
                  <span>Notes</span>
                  <textarea name="notes" rows={3} />
                </label>
                <button className="secondary" disabled={!selectedNeed || loading}>
                  <UserCheck size={18} />
                  <span>Add Candidate</span>
                </button>
              </form>

              <section className="panel wide">
                <PanelTitle icon={<Users size={18} />} title="Candidate Status" />
                <label className="field">
                  <span>Candidate</span>
                  <select value={selectedCandidate?.id ?? ''} onChange={(event) => setSelectedCandidateId(Number(event.target.value))}>
                    {candidatesForNeed.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>{candidate.full_name} · {candidate.status}</option>
                    ))}
                  </select>
                </label>
                {selectedCandidate ? (
                  <>
                    <dl className="facts">
                      <div><dt>Name</dt><dd>{selectedCandidate.full_name}</dd></div>
                      <div><dt>Email</dt><dd>{selectedCandidate.email}</dd></div>
                      <div><dt>Position</dt><dd>{selectedCandidate.position_title}</dd></div>
                      <div><dt>Status</dt><dd><Status value={selectedCandidate.status} /></dd></div>
                    </dl>
                    <div className="actions horizontalActions">
                      <button className="secondary" onClick={() => void updateCandidateStatus('shortlisted_for_interview')} disabled={loading}>Shortlist</button>
                      <button className="secondary" onClick={() => void updateCandidateStatus('backup_candidate')} disabled={loading}>Back-up</button>
                      <button className="secondary danger" onClick={() => void updateCandidateStatus('rejected')} disabled={loading}>Reject</button>
                      <button className="secondary" onClick={() => void updateCandidateStatus('send_contract')} disabled={loading}>Send Contract</button>
                    </div>
                  </>
                ) : (
                  <p className="empty">No candidates for the selected position.</p>
                )}
              </section>

              <form className="panel" onSubmit={(event) => void submitInterview(event)}>
                <PanelTitle icon={<CalendarPlus size={18} />} title="Interview Assignment" />
                <p className="contextLine">{selectedCandidate ? selectedCandidate.full_name : 'Select a candidate first'}</p>
                <Field label="Internal interviewer email 1" name="interviewer_email_1" type="email" list="internal-interviewer-emails" required />
                <Field label="Internal interviewer email 2" name="interviewer_email_2" type="email" list="internal-interviewer-emails" />
                <Field label="Internal interviewer email 3" name="interviewer_email_3" type="email" list="internal-interviewer-emails" />
                <datalist id="internal-interviewer-emails">
                  {internalInterviewers.map((user) => (
                    <option key={user.id} value={user.email}>{user.full_name}</option>
                  ))}
                </datalist>
                <button className="secondary" disabled={!selectedCandidate || loading}>
                  <CalendarPlus size={18} />
                  <span>Assign Interview</span>
                </button>
              </form>

              <section className="panel wide">
                <PanelTitle icon={<BadgeCheck size={18} />} title="Hired Candidates" />
                {hiredCandidates.length > 0 ? (
                  <div className="grid two">
                    {hiredCandidates.map((candidate) => {
                      const contract = latestContract(candidate);
                      return (
                        <div className="candidateBlock" key={candidate.id}>
                          <h2>{candidate.full_name}</h2>
                          <dl className="facts">
                            <div><dt>Email</dt><dd>{candidate.email}</dd></div>
                            <div><dt>Phone</dt><dd>{candidate.phone ?? 'Not set'}</dd></div>
                            <div><dt>Client</dt><dd>{candidate.client_company_name}</dd></div>
                            <div><dt>SOW</dt><dd>{candidate.project_code} · {candidate.project_title}</dd></div>
                            <div><dt>Position</dt><dd>{candidate.position_title ?? 'Not set'}</dd></div>
                            <div><dt>Invoice</dt><dd>{contractInvoiceSummary(contract)}</dd></div>
                            <div><dt>Invoice dates</dt><dd>{contractInvoiceDates(contract)}</dd></div>
                            <div><dt>Contract</dt><dd>{contract?.contract_document_name ?? 'Not uploaded'}</dd></div>
                          </dl>
                          {contract?.contract_document_id && (
                            <button className="secondary" type="button" onClick={() => downloadDocument(contract.contract_document_id)}>
                              <Download size={18} />
                              <span>Download Contract</span>
                            </button>
                          )}
                          <button className="primary" type="button" onClick={() => editCandidateInvoiceTerms(candidate)}>
                            <Pencil size={18} />
                            <span>Edit Invoice Terms</span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="empty">No hired candidates yet.</p>
                )}
              </section>

              <form className="panel" key={`${selectedCandidate?.id ?? 'none'}-${selectedCandidateContract?.id ?? 'new'}`} onSubmit={(event) => void submitContract(event)}>
                <PanelTitle icon={<FileCheck2 size={18} />} title={selectedCandidateContract ? 'Edit Candidate Invoice Terms' : 'Signed Contract And Invoice Terms'} />
                <p className="contextLine">{selectedCandidate ? selectedCandidate.full_name : 'Select a candidate first'}</p>
                <Field label="Signed contract upload" name="signed_contract" type="file" />
                <Field label="Invoice amount" name="invoice_amount" type="number" step="0.01" defaultValue={selectedCandidateContract?.invoice_amount ?? ''} />
                <Field label="Currency" name="currency" defaultValue={selectedCandidateContract?.currency ?? 'USD'} />
                <label className="field">
                  <span>Invoice frequency</span>
                  <select name="invoice_frequency" value={contractInvoiceFrequency} onChange={(event) => setContractInvoiceFrequency(event.target.value)}>
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                {contractInvoiceFrequency === 'single' ? (
                  <Field label="Invoice date" name="invoice_date" type="date" defaultValue={selectedCandidateContract?.invoice_date ?? ''} />
                ) : (
                  <>
                    <Field label="Invoice start" name="invoice_start_date" type="date" defaultValue={selectedCandidateContract?.invoice_start_date ?? ''} />
                    <Field label="Invoice end" name="invoice_end_date" type="date" defaultValue={selectedCandidateContract?.invoice_end_date ?? ''} />
                  </>
                )}
                {selectedCandidateContract && (
                  <label className="field">
                    <span>Contract status</span>
                    <select name="status" defaultValue={selectedCandidateContract.status}>
                      <option value="signed">Signed</option>
                      <option value="terminated">Terminated</option>
                      <option value="inactive">Inactive</option>
                      <option value="draft">Draft</option>
                    </select>
                  </label>
                )}
                <label className="field">
                  <span>Invoice terms</span>
                  <textarea name="invoice_terms" rows={3} defaultValue={selectedCandidateContract?.invoice_terms ?? ''} />
                </label>
                <button className="primary" disabled={!selectedCandidate || loading}>
                  <BadgeCheck size={18} />
                  <span>{selectedCandidateContract ? 'Update Terms' : 'Mark Hired'}</span>
                </button>
              </form>
            </>
          )}

          {(canInterview || canHrManage) && (
            <section className="panel wide">
              <PanelTitle icon={<UserCheck size={18} />} title={canInterview ? 'My Interview Evaluations' : 'Interview Evaluations'} />
              <label className="field">
                <span>Interview</span>
                <select value={selectedInterview?.id ?? ''} onChange={(event) => setSelectedInterviewId(Number(event.target.value))}>
                  {interviews.map((interview) => {
                    const candidate = candidates.find((item) => item.id === interview.candidate_id);
                    return <option key={interview.id} value={interview.id}>{candidate?.full_name ?? `Candidate ${interview.candidate_id}`} · {interview.interviewer_name} · {interview.status}</option>;
                  })}
                </select>
              </label>
              {selectedInterview ? (
                <dl className="facts">
                  <div><dt>Interviewer</dt><dd>{selectedInterview.interviewer_name}</dd></div>
                  <div><dt>Status</dt><dd><Status value={selectedInterview.status} /></dd></div>
                  <div><dt>Score</dt><dd>{selectedInterview.score ?? 'Not submitted'}</dd></div>
                  <div><dt>Recommendation</dt><dd>{selectedInterview.recommendation ?? 'Not submitted'}</dd></div>
                  <div>
                    <dt>Checklist</dt>
                    <dd>
                      {selectedInterview.evaluation_document_id ? (
                        <button className="secondary" type="button" onClick={() => downloadDocument(selectedInterview.evaluation_document_id)}>
                          <Download size={18} />
                          <span>{selectedInterview.evaluation_document_name ?? 'Download checklist'}</span>
                        </button>
                      ) : (
                        'Not uploaded'
                      )}
                    </dd>
                  </div>
                  <div><dt>Calendly</dt><dd>{selectedInterview.calendly_url ?? 'Not set'}</dd></div>
                </dl>
              ) : (
                <p className="empty">No interviews yet.</p>
              )}
            </section>
          )}

          {canInterview && (
            <form className="panel" onSubmit={(event) => void submitScorecard(event)}>
              <PanelTitle icon={<Upload size={18} />} title="Upload Evaluation Checklist" />
              <p className="contextLine">{selectedInterview ? `Interview ${selectedInterview.id}` : 'Select an interview first'}</p>
              <Field label="Checklist upload" name="evaluation_checklist" type="file" />
              <Field label="Score" name="score" type="number" min="0" max="100" required />
              <label className="field">
                <span>Recommendation</span>
                <select name="recommendation" required defaultValue="advance">
                  <option value="advance">Advance</option>
                  <option value="backup">Back-up</option>
                  <option value="reject">Reject</option>
                  <option value="hire">Hire</option>
                </select>
              </label>
              <label className="field">
                <span>Notes</span>
                <textarea name="notes" rows={4} />
              </label>
              <button className="primary" disabled={!selectedInterview || loading}>
                <FileCheck2 size={18} />
                <span>Submit Evaluation</span>
              </button>
            </form>
          )}
        </section>
      )}

      {activeView === 'invoices' && me.active_role && (
        <section className="workspace invoiceWorkspace">
          <form className="panel wide" onSubmit={(event) => void submitInvoiceFilters(event)}>
            <PanelTitle icon={<FileCheck2 size={18} />} title="All Invoices" />
            <div className="grid four">
              <label className="field">
                <span>Status</span>
                <select value={invoiceStatusFilter} onChange={(event) => setInvoiceStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  <option value={UPCOMING_INVOICES_FILTER}>Upcoming invoices</option>
                  {INVOICE_STATUSES.map((status) => (
                    <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>
                  ))}
                </select>
              </label>
              <Field label="From invoice date" name="date_from" type="date" value={invoiceDateFrom} onChange={(event) => setInvoiceDateFrom(event.currentTarget.value)} />
              <Field label="To invoice date" name="date_to" type="date" value={invoiceDateTo} onChange={(event) => setInvoiceDateTo(event.currentTarget.value)} />
              <button className="primary" disabled={loading}>
                <RefreshCw size={18} />
                <span>Apply</span>
              </button>
            </div>
            <div className="toolbar">
              <button className="secondary" type="button" disabled={invoicePage <= 1 || loading} onClick={() => setInvoicePage((page) => Math.max(1, page - 1))}>Previous</button>
              <span className="status">Page {invoicePage}</span>
              <button className="secondary" type="button" disabled={invoiceListCount < invoicePageSize || loading} onClick={() => setInvoicePage((page) => page + 1)}>Next</button>
            </div>
          </form>

          <section className="panel wide">
            {showingUpcomingInvoices ? (
              <>
                <PanelTitle icon={<CalendarPlus size={18} />} title="Upcoming Invoice Schedule" />
                {upcomingInvoices.length > 0 ? (
                  <div className="userList">
                    {upcomingInvoices.map((invoice) => (
                      <div className="userRow" key={invoice.schedule_id}>
                        <div>
                          <strong>{invoice.next_invoice_date} · {invoice.currency} {invoice.amount}</strong>
                          <span>{invoice.project_code} · {invoice.client_company_name} · {invoice.project_title}</span>
                          <span>{invoice.item_description ?? invoice.label}</span>
                        </div>
                        <div className="rolePills">
                          <span className="status">{invoice.frequency.replaceAll('_', ' ')}</span>
                          {invoice.final_invoice_date && <span className="status">Until {invoice.final_invoice_date}</span>}
                          {invoice.client_account_executive_email && <span className="status">{invoice.client_account_executive_email}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty">No upcoming scheduled invoices match the filters.</p>
                )}
              </>
            ) : (
              <>
                <PanelTitle icon={<FileCheck2 size={18} />} title="Invoice Register" />
                <select value={selectedInvoice?.id ?? ''} onChange={(event) => setSelectedInvoiceId(Number(event.target.value))}>
                  {invoices.map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      {invoice.issue_date} · {invoice.invoice_number} · {invoice.status}
                    </option>
                  ))}
                </select>
                <InvoiceDetail
                  selectedInvoice={selectedInvoice}
                  loading={loading}
                  canClientApprove={canClientApprove}
                  canFinance={canFinance}
                  downloadInvoice={downloadInvoice}
                  invoiceAction={invoiceAction}
                  currentUserName={me.full_name}
                />
              </>
            )}
          </section>

          <section className="panel wide">
            <PanelTitle icon={<Banknote size={18} />} title="Candidate Invoices" />
            {candidateInvoices.length > 0 ? (
              <>
                <select value={selectedCandidateInvoice?.id ?? ''} onChange={(event) => setSelectedCandidateInvoiceId(Number(event.target.value))}>
                  {candidateInvoices.map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      {invoice.invoice_due_date ?? invoice.submitted_at.slice(0, 10)} · {invoice.candidate_name} · {invoice.status}
                    </option>
                  ))}
                </select>
                {selectedCandidateInvoice && (
                  <div className="invoiceGrid">
                    <dl className="facts">
                      <div><dt>Candidate</dt><dd>{selectedCandidateInvoice.candidate_name}</dd></div>
                      <div><dt>Client</dt><dd>{selectedCandidateInvoice.client_company_name}</dd></div>
                      <div><dt>SOW</dt><dd>{selectedCandidateInvoice.project_code} · {selectedCandidateInvoice.project_title}</dd></div>
                      <div><dt>Position</dt><dd>{selectedCandidateInvoice.position_title ?? 'Not set'}</dd></div>
                      <div><dt>Invoice due date</dt><dd>{selectedCandidateInvoice.invoice_due_date ?? 'Not set'}</dd></div>
                      <div><dt>Amount</dt><dd>{selectedCandidateInvoice.currency} {selectedCandidateInvoice.amount}</dd></div>
                      <div><dt>Status</dt><dd><Status value={selectedCandidateInvoice.status} /></dd></div>
                      <div><dt>Paid</dt><dd>{selectedCandidateInvoice.currency} {selectedCandidateInvoice.paid_total}</dd></div>
                      <div><dt>Balance</dt><dd>{selectedCandidateInvoice.currency} {selectedCandidateInvoice.balance_due}</dd></div>
                      <div><dt>CAE comments</dt><dd>{selectedCandidateInvoice.approval_comments ?? 'None'}</dd></div>
                    </dl>
                    <div className="actions">
                      <button className="secondary" type="button" onClick={() => downloadCandidateInvoice(selectedCandidateInvoice.id)} disabled={!selectedCandidateInvoice.invoice_document_id}>
                        <Download size={18} />
                        <span>Download Invoice</span>
                      </button>
                    </div>
                  </div>
                )}
                {canFinance && selectedCandidateInvoice && (
                  <form className="grid four" onSubmit={(event) => void candidateInvoicePaymentAction(event)}>
                    <Field label="Amount paid" name="amount_paid" type="number" step="0.01" required />
                    <Field label="Paid date" name="paid_date" type="date" defaultValue={today()} required />
                    <Field label="Bank reference" name="bank_reference" />
                    <label className="field">
                      <span>Status</span>
                      <select name="status" defaultValue="">
                        <option value="">Calculate from paid amount</option>
                        <option value="paid">Paid</option>
                        <option value="partially_paid">Partially paid</option>
                      </select>
                    </label>
                    <input type="hidden" name="recorded_by_name" value={me.full_name ?? 'Finance Manager'} />
                    <button className="primary" disabled={loading || !['approved', 'partially_paid', 'paid'].includes(selectedCandidateInvoice.status)}>
                      <Banknote size={18} />
                      <span>Record Payment</span>
                    </button>
                  </form>
                )}
              </>
            ) : (
              <p className="empty">No candidate invoices have been submitted yet.</p>
            )}
          </section>
        </section>
      )}

      {activeView === 'workflow' && canViewWorkflow && (
        <section className="workspace">
          {canOperate && (
            <form className="panel wide" key={internalRecruitmentProject ? 'internal-project' : 'client-project'} onSubmit={(event) => void submitProject(event)}>
              <PanelTitle icon={<FilePlus2 size={18} />} title="Project And Initial SOW Entry" />
              <label className="checkField">
                <input
                  checked={internalRecruitmentProject}
                  onChange={(event) => setInternalRecruitmentProject(event.target.checked)}
                  type="checkbox"
                />
                <span>Internal FlexGCC sales support recruitment - no MSA or SOW</span>
              </label>
              {internalRecruitmentProject && (
                <p className="contextLine">
                  Creates an internal project named FlexGCC sales support. After creation, use Recruitment to add historical completed positions and hired candidates.
                </p>
              )}
              <div className="grid two">
                <Field label="Client company" name="client_company_name" defaultValue={internalRecruitmentProject ? 'FlexGCC' : ''} disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <label className="field">
                  <span>Client billing address</span>
                  <textarea name="client_billing_address" rows={3} disabled={internalRecruitmentProject} />
                </label>
                <Field label="Client contact name" name="client_contact_name" defaultValue={internalRecruitmentProject ? 'FlexGCC Sales Support' : ''} disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <Field label="Client contact email" name="client_contact_email" type="email" defaultValue={internalRecruitmentProject ? 'finance@flexGCC.com' : ''} disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <Field label="Client contact phone" name="client_contact_phone" disabled={internalRecruitmentProject} />
                <label className="field">
                  <span>Client Account Executive</span>
                  <select name="client_account_executive_id" required={!internalRecruitmentProject} disabled={internalRecruitmentProject} defaultValue="">
                    <option value="" disabled>Select Client Account Executive</option>
                    {clientAccountExecutives.map((user) => (
                      <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>
                    ))}
                  </select>
                </label>
                <Field label="MSA reference" name="msa_reference" disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <Field label="MSA upload" name="msa_document" type="file" disabled={internalRecruitmentProject} />
                <Field label="SOW title" name="sow_title" defaultValue={internalRecruitmentProject ? 'FlexGCC sales support' : ''} disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <Field label="SOW upload" name="sow_document" type="file" disabled={internalRecruitmentProject} />
                <Field label="SOW amount" name="sow_amount" type="number" step="0.01" defaultValue={internalRecruitmentProject ? '0' : '12000'} disabled={internalRecruitmentProject} required={!internalRecruitmentProject} />
                <Field label="Currency" name="currency" defaultValue="USD" required />
                <Field label="Start date" name="start_date" type="date" defaultValue={today()} required />
                <Field label="End date" name="end_date" type="date" />
                <Field label="Operations manager" name="operations_manager_name" defaultValue={me.full_name ?? 'Operations Manager'} required />
              </div>
              <label className="field full">
                <span>SOW description</span>
                <textarea name="sow_description" rows={3} />
              </label>
              <button className="primary" disabled={loading}>
                <FileCheck2 size={18} />
                <span>Create Project</span>
              </button>
            </form>
          )}

          <section className="panel">
            <PanelTitle icon={<ClipboardList size={18} />} title="Project And SOW Register" />
            <select value={selectedProject?.id ?? ''} onChange={(event) => setSelectedProjectId(Number(event.target.value))}>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.project_code} · {project.client_company_name} · {project.title}
                </option>
              ))}
            </select>
            {selectedProject && editingProject ? (
              <form className="editStack" key={selectedProject.id} onSubmit={(event) => void submitProjectUpdate(event)}>
                <PanelTitle icon={<Pencil size={18} />} title="Edit Project Details" />
                <div className="grid two">
                  <Field label="Client company" name="client_company_name" defaultValue={selectedProject.client_company_name} />
                  <Field label="Client contact name" name="client_contact_name" defaultValue={selectedProject.client_contact_name} />
                  <label className="field">
                    <span>Client billing address</span>
                    <textarea name="client_billing_address" rows={3} defaultValue={selectedProject.client_billing_address ?? ''} />
                  </label>
                  <Field label="Client contact email" name="client_contact_email" type="email" defaultValue={selectedProject.client_contact_email} />
                  <Field label="Client contact phone" name="client_contact_phone" defaultValue={selectedProject.client_contact_phone ?? ''} />
                  <label className="field">
                    <span>Client Account Executive</span>
                    <select name="client_account_executive_id" defaultValue={selectedProject.client_account_executive_id ?? ''}>
                      <option value="" disabled>Select Client Account Executive</option>
                      {clientAccountExecutives.map((user) => (
                        <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>
                      ))}
                    </select>
                  </label>
                  <Field label="MSA reference" name="msa_reference" defaultValue={selectedProject.msa_reference ?? ''} />
                  <Field label="MSA upload" name="msa_document" type="file" />
                  <Field label="SOW title" name="sow_title" defaultValue={selectedProject.title} />
                  <Field label="SOW upload" name="sow_document" type="file" />
                  <Field label="SOW amount" name="sow_amount" type="number" step="0.01" defaultValue={selectedProject.sow_amount} />
                  <Field label="Currency" name="currency" defaultValue={selectedProject.currency} />
                  <Field label="Start date" name="start_date" type="date" defaultValue={selectedProject.start_date} />
                  <Field label="End date" name="end_date" type="date" defaultValue={selectedProject.end_date ?? ''} />
                  <Field label="Operations manager" name="operations_manager_name" defaultValue={selectedProject.operations_manager_name} />
                </div>
                <label className="field full">
                  <span>SOW description</span>
                  <textarea name="sow_description" rows={3} defaultValue={selectedProject.description ?? ''} />
                </label>
                <div className="toolbar">
                  <button className="primary" disabled={loading}>
                    <FileCheck2 size={18} />
                    <span>Save Changes</span>
                  </button>
                  <button className="secondary" type="button" onClick={() => setEditingProject(false)} disabled={loading}>
                    <span>Cancel</span>
                  </button>
                </div>
              </form>
            ) : selectedProject ? (
              <>
                <dl className="facts">
                  <div><dt>SOW</dt><dd>{selectedProject.title}</dd></div>
                  <div><dt>Client</dt><dd>{selectedProject.client_company_name}</dd></div>
                  <div><dt>Billing address</dt><dd>{selectedProject.client_billing_address ?? 'Not entered'}</dd></div>
                  <div><dt>Contact name</dt><dd>{selectedProject.client_contact_name}</dd></div>
                  <div><dt>Contact email</dt><dd>{selectedProject.client_contact_email}</dd></div>
                  <div><dt>Contact phone</dt><dd>{selectedProject.client_contact_phone ?? 'Not entered'}</dd></div>
                  <div><dt>MSA</dt><dd>{selectedProject.msa_reference}</dd></div>
                  <div><dt>Value</dt><dd>{selectedProject.currency} {selectedProject.sow_amount}</dd></div>
                  <div><dt>Client Account Executive</dt><dd>{selectedProject.client_account_executive_name ?? 'Not assigned'}</dd></div>
                  <div><dt>Needs</dt><dd>{selectedProject.recruitment_needs.length}</dd></div>
                  <div><dt>Schedules</dt><dd>{selectedProject.invoice_schedules.length}</dd></div>
                </dl>
                {selectedProject.documents.length > 0 && (
                  <div className="documentList">
                    {selectedProject.documents.map((document) => (
                      <span className="status" key={document.id}>{document.document_type.toUpperCase()}: {document.original_filename}</span>
                    ))}
                  </div>
                )}
                {canOperate && (
                  <button className="secondary" type="button" onClick={() => setEditingProject(true)}>
                    <Pencil size={18} />
                    <span>Edit Project Details</span>
                  </button>
                )}
              </>
            ) : (
              <p className="empty">No projects yet.</p>
            )}
          </section>

          {canOperate && (
            <>
              <form className="panel" onSubmit={(event) => void submitAdditionalSow(event)}>
                <PanelTitle icon={<FilePlus2 size={18} />} title="Add SOW To Selected MSA" />
                <p className="contextLine">{selectedProject ? `${selectedProject.client_company_name} · ${selectedProject.msa_reference}` : 'Select an existing SOW first'}</p>
                <Field label="SOW title" name="sow_title" required />
                <Field label="SOW upload" name="sow_document" type="file" />
                <Field label="SOW amount" name="sow_amount" type="number" step="0.01" defaultValue="5000" required />
                <Field label="Currency" name="currency" defaultValue={selectedProject?.currency ?? 'USD'} required />
                <Field label="Start date" name="start_date" type="date" defaultValue={today()} required />
                <Field label="End date" name="end_date" type="date" />
                <Field label="Operations manager" name="operations_manager_name" defaultValue={me.full_name ?? 'Operations Manager'} required />
                <label className="field">
                  <span>SOW description</span>
                  <textarea name="sow_description" rows={3} />
                </label>
                <button className="secondary" disabled={!selectedProject || loading}>
                  <FilePlus2 size={18} />
                  <span>Add SOW</span>
                </button>
              </form>

              <form className="panel" onSubmit={(event) => void submitNeed(event)}>
                <PanelTitle icon={<ClipboardList size={18} />} title="Recruitment Need" />
                <label className="field">
                  <span>SOW</span>
                  <select value={selectedProject?.id ?? ''} onChange={(event) => setSelectedProjectId(Number(event.target.value))}>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>{project.project_code} · {project.title}</option>
                    ))}
                  </select>
                </label>
                <Field label="Position" name="position_title" required />
                <Field label="Number" name="number_of_positions" type="number" defaultValue="1" required />
                <label className="field">
                  <span>Type</span>
                  <select name="employment_type" defaultValue="FTE">
                    <option>FE</option>
                    <option>FTE</option>
                    <option>Fractional Consultant</option>
                  </select>
                </label>
                <label className="field">
                  <span>Billing type</span>
                  <select name="position_billing_type" value={needBillingType} onChange={(event) => setNeedBillingType(event.target.value)}>
                    <option value="fixed_fee">Fixed fee</option>
                    <option value="periodic">Periodic</option>
                  </select>
                </label>
                <Field label="Fee amount" name="fee_amount" type="number" step="0.01" />
                <Field label="Currency" name="currency" defaultValue={selectedProject?.currency ?? 'USD'} />
                <label className="field">
                  <span>Billing frequency</span>
                  <select name="billing_frequency" defaultValue={needBillingType === 'fixed_fee' ? 'single' : 'monthly'}>
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                <Field label={needBillingType === 'fixed_fee' ? 'Billing date' : 'Billing start'} name="billing_start_date" type="date" />
                {needBillingType !== 'fixed_fee' && <Field label="Billing end" name="billing_end_date" type="date" />}
                <Field label="Target start" name="target_start_date" type="date" />
                <Field label="Internal interviewers" name="internal_interviewers" placeholder="Names separated by semicolons" />
                <Field label="Detailed position upload" name="detail_document" type="file" />
                <label className="field">
                  <span>Description</span>
                  <textarea name="description" rows={4} required minLength={5} />
                </label>
                <button className="secondary" disabled={!selectedProject || loading}>
                  <BadgeCheck size={18} />
                  <span>Add Need</span>
                </button>
              </form>

              <form className="panel" onSubmit={(event) => void submitSchedule(event)}>
                <PanelTitle icon={<CalendarPlus size={18} />} title="Client Invoice Schedule" />
                <label className="field">
                  <span>SOW</span>
                  <select value={selectedProject?.id ?? ''} onChange={(event) => setSelectedProjectId(Number(event.target.value))}>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>{project.project_code} · {project.title}</option>
                    ))}
                  </select>
                </label>
                <Field label="Label" name="label" defaultValue="Monthly client billing" required />
                <label className="field">
                  <span>Invoice item description</span>
                  <textarea name="item_description" rows={3} defaultValue="Monthly outcome pod member X 1" required />
                </label>
                <Field label="Amount" name="amount" type="number" step="0.01" defaultValue="4000" required />
                <Field label="Currency" name="currency" defaultValue="USD" required />
                <label className="field">
                  <span>Frequency</span>
                  <select name="frequency" value={scheduleFrequency} onChange={(event) => setScheduleFrequency(event.target.value)}>
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                <Field label={scheduleBackfill ? 'Original first invoice date' : scheduleFrequency === 'single' ? 'Invoice date' : 'First invoice date'} name="first_invoice_date" type="date" defaultValue={today()} required />
                {scheduleFrequency !== 'single' && <Field label="Final invoice date" name="final_invoice_date" type="date" />}
                <label className="checkField">
                  <input name="historical_backfill" type="checkbox" checked={scheduleBackfill} onChange={(event) => setScheduleBackfill(event.currentTarget.checked)} />
                  <span>Historical schedule - start reminders from next cycle</span>
                </label>
                {scheduleBackfill && <Field label="Next invoice/reminder date" name="next_invoice_generation_date" type="date" defaultValue={endOfCurrentMonth()} required />}
                <button className="secondary" disabled={!selectedProject || loading}>
                  <CalendarPlus size={18} />
                  <span>Add Schedule</span>
                </button>
              </form>
            </>
          )}

          {!canOperate && (
          <section className="panel wide">
            <PanelTitle icon={<FileCheck2 size={18} />} title="Client Invoices" />
            <div className="toolbar">
              <select value={selectedInvoice?.id ?? ''} onChange={(event) => setSelectedInvoiceId(Number(event.target.value))}>
                {invoices.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    {invoice.invoice_number} · {invoice.status}
                  </option>
                ))}
              </select>
            </div>
            {selectedInvoice ? (
              <div className="invoiceGrid">
                <dl className="facts">
                  <div><dt>Invoice</dt><dd>{selectedInvoice.invoice_number}</dd></div>
                  <div><dt>Project</dt><dd>{selectedInvoice.project_code}</dd></div>
                  <div><dt>Client</dt><dd>{selectedInvoice.client_company_name}</dd></div>
                  <div><dt>Item</dt><dd>{selectedInvoice.item_description ?? 'Not entered'}</dd></div>
                  <div><dt>Amount</dt><dd>{selectedInvoice.currency} {selectedInvoice.amount}</dd></div>
                  <div><dt>Status</dt><dd><Status value={selectedInvoice.status} /></dd></div>
                  <div><dt>Paid</dt><dd>{selectedInvoice.currency} {selectedInvoice.paid_total ?? '0.00'}</dd></div>
                  {selectedInvoice.cancelled_amount && selectedInvoice.cancelled_amount !== '0.00' && (
                    <div><dt>Cancelled</dt><dd>{selectedInvoice.currency} {selectedInvoice.cancelled_amount}</dd></div>
                  )}
                  <div><dt>Balance</dt><dd>{selectedInvoice.currency} {selectedInvoice.balance_due ?? selectedInvoice.amount}</dd></div>
                </dl>
                <div className="actions">
                  <button className="secondary" onClick={downloadInvoice}>
                    <Download size={18} />
                    <span>Download</span>
                  </button>
                  {canClientApprove && (
                    <button
                      className="secondary"
                      disabled={loading || selectedInvoice.status !== 'due_for_client_approval'}
                      onClick={() => void invoiceAction('/client-account-approval', { approver_name: me.full_name ?? 'Client Account Executive' }, 'Client account executive approved invoice')}
                    >
                      <BadgeCheck size={18} />
                      <span>CAE Approve</span>
                    </button>
                  )}
                  {canFinance && (
                    <>
                      <button
                        className="secondary"
                        disabled={loading || selectedInvoice.status !== 'approved_by_client_account'}
                        onClick={() => void invoiceAction('/finance-approval', { approver_name: me.full_name ?? 'Finance Manager' }, 'Finance approved invoice')}
                      >
                        <FileCheck2 size={18} />
                        <span>Finance Approve</span>
                      </button>
                      <button
                        className="secondary"
                        disabled={loading || selectedInvoice.status !== 'approved_for_sending'}
                        onClick={() => void invoiceAction('/send', { sender_name: me.full_name ?? 'Finance Manager', recipient_email: selectedInvoice.client_contact_email }, 'Invoice sent to client')}
                      >
                        <Send size={18} />
                        <span>Send</span>
                      </button>
                      <button
                        className="secondary danger"
                        disabled={loading || ['paid', 'cancelled', 'partially_paid_remainder_cancelled'].includes(selectedInvoice.status)}
                        onClick={() => {
                          const reason = window.prompt('Reason for cancelling this invoice');
                          if (reason) void invoiceAction('/cancel', { cancelled_by_name: me.full_name ?? 'Finance Manager', reason }, 'Invoice cancelled');
                        }}
                      >
                        <span>Cancel Invoice</span>
                      </button>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <p className="empty">No invoices yet.</p>
            )}
          </section>
          )}

          {canFinance && (
            <form
              className="panel"
              onSubmit={(event) => {
                event.preventDefault();
                if (!selectedInvoice) return;
                const formElement = event.currentTarget;
                void invoiceAction('/payments', formPayload(formElement), 'Payment recorded');
                formElement.reset();
              }}
            >
              <PanelTitle icon={<Banknote size={18} />} title="Client Collection" />
              <Field label="Amount received" name="amount_received" type="number" step="0.01" defaultValue={selectedInvoice?.balance_due ?? selectedInvoice?.amount ?? '0'} required />
              <Field label="Received date" name="received_date" type="date" defaultValue={today()} required />
              <Field label="Bank reference" name="bank_reference" />
              <Field label="Recorded by" name="recorded_by_name" defaultValue={me.full_name ?? 'Finance Manager'} required />
              <label className="field">
                <span>Notes</span>
                <textarea name="notes" rows={3} />
              </label>
              <button className="primary" disabled={loading || !selectedInvoice || !['sent_to_client', 'partially_paid'].includes(selectedInvoice.status)}>
                <Banknote size={18} />
                <span>Record Payment</span>
              </button>
            </form>
          )}
        </section>
      )}
    </main>
  );
}

function ShellHeader({ loading, onRefresh, me, onLogout, onRoleChange }: { loading: boolean; onRefresh: () => void; me?: CurrentUser; onLogout?: () => void; onRoleChange?: () => void }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Project Billing Recruitment Payroll</p>
        <h1>Client Project To Collection</h1>
      </div>
      <div className="topActions">
        {me?.active_role && <span className="status">{roleLabel(me.active_role)}</span>}
        {me?.roles && me.roles.length > 1 && <button className="iconButton" onClick={onRoleChange} title="Change active role"><UserCog size={18} /><span>Role</span></button>}
        <button className="iconButton" onClick={onRefresh} disabled={loading} title="Refresh data">
          <RefreshCw size={18} />
          <span>Refresh</span>
        </button>
        {me?.authenticated && <button className="iconButton" onClick={onLogout} title="Log out"><LogOut size={18} /><span>Logout</span></button>}
      </div>
    </header>
  );
}

function ApprovalShell({
  loading,
  notice,
  me,
  approvalInvoiceId,
  approvalError,
  approvalInvoice,
  onApprove,
}: {
  loading: boolean;
  notice: Notice;
  me?: CurrentUser | null;
  approvalInvoiceId?: string;
  approvalError?: string | null;
  approvalInvoice?: ClientInvoice | null;
  onApprove?: () => void;
}) {
  if (!me) {
    return (
      <main className="approvalOnly">
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Invoice Approval Login</h2>
          <p>Sign in with the Google account assigned as Client Account Executive for this invoice.</p>
        </section>
      </main>
    );
  }

  if (!me.authenticated) {
    return (
      <main className="approvalOnly">
        {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Invoice Approval Login</h2>
          <p>Sign in with the Google account assigned as Client Account Executive for this invoice.</p>
          <a className="primary linkButton" href={`${API_BASE}/auth/login?approval_invoice_id=${encodeURIComponent(approvalInvoiceId ?? '')}`}>Continue with Google</a>
        </section>
      </main>
    );
  }

  if (approvalError === 'not_authorized') {
    return (
      <main className="approvalOnly">
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Invoice Not Available</h2>
          <p>This invoice approval link is only available to the Client Account Executive assigned to the project.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="approvalOnly">
      {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
      <section className="authGate approvalPanel">
        <FileCheck2 size={42} />
        <h2>Client Invoice Approval</h2>
        {!approvalInvoice && <p>{loading ? 'Loading invoice...' : 'This invoice approval link is not available for this account.'}</p>}
        {approvalInvoice && (
          <>
            <dl className="facts">
              <div><dt>Invoice</dt><dd>{approvalInvoice.invoice_number}</dd></div>
              <div><dt>Status</dt><dd><Status value={approvalInvoice.status} /></dd></div>
              <div><dt>Client</dt><dd>{approvalInvoice.client_company_name}</dd></div>
              <div><dt>Item</dt><dd>{approvalInvoice.item_description ?? 'Not entered'}</dd></div>
              <div><dt>SOW</dt><dd>{approvalInvoice.project_title}</dd></div>
              <div><dt>Invoice date</dt><dd>{approvalInvoice.issue_date}</dd></div>
              <div><dt>Due date</dt><dd>{approvalInvoice.due_date}</dd></div>
              <div><dt>Amount</dt><dd>{approvalInvoice.currency} {approvalInvoice.amount}</dd></div>
              <div><dt>Balance</dt><dd>{approvalInvoice.currency} {approvalInvoice.balance_due ?? approvalInvoice.amount}</dd></div>
            </dl>
            <button className="primary" disabled={loading || approvalInvoice.status !== 'due_for_client_approval'} onClick={onApprove}>
              <BadgeCheck size={18} />
              <span>Approve Invoice</span>
            </button>
          </>
        )}
      </section>
    </main>
  );
}

function CandidateInvoiceUploadShell({
  loading,
  notice,
  invoice,
  onSubmit,
}: {
  loading: boolean;
  notice: Notice;
  invoice: CandidateInvoiceUpload | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <main className="approvalOnly">
      {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
      <section className="authGate approvalPanel">
        <Upload size={42} />
        <h2>Upload Candidate Invoice</h2>
        {!invoice && <p>{loading ? 'Loading upload link...' : 'This candidate invoice upload link is not available.'}</p>}
        {invoice && (
          <>
            <dl className="facts">
              <div><dt>Candidate</dt><dd>{invoice.candidate_name}</dd></div>
              <div><dt>Position</dt><dd>{invoice.position_title ?? 'Not set'}</dd></div>
              <div><dt>Invoice due date</dt><dd>{invoice.invoice_due_date ?? 'Not set'}</dd></div>
              <div><dt>Amount</dt><dd>{invoice.currency} {invoice.amount}</dd></div>
              <div><dt>Status</dt><dd><Status value={invoice.status} /></dd></div>
            </dl>
            {invoice.token_used ? (
              <p className="empty">This single-use upload link has already been used.</p>
            ) : (
              <form className="stackedForm" onSubmit={onSubmit}>
                <p className="contextLine">This link is single-use and can be used only once.</p>
                <Field label="Invoice file" name="invoice_document" type="file" required />
                <button className="primary" disabled={loading}>
                  <Upload size={18} />
                  <span>Upload Invoice</span>
                </button>
              </form>
            )}
          </>
        )}
      </section>
    </main>
  );
}

function CandidateApprovalShell({
  loading,
  notice,
  me,
  candidateInvoiceId,
  candidateInvoiceError,
  invoice,
  onSubmit,
  onDownload,
}: {
  loading: boolean;
  notice: Notice;
  me?: CurrentUser | null;
  candidateInvoiceId?: string;
  candidateInvoiceError?: string | null;
  invoice?: CandidateInvoice | null;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onDownload?: () => void;
}) {
  if (!me) {
    return (
      <main className="approvalOnly">
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Candidate Invoice Approval Login</h2>
          <p>Sign in with the Google account assigned as Client Account Executive for this project.</p>
        </section>
      </main>
    );
  }

  if (!me.authenticated) {
    return (
      <main className="approvalOnly">
        {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Candidate Invoice Approval Login</h2>
          <p>Sign in with the Google account assigned as Client Account Executive for this project.</p>
          <a className="primary linkButton" href={`${API_BASE}/auth/login?candidate_invoice_id=${encodeURIComponent(candidateInvoiceId ?? '')}`}>Continue with Google</a>
        </section>
      </main>
    );
  }

  if (candidateInvoiceError === 'not_authorized') {
    return (
      <main className="approvalOnly">
        <section className="authGate">
          <ShieldCheck size={42} />
          <h2>Candidate Invoice Not Available</h2>
          <p>This approval link is only available to the Client Account Executive assigned to the project.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="approvalOnly">
      {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
      <section className="authGate approvalPanel">
        <FileCheck2 size={42} />
        <h2>Candidate Invoice Approval</h2>
        {!invoice && <p>{loading ? 'Loading candidate invoice...' : 'This candidate invoice approval link is not available for this account.'}</p>}
        {invoice && (
          <form className="stackedForm" onSubmit={onSubmit}>
            <dl className="facts">
              <div><dt>Project</dt><dd>{invoice.project_code}</dd></div>
              <div><dt>SOW</dt><dd>{invoice.project_title}</dd></div>
              <div><dt>Client</dt><dd>{invoice.client_company_name}</dd></div>
              <div><dt>Candidate</dt><dd>{invoice.candidate_name}</dd></div>
              <div><dt>Position</dt><dd>{invoice.position_title ?? 'Not set'}</dd></div>
              <div><dt>Invoice due date</dt><dd>{invoice.invoice_due_date ?? 'Not set'}</dd></div>
              <div><dt>Amount</dt><dd>{invoice.currency} {invoice.amount}</dd></div>
              <div><dt>Status</dt><dd><Status value={invoice.status} /></dd></div>
            </dl>
            <button className="secondary" type="button" onClick={onDownload} disabled={!invoice.invoice_document_id}>
              <Download size={18} />
              <span>Download Invoice</span>
            </button>
            <label className="field">
              <span>Comments</span>
              <textarea name="comments" rows={4} defaultValue={invoice.approval_comments ?? ''} />
            </label>
            <label className="field">
              <span>Decision</span>
              <select name="decision" defaultValue="approved">
                <option value="approved">Invoice approved</option>
                <option value="rejected">Rejected</option>
                <option value="on-hold">On-hold</option>
              </select>
            </label>
            <button className="primary" disabled={loading || ['paid', 'partially_paid'].includes(invoice.status)}>
              <BadgeCheck size={18} />
              <span>Submit Decision</span>
            </button>
          </form>
        )}
      </section>
    </main>
  );
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="panelTitle">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Field(props: React.InputHTMLAttributes<HTMLInputElement> & { label: string; name: string }) {
  const { label, ...inputProps } = props;
  return (
    <label className="field">
      <span>{label}</span>
      <input {...inputProps} />
    </label>
  );
}

function InvoiceDetail({
  selectedInvoice,
  loading,
  canClientApprove,
  canFinance,
  downloadInvoice,
  invoiceAction,
  currentUserName,
}: {
  selectedInvoice: ClientInvoice | undefined;
  loading: boolean;
  canClientApprove: boolean;
  canFinance: boolean;
  downloadInvoice: () => void;
  invoiceAction: (path: string, body: Record<string, unknown>, message: string) => Promise<void>;
  currentUserName: string | null;
}) {
  if (!selectedInvoice) return <p className="empty">No invoices yet.</p>;

  return (
    <div className="invoiceGrid">
      <dl className="facts">
        <div><dt>Invoice</dt><dd>{selectedInvoice.invoice_number}</dd></div>
        <div><dt>Project</dt><dd>{selectedInvoice.project_code}</dd></div>
        <div><dt>Client</dt><dd>{selectedInvoice.client_company_name}</dd></div>
        <div><dt>Item</dt><dd>{selectedInvoice.item_description ?? 'Not entered'}</dd></div>
        <div><dt>Amount</dt><dd>{selectedInvoice.currency} {selectedInvoice.amount}</dd></div>
        <div><dt>Status</dt><dd><Status value={selectedInvoice.status} /></dd></div>
        <div><dt>Paid</dt><dd>{selectedInvoice.currency} {selectedInvoice.paid_total ?? '0.00'}</dd></div>
        {selectedInvoice.cancelled_amount && selectedInvoice.cancelled_amount !== '0.00' && (
          <div><dt>Cancelled</dt><dd>{selectedInvoice.currency} {selectedInvoice.cancelled_amount}</dd></div>
        )}
        <div><dt>Balance</dt><dd>{selectedInvoice.currency} {selectedInvoice.balance_due ?? selectedInvoice.amount}</dd></div>
      </dl>
      <div className="actions">
        <button className="secondary" onClick={downloadInvoice}>
          <Download size={18} />
          <span>Download</span>
        </button>
        {canClientApprove && (
          <button
            className="secondary"
            disabled={loading || selectedInvoice.status !== 'due_for_client_approval'}
            onClick={() => void invoiceAction('/client-account-approval', { approver_name: currentUserName ?? 'Client Account Executive' }, 'Client account executive approved invoice')}
          >
            <BadgeCheck size={18} />
            <span>CAE Approve</span>
          </button>
        )}
        {canFinance && (
          <>
            <button
              className="secondary"
              disabled={loading || selectedInvoice.status !== 'approved_by_client_account'}
              onClick={() => void invoiceAction('/finance-approval', { approver_name: currentUserName ?? 'Finance Manager' }, 'Finance approved invoice')}
            >
              <FileCheck2 size={18} />
              <span>Finance Approve</span>
            </button>
            <button
              className="secondary"
              disabled={loading || selectedInvoice.status !== 'approved_for_sending'}
              onClick={() => void invoiceAction('/send', { sender_name: currentUserName ?? 'Finance Manager', recipient_email: selectedInvoice.client_contact_email }, 'Invoice sent to client')}
            >
              <Send size={18} />
              <span>Send</span>
            </button>
            <button
              className="secondary danger"
              disabled={loading || ['paid', 'cancelled', 'partially_paid_remainder_cancelled'].includes(selectedInvoice.status)}
              onClick={() => {
                const reason = window.prompt('Reason for cancelling this invoice');
                if (reason) void invoiceAction('/cancel', { cancelled_by_name: currentUserName ?? 'Finance Manager', reason }, 'Invoice cancelled');
              }}
            >
              <span>Cancel Invoice</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function Status({ value }: { value: string }) {
  return <span className={`status ${value}`}>{value.replaceAll('_', ' ')}</span>;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
