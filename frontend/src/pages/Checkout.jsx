import { useEffect, useMemo, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaymentPanel from "../components/PaymentPanel.jsx";
import Receipt from "../components/Receipt.jsx";

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
  READY: "Ready for payment",
  APPROVED: "Approved",
  PENDING_APPROVAL: "Awaiting approval",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

export default function Checkout() {
  const [products, setProducts] = useState([]);
  const [q, setQ] = useState("");
  const [cart, setCart] = useState({}); // productId -> qty
  const [customer, setCustomer] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [discount, setDiscount] = useState("");
  const [sale, setSale] = useState(null); // order already created
  const [receiptId, setReceiptId] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/products").then((r) => setProducts(r.data));
  useEffect(() => { load(); }, []);

  const byId = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);
  const lines = Object.entries(cart).map(([id, qty]) => ({ p: byId[id], qty })).filter((l) => l.p);
  const subtotal = lines.reduce((s, l) => s + Number(l.p.price) * l.qty, 0);
  const discountValue = Number(discount || 0);
  const total = Math.max(0, subtotal - discountValue);

  const add = (p) => setCart((c) => ({ ...c, [p.id]: Math.min((c[p.id] || 0) + 1, p.stock_qty) }));
  const setQty = (id, v) =>
    setCart((c) => {
      const n = { ...c };
      if (v <= 0) delete n[id];
      else n[id] = Math.min(v, byId[id].stock_qty);
      return n;
    });

  useEffect(() => {
    const digits = customerPhone.replace(/\D+/g, "");
    if (digits.length < 6) {
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get("/customers", { params: { phone: digits } });
        const match = data?.[0];
        if (match && (!customer || customer.trim() === "" || customer.trim() === match.full_name || customer.trim() === "Customer")) {
          setCustomer(match.full_name || "");
        }
      } catch (e) {
        // ignore lookup errors; a customer may not exist yet
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [customerPhone]);

  const createOrder = async () => {
    setError("");
    if (busy || lines.length === 0) return;
    setBusy(true);
    try {
      const { data } = await api.post("/sales", {
        customer_name: customer || null,
        customer_phone: customerPhone || null,
        discount: Number(discount || 0),
        items: lines.map((l) => ({ product_id: l.p.id, quantity: l.qty })),
      });
      setSale(data);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setSale(null); setCart({}); setCustomer(""); setCustomerPhone(""); setDiscount(""); setError(""); setBusy(false); load();
  };

  const filtered = products.filter(
    (p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.sku.toLowerCase().includes(q.toLowerCase())
  );

  // ---------- after the order is created ----------
  if (sale) {
    return (
      <div className="page">
        <PageHeader
          eyebrow="Point of sale"
          title={`Order ${sale.receipt_no}`}
          subtitle={STATUS_LABEL[sale.status] || sale.status}
          actions={<span className={`pill ${STATUS_CLASS[sale.status] || "info"}`}>{STATUS_LABEL[sale.status] || sale.status}</span>}
        />

        <div className="checkout-result">
          <section className="card">
            <div className="section-head">
              <div>
                <h3>Order summary</h3>
                <p className="small">Confirm the items before taking payment.</p>
              </div>
              <span className="pill muted">{sale.items.length} line{sale.items.length === 1 ? "" : "s"}</span>
            </div>

            {(sale.customer_name || sale.customer_phone) && (
              <div className="order-customer">
                <div className="avatar avatar-sm">
                  {(sale.customer_name || "?").slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <strong>{sale.customer_name || "Walk-in customer"}</strong>
                  {sale.customer_phone && <span>{sale.customer_phone}</span>}
                </div>
              </div>
            )}

            <div className="table-wrap">
              <table className="table compact">
                <thead>
                  <tr><th>Item</th><th className="right">Qty</th><th className="right">Price</th><th className="right">Amount</th></tr>
                </thead>
                <tbody>
                  {sale.items.map((i) => (
                    <tr key={i.id}>
                      <td>{i.product_name}</td>
                      <td className="right">{i.quantity}</td>
                      <td className="right">{money(i.unit_price)}</td>
                      <td className="right">{money(i.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="totals">
              <div><span>Subtotal</span><span>{money(sale.subtotal)}</span></div>
              {Number(sale.discount) > 0 && (
                <div className="discount-row"><span>Discount</span><span>-{money(sale.discount)}</span></div>
              )}
              <div className="total-row"><span>Total</span><strong>{money(sale.total)}</strong></div>
            </div>
          </section>

          <div className="checkout-side">
            {sale.status === "PENDING_APPROVAL" && (
              <div className="card">
                <div className="empty-icon warn"><Icon name="warning" size={22} /></div>
                <h3>Approval needed</h3>
                <p className="small">
                  This order is above the approval threshold. An admin must approve it before checkout.
                  You can find it under <strong>My sales</strong> once approved.
                </p>
                <button className="primary full" type="button" onClick={reset}>Start a new order</button>
              </div>
            )}

            {sale.status === "READY" && (
              <PaymentPanel sale={sale} onPaid={(s) => { setSale(s); setReceiptId(s.id); }} />
            )}

            {sale.status === "PAID" && (
              <div className="card">
                <div className="paid-banner">
                  <div className="empty-icon ok"><Icon name="check" size={22} /></div>
                  <div>
                    <h3>Payment complete</h3>
                    <p className="small">Change given: <strong>{money(sale.payment?.change_given)}</strong></p>
                  </div>
                </div>
                <button className="primary full" type="button" onClick={() => setReceiptId(sale.id)}>
                  <Icon name="receipt" size={16} /> Print receipt
                </button>
                <button className="ghost full" type="button" onClick={reset}>Start a new order</button>
              </div>
            )}
          </div>
        </div>

        {receiptId && <Receipt saleId={receiptId} onClose={() => setReceiptId(null)} />}
      </div>
    );
  }

  // ---------- building the cart ----------
  return (
    <div className="page">
      <PageHeader
        eyebrow="Point of sale"
        title="New sale"
        subtitle="Build the cart, confirm stock, then take payment."
        actions={<span className="pill info">{lines.length ? `${lines.length} line${lines.length === 1 ? "" : "s"}` : "Empty cart"}</span>}
      />

      <div className="pos-layout">
        <section className="card pos-products">
          <div className="section-head">
            <div>
              <h3>Products</h3>
              <p className="small">Click a product to add it to the cart.</p>
            </div>
            <span className="pill muted">{filtered.length} shown</span>
          </div>

          <div className="search-field">
            <Icon name="search" size={17} />
            <input placeholder="Search name or SKU…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>

          <div className="product-list">
            {filtered.map((p) => (
              <button
                key={p.id}
                className="product"
                disabled={p.stock_qty === 0}
                onClick={() => add(p)}
                type="button"
              >
                {p.image_url ? (
                  <img className="product-image" src={p.image_url} alt="" />
                ) : (
                  <span className="product-image-placeholder"><Icon name="products" size={24} /></span>
                )}
                <span className="product-name">{p.name}</span>
                <span className="product-price">{money(p.price)}</span>
                <span className={p.stock_qty <= p.min_stock ? "low" : "small"}>
                  {p.stock_qty === 0 ? "Out of stock" : `${p.stock_qty} in stock`}
                </span>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="empty-state inline">
                <Icon name="search" size={22} />
                <p>No products match “{q}”.</p>
              </div>
            )}
          </div>
        </section>

        <aside className="card pos-cart">
          <div className="section-head">
            <div>
              <h3>Cart</h3>
              <p className="small">Adjust quantities before creating the order.</p>
            </div>
            {lines.length > 0 && (
              <button className="ghost small-button" type="button" onClick={() => setCart({})}>Clear</button>
            )}
          </div>

          {lines.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Icon name="checkout" size={24} /></div>
              <h4>Your cart is empty</h4>
              <p>Choose products from the list to get started.</p>
            </div>
          ) : (
            <div className="cart-lines">
              {lines.map(({ p, qty }) => (
                <div className="cart-line" key={p.id}>
                  <div className="cart-line-main">
                    <strong>{p.name}</strong>
                    <span>{money(p.price)} each</span>
                  </div>
                  <div className="qty-control">
                    <button type="button" onClick={() => setQty(p.id, qty - 1)} aria-label={`Remove one ${p.name}`}>−</button>
                    <input
                      className="qty"
                      type="number"
                      min="0"
                      max={p.stock_qty}
                      value={qty}
                      onChange={(e) => setQty(p.id, Number(e.target.value))}
                      aria-label={`Quantity for ${p.name}`}
                    />
                    <button type="button" onClick={() => setQty(p.id, qty + 1)} aria-label={`Add one ${p.name}`}>+</button>
                  </div>
                  <strong className="cart-line-total">{money(Number(p.price) * qty)}</strong>
                </div>
              ))}
            </div>
          )}

          <div className="divider" />

          <div className="form-grid two">
            <div className="field">
              <label htmlFor="customer-name">Customer name <span className="optional">(optional)</span></label>
              <input id="customer-name" value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="Walk-in customer" />
            </div>
            <div className="field">
              <label htmlFor="customer-phone">Customer phone</label>
              <input
                id="customer-phone"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
                placeholder="e.g. 0991234567"
              />
            </div>
            <div className="field">
              <label htmlFor="discount">Discount</label>
              <div className="money-input">
                <span>$</span>
                <input
                  id="discount"
                  type="number"
                  min="0"
                  step="0.01"
                  value={discount}
                  onChange={(e) => setDiscount(e.target.value)}
                  placeholder="0.00"
                />
              </div>
            </div>
          </div>

          <div className="totals">
            <div><span>Subtotal</span><span>{money(subtotal)}</span></div>
            {discountValue > 0 && <div className="discount-row"><span>Discount</span><span>-{money(Math.min(discountValue, subtotal))}</span></div>}
            <div className="total-row"><span>Total</span><strong>{money(total)}</strong></div>
          </div>

          <p className="form-hint">
            Orders above the approval threshold are sent to an admin automatically before payment.
          </p>

          {error && <div className="alert error">{error}</div>}

          <button className="primary full" disabled={lines.length === 0 || busy} onClick={createOrder} type="button">
            {busy ? "Creating order…" : "Create order"}
            {!busy && <Icon name="arrowRight" size={16} />}
          </button>
        </aside>
      </div>
    </div>
  );
}
