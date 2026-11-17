import { useEffect, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "./Icon.jsx";

/** Loads receipt data for a paid sale and prints it (only .receipt is visible in print CSS). */
export default function Receipt({ saleId, onClose }) {
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/sales/${saleId}/receipt`).then((x) => setR(x.data)).catch((e) => setErr(errMsg(e)));
  }, [saleId]);

  if (err) {
    return (
      <div className="modal">
        <div className="modal-box small-modal">
          <div className="alert error">{err}</div>
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    );
  }
  if (!r) {
    return (
      <div className="modal">
        <div className="modal-box small-modal">
          <p className="small">Loading receipt…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="modal">
      <div className="modal-box receipt-box">
        <div className="receipt" id="receipt">
          <div className="receipt-brand-row">
            <div className="logo-mark">
              <Icon name="home" size={18} />
            </div>
            <div>
              <h3>House Store</h3>
              <span>Sales receipt</span>
            </div>
          </div>

          <div className="receipt-meta">
            <div><span>Receipt</span><strong>{r.receipt_no}</strong></div>
            <div><span>Date</span><strong>{new Date(r.date).toLocaleString()}</strong></div>
            <div><span>Cashier</span><strong>{r.cashier}</strong></div>
            {r.customer_name && <div><span>Customer</span><strong>{r.customer_name}</strong></div>}
          </div>

          <hr />
          <table className="receipt-items">
            <tbody>
              {r.items.map((i, idx) => (
                <tr key={idx}>
                  <td>
                    {i.name}
                    <span className="receipt-line-note">{i.qty} × {money(i.unit_price)}</span>
                  </td>
                  <td className="right">{money(i.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <hr />

          <div className="receipt-totals">
            <div><span>Subtotal</span><span>{money(r.subtotal)}</span></div>
            {Number(r.discount) > 0 && <div><span>Discount</span><span>-{money(r.discount)}</span></div>}
            <div className="receipt-grand-total"><span>TOTAL</span><strong>{money(r.total)}</strong></div>
          </div>

          <div className="receipt-payment">
            <div>
              <span>Paid ({r.payment_provider === "PAYWAY" ? "QR / ABA Pay" : r.payment_method})</span>
              <span>{money(r.amount_received)}</span>
            </div>
            {r.payment_reference && (
              <div><span>Reference</span><span className="mono">{r.payment_reference}</span></div>
            )}
            <div><span>Change</span><span>{money(r.change)}</span></div>
          </div>

          {r.change_breakdown?.length > 0 && (
            <div className="receipt-breakdown">
              <span>Change breakdown</span>
              <div>
                {r.change_breakdown.map((b) => (
                  <em key={b.denomination}>{b.count} × ${b.denomination}</em>
                ))}
              </div>
            </div>
          )}

          <p className="receipt-thanks">Thank you for shopping with us.</p>
          <p className="receipt-fineprint">Please keep this receipt for your records.</p>
        </div>

        <div className="row no-print receipt-actions">
          <button className="primary" type="button" onClick={() => window.print()}>
            <Icon name="receipt" size={16} /> Print receipt
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
