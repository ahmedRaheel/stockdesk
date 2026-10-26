import { useEffect, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";
const labels: Record<string, string> = {
  low_stock: "Low stock",
  stock_out: "Out of stock",
  expiry: "Expiry",
  info: "Information",
  warning: "Warning",
  critical: "Critical",
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
  all: "All",
  condition_cleared: "Condition cleared",
  rule_changed: "Rule changed",
};
const label = (value: string) => tr(labels[value] || value);
const initial = {
  name: "",
  kind: "low_stock",
  product: null as string | null,
  threshold: "",
  expiry_days: 30,
  severity: "warning",
  escalate_after_minutes: "",
  active: true,
};
export default function InventoryAlerts({ tenant }: { tenant: string }) {
  const base = `/api/v1/tenants/${tenant}/alert-center`;
  const [rules, setRules] = useState<any[]>([]),
    [form, setForm] = useState(initial),
    [editing, setEditing] = useState<any>(null),
    [selected, setSelected] = useState<PurchaseOption>(),
    [workerEnabled, setWorkerEnabled] = useState(false),
    [status, setStatus] = useState("open"),
    [escalatedOnly, setEscalatedOnly] = useState(false),
    [page, setPage] = useState(0),
    [data, setData] = useState<any>(null),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [ack, setAck] = useState(""),
    [note, setNote] = useState("");
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setError("");
    Promise.all([
      api<any>(base + "/rules", { signal: c.signal }),
      api<any>(
        `${base}?status=${status}&escalated_only=${escalatedOnly}&offset=${page * 50}`,
        {
          signal: c.signal,
        },
      ),
    ])
      .then(([r, d]) => {
        setRules(r.items);
        setWorkerEnabled(r.worker_enabled);
        setData(d);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [tenant, status, escalatedOnly, page, revision]);
  useEffect(() => {
    const timer = setInterval(() => setRevision((x) => x + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  async function action(path: string, payload: any, method = "POST") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await send(base + path, payload, method);
      setRevision((x) => x + 1);
      setNotice("Saved.");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  function reset() {
    setEditing(null);
    setSelected(undefined);
    setForm(initial);
  }
  return (
    <>
      <p>
        {tr(
          workerEnabled
            ? "Automatic evaluation enabled (about every minute)."
            : "Manual evaluation mode. Use Evaluate alerts now.",
        )}
      </p>
      <div className="toolbar">
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            if (await action("/evaluate", {})) setNotice("Alerts evaluated.");
          }}
        >
          {tr("Evaluate alerts now")}
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setRevision((x) => x + 1)}
        >
          {tr("Refresh")}
        </button>
      </div>
      <p>
        {tr(
          "Acknowledging an alert records ownership; it does not correct stock. Cleared conditions resolve on evaluation. Rule changes close existing episodes; recurring conditions create new alerts.",
        )}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      <section className="panel">
        <h2>{tr("Alert inbox")}</h2>
        <label className="field">
          {tr("Status")}
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            {["open", "acknowledged", "resolved", "all"].map((x) => (
              <option key={x} value={x}>
                {label(x)}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={escalatedOnly}
            onChange={(e) => {
              setEscalatedOnly(e.target.checked);
              setPage(0);
            }}
          />
          {tr("Escalated alerts only")}
        </label>
        {!data ? (
          <p>{tr("Loading…")}</p>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      "Rule",
                      "Product",
                      "Condition",
                      "Severity",
                      "Status",
                      "Opened",
                      "Action",
                    ].map((x) => (
                      <th key={x}>{label(x)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((a: any) => {
                    const d =
                      typeof a.details === "string"
                        ? JSON.parse(a.details)
                        : a.details;
                    return (
                      <tr key={a.id}>
                        <td>{a.rule_name}</td>
                        <td>
                          {d.sku} · {d.name}
                        </td>
                        <td>
                          {label(a.kind)} · {d.stock} {d.unit}
                          {d.threshold != null && <> ≤ {d.threshold}</>}
                          {d.expires && (
                            <>
                              {" "}
                              · {d.lot} · {d.expires}
                            </>
                          )}
                        </td>
                        <td>
                          {label(a.severity)}
                          {a.escalated_at && (
                            <p>
                              <strong>{tr("Escalated")}</strong> ·{" "}
                              {label(a.escalated_from)} → {label(a.severity)}
                              <br />
                              {new Date(a.escalated_at).toLocaleString()}
                              <br />
                              {tr("Unacknowledged minutes")}:{" "}
                              {a.escalation_minutes}
                            </p>
                          )}
                        </td>
                        <td>
                          {label(a.status)}
                          {a.acknowledged_by && (
                            <p>
                              {a.acknowledged_by}: {a.acknowledgement_note}
                            </p>
                          )}
                          {a.resolution && <p>{label(a.resolution)}</p>}
                        </td>
                        <td>{new Date(a.opened).toLocaleString()}</td>
                        <td>
                          {a.status === "open" && (
                            <button
                              className="secondary"
                              disabled={busy}
                              onClick={() => {
                                setAck(a.id);
                                setNote("");
                              }}
                            >
                              {tr("Acknowledge")}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!data.items.length && <p>{tr("No matching records.")}</p>}
            </div>
            <div className="toolbar">
              <button
                className="secondary"
                disabled={busy || !page}
                onClick={() => setPage(page - 1)}
              >
                {tr("Previous")}
              </button>
              <span>
                {data.total} {tr("Alerts")}
              </span>
              <button
                className="secondary"
                disabled={busy || (page + 1) * 50 >= data.total}
                onClick={() => setPage(page + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </>
        )}
        {ack && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (await action(`/${ack}/acknowledge`, { note })) setAck("");
            }}
          >
            <label className="field">
              {tr("Acknowledgement note")}
              <textarea
                required
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button className="primary" disabled={busy}>
              {tr("Confirm acknowledgement")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => setAck("")}
            >
              {tr("Cancel")}
            </button>
          </form>
        )}
      </section>
      <section className="panel">
        <h2>{tr(editing ? "Edit alert rule" : "New alert rule")}</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const payload = {
              ...form,
              escalate_after_minutes:
                form.severity !== "critical" &&
                form.escalate_after_minutes !== ""
                  ? Number(form.escalate_after_minutes)
                  : null,
              threshold:
                form.kind === "low_stock" && form.threshold !== ""
                  ? Number(form.threshold)
                  : null,
              ...(editing ? { version: editing.version } : {}),
            };
            if (
              await action(
                editing ? `/rules/${editing.id}` : "/rules",
                payload,
                editing ? "PUT" : "POST",
              )
            )
              reset();
          }}
        >
          <div className="form-grid">
            <label className="field">
              {tr("Rule name")}
              <input
                required
                maxLength={100}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label className="field">
              {tr("Alert condition")}
              <select
                value={form.kind}
                onChange={(e) =>
                  setForm({ ...form, kind: e.target.value, threshold: "" })
                }
              >
                {["low_stock", "stock_out", "expiry"].map((x) => (
                  <option key={x} value={x}>
                    {label(x)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {tr("Severity")}
              <select
                value={form.severity}
                onChange={(e) =>
                  setForm({
                    ...form,
                    severity: e.target.value,
                    escalate_after_minutes:
                      e.target.value === "critical"
                        ? ""
                        : form.escalate_after_minutes,
                  })
                }
              >
                {["info", "warning", "critical"].map((x) => (
                  <option key={x} value={x}>
                    {label(x)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {tr("Escalate to critical after minutes (optional)")}
              <input
                type="number"
                min="1"
                max="10080"
                step="1"
                disabled={form.severity === "critical"}
                value={form.escalate_after_minutes}
                onChange={(e) =>
                  setForm({ ...form, escalate_after_minutes: e.target.value })
                }
              />
            </label>
            <PurchaseLookup
              tenant={tenant}
              kind="products"
              required={false}
              value={form.product || ""}
              selected={selected}
              onChange={(p) => {
                setSelected(p);
                setForm({ ...form, product: p?.id || null });
              }}
            />
            {form.kind === "low_stock" && (
              <label className="field">
                {tr("Quantity threshold (blank uses product reorder level)")}
                <input
                  type="number"
                  min="0"
                  max="1000000000"
                  step="0.001"
                  value={form.threshold}
                  onChange={(e) =>
                    setForm({ ...form, threshold: e.target.value })
                  }
                />
              </label>
            )}
            {form.kind === "expiry" && (
              <label className="field">
                {tr("Expiry window (days)")}
                <input
                  type="number"
                  required
                  min="0"
                  max="365"
                  value={form.expiry_days}
                  onChange={(e) =>
                    setForm({ ...form, expiry_days: Number(e.target.value) })
                  }
                />
              </label>
            )}
            <label>
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })}
              />
              {tr("Active")}
            </label>
          </div>
          <p>
            {tr(
              "No product selection applies the rule to all active products. Expiry rules include already expired batches with remaining stock. No message is sent outside StockDesk.",
            )}
          </p>
          <p className="hint">
            {tr(
              "Escalation raises unacknowledged open alerts to critical on evaluation. Acknowledged or cleared alerts do not escalate. Leave blank to disable.",
            )}
          </p>
          <button className="primary" disabled={busy}>
            {tr("Save alert rule")}
          </button>
          {editing && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={reset}
            >
              {tr("Cancel")}
            </button>
          )}
        </form>
      </section>
      <section className="panel">
        <h2>{tr("Alert rules")}</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "Rule",
                  "Condition",
                  "Product",
                  "Active",
                  "Last evaluated",
                  "Action",
                ].map((x) => (
                  <th key={x}>{label(x)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>{label(r.kind)}</td>
                  <td>{r.product_name || tr("All products")}</td>
                  <td>{tr(r.active ? "Yes" : "No")}</td>
                  <td>
                    {r.last_evaluated
                      ? new Date(r.last_evaluated).toLocaleString()
                      : "—"}
                  </td>
                  <td>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditing(r);
                        setForm({
                          name: r.name,
                          kind: r.kind,
                          product: r.product,
                          threshold:
                            r.threshold == null ? "" : String(r.threshold),
                          expiry_days: r.expiry_days,
                          severity: r.severity,
                          escalate_after_minutes:
                            r.escalate_after_minutes == null
                              ? ""
                              : String(r.escalate_after_minutes),
                          active: r.active,
                        });
                        setSelected(
                          r.product
                            ? {
                                id: r.product,
                                name: r.product_name,
                                sku: r.sku,
                              }
                            : undefined,
                        );
                      }}
                    >
                      {tr("Edit")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
