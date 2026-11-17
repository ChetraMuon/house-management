import { useCallback, useEffect, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "./Icon.jsx";
import PaywayQr from "./PaywayQr.jsx";

const METHODS = [
  { value: "CASH", label: "Cash" },
  { value: "CARD", label: "Card" },
];

const TRANSFER_METHOD = { value: "TRANSFER", label: "Transfer" };
const MANUAL_TRANSFER_METHOD = { value: "MANUAL_TRANSFER", label: "Manual transfer" };

/**
 * Payment panel for one sale. Cash calculates change, card/manual transfer
 * record a terminal payment, and an enabled ABA PayWay transfer shows a
 * dynamic KHQR that is confirmed automatically.
 */
export default function PaymentPanel({ sale, onPaid }) {
  const [method, setMethod] = useState("CASH");
  const [received, setReceived] = useState("");
  const [calc, setCalc] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [paywayEnabled, setPaywayEnabled] = useState(false);
  const [paywaySandbox, setPaywaySandbox] = useState(false);
  const [paywayPending, setPaywayPending] = useState(false);

  useEffect(() => {
    api.get("/payments/config")
      .then(({ data }) => {
        setPaywayEnabled(!!data.payway_enabled);
        setPaywaySandbox(!!data.sandbox);
      })
      .catch(() => {});
  }, []);

  const handlePendingChange = useCallback((value) => setPaywayPending(value), []);
  const methods = paywayEnabled
    ? [...METHODS, { ...TRANSFER_METHOD, label: "Transfer (ABA QR)" }, MANUAL_TRANSFER_METHOD]
    : [...METHODS, TRANSFER_METHOD];
  const transferUsesPayway = method === "TRANSFER" && paywayEnabled;

  const total = Number(sale.total);
  const num = Number(received);
  const cashEntered = received !== "" && Number.isFinite(num);
  const short = method === "CASH" && cashEntered && num < total;
  const canPay = method !== "CASH" || (cashEntered && num >= total);

  // ask the server for change + denomination breakdown whenever the amount changes
  useEffect(() => {
    setCalc(null);
    if (method !== "CASH" || !cashEntered || num < total) return;
    const t = setTimeout(() => {
      api.post("/sales/change", { total, received: num }).then((r) => setCalc(r.data)).catch(() => {});
    }, 150);
    return () => clearTimeout(t);
  }, [received, method, total]);

  const quick = [total, Math.ceil(total / 10) * 10, Math.ceil(total / 50) * 50, Math.ceil(total / 100) * 100];

  const pay = async () => {
    setError("");
    if (!canPay) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/sales/${sale.id}/checkout`, {
        method: method === "MANUAL_TRANSFER" ? "TRANSFER" : method,
        amount_received: method === "CASH" ? num : total,
      });
      onPaid(data);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card payment-card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Payment</span>
          <h3>Take payment</h3>
        </div>
        <span className="pill info">{sale.receipt_no}</span>
      </div>

      <div className="amount-due">
        <span>Amount due</span>
        <strong>{money(sale.total)}</strong>
      </div>

      <div className="field">
        <label>Payment method</label>
        <div
          className={`segmented${methods.length === 4 ? " methods-four" : ""}`}
          role="group"
          aria-label="Payment method"
        >
          {methods.map((item) => (
            <button
              key={item.value}
              type="button"
              className={method === item.value ? "active" : ""}
              onClick={() => { setMethod(item.value); setError(""); }}
              aria-pressed={method === item.value}
              disabled={paywayPending}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {method === "CASH" ? (
        <>
          <div className="field">
            <label htmlFor="money-received">Money received from customer</label>
            <div className="money-input">
              <span>$</span>
              <input
                id="money-received"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                autoFocus
                value={received}
                onChange={(e) => setReceived(e.target.value)}
                placeholder="0.00"
              />
            </div>
          </div>

          <div className="quick-cash">
            {[...new Set(quick)].map((v) => (
              <button key={v} type="button" onClick={() => setReceived(String(v))}>
                {money(v)}
              </button>
            ))}
            <button type="button" className="ghost" onClick={() => setReceived("")}>
              Clear
            </button>
          </div>

          {short && <div className="alert error">Short by {money(total - num)}</div>}

          {calc && (
            <div className="change-box">
              <div className="change-head">
                <span>Change to give back</span>
                <Icon name="check" size={16} />
              </div>
              <div className="change-amount">{money(calc.change)}</div>
              {calc.breakdown.length > 0 && (
                <div className="change-breakdown">
                  {calc.breakdown.map((b) => (
                    <span key={b.denomination}>
                      {b.count} × ${b.denomination}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      ) : transferUsesPayway ? (
        <PaywayQr sale={sale} onPaid={onPaid} onPendingChange={handlePendingChange} sandbox={paywaySandbox} />
      ) : (
        <div className="payment-note">
          <Icon name={method === "CARD" ? "wallet" : "banknote"} size={18} />
          <p>
            Charge <strong>{money(sale.total)}</strong> on the {method === "CARD" ? "card terminal" : "bank transfer"}.
            The payment will be recorded as paid in full.
          </p>
        </div>
      )}

      {error && <div className="alert error">{error}</div>}

      {!transferUsesPayway && (
        <button className="primary full" type="button" disabled={busy || !canPay} onClick={pay}>
          {busy ? "Processing…" : "Complete payment"}
        </button>
      )}
    </div>
  );
}
