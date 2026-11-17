import { useEffect, useRef, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";

const EMPTY = { sku: "", name: "", category_id: "", unit: "pcs", price: "", cost: "", min_stock: 5 };
const PAGE_SIZE = 10;

export default function Products() {
  const [products, setProducts] = useState([]);
  const [cats, setCats] = useState([]);
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [newCat, setNewCat] = useState("");
  const [msg, setMsg] = useState(null);
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [catBusy, setCatBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState(null);
  const [showArchived, setShowArchived] = useState(false);
  const imageInput = useRef(null);

  const totalPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE));
  const visibleProducts = products.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const activeCount = products.filter((p) => p.is_active).length;
  const archivedCount = products.length - activeCount;

  const load = async () => {
    try {
      const [productsRes, catsRes] = await Promise.all([
        api.get("/products", { params: { only_active: !showArchived } }),
        api.get("/categories"),
      ]);
      setProducts(productsRes.data);
      setCats(catsRes.data);
      setPage(1);
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    }
  };
  useEffect(() => { load(); }, [showArchived]);
  useEffect(() => {
    if (!imagePreview.startsWith("blob:")) return undefined;
    return () => URL.revokeObjectURL(imagePreview);
  }, [imagePreview]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const resetForm = () => {
    setForm(EMPTY);
    setEditingId(null);
    setImageFile(null);
    setImagePreview("");
    if (imageInput.current) imageInput.current.value = "";
  };

  const uploadImage = async (productId, file) => {
    const body = new FormData();
    body.append("image", file);
    await api.put(`/products/${productId}/image`, body);
  };

  const payload = () => ({
    ...form,
    category_id: form.category_id ? +form.category_id : null,
    price: +form.price,
    cost: +form.cost || 0,
    min_stock: +form.min_stock,
  });

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setMsg(null);
    setBusy(true);
    try {
      if (editingId) {
        await api.patch(`/products/${editingId}`, payload());
        if (imageFile) await uploadImage(editingId, imageFile);
        setMsg({ ok: true, text: "Product updated." });
      } else {
        const { data: product } = await api.post("/products", payload());
        if (imageFile) {
          setEditingId(product.id);
          await uploadImage(product.id, imageFile);
        }
        setMsg({ ok: true, text: "Product created. Use the Stock page to add quantity." });
      }
      resetForm();
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setBusy(false);
    }
  };

  const setActive = async (product, active) => {
    const question = active
      ? "Restore this product? It will be available again."
      : "Archive this product? It will be hidden from checkout and active listings, but its sales and stock history will be kept.";
    if (!window.confirm(question)) return;
    setRowBusy(product.id);
    try {
      await api.patch(`/products/${product.id}`, { is_active: active });
      setMsg({
        ok: true,
        text: active ? "Product restored." : "Product archived. Sales and stock history are kept.",
      });
      resetForm();
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setRowBusy(null);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this product permanently? This cannot be undone.")) return;
    setRowBusy(id);
    try {
      await api.delete(`/products/${id}`);
      setMsg({ ok: true, text: "Product deleted permanently." });
      resetForm();
      await load();
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setRowBusy(null);
    }
  };

  const beginEdit = (p) => {
    setEditingId(p.id);
    setForm({
      sku: p.sku,
      name: p.name,
      category_id: p.category_id ?? "",
      unit: p.unit,
      price: p.price,
      cost: p.cost,
      min_stock: p.min_stock,
    });
    setImageFile(null);
    setImagePreview(p.image_url || "");
    setMsg(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const selectImage = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/gif", "image/webp"].includes(file.type)) {
      setMsg({ ok: false, text: "Choose a PNG, JPEG, GIF, or WebP image." });
      event.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setMsg({ ok: false, text: "Product images must be 5 MB or smaller." });
      event.target.value = "";
      return;
    }
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
    setMsg(null);
  };

  const addCat = async () => {
    if (!newCat.trim() || catBusy) return;
    setCatBusy(true);
    setMsg(null);
    try {
      await api.post("/categories", { name: newCat });
      setNewCat("");
      const { data } = await api.get("/categories");
      setCats(data);
      setMsg({ ok: true, text: "Category added." });
    } catch (err) {
      setMsg({ ok: false, text: errMsg(err) });
    } finally {
      setCatBusy(false);
    }
  };

  const categoryName = (id) => cats.find((c) => c.id === id)?.name;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Catalog"
        title="Products"
        subtitle="Keep pricing and stock thresholds current. Archive retired items to keep their sales history."
        actions={
          <span className="pill muted">
            {activeCount} active{showArchived && archivedCount > 0 ? ` · ${archivedCount} archived` : ""}
          </span>
        }
      />

      {msg && <div className={`alert ${msg.ok ? "ok" : "error"}`}>{msg.text}</div>}

      <div className="split-layout">
        <section className="card">
          <div className="section-head">
            <div>
              <span className="eyebrow">{editingId ? "Editing product" : "New product"}</span>
              <h3>{editingId ? form.name || "Edit product" : "Add a product"}</h3>
              <p className="small">
                {editingId
                  ? "Update the details below, then save your changes."
                  : "Create the catalog item first, then add stock from the Stock page."}
              </p>
            </div>
            {editingId && <span className="pill info">Editing</span>}
          </div>

          <form onSubmit={submit}>
            <div className="form-grid two">
              <div className="field">
                <label htmlFor="product-sku">SKU</label>
                <input id="product-sku" value={form.sku} onChange={set("sku")} placeholder="e.g. BEV-001" required />
              </div>
              <div className="field">
                <label htmlFor="product-name">Product name</label>
                <input id="product-name" value={form.name} onChange={set("name")} placeholder="e.g. Sparkling water" required />
              </div>
              <div className="field">
                <label htmlFor="product-category">Category</label>
                <select id="product-category" value={form.category_id} onChange={set("category_id")}>
                  <option value="">No category</option>
                  {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="product-unit">Unit</label>
                <input id="product-unit" value={form.unit} onChange={set("unit")} placeholder="pcs" />
              </div>
              <div className="field">
                <label htmlFor="product-price">Selling price</label>
                <div className="money-input">
                  <span>$</span>
                  <input
                    id="product-price"
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.price}
                    onChange={set("price")}
                    placeholder="0.00"
                    required
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="product-cost">Cost price</label>
                <div className="money-input">
                  <span>$</span>
                  <input
                    id="product-cost"
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.cost}
                    onChange={set("cost")}
                    placeholder="0.00"
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="product-min">Low-stock threshold</label>
                <input
                  id="product-min"
                  type="number"
                  min="0"
                  value={form.min_stock}
                  onChange={set("min_stock")}
                  placeholder="5"
                />
                <span className="form-hint">You will be warned when stock reaches this level.</span>
              </div>
            </div>

            <div className="field product-image-field">
              <label htmlFor="product-image">Product image</label>
              <input
                ref={imageInput}
                id="product-image"
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                onChange={selectImage}
              />
              <span className="form-hint">PNG, JPEG, GIF, or WebP · up to 5 MB. Employees see this at checkout.</span>
              {imagePreview && (
                <img className="product-image-preview" src={imagePreview} alt="Product preview" />
              )}
            </div>

            <div className="row form-actions">
              <button className="primary" disabled={busy}>
                {busy ? "Saving…" : editingId ? "Save changes" : "Add product"}
              </button>
              {editingId && (
                <button type="button" className="ghost" onClick={resetForm} disabled={busy}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </section>

        <aside className="card category-panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">Organization</span>
              <h3>Categories</h3>
              <p className="small">Group products so the catalog stays easy to scan.</p>
            </div>
            <span className="pill muted">{cats.length}</span>
          </div>

          <div className="category-list">
            {cats.map((c) => (
              <span className="category-chip" key={c.id}>
                <Icon name="tag" size={14} /> {c.name}
              </span>
            ))}
            {cats.length === 0 && <p className="small">No categories yet.</p>}
          </div>

          <div className="field">
            <label htmlFor="new-category">New category</label>
            <input
              id="new-category"
              value={newCat}
              onChange={(e) => setNewCat(e.target.value)}
              placeholder="e.g. Beverages"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCat();
                }
              }}
            />
          </div>
          <button className="ghost full" type="button" onClick={addCat} disabled={!newCat.trim() || catBusy}>
            <Icon name="plus" size={16} /> {catBusy ? "Adding…" : "Add category"}
          </button>
        </aside>
      </div>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Product catalog</h3>
            <p className="small">
              Prices, cost, and current stock in one view. Delete is only offered for products with no stock or sales history.
            </p>
          </div>
          <div className="row">
            <label className="row small archived-toggle">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
              />
              Show archived
            </label>
            <span className="pill muted">Page {page} of {totalPages}</span>
          </div>
        </div>

        <div className="table-wrap flush">
          <table className="table product-table">
            <thead>
              <tr>
                <th>Product</th><th>Category</th><th className="right">Price</th><th className="right">Cost</th>
                <th className="right">Stock</th><th>Status</th><th className="right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleProducts.map((p) => {
                const low = p.stock_qty <= p.min_stock;
                const out = p.stock_qty === 0;
                return (
                  <tr key={p.id} className={p.is_active ? "" : "row-muted"}>
                    <td>
                      <div className="product-catalog-cell">
                        {p.image_url ? (
                          <img className="product-catalog-image" src={p.image_url} alt="" />
                        ) : (
                          <span className="product-catalog-placeholder"><Icon name="products" size={18} /></span>
                        )}
                        <div>
                          <strong>{p.name}</strong>
                          <div className="small table-note mono">{p.sku}</div>
                        </div>
                      </div>
                    </td>
                    <td>{categoryName(p.category_id) || <span className="muted-text">Uncategorized</span>}</td>
                    <td className="right"><strong>{money(p.price)}</strong></td>
                    <td className="right">{money(p.cost)}</td>
                    <td className="right">
                      <strong className={out || low ? "text-warn" : ""}>{p.stock_qty}</strong>
                      <div className="small table-note">{p.unit}</div>
                    </td>
                    <td>
                      {!p.is_active ? (
                        <span className="pill muted">Archived</span>
                      ) : out ? (
                        <span className="pill error">Out of stock</span>
                      ) : low ? (
                        <span className="pill warn">Low stock</span>
                      ) : (
                        <span className="pill ok">Active</span>
                      )}
                    </td>
                    <td>
                      <div className="row actions-cell">
                        <button className="ghost small-button" type="button" onClick={() => beginEdit(p)} disabled={rowBusy === p.id}>
                          Edit
                        </button>
                        {p.can_delete && (
                          <button
                            className="ghost small-button danger-text"
                            type="button"
                            onClick={() => remove(p.id)}
                            disabled={rowBusy === p.id}
                          >
                            Delete
                          </button>
                        )}
                        {!p.is_active ? (
                          <button
                            className="ghost small-button"
                            type="button"
                            onClick={() => setActive(p, true)}
                            disabled={rowBusy === p.id}
                          >
                            Restore
                          </button>
                        ) : !p.can_delete ? (
                          <button
                            className="ghost small-button"
                            type="button"
                            onClick={() => setActive(p, false)}
                            disabled={rowBusy === p.id}
                          >
                            Archive
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {visibleProducts.length === 0 && (
                <tr>
                  <td colSpan="7">
                    <div className="empty-state">
                      <div className="empty-icon"><Icon name="products" size={24} /></div>
                      <h4>{showArchived ? "No products yet" : "No active products"}</h4>
                      <p>
                        {showArchived
                          ? "Add your first product above and it will appear here."
                          : "Archived products are hidden. Tick Show archived to view and restore them."}
                      </p>
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
      </section>
    </div>
  );
}
