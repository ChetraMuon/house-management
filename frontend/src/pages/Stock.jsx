import { useEffect, useState } from "react";
import api, { errMsg } from "../api";
import { useAuth } from "../auth.jsx";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const PAGE_SIZE = 10;

const MOVE_CLASS = { IN: "ok", OUT: "warn", ADJUST: "info", SALE: "muted" };
const MOVE_LABEL = { IN: "Stock in", OUT: "Stock out", ADJUST: "Adjustment", SALE: "Sale" };

function stockStatus(product) {
  if (product.stock_qty === 0) return { label: "Out of stock", className: "error" };
  if (product.stock_qty <= product.min_stock) return { label: "Low stock", className: "warn" };
  return { label: "In stock", className: "ok" };
}

export default function Stock() {
  const { user } = useAuth();
  const [products, setProducts] = useState([]);
  const [moves, setMoves] = useState([]);
  const [form, setForm] = useState({ product_id: "", type: "in", quantity: "", reference: "", note: "" });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stockPage, setStockPage] = useState(1);
  const [movePage, setMovePage] = useState(1);
  const [quick, setQuick] = useState(null);
  const [quickForm, setQuickForm] = useState({ type: "in", quantity: "", reference: "", note: "" });
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickError, setQuickError] = useState("");
  const [quickMsg, setQuickMsg] = useState(null);
  const [productQuery, setProductQuery] = useState("");
  const [productOpen, setProductOpen] = useState(false);
  const [productIndex, setProductIndex] = useState(0);

  const totalStockPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE));
  const visibleProducts = products.slice((stockPage - 1) * PAGE_SIZE, stockPage * PAGE_SIZE);
  const totalMovesPages = Math.max(1, Math.ceil(moves.length / PAGE_SIZE));
  const visibleMoves = moves.slice((movePage - 1) * PAGE_SIZE, movePage * PAGE_SIZE);

  const lowStock = products.filter((p) => p.stock_qty <= p.min_stock).length;
  const outOfStock = products.filter((p) => p.stock_qty === 0).length;
  const totalUnits = products.reduce((sum, p) => sum + Number(p.stock_qty || 0), 0);
  const quickStatus = quick ? stockStatus(quick) : null;
  const quickQty = Number(quickForm.quantity);
  const quickBalance = quick ? quick.stock_qty + (quickForm.type === "in" ? quickQty : -quickQty) : 0;

  const selectedProduct = products.find((p) => String(p.id) === String(form.product_id)) ?? null;
  const productSearch = productQuery.trim().toLowerCase();
  const productResults = (
    productSearch
      ? products.filter(
          (p) =>
            p.name.toLowerCase().includes(productSearch) ||
            p.sku.toLowerCase().includes(productSearch),
        )
      : products
  ).slice(0, 8);

  const load = async (resetPages = true) => {
    try {
      setLoading(true);
      const [productsRes, movesRes] = await Promise.all([
        api.get("/products", { params: { only_active: false } }),
        api.get("/stock/movements", { params: { limit: 50 } }),
      ]);
      setProducts(productsRes.data);
      setMoves(movesRes.data);
      if (resetPages) {
        setStockPage(1);
        setMovePage(1);
      }
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const name = (id) => products.find((p) => p.id === id)?.name ?? `#${id}`;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const chooseProduct = (product) => {
    setForm((prev) => ({ ...prev, product_id: String(product.id) }));
    setProductQuery("");
    setProductOpen(false);
    setProductIndex(0);
  };

  const clearProduct = () => {
    setForm((prev) => ({ ...prev, product_id: "" }));
    setProductQuery("");
    setProductOpen(false);
    setProductIndex(0);
  };

  const searchProducts = (e) => {
    setProductQuery(e.target.value);
    setProductOpen(true);
    setProductIndex(0);
  };

  const productKeys = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!productOpen) {
        setProductOpen(true);
        setProductIndex(0);
      } else {
        setProductIndex((i) => Math.min(i + 1, Math.max(productResults.length - 1, 0)));
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setProductIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (productOpen && productResults[productIndex]) {
        e.preventDefault();
        chooseProduct(productResults[productIndex]);
      }
    } else if (e.key === "Escape") {
      setProductOpen(false);
    }
  };

  const closeProductMenu = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setProductOpen(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    setMsg(null);
    if (busy) return;
    if (!form.product_id) {
      setMsg({ ok: false, text: "Search for a product and choose a result first." });
      return;
    }
    setBusy(true);
    try {
      let response;
      if (form.type === "adjust") {
        response = await api.post("/stock/adjust", {
          product_id: +form.product_id,
          new_quantity: +form.quantity,
          note: form.note || null,
        });
      } else {
        response = await api.post(`/stock/${form.type}`, {
          product_id: +form.product_id,
          quantity: +form.quantity,
          reference: form.reference || null,
          note: form.note || null,
        });
      }

      const updatedProduct = response.data;
      setProducts((prev) => prev.map((p) => (p.id === updatedProduct.id ? updatedProduct : p)));
      setMsg({ ok: true, text: "Stock updated successfully." });
      setForm({ ...form, quantity: "", reference: "", note: "" });
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setBusy(false);
    }
  };

  const openQuick = (product, type = "in") => {
    setQuick(product);
    setQuickForm({ type, quantity: "", reference: "", note: "" });
    setQuickError("");
    setQuickMsg(null);
    setMsg(null);
  };

  const closeQuick = () => {
    if (quickBusy) return;
    setQuick(null);
    setQuickError("");
  };

  const setQuickField = (key) => (e) => setQuickForm({ ...quickForm, [key]: e.target.value });

  const submitQuick = async (e) => {
    e.preventDefault();
    if (!quick || quickBusy) return;

    const qty = Number(quickForm.quantity);
    if (!Number.isInteger(qty) || qty <= 0) {
      setQuickError("Enter a whole number greater than 0.");
      return;
    }
    if (quickForm.type === "out" && qty > quick.stock_qty) {
      setQuickError(`Only ${quick.stock_qty} ${quick.unit} on hand.`);
      return;
    }

    setQuickBusy(true);
    setQuickError("");
    try {
      const { data: updated } = await api.post(`/stock/${quickForm.type}`, {
        product_id: quick.id,
        quantity: qty,
        reference: quickForm.reference || null,
        note: quickForm.note || null,
      });
      setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setQuickMsg({
        ok: true,
        text: `${quickForm.type === "in" ? "Stock in" : "Stock out"} saved for ${updated.name}. New balance: ${updated.stock_qty} ${updated.unit}.`,
      });
      setQuick(null);
      await load(false);
    } catch (err) {
      setQuickError(errMsg(err));
    } finally {
      setQuickBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Inventory"
        title="Stock control"
        subtitle="Receive stock, record usage, and keep an eye on products running low."
        actions={
          <button className="ghost" type="button" onClick={() => load()} disabled={loading}>
            <Icon name="refresh" size={16} /> {loading ? "Refreshing…" : "Refresh"}
          </button>
        }
      />

      {quick && (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="quick-stock-title">
          <div className="modal-box">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Quick stock update</span>
                <h3 id="quick-stock-title">{quick.name}</h3>
                <p className="small mono">{quick.sku}</p>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={closeQuick}
                disabled={quickBusy}
                aria-label="Close"
              >
                <Icon name="close" />
              </button>
            </div>

            <div className="row stock-quick-summary">
              <span className="pill muted">On hand: {quick.stock_qty} {quick.unit}</span>
              <span className="pill muted">Minimum: {quick.min_stock}</span>
              <span className={`pill ${quickStatus.className}`}>{quickStatus.label}</span>
              {!quick.is_active && <span className="pill muted">Archived</span>}
            </div>

            <div className="segmented two stock-type-toggle" role="group" aria-label="Stock movement type">
              <button
                className={quickForm.type === "in" ? "active" : ""}
                type="button"
                onClick={() => setQuickForm({ ...quickForm, type: "in" })}
                disabled={quickBusy}
              >
                <Icon name="plus" size={15} /> Stock in
              </button>
              <button
                className={quickForm.type === "out" ? "active" : ""}
                type="button"
                onClick={() => setQuickForm({ ...quickForm, type: "out" })}
                disabled={quickBusy}
              >
                <Icon name="minus" size={15} /> Stock out
              </button>
            </div>

            <form onSubmit={submitQuick}>
              <div className="form-grid two">
                <div className="field">
                  <label htmlFor="quick-stock-quantity">Quantity</label>
                  <input
                    id="quick-stock-quantity"
                    type="number"
                    min="1"
                    step="1"
                    value={quickForm.quantity}
                    onChange={setQuickField("quantity")}
                    placeholder={quickForm.type === "in" ? "How many received?" : "How many removed?"}
                    autoFocus
                    required
                  />
                  <span className="form-hint">
                    {Number.isInteger(quickQty) && quickQty > 0 ? (
                      <>
                        New balance:{" "}
                        <strong className={quickBalance < 0 ? "text-danger" : ""}>
                          {quickBalance} {quick.unit}
                        </strong>
                      </>
                    ) : (
                      "Enter a whole number."
                    )}
                  </span>
                </div>

                <div className="field">
                  <label htmlFor="quick-stock-reference">
                    Reference / PO <span className="optional">(optional)</span>
                  </label>
                  <input
                    id="quick-stock-reference"
                    value={quickForm.reference}
                    onChange={setQuickField("reference")}
                    placeholder="e.g. PO-1042"
                  />
                </div>

                <div className="field grow">
                  <label htmlFor="quick-stock-note">
                    Note <span className="optional">(optional)</span>
                  </label>
                  <input
                    id="quick-stock-note"
                    value={quickForm.note}
                    onChange={setQuickField("note")}
                    placeholder="Anything worth remembering"
                  />
                </div>
              </div>

              {quickError && <div className="alert error">{quickError}</div>}

              <div className="modal-actions">
                <button type="button" className="ghost" onClick={closeQuick} disabled={quickBusy}>
                  Cancel
                </button>
                <button className="primary" disabled={quickBusy}>
                  {quickBusy
                    ? "Saving…"
                    : quickForm.type === "in"
                      ? "Add stock"
                      : "Remove stock"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="mini-stats">
        <div className="mini-stat"><span>Products tracked</span><strong>{products.length}</strong></div>
        <div className="mini-stat"><span>Units on hand</span><strong>{totalUnits}</strong></div>
        <div className="mini-stat"><span>Low stock</span><strong className={lowStock ? "text-warn" : ""}>{lowStock}</strong></div>
        <div className="mini-stat"><span>Out of stock</span><strong className={outOfStock ? "text-danger" : ""}>{outOfStock}</strong></div>
      </div>

      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Record a change</span>
            <h3>Update stock</h3>
            <p className="small">Choose a product and the kind of movement to record.</p>
          </div>
          <span className="pill info">{user.role === "manager" ? "Manager access" : "Admin access"}</span>
        </div>

        <form onSubmit={submit}>
          <div className="form-grid three">
            <div className="field">
              <label htmlFor={selectedProduct ? undefined : "stock-product"}>Product</label>
              {selectedProduct ? (
                <div className="selected-product">
                  <span className="selected-product-main">
                    <strong>{selectedProduct.name}</strong>
                    <span className="small muted-text">
                      {selectedProduct.sku} · {selectedProduct.stock_qty} in stock
                      {!selectedProduct.is_active ? " · Archived" : ""}
                    </span>
                  </span>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={clearProduct}
                    aria-label="Choose a different product"
                    title="Choose a different product"
                  >
                    <Icon name="close" size={15} />
                  </button>
                </div>
              ) : (
                <div className="product-picker" onBlur={closeProductMenu}>
                  <div className="search-field">
                    <Icon name="search" size={17} />
                    <input
                      id="stock-product"
                      role="combobox"
                      aria-expanded={productOpen}
                      aria-controls="stock-product-results"
                      aria-autocomplete="list"
                      autoComplete="off"
                      placeholder="Search name or SKU…"
                      value={productQuery}
                      onChange={searchProducts}
                      onFocus={() => setProductOpen(true)}
                      onKeyDown={productKeys}
                    />
                  </div>
                  {productOpen && (
                    <div className="product-results" id="stock-product-results" role="listbox">
                      {productResults.map((p, index) => (
                        <button
                          key={p.id}
                          className={`product-result${index === productIndex ? " active" : ""}`}
                          type="button"
                          role="option"
                          aria-selected={index === productIndex}
                          onMouseEnter={() => setProductIndex(index)}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => chooseProduct(p)}
                        >
                          <span className="product-result-main">
                            <strong>{p.name}</strong>
                            <span className="small muted-text">
                              {p.sku}
                              {!p.is_active ? " · Archived" : ""}
                            </span>
                          </span>
                          <span className={p.stock_qty <= p.min_stock ? "pill warn" : "pill muted"}>
                            {p.stock_qty} in stock
                          </span>
                        </button>
                      ))}
                      {productResults.length === 0 && (
                        <div className="product-result-empty">
                          No products match “{productQuery}”.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              <span className="form-hint">
                {selectedProduct
                  ? "Use the × button to choose a different product."
                  : "Search by product name or SKU, then choose a result."}
              </span>
            </div>

            <div className="field">
              <label htmlFor="stock-type">Movement type</label>
              <select id="stock-type" value={form.type} onChange={set("type")}>
                <option value="in">Stock in</option>
                <option value="out">Stock out</option>
                {user.role === "manager" && <option value="adjust">Adjust to exact quantity</option>}
              </select>
            </div>

            <div className="field">
              <label htmlFor="stock-quantity">
                {form.type === "adjust" ? "New quantity" : "Quantity"}
              </label>
              <input
                id="stock-quantity"
                type="number"
                min="0"
                value={form.quantity}
                onChange={set("quantity")}
                placeholder={form.type === "adjust" ? "Exact count" : "How many?"}
                required
              />
            </div>

            {form.type !== "adjust" && (
              <div className="field">
                <label htmlFor="stock-reference">Reference / PO <span className="optional">(optional)</span></label>
                <input
                  id="stock-reference"
                  value={form.reference}
                  onChange={set("reference")}
                  placeholder="e.g. PO-1042"
                />
              </div>
            )}

            <div className="field grow">
              <label htmlFor="stock-note">Note <span className="optional">(optional)</span></label>
              <input
                id="stock-note"
                value={form.note}
                onChange={set("note")}
                placeholder="Anything worth remembering"
              />
            </div>

            <div className="field field-action">
              <button className="primary" disabled={busy}>{busy ? "Saving…" : "Save stock change"}</button>
            </div>
          </div>
        </form>

        {msg && <div className={`alert ${msg.ok ? "ok" : "error"}`}>{msg.text}</div>}
      </section>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Current stock</h3>
            <p className="small">Click a product name to stock in or out. A live count for every product in the catalog.</p>
          </div>
          <span className="pill muted">{products.length} products</span>
        </div>

        {quickMsg && <div className={`alert ${quickMsg.ok ? "ok" : "error"}`}>{quickMsg.text}</div>}

        <div className="table-wrap flush">
          <table className="table">
            <thead>
              <tr><th>SKU</th><th>Product</th><th className="right">On hand</th><th className="right">Minimum</th><th>Status</th><th className="right">Quick update</th></tr>
            </thead>
            <tbody>
              {visibleProducts.map((p) => {
                const status = stockStatus(p);
                return (
                  <tr key={p.id} className={p.stock_qty <= p.min_stock ? "row-low" : ""}>
                    <td className="mono">{p.sku}</td>
                    <td>
                      <button className="link-button" type="button" onClick={() => openQuick(p)}>
                        {p.name}
                      </button>
                      {!p.is_active && <div className="small table-note">Inactive product</div>}
                    </td>
                    <td className="right"><strong>{p.stock_qty}</strong></td>
                    <td className="right">{p.min_stock}</td>
                    <td><span className={`pill ${status.className}`}>{status.label}</span></td>
                    <td>
                      <div className="row actions-cell">
                        <button className="ghost small-button" type="button" onClick={() => openQuick(p, "in")}>
                          <Icon name="plus" size={14} /> Stock in
                        </button>
                        <button className="ghost small-button" type="button" onClick={() => openQuick(p, "out")}>
                          <Icon name="minus" size={14} /> Stock out
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {visibleProducts.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty-state">
                      <div className="empty-icon"><Icon name="stock" size={24} /></div>
                      <h4>No products yet</h4>
                      <p>Add products from the Products page to start tracking stock.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <PaginationControls
          page={stockPage}
          totalPages={totalStockPages}
          onPrev={() => setStockPage((p) => Math.max(1, p - 1))}
          onNext={() => setStockPage((p) => Math.min(totalStockPages, p + 1))}
        />
      </section>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Recent movements</h3>
            <p className="small">The latest 50 stock changes across the store.</p>
          </div>
          <span className="pill muted">{moves.length} recorded</span>
        </div>

        <div className="table-wrap flush">
          <table className="table">
            <thead>
              <tr><th>Date</th><th>Product</th><th>Type</th><th className="right">Qty</th><th>Before → after</th><th>Reference / note</th></tr>
            </thead>
            <tbody>
              {visibleMoves.map((m) => (
                <tr key={m.id}>
                  <td className="nowrap">{new Date(m.created_at).toLocaleString()}</td>
                  <td><strong>{name(m.product_id)}</strong></td>
                  <td><span className={`pill ${MOVE_CLASS[m.movement_type] || "info"}`}>{MOVE_LABEL[m.movement_type] || m.movement_type}</span></td>
                  <td className="right">{m.quantity}</td>
                  <td className="nowrap">{m.qty_before} <span className="arrow">→</span> <strong>{m.qty_after}</strong></td>
                  <td className="cell-summary">{m.reference || m.note || <span className="muted-text">—</span>}</td>
                </tr>
              ))}
              {visibleMoves.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty-state">
                      <div className="empty-icon"><Icon name="rotate" size={24} /></div>
                      <h4>No movements recorded</h4>
                      <p>Stock changes will appear here as soon as they happen.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <PaginationControls
          page={movePage}
          totalPages={totalMovesPages}
          onPrev={() => setMovePage((p) => Math.max(1, p - 1))}
          onNext={() => setMovePage((p) => Math.min(totalMovesPages, p + 1))}
        />
      </section>
    </div>
  );
}
