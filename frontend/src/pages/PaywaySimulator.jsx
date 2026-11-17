import { useCallback, useEffect, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import QrScanner from "../components/QrScanner.jsx";
import Receipt from "../components/Receipt.jsx";

const REFRESH_MS = 5000;

const clock = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
};

const secondsLeft = (expiresAt, now) => {
  if (!expiresAt) return null;
  return Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
};

/**
 * Sandbox-only test payer for ABA PayWay. Marks a pending test QR as paid in
 * the POS without moving real money. The backend refuses to run this page
 * when PayWay is configured for production.
 */
export default function PaywaySimulator() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [receiptId, setReceiptId] = useState(null);
  const [lastReceipt, setLastReceipt] = useState(null);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const { data } = await api.get("/payway-simulator/pending");
      setRows(data);
      setError("");
    } catch (e) {
      setError(errMsg(e));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(() => load(true), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const pay = async (sale) => {
    setBusyId(sale.sale_id);
    setError("");
    try {
      const { data } = await api.post(`/payway-simulator/${sale.sale_id}/pay`);
      setNotice(`${data.message} Receipt ${sale.receipt_no} is now ${data.sale_status}.`);
      setConfirming(null);
      setLastReceipt(sale);
      setReceiptId(sale.sale_id);
      load(true);
    } catch (e) {
      // A flaky tunnel can drop the response after the backend has already
      // committed the simulated payment. Re-check before showing an error.
      try {
        const { data } = await api.get(`/sales/${sale.sale_id}`);
        if (data.status === "PAID") {
          setNotice(`Simulated payment approved. Receipt ${sale.receipt_no} is now PAID.`);
          setConfirming(null);
          setLastReceipt(sale);
          setReceiptId(sale.sale_id);
          load(true);
          return;
        }
      } catch {
        // Fall through to the original error.
      }
      setError(errMsg(e));
    } finally {
      setBusyId(null);
    }
  };

  const scan = async (code) => {
    setScanBusy(true);
    setError("");
    setNotice("");
    setReceiptId(null);
    try {
      const { data } = await api.post("/payway-simulator/scan", { code });
      setConfirming(data);
    } catch (e) {
      setConfirming(null);
      setError(errMsg(e));
    } finally {
      setScanBusy(false);
    }
  };

  const pendingTotal = rows.reduce((sum, row) => sum + Number(row.total || 0), 0);
  const stage = receiptId ? 4 : confirming ? 2 : rows.length ? 1 : 0;
  const steps = [
    { title: "Payment request", note: "Your app creates the QR" },
    { title: "Scan QR code", note: "Camera reads the POS screen" },
    { title: "ABA Simulator", note: "Approve the test payment" },
    { title: "Payment result", note: "POS marks the sale paid" },
  ];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Sandbox tools"
        title="ABA Simulator"
        subtitle="Scan the QR shown on checkout, approve the test payment, and the result returns to the POS."
        actions={
          <div className="row page-actions-row no-print">
            <button
              className="ghost"
              type="button"
              onClick={() => load()}
              disabled={loading}
            >
              <Icon name="refresh" size={16} /> {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      <ol className="payway-steps" aria-label="ABA test payment flow">
        {steps.map((step, index) => (
          <li
            key={step.title}
            className={
              index < stage ? "done" : index === stage ? "active" : ""
            }
          >
            <span className="payway-step-number">
              {index < stage ? <Icon name="check" size={14} /> : index + 1}
            </span>
            <div>
              <strong>{step.title}</strong>
              <small>{step.note}</small>
            </div>
          </li>
        ))}
      </ol>

      <div className="alert warn">
        <Icon name="warning" size={18} />
        <span>
          <strong>Simulated payments only.</strong> This marks the pending QR as paid
          inside this POS. No real money moves and no ABA account is charged. The live
          ABA Mobile app cannot pay sandbox QR codes.
        </span>
      </div>

      <div className="alert info compact-alert">
        <Icon name="key" size={16} />
        <span>
          This page is manager/admin-only and disappears automatically when PayWay is
          pointed at the production environment.
        </span>
      </div>

      {error && (
        <div className="alert error">
          <Icon name="warning" size={16} />
          <span>{error}</span>
        </div>
      )}

      {notice && (
        <div className="alert ok">
          <Icon name="check" size={16} />
          <span>
            {notice}{" "}
            <button
              className="link-button"
              type="button"
              onClick={() => setReceiptId(lastReceipt.sale_id)}
              disabled={!lastReceipt}
            >
              View receipt
            </button>
          </span>
        </div>
      )}

      <div className="card simulator-scan-card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Step 2 of 4</span>
            <h3>Scan the QR code</h3>
            <p className="small">
              Open this page on a phone, then scan the QR on the checkout screen. On
              iPhone, allow camera access when Safari asks. If the camera is blocked,
              upload a photo or type the reference.
            </p>
          </div>
          <span className="pill info">Sandbox</span>
        </div>
        <QrScanner onScan={scan} disabled={scanBusy} />
        {scanBusy && (
          <div className="qr-wait">
            <span className="spinner" />
            <span>Looking up the payment request…</span>
          </div>
        )}
      </div>

      <div className="simulator-summary">
        <div className="simulator-stat">
          <span>Pending test QRs</span>
          <strong>{rows.length}</strong>
        </div>
        <div className="simulator-stat">
          <span>Pending value</span>
          <strong>{money(pendingTotal)}</strong>
        </div>
        <div className="simulator-stat">
          <span>Environment</span>
          <strong className="simulator-env">Sandbox</strong>
        </div>
      </div>

      {confirming && (
        <div className="card simulator-confirm">
          <div className="section-head">
            <div>
              <span className="eyebrow">Step 3 of 4 · ABA Simulator</span>
              <h3>Approve {confirming.receipt_no}?</h3>
              <p className="small">
                This creates the sandbox payment approval and finishes the normal
                receipt flow.
              </p>
            </div>
            <span className="pill warn">Test only</span>
          </div>

          <div className="simulator-details">
            <div>
              <span>Amount</span>
              <strong>{money(confirming.total)}</strong>
            </div>
            <div>
              <span>Customer</span>
              <strong>{confirming.customer_name || "Walk-in"}</strong>
            </div>
            <div>
              <span>Cashier</span>
              <strong>{confirming.cashier_name}</strong>
            </div>
            <div>
              <span>Transaction</span>
              <strong className="mono">{confirming.tran_id}</strong>
            </div>
          </div>

          {confirming.expired ? (
            <div className="alert error compact-alert">
              <Icon name="warning" size={16} />
              <span>
                This QR has expired. Ask the cashier to refresh the QR on the checkout
                screen, then scan the new code.
              </span>
            </div>
          ) : (
            <div className="alert warn compact-alert">
              <Icon name="warning" size={16} />
              <span>No money will be collected. This is a sandbox test approval.</span>
            </div>
          )}

          <div className="row form-actions">
            <button
              className="primary"
              type="button"
              onClick={() => pay(confirming)}
              disabled={busyId === confirming.sale_id || confirming.expired}
            >
              <Icon name="check" size={16} />
              {busyId === confirming.sale_id
                ? "Approving…"
                : `Approve ${money(confirming.total)} test payment`}
            </button>
            <button
              className="ghost"
              type="button"
              onClick={() => setConfirming(null)}
              disabled={busyId === confirming.sale_id}
            >
              Scan another
            </button>
          </div>
        </div>
      )}

      <div className="section-head simulator-list-head">
        <div>
          <span className="eyebrow">Fallback</span>
          <h3>Pending test QRs</h3>
          <p className="small">
            Use this list if the camera is unavailable, or pick a payment directly.
          </p>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table simulator-table">
          <thead>
            <tr>
              <th>Receipt</th>
              <th>Customer</th>
              <th>Cashier</th>
              <th className="right">Amount</th>
              <th>Reference</th>
              <th>Expires</th>
              <th className="right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((sale) => {
              const left = secondsLeft(sale.expires_at, now);
              const expired = sale.expired || left === 0;
              return (
                <tr key={sale.sale_id} className={expired ? "row-muted" : ""}>
                  <td>
                    <strong className="mono">{sale.receipt_no}</strong>
                    <div className="small table-note muted-text">
                      {new Date(sale.created_at).toLocaleString()}
                    </div>
                  </td>
                  <td>
                    {sale.customer_name || <span className="muted-text">Walk-in</span>}
                    {sale.customer_phone && (
                      <div className="small table-note mono">{sale.customer_phone}</div>
                    )}
                  </td>
                  <td>{sale.cashier_name}</td>
                  <td className="right">
                    <strong>{money(sale.total)}</strong>
                    <div className="small table-note">{sale.currency}</div>
                  </td>
                  <td className="mono">{sale.tran_id}</td>
                  <td>
                    {expired ? (
                      <span className="pill error">Expired</span>
                    ) : (
                      <span className="pill warn simulator-countdown">
                        {left == null ? "No expiry" : clock(left)}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="row actions-cell">
                      <button
                        className="primary small-button"
                        type="button"
                        disabled={expired || busyId === sale.sale_id}
                        onClick={() => {
                          setNotice("");
                          setError("");
                          setNotice("");
                          setReceiptId(null);
                          setConfirming(sale);
                        }}
                      >
                        <Icon name="check" size={14} />
                        {busyId === sale.sale_id ? "Approving…" : "Simulate payment"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={7}>
                  <div className="empty-state">
                    <div className="empty-icon ok">
                      <Icon name="qr" size={24} />
                    </div>
                    <h4>No pending sandbox QRs</h4>
                    <p>
                      Create a sale and choose Transfer (ABA QR) on the checkout screen.
                      Pending test payments will appear here.
                    </p>
                  </div>
                </td>
              </tr>
            )}
            {loading && rows.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <div className="empty-state inline">
                    <span className="spinner" />
                    <p>Loading pending sandbox QRs…</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {receiptId && <Receipt saleId={receiptId} onClose={() => setReceiptId(null)} />}
    </div>
  );
}
