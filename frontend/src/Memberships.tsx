import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
import CustomerSelect from "./CustomerSelect";
import "./memberships.css";
type Plan = {
  id: string;
  code: string;
  name: string;
  duration_days: number;
  benefits: string;
  active: boolean;
  version: number;
};
type Member = {
  id: string;
  number: string;
  customer_name: string;
  phone: string;
  plan_snapshot: Omit<Plan, "id" | "active">;
  valid_from: string;
  valid_until: string;
  membership_status: string;
  status: string;
  version: number;
};
type History = {
  kind: string;
  note: string;
  version: number;
  actor: string;
  created: string;
  details: { valid_from: string; valid_until: string };
};
const states: Record<string, string> = {
  all: "All memberships",
  active: "Active memberships",
  scheduled: "Scheduled memberships",
  expired: "Expired memberships",
  cancelled: "Cancelled memberships",
};
const events: Record<string, string> = {
  enrolled: "Enrolled",
  renewed: "Renewed",
  cancelled: "Cancelled",
};
export default function Memberships({ tenant }: { tenant: string }) {
  const url = `/api/v1/tenants/${tenant}/memberships`;
  const [tab, setTab] = useState("members"),
    [state, setState] = useState("all"),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [members, setMembers] = useState<Member[]>([]),
    [counts, setCounts] = useState<Record<string, number>>({}),
    [plans, setPlans] = useState<Plan[]>([]);
  const [mode, setMode] = useState<
      "plan" | "enroll" | "renew" | "cancel" | "history" | null
    >(null),
    [plan, setPlan] = useState<Plan | null>(null),
    [member, setMember] = useState<Member | null>(null),
    [customer, setCustomer] = useState("");
  const [planSearch, setPlanSearch] = useState(""),
    [choices, setChoices] = useState<Plan[]>([]),
    [chosen, setChosen] = useState<Plan | null>(null);
  const [history, setHistory] = useState<History[]>([]),
    [historyPage, setHistoryPage] = useState(0);
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const pending = useRef<{ signature: string; id: string } | null>(null),
    editor = useRef<HTMLDivElement>(null);
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    const timer = setTimeout(
      () =>
        api<any>(
          tab === "plans"
            ? `${url}/plans?q=${encodeURIComponent(query)}&offset=${page * 50}`
            : `${url}?state=${state}&q=${encodeURIComponent(query)}&offset=${page * 30}`,
          { signal: c.signal },
        )
          .then((r) => {
            if (c.signal.aborted) return;
            if (tab === "plans") setPlans(r.items);
            else {
              setMembers(r.items);
              setCounts(r.counts);
            }
          })
          .catch((e) => {
            if (!c.signal.aborted) setError(e.message);
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
  }, [tenant, tab, state, query, page, revision]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") setRevision((n) => n + 1);
    }, 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const c = new AbortController();
    if (mode !== "enroll") return () => c.abort();
    const timer = setTimeout(
      () =>
        api<{ items: Plan[] }>(
          `${url}/plans?q=${encodeURIComponent(planSearch)}`,
          { signal: c.signal },
        )
          .then((r) => {
            if (!c.signal.aborted) setChoices(r.items.filter((p) => p.active));
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
  }, [mode, planSearch, tenant]);
  useEffect(() => {
    const c = new AbortController();
    setHistory([]);
    if (mode !== "history" || !member) return () => c.abort();
    api<{ items: History[] }>(
      `${url}/${member.id}/history?offset=${historyPage * 30}`,
      { signal: c.signal },
    )
      .then((r) => {
        if (!c.signal.aborted) setHistory(r.items);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [tenant, mode, member?.id, historyPage]);
  useEffect(() => {
    if (mode) {
      editor.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      editor.current?.focus();
    }
  }, [mode, member?.id, plan?.id]);
  function open(
    next: typeof mode,
    m: Member | null = null,
    p: Plan | null = null,
  ) {
    setMode(next);
    setMember(m);
    setPlan(p);
    setCustomer("");
    setChosen(null);
    setPlanSearch("");
    setHistoryPage(0);
    setError("");
    setNotice("");
    pending.current = null;
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const f = new FormData(e.currentTarget);
    let path = url,
      method = "POST",
      payload: Record<string, unknown> = {};
    if (mode === "plan") {
      path += "/plans" + (plan ? `/${plan.id}` : "");
      method = plan ? "PUT" : "POST";
      payload = {
        code: f.get("code"),
        name: f.get("name"),
        duration_days: Number(f.get("duration_days")),
        benefits: f.get("benefits"),
        active: f.get("active") === "on",
        ...(plan ? { version: plan.version } : {}),
      };
    } else if (mode === "enroll") {
      if (!chosen || !customer) return;
      payload = {
        customer,
        plan: chosen.id,
        plan_version: chosen.version,
        valid_from: f.get("valid_from"),
        note: f.get("note"),
      };
    } else if (member) {
      path += `/${member.id}/actions`;
      payload = { version: member.version, action: mode, note: f.get("note") };
    } else return;
    if (mode !== "plan") {
      const signature = JSON.stringify({ path, payload });
      if (pending.current?.signature !== signature)
        pending.current = { signature, id: newRequestId() };
      payload.request = pending.current.id;
    }
    setBusy(true);
    setError("");
    try {
      await send(path, payload, method);
      setMode(null);
      setNotice("Membership changes saved.");
      setRevision((n) => n + 1);
      pending.current = null;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const rows = tab === "plans" ? plans : members;
  return (
    <section className="panel memberships">
      <div className="membership-heading">
        <div>
          <h2>{tr("Customer memberships")}</h2>
          <p>
            {tr(
              "Manage enrollment, renewal and expiry with a clear membership history.",
            )}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            disabled={busy || loading}
            onClick={() => {
              setMode(null);
              setError("");
              setRevision((n) => n + 1);
            }}
          >
            {tr("Reload")}
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => open(tab === "plans" ? "plan" : "enroll")}
          >
            {tr(tab === "plans" ? "Add membership plan" : "Enroll customer")}
          </button>
        </div>
      </div>
      <div className="actions membership-tabs">
        {[
          ["members", "Memberships"],
          ["plans", "Membership plans"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "primary" : "secondary"}
            onClick={() => {
              setTab(key);
              setPage(0);
              setQuery("");
              setMode(null);
            }}
          >
            {tr(label)}
          </button>
        ))}
      </div>
      <p className="hint">
        {tr(
          "Memberships do not charge fees or change POS prices. Benefits are recorded terms for staff reference. Dates use Asia/Karachi.",
        )}
      </p>
      <div className="form-grid">
        <label className="field">
          <span>{tr("Search memberships or plans")}</span>
          <input
            value={query}
            maxLength={100}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        {tab === "members" && (
          <label className="field">
            <span>{tr("Membership status")}</span>
            <select
              aria-label={tr("Membership status")}
              value={state}
              onChange={(e) => {
                setState(e.target.value);
                setPage(0);
              }}
            >
              {Object.entries(states).map(([key, label]) => (
                <option key={key} value={key}>
                  {tr(label)}
                  {key !== "all" ? ` (${counts[key] || 0})` : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && (
        <p role="status" className="operation-notice">
          {tr(notice)}
        </p>
      )}
      {mode && (
        <div className="membership-editor" ref={editor} tabIndex={-1}>
          <div className="membership-heading">
            <h3>
              {tr(
                mode === "plan"
                  ? plan
                    ? "Edit membership plan"
                    : "Add membership plan"
                  : mode === "enroll"
                    ? "Enroll customer"
                    : mode === "renew"
                      ? "Renew membership"
                      : mode === "cancel"
                        ? "Cancel membership"
                        : "Membership history",
              )}
            </h3>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => setMode(null)}
            >
              {tr("Close")}
            </button>
          </div>
          {member && (
            <p>
              <strong>
                {member.number} · {member.customer_name}
              </strong>{" "}
              · {member.plan_snapshot.name} ·{" "}
              <span dir="ltr">
                {member.valid_from} — {member.valid_until}
              </span>
            </p>
          )}
          {mode !== "history" ? (
            <form
              key={`${mode}:${plan?.id || member?.id || "new"}`}
              onSubmit={save}
            >
              <fieldset disabled={busy}>
                {mode === "plan" ? (
                  <>
                    <div className="form-grid">
                      <label className="field">
                        <span>{tr("Plan code")}</span>
                        <input
                          name="code"
                          required
                          maxLength={30}
                          pattern="[A-Z0-9_-]+"
                          readOnly={!!plan}
                          defaultValue={plan?.code || ""}
                        />
                      </label>
                      <label className="field">
                        <span>{tr("Plan name")}</span>
                        <input
                          name="name"
                          required
                          maxLength={100}
                          defaultValue={plan?.name || ""}
                        />
                      </label>
                      <label className="field">
                        <span>{tr("Term length (days)")}</span>
                        <input
                          name="duration_days"
                          type="number"
                          required
                          min={1}
                          max={730}
                          step={1}
                          defaultValue={plan?.duration_days || 365}
                        />
                      </label>
                      <label className="field">
                        <span>{tr("Available for enrollment")}</span>
                        <input
                          name="active"
                          type="checkbox"
                          defaultChecked={plan?.active ?? true}
                        />
                      </label>
                    </div>
                    <label className="field">
                      <span>{tr("Membership benefits")}</span>
                      <textarea
                        name="benefits"
                        maxLength={2000}
                        rows={3}
                        defaultValue={plan?.benefits || ""}
                      />
                    </label>
                    <p className="hint">
                      {tr(
                        "Plan edits apply to new enrollments. Existing memberships keep their original benefits and renewal term. Inactive plans cannot be renewed.",
                      )}
                    </p>
                  </>
                ) : (
                  <>
                    {mode === "enroll" ? (
                      <>
                        <CustomerSelect
                          tenant={tenant}
                          value={customer}
                          onChange={setCustomer}
                        />
                        <div className="form-grid">
                          <label className="field">
                            <span>{tr("Find membership plan")}</span>
                            <input
                              value={planSearch}
                              maxLength={100}
                              onChange={(e) => setPlanSearch(e.target.value)}
                            />
                          </label>
                          <label className="field">
                            <span>{tr("Membership plan")}</span>
                            <select
                              aria-label={tr("Membership plan")}
                              required
                              value={chosen?.id || ""}
                              onChange={(e) =>
                                setChosen(
                                  choices.find(
                                    (p) => p.id === e.target.value,
                                  ) || null,
                                )
                              }
                            >
                              <option value="">{tr("Select plan")}</option>
                              {chosen &&
                                !choices.some((p) => p.id === chosen.id) && (
                                  <option value={chosen.id}>
                                    {chosen.name}
                                  </option>
                                )}
                              {choices.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name} · {p.duration_days} {tr("days")}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="field">
                            <span>{tr("Membership starts")}</span>
                            <input
                              name="valid_from"
                              type="date"
                              required
                              min={today}
                              defaultValue={today}
                            />
                          </label>
                        </div>
                        <small>
                          {tr(
                            "First 50 active plans; search to narrow results.",
                          )}
                        </small>
                        {chosen && (
                          <p className="membership-benefits">
                            {chosen.benefits || tr("No benefits specified.")}
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="hint">
                        {tr(
                          mode === "renew"
                            ? "Renewal adds the original term after the current expiry, or starts today if expired. Existing terms are retained."
                            : "Cancellation takes effect immediately and does not refund or waive any amount. To join again, create a new enrollment.",
                        )}
                        {mode === "renew" && member && (
                          <>
                            {" "}
                            {member.plan_snapshot.duration_days} {tr("days")}
                          </>
                        )}
                      </p>
                    )}
                    <label className="field">
                      <span>{tr("Membership note")}</span>
                      <textarea
                        name="note"
                        rows={3}
                        maxLength={1000}
                        required
                      />
                    </label>
                  </>
                )}
                <button
                  className="primary"
                  disabled={
                    busy || (mode === "enroll" && (!customer || !chosen))
                  }
                >
                  {tr(busy ? "Saving…" : "Save membership changes")}
                </button>
              </fieldset>
            </form>
          ) : (
            <div className="membership-history">
              {history.map((h) => (
                <article key={h.version}>
                  <strong>
                    {tr(events[h.kind])} · {tr("Version")} {h.version}
                  </strong>
                  <small>
                    {h.actor} ·{" "}
                    <span dir="ltr">
                      {new Intl.DateTimeFormat("en-GB", {
                        timeZone: "Asia/Karachi",
                        dateStyle: "medium",
                        timeStyle: "short",
                      }).format(new Date(h.created))}
                    </span>
                  </small>
                  <p dir="auto">{h.note}</p>
                  <span dir="ltr">
                    {h.details.valid_from} — {h.details.valid_until}
                  </span>
                </article>
              ))}
              <div className="pagination">
                <button
                  className="secondary"
                  disabled={!historyPage}
                  onClick={() => setHistoryPage((p) => p - 1)}
                >
                  {tr("Previous history")}
                </button>
                <button
                  className="secondary"
                  disabled={history.length < 30}
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
        <div className="membership-cards">
          {tab === "plans"
            ? plans.map((p) => (
                <article key={p.id}>
                  <div className="membership-heading">
                    <h3>{p.name}</h3>
                    <span>{tr(p.active ? "Active" : "Inactive")}</span>
                  </div>
                  <small>
                    {p.code} · {p.duration_days} {tr("days")} · {tr("Version")}{" "}
                    {p.version}
                  </small>
                  <p className="membership-benefits">
                    {p.benefits || tr("No benefits specified.")}
                  </p>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => open("plan", null, p)}
                  >
                    {tr("Edit plan")}
                  </button>
                </article>
              ))
            : members.map((m) => (
                <article key={m.id}>
                  <div className="membership-heading">
                    <h3>{m.customer_name}</h3>
                    <span
                      className={`membership-badge membership-${m.membership_status}`}
                    >
                      {tr(
                        (
                          {
                            active: "Active",
                            scheduled: "Scheduled",
                            expired: "Expired",
                            cancelled: "Cancelled",
                          } as Record<string, string>
                        )[m.membership_status],
                      )}
                    </span>
                  </div>
                  <p>
                    {m.number} · {m.phone || "—"}
                  </p>
                  <strong>{m.plan_snapshot.name}</strong>
                  <p>
                    <span dir="ltr">
                      {m.valid_from} — {m.valid_until}
                    </span>
                  </p>
                  <p className="membership-benefits">
                    {m.plan_snapshot.benefits}
                  </p>
                  <div className="actions">
                    {m.status !== "cancelled" && (
                      <>
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => open("renew", m)}
                        >
                          {tr("Renew membership")}
                        </button>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => open("cancel", m)}
                        >
                          {tr("Cancel membership")}
                        </button>
                      </>
                    )}
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => open("history", m)}
                    >
                      {tr("History")}
                    </button>
                  </div>
                </article>
              ))}
        </div>
      )}
      {!loading && !rows.length && (
        <p>{tr("No memberships or plans match these filters.")}</p>
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
            disabled={rows.length < (tab === "plans" ? 50 : 30) || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            {tr("Next")}
          </button>
        </div>
      </div>
    </section>
  );
}
