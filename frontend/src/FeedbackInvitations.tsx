import { useEffect, useState } from "react";
import { Copy, Link, ShieldCheck } from "lucide-react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
import "./feedback-public.css";

export default function FeedbackInvitations({ tenant }: { tenant: string }) {
  const base = `/api/v1/tenants/${tenant}/feedback/invitations`;
  const [data, setData] = useState<any>(null),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [invoice, setInvoice] = useState(""),
    [days, setDays] = useState(7),
    [link, setLink] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    api<any>(`${base}?offset=${page * 30}`, { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [base, page, revision]);
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    setLink("");
    try {
      const result = await send<{ url: string }>(base, {
        invoice_number: invoice,
        expires_days: days,
      });
      setLink(result.url);
      setPage(0);
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await send(`${base}/${id}/revoke`, {});
      setLink("");
      setNotice("Feedback link revoked.");
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const statusLabel: Record<string, string> = {
    active: "Active",
    submitted: "Submitted",
    revoked: "Revoked",
    expired: "Expired",
  };
  return (
    <section className="panel feedback-links">
      <div className="feedback-links-title">
        <Link size={20} />
        <div>
          <h2>{tr("Customer feedback links")}</h2>
          <p>{tr("Invite a customer to respond without a staff account.")}</p>
        </div>
      </div>
      <form onSubmit={create}>
        <fieldset disabled={busy} className="feedback-link-fields">
          <label className="field">
            {tr("Invoice number")}
            <input
              required
              maxLength={100}
              value={invoice}
              onChange={(e) => setInvoice(e.target.value)}
              placeholder="INV-…"
            />
          </label>
          <label className="field">
            {tr("Link validity (days)")}
            <input
              type="number"
              required
              min="1"
              max="30"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
          <button className="primary">{tr("Create feedback link")}</button>
        </fieldset>
      </form>
      <p className="hint">
        {tr(
          "One customer response per invoice. Creating a replacement revokes the previous link. Anyone with the link can submit; share it only with the intended customer. No message is sent automatically.",
        )}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {link && (
        <div className="feedback-share">
          <ShieldCheck size={20} />
          <div>
            <label className="field">
              {tr("Shareable feedback link")}
              <input
                readOnly
                value={link}
                dir="ltr"
                onFocus={(e) => e.currentTarget.select()}
              />
            </label>
            <small>
              {tr(
                "Copy this link now. For privacy, saved links cannot be retrieved later; create a replacement if needed.",
              )}
            </small>
          </div>
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(link);
                setNotice("Feedback link copied.");
              } catch {
                setNotice("Select the link and copy it manually.");
              }
            }}
          >
            <Copy size={16} />
            {tr("Copy link")}
          </button>
        </div>
      )}
      {!data ? (
        <p>{tr("Loading…")}</p>
      ) : (
        <>
          <div className="feedback-invitations">
            {data.items.map((item: any) => (
              <article key={item.id}>
                <div>
                  <strong>{item.invoice_number}</strong>
                  <span>{tr(statusLabel[item.status])}</span>
                  <small>
                    {tr("Expires")}: {new Date(item.expires).toLocaleString()}
                  </small>
                </div>
                {item.status === "active" && (
                  <button
                    type="button"
                    disabled={busy}
                    className="secondary"
                    onClick={() => revoke(item.id)}
                  >
                    {tr("Revoke link")}
                  </button>
                )}
              </article>
            ))}
          </div>
          {!data.items.length && (
            <p className="hint">{tr("No feedback invitations yet.")}</p>
          )}
          {data.total > 30 && (
            <div className="toolbar">
              <button
                disabled={busy || page === 0}
                onClick={() => setPage((x) => x - 1)}
              >
                {tr("Previous")}
              </button>
              <span>
                {page * 30 + 1}–{Math.min((page + 1) * 30, data.total)} /{" "}
                {data.total}
              </span>
              <button
                disabled={busy || (page + 1) * 30 >= data.total}
                onClick={() => setPage((x) => x + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
