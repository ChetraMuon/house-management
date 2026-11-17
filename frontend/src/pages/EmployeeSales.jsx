import { useEffect, useRef, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "../components/Icon.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PaginationControls from "../components/PaginationControls.jsx";
import Receipt from "../components/Receipt.jsx";

const PAGE_SIZE = 15;

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

const saleTime = (sale) => sale.paid_at || sale.created_at;

export default function EmployeeSales() {
  const [day, setDay] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [status, setStatus] = useState("PAID");
  const [employees, setEmployees] = useState([]);
  const [employeesLoading, setEmployeesLoading] = useState(true);
  const [data, setData] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [receiptId, setReceiptId] = useState(null);
  const requestRef = useRef(0);

  useEffect(() => {
    let active = true;
    api
      .get("/sales/employee-sales/employees")
      .then((response) => {
        if (active) setEmployees(response.data);
      })
      .catch((err) => {
        if (active) setError(errMsg(err));
      })
      .finally(() => {
        if (active) setEmployeesLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const resetResults = () => {
    requestRef.current += 1;
    setData(null);
    setHasSearched(false);
    setLoading(false);
    setPage(1);
    setError("");
  };

  const chooseDay = (value) => {
    setDay(value);
    resetResults();
  };

  const chooseEmployee = (value) => {
    setEmployeeId(value);
    resetResults();
  };

  const chooseStatus = (value) => {
    setStatus(value);
    resetResults();
  };

  const load = async (targetDay = day, targetEmployee = employeeId, targetStatus = status) => {
    if (!targetDay) {
      setError("Select a date first.");
      return;
    }

    setLoading(true);
    setError("");
    const requestId = ++requestRef.current;
    try {
      const { data: response } = await api.get("/sales/employee-sales", {
        params: {
          day: targetDay,
          employee_id: targetEmployee || undefined,
          status: targetStatus || undefined,
        },
      });
      if (requestId !== requestRef.current) return;
      setData(response);
      setHasSearched(true);
      setPage(1);
    } catch (err) {
      if (requestId === requestRef.current) setError(errMsg(err));
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  };

  const showToday = () => {
    const today = localDate();
    resetResults();
    setDay(today);
    load(today, employeeId, status);
  };

  const sales = data?.sales ?? [];
  const totalPages = Math.max(1, Math.ceil(sales.length / PAGE_SIZE));
  const visibleSales = sales.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const sellingEmployees = new Set(sales.map((sale) => sale.employee_id)).size;
  const dayLabel = formatDay(day);
  const selectedEmployee = employees.find(
    (employee) => String(employee.id) === String(employeeId),
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Operations"
        title="Employee sales"
        subtitle="Check employee receipts, customer details, and daily sales activity."
        actions={
          hasSearched ? (
            <div className="row page-actions-row no-print">
              <button className="ghost" type="button" onClick={() => load()} disabled={loading}>
                <Icon name="refresh" size={16} /> {loading ? "Refreshing…" : "Refresh"}
              </button>
            </div>
          ) : null
        }
      />

      <section className="card report-filter no-print">
        <div className="report-filter-fields">
          <div className="field">
            <label htmlFor="employee-sales-day">Day</label>
            <input
              id="employee-sales-day"
              type="date"
              value={day}
              onChange={(event) => chooseDay(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="employee-sales-employee">Employee</label>
            <select
              id="employee-sales-employee"
              value={employeeId}
              onChange={(event) => chooseEmployee(event.target.value)}
              disabled={employeesLoading}
            >
              <option value="">All employees</option>
              {employees.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} (@{employee.username})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="employee-sales-status">Status</label>
            <select
              id="employee-sales-status"
              value={status}
              onChange={(event) => chooseStatus(event.target.value)}
            >
              <option value="PAID">Paid only</option>
              <option value="">All statuses</option>
              <option value="PENDING_APPROVAL">Awaiting approval</option>
              <option value="READY">Ready</option>
              <option value="APPROVED">Approved</option>
              <option value="CANCELLED">Cancelled</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          <button
            className="primary"
            type="button"
            onClick={() => load()}
            disabled={!day || loading}
          >
            <Icon name="search" size={16} /> {loading ? "Loading…" : "Show sales"}
          </button>
          <button className="ghost" type="button" onClick={showToday} disabled={loading}>
            <Icon name="receipt" size={16} /> Today
          </button>
        </div>
        <p className="small report-range">
          {day
            ? `${formatDay(day)} · ${selectedEmployee ? selectedEmployee.full_name : "All employees"}`
            : "Select a date, then choose Show sales or Today."}
        </p>
      </section>

      {error && <div className="alert error">{error}</div>}

      {!hasSearched && (
        <section className="card">
          <div className="empty-state">
            <div className="empty-icon"><Icon name="receipt" size={24} /></div>
            <h4>{loading ? "Loading employee sales…" : "Select a date"}</h4>
            <p>
              {loading
                ? "Fetching the daily register."
                : "Choose a day above, then select Show sales or Today. Leave the employee on All employees to include everyone."}
            </p>
          </div>
        </section>
      )}

      {hasSearched && (
        <div className="mini-stats">
          <div className="mini-stat"><span>Receipts</span><strong>{data?.count ?? 0}</strong></div>
          <div className="mini-stat"><span>Paid sales</span><strong>{data?.paid_count ?? 0}</strong></div>
          <div className="mini-stat"><span>Paid total</span><strong>{money(data?.total)}</strong></div>
          <div className="mini-stat"><span>Employees selling</span><strong>{sellingEmployees}</strong></div>
        </div>
      )}

      {hasSearched && (
      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Daily register</span>
            <h3>{dayLabel}</h3>
            <p className="small">
              {selectedEmployee ? `${selectedEmployee.full_name} · ` : "All employees · "}
              {sales.length} receipt{sales.length === 1 ? "" : "s"}
              {data?.paid_count > 0 ? ` · ${money(data.total)} paid` : ""}
            </p>
          </div>
        </div>

        <div className="table-wrap flush employee-sales-table-wrap">
          <table className="table employee-sales-table">
            <thead>
              <tr>
                <th>Receipt</th>
                <th>Time</th>
                <th>Employee</th>
                <th>Customer</th>
                <th>Phone</th>
                <th className="right">Total</th>
                <th>Status</th>
                <th className="right">Action</th>
              </tr>
            </thead>
            <tbody>
              {visibleSales.map((sale) => (
                <tr key={sale.id}>
                  <td className="mono">{sale.receipt_no}</td>
                  <td className="nowrap">
                    {new Date(saleTime(sale)).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td>
                    <strong>{sale.employee_name}</strong>
                    {sale.employee_username && (
                      <div className="small table-note">@{sale.employee_username}</div>
                    )}
                  </td>
                  <td>
                    {sale.customer_name || <span className="muted-text">Walk-in customer</span>}
                  </td>
                  <td className="mono">
                    {sale.customer_phone || <span className="muted-text">—</span>}
                  </td>
                  <td className="right"><strong>{money(sale.total)}</strong></td>
                  <td>
                    <span className={`pill ${STATUS_CLASS[sale.status] || "muted"}`}>
                      {STATUS_LABEL[sale.status] || sale.status}
                    </span>
                  </td>
                  <td className="right">
                    {sale.status === "PAID" ? (
                      <button
                        className="ghost small-button"
                        type="button"
                        onClick={() => setReceiptId(sale.id)}
                      >
                        <Icon name="receipt" size={15} /> View
                      </button>
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                </tr>
              ))}

              {visibleSales.length === 0 && (
                <tr>
                  <td colSpan="8">
                    <div className="empty-state">
                      <div className="empty-icon"><Icon name="receipt" size={24} /></div>
                      <h4>{loading ? "Loading sales…" : "No employee sales for this selection"}</h4>
                      <p>
                        {loading
                          ? "Fetching the daily register."
                          : "Try another date, employee, or status."}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mobile-sales-list">
          {visibleSales.map((sale) => (
            <article className="sale-card" key={sale.id}>
              <div className="sale-card-head">
                <div>
                  <strong className="mono">{sale.receipt_no}</strong>
                  <span className="small">
                    {new Date(saleTime(sale)).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {" · "}
                    {sale.employee_name}
                  </span>
                </div>
                <span className={`pill ${STATUS_CLASS[sale.status] || "muted"}`}>
                  {STATUS_LABEL[sale.status] || sale.status}
                </span>
              </div>

              <div className="sale-card-customer">
                <div>
                  <span>Customer</span>
                  <strong>{sale.customer_name || "Walk-in customer"}</strong>
                </div>
                <div>
                  <span>Phone</span>
                  <strong className="mono">{sale.customer_phone || "—"}</strong>
                </div>
              </div>

              <div className="sale-card-foot">
                <strong>{money(sale.total)}</strong>
                {sale.status === "PAID" && (
                  <button
                    className="ghost small-button"
                    type="button"
                    onClick={() => setReceiptId(sale.id)}
                  >
                    <Icon name="receipt" size={15} /> View receipt
                  </button>
                )}
              </div>
            </article>
          ))}

          {visibleSales.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon"><Icon name="receipt" size={24} /></div>
              <h4>{loading ? "Loading sales…" : "No employee sales for this selection"}</h4>
              <p>
                {loading
                  ? "Fetching the daily register."
                  : "Try another date, employee, or status."}
              </p>
            </div>
          )}
        </div>

        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPrev={() => setPage((current) => Math.max(1, current - 1))}
          onNext={() => setPage((current) => Math.min(totalPages, current + 1))}
        />
      </section>
      )}

      {receiptId && <Receipt saleId={receiptId} onClose={() => setReceiptId(null)} />}
    </div>
  );
}
