import { useCallback, useEffect, useRef, useState } from "react";
import api, { errMsg } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const PAGE_SIZE = 10;
const EMPTY_FILTERS = { start: "", end: "", event: "", username: "" };

const EVENT_CLASS = { LOGIN: "ok", LOGOUT: "info", LOGIN_FAILED: "error" };
const EVENT_LABEL = { LOGIN: "Login", LOGOUT: "Logout", LOGIN_FAILED: "Failed login" };

// The API stores UTC timestamps without a timezone suffix. Add "Z" so the
// browser shows them in the user's local time.
const formatTimestamp = (value) => {
  if (!value) return "";
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`).toLocaleString();
};

export default function Logs() {
  const [tab, setTab] = useState("logins");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState(EMPTY_FILTERS);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [deletingAction, setDeletingAction] = useState("");
  const [retentionDays, setRetentionDays] = useState(7);
  const [page, setPage] = useState(1);
  const requestRef = useRef(0);

  const load = useCallback(
    async (query) => {
      const requestId = ++requestRef.current;
      setError("");
      setLoading(true);
      try {
        const common = {
          start: query.start || undefined,
          end: query.end || undefined,
        };
        const req = tab === "logins"
          ? api.get("/logs/logins", { params: { ...common, event: query.event || undefined } })
          : api.get("/logs/audit", {
              params: { ...common, username: query.username || undefined },
            });
        const { data } = await req;
        if (requestId !== requestRef.current) return;
        setRows(data);
        setPage(1);
      } catch (e) {
        if (requestId === requestRef.current) setError(errMsg(e));
      } finally {
        if (requestId === requestRef.current) setLoading(false);
      }
    },
    [tab],
  );

  useEffect(() => {
    load(applied);
  }, [load, applied]);

  useEffect(() => {
    api
      .get("/logs/retention")
      .then(({ data }) => setRetentionDays(data.days))
      .catch(() => {});
  }, []);

  const switchTab = (next) => {
    if (next === tab) return;
    setTab(next);
    setFilters(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setNotice("");
  };

  const updateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
  };

  const applyFilters = () => {
    if (filters.start && filters.end && filters.start > filters.end) {
      setError("From date must be on or before To date.");
      return;
    }
    setNotice("");
    setApplied({ ...filters });
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setApplied({ ...EMPTY_FILTERS });
    setNotice("");
  };

  const rangeLabel = () => {
    if (filters.start && filters.end) return `${filters.start} to ${filters.end}`;
    if (filters.start) return `from ${filters.start}`;
    if (filters.end) return `through ${filters.end}`;
    return "the selected dates";
  };

  const deleteByDate = async () => {
    if (!filters.start && !filters.end) {
      setError("Choose a From or To date before deleting.");
      return;
    }
    if (filters.start && filters.end && filters.start > filters.end) {
      setError("From date must be on or before To date.");
      return;
    }
    const kind = tab === "logins" ? "sign-in" : "audit";
    const confirmed = window.confirm(
      `Delete ${kind} records ${rangeLabel()}? This cannot be undone.`,
    );
    if (!confirmed) return;

    setDeleting(true);
    setDeletingAction("date");
    setError("");
    setNotice("");
    try {
      const { data } = await api.delete(tab === "logins" ? "/logs/logins" : "/logs/audit", {
        params: {
          start: filters.start || undefined,
          end: filters.end || undefined,
        },
      });
      setNotice(
        `${data.deleted} ${kind} record${data.deleted === 1 ? "" : "s"} deleted.`,
      );
      setApplied({ ...filters });
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setDeleting(false);
      setDeletingAction("");
    }
  };

  const clearAll = async () => {
    const kind = tab === "logins" ? "sign-in" : "audit";
    const extra = tab === "logins"
      ? "A manager deletion entry will be kept in the audit trail."
      : "One manager deletion entry will remain in the audit trail.";
    const confirmed = window.confirm(
      `Permanently delete all ${kind} records? ${extra}`,
    );
    if (!confirmed) return;

    setDeleting(true);
    setDeletingAction("all");
    setError("");
    setNotice("");
    try {
      const { data } = await api.delete(`/logs/${tab === "logins" ? "logins" : "audit"}/all`);
      setNotice(
        `${data.deleted} ${kind} record${data.deleted === 1 ? "" : "s"} deleted.`,
      );
      setApplied({ ...applied });
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setDeleting(false);
      setDeletingAction("");
    }
  };

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visibleRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Administration"
        title="Activity & audit"
        subtitle="Review sign-ins and every recorded change across the store."
        actions={
          <button className="ghost" type="button" onClick={() => load(applied)} disabled={loading || deleting}>
            <Icon name="refresh" size={16} /> {loading ? "Refreshing…" : "Refresh"}
          </button>
        }
      />

      <section className="card">
        <div className="log-toolbar">
          <div className="tabs" role="tablist" aria-label="Log type">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "logins"}
              className={`tab ${tab === "logins" ? "active" : ""}`}
              onClick={() => switchTab("logins")}
            >
              <Icon name="key" size={15} /> Sign-ins
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "audit"}
              className={`tab ${tab === "audit" ? "active" : ""}`}
              onClick={() => switchTab("audit")}
            >
              <Icon name="logs" size={15} /> Audit trail
            </button>
          </div>
          <span className="pill muted">{rows.length} records</span>
        </div>

        <div className="log-filters">
          <div className="field">
            <label htmlFor="log-start">From</label>
            <input
              id="log-start"
              type="date"
              value={filters.start}
              onChange={(event) => updateFilter("start", event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="log-end">To</label>
            <input
              id="log-end"
              type="date"
              value={filters.end}
              onChange={(event) => updateFilter("end", event.target.value)}
            />
          </div>
          {tab === "logins" ? (
            <div className="field">
              <label htmlFor="log-event">Event</label>
              <select
                id="log-event"
                value={filters.event}
                onChange={(event) => {
                  const next = { ...filters, event: event.target.value };
                  setFilters(next);
                  setApplied(next);
                }}
              >
                <option value="">All events</option>
                <option value="LOGIN">Login</option>
                <option value="LOGOUT">Logout</option>
                <option value="LOGIN_FAILED">Failed login</option>
              </select>
            </div>
          ) : (
            <div className="field">
              <label htmlFor="log-username">Username</label>
              <input
                id="log-username"
                type="search"
                placeholder="Any username"
                value={filters.username}
                onChange={(event) => updateFilter("username", event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") applyFilters();
                }}
              />
            </div>
          )}
          <button className="primary" type="button" onClick={applyFilters} disabled={loading || deleting}>
            <Icon name="search" size={16} /> Filter
          </button>
          <button className="ghost" type="button" onClick={resetFilters} disabled={loading || deleting}>
            Reset
          </button>
        </div>

        <div className="log-maintenance">
          <p className="small">
            Sign-in and audit records older than <strong>{retentionDays} days</strong> are
            deleted automatically.
          </p>
          <div className="row">
            <button
              className="ghost danger-text"
              type="button"
              onClick={deleteByDate}
              disabled={deleting || (!filters.start && !filters.end)}
            >
              <Icon name="warning" size={15} /> {deletingAction === "date" ? "Deleting…" : "Delete selected dates"}
            </button>
            <button className="danger" type="button" onClick={clearAll} disabled={deleting}>
              <Icon name="warning" size={15} /> {deletingAction === "all" ? "Deleting…" : `Clear all ${tab === "logins" ? "sign-ins" : "audit entries"}`}
            </button>
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert ok">{notice}</div>}

        <div className="table-wrap flush">
          {tab === "logins" ? (
            <table className="table">
              <thead>
                <tr><th>Time</th><th>User</th><th>Event</th><th>IP address</th><th>Device</th></tr>
              </thead>
              <tbody>
                {visibleRows.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{formatTimestamp(r.created_at)}</td>
                    <td>
                      <div className="person-cell compact">
                        <div className="avatar avatar-sm">{r.username?.slice(0, 2).toUpperCase()}</div>
                        <strong>{r.username}</strong>
                      </div>
                    </td>
                    <td>
                      <span className={`pill ${EVENT_CLASS[r.event] || "muted"}`}>
                        {EVENT_LABEL[r.event] || r.event}
                      </span>
                    </td>
                    <td className="mono">{r.ip_address || <span className="muted-text">—</span>}</td>
                    <td className="cell-summary small">{r.user_agent || <span className="muted-text">—</span>}</td>
                  </tr>
                ))}
                {visibleRows.length === 0 && (
                  <tr>
                    <td colSpan="5">
                      <div className="empty-state">
                        <div className="empty-icon"><Icon name="key" size={24} /></div>
                        <h4>No sign-in activity</h4>
                        <p>Login and logout events will appear here.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Time</th><th>User</th><th>IP address</th><th>Action</th><th>Entity</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {visibleRows.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{formatTimestamp(r.created_at)}</td>
                    <td>
                      <div className="person-cell compact">
                        <div className="avatar avatar-sm">
                          {(r.username || String(r.actor_id ?? "?")).slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <strong>{r.username || <span className="muted-text">Unknown</span>}</strong>
                          {r.actor_id != null && <div className="small table-note">#{r.actor_id}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="mono">{r.ip_address || <span className="muted-text">—</span>}</td>
                    <td><strong>{r.action}</strong></td>
                    <td>
                      <span className="mono">{r.entity}</span>
                      {r.entity_id && <div className="small table-note">#{r.entity_id}</div>}
                    </td>
                    <td className="cell-summary small">{r.detail || <span className="muted-text">—</span>}</td>
                  </tr>
                ))}
                {visibleRows.length === 0 && (
                  <tr>
                    <td colSpan="6">
                      <div className="empty-state">
                        <div className="empty-icon"><Icon name="logs" size={24} /></div>
                        <h4>No audit events</h4>
                        <p>Changes made in the system will be recorded here.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
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
