import FeedbackInvitations from "./FeedbackInvitations";
import { useEffect, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
export default function Feedback({ tenant }: { tenant: string }) {
  const base = `/api/v1/tenants/${tenant}/feedback`;
  const [data, setData] = useState<any>(null),
    [status, setStatus] = useState("all"),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [rating, setRating] = useState("5"),
    [comment, setComment] = useState(""),
    [invoice, setInvoice] = useState(""),
    [selected, setSelected] = useState<any>(null),
    [note, setNote] = useState("");
  const [pending, setPending] = useState<{
    key: string;
    request: string;
  } | null>(null);
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    api<any>(`${base}?status=${status}&offset=${page * 50}`, {
      signal: c.signal,
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [base, status, page, revision]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = { rating: Number(rating), comment, invoice_number: invoice };
      const key = JSON.stringify(body);
      const request = pending?.key === key ? pending.request : newRequestId();
      setPending({ key, request });
      await send(base, { ...body, request });
      setComment("");
      setInvoice("");
      setPending(null);
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resolve(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(
        base + "/" + selected.id,
        {
          version: selected.version,
          status: selected.status === "open" ? "resolved" : "open",
          note,
        },
        "PUT",
      );
      setSelected(null);
      setNote("");
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
      setRevision((x) => x + 1);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <FeedbackInvitations tenant={tenant} />
      <p>
        {tr(
          "Record feedback received from customers. Entries remain unchanged; resolution notes are audited.",
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      <section className="panel">
        <h2>{tr("Record customer feedback")}</h2>
        <form onSubmit={submit}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
            <div className="form-grid">
              <label className="field">
                {tr("Rating")}
                <select
                  dir="ltr"
                  value={rating}
                  onChange={(e) => setRating(e.target.value)}
                >
                  {[5, 4, 3, 2, 1].map((n) => (
                    <option key={n} value={n}>
                      {n} / 5
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                {tr("Invoice number (optional)")}
                <input
                  maxLength={100}
                  value={invoice}
                  onChange={(e) => setInvoice(e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              {tr("Customer feedback")}
              <textarea
                rows={3}
                required
                maxLength={2000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </label>
            <button className="primary">{tr("Save feedback")}</button>
          </fieldset>
        </form>
      </section>
      <section className="panel">
        <h2>{tr("Feedback inbox")}</h2>
        {data && (
          <p>
            {tr("Total")}: {data.summary.total} · {tr("Open")}:{" "}
            {data.summary.open} · {tr("Average rating")}:{" "}
            <bdi dir="ltr">{data.summary.average ?? "—"} / 5</bdi>
          </p>
        )}
        <label className="field">
          {tr("Status")}
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            {["all", "open", "resolved"].map((x) => (
              <option key={x} value={x}>
                {tr(x === "all" ? "All" : x === "open" ? "Open" : "Resolved")}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => {
            setSelected(null);
            setRevision((x) => x + 1);
          }}
        >
          {tr("Refresh")}
        </button>
        {!data ? (
          <p>{tr("Loading…")}</p>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      "Rating",
                      "Customer feedback",
                      "Invoice",
                      "Status",
                      "Resolution note",
                      "Action",
                    ].map((x) => (
                      <th key={x}>{tr(x)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((f: any) => (
                    <tr key={f.id}>
                      <td>
                        <bdi dir="ltr">{f.rating} / 5</bdi>
                      </td>
                      <td style={{ whiteSpace: "pre-wrap", maxWidth: 400 }}>
                        {f.comment}
                        <br />
                        <small>
                          {new Date(f.created).toLocaleString()} ·{" "}
                          {tr(
                            f.source === "customer"
                              ? "Submitted by customer"
                              : "Recorded by staff",
                          )}
                        </small>
                      </td>
                      <td>{f.invoice_number || "—"}</td>
                      <td>{tr(f.status === "open" ? "Open" : "Resolved")}</td>
                      <td style={{ whiteSpace: "pre-wrap", maxWidth: 400 }}>
                        {f.resolution || "—"}
                      </td>
                      <td>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => {
                            setSelected(f);
                            setNote("");
                          }}
                        >
                          {tr(
                            f.status === "open"
                              ? "Resolve feedback"
                              : "Reopen feedback",
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.items.length && <p>{tr("No matching records.")}</p>}
            </div>
            <div className="toolbar">
              <button
                disabled={busy || page === 0}
                onClick={() => setPage(page - 1)}
              >
                {tr("Previous")}
              </button>
              <span>{data.total}</span>
              <button
                disabled={busy || (page + 1) * 50 >= data.total}
                onClick={() => setPage(page + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </>
        )}
        {selected && (
          <form onSubmit={resolve}>
            <h3>
              {tr(
                selected.status === "open"
                  ? "Resolve feedback"
                  : "Reopen feedback",
              )}
            </h3>
            <label className="field">
              {tr("Resolution note")}
              <textarea
                rows={3}
                required
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button className="primary" disabled={busy}>
              {tr("Save resolution")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setSelected(null)}
            >
              {tr("Cancel")}
            </button>
          </form>
        )}
      </section>
    </>
  );
}
