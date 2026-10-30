import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
import CustomerSelect from "./CustomerSelect";
import "./recovery-desk.css";

type Case = {
  id: string;
  version: number;
  assigned_to: string;
  agent_name: string;
  agent_available: boolean;
  receivable: string;
  customer_name: string;
  phone: string;
  invoice_number: string;
  invoice_due: string;
  balance: number;
  next_follow_up: string;
  status: string;
  queue_status: string;
};
type Agent = { id: string; name: string };
type History = {
  id: string;
  kind: string;
  note: string;
  actor_name: string;
  created: string;
  version: number;
  details: {
    agent_name?: string;
    next_follow_up?: string;
    promised_on?: string;
    promised_amount?: number;
    before?: { status: string };
    after?: { status: string; next_follow_up: string; agent_name?: string };
  };
};
type Invoice = {
  id: string;
  invoice_number: string;
  balance: number;
  status: string;
};
const statuses: Record<string, string> = {
  due: "Follow-up due",
  upcoming: "Upcoming follow-up",
  settled: "Invoice settled",
  closed: "Case closed",
  cancelled: "Case cancelled",
  all: "All cases",
  open: "Open case",
};
const outcomes: Record<string, string> = {
  contacted: "Contacted",
  no_answer: "No answer",
  visited: "Visited",
  disputed: "Disputed",
  promise: "Payment promise",
  note: "Recovery note",
  created: "Case created",
  updated: "Case updated",
};
function localTime(value: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const p = (kind: string) => parts.find((v) => v.type === kind)?.value;
  return `${p("year")}-${p("month")}-${p("day")}T${p("hour")}:${p("minute")}`;
}
export default function RecoveryDesk({
  tenant,
  currency,
  onCustomer,
}: {
  tenant: string;
  currency: string;
  onCustomer: (id: string) => void;
}) {
  const base = `/api/v1/tenants/${tenant}`,
    url = base + "/recovery-cases";
  const [data, setData] = useState<{
    items: (Case & { customer: string })[];
    counts: Record<string, number>;
    can_manage: boolean;
    user_id: string;
  }>({ items: [], counts: {}, can_manage: false, user_id: "" });
  const [state, setState] = useState("due"),
    [mine, setMine] = useState(false),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [listError, setListError] = useState("");
  const [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Case | null>(null),
    [mode, setMode] = useState<
      "create" | "manage" | "activity" | "history" | null
    >(null);
  const [customer, setCustomer] = useState(""),
    [documents, setDocuments] = useState<Invoice[]>([]),
    [agents, setAgents] = useState<Agent[]>([]),
    [agentQuery, setAgentQuery] = useState("");
  const [history, setHistory] = useState<History[]>([]),
    [historyPage, setHistoryPage] = useState(0),
    [historyLoading, setHistoryLoading] = useState(false),
    [outcome, setOutcome] = useState("contacted");
  const editor = useRef<HTMLDivElement>(null),
    pending = useRef<{ signature: string; id: string } | null>(null);
  const money = (n: number) =>
    new Intl.NumberFormat("en", { style: "currency", currency }).format(
      n / 100,
    );
  const time = (value: string) =>
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Karachi",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    const timer = setTimeout(
      () =>
        api<typeof data>(
          `${url}?state=${state}&mine=${mine}&q=${encodeURIComponent(query)}&offset=${page * 30}`,
          { signal: c.signal },
        )
          .then((r) => {
            if (!c.signal.aborted) {
              setData(r);
              setListError("");
            }
          })
          .catch((e) => {
            if (!c.signal.aborted) setListError(e.message);
          })
          .finally(() => {
            if (!c.signal.aborted) setLoading(false);
          }),
      200,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, state, mine, query, page, revision]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") setRevision((v) => v + 1);
    }, 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const c = new AbortController();
    setDocuments([]);
    if (customer && mode === "create")
      api<{ documents: Invoice[] }>(`${base}/customers/${customer}/statement`, {
        signal: c.signal,
      })
        .then((r) => {
          if (!c.signal.aborted)
            setDocuments(
              r.documents.filter((d) => d.status === "open" && d.balance > 0),
            );
        })
        .catch((e) => {
          if (!c.signal.aborted) setError(e.message);
        });
    return () => c.abort();
  }, [customer, tenant, mode]);
  useEffect(() => {
    const c = new AbortController();
    if (mode !== "create" && mode !== "manage") return () => c.abort();
    const timer = setTimeout(
      () =>
        api<{ items: Agent[] }>(
          `${url}/agents?q=${encodeURIComponent(agentQuery)}`,
          { signal: c.signal },
        )
          .then((r) => {
            if (!c.signal.aborted) setAgents(r.items);
          })
          .catch((e) => {
            if (!c.signal.aborted) setError(e.message);
          }),
      200,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [mode, tenant, agentQuery]);
  useEffect(() => {
    const c = new AbortController();
    setHistory([]);
    if (!selected || !mode) return () => c.abort();
    setHistoryLoading(true);
    api<{ items: History[] }>(
      `${url}/${selected.id}/history?offset=${historyPage * 30}`,
      { signal: c.signal },
    )
      .then((r) => {
        if (!c.signal.aborted) setHistory(r.items);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setHistoryLoading(false);
      });
    return () => c.abort();
  }, [tenant, selected?.id, mode, historyPage, revision]);
  useEffect(() => {
    if (mode) {
      editor.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      editor.current?.focus();
    }
  }, [mode, selected?.id]);
  function open(next: typeof mode, row: Case | null = null) {
    setSelected(row);
    setMode(next);
    setError("");
    setNotice("");
    setHistoryPage(0);
    setAgentQuery("");
    setAgents([]);
    setCustomer("");
    setOutcome("contacted");
    pending.current = null;
  }
  function refresh() {
    setMode(null);
    setError("");
    setRevision((v) => v + 1);
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const f = new FormData(e.currentTarget),
      next_follow_up = String(f.get("next_follow_up")) + "+05:00";
    let payload: Record<string, unknown> = {
      note: f.get("note"),
      next_follow_up,
    };
    let path = url,
      method = "POST";
    if (mode === "create")
      payload = {
        ...payload,
        receivable: f.get("receivable"),
        assigned_to: f.get("assigned_to"),
      };
    else if (selected) {
      payload = { ...payload, version: selected.version };
      path += `/${selected.id}`;
      if (mode === "manage") {
        method = "PUT";
        payload = {
          ...payload,
          assigned_to: f.get("assigned_to"),
          status: f.get("status"),
        };
      } else {
        path += "/activities";
        payload = {
          ...payload,
          outcome,
          promised_on: outcome === "promise" ? f.get("promised_on") : null,
          promised_amount:
            outcome === "promise"
              ? Math.round(Number(f.get("promised_amount")) * 100)
              : null,
        };
      }
    } else return;
    const signature = JSON.stringify({ path, method, payload });
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: newRequestId() };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await send(path, { ...payload, request: pending.current.id }, method);
      setMode(null);
      setNotice("Recovery follow-up saved.");
      setRevision((v) => v + 1);
      pending.current = null;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel recovery-desk">
      <div className="recovery-heading">
        <div>
          <h2>{tr("Recovery follow-ups")}</h2>
          <p>
            {tr(
              "Assign responsibility, plan the next contact, and retain a clear recovery history.",
            )}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            disabled={busy || loading}
            onClick={refresh}
          >
            {tr("Reload cases")}
          </button>
          {data.can_manage && (
            <button
              className="primary"
              disabled={busy}
              onClick={() => open("create")}
            >
              {tr("Plan recovery")}
            </button>
          )}
        </div>
      </div>
      <p className="hint">
        {tr(
          "Times use Asia/Karachi. Due reminders update every minute while this page is visible. Notes and promises do not record payments or send messages.",
        )}
      </p>
      <div className="recovery-filters">
        {Object.entries(statuses)
          .filter(([key]) => key !== "open")
          .map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={state === key ? "primary" : "secondary"}
              aria-pressed={state === key}
              onClick={() => {
                setState(key);
                setPage(0);
              }}
            >
              {tr(label)}{" "}
              <b>
                {key === "all"
                  ? Object.values(data.counts).reduce((a, b) => a + b, 0)
                  : data.counts[key] || 0}
              </b>
            </button>
          ))}
      </div>
      <div className="form-grid">
        <label className="field">
          <span>{tr("Search recovery cases")}</span>
          <input
            value={query}
            maxLength={100}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder={tr("Customer, invoice or agent")}
          />
        </label>
        <label className="recovery-mine">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => {
              setMine(e.target.checked);
              setPage(0);
            }}
          />
          {tr("Assigned to me")}
        </label>
      </div>
      {(error || listError) && (
        <p role="alert" className="form-error">
          {tr(error || listError)}
        </p>
      )}
      {notice && (
        <p role="status" className="operation-notice">
          {tr(notice)}
        </p>
      )}
      {mode && (
        <div className="recovery-editor" ref={editor} tabIndex={-1}>
          <div className="recovery-heading">
            <h3>
              {tr(
                mode === "create"
                  ? "Plan recovery"
                  : mode === "manage"
                    ? "Manage recovery case"
                    : mode === "activity"
                      ? "Record contact outcome"
                      : "Recovery history",
              )}
            </h3>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => setMode(null)}
            >
              {tr("Close")}
            </button>
          </div>
          {selected && (
            <p>
              <strong>
                {selected.customer_name} · {selected.invoice_number}
              </strong>{" "}
              · {tr("Outstanding")}: {money(selected.balance)}
            </p>
          )}
          {mode !== "history" && (
            <form onSubmit={submit} key={`${mode}:${selected?.id || "new"}`}>
              <fieldset disabled={busy}>
                {mode === "create" && (
                  <>
                    <CustomerSelect
                      tenant={tenant}
                      value={customer}
                      onChange={setCustomer}
                    />
                    <label className="field">
                      <span>{tr("Outstanding invoice")}</span>
                      <select
                        aria-label={tr("Outstanding invoice")}
                        name="receivable"
                        required
                        key={customer}
                        defaultValue=""
                      >
                        <option value="">{tr("Select invoice")}</option>
                        {documents.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.invoice_number} · {money(d.balance)}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
                <div className="form-grid">
                  {(mode === "create" || mode === "manage") && (
                    <div>
                      <label className="field">
                        <span>{tr("Find recovery agent")}</span>
                        <input
                          value={agentQuery}
                          maxLength={100}
                          onChange={(e) => setAgentQuery(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>{tr("Assigned recovery agent")}</span>
                        <select
                          aria-label={tr("Assigned recovery agent")}
                          name="assigned_to"
                          required
                          defaultValue={selected?.assigned_to || ""}
                        >
                          <option value="">{tr("Select agent")}</option>
                          {selected &&
                            !agents.some(
                              (a) => a.id === selected.assigned_to,
                            ) && (
                              <option value={selected.assigned_to}>
                                {selected.agent_name}
                              </option>
                            )}
                          {agents.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <small>
                        {tr(
                          "First 50 eligible agents; search to narrow results.",
                        )}
                      </small>
                    </div>
                  )}
                  {mode === "manage" && (
                    <label className="field">
                      <span>{tr("Case status")}</span>
                      <select
                        aria-label={tr("Case status")}
                        name="status"
                        defaultValue={selected?.status}
                      >
                        {["open", "closed", "cancelled"].map((s) => (
                          <option key={s} value={s}>
                            {tr(statuses[s])}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {mode === "activity" && (
                    <label className="field">
                      <span>{tr("Contact outcome")}</span>
                      <select
                        aria-label={tr("Contact outcome")}
                        value={outcome}
                        onChange={(e) => setOutcome(e.target.value)}
                      >
                        {Object.entries(outcomes)
                          .filter(([k]) => !["created", "updated"].includes(k))
                          .map(([key, label]) => (
                            <option key={key} value={key}>
                              {tr(label)}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                  <label className="field">
                    <span>{tr("Next follow-up (Karachi)")}</span>
                    <input
                      name="next_follow_up"
                      type="datetime-local"
                      required
                      defaultValue={localTime(
                        selected?.next_follow_up || new Date().toISOString(),
                      )}
                    />
                  </label>
                  {mode === "activity" && outcome === "promise" && (
                    <>
                      <label className="field">
                        <span>{tr("Promised date")}</span>
                        <input name="promised_on" type="date" required />
                      </label>
                      <label className="field">
                        <span>
                          {tr("Promised amount")} ({currency})
                        </span>
                        <input
                          name="promised_amount"
                          type="number"
                          min="0.01"
                          max={(selected?.balance || 0) / 100}
                          step="0.01"
                          required
                        />
                      </label>
                    </>
                  )}
                </div>
                <label className="field">
                  <span>{tr("Recovery note")}</span>
                  <textarea
                    name="note"
                    required
                    maxLength={2000}
                    rows={3}
                    dir="auto"
                  />
                </label>
                <p className="hint">
                  {tr(
                    "Use the existing Recovery payment action to record money received. Closing a case does not waive its debt.",
                  )}
                </p>
                <button className="primary" disabled={busy}>
                  {tr(busy ? "Saving…" : "Save follow-up")}
                </button>
              </fieldset>
            </form>
          )}
          {selected && (
            <div className="recovery-history">
              <h4>{tr("Recovery history")}</h4>
              {historyLoading ? (
                <p role="status">{tr("Loading…")}</p>
              ) : (
                history.map((e) => (
                  <article key={e.id}>
                    <div>
                      <strong>{tr(outcomes[e.kind] || e.kind)}</strong> ·{" "}
                      {e.actor_name}
                    </div>
                    <small>
                      <time dir="ltr">{time(e.created)}</time> · {tr("Version")}{" "}
                      {e.version}
                    </small>
                    <p dir="auto">{e.note}</p>
                    {(e.details.agent_name || e.details.after?.agent_name) && (
                      <small>
                        {tr("Assigned recovery agent")}:{" "}
                        {e.details.agent_name || e.details.after?.agent_name}
                      </small>
                    )}
                    {(e.details.next_follow_up ||
                      e.details.after?.next_follow_up) && (
                      <small>
                        {tr("Next follow-up (Karachi)")}:{" "}
                        <time dir="ltr">
                          {time(
                            e.details.next_follow_up ||
                              e.details.after!.next_follow_up,
                          )}
                        </time>
                      </small>
                    )}
                    {e.details.after && (
                      <small>
                        {tr("Case status")}:{" "}
                        {tr(statuses[e.details.after.status])}
                      </small>
                    )}
                    {e.details.promised_amount != null && (
                      <p>
                        {tr("Payment promise")}:{" "}
                        {money(e.details.promised_amount)} ·{" "}
                        {e.details.promised_on}
                      </p>
                    )}
                  </article>
                ))
              )}
              <div className="pagination">
                <button
                  className="secondary"
                  disabled={!historyPage || historyLoading}
                  onClick={() => setHistoryPage((p) => p - 1)}
                >
                  {tr("Previous history")}
                </button>
                <button
                  className="secondary"
                  disabled={history.length < 30 || historyLoading}
                  onClick={() => setHistoryPage((p) => p + 1)}
                >
                  {tr("Next history")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      {loading ? (
        <p role="status">{tr("Loading…")}</p>
      ) : (
        <div className="recovery-cards">
          {data.items.map((row) => (
            <article
              key={row.id}
              className={`recovery-card recovery-${row.queue_status}`}
            >
              <div className="recovery-heading">
                <strong>{row.customer_name}</strong>
                <span className="recovery-badge">
                  {tr(statuses[row.queue_status])}
                </span>
              </div>
              <p>
                {row.invoice_number} · {row.phone || "—"}
              </p>
              <dl>
                <div>
                  <dt>{tr("Outstanding")}</dt>
                  <dd dir="ltr">{money(row.balance)}</dd>
                </div>
                <div>
                  <dt>{tr("Assigned recovery agent")}</dt>
                  <dd>
                    {row.agent_name}
                    {!row.agent_available && (
                      <small>{tr("Agent access unavailable")}</small>
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{tr("Next follow-up (Karachi)")}</dt>
                  <dd dir="ltr">{time(row.next_follow_up)}</dd>
                </div>
              </dl>
              <div className="actions">
                {["due", "upcoming"].includes(row.queue_status) &&
                  (data.can_manage || data.user_id === row.assigned_to) && (
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => open("activity", row)}
                    >
                      {tr("Record contact outcome")}
                    </button>
                  )}
                {data.can_manage && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => open("manage", row)}
                  >
                    {tr("Manage case")}
                  </button>
                )}
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => open("history", row)}
                >
                  {tr("History")}
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => onCustomer(row.customer)}
                >
                  {tr("Open khata")}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {!loading && !data.items.length && (
        <p>{tr("No recovery cases match these filters.")}</p>
      )}
      <div className="pagination">
        <span>
          {tr("Page")} {page + 1}
        </span>
        <div className="actions">
          <button
            className="secondary"
            disabled={!page || loading}
            onClick={() => setPage((p) => p - 1)}
          >
            {tr("Previous")}
          </button>
          <button
            className="secondary"
            disabled={data.items.length < 30 || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            {tr("Next")}
          </button>
        </div>
      </div>
    </section>
  );
}
