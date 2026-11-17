import { useEffect, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const CUSTOMER_PAGE_SIZE = 10;
const HISTORY_PAGE_SIZE = 20;

const STATUS_CLASS = {
  PAID: "ok",
  READY: "info",
  APPROVED: "ok",
  PENDING_APPROVAL: "warn",
  REJECTED: "error",
  CANCELLED: "muted",
};

const STATUS_LABEL = {
  PAID: "Paid",
  READY: "Ready",
  APPROVED: "Approved",
  PENDING_APPROVAL: "Awaiting approval",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

function initials(name) {
  return (name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [customerPage, setCustomerPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [expandedSaleId, setExpandedSaleId] = useState(null);

  const filteredCustomers = customers.filter((customer) => {
    const needle = search.trim().toLowerCase();
    if (!needle) return true;
    return (customer.full_name || "").toLowerCase().includes(needle) || (customer.phone || "").includes(needle);
  });

  const totalPages = Math.max(1, Math.ceil(filteredCustomers.length / CUSTOMER_PAGE_SIZE));
  const visibleCustomers = filteredCustomers.slice((customerPage - 1) * CUSTOMER_PAGE_SIZE, customerPage * CUSTOMER_PAGE_SIZE);

  const loadCustomers = async () => {
    setError("");
    setListLoading(true);
    try {
      const { data } = await api.get("/customers");
      setCustomers(data);
      setCustomerPage(1);
      setHistoryPage(1);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    loadCustomers();
  }, []);

  const openCustomer = async (customerId) => {
    setSelectedId(customerId);
    setExpandedSaleId(null);
    setLoading(true);
    setError("");

    try {
      const r = await api.get(`/customers/${customerId}/history`);
      setHistory(r.data);
      setHistoryPage(1);
    } catch (e) {
      setError(errMsg(e));
      setHistory(null);
    } finally {
      setLoading(false);
    }
  };

  const normalizedPurchases = history
    ? [...history.purchases].filter((sale, index, arr) => arr.findIndex((item) => item.receipt_no === sale.receipt_no) === index)
    : [];
  const purchasePage = history ? Math.max(1, Math.ceil(normalizedPurchases.length / HISTORY_PAGE_SIZE)) : 1;
  const visiblePurchases = history ? normalizedPurchases.slice((historyPage - 1) * HISTORY_PAGE_SIZE, historyPage * HISTORY_PAGE_SIZE) : [];
  const selectedCustomer = customers.find((customer) => customer.id === selectedId) || null;

  return (
    <div className="page customer-shell">
      <PageHeader
        eyebrow="Operations"
        title="Customers"
        subtitle="Look up a customer and review everything they have bought."
        actions={
          <div className="row page-actions-row">
            <span className="pill info">{customers.length} total</span>
            <button className="ghost" type="button" onClick={loadCustomers} disabled={listLoading}>
              <Icon name="refresh" size={16} /> {listLoading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error && <div className="alert error">{error}</div>}

      <div className="customer-layout">
        <section className="card customer-card">
          <div className="section-head">
            <div>
              <h3>Customer list</h3>
              <p className="small">Search by name or phone number.</p>
            </div>
            <span className="pill muted">{filteredCustomers.length} shown</span>
          </div>

          <div className="search-field">
            <Icon name="search" size={17} />
            <input
              placeholder="Search customers…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCustomerPage(1);
              }}
            />
          </div>

          <div className="table-wrap flush">
            <table className="table customer-table">
              <thead>
                <tr><th>Customer</th><th>Phone</th><th>Since</th><th className="right">Actions</th></tr>
              </thead>
              <tbody>
                {visibleCustomers.map((customer) => (
                  <tr key={customer.id} className={selectedId === customer.id ? "row-selected" : ""}>
                    <td>
                      <div className="person-cell">
                        <div className="avatar avatar-sm">{initials(customer.full_name)}</div>
                        <strong>{customer.full_name || "Unnamed customer"}</strong>
                      </div>
                    </td>
                    <td className="mono">{customer.phone}</td>
                    <td className="nowrap">{new Date(customer.created_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className={`small-button ${selectedId === customer.id ? "primary" : "ghost"}`}
                        type="button"
                        onClick={() => openCustomer(customer.id)}
                      >
                        {selectedId === customer.id ? "Viewing" : "Detail"}
                      </button>
                    </td>
                  </tr>
                ))}
                {visibleCustomers.length === 0 && (
                  <tr>
                    <td colSpan="4">
                      <div className="empty-state">
                        <div className="empty-icon"><Icon name="customers" size={24} /></div>
                        <h4>{search ? "No matching customers" : "No customers yet"}</h4>
                        <p>{search ? "Try a different name or phone number." : "Customers are created automatically at checkout."}</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <PaginationControls
            page={customerPage}
            totalPages={totalPages}
            onPrev={() => setCustomerPage((p) => Math.max(1, p - 1))}
            onNext={() => setCustomerPage((p) => Math.min(totalPages, p + 1))}
          />
        </section>

        <section className="card customer-detail-card">
          <div className="section-head">
            <div>
              <h3>Purchase history</h3>
              <p className="small">Select a customer to see their receipts.</p>
            </div>
            {history && <span className="pill muted">{normalizedPurchases.length} receipts</span>}
          </div>

          {loading && (
            <div className="empty-state">
              <div className="empty-icon"><Icon name="refresh" size={24} /></div>
              <h4>Loading history…</h4>
              <p>Fetching this customer’s receipts.</p>
            </div>
          )}

          {!loading && !history && !selectedCustomer && (
            <div className="empty-state">
              <div className="empty-icon"><Icon name="customers" size={24} /></div>
              <h4>No customer selected</h4>
              <p>Choose someone from the list to review their purchase history.</p>
            </div>
          )}

          {!loading && history && (
            <>
              <div className="customer-summary">
                <div className="person-cell">
                  <div className="avatar avatar-lg">{initials(history.customer.full_name)}</div>
                  <div>
                    <div className="small">Customer</div>
                    <div className="customer-name big-name">{history.customer.full_name || "Unnamed customer"}</div>
                    <div className="small mono">{history.customer.phone}</div>
                  </div>
                </div>

                <div className="customer-meta">
                  <div className="meta-card">
                    <span>Total spent</span>
                    <strong>{money(history.total_spent)}</strong>
                  </div>
                  <div className="meta-card">
                    <span>Orders</span>
                    <strong>{normalizedPurchases.length}</strong>
                  </div>
                  <div className="meta-card">
                    <span>Customer since</span>
                    <strong>{new Date(history.customer.created_at).toLocaleDateString()}</strong>
                  </div>
                </div>
              </div>

              <div className="detail-history-header">
                <h4>Receipt history</h4>
                <span className="small">Page {historyPage} of {purchasePage}</span>
              </div>

              <div className="details-list">
                {visiblePurchases.length === 0 && (
                  <div className="empty-state">
                    <div className="empty-icon"><Icon name="receipt" size={24} /></div>
                    <h4>No purchases yet</h4>
                    <p>This customer has no receipts on record.</p>
                  </div>
                )}

                {visiblePurchases.map((sale) => (
                  <div key={sale.id} className={`detail-box ${expandedSaleId === sale.id ? "expanded" : ""}`}>
                    <div className="detail-head">
                      <div>
                        <div className="row detail-title-row">
                          <strong className="mono">{sale.receipt_no}</strong>
                          <span className={`pill ${STATUS_CLASS[sale.status] || "muted"}`}>
                            {STATUS_LABEL[sale.status] || sale.status}
                          </span>
                        </div>
                        <div className="small">{new Date(sale.created_at).toLocaleString()}</div>
                      </div>
                      <div className="row detail-actions">
                        <div className="detail-amount">
                          <strong>{money(sale.total)}</strong>
                          {Number(sale.discount) > 0 && (
                            <span className="small discount-note">−{money(sale.discount)} discount</span>
                          )}
                        </div>
                        <button
                          className="ghost small-button"
                          type="button"
                          onClick={() => setExpandedSaleId((prev) => (prev === sale.id ? null : sale.id))}
                        >
                          {expandedSaleId === sale.id ? "Hide detail" : "Detail"}
                        </button>
                      </div>
                    </div>

                    {expandedSaleId === sale.id && (
                      <div className="detail-body">
                        {sale.items.length === 0 ? (
                          <p className="small">No product detail available.</p>
                        ) : (
                          <ul className="purchase-items">
                            {sale.items.map((item) => (
                              <li key={item.id}>
                                <div>
                                  <strong>{item.product_name}</strong>
                                  <span className="small">{item.quantity} × {money(item.unit_price)}</span>
                                </div>
                                <strong>{money(item.line_total)}</strong>
                              </li>
                            ))}
                          </ul>
                        )}

                        <div className="purchase-totals">
                          <div><span>Subtotal</span><span>{money(sale.subtotal)}</span></div>
                          <div className={Number(sale.discount) > 0 ? "discount-row" : ""}>
                            <span>Discount</span>
                            <span>{Number(sale.discount) > 0 ? `−${money(sale.discount)}` : money(0)}</span>
                          </div>
                          <div className="total-row"><span>Total</span><span>{money(sale.total)}</span></div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <PaginationControls
                page={historyPage}
                totalPages={purchasePage}
                onPrev={() => setHistoryPage((p) => Math.max(1, p - 1))}
                onNext={() => setHistoryPage((p) => Math.min(purchasePage, p + 1))}
              />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
