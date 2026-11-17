import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import api from "./api";
import { useAuth } from "./auth.jsx";
import ChangePasswordModal from "./components/ChangePasswordModal.jsx";
import Icon from "./components/Icon.jsx";
import Login from "./pages/Login.jsx";
import Checkout from "./pages/Checkout.jsx";
import Sales from "./pages/Sales.jsx";
import Products from "./pages/Products.jsx";
import Stock from "./pages/Stock.jsx";
import Approvals from "./pages/Approvals.jsx";
import Reports from "./pages/Reports.jsx";
import Users from "./pages/Users.jsx";
import Logs from "./pages/Logs.jsx";
import Customers from "./pages/Customers.jsx";
import EmployeeSales from "./pages/EmployeeSales.jsx";
import PaywaySimulator from "./pages/PaywaySimulator.jsx";

// which pages each role can open
const MENU = [
  { to: "/checkout", label: "New sale", icon: "checkout", roles: ["emp"], group: "Sell" },
  { to: "/sales", label: "My sales", icon: "receipt", roles: ["emp"], group: "Sell" },
  { to: "/approvals", label: "Approvals", icon: "approvals", roles: ["admin", "manager"], group: "Operations" },
  { to: "/stock", label: "Stock", icon: "stock", roles: ["admin", "manager"], group: "Operations" },
  { to: "/customers", label: "Customers", icon: "customers", roles: ["admin", "manager"], group: "Operations" },
  { to: "/employee-sales", label: "Employee sales", icon: "receipt", roles: ["admin", "manager"], group: "Operations" },
  { to: "/products", label: "Products", icon: "products", roles: ["manager"], group: "Catalog" },
  { to: "/reports", label: "Reports", icon: "reports", roles: ["emp", "admin", "manager"], group: "Insights" },
  { to: "/users", label: "Team", icon: "users", roles: ["manager"], group: "Administration" },
  { to: "/logs", label: "Activity & audit", icon: "logs", roles: ["manager"], group: "Administration" },
];

const GROUPS = ["Sell", "Operations", "Catalog", "Insights", "Administration"];
const HOME = { emp: "/checkout", admin: "/approvals", manager: "/reports" };
const SIMULATOR_ITEM = {
  to: "/payway-simulator",
  label: "ABA Simulator",
  icon: "qr",
  roles: ["admin", "manager"],
  group: "Operations",
};

function initials(name) {
  return (name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

function Layout() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [simulatorEnabled, setSimulatorEnabled] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!["admin", "manager"].includes(user.role)) return;
    api.get("/payments/config")
      .then(({ data }) => setSimulatorEnabled(!!data.simulator_enabled))
      .catch(() => setSimulatorEnabled(false));
  }, [user.role]);

  const menu = simulatorEnabled ? [...MENU, SIMULATOR_ITEM] : MENU;
  const current = menu.find((item) => item.to === location.pathname);

  return (
    <div className="layout">
      {menuOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="sidebar-brand">
          <div className="logo-mark">
            <Icon name="home" size={20} />
          </div>
          <div className="brand-text">
            <strong>House</strong>
            <span>Management</span>
          </div>
          <button
            type="button"
            className="icon-button sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {GROUPS.map((group) => {
            const items = menu.filter(
              (item) => item.group === group && item.roles.includes(user.role)
            );
            if (!items.length) return null;
            return (
              <div className="nav-section" key={group}>
                <span className="nav-label">{group}</span>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end
                    className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                  >
                    <Icon name={item.icon} size={18} />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-user">
          <div className="avatar">{initials(user.full_name)}</div>
          <div className="user-meta">
            <strong>{user.full_name}</strong>
            <span className={`badge ${user.role}`}>{user.role}</span>
          </div>
          <button
            type="button"
            className="icon-button"
            title="Change password"
            aria-label="Change password"
            onClick={() => setPasswordOpen(true)}
          >
            <Icon name="key" size={17} />
          </button>
          <button
            type="button"
            className="icon-button"
            title="Log out"
            aria-label="Log out"
            onClick={logout}
          >
            <Icon name="logout" size={17} />
          </button>
        </div>
      </aside>

      <div className="main-shell">
        <header className="mobile-topbar">
          <button
            type="button"
            className="icon-button"
            aria-label="Open navigation"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <span className="mobile-title">{current?.label || "House Management"}</span>
          <div className="avatar avatar-sm">{initials(user.full_name)}</div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>

      {passwordOpen && <ChangePasswordModal onClose={() => setPasswordOpen(false)} />}
    </div>
  );
}

function Guard({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={HOME[user.role]} replace />;
  return children;
}

export default function App() {
  const { user } = useAuth();
  const page = (roles, el) => <Guard roles={roles}>{el}</Guard>;

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={HOME[user.role]} replace /> : <Login />} />
      <Route element={<Guard><Layout /></Guard>}>
        <Route path="/checkout" element={page(["emp"], <Checkout />)} />
        <Route path="/sales" element={page(["emp"], <Sales />)} />
        <Route path="/approvals" element={page(["admin", "manager"], <Approvals />)} />
        <Route path="/stock" element={page(["admin", "manager"], <Stock />)} />
        <Route path="/customers" element={page(["admin", "manager"], <Customers />)} />
        <Route path="/employee-sales" element={page(["admin", "manager"], <EmployeeSales />)} />
        <Route path="/payway-simulator" element={page(["admin", "manager"], <PaywaySimulator />)} />
        <Route path="/products" element={page(["manager"], <Products />)} />
        <Route path="/reports" element={page(["emp", "admin", "manager"], <Reports />)} />
        <Route path="/users" element={page(["manager"], <Users />)} />
        <Route path="/logs" element={page(["manager"], <Logs />)} />
      </Route>
      <Route path="*" element={<Navigate to={user ? HOME[user.role] : "/login"} replace />} />
    </Routes>
  );
}
