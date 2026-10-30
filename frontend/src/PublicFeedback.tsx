import { useEffect, useState } from "react";
import { CheckCircle2, MessageSquare, Star } from "lucide-react";
import { api, ApiError } from "./api";
import { t as tr, useLanguage } from "./i18n";
import "./feedback-public.css";

export default function PublicFeedback() {
  const [language, setLanguage] = useLanguage();
  const [token] = useState(() => window.location.hash.slice(1));
  const [details, setDetails] = useState<{
    business_name: string;
    expires: string;
    submitted: boolean;
  } | null>(null);
  const [error, setError] = useState(""),
    [invalid, setInvalid] = useState(false),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(0),
    [comment, setComment] = useState(""),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setError("");
    setLoading(true);
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
      setInvalid(true);
      setLoading(false);
      return;
    }
    api<any>("/api/public/feedback/preview", {
      method: "POST",
      credentials: "omit",
      body: JSON.stringify({ token }),
      signal: c.signal,
    })
      .then(setDetails)
      .catch((e) => {
        if (e.name !== "AbortError") {
          if (e instanceof ApiError && e.status === 404) setInvalid(true);
          else setError(e.message);
        }
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [token, revision]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/public/feedback/submit", {
        method: "POST",
        credentials: "omit",
        body: JSON.stringify({ token, rating, comment }),
      });
      setDetails((d) => (d ? { ...d, submitted: true } : d));
      setComment("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setInvalid(true);
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="customer-feedback-page">
      <div className="customer-feedback-wrap">
        <div className="customer-feedback-brand">
          <MessageSquare size={22} />
          <span>{tr("StockDesk")}</span>
          <button
            className="secondary"
            onClick={() => setLanguage(language === "en" ? "ur" : "en")}
          >
            {language === "en" ? "اردو" : "English"}
          </button>
        </div>
        <section className="customer-feedback-card">
          {loading ? (
            <p role="status">{tr("Loading…")}</p>
          ) : invalid ? (
            <>
              <h1>{tr("This feedback link is unavailable")}</h1>
              <p>
                {tr(
                  "It may have expired or been revoked. Ask the store for a new link.",
                )}
              </p>
            </>
          ) : details?.submitted ? (
            <div className="customer-feedback-thanks">
              <CheckCircle2 size={42} />
              <h1>{tr("Thank you for your feedback")}</h1>
              <p>{tr("Your response has been received by the store.")}</p>
            </div>
          ) : details ? (
            <>
              <p className="customer-feedback-store">{details.business_name}</p>
              <h1>{tr("How was your experience?")}</h1>
              <p>{tr("Your comments help the store improve its service.")}</p>
              <form onSubmit={submit}>
                <fieldset disabled={busy} className="customer-feedback-fields">
                  <legend>{tr("Your rating")}</legend>
                  <div className="customer-rating">
                    {[1, 2, 3, 4, 5].map((value) => (
                      <label
                        key={value}
                        className={rating === value ? "selected" : ""}
                      >
                        <input
                          type="radio"
                          name="rating"
                          value={value}
                          checked={rating === value}
                          required
                          onChange={() => setRating(value)}
                        />
                        <Star
                          size={22}
                          aria-hidden="true"
                          fill={rating >= value ? "currentColor" : "none"}
                        />
                        <span dir="ltr">{value} / 5</span>
                      </label>
                    ))}
                  </div>
                  <label className="field">
                    {tr("Your feedback")}
                    <textarea
                      dir="auto"
                      required
                      minLength={1}
                      maxLength={2000}
                      rows={5}
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                    />
                  </label>
                  <div className="customer-feedback-count">
                    <bdi dir="ltr">{comment.length} / 2000</bdi>
                  </div>
                  <p className="hint">
                    {tr(
                      "Please do not include payment details, passwords or identity documents. Your response is visible to the store's authorized staff.",
                    )}
                  </p>
                  <button
                    className="primary"
                    disabled={rating === 0 || !comment.trim()}
                  >
                    {tr(busy ? "Submitting…" : "Send feedback")}
                  </button>
                </fieldset>
              </form>
            </>
          ) : null}
          {error && (
            <div role="alert" className="form-error">
              {tr(error)}
              {!details && !invalid && (
                <button
                  className="secondary"
                  onClick={() => setRevision((x) => x + 1)}
                >
                  {tr("Try again")}
                </button>
              )}
            </div>
          )}
        </section>
        <p className="customer-feedback-footer">
          {tr("No account needed. One response per invitation.")}
        </p>
      </div>
    </main>
  );
}
