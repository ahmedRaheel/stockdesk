import { t as translate } from "./i18n";
import { useEffect, useRef, useState } from "react";
import { Plus, RefreshCw, Download, X, ArrowLeft } from "lucide-react";
import { api, send } from "./api";
import LookupSelect from "./LookupSelect";

type Customer = {
  id: string;
  name: string;
  phone: string;
  balance: number;
  credit_limit: number;
  credit_enabled: boolean;
};
type Props = {
  tenant: string;
  currency: string;
  approve: boolean;
  lookupAdmin: boolean;
  mode?: "khata" | "lookups";
  language: "en" | "ur";
};
const kinds = [
  ["category", "Categories"],
  ["unit", "Units"],
  ["payment_method", "Payment methods"],
  ["adjustment_reason", "Adjustment reasons"],
  ["return_reason", "Return reasons"],
  ["supplier_return_reason", "Supplier return reasons"],
  ["customer_segment", "Customer segments"],
];
const labels: Record<string, string> = {
  "Customers & khata": "گاہک اور کھاتہ",
  "New customer": "نیا گاہک",
  Recovery: "وصولی",
  "Credit requests": "ادھار کی منظوری",
  "Due & overdue": "واجب الادا",
  Statement: "کھاتہ کی تفصیل",
  Outstanding: "بقایا",
  "Credit limit": "ادھار کی حد",
  "Installment plan": "اقساط کا منصوبہ",
  "Payment promise": "ادائیگی کا وعدہ",
  Name: "نام",
  Phone: "فون",
  Amount: "رقم",
  Save: "محفوظ کریں",
  Close: "بند کریں",
  "Request credit": "ادھار کی درخواست",
  "Lookup management": "فہرستوں کا انتظام",
};
export default function Retail({
  tenant,
  currency,
  approve,
  lookupAdmin,
  mode = "khata",
  language,
}: Props) {
  const tr = (s: string) => (language === "ur" ? labels[s] || translate(s) : s);
  const money = (n: number) =>
    `${currency === "PKR" ? "Rs." : currency} ${(n / 100).toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const base = `/api/v1/tenants/${tenant}`;
  const [customers, setCustomers] = useState<Customer[]>([]),
    [requests, setRequests] = useState<any[]>([]),
    [overview, setOverview] = useState<any>(null),
    [statement, setStatement] = useState<any>(null),
    [kind, setKind] = useState("category"),
    [lookups, setLookups] = useState<any[]>([]),
    [tab, setTab] = useState("customers"),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [modal, setModal] = useState(""),
    [record, setRecord] = useState<any>(null),
    [notice, setNotice] = useState("");
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const [method, setMethod] = useState("");
  async function load(signal?: AbortSignal) {
    setLoading(true);
    setError("");
    try {
      if (mode === "lookups") {
        const d = await api<any>(
          `${base}/lookups?kind=${kind}&include_inactive=true&limit=50&offset=${page * 50}&q=${encodeURIComponent(query)}`,
          { signal },
        );
        setLookups(d.items);
      } else {
        const [c, r, o] = await Promise.all([
          api<any>(
            `${base}/customers?q=${encodeURIComponent(query)}&limit=50&offset=${page * 50}`,
            { signal },
          ),
          api<any>(`${base}/credit-requests`, { signal }),
          api<any>(`${base}/credit-overview`, { signal }),
        ]);
        setCustomers(c.items);
        setRequests(r.items);
        setOverview(o);
      }
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => load(controller.signal), 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [tenant, mode, query, page, kind]);
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement as HTMLElement;
    dialog.current?.querySelector<HTMLElement>("input,select,button")?.focus();
    return () => previous?.focus();
  }, [modal]);
  async function show(id: string) {
    setError("");
    try {
      setStatement(await api(`${base}/customers/${id}/statement`));
    } catch (e: any) {
      setError(e.message);
    }
  }
  function open(action: string, item: any = null) {
    setModal(action);
    setRecord(item);
    setError("");
    setNotice("");
    setMethod("");
    pending.current = null;
  }
  const field = (
    label: string,
    name: string,
    type = "text",
    value: any = "",
    required = true,
  ) => (
    <label className="field">
      <span>{tr(label)}</span>
      <input
        name={name}
        aria-label={label}
        type={type}
        defaultValue={value}
        required={required}
        min={type === "number" ? 0 : undefined}
        step={type === "number" ? "0.01" : undefined}
      />
    </label>
  );
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const f: any = Object.fromEntries(
      new FormData(event.currentTarget).entries(),
    );
    try {
      if (modal === "customer") await send(`${base}/customers`, f);
      if (modal === "credit")
        await send(`${base}/credit-requests`, {
          customer: record.id,
          proposed_limit: Math.round(Number(f.amount) * 100),
          reason: f.reason,
        });
      if (modal === "decision")
        await send(`${base}/credit-requests/${record.id}/decision`, f);
      if (modal === "recover") {
        const payload = {
          customer: record.id,
          amount: Math.round(Number(f.amount) * 100),
          method,
          reference: f.reference,
        };
        const signature = JSON.stringify(payload);
        if (pending.current?.signature !== signature)
          pending.current = { signature, id: crypto.randomUUID() };
        const response: any = await send(`${base}/recoveries`, {
          ...payload,
          request: pending.current.id,
        });
        setNotice(
          `Recovery ${response.id} recorded. Print its row from the customer statement.`,
        );
      }
      if (modal === "plan")
        await send(`${base}/installment-plans`, {
          receivable: f.receivable,
          frequency: f.frequency,
          installments: Number(f.installments),
          first_due: f.first_due,
          markup: Math.round(Number(f.markup) * 100),
        });
      if (modal === "promise")
        await send(`${base}/customers/${record.id}/promises`, {
          ...f,
          amount: Math.round(Number(f.amount) * 100),
        });
      if (modal === "lookup")
        await send(
          `${base}/lookups${record ? "/" + record.id : ""}`,
          {
            kind,
            code: f.code,
            name: f.name,
            name_ur: f.name_ur,
            sort_order: Number(f.sort_order),
            active: f.active === "on",
            fractional: kind === "unit" ? f.fractional === "on" : null,
          },
          record ? "PUT" : "POST",
        );
      setModal("");
      pending.current = null;
      await load();
      if (statement) await show(statement.customer.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const buckets = overview?.buckets || {};
  function printRecovery(payment: any) {
    const popup = window.open("", "_blank");
    if (!popup) {
      setError("Allow popups to print a receipt.");
      return;
    }
    const safe = (x: any) =>
      String(x).replace(
        /[&<>"']/g,
        (c) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[c]!,
      );
    popup.document.write(
      `<html><head><title>Recovery receipt</title></head><body style="font:14px Arial;max-width:600px;margin:40px auto"><h1>StockDesk / Recovery receipt</h1><p>${safe(statement.customer.name)}</p><p>Receipt: ${safe(payment.id)}</p><p>Date: ${safe(new Date(payment.created).toLocaleString())}</p><p>Payment: ${safe(money(payment.amount))} · ${safe(payment.method_name)}</p><p>Reference: ${safe(payment.reference)}</p><p>Current outstanding: ${safe(money(statement.balance))}</p><button onclick="window.print()">Print / Save PDF</button></body></html>`,
    );
    popup.document.close();
  }
  return (
    <div className="retail-feature" dir={language === "ur" ? "rtl" : "ltr"}>
      {error && !modal && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="operation-notice" role="status">
          {notice}
        </div>
      )}
      <div className="retail-toolbar">
        <div className="actions">
          {statement && (
            <button className="secondary" onClick={() => setStatement(null)}>
              <ArrowLeft size={16} />
              {tr("Customers & khata")}
            </button>
          )}
          <button
            className="secondary"
            disabled={loading}
            onClick={() => load()}
          >
            <RefreshCw size={16} /> {tr("Refresh")}{" "}
          </button>
          {mode === "lookups" ? (
            lookupAdmin && (
              <button className="primary" onClick={() => open("lookup")}>
                <Plus size={16} /> {tr("Add lookup")}{" "}
              </button>
            )
          ) : (
            <button className="primary" onClick={() => open("customer")}>
              <Plus size={16} />
              {tr("New customer")}
            </button>
          )}
        </div>
        <input
          className="retail-search"
          type="search"
          placeholder={tr("Search / تلاش / Roman Urdu")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
      </div>
      {mode === "lookups" ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>{tr("Lookup management")}</h2>
            <select
              aria-label={tr("Lookup type")}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setPage(0);
              }}
            >
              {kinds.map(([k, n]) => (
                <option key={k} value={k}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <p>
            {" "}
            {tr(
              "Codes are stable. Deactivate used values instead of deleting historical references.",
            )}{" "}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr("Code")}</th>
                  <th>{tr("Name")}</th>
                  <th>{tr("Urdu")}</th>
                  <th>{tr("Status")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lookups.map((l) => (
                  <tr key={l.id}>
                    <td>{l.code}</td>
                    <td>{l.name}</td>
                    <td dir="rtl">{l.name_ur}</td>
                    <td>{l.active ? "Active" : "Inactive"}</td>
                    <td>
                      <button
                        className="mini"
                        onClick={() => open("lookup", l)}
                      >
                        {" "}
                        {tr("Edit")}{" "}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : statement ? (
        <>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>{statement.customer.name}</h2>
                <p>
                  {statement.customer.phone} · {tr("Outstanding")}:{" "}
                  <b>{money(statement.balance)}</b>
                </p>
              </div>
              <a
                className="secondary"
                href={`${base}/customers/${statement.customer.id}/statement.pdf`}
                target="_blank"
                rel="noreferrer"
              >
                <Download size={15} /> {tr("PDF")}{" "}
              </a>
            </div>
            <div className="actions">
              <button
                className="primary"
                onClick={() => open("recover", statement.customer)}
              >
                {tr("Recovery")}
              </button>
              <button
                className="secondary"
                onClick={() => open("promise", statement.customer)}
              >
                {tr("Payment promise")}
              </button>
              {approve && (
                <button
                  className="secondary"
                  onClick={() => open("plan", statement)}
                >
                  {tr("Installment plan")}
                </button>
              )}
            </div>
            <div className="table-scroll retail-table">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Date")}</th>
                    <th>{tr("Entry")}</th>
                    <th>{tr("Reference")}</th>
                    <th>{tr("Debit / credit")}</th>
                    <th>{tr("Balance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.entries.map((e: any) => (
                    <tr key={e.id}>
                      <td>{new Date(e.created).toLocaleDateString()}</td>
                      <td>{e.kind}</td>
                      <td className="wrap">{e.reference}</td>
                      <td>{money(e.amount)}</td>
                      <td>{money(e.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel retail-table">
            <h2>{tr("Installments / اقساط")}</h2>
            <div className="table-scroll retail-table">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Due")}</th>
                    <th>{tr("Amount")}</th>
                    <th>{tr("Paid")}</th>
                    <th>{tr("Status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.schedule.map((s: any) => (
                    <tr key={s.id}>
                      <td>{s.due_date}</td>
                      <td>{money(s.amount)}</td>
                      <td>{money(s.paid)}</td>
                      <td>
                        {s.document_status === "cancelled"
                          ? "Cancelled"
                          : s.paid === s.amount
                            ? "Paid"
                            : "Outstanding"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel retail-table">
            <h2>{tr("Recovery receipts")}</h2>
            <div className="table-scroll retail-table">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Date")}</th>
                    <th>{tr("Amount")}</th>
                    <th>{tr("Method")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {statement.payments.map((p: any) => (
                    <tr key={p.id}>
                      <td>{new Date(p.created).toLocaleDateString()}</td>
                      <td>{money(p.amount)}</td>
                      <td>{p.method_name}</td>
                      <td>
                        <button
                          className="mini"
                          onClick={() => printRecovery(p)}
                        >
                          {" "}
                          {tr("Print receipt")}{" "}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel retail-table">
            <h2>{tr("Promises and recovery notes")}</h2>
            {statement.promises.map((p: any) => (
              <p key={p.id}>
                {p.promised_date} · {money(p.amount)} · {p.notes}
              </p>
            ))}
          </section>
        </>
      ) : (
        <>
          <div className="kpis">
            {[
              ["Not yet due", buckets.not_due],
              ["Due / 0–7 days", buckets.days_0_7],
              ["8–30 days overdue", buckets.days_8_30],
              ["31+ days overdue", buckets.days_31_plus],
            ].map(([label, value]) => (
              <div className="kpi" key={label}>
                <div>{label}</div>
                <strong>{money(Number(value) || 0)}</strong>
              </div>
            ))}
          </div>
          <div className="forecast-tabs">
            {[
              ["customers", "Customers & khata"],
              ["requests", "Credit requests"],
              ["dues", "Due & overdue"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                onClick={() => setTab(key)}
              >
                {tr(label)}
              </button>
            ))}
          </div>
          <section className="panel">
            {loading ? (
              <p role="status">{tr("Loading…")}</p>
            ) : (
              <div className="table-scroll">
                {tab === "customers" ? (
                  <table>
                    <thead>
                      <tr>
                        <th>{tr("Name")}</th>
                        <th>{tr("Phone")}</th>
                        <th>{tr("Credit limit")}</th>
                        <th>{tr("Outstanding")}</th>
                        <th>{tr("Actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {customers.map((c) => (
                        <tr key={c.id}>
                          <td>
                            <b>{c.name}</b>
                            <small>
                              {c.credit_enabled
                                ? "Credit enabled"
                                : "Approval required"}
                            </small>
                          </td>
                          <td>{c.phone}</td>
                          <td>{money(c.credit_limit)}</td>
                          <td>{money(c.balance)}</td>
                          <td>
                            <div className="actions">
                              <button
                                className="mini"
                                onClick={() => show(c.id)}
                              >
                                {tr("Statement")}
                              </button>
                              <button
                                className="mini"
                                onClick={() => open("recover", c)}
                              >
                                {tr("Recovery")}
                              </button>
                              <button
                                className="mini"
                                onClick={() => open("credit", c)}
                              >
                                {tr("Request credit")}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : tab === "requests" ? (
                  <table>
                    <thead>
                      <tr>
                        <th>{tr("Customer")}</th>
                        <th>{tr("Requested limit")}</th>
                        <th>{tr("Requested by")}</th>
                        <th>{tr("Status")}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {requests.map((r) => (
                        <tr key={r.id}>
                          <td>
                            {r.customer_name}
                            <small>{r.reason}</small>
                          </td>
                          <td>{money(r.proposed_limit)}</td>
                          <td>{r.requester}</td>
                          <td>{r.status}</td>
                          <td>
                            {approve && r.status === "pending" && (
                              <button
                                className="mini"
                                onClick={() => open("decision", r)}
                              >
                                {" "}
                                {tr("Review")}{" "}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>{tr("Customer")}</th>
                        <th>{tr("Due date")}</th>
                        <th>{tr("Amount")}</th>
                        <th>{tr("Days overdue")}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {overview?.dues.map((d: any, i: number) => (
                        <tr key={d.receivable + i}>
                          <td>{d.name}</td>
                          <td>{d.due_date}</td>
                          <td>{money(d.amount)}</td>
                          <td>{d.days_overdue}</td>
                          <td>
                            <button
                              className="mini"
                              onClick={() => show(d.customer)}
                            >
                              {" "}
                              {tr("Open khata")}{" "}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {tab === "dues" && (
              <p>
                {" "}
                {tr("Scheduled next 30 days:")}{" "}
                {money(overview?.scheduled_next30 || 0)}{" "}
                {tr(
                  ". These are contractual amounts, not guaranteed collections. Reminders are listed here; no external message is sent.",
                )}{" "}
              </p>
            )}
          </section>
        </>
      )}
      {!statement && (
        <div className="pagination">
          <span>
            {tr("Page")} {page + 1}
          </span>
          <div>
            <button
              className="mini"
              disabled={!page || loading}
              onClick={() => setPage(page - 1)}
            >
              {" "}
              {tr("Previous")}{" "}
            </button>
            <button
              className="mini"
              disabled={
                loading ||
                (mode === "lookups" ? lookups : customers).length < 50
              }
              onClick={() => setPage(page + 1)}
            >
              {" "}
              {tr("Next")}{" "}
            </button>
          </div>
        </div>
      )}
      {modal && (
        <div className="modal-overlay">
          <section
            ref={dialog}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="retail-title"
            onKeyDown={(e) => {
              if (e.key === "Escape" && !busy) setModal("");
              if (e.key === "Tab") {
                const nodes = [
                  ...(dialog.current?.querySelectorAll<HTMLElement>(
                    "button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]",
                  ) || []),
                ];
                const first = nodes[0],
                  last = nodes[nodes.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                }
                if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <div className="modal-heading">
              <h2 id="retail-title">
                {tr(
                  (
                    {
                      customer: "New customer",
                      credit: "Request credit",
                      recover: "Recovery",
                      plan: "Installment plan",
                      promise: "Payment promise",
                      lookup: "Lookup management",
                      decision: "Review credit request",
                    } as any
                  )[modal],
                )}
              </h2>
              <button
                className="icon-button"
                aria-label={tr("Close")}
                disabled={busy}
                onClick={() => setModal("")}
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={submit}>
              <fieldset disabled={busy}>
                {modal === "customer" && (
                  <>
                    {field("Name", "name")}
                    {field("Phone", "phone", "tel", "", false)}
                    {field(
                      "Roman Urdu / search aliases",
                      "search_aliases",
                      "text",
                      "",
                      false,
                    )}
                    {field("Address", "address", "text", "", false)}
                    {field(
                      "Reference contact (optional)",
                      "reference_contact",
                      "text",
                      "",
                      false,
                    )}
                  </>
                )}
                {modal === "credit" && (
                  <>
                    <p>
                      {record.name}
                      {tr(
                        ". A different authorized manager must approve this request.",
                      )}{" "}
                    </p>
                    {field(
                      "Credit limit",
                      "amount",
                      "number",
                      record.credit_limit / 100,
                    )}
                    {field("Reason", "reason")}
                  </>
                )}
                {modal === "decision" && (
                  <>
                    <p>
                      {record.customer_name} · {money(record.proposed_limit)}
                    </p>
                    <label className="field">
                      <span>{tr("Decision")}</span>
                      <select name="decision">
                        <option value="approved">{tr("Approve")}</option>
                        <option value="rejected">{tr("Reject")}</option>
                      </select>
                    </label>
                    {field("Decision reason", "note")}
                  </>
                )}
                {modal === "recover" && (
                  <>
                    <p>{record.name}</p>
                    {field("Amount", "amount", "number")}
                    <LookupSelect
                      tenant={tenant}
                      kind="payment_method"
                      label="Payment method"
                      value={method}
                      onChange={setMethod}
                      language={language}
                    />
                    {field("Payment reference", "reference", "text", "", false)}
                    <p className="hint">
                      {" "}
                      {tr(
                        "Confirm payment was collected. Wallet and bank methods record external receipts; this does not initiate a transfer. Retrying unchanged data is safe.",
                      )}{" "}
                    </p>
                  </>
                )}
                {modal === "promise" && (
                  <>
                    {field("Promise date", "promised_date", "date")}
                    {field("Amount", "amount", "number")}
                    {field("Recovery notes", "notes", "text", "", false)}
                  </>
                )}
                {modal === "plan" && (
                  <>
                    <label className="field">
                      <span>{tr("Outstanding invoice")}</span>
                      <select name="receivable" required>
                        <option value="">{tr("Choose invoice")}</option>
                        {record.documents
                          .filter(
                            (d: any) =>
                              d.status === "open" &&
                              d.balance > 0 &&
                              !record.schedule.some(
                                (s: any) => s.receivable === d.id,
                              ),
                          )
                          .map((d: any) => (
                            <option key={d.id} value={d.id}>
                              {d.invoice_number} · {money(d.balance)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>{tr("Frequency")}</span>
                      <select name="frequency">
                        <option value="weekly">{tr("Weekly")}</option>
                        <option value="fortnightly">{tr("Fortnightly")}</option>
                        <option value="monthly">{tr("Monthly")}</option>
                      </select>
                    </label>
                    {field(
                      "Number of installments",
                      "installments",
                      "number",
                      3,
                    )}
                    {field("First due date", "first_due", "date")}
                    {field(
                      "Agreed fixed markup (optional)",
                      "markup",
                      "number",
                      0,
                    )}
                    <p className="hint">
                      {" "}
                      {tr(
                        "A plan applies to the remaining invoice balance after the down payment. Markup is a fixed agreed amount, not a recurring rate.",
                      )}{" "}
                    </p>
                  </>
                )}
                {modal === "lookup" && (
                  <>
                    {kind === "unit" && (
                      <label className="checkbox">
                        <input
                          name="fractional"
                          type="checkbox"
                          defaultChecked={record?.fractional ?? false}
                        />
                        {tr("Allow fractional quantities")}
                      </label>
                    )}
                    {field(
                      "Code (immutable)",
                      "code",
                      "text",
                      record?.code || "",
                    )}
                    {field("Name", "name", "text", record?.name || "")}
                    {field(
                      "Urdu label",
                      "name_ur",
                      "text",
                      record?.name_ur || "",
                      false,
                    )}
                    {field(
                      "Sort order",
                      "sort_order",
                      "number",
                      record?.sort_order || 0,
                    )}
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        name="active"
                        defaultChecked={record?.active ?? true}
                      />{" "}
                      {tr("Active")}{" "}
                    </label>
                  </>
                )}
                {error && (
                  <div className="form-error" role="alert">
                    {error}
                  </div>
                )}
                <div className="modal-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setModal("")}
                  >
                    {tr("Close")}
                  </button>
                  <button className="primary" disabled={busy}>
                    {busy ? "Saving…" : tr("Save")}
                  </button>
                </div>
              </fieldset>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
