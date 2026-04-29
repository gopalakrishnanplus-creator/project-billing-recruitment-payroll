import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  BadgeCheck,
  Banknote,
  CalendarPlus,
  ClipboardList,
  FileCheck2,
  FilePlus2,
  LogOut,
  RefreshCw,
  Send,
  ShieldCheck,
  UserCog,
} from 'lucide-react';
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

type Project = {
  id: number;
  project_code: string;
  title: string;
  sow_amount: string;
  currency: string;
  start_date: string;
  end_date: string | null;
  operations_manager_name: string;
  status: string;
  client_company_name: string;
  client_contact_name: string;
  client_contact_email: string;
  msa_reference: string | null;
  recruitment_needs: RecruitmentNeed[];
  invoice_schedules: InvoiceSchedule[];
  client_invoices: ClientInvoice[];
};

type RecruitmentNeed = {
  id: number;
  position_title: string;
  number_of_positions: number;
  employment_type: string;
  status: string;
};

type InvoiceSchedule = {
  id: number;
  label: string;
  amount: string;
  currency: string;
  frequency: string;
  first_invoice_date: string;
  final_invoice_date: string | null;
};

type ClientInvoice = {
  id: number;
  project_id: number;
  invoice_number: string;
  issue_date: string;
  due_date: string;
  amount: string;
  currency: string;
  status: string;
  project_code?: string;
  project_title?: string;
  client_company_name?: string;
  client_contact_name?: string;
  client_contact_email?: string;
  paid_total?: string;
  balance_due?: string;
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

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function formPayload(form: HTMLFormElement): Record<string, FormDataEntryValue> {
  return Object.fromEntries(Array.from(new FormData(form).entries()).filter(([, value]) => value !== ''));
}

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role.replaceAll('_', ' ');
}

function App() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [invoices, setInvoices] = useState<ClientInvoice[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(null);
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

  const activeRole = me?.active_role;
  const canAdmin = activeRole === 'system_admin';
  const canOperate = activeRole === 'operations_manager';
  const canFinance = activeRole === 'finance_manager';
  const canClientApprove = activeRole === 'client_account_executive';
  const canViewWorkflow = Boolean(activeRole && activeRole !== 'system_admin');

  async function refreshMe() {
    const current = await api<CurrentUser>('/auth/me');
    setMe(current);
    return current;
  }

  async function refreshData(current = me) {
    if (!current?.authenticated || !current.active_role || current.active_role === 'system_admin') return;
    setLoading(true);
    try {
      const [projectData, invoiceData] = await Promise.all([
        api<Project[]>('/projects'),
        api<ClientInvoice[]>('/client-invoices'),
      ]);
      setProjects(projectData);
      setInvoices(invoiceData);
      if (!selectedProjectId && projectData[0]) setSelectedProjectId(projectData[0].id);
      if (!selectedInvoiceId && invoiceData[0]) setSelectedInvoiceId(invoiceData[0].id);
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
      if (current.authenticated && current.active_role && current.active_role !== 'system_admin') {
        await refreshData(current);
      }
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Unable to load app state' });
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
    void refreshAll();
  }, []);

  useEffect(() => {
    if (me?.active_role === 'system_admin') void refreshUsers();
    if (me?.active_role && me.active_role !== 'system_admin') void refreshData(me);
  }, [me?.active_role]);

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
  }

  async function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    await mutate(async () => {
      const project = await api<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setSelectedProjectId(project.id);
      formElement.reset();
      return `Created ${project.project_code}`;
    });
  }

  async function submitNeed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    await mutate(async () => {
      await api<RecruitmentNeed>(`/projects/${selectedProject.id}/recruitment-needs`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      formElement.reset();
      return 'Recruitment need added';
    });
  }

  async function submitSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    const formElement = event.currentTarget;
    const payload = formPayload(formElement);
    await mutate(async () => {
      await api<InvoiceSchedule>(`/projects/${selectedProject.id}/invoice-schedules`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      formElement.reset();
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

  async function generateInvoices() {
    await mutate(async () => {
      const result = await api<{ generated_count: number; invoices: ClientInvoice[] }>(`/invoices/generate?as_of=${today()}`, {
        method: 'POST',
      });
      if (result.invoices[0]) setSelectedInvoiceId(result.invoices[0].id);
      return `${result.generated_count} invoice${result.generated_count === 1 ? '' : 's'} generated`;
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

  async function mutate(work: () => Promise<string>) {
    setLoading(true);
    setNotice(null);
    try {
      const message = await work();
      if (me?.active_role === 'system_admin') await refreshUsers();
      if (me?.active_role && me.active_role !== 'system_admin') await refreshData(me);
      setNotice({ tone: 'ok', message });
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : 'Action failed' });
    } finally {
      setLoading(false);
    }
  }

  if (me === null) {
    return <ShellHeader loading={loading} onRefresh={() => void refreshAll()} />;
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

      {canAdmin && (
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
            <PanelTitle icon={<ShieldCheck size={18} />} title="Provisioned Users" />
            <div className="userList">
              {users.map((user) => (
                <div className="userRow" key={user.id}>
                  <div>
                    <strong>{user.full_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <div className="rolePills">
                    {user.roles.map((role) => <span className="status" key={role}>{roleLabel(role)}</span>)}
                    {!user.is_active && <span className="status cancelled">inactive</span>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </section>
      )}

      {canViewWorkflow && (
        <section className="workspace">
          {canOperate && (
            <form className="panel wide" onSubmit={(event) => void submitProject(event)}>
              <PanelTitle icon={<FilePlus2 size={18} />} title="Project Entry" />
              <div className="grid two">
                <Field label="Client company" name="client_company_name" required />
                <Field label="Client contact name" name="client_contact_name" required />
                <Field label="Client contact email" name="client_contact_email" type="email" required />
                <Field label="Client contact phone" name="client_contact_phone" />
                <Field label="MSA reference" name="msa_reference" required />
                <Field label="MSA file name" name="msa_document_name" placeholder="master-services.pdf" />
                <Field label="SOW title" name="sow_title" required />
                <Field label="SOW file name" name="sow_document_name" placeholder="signed-sow.pdf" />
                <Field label="SOW amount" name="sow_amount" type="number" step="0.01" defaultValue="12000" required />
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
            <PanelTitle icon={<ClipboardList size={18} />} title="Project Register" />
            <select value={selectedProject?.id ?? ''} onChange={(event) => setSelectedProjectId(Number(event.target.value))}>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.project_code} · {project.client_company_name}
                </option>
              ))}
            </select>
            {selectedProject ? (
              <dl className="facts">
                <div><dt>Project</dt><dd>{selectedProject.title}</dd></div>
                <div><dt>Client</dt><dd>{selectedProject.client_company_name}</dd></div>
                <div><dt>Contact</dt><dd>{selectedProject.client_contact_email}</dd></div>
                <div><dt>SOW</dt><dd>{selectedProject.currency} {selectedProject.sow_amount}</dd></div>
                <div><dt>Needs</dt><dd>{selectedProject.recruitment_needs.length}</dd></div>
                <div><dt>Schedules</dt><dd>{selectedProject.invoice_schedules.length}</dd></div>
              </dl>
            ) : (
              <p className="empty">No projects yet.</p>
            )}
          </section>

          {canOperate && (
            <>
              <form className="panel" onSubmit={(event) => void submitNeed(event)}>
                <PanelTitle icon={<ClipboardList size={18} />} title="Recruitment Need" />
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
                <Field label="Target start" name="target_start_date" type="date" />
                <Field label="Internal interviewers" name="internal_interviewers" placeholder="Names separated by semicolons" />
                <label className="field">
                  <span>Description</span>
                  <textarea name="description" rows={4} required />
                </label>
                <button className="secondary" disabled={!selectedProject || loading}>
                  <BadgeCheck size={18} />
                  <span>Add Need</span>
                </button>
              </form>

              <form className="panel" onSubmit={(event) => void submitSchedule(event)}>
                <PanelTitle icon={<CalendarPlus size={18} />} title="Client Invoice Schedule" />
                <Field label="Label" name="label" defaultValue="Monthly client billing" required />
                <Field label="Amount" name="amount" type="number" step="0.01" defaultValue="4000" required />
                <Field label="Currency" name="currency" defaultValue="USD" required />
                <label className="field">
                  <span>Frequency</span>
                  <select name="frequency" defaultValue="monthly">
                    <option value="single">Single</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                  </select>
                </label>
                <Field label="First invoice date" name="first_invoice_date" type="date" defaultValue={today()} required />
                <Field label="Final invoice date" name="final_invoice_date" type="date" />
                <button className="secondary" disabled={!selectedProject || loading}>
                  <CalendarPlus size={18} />
                  <span>Add Schedule</span>
                </button>
              </form>
            </>
          )}

          <section className="panel wide">
            <PanelTitle icon={<FileCheck2 size={18} />} title="Client Invoices" />
            <div className="toolbar">
              {canOperate && (
                <button className="primary" onClick={() => void generateInvoices()} disabled={loading}>
                  <FilePlus2 size={18} />
                  <span>Generate Due</span>
                </button>
              )}
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
                  <div><dt>Amount</dt><dd>{selectedInvoice.currency} {selectedInvoice.amount}</dd></div>
                  <div><dt>Status</dt><dd><Status value={selectedInvoice.status} /></dd></div>
                  <div><dt>Balance</dt><dd>{selectedInvoice.currency} {selectedInvoice.balance_due ?? selectedInvoice.amount}</dd></div>
                </dl>
                <div className="actions">
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
                    </>
                  )}
                </div>
              </div>
            ) : (
              <p className="empty">No invoices yet.</p>
            )}
          </section>

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

function Status({ value }: { value: string }) {
  return <span className={`status ${value}`}>{value.replaceAll('_', ' ')}</span>;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
