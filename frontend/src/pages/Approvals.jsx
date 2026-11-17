import { useEffect, useState } from "react";
import api, { errMsg, money } from "../api";
import { useAuth } from "../auth.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const PAGE_SIZE = 10;
const STATUS_CLASS = { APPROVED: "ok", REJECTED: "error", PENDING: "warn" };
const STATUS_LABEL = { APPROVED: "Approved", REJECTED: "Rejected", PENDING: "Pending" };

/** admin: approve / reject sales over the limit. manager: read-only tracking. */
export default function Approvals() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("PENDING");
  const [error, setError] = useState("");
  const [decision, setDecision] = useState(null); // { id, action }
  const [decisionNote, setDecisionNote] = useState("");
  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visibleRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const load = (resetPage = true) =>
    api.get("/approvals", { params: { status: filter || undefined } })
      .then((r) => {
        setRows(r.data);
        if (resetPage) setPage(1);
        setError("");
      }).catch((e) => setError(errMsg(e)));
  useEffect(() => { load(); const t = setInterval(() => load(false), 10000); return () => clearInterval(t); }, [filter]);

  const decide = async (id, action) => {
    const note = decisionNote.trim();
    if (action === "reject" && !note) {
      setError("Please enter a rejection reason.");
      return;
    }
    try {
      await api.post(`/approvals/${id}/${action}`, { note: note || null });
      setDecision(null);
      setDecisionNote("");
      setError("");
      load(false);
    } catch (e) { setError(errMsg(e)); }
  };

  const openDecision = (id, action) => {
    setDecision({ id, action });
    setDecisionNote("");
    setError("");
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Operations"
        title="Approvals"
        subtitle={user.role === "manager"
          ? "Track every high-value sale decision across the store."
          : "Review high-value sales before they reach the checkout."}
        actions={
          <div className="filter-control">
            <Icon name="approvals" size={16} />
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter approvals">
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="">All decisions</option>
            </select>
          </div>
        }
      />

      {user.role === "manager" && (
        <div className="alert info">
          Managers can monitor the approval trail. Only admins can approve or reject a sale.
        </div>
      )}

      {error && <div className="alert error">{error}</div>}

      {decision && (
        <div className="card decision-card">
          <div className="section-head">
            <div>
              <span className="eyebrow">{decision.action === "approve" ? "Approve sale" : "Reject sale"}</span>
              <h3>{decision.action === "approve" ? "Confirm approval" : "Tell the cashier why"}</h3>
            </div>
            <span className={`pill ${decision.action === "approve" ? "ok" : "error"}`}>
              {decision.action === "approve" ? "Approval" : "Rejection"}
            </span>
          </div>
          <div className="field">
            <label htmlFor="decision-note">
              {decision.action === "reject" ? "Reason for rejection (required)" : "Optional note"}
            </label>
            <textarea
              id="decision-note"
              rows="3"
              placeholder={decision.action === "reject" ? "Reason for rejection" : "Optional note"}
              value={decisionNote}
              onChange={(e) => setDecisionNote(e.target.value)}
            />
          </div>
          <div className="row">
            <button className="primary" type="button" onClick={() => decide(decision.id, decision.action)}>
              Confirm {decision.action}
            </button>
            <button className="ghost" type="button" onClick={() => { setDecision(null); setDecisionNote(""); setError(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Receipt</th><th className="right">Total</th><th>Requested by</th><th>Requested</th><th>Status</th><th>Decided by</th><th>Note</th>{user.role === "admin" && <th className="right">Actions</th>}</tr></thead>
          <tbody>
            {visibleRows.map((r) => (
              <tr key={r.approval_id}>
                <td className="mono">{r.receipt_no}</td>
                <td className="right"><strong>{money(r.total)}</strong></td>
                <td>{r.requested_by}</td>
                <td>{new Date(r.requested_at).toLocaleString()}</td>
                <td><span className={`pill ${STATUS_CLASS[r.status] || "muted"}`}>{STATUS_LABEL[r.status] || r.status}</span></td>
                <td>
                  {r.decided_by ?? <span className="muted-text">—</span>}
                  {r.decided_at && <div className="small table-note">{new Date(r.decided_at).toLocaleString()}</div>}
                </td>
                <td className="cell-summary">{r.decision_note || <span className="muted-text">—</span>}</td>
                {user.role === "admin" && (
                  <td>
                    <div className="row actions-cell">
                      {r.status === "PENDING" && (
                        <>
                          <button className="primary small-button" type="button" onClick={() => openDecision(r.approval_id, "approve")}>Approve</button>
                          <button className="ghost small-button" type="button" onClick={() => openDecision(r.approval_id, "reject")}>Reject</button>
                        </>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {visibleRows.length === 0 && (
              <tr>
                <td colSpan={user.role === "admin" ? 8 : 7}>
                  <div className="empty-state">
                    <div className="empty-icon ok"><Icon name="approvals" size={24} /></div>
                    <h4>Nothing waiting</h4>
                    <p>Approval requests will show up here when a sale needs review.</p>
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
    </div>
  );
}
