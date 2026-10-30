import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
import "./memberships.css";
type Campaign = {
  id: string;
  name: string;
  message: string;
  audience: string;
  status: string;
  version: number;
  recipients: number;
};
type Recipient = {
  customer: string;
  name: string;
  phone: string;
  outcome: string;
  version: number;
  active: boolean;
  suppressed: boolean;
};
type Preview = {
  count: number;
  sample: { id: string; name: string; phone: string }[];
  audience_token: string;
};
type Event = {
  id: string;
  kind: string;
  note: string;
  actor: string;
  created: string;
  customer_name: string | null;
  details: { outcome?: string; count?: number };
};
const labels: Record<string, string> = {
  all: "All active customers",
  members: "Current members",
  active: "Active",
  completed: "Completed",
  cancelled: "Cancelled",
  pending: "Pending",
  contacted: "Contacted",
  interested: "Interested",
  not_interested: "Not interested",
  no_answer: "No answer",
  opted_out: "Opted out",
  skipped: "Skipped",
  started: "Campaign started",
  contact: "Contact outcome",
};
export default function Campaigns({ tenant }: { tenant: string }) {
  const url = `/api/v1/tenants/${tenant}/campaigns`;
  const [items, setItems] = useState<Campaign[]>([]),
    [selected, setSelected] = useState<Campaign | null>(null),
    [recipients, setRecipients] = useState<Recipient[]>([]),
    [counts, setCounts] = useState<Record<string, number>>({});
  const [page, setPage] = useState(0),
    [recipientPage, setRecipientPage] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [history, setHistory] = useState<Event[]>([]),
    [showHistory, setShowHistory] = useState(false);
  const [creating, setCreating] = useState(false),
    [audience, setAudience] = useState("all"),
    [preview, setPreview] = useState<Preview | null>(null),
    [contact, setContact] = useState<Recipient | null>(null),
    [action, setAction] = useState("");
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [revision, setRevision] = useState(0);
  const editor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (creating || contact || action) {
      editor.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      editor.current?.focus();
    }
  }, [creating, contact?.customer, action]);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    setError("");
    const path = selected
      ? `${url}/${selected.id}${showHistory ? `/history?offset=${historyPage * 30}` : `?offset=${recipientPage * 30}`}`
      : `${url}?offset=${page * 30}`;
    api<any>(path, { signal: c.signal })
      .then((r) => {
        if (c.signal.aborted) return;
        if (!selected) setItems(r.items);
        else if (showHistory) setHistory(r.items);
        else {
          setSelected(r.campaign);
          setRecipients(r.items);
          setCounts(r.counts);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [
    tenant,
    selected?.id,
    page,
    recipientPage,
    showHistory,
    historyPage,
    revision,
  ]);
  async function mutate(path: string, payload: Record<string, unknown>) {
    const signature = JSON.stringify({ path, payload });
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: newRequestId() };
    await send(path, { ...payload, request: pending.current.id });
    pending.current = null;
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (creating && preview) {
        await mutate(url, {
          name: f.get("name"),
          message: f.get("message"),
          audience,
          audience_token: preview.audience_token,
        });
        setCreating(false);
        setPreview(null);
        setPage(0);
      } else if (selected && contact) {
        await mutate(`${url}/${selected.id}/recipients/${contact.customer}`, {
          version: contact.version,
          outcome: f.get("outcome"),
          note: f.get("note"),
        });
        setContact(null);
      } else if (selected && action) {
        await mutate(`${url}/${selected.id}/actions`, {
          version: selected.version,
          action,
          note: f.get("note"),
        });
        setAction("");
      }
      setNotice("Campaign changes saved.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function previewAudience() {
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      setPreview(await send<Preview>(url + "/preview", { audience }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function closeEditor() {
    setCreating(false);
    setContact(null);
    setAction("");
    setError("");
    pending.current = null;
  }
  const currentRows = selected ? (showHistory ? history : recipients) : items;
  return (
    <section className="panel memberships campaigns">
      <div className="membership-heading">
        <div>
          <h2>{tr("Customer campaigns")}</h2>
          <p>
            {tr(
              "Plan a staff-run campaign, review recipients and record contact outcomes.",
            )}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            disabled={busy || loading}
            onClick={() => {
              closeEditor();
              setRevision((n) => n + 1);
            }}
          >
            {tr("Reload")}
          </button>
          {selected ? (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                closeEditor();
                setSelected(null);
                setShowHistory(false);
                setNotice("");
              }}
            >
              {tr("All campaigns")}
            </button>
          ) : (
            <button
              className="primary"
              disabled={busy}
              onClick={() => {
                closeEditor();
                setCreating(true);
                setPreview(null);
                setNotice("");
              }}
            >
              {tr("New campaign")}
            </button>
          )}
        </div>
      </div>
      <p className="hint">
        {tr(
          "No messages are sent automatically. Check customer consent before contact. Opt-outs apply to all campaigns in this business.",
        )}
      </p>
      {error && (
        <p className="error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {(creating || contact || action) && (
        <div className="membership-editor" ref={editor} tabIndex={-1}>
          <div className="membership-heading">
            <h3>
              {creating
                ? tr("New campaign")
                : contact?.name || tr(labels[action])}
            </h3>
            <button className="secondary" disabled={busy} onClick={closeEditor}>
              {tr("Close")}
            </button>
          </div>
          <form onSubmit={save}>
            <fieldset disabled={busy}>
              {creating ? (
                <>
                  <label className="field">
                    <span>{tr("Campaign name")}</span>
                    <input name="name" required maxLength={100} />
                  </label>
                  <label className="field">
                    <span>{tr("Campaign message")}</span>
                    <textarea
                      name="message"
                      required
                      maxLength={2000}
                      rows={4}
                    />
                  </label>
                  <label className="field">
                    <span>{tr("Audience")}</span>
                    <select
                      aria-label={tr("Audience")}
                      value={audience}
                      onChange={(e) => {
                        setAudience(e.target.value);
                        setPreview(null);
                      }}
                    >
                      <option value="all">{tr(labels.all)}</option>
                      <option value="members">{tr(labels.members)}</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="secondary"
                    onClick={previewAudience}
                  >
                    {tr("Preview audience")}
                  </button>
                  {preview && (
                    <div className="campaign-preview">
                      <strong>
                        {tr("Eligible recipients")}: {preview.count}
                      </strong>
                      <p>
                        {tr(
                          "First ten recipients shown. Starting freezes the full audience and message; later customer changes do not add recipients.",
                        )}
                      </p>
                      <ul>
                        {preview.sample.map((r) => (
                          <li key={r.id}>
                            {r.name} · <span dir="ltr">{r.phone || "—"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <button className="primary" disabled={!preview?.count}>
                    {tr("Start campaign")}
                  </button>
                </>
              ) : (
                <>
                  {contact ? (
                    <>
                      <label className="field">
                        <span>{tr("Contact outcome")}</span>
                        <select
                          aria-label={tr("Contact outcome")}
                          name="outcome"
                          defaultValue={
                            contact.suppressed || !contact.active
                              ? "skipped"
                              : "contacted"
                          }
                        >
                          {[
                            "contacted",
                            "interested",
                            "not_interested",
                            "no_answer",
                            "opted_out",
                            "skipped",
                          ]
                            .filter(
                              (k) =>
                                (contact.active && !contact.suppressed) ||
                                ["skipped", "opted_out"].includes(k),
                            )
                            .map((k) => (
                              <option key={k} value={k}>
                                {tr(labels[k])}
                              </option>
                            ))}
                        </select>
                      </label>
                      <p>
                        {tr(
                          "Opted out blocks future campaign contact. This action cannot be undone here.",
                        )}
                      </p>
                    </>
                  ) : (
                    <p>
                      {tr(
                        action === "completed"
                          ? "Every recipient needs an outcome before completion. Closed campaigns cannot be reopened."
                          : "Cancellation closes the campaign and preserves its audience and history.",
                      )}
                    </p>
                  )}
                  <label className="field">
                    <span>{tr("Campaign note")}</span>
                    <textarea name="note" required maxLength={1000} rows={3} />
                  </label>
                  <button className="primary">
                    {tr("Save campaign changes")}
                  </button>
                </>
              )}
            </fieldset>
          </form>
        </div>
      )}
      {selected && (
        <>
          <div className="membership-editor">
            <div className="membership-heading">
              <div>
                <h3>{selected.name}</h3>
                <span className="membership-badge">
                  {tr(labels[selected.status])}
                </span>
              </div>
              <div className="actions">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => {
                    closeEditor();
                    setShowHistory(!showHistory);
                    setHistoryPage(0);
                  }}
                >
                  {tr(showHistory ? "Recipients" : "History")}
                </button>
                {selected.status === "active" && (
                  <>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => {
                        closeEditor();
                        setShowHistory(false);
                        setAction("completed");
                      }}
                    >
                      {tr("Complete campaign")}
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        closeEditor();
                        setShowHistory(false);
                        setAction("cancelled");
                      }}
                    >
                      {tr("Cancel campaign")}
                    </button>
                  </>
                )}
              </div>
            </div>
            <p className="membership-benefits" dir="auto">
              {selected.message}
            </p>
          </div>
          {!showHistory && (
            <div className="actions campaign-counts">
              {Object.entries(counts).map(([k, v]) => (
                <span className="membership-badge" key={k}>
                  {tr(labels[k])}: {v}
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {loading ? (
        <p role="status">{tr("Loading…")}</p>
      ) : showHistory ? (
        <div className="membership-history">
          {history.map((h) => (
            <article key={h.id}>
              <strong>
                {tr(labels[h.kind])}
                {h.customer_name ? ` · ${h.customer_name}` : ""}
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
              {h.details.outcome && <p>{tr(labels[h.details.outcome])}</p>}
              {h.details.count !== undefined && (
                <p>
                  {tr("Recipients")}: {h.details.count}
                </p>
              )}
              <p dir="auto">{h.note}</p>
            </article>
          ))}
        </div>
      ) : (
        <div className="membership-cards">
          {selected
            ? recipients.map((r) => (
                <article key={r.customer}>
                  <div className="membership-heading">
                    <h3>{r.name}</h3>
                    <span className="membership-badge">
                      {tr(labels[r.outcome])}
                    </span>
                  </div>
                  <p dir="ltr">{r.phone || tr("No phone recorded")}</p>
                  {(r.suppressed || !r.active) && (
                    <p className="hint">
                      {tr("Do not contact: inactive or opted out.")}
                    </p>
                  )}
                  <small>
                    {tr("Contact details captured when the campaign started.")}
                  </small>
                  {selected.status === "active" && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        closeEditor();
                        setContact(r);
                      }}
                    >
                      {tr("Record outcome")}
                    </button>
                  )}
                </article>
              ))
            : items.map((c) => (
                <article key={c.id}>
                  <div className="membership-heading">
                    <h3>{c.name}</h3>
                    <span className="membership-badge">
                      {tr(labels[c.status])}
                    </span>
                  </div>
                  <p>
                    {tr(labels[c.audience])} · {c.recipients} {tr("Recipients")}
                  </p>
                  <p className="membership-benefits" dir="auto">
                    {c.message}
                  </p>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => {
                      closeEditor();
                      setSelected(c);
                      setRecipientPage(0);
                      setShowHistory(false);
                      setNotice("");
                    }}
                  >
                    {tr("Open campaign")}
                  </button>
                </article>
              ))}
        </div>
      )}
      {!loading && !currentRows.length && (
        <p>{tr("No campaign records to display.")}</p>
      )}
      <div className="pagination">
        <span>
          {tr("Page")}{" "}
          {(selected ? (showHistory ? historyPage : recipientPage) : page) + 1}
        </span>
        <div className="actions">
          {[-1, 1].map((delta) => (
            <button
              key={delta}
              className="secondary"
              disabled={
                busy ||
                loading ||
                (delta < 0
                  ? (selected
                      ? showHistory
                        ? historyPage
                        : recipientPage
                      : page) === 0
                  : currentRows.length < 30)
              }
              onClick={() => {
                closeEditor();
                (selected
                  ? showHistory
                    ? setHistoryPage
                    : setRecipientPage
                  : setPage)((p) => p + delta);
              }}
            >
              {tr(delta < 0 ? "Previous" : "Next")}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
