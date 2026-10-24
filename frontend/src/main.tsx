import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Boxes, ShieldCheck, ArrowRight, Loader2 } from "lucide-react";
import Workspace from "./Workspace";
import ErrorBoundary from "./ErrorBoundary";
import "./styles.css";
function App() {
  const [user, setUser] = useState<any>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setUser(d?.user || null))
      .catch(() => setError("The server could not be reached."))
      .finally(() => setLoading(false));
  }, []);
  async function login(e: any) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          Object.fromEntries(new FormData(e.target).entries()),
        ),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      setUser(d.user);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }
  if (loading)
    return (
      <div className="auth-page">
        <Loader2 className="spin" /> Connecting…
      </div>
    );
  if (user) return <Workspace onLogout={logout} />;
  return (
    <div className="auth-page">
      <div className="auth-story">
        <div className="brand">
          <span>
            <Boxes size={26} />
          </span>
          StockDesk
        </div>
        <div className="eyebrow">INVENTORY & POINT OF SALE</div>
        <h1>
          Retail operations,
          <br />
          under control.
        </h1>
        <p>
          Inventory, purchasing, and point of sale.
          <br />
          One workspace for the people running your store.
        </p>
        <div className="auth-feature">
          <ShieldCheck size={20} />
          StockDesk / Operations console
        </div>
      </div>
      <section className="auth-card">
        <div className="eyebrow">WELCOME BACK</div>
        <h2>Sign in to your workspace</h2>
        <p>Use the account provided by your business owner.</p>
        <form onSubmit={login}>
          <label className="field">
            <span>Email address</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              disabled={busy}
            />
          </label>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            {busy ? (
              <Loader2 className="spin" size={17} />
            ) : (
              <ArrowRight size={17} />
            )}
            Sign in
          </button>
        </form>
        <small>
          Need access? Contact your business owner or platform administrator.
        </small>
      </section>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
