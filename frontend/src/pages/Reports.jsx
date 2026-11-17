import { useState } from "react";
import api, { errMsg, money } from "../api";
import { useAuth } from "../auth.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";

const localDate = (value = new Date()) =>
  new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const PAYMENT_LABEL = { CASH: "Cash", CARD: "Card", TRANSFER: "Transfer" };

export default function Reports() {
  const { user } = useAuth();
  const staff = user.role !== "emp";
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState(null);
  const [stock, setStock] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);

  const loadStock = () => {
    if (!staff) return;
    setStock(null);
    api.get("/reports/stock").then((r) => setStock(r.data)).catch(() => {});
  };

  const fetchSales = async (from, to) => {
    setError("");
    setData(null);
    setLoading(true);
    try {
      const { data: report } = await api.get("/reports/sales", { params: { start: from, end: to } });
      setData(report);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setLoading(false);
    }
  };

  const run = () => {
    if (!start || !end) {
      setError("Select both a From and To date.");
      return;
    }
    if (start > end) {
      setError("The From date must be on or before the To date.");
      return;
    }
    fetchSales(start, end);
    loadStock();
  };

  const changeStart = (value) => {
    setStart(value);
    setData(null);
    setStock(null);
    setError("");
  };

  const changeEnd = (value) => {
    setEnd(value);
    setData(null);
    setStock(null);
    setError("");
  };

  const showToday = () => {
    const day = localDate();
    setStart(day);
    setEnd(day);
    setData(null);
    setStock(null);
    setError("");
  };

  const downloadCsv = async () => {
    if (csvBusy || !data) return;
    setError("");
    setCsvBusy(true);
    try {
      const r = await api.get("/reports/sales.csv", { params: { start, end }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sales_${start}_${end}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setCsvBusy(false);
    }
  };

  const printReport = () => {
    if (!data) return;
    document.body.classList.add("print-report");
    window.print();
    document.body.classList.remove("print-report");
  };

  return (
    <div className="page report-page">
      <PageHeader
        eyebrow="Insights"
        title="Reports"
        subtitle={staff ? "Choose a date range to generate sales, payment, and stock reports." : "Choose a date range to generate your own sales report."}
        actions={
          <div className="row page-actions-row no-print">
            <button className="ghost" type="button" onClick={downloadCsv} disabled={csvBusy || !data}>
              <Icon name="receipt" size={16} /> {csvBusy ? "Preparing…" : "Export CSV"}
            </button>
            <button className="ghost" type="button" onClick={printReport} disabled={!data}>
              <Icon name="reports" size={16} /> Print
            </button>
          </div>
        }
      />

      {!staff && (
        <div className="alert info">This report only includes sales you processed.</div>
      )}

      <section className="card report-filter no-print">
        <div className="report-filter-fields">
          <div className="field">
            <label htmlFor="report-start">From</label>
            <input id="report-start" type="date" value={start} onChange={(e) => changeStart(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="report-end">To</label>
            <input id="report-end" type="date" value={end} onChange={(e) => changeEnd(e.target.value)} />
          </div>
          <button className="primary" type="button" onClick={run} disabled={loading || !start || !end}>
            {loading ? "Generating…" : "Generate report"}
          </button>
          <button className="ghost" type="button" onClick={showToday} disabled={loading}>
            <Icon name="refresh" size={15} /> Today
          </button>
        </div>
        <p className="small report-range">
          {data ? `Showing ${data.start} to ${data.end}` : "Choose a date range, then select Generate report."}
        </p>
      </section>

      {error && <div className="alert error">{error}</div>}

      {!data && (
        <section className="card">
          <div className="empty-state">
            <div className="empty-icon"><Icon name="reports" size={24} /></div>
            <h4>{loading ? "Generating report…" : "Select a date range"}</h4>
            <p>
              {loading
                ? "Fetching sales for the selected dates."
                : "Choose From and To dates, then select Generate report. No sales data is shown automatically."}
            </p>
          </div>
        </section>
      )}

      {data && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-icon"><Icon name="receipt" size={19} /></div>
              <span>Paid sales</span>
              <strong>{data.sales_count}</strong>
            </div>
            <div className="stat-card">
              <div className="stat-icon accent"><Icon name="wallet" size={19} /></div>
              <span>Revenue</span>
              <strong>{money(data.revenue)}</strong>
            </div>
            <div className="stat-card">
              <div className="stat-icon"><Icon name="tag" size={19} /></div>
              <span>Discounts given</span>
              <strong>{money(data.discount)}</strong>
            </div>
            <div className="stat-card">
              <div className="stat-icon"><Icon name="banknote" size={19} /></div>
              <span>Cash received</span>
              <strong>{money(data.cash_received)}</strong>
            </div>
            <div className="stat-card">
              <div className="stat-icon"><Icon name="rotate" size={19} /></div>
              <span>Change given</span>
              <strong>{money(data.cash_change_given)}</strong>
            </div>
            <div className="stat-card">
              <div className="stat-icon accent"><Icon name="banknote" size={19} /></div>
              <span>Cash in drawer</span>
              <strong>{money(data.cash_net)}</strong>
            </div>
          </div>

          <div className="report-grid">
            <section className="card">
              <div className="section-head">
                <div>
                  <h3>Payment methods</h3>
                  <p className="small">How customers paid during this range.</p>
                </div>
              </div>
              <div className="table-wrap flush">
                <table className="table compact">
                  <thead><tr><th>Method</th><th className="right">Count</th><th className="right">Amount</th></tr></thead>
                  <tbody>
                    {data.by_method.map((m) => (
                      <tr key={m.method}>
                        <td><span className="pill info">{PAYMENT_LABEL[m.method] || m.method}</span></td>
                        <td className="right">{m.count}</td>
                        <td className="right"><strong>{money(m.amount)}</strong></td>
                      </tr>
                    ))}
                    {data.by_method.length === 0 && (
                      <tr><td colSpan="3" className="muted-text center">No payments in this range.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="section-head stacked-top">
                <div>
                  <h3>Per day</h3>
                  <p className="small">Daily totals for the selected range.</p>
                </div>
              </div>
              <div className="table-wrap flush">
                <table className="table compact">
                  <thead><tr><th>Date</th><th className="right">Sales</th><th className="right">Amount</th></tr></thead>
                  <tbody>
                    {data.per_day.map((d) => (
                      <tr key={d.date}>
                        <td>{new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</td>
                        <td className="right">{d.count}</td>
                        <td className="right"><strong>{money(d.amount)}</strong></td>
                      </tr>
                    ))}
                    {data.per_day.length === 0 && (
                      <tr><td colSpan="3" className="muted-text center">No sales in this range.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card">
              <div className="section-head">
                <div>
                  <h3>Products sold</h3>
                  <p className="small">Ranked by revenue contribution.</p>
                </div>
                <span className="pill muted">{data.products.length}</span>
              </div>
              <div className="table-wrap flush">
                <table className="table compact">
                  <thead><tr><th>Product</th><th className="right">Qty</th><th className="right">Amount</th></tr></thead>
                  <tbody>
                    {data.products.map((p) => (
                      <tr key={p.name}>
                        <td><strong>{p.name}</strong></td>
                        <td className="right">{p.qty}</td>
                        <td className="right">{money(p.amount)}</td>
                      </tr>
                    ))}
                    {data.products.length === 0 && (
                      <tr><td colSpan="3" className="muted-text center">Nothing sold in this range.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </>
      )}

      {staff && stock && (
        <>
          <div className="section-head page-section-head">
            <div>
              <span className="eyebrow">Inventory</span>
              <h2>Stock summary</h2>
            </div>
          </div>

          <div className="stat-grid four">
            <div className="stat-card"><span>Products</span><strong>{stock.total_items}</strong></div>
            <div className="stat-card"><span>Units</span><strong>{stock.total_units}</strong></div>
            <div className="stat-card"><span>Cost value</span><strong>{money(stock.total_cost_value)}</strong></div>
            <div className="stat-card"><span>Retail value</span><strong>{money(stock.total_retail_value)}</strong></div>
          </div>

          {stock.low_stock.length > 0 ? (
            <section className="card low-stock-card">
              <div className="section-head">
                <div className="row">
                  <div className="empty-icon warn small"><Icon name="warning" size={18} /></div>
                  <div>
                    <h3>Low stock</h3>
                    <p className="small">These products have reached their minimum level.</p>
                  </div>
                </div>
                <span className="pill warn">{stock.low_stock.length}</span>
              </div>
              <div className="low-stock-list">
                {stock.low_stock.map((p) => (
                  <span className="low-stock-item" key={p.id}>
                    <strong>{p.name}</strong>
                    <span>{p.sku} · {p.stock_qty} left</span>
                  </span>
                ))}
              </div>
            </section>
          ) : (
            <div className="alert ok">Every product is above its low-stock threshold.</div>
          )}
        </>
      )}
    </div>
  );
}
