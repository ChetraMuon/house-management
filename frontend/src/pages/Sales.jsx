import { useRef, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaymentPanel from "../components/PaymentPanel.jsx";
import Receipt from "../components/Receipt.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const STATUS_CLASS = {
  PAID: "ok", READY: "info", APPROVED: "ok", PENDING_APPROVAL: "warn", REJECTED: "error", CANCELLED: "muted",
};
const STATUS_LABEL = {
  PAID: "Paid", READY: "Ready", APPROVED: "Approved", PENDING_APPROVAL: "Awaiting approval",
  REJECTED: "Rejected", CANCELLED: "Cancelled",
};
const PAGE_SIZE = 10;

const localDate = (value = new Date()) =>
  new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const formatDay = (day) =>
  day
    ? new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "";

export default function Sales() {
  const [day, setDay] = useState("");
  const [sales, setSales] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [paying, setPaying] = useState(null);
  const [receiptId, setReceiptId] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const requestRef = useRef(0);

  const totalPages = Math.max(1, Math.ceil(sales.length / PAGE_SIZE));
  const visibleSales = sales.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const load = async (resetPage = true) => {
    if (!day) {
      setError("Select a date first.");
      return;
    }

    const requestId = ++requestRef.current;
    setLoading(true);
    setError("");

    try {
      const { data } = await api.get("/sales", {
        params: { start: day, end: day },
      });
      if (requestId !== requestRef.current) return;
      setSales(data);
      setHasSearched(true);
      if (resetPage) setPage(1);
    } catch (e) {
      if (requestId === requestRef.current) setError(errMsg(e));
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  };

  const chooseDay = (value) => {
    requestRef.current += 1;
    setDay(value);
    setSales([]);
    setHasSearched(false);
    setLoading(false);
    setPage(1);
    setError("");
  };

  const showToday = () => {
    chooseDay(localDate());
  };

  const cancel = async (id) => {
    if (!confirm("Cancel this order?")) return;
    try { await api.post(`/sales/${id}/cancel`); load(false); } catch (e) { setError(errMsg(e)); }
  };

  const awaiting = sales.filter((s) => s.status === "PENDING_APPROVAL").length;
  const paid = sales.filter((s) => s.status === "PAID").length;
  const paidTotal = sales
    .filter((s) => s.status === "PAID")
    .reduce((sum, s) => sum + Number(s.total || 0), 0);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Point of sale"
        title="My sales"
        subtitle="Choose a day to review your orders, approval status, and payment actions."
        actions={
          hasSearched ? (
            <button className="ghost" type="button" onClick={() => load(false)} disabled={loading}>
              <Icon name="refresh" size={16} /> {loading ? "Refreshing…" : "Refresh"}
            </button>
          ) : null
        }
      />

      <section className="card report-filter no-print">
        <div className="report-filter-fields">
          <div className="field">
            <label htmlFor="my-sales-day">Select date</label>
            <input
              id="my-sales-day"
              type="date"
              value={day}
              onChange={(event) => chooseDay(event.target.value)}
            />
          </div>
          <button className="primary" type="button" onClick={() => load(true)} disabled={!day || loading}>
            <Icon name="search" size={16} /> {loading ? "Loading…" : "Show sales"}
          </button>
          <button className="ghost" type="button" onClick={showToday} disabled={loading}>
            <Icon name="receipt" size={16} /> Today
          </button>
        </div>
        <p className="small report-range">
          {day ? `Selected: ${formatDay(day)}` : "Select a date, then choose Show sales."}
        </p>
      </section>

      {error && <div className="alert error">{error}</div>}

      {!hasSearched ? (
        <section className="card">
          <div className="empty-state">
            <div className="empty-icon"><Icon name="receipt" size={24} /></div>
            <h4>{loading ? "Loading sales…" : "Select a date to view your sales"}</h4>
            <p>
              {loading
                ? "Fetching your orders for the selected day."
                : "Choose a day above, then select Show sales. Nothing is loaded automatically."}
            </p>
          </div>
        </section>
      ) : (
        <>
          <div className="mini-stats">
            <div className="mini-stat"><span>Receipts</span><strong>{sales.length}</strong></div>
            <div className="mini-stat"><span>Awaiting approval</span><strong>{awaiting}</strong></div>
            <div className="mini-stat"><span>Paid</span><strong>{paid}</strong></div>
            <div className="mini-stat"><span>Paid total</span><strong>{money(paidTotal)}</strong></div>
          </div>

          {paying && (
            <div className="modal">
              <div className="modal-box payment-modal">
                <PaymentPanel sale={paying} onPaid={(s) => { setPaying(null); setReceiptId(s.id); load(false); }} />
                <button className="ghost full" type="button" onClick={() => setPaying(null)}>Close</button>
              </div>
            </div>
          )}
          {receiptId && <Receipt saleId={receiptId} onClose={() => setReceiptId(null)} />}

          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Receipt</th><th>Time</th><th>Items</th><th className="right">Total</th><th>Status</th><th className="right">Actions</th></tr></thead>
              <tbody>
                {visibleSales.map((s) => (
                  <tr key={s.id}>
                    <td className="mono">{s.receipt_no}</td>
                    <td>{new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
                    <td className="cell-summary">{s.items.map((i) => `${i.product_name} ×${i.quantity}`).join(", ")}</td>
                    <td className="right"><strong>{money(s.total)}</strong></td>
                    <td>
                      <span className={`pill ${STATUS_CLASS[s.status] || "muted"}`}>{STATUS_LABEL[s.status] || s.status}</span>
                      {s.approval?.decision_note && <div className="small table-note">{s.approval.decision_note}</div>}
                    </td>
                    <td className="row actions-cell">
                      {(s.status === "READY" || s.status === "APPROVED") && (
                        <button className="primary small-button" type="button" onClick={() => setPaying(s)}>Checkout</button>
                      )}
                      {s.status === "PAID" && (
                        <button className="ghost small-button" type="button" onClick={() => setReceiptId(s.id)}>
                          <Icon name="receipt" size={15} /> Receipt
                        </button>
                      )}
                      {["READY", "PENDING_APPROVAL", "APPROVED"].includes(s.status) && (
                        <button className="ghost small-button" type="button" onClick={() => cancel(s.id)}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
                {visibleSales.length === 0 && (
                  <tr>
                    <td colSpan="6">
                      <div className="empty-state">
                        <div className="empty-icon"><Icon name="receipt" size={24} /></div>
                        <h4>{loading ? "Loading sales…" : "No sales on this day"}</h4>
                        <p>{loading ? "Fetching your orders." : "Try another date."}</p>
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
        </>
      )}
    </div>
  );
}
