import { useState } from "react";
import { useAuth } from "../auth.jsx";
import { errMsg } from "../api";
import Icon from "../components/Icon.jsx";

const FEATURES = [
  "Live stock and checkout controls",
  "Approval trail for high-value sales",
  "Daily reporting without the spreadsheet",
];

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <section className="auth-brand-panel">
        <div className="auth-brand">
          <div className="logo-mark logo-mark-lg">
            <Icon name="home" size={24} />
          </div>
          <div className="brand-text">
            <strong>House</strong>
            <span>Management</span>
          </div>
        </div>

        <div className="auth-copy">
          <span className="auth-eyebrow">Retail operations</span>
          <h1>Everything your store needs, in one calm place.</h1>
          <p>
            Keep stock accurate, approvals moving, and the day’s numbers close at hand —
            without juggling three tools.
          </p>
          <ul className="auth-features">
            {FEATURES.map((feature) => (
              <li key={feature}>
                <span className="feature-check"><Icon name="check" size={14} /></span>
                {feature}
              </li>
            ))}
          </ul>
        </div>

        <p className="auth-footnote">Built for small teams that care about the details.</p>
      </section>

      <section className="auth-form-panel">
        <form className="auth-card" onSubmit={submit}>
          <div className="auth-mobile-brand">
            <div className="logo-mark"><Icon name="home" size={19} /></div>
            <span>House Management</span>
          </div>

          <span className="eyebrow">Welcome back</span>
          <h2>Sign in to your workspace</h2>
          <p className="muted-text">Use the account your manager created for you.</p>

          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && <div className="alert error">{error}</div>}

          <button className="primary full auth-submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
            {!busy && <Icon name="arrowRight" size={17} />}
          </button>

          <p className="auth-help">Forgot your password? Ask a manager to reset it for you.</p>
        </form>
      </section>
    </div>
  );
}
