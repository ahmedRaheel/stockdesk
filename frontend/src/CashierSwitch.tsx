import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
export default function CashierSwitch({
  tenant,
  userId,
  pinSession,
  blocked,
  canManage,
}: {
  tenant: string;
  userId: string;
  pinSession: boolean;
  blocked: boolean;
  canManage: boolean;
}) {
  const [opened, setOpened] = useState(false),
    [cashiers, setCashiers] = useState<any[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!opened) return;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current
      ?.querySelector<HTMLElement>("button, select, input")
      ?.focus();
    return () => previous?.focus();
  }, [opened]);
  const base = `/api/v1/tenants/${tenant}/cashiers`;
  async function load() {
    const data = await api<{ items: any[] }>(base);
    setCashiers(data.items);
  }
  useEffect(() => {
    setOpened(false);
    setCashiers([]);
    setError("");
    setMessage("");
  }, [tenant]);
  async function show() {
    setOpened(true);
    setError("");
    try {
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function submit(e: React.FormEvent<HTMLFormElement>, action: string) {
    e.preventDefault();
    if (busy || (action === "switch" && blocked)) return;
    const form = e.currentTarget,
      values = Object.fromEntries(new FormData(form));
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await send(
        base + (action === "switch" ? "/switch" : "/pin"),
        values,
        action === "switch" ? "POST" : "PUT",
      );
      form.reset();
      if (action === "switch") {
        localStorage.setItem("stockdesk-session-change", String(Date.now()));
        window.location.reload();
      } else {
        await load();
        setMessage(
          tr("Cashier PIN saved. Previous PIN sessions were revoked."),
        );
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    try {
      await api(base + `/${id}/pin`, { method: "DELETE" });
      await load();
      setMessage(tr("Cashier PIN revoked."));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const pin = (
    <label className="field">
      <span>{tr("Cashier PIN")}</span>
      <input
        name="pin"
        type="password"
        inputMode="numeric"
        pattern="[0-9]{6,12}"
        minLength={6}
        maxLength={12}
        autoComplete="off"
        required
      />
    </label>
  );
  return (
    <>
      <button className="secondary" disabled={blocked} onClick={show}>
        {tr("Switch cashier")}
      </button>
      {opened && (
        <div className="modal-overlay">
          <section
            className="modal cashier-dialog"
            ref={dialog}
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) {
                event.preventDefault();
                setOpened(false);
              }
              if (event.key === "Tab") {
                const nodes = Array.from(
                  dialog.current?.querySelectorAll<HTMLElement>(
                    "button:not(:disabled), input:not(:disabled), select:not(:disabled)",
                  ) || [],
                ).filter((n) => !n.closest("fieldset:disabled"));
                const first = nodes[0],
                  last = nodes[nodes.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last?.focus();
                }
                if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first?.focus();
                }
              }
            }}
            role="dialog"
            aria-modal="true"
            aria-label={tr("Switch cashier")}
            style={{ maxHeight: "90vh", overflowY: "auto" }}
          >
            <div className="modal-heading">
              <h2>{tr("Switch cashier")}</h2>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setOpened(false)}
              >
                {tr("Close")}
              </button>
            </div>
            <p>
              {tr(
                "Hold or clear the current bill before switching. Each cashier keeps their own till and held bills.",
              )}
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {message && <p role="status">{message}</p>}
            <form onSubmit={(e) => submit(e, "switch")}>
              <fieldset disabled={busy || blocked}>
                <label className="field">
                  <span>{tr("Cashier")}</span>
                  <select name="user_id" aria-label={tr("Cashier")} required>
                    <option value="">{tr("Select cashier")}</option>
                    {cashiers
                      .filter((c) => c.pin_enabled)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                  </select>
                </label>
                {pin}
                <button className="primary">{tr("Sign in with PIN")}</button>
              </fieldset>
            </form>
            {cashiers.some((c) => c.id === userId) && !pinSession && (
              <form onSubmit={(e) => submit(e, "setup")}>
                <fieldset disabled={busy}>
                  <h3>{tr("Set my cashier PIN")}</h3>
                  <p className="hint">
                    {tr(
                      "Use 6–12 digits. Your account password is required to set or replace your PIN.",
                    )}
                  </p>
                  <label className="field">
                    <span>{tr("Current password")}</span>
                    <input
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      minLength={12}
                      maxLength={128}
                    />
                  </label>
                  {pin}
                  <button className="primary">{tr("Save PIN")}</button>
                </fieldset>
              </form>
            )}
            {cashiers
              .filter(
                (c) =>
                  c.pin_enabled &&
                  (canManage || (c.id === userId && !pinSession)),
              )
              .map((c) => (
                <p key={c.id}>
                  {c.name}{" "}
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => revoke(c.id)}
                  >
                    {tr("Revoke PIN")}
                  </button>
                </p>
              ))}
            {pinSession && (
              <p className="hint">
                {tr(
                  "This PIN session is restricted to this business. Sign out and use your password to manage your PIN.",
                )}
              </p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
