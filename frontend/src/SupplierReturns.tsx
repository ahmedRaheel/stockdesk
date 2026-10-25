import { newRequestId } from "./requestId";
import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
import LookupSelect from "./LookupSelect";
export type Credit = {
  id: string;
  credit_number: string;
  returned_on: string;
  total: number;
  tax: number;
  reason: string;
};
export type Refund = {
  id: string;
  received_on: string;
  amount: number;
  method_name: string;
  reference: string;
  status: string;
};
type Source = {
  movement: string;
  sku: string;
  name: string;
  lot: string;
  expires: string | null;
  source_remaining: number;
  billed_remaining: number;
  stock: number;
  fractional: boolean;
};
const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export default function SupplierReturns({
  tenant,
  billId,
  currency,
  canReturn,
  active,
  creditBalance,
  credits,
  refunds,
  onSaved,
}: {
  tenant: string;
  billId: string;
  currency: string;
  canReturn: boolean;
  active: boolean;
  creditBalance: number;
  credits: Credit[];
  refunds: Refund[];
  onSaved: () => Promise<void>;
}) {
  const base = `/api/v1/tenants/${tenant}/payables/${billId}`;
  const [sources, setSources] = useState<Source[] | null>(null),
    [mode, setMode] = useState<"return" | "refund" | null>(null),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [voidId, setVoidId] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const money = (n: number) =>
    new Intl.NumberFormat("en-PK", { style: "currency", currency }).format(
      n / 100,
    );
  useEffect(() => {
    if (mode !== "return" || !canReturn) return;
    const c = new AbortController();
    setSources(null);
    api<{ items: Source[] }>(
      base +
        `/return-options?q=${encodeURIComponent(query)}&offset=${page * 50}`,
      { signal: c.signal },
    )
      .then((r) => setSources(r.items))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [base, mode, canReturn, query, page]);
  async function mutate(
    path: string,
    payload: Record<string, unknown>,
    dedup = true,
  ) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    const signature = JSON.stringify({ path, payload });
    if (dedup && pending.current?.signature !== signature)
      pending.current = { signature, id: newRequestId() };
    try {
      await send(
        path,
        dedup ? { ...payload, request: pending.current!.id } : payload,
      );
      pending.current = null;
      setMode(null);
      setVoidId(null);
      await onSaved();
      setNotice("Supplier return ledger updated.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function returned(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    mutate(base + "/returns", {
      credit_number: f.get("credit_number"),
      returned_on: f.get("returned_on"),
      reason_id: f.get("reason_id"),
      reason: f.get("reason"),
      tax: Math.round(Number(f.get("tax")) * 100),
      lines: (sources || [])
        .map((s) => ({
          source: s.movement,
          quantity: Number(f.get(s.movement)),
        }))
        .filter((s) => s.quantity > 0),
    });
  }
  function refunded(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    mutate(base + "/refunds", {
      amount: Math.round(Number(f.get("amount")) * 100),
      received_on: f.get("received_on"),
      method_id: f.get("method_id"),
      reference: f.get("reference"),
    });
  }
  return (
    <section className="panel">
      <h2>{tr("Supplier returns & credits")}</h2>
      <p>
        {tr("Credit owed by supplier")}: <strong>{money(creditBalance)}</strong>
      </p>
      <p>
        {tr(
          "Goods returns reduce stock and credit the original bill. Refund entries record money received externally; they do not move bank or till cash.",
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      <div className="toolbar">
        {active && canReturn && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              setMode("return");
              setError("");
            }}
          >
            {tr("Return supplier goods")}
          </button>
        )}
        {active && creditBalance > 0 && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              setMode("refund");
              setError("");
            }}
          >
            {tr("Record supplier refund")}
          </button>
        )}
      </div>
      {mode === "return" && (
        <form onSubmit={returned}>
          <fieldset disabled={busy}>
            <h3>{tr("Post goods return and credit")}</h3>
            <p>
              {tr(
                "Only receipts captured from version 1.7 onward have verifiable source links. Older receipts are not offered here. Credits use original bill amounts and cannot be voided in this release.",
              )}
            </p>
            <div className="payables-fields">
              <label className="field">
                {tr("Supplier credit note number")}
                <input name="credit_number" required maxLength={100} />
              </label>
              <label className="field">
                {tr("Return date")}
                <input
                  name="returned_on"
                  type="date"
                  defaultValue={today()}
                  max={today()}
                  required
                />
              </label>
              <label className="field">
                {tr("Tax credited by supplier")}
                <input
                  name="tax"
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue="0"
                  required
                />
              </label>
              <LookupSelect
                tenant={tenant}
                kind="supplier_return_reason"
                label={tr("Return reason")}
                name="reason_id"
              />
            </div>
            <label className="field">
              {tr("Search product or batch")}
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </label>
            <p>
              {tr(
                "Each return uses the quantities on the current source page only.",
              )}
            </p>
            <label className="field">
              {tr("Return notes")}
              <textarea name="reason" required maxLength={500} />
            </label>
            {sources === null ? (
              <p>{tr("Loading…")}</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{tr("Product")}</th>
                      <th>{tr("Batch")}</th>
                      <th>{tr("Expiry")}</th>
                      <th>{tr("Available to return")}</th>
                      <th>{tr("Return quantity")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s, i) => {
                      const maximum = Math.max(
                        0,
                        Math.min(
                          s.stock,
                          s.billed_remaining,
                          s.source_remaining,
                        ),
                      );
                      return (
                        <tr key={s.movement}>
                          <td>
                            {s.sku} · {s.name}
                            <small>
                              {tr("Receipt source")} {i + 1}
                            </small>
                          </td>
                          <td>{s.lot}</td>
                          <td>{s.expires || "—"}</td>
                          <td>{maximum}</td>
                          <td>
                            <input
                              aria-label={`${tr("Return quantity")} ${s.sku} ${i + 1}`}
                              name={s.movement}
                              type="number"
                              min="0"
                              max={maximum}
                              step={s.fractional ? "0.001" : "1"}
                              defaultValue="0"
                              required
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!sources.length && <p>{tr("No eligible receipt sources.")}</p>}
              </div>
            )}
            <div className="toolbar">
              <button
                type="button"
                disabled={!page || busy}
                onClick={() => setPage((p) => p - 1)}
              >
                {tr("Previous")}
              </button>
              <button
                type="button"
                disabled={sources?.length !== 50 || busy}
                onClick={() => setPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
            <button className="primary" disabled={busy || !sources?.length}>
              {tr("Post return and credit")}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setMode(null)}
            >
              {tr("Cancel")}
            </button>
          </fieldset>
        </form>
      )}
      {mode === "refund" && (
        <form onSubmit={refunded}>
          <fieldset disabled={busy}>
            <h3>{tr("Record supplier refund")}</h3>
            <div className="payables-fields">
              <label className="field">
                {tr("Refund amount")}
                <input
                  name="amount"
                  type="number"
                  min="0.01"
                  max={creditBalance / 100}
                  step="0.01"
                  required
                />
              </label>
              <label className="field">
                {tr("Received on")}
                <input
                  type="date"
                  name="received_on"
                  defaultValue={today()}
                  max={today()}
                  required
                />
              </label>
              <LookupSelect
                tenant={tenant}
                kind="payment_method"
                label={tr("Refund method")}
                name="method_id"
              />
              <label className="field">
                {tr("Refund reference")}
                <input name="reference" required maxLength={150} />
              </label>
            </div>
            <button className="primary" disabled={busy}>
              {tr("Save refund record")}
            </button>
            <button type="button" onClick={() => setMode(null)}>
              {tr("Cancel")}
            </button>
          </fieldset>
        </form>
      )}
      <h3>{tr("Credit note history")}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{tr("Credit note")}</th>
              <th>{tr("Date")}</th>
              <th>{tr("Amount")}</th>
              <th>{tr("Reason")}</th>
            </tr>
          </thead>
          <tbody>
            {credits.map((c) => (
              <tr key={c.id}>
                <td>{c.credit_number}</td>
                <td>{c.returned_on}</td>
                <td>{money(c.total)}</td>
                <td>{c.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{tr("Supplier refund history")}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{tr("Date")}</th>
              <th>{tr("Amount")}</th>
              <th>{tr("Payment method")}</th>
              <th>{tr("Reference")}</th>
              <th>{tr("Status")}</th>
              <th>{tr("Action")}</th>
            </tr>
          </thead>
          <tbody>
            {refunds.map((r) => (
              <tr key={r.id}>
                <td>{r.received_on}</td>
                <td>{money(r.amount)}</td>
                <td>{r.method_name}</td>
                <td>{r.reference}</td>
                <td>{tr(r.status)}</td>
                <td>
                  {r.status === "posted" && (
                    <button disabled={busy} onClick={() => setVoidId(r.id)}>
                      {tr("Void refund record")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {voidId && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutate(
              `${base}/refunds/${voidId}/void`,
              { reason: new FormData(e.currentTarget).get("reason") },
              false,
            );
          }}
        >
          <p>
            {tr(
              "This corrects the ledger only. It does not reverse an external refund.",
            )}
          </p>
          <label className="field">
            {tr("Reason")}
            <textarea name="reason" required maxLength={500} />
          </label>
          <button className="primary" disabled={busy}>
            {tr("Confirm void")}
          </button>
          <button type="button" onClick={() => setVoidId(null)} disabled={busy}>
            {tr("Cancel")}
          </button>
        </form>
      )}
    </section>
  );
}
