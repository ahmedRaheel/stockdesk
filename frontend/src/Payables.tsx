import { newRequestId } from "./requestId";
import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { t as tr, useLanguage } from "./i18n";
import SupplierReturns, { Credit, Refund } from "./SupplierReturns";
import LookupSelect from "./LookupSelect";
type OrderLine = {
  product: string;
  name: string;
  sku: string;
  unbilled: number;
  unit_cost: number;
  fractional: boolean;
};
type Order = {
  id: string;
  reference: string;
  supplier_name: string;
  lines: OrderLine[];
};
type Bill = {
  supplier: string;
  id: string;
  invoice_number: string;
  supplier_name: string;
  due_date: string;
  total: number;
  paid: number;
  credited: number;
  refunded: number;
  balance: number;
  status: string;
};
type Listing = {
  items: Bill[];
  summary: Record<string, number>;
  as_of: string;
};
type Detail = {
  bill: Bill;
  paid: number;
  credited: number;
  refunded: number;
  credits: Credit[];
  refunds: Refund[];
  lines: {
    product: string;
    name: string;
    quantity: number;
    line_total: number;
  }[];
  payments: {
    id: string;
    paid_on: string;
    amount: number;
    method_name: string;
    reference: string;
    status: string;
  }[];
};
const localDate = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export default function Payables({
  tenant,
  currency,
  canReturn,
}: {
  tenant: string;
  currency: string;
  canReturn: boolean;
}) {
  const [language] = useLanguage();
  const base = `/api/v1/tenants/${tenant}/payables`;
  const [data, setData] = useState<Listing | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [orders, setOrders] = useState<Order[]>([]),
    [order, setOrder] = useState<Order | null>(null),
    [query, setQuery] = useState(""),
    [orderPage, setOrderPage] = useState(0),
    [page, setPage] = useState(0),
    [creating, setCreating] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [voidTarget, setVoidTarget] = useState<string | null>(null);
  const balance = detail
    ? detail.bill.total - detail.paid - detail.credited + detail.refunded
    : 0;
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const money = (n: number) =>
    new Intl.NumberFormat("en-PK", { style: "currency", currency }).format(
      n / 100,
    );
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    api<Listing>(`${base}?offset=${page * 50}`, { signal: c.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [base, page, revision]);
  useEffect(() => {
    if (!creating) return;
    const c = new AbortController();
    const timer = setTimeout(
      () =>
        api<{ items: Order[] }>(
          `${base}/matchable-orders?q=${encodeURIComponent(query)}&offset=${orderPage * 50}`,
          { signal: c.signal },
        )
          .then((r) => setOrders(r.items))
          .catch((e) => {
            if (e.name !== "AbortError") setError(e.message);
          }),
      180,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [base, query, orderPage, creating, revision]);
  async function open(id: string) {
    setError("");
    try {
      setDetail(await api<Detail>(`${base}/${id}`));
      setCreating(false);
      setVoidTarget(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function mutate(
    path: string,
    payload: Record<string, unknown>,
    deduplicate = true,
  ) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    const signature = JSON.stringify({ path, payload });
    if (deduplicate && pending.current?.signature !== signature)
      pending.current = { signature, id: newRequestId() };
    try {
      const r = await send<{ id?: string }>(
        path,
        deduplicate ? { ...payload, request: pending.current!.id } : payload,
      );
      pending.current = null;
      setRevision((x) => x + 1);
      setNotice("Supplier ledger updated.");
      if (detail) await open(detail.bill.id);
      else if (r.id) await open(r.id);
      setVoidTarget(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function createBill(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!order) return;
    const f = new FormData(e.currentTarget);
    mutate(base, {
      purchase: order.id,
      invoice_number: f.get("invoice"),
      invoice_date: f.get("invoice_date"),
      due_date: f.get("due_date"),
      tax: Math.round(Number(f.get("tax")) * 100),
      lines: order.lines
        .map((l) => ({
          product: l.product,
          quantity: Number(f.get(l.product)),
          unit_cost: l.unit_cost,
        }))
        .filter((l) => l.quantity > 0),
    });
  }
  function payment(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!detail) return;
    const f = new FormData(e.currentTarget);
    mutate(`${base}/${detail.bill.id}/payments`, {
      amount: Math.round(Number(f.get("amount")) * 100),
      method_id: f.get("method"),
      reference: f.get("reference"),
      paid_on: f.get("paid_on"),
    });
  }
  return (
    <div className="payables">
      <p>
        {tr(
          "Match supplier invoices to received purchase quantities. Record payments already made outside StockDesk.",
        )}
      </p>
      <div className="toolbar">
        <button
          className="primary"
          onClick={() => {
            setCreating(true);
            setDetail(null);
            setOrder(null);
            setError("");
          }}
        >
          {tr("Register supplier bill")}
        </button>
        <button
          className="secondary"
          onClick={() => {
            setCreating(false);
            setDetail(null);
            setRevision((x) => x + 1);
          }}
        >
          {tr("Bill register")}
        </button>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {creating ? (
        <form className="panel" onSubmit={createBill}>
          <h2>{tr("Match invoice")}</h2>
          <fieldset disabled={busy}>
            <label className="field">
              {tr("Search purchase reference or supplier")}
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setOrderPage(0);
                }}
              />
            </label>
            <label className="field">
              {tr("Purchase order")}
              <select
                aria-label={tr("Purchase order")}
                required
                value={order?.id || ""}
                onChange={(e) =>
                  setOrder(orders.find((o) => o.id === e.target.value) || null)
                }
              >
                <option value="">{tr("Select…")}</option>
                {orders.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.reference || o.id} · {o.supplier_name}
                  </option>
                ))}
              </select>
            </label>
            <div className="toolbar">
              <button
                type="button"
                disabled={!orderPage}
                onClick={() => setOrderPage((p) => p - 1)}
              >
                {tr("Previous")}
              </button>
              <button
                type="button"
                disabled={orders.length < 50}
                onClick={() => setOrderPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
            <div className="payables-fields">
              <label className="field">
                {tr("Supplier invoice number")}
                <input name="invoice" required maxLength={100} />
              </label>
              <label className="field">
                {tr("Invoice date")}
                <input
                  name="invoice_date"
                  type="date"
                  defaultValue={localDate()}
                  max={localDate()}
                  required
                />
              </label>
              <label className="field">
                {tr("Due date")}
                <input
                  name="due_date"
                  type="date"
                  defaultValue={localDate()}
                  required
                />
              </label>
              <label className="field">
                {tr("Invoice tax amount")}
                <input
                  name="tax"
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue="0"
                  required
                />
              </label>
            </div>
            {order && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{tr("Product")}</th>
                      <th>{tr("Received, unbilled")}</th>
                      <th>{tr("Agreed unit cost")}</th>
                      <th>{tr("Invoice quantity")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {order.lines.map((l) => (
                      <tr key={l.product}>
                        <td>
                          {l.sku} · {l.name}
                        </td>
                        <td>{l.unbilled}</td>
                        <td>{money(l.unit_cost)}</td>
                        <td>
                          <input
                            key={order.id + l.product}
                            aria-label={`${tr("Invoice quantity")} ${l.sku}`}
                            name={l.product}
                            type="number"
                            min="0"
                            max={l.unbilled}
                            step={l.fractional ? "0.001" : "1"}
                            defaultValue="0"
                            required
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p>
              {tr(
                "Zero quantity excludes a line. Cost differences must be resolved before registering the invoice. Tax is recorded from the supplier document.",
              )}
            </p>
            <button className="primary" disabled={!order || busy}>
              {tr("Post matched bill")}
            </button>
          </fieldset>
        </form>
      ) : detail ? (
        <>
          <section className="panel">
            <h2>
              {detail.bill.invoice_number} · {tr(detail.bill.status)}
            </h2>
            <p>
              {tr("Total")}: {money(detail.bill.total)} · {tr("Paid")}:{" "}
              {money(detail.paid)} · {tr("Credits")}: {money(detail.credited)} ·{" "}
              {tr("Refunds received")}: {money(detail.refunded)} ·{" "}
              {tr("Outstanding")}:{" "}
              {money(detail.bill.status === "void" ? 0 : Math.max(0, balance))}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Product")}</th>
                    <th>{tr("Quantity")}</th>
                    <th>{tr("Total")}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.lines.map((l) => (
                    <tr key={l.product}>
                      <td>{l.name}</td>
                      <td>{l.quantity}</td>
                      <td>{money(l.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {detail.bill.status === "posted" && (
              <button
                className="secondary"
                disabled={busy || detail.paid > 0 || detail.credits.length > 0}
                onClick={() => setVoidTarget("bill")}
              >
                {tr("Void bill")}
              </button>
            )}
          </section>
          {detail.bill.status === "posted" && balance > 0 && (
            <form
              key={`${detail.bill.id}-${detail.paid}`}
              className="panel"
              onSubmit={payment}
            >
              <h2>{tr("Record supplier payment")}</h2>
              <fieldset disabled={busy}>
                <div className="payables-fields">
                  <label className="field">
                    {tr("Amount")}
                    <input
                      name="amount"
                      type="number"
                      min="0.01"
                      max={balance / 100}
                      step="0.01"
                      required
                    />
                  </label>
                  <label className="field">
                    {tr("Payment date")}
                    <input
                      type="date"
                      name="paid_on"
                      defaultValue={localDate()}
                      max={localDate()}
                      required
                    />
                  </label>
                  <label className="field">
                    {tr("Payment reference")}
                    <input name="reference" required maxLength={150} />
                  </label>
                  <LookupSelect
                    tenant={tenant}
                    kind="payment_method"
                    label={tr("Payment method")}
                    name="method"
                  />
                </div>
                <p>
                  {tr(
                    "This records an external payment; it does not send money or change till cash.",
                  )}
                </p>
                <button className="primary" disabled={busy}>
                  {tr("Record payment")}
                </button>
              </fieldset>
            </form>
          )}
          <section className="panel">
            <h2>{tr("Payment history")}</h2>
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
                  {detail.payments.map((p) => (
                    <tr key={p.id}>
                      <td>{p.paid_on}</td>
                      <td>{money(p.amount)}</td>
                      <td>{p.method_name}</td>
                      <td>{p.reference}</td>
                      <td>{tr(p.status)}</td>
                      <td>
                        {p.status === "posted" && (
                          <button
                            disabled={busy}
                            onClick={() => setVoidTarget(p.id)}
                          >
                            {tr("Void payment record")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <SupplierReturns
            key={detail.bill.id}
            tenant={tenant}
            billId={detail.bill.id}
            currency={currency}
            canReturn={canReturn}
            active={detail.bill.status === "posted"}
            creditBalance={Math.max(0, -balance)}
            credits={detail.credits}
            refunds={detail.refunds}
            onSaved={async () => {
              await open(detail.bill.id);
              setRevision((x) => x + 1);
            }}
          />
          {voidTarget && (
            <form
              className="panel"
              onSubmit={(e) => {
                e.preventDefault();
                mutate(
                  voidTarget === "bill"
                    ? `${base}/${detail.bill.id}/void`
                    : `${base}/${detail.bill.id}/payments/${voidTarget}/void`,
                  { reason: new FormData(e.currentTarget).get("reason") },
                  false,
                );
              }}
            >
              <h2>{tr("Correct ledger record")}</h2>
              <p>
                {tr(
                  "Voiding preserves the audit history. It does not refund or reverse an external transfer.",
                )}
              </p>
              <label className="field">
                {tr("Reason")}
                <textarea name="reason" required maxLength={500} />
              </label>
              <button className="primary" disabled={busy}>
                {tr("Confirm void")}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setVoidTarget(null)}
              >
                {tr("Cancel")}
              </button>
            </form>
          )}
        </>
      ) : !data ? (
        <p>{tr("Loading…")}</p>
      ) : (
        <>
          <p>
            {tr("Ageing as of")} {data.as_of} · Asia/Karachi
          </p>
          <div className="kpis">
            {[
              ["outstanding", "Outstanding"],
              ["supplier_credit", "Credit owed by supplier"],
              ["not_due", "Not overdue"],
              ["days_1_7", "1–7 days overdue"],
              ["days_8_30", "8–30 days overdue"],
              ["days_31_plus", "31+ days overdue"],
            ].map(([key, label]) => (
              <div className="kpi" key={key}>
                <span>{tr(label)}</span>
                <strong>{money(data.summary[key])}</strong>
              </div>
            ))}
          </div>
          <div className="panel table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr("Invoice")}</th>
                  <th>{tr("Supplier")}</th>
                  <th>{tr("Due date")}</th>
                  <th>{tr("Total")}</th>
                  <th>{tr("Outstanding")}</th>
                  <th>{tr("Status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <button onClick={() => open(b.id)}>
                        {b.invoice_number}
                      </button>
                    </td>
                    <td>
                      {b.supplier_name}
                      <br />
                      <a
                        href={`${base}/suppliers/${b.supplier}/statement.pdf?language=${language}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {tr("Supplier statement PDF")}
                      </a>
                    </td>
                    <td>{b.due_date}</td>
                    <td>{money(b.total)}</td>
                    <td>
                      {money(b.status === "void" ? 0 : Math.max(0, b.balance))}
                    </td>
                    <td>{tr(b.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.items.length && <p>{tr("No supplier bills yet.")}</p>}
          </div>
          <div className="toolbar">
            <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
              {tr("Previous")}
            </button>
            <button
              disabled={data.items.length < 50}
              onClick={() => setPage((p) => p + 1)}
            >
              {tr("Next")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
