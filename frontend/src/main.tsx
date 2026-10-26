import { t as tr } from "./i18n";
import { useLanguage } from "./i18n";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Boxes, ShieldCheck, ArrowRight, Loader2 } from "lucide-react";
import Workspace from "./Workspace";
import ErrorBoundary from "./ErrorBoundary";
import "./styles.css";
function App() {
  const [language, setLanguage] = useLanguage();
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
  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key === "stockdesk-session-change") window.location.reload();
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
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
        <Loader2 className="spin" /> {tr("Connecting…")}{" "}
      </div>
    );
  if (user) return <Workspace onLogout={logout} />;
  return (
    <div className="auth-page">
      <div className="auth-story">
        <div className="brand">
          <span>
            <Boxes size={26} />
          </span>{" "}
          {tr("StockDesk")}{" "}
        </div>
        <div className="eyebrow">{tr("INVENTORY & POINT OF SALE")}</div>
        <h1>
          {" "}
          {tr("Retail operations,")} <br /> {tr("under control.")}{" "}
        </h1>
        <p>
          {" "}
          {tr("Inventory, purchasing, and point of sale.")} <br />{" "}
          {tr("One workspace for the people running your store.")}{" "}
        </p>
        <div className="auth-feature">
          <ShieldCheck size={20} /> {tr("StockDesk / Operations console")}{" "}
        </div>
      </div>
      <section className="auth-card">
        <button
          type="button"
          className="secondary"
          onClick={() => setLanguage(language === "en" ? "ur" : "en")}
        >
          {language === "en" ? "اردو" : tr("English")}
        </button>
        <div className="eyebrow">{tr("WELCOME BACK")}</div>
        <h2>{tr("Sign in to your workspace")}</h2>
        <p>{tr("Use the account provided by your business owner.")}</p>
        <form onSubmit={login}>
          <label className="field">
            <span>{tr("Email address")}</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>{tr("Password")}</span>
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
            )}{" "}
            {tr("Sign in")}{" "}
          </button>
        </form>
        <small>
          {" "}
          {tr(
            "Need access? Contact your business owner or platform administrator.",
          )}{" "}
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
