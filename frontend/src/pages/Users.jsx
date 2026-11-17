import { useEffect, useState } from "react";
import api, { errMsg } from "../api";
import { useAuth } from "../auth.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const EMPTY = { username: "", password: "", full_name: "", email: "" };
const PAGE_SIZE = 10;

const ROLE_LABEL = { manager: "Manager", admin: "Admin", emp: "Employee" };

function initials(name) {
  return (name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState(null);
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState(null);

  const totalPages = Math.max(1, Math.ceil(users.length / PAGE_SIZE));
  const visibleUsers = users.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const activeCount = users.filter((u) => u.is_active).length;
  const adminCount = users.filter((u) => u.role === "admin").length;
  const employeeCount = users.filter((u) => u.role === "emp").length;

  const load = async () => {
    try {
      const { data } = await api.get("/users");
      setUsers(data);
      setPage(1);
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    }
  };
  useEffect(() => { load(); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const beginEdit = (employee) => {
    setEditingId(employee.id);
    setForm({
      username: employee.username,
      password: "",
      full_name: employee.full_name,
      email: employee.email || "",
    });
    setMsg(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY);
  };

  const create = async (e) => {
    e.preventDefault();
    if (busy) return;
    setMsg(null);
    setBusy(true);
    try {
      if (editingId) {
        const payload = {
          username: form.username || undefined,
          full_name: form.full_name || undefined,
          email: form.email || null,
          ...(form.password ? { password: form.password } : {}),
        };
        await api.patch(`/users/${editingId}`, payload);
        setMsg({ ok: true, text: "Employee updated." });
        cancelEdit();
      } else {
        await api.post("/users", { ...form, email: form.email || null });
        setMsg({ ok: true, text: "Employee created." });
        setForm(EMPTY);
      }
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setBusy(false);
    }
  };

  const act = async (id, fn) => {
    setRowBusy(id);
    setMsg(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setRowBusy(null);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Administration"
        title="Team"
        subtitle="Create accounts, manage access, and keep the team list current."
        actions={<span className="pill muted">{users.length} people</span>}
      />

      <div className="mini-stats">
        <div className="mini-stat"><span>Team members</span><strong>{users.length}</strong></div>
        <div className="mini-stat"><span>Active accounts</span><strong>{activeCount}</strong></div>
        <div className="mini-stat"><span>Admins</span><strong>{adminCount}</strong></div>
        <div className="mini-stat"><span>Employees</span><strong>{employeeCount}</strong></div>
      </div>

      {msg && <div className={`alert ${msg.ok ? "ok" : "error"}`}>{msg.text}</div>}

      <div className="split-layout">
        <section className="card">
          <div className="section-head">
            <div>
              <span className="eyebrow">{editingId ? "Editing employee" : "New account"}</span>
              <h3>{editingId ? "Update team member" : "Add a team member"}</h3>
              <p className="small">
                {editingId
                  ? "Leave the password blank if you want to keep the current one."
                  : "New accounts are created as employees with checkout access."}
              </p>
            </div>
            {editingId && <span className="pill info">Editing</span>}
          </div>

          <form onSubmit={create}>
            <div className="form-grid two">
              <div className="field">
                <label htmlFor="user-username">Username</label>
                <input
                  id="user-username"
                  value={form.username}
                  onChange={set("username")}
                  placeholder="e.g. alex"
                  required
                  minLength={3}
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label htmlFor="user-name">Full name</label>
                <input
                  id="user-name"
                  value={form.full_name}
                  onChange={set("full_name")}
                  placeholder="e.g. Alex Rivera"
                  required
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label htmlFor="user-email">Email <span className="optional">(optional)</span></label>
                <input
                  id="user-email"
                  type="email"
                  value={form.email}
                  onChange={set("email")}
                  placeholder="alex@example.com"
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label htmlFor="user-password">
                  {editingId ? "New password" : "Password"}
                  {editingId && <span className="optional"> (optional)</span>}
                </label>
                <input
                  id="user-password"
                  placeholder={editingId ? "Leave blank to keep current" : "At least 8 characters"}
                  type="password"
                  value={form.password}
                  onChange={set("password")}
                  required={!editingId}
                  minLength={editingId ? undefined : 8}
                  autoComplete="new-password"
                />
              </div>
            </div>

            <div className="row form-actions">
              <button className="primary" disabled={busy}>
                {busy ? "Saving…" : editingId ? "Update employee" : "Create employee"}
              </button>
              {editingId && (
                <button type="button" className="ghost" onClick={cancelEdit} disabled={busy}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </section>

        <aside className="card role-guide">
          <div className="section-head">
            <div>
              <span className="eyebrow">Access levels</span>
              <h3>What each role can do</h3>
            </div>
          </div>
          <div className="role-guide-list">
            <div className="role-guide-item">
              <span className="badge manager">Manager</span>
              <p>Full oversight: products, team, customers, approvals, stock, and the audit trail.</p>
            </div>
            <div className="role-guide-item">
              <span className="badge admin">Admin</span>
              <p>Approves sales, manages stock and customers, and reviews reports.</p>
            </div>
            <div className="role-guide-item">
              <span className="badge emp">Employee</span>
              <p>Runs checkout, tracks their own sales, and views their own report.</p>
            </div>
          </div>
          <div className="alert info compact-alert">
            <Icon name="warning" size={16} />
            <span>Only managers can create accounts or change roles.</span>
          </div>
        </aside>
      </div>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Team directory</h3>
            <p className="small">Accounts and their current access level.</p>
          </div>
          <span className="pill muted">Page {page} of {totalPages}</span>
        </div>

        <div className="table-wrap flush">
          <table className="table users-table">
            <thead>
              <tr><th>Employee</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th className="right">Actions</th></tr>
            </thead>
            <tbody>
              {visibleUsers.map((u) => (
                <tr key={u.id} className={u.is_active ? "" : "row-muted"}>
                  <td>
                    <div className="person-cell">
                      <div className={`avatar role-${u.role}`}>{initials(u.full_name)}</div>
                      <div>
                        <strong>{u.full_name}</strong>
                        <div className="small table-note">
                          @{u.username} {u.id === me.id && <span className="you-tag">You</span>}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>{u.email || <span className="muted-text">—</span>}</td>
                  <td><span className={`badge ${u.role}`}>{ROLE_LABEL[u.role] || u.role}</span></td>
                  <td>
                    <span className={`pill ${u.is_active ? "ok" : "muted"}`}>
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="nowrap">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="row actions-cell">
                      {u.role === "emp" && (
                        <button
                          className="ghost small-button"
                          type="button"
                          title="Promote to admin"
                          onClick={() => act(u.id, () => api.patch(`/users/${u.id}/role`, { role: "admin" }))}
                          disabled={rowBusy === u.id}
                        >
                          Promote
                        </button>
                      )}
                      {u.role === "admin" && (
                        <button
                          className="ghost small-button"
                          type="button"
                          title="Demote to employee"
                          onClick={() => act(u.id, () => api.patch(`/users/${u.id}/role`, { role: "emp" }))}
                          disabled={rowBusy === u.id}
                        >
                          Demote
                        </button>
                      )}
                      {u.id !== me.id && (
                        <button className="ghost small-button" type="button" onClick={() => beginEdit(u)} disabled={rowBusy === u.id}>
                          Edit
                        </button>
                      )}
                      {u.id !== me.id && (
                        <button
                          className="ghost small-button"
                          type="button"
                          onClick={() => act(u.id, () => api.patch(`/users/${u.id}/active`, { is_active: !u.is_active }))}
                          disabled={rowBusy === u.id}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {visibleUsers.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty-state">
                      <div className="empty-icon"><Icon name="users" size={24} /></div>
                      <h4>No team members yet</h4>
                      <p>Create the first employee account using the form above.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
        />
      </section>
    </div>
  );
}
