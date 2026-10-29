import { useEffect, useState } from "react";
import { Bell, CheckCircle2, RefreshCw, Plus, Settings2 } from "lucide-react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";
import "./alerts.css";

const labels: Record<string, string> = {
  low_stock: "Low stock",
  stock_out: "Out of stock",
  expiry: "Expiry",
  customer_overdue: "Overdue customer invoice",
  supplier_overdue: "Overdue supplier bill",
  cash_variance: "Cash discrepancy",
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
const label = (key: string) => tr(labels[key] || key);
const financial = (kind: string) =>
  ["customer_overdue", "supplier_overdue", "cash_variance"].includes(kind);
const initial = {
  name: "",
  kind: "low_stock",
  product: null as string | null,
  threshold: "",
  expiry_days: 30,
  minimum_amount: "0",
  overdue_days: 0,
  lookback_days: 30,
  severity: "warning",
  escalate_after_minutes: "",
  quiet_start: "",
  quiet_end: "",
  active: true,
};
const clock = (minutes: number | null) =>
  minutes == null
    ? ""
    : `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
const minutes = (value: string) =>
  value ? Number(value.slice(0, 2)) * 60 + Number(value.slice(3)) : null;
const dateTime = (value: string) => new Date(value).toLocaleString();
const amount = (value: unknown) =>
  (Number(value) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export default function InventoryAlerts({ tenant }: { tenant: string }) {
  const base = `/api/v1/tenants/${tenant}/alert-center`;
  const [rules, setRules] = useState<any[]>([]),
    [kinds, setKinds] = useState<string[]>([]),
    [currency, setCurrency] = useState("");
  const [data, setData] = useState<any>(null),
    [worker, setWorker] = useState(false),
    [tab, setTab] = useState("inbox");
  const [status, setStatus] = useState("open"),
    [escalated, setEscalated] = useState(false),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [form, setForm] = useState(initial),
    [editing, setEditing] = useState<any>(null),
    [editor, setEditor] = useState(false),
    [selected, setSelected] = useState<PurchaseOption>();
  const [ack, setAck] = useState(""),
    [note, setNote] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    setData(null);
    Promise.all([
      api<any>(base + "/rules", { signal: abort.signal }),
      api<any>(
        `${base}?status=${status}&escalated_only=${escalated}&offset=${page * 50}`,
        { signal: abort.signal },
      ),
    ])
      .then(([r, d]) => {
        setRules(r.items);
        setKinds(r.allowed_kinds);
        setCurrency(r.currency);
        setWorker(r.worker_enabled);
        setData(d);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [tenant, status, escalated, page, revision]);
  useEffect(() => {
    const timer = setInterval(() => setRevision((x) => x + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  async function action(path: string, payload: unknown, method = "POST") {
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
  function openEditor(rule?: any) {
    setEditing(rule || null);
    setSelected(
      rule?.product
        ? ({
            id: rule.product,
            name: rule.product_name,
            sku: rule.sku,
          } as PurchaseOption)
        : undefined,
    );
    setForm(
      rule
        ? {
            ...initial,
            ...rule,
            threshold: rule.threshold == null ? "" : String(rule.threshold),
            minimum_amount: String(rule.minimum_amount),
            escalate_after_minutes:
              rule.escalate_after_minutes == null
                ? ""
                : String(rule.escalate_after_minutes),
            quiet_start: clock(rule.quiet_start),
            quiet_end: clock(rule.quiet_end),
          }
        : initial,
    );
    setEditor(true);
    setTab("rules");
    setError("");
    setNotice("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    const payload = {
      name: form.name,
      kind: form.kind,
      product: financial(form.kind) ? null : form.product,
      threshold:
        form.kind === "low_stock" && form.threshold !== ""
          ? form.threshold
          : null,
      expiry_days: form.expiry_days,
      minimum_amount: financial(form.kind) ? form.minimum_amount : "0",
      overdue_days: form.overdue_days,
      lookback_days: form.lookback_days,
      severity: form.severity,
      active: form.active,
      escalate_after_minutes:
        form.severity !== "critical" && form.escalate_after_minutes !== ""
          ? Number(form.escalate_after_minutes)
          : null,
      quiet_start: minutes(form.quiet_start),
      quiet_end: form.quiet_end ? minutes(form.quiet_end) || 1440 : null,
      ...(editing ? { version: editing.version } : {}),
    };
    if (
      await action(
        editing ? `/rules/${editing.id}` : "/rules",
        payload,
        editing ? "PUT" : "POST",
      )
    )
      setEditor(false);
  }
  return (
    <div className="alert-center">
      <div className="alert-heading">
        <div>
          <h2>{tr("Monitor and respond")}</h2>
          <p>
            {tr("Review exceptions, assign follow-up and keep clear records.")}
          </p>
        </div>
        <button
          className="primary"
          onClick={() => openEditor()}
          disabled={busy}
        >
          <Plus size={17} />
          {tr("New alert rule")}
        </button>
      </div>
      <div className="alert-service">
        <span className={worker ? "alert-dot live" : "alert-dot"} />
        <span>
          {tr(
            worker
              ? "Automatic evaluation enabled (about every minute)."
              : "Manual evaluation mode. Use Evaluate alerts now.",
          )}
        </span>
      </div>
      <div className="alert-nav" aria-label={tr("Alert views")}>
        <button
          className={tab === "inbox" ? "selected" : ""}
          aria-pressed={tab === "inbox"}
          onClick={() => setTab("inbox")}
        >
          <Bell size={17} />
          {tr("Inbox")}
        </button>
        <button
          className={tab === "rules" ? "selected" : ""}
          aria-pressed={tab === "rules"}
          onClick={() => setTab("rules")}
        >
          <Settings2 size={17} />
          {tr("Alert rules")}
          <span>{rules.length}</span>
        </button>
        <button
          className="alert-refresh"
          disabled={busy}
          onClick={() => {
            setError("");
            setRevision((x) => x + 1);
          }}
        >
          <RefreshCw size={16} />
          {tr("Refresh")}
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && (
        <p className="alert-notice" role="status">
          <CheckCircle2 size={16} />
          {tr(notice)}
        </p>
      )}
      {tab === "inbox" ? (
        <section className="panel alert-inbox">
          <div className="alert-filters">
            <div className="alert-statuses">
              {["open", "acknowledged", "resolved", "all"].map((value) => (
                <button
                  key={value}
                  aria-pressed={status === value}
                  className={status === value ? "selected" : ""}
                  onClick={() => {
                    setStatus(value);
                    setPage(0);
                    setAck("");
                  }}
                >
                  {label(value)}
                </button>
              ))}
            </div>
            <button
              className="secondary"
              disabled={busy}
              onClick={async () => {
                if (await action("/evaluate", {}))
                  setNotice("Alerts evaluated.");
              }}
            >
              {tr("Evaluate alerts now")}
            </button>
          </div>
          <div className="alert-list-meta">
            <span>
              {data ? `${data.total} ${tr("matching alerts")}` : tr("Loading…")}
            </span>
            <label>
              <input
                type="checkbox"
                checked={escalated}
                onChange={(e) => {
                  setEscalated(e.target.checked);
                  setPage(0);
                }}
              />
              {tr("Escalated alerts only")}
            </label>
          </div>
          {!data ? (
            <p role="status">{tr("Loading…")}</p>
          ) : !data.items.length ? (
            <div className="alert-empty">
              <CheckCircle2 size={32} />
              <h3>{tr("No alerts in this view")}</h3>
              <p>{tr("Try another status or evaluate your active rules.")}</p>
            </div>
          ) : (
            <div className="alert-list">
              {data.items.map((a: any) => {
                const d =
                  typeof a.details === "string"
                    ? JSON.parse(a.details)
                    : a.details;
                return (
                  <article
                    className={`alert-card severity-${a.severity}`}
                    key={a.id}
                  >
                    <div className="alert-card-top">
                      <div>
                        <span className={`alert-badge ${a.severity}`}>
                          {label(a.severity)}
                        </span>
                        <span className="alert-kind">{label(a.kind)}</span>
                        <h3>{a.rule_name}</h3>
                        <p className="alert-record">
                          {d.name}
                          {d.sku && ` · ${d.sku}`}
                        </p>
                      </div>
                      <span className="alert-state">{label(a.status)}</span>
                    </div>
                    <div className="alert-evidence">
                      {financial(a.kind) ? (
                        <>
                          <strong>
                            {d.currency} {amount(d.amount)}
                          </strong>
                          {d.due_date && (
                            <span>
                              {tr("Due date")}: {d.due_date}
                            </span>
                          )}
                          {d.closed && (
                            <span>
                              {tr("Expected cash")}: {amount(d.expected_cash)} ·{" "}
                              {tr("Counted cash")}: {amount(d.counted_cash)}
                            </span>
                          )}
                          <span className="alert-reference">{d.reference}</span>
                        </>
                      ) : (
                        <>
                          <strong>
                            {d.stock} {d.unit}
                          </strong>
                          {d.threshold != null && (
                            <span>
                              {tr("Threshold")}: ≤ {d.threshold}
                            </span>
                          )}
                          {d.expires && (
                            <span>
                              {d.lot} · {tr("Expiry")}: {d.expires}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    <div className="alert-card-footer">
                      <span>
                        {tr("Opened")}: {dateTime(a.opened)}
                      </span>
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
                    </div>
                    {a.escalated_at && (
                      <p className="alert-history">
                        {tr("Escalated")}: {label(a.escalated_from)} →{" "}
                        {label(a.severity)} · {dateTime(a.escalated_at)} ·{" "}
                        {a.escalation_minutes} {tr("Unacknowledged minutes")}
                      </p>
                    )}
                    {a.acknowledged && (
                      <p className="alert-history">
                        {a.acknowledged_by} · {dateTime(a.acknowledged)}
                        <br />
                        {a.acknowledgement_note}
                      </p>
                    )}
                    {a.resolved && (
                      <p className="alert-history">
                        {label(a.resolution)} · {dateTime(a.resolved)}
                      </p>
                    )}
                    {ack === a.id && (
                      <form
                        className="alert-ack"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          if (await action(`/${ack}/acknowledge`, { note }))
                            setAck("");
                        }}
                      >
                        <label className="field">
                          {tr("Acknowledgement note")}
                          <textarea
                            autoFocus
                            required
                            maxLength={500}
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                          />
                        </label>
                        <div className="alert-actions">
                          <button className="primary" disabled={busy}>
                            {tr("Confirm acknowledgement")}
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            onClick={() => setAck("")}
                          >
                            {tr("Cancel")}
                          </button>
                        </div>
                      </form>
                    )}
                  </article>
                );
              })}
            </div>
          )}
          {data && data.total > 50 && (
            <div className="alert-pagination">
              <button
                className="secondary"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                {tr("Previous")}
              </button>
              <span>
                {page * 50 + 1}–{Math.min((page + 1) * 50, data.total)} /{" "}
                {data.total}
              </span>
              <button
                className="secondary"
                disabled={(page + 1) * 50 >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          )}
        </section>
      ) : (
        <section>
          {editor && (
            <form className="panel alert-editor" onSubmit={save}>
              <div className="alert-section-title">
                <h3>{tr(editing ? "Edit alert rule" : "New alert rule")}</h3>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditor(false)}
                >
                  {tr("Cancel")}
                </button>
              </div>
              <div className="form-grid">
                <label className="field">
                  {tr("Rule name")}
                  <input
                    autoFocus
                    required
                    maxLength={100}
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </label>
                <label className="field">
                  {tr("Alert condition")}
                  <select
                    aria-label={tr("Alert condition")}
                    value={form.kind}
                    onChange={(e) => {
                      setSelected(undefined);
                      setForm({
                        ...form,
                        kind: e.target.value,
                        product: null,
                        threshold: "",
                        minimum_amount: "0",
                      });
                    }}
                  >
                    {kinds.map((kind) => (
                      <option key={kind} value={kind}>
                        {label(kind)}
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
                    {["info", "warning", "critical"].map((value) => (
                      <option key={value} value={value}>
                        {label(value)}
                      </option>
                    ))}
                  </select>
                </label>
                {!financial(form.kind) && (
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
                )}
                {form.kind === "low_stock" && (
                  <label className="field">
                    {tr(
                      "Quantity threshold (blank uses product reorder level)",
                    )}
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
                        setForm({
                          ...form,
                          expiry_days: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                )}
                {financial(form.kind) && (
                  <label className="field">
                    {tr("Minimum amount")} ({currency})
                    <input
                      type="number"
                      required
                      min="0"
                      max="1000000000"
                      step="0.01"
                      value={form.minimum_amount}
                      onChange={(e) =>
                        setForm({ ...form, minimum_amount: e.target.value })
                      }
                    />
                  </label>
                )}
                {["customer_overdue", "supplier_overdue"].includes(
                  form.kind,
                ) && (
                  <label className="field">
                    {tr("Overdue grace days")}
                    <input
                      type="number"
                      required
                      min="0"
                      max="3650"
                      value={form.overdue_days}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          overdue_days: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                )}
                {form.kind === "cash_variance" && (
                  <label className="field">
                    {tr("Closed till lookback days")}
                    <input
                      type="number"
                      required
                      min="1"
                      max="365"
                      value={form.lookback_days}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          lookback_days: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                )}
              </div>
              <p className="hint">
                {tr(
                  financial(form.kind)
                    ? "Overdue rules use invoice balances after payments and credits. Zero grace days starts the day after the due date. Cash rules compare shortages and surpluses within the lookback window."
                    : "No product selection applies the rule to all active products. Expiry rules include already expired batches with remaining stock. No message is sent outside StockDesk.",
                )}
              </p>
              <details className="alert-advanced" open={Boolean(editing)}>
                <summary>{tr("Quiet hours and escalation")}</summary>
                <div className="form-grid">
                  <label className="field">
                    {tr("Quiet hours start (Karachi)")}
                    <input
                      type="time"
                      value={form.quiet_start}
                      onChange={(e) =>
                        setForm({ ...form, quiet_start: e.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    {tr("Quiet hours end (Karachi)")}
                    <input
                      type="time"
                      value={form.quiet_end}
                      onChange={(e) =>
                        setForm({ ...form, quiet_end: e.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    {tr("Escalate after minutes")}
                    <input
                      type="number"
                      min="1"
                      max="10080"
                      disabled={form.severity === "critical"}
                      value={form.escalate_after_minutes}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          escalate_after_minutes: e.target.value,
                        })
                      }
                    />
                  </label>
                </div>
                <p className="hint">
                  {tr(
                    "Quiet hours defer new alerts and escalation. Cleared conditions still resolve. Only unacknowledged alerts escalate; leave the interval blank to disable.",
                  )}
                </p>
              </details>
              <div className="alert-editor-footer">
                <label>
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) =>
                      setForm({ ...form, active: e.target.checked })
                    }
                  />
                  {tr("Active")}
                </label>
                <button className="primary" disabled={busy}>
                  {tr("Save alert rule")}
                </button>
              </div>
            </form>
          )}
          {!rules.length && !editor && (
            <div className="panel alert-empty">
              <Settings2 size={32} />
              <h3>{tr("No alert rules yet")}</h3>
              <p>
                {tr("Create a rule to monitor stock or financial exceptions.")}
              </p>
              <button className="primary" onClick={() => openEditor()}>
                {tr("New alert rule")}
              </button>
            </div>
          )}
          <div className="alert-rule-grid">
            {rules.map((r) => (
              <article className="panel alert-rule" key={r.id}>
                <div className="alert-card-top">
                  <span className="alert-kind">{label(r.kind)}</span>
                  <span className="alert-state">
                    {tr(r.active ? "Active" : "Inactive")}
                  </span>
                </div>
                <h3>{r.name}</h3>
                <p>
                  {r.product_name ||
                    tr(
                      financial(r.kind)
                        ? "Business financial records"
                        : "All products",
                    )}
                </p>
                {financial(r.kind) && (
                  <p>
                    {tr("Minimum amount")}: {currency}{" "}
                    {Number(r.minimum_amount).toFixed(2)}
                  </p>
                )}
                <p className="alert-history">
                  {tr("Last evaluated")}:{" "}
                  {r.last_evaluated ? dateTime(r.last_evaluated) : "—"}
                </p>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => openEditor(r)}
                >
                  {tr("Edit")}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
      <p className="alert-footnote">
        {tr(
          "Acknowledgement records follow-up only. It does not change inventory, payments or accounting balances.",
        )}
      </p>
    </div>
  );
}
