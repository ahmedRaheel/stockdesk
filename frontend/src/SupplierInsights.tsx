import { useEffect, useState } from "react";
import { api, send } from "./api";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";
import { t as tr } from "./i18n";
type Quote = {
  id: string;
  supplier: string;
  product: string;
  supplier_name: string;
  product_name: string;
  sku: string;
  unit_name: string;
  unit_cost: number;
  minimum_quantity: number;
  lead_days: number;
  valid_from: string;
  valid_until: string | null;
  active: boolean;
  eligible: boolean;
  version: number;
  notes: string;
};
type Performance = {
  id: string;
  name: string;
  orders: number;
  completed: number;
  pending_approval: number;
  open_orders: number;
  late_open_orders: number;
  delivery_samples: number;
  avg_first_delivery_days: number | null;
};
export default function SupplierInsights({
  tenant,
  currency,
}: {
  tenant: string;
  currency: string;
}) {
  const base = `/api/v1/tenants/${tenant}`;
  const [tab, setTab] = useState<"quotes" | "performance">("quotes"),
    [quotes, setQuotes] = useState<Quote[]>([]),
    [performance, setPerformance] = useState<Performance[]>([]);
  const [q, setQ] = useState(""),
    [quantity, setQuantity] = useState(1),
    [eligible, setEligible] = useState(false),
    [filterProduct, setFilterProduct] = useState<PurchaseOption>();
  const [page, setPage] = useState(0),
    [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [editor, setEditor] = useState<Quote | "new" | null>(null),
    [supplier, setSupplier] = useState<PurchaseOption>(),
    [product, setProduct] = useState<PurchaseOption>();
  const [revision, setRevision] = useState(0);
  const money = (n: number) =>
    new Intl.NumberFormat("en", { style: "currency", currency }).format(
      n / 100,
    );
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      const path =
        tab === "quotes"
          ? `/supplier-offers?q=${encodeURIComponent(q)}&quantity=${quantity || 1}&eligible=${eligible}&product=${encodeURIComponent(filterProduct?.id || "")}&offset=${page * 50}`
          : `/supplier-performance?q=${encodeURIComponent(q)}&offset=${page * 50}`;
      api<{ items: Quote[] | Performance[] }>(base + path, { signal: c.signal })
        .then((r) => {
          if (tab === "quotes") setQuotes(r.items as Quote[]);
          else setPerformance(r.items as Performance[]);
          setError("");
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => {
          if (!c.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, tab, q, quantity, eligible, filterProduct?.id, page, revision]);
  function edit(quote: Quote | "new") {
    setEditor(quote);
    setError("");
    setNotice("");
    setSupplier(
      quote === "new"
        ? undefined
        : { id: quote.supplier, name: quote.supplier_name },
    );
    setProduct(
      quote === "new"
        ? undefined
        : { id: quote.product, name: quote.product_name },
    );
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || !editor || !supplier || !product) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        supplier: supplier.id,
        product: product.id,
        unit_cost: Math.round(Number(f.get("unit_cost")) * 100),
        minimum_quantity: Number(f.get("minimum_quantity")),
        lead_days: Number(f.get("lead_days")),
        valid_from: f.get("valid_from"),
        valid_until: f.get("valid_until") || null,
        active: f.get("active") === "on",
        notes: f.get("notes"),
      };
      await send(
        base + "/supplier-offers" + (editor === "new" ? "" : `/${editor.id}`),
        editor === "new" ? payload : { ...payload, version: editor.version },
        editor === "new" ? "POST" : "PUT",
      );
      setEditor(null);
      setRevision((r) => r + 1);
      setNotice("Supplier quote saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const existing = editor && editor !== "new" ? editor : null;
  const items = tab === "quotes" ? quotes : performance;
  return (
    <section className="panel supplier-panel">
      <div className="panel-heading">
        <h2>{tr("Supplier insights")}</h2>
        <div className="actions">
          <button
            className="mini"
            onClick={() => setRevision((r) => r + 1)}
            disabled={loading || busy}
          >
            {tr("Refresh")}
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => edit("new")}
          >
            {tr("Add supplier quote")}
          </button>
        </div>
      </div>
      <div className="actions">
        <button
          className={tab === "quotes" ? "primary" : "secondary"}
          aria-pressed={tab === "quotes"}
          onClick={() => {
            setTab("quotes");
            setPage(0);
            setQ("");
          }}
        >
          {tr("Price comparison")}
        </button>
        <button
          className={tab === "performance" ? "primary" : "secondary"}
          aria-pressed={tab === "performance"}
          onClick={() => {
            setTab("performance");
            setPage(0);
            setQ("");
          }}
        >
          {tr("Delivery performance")}
        </button>
      </div>
      <p className="hint">
        {tab === "quotes"
          ? tr(
              "Prices are per catalog unit, before tax and freight. Quotes do not automatically change order prices. Compare the same product and quantity.",
            )
          : tr(
              "Observed orders and time to first receipt, not a delivery forecast. Approved orders start their lead-time clock at approval. Older orders without a lead-time snapshot are excluded from late counts.",
            )}
      </p>
      <div className="form-grid">
        <label className="field">
          <span>{tr("Search suppliers or products")}</span>
          <input
            value={q}
            maxLength={100}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </label>
        {tab === "quotes" && (
          <>
            <PurchaseLookup
              tenant={tenant}
              kind="products"
              value={filterProduct?.id || ""}
              selected={filterProduct}
              required={false}
              onChange={(p) => {
                setFilterProduct(p);
                setPage(0);
              }}
            />
            <label className="field">
              <span>{tr("Comparison quantity")}</span>
              <input
                type="number"
                min="0.001"
                max="1000000"
                step="0.001"
                value={quantity}
                onChange={(e) => {
                  setQuantity(Number(e.target.value));
                  setPage(0);
                }}
              />
            </label>
            <label className="field">
              <span>{tr("Eligible quotes only")}</span>
              <input
                type="checkbox"
                checked={eligible}
                onChange={(e) => {
                  setEligible(e.target.checked);
                  setPage(0);
                }}
              />
            </label>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {editor && (
        <form className="panel" onSubmit={save} key={existing?.id || "new"}>
          <h3>{tr(existing ? "Edit supplier quote" : "Add supplier quote")}</h3>
          <fieldset disabled={busy}>
            <div className="form-grid">
              {existing ? (
                <>
                  <p>{existing.supplier_name}</p>
                  <p>
                    {existing.sku} · {existing.product_name}
                  </p>
                </>
              ) : (
                <>
                  <PurchaseLookup
                    tenant={tenant}
                    kind="suppliers"
                    value={supplier?.id || ""}
                    selected={supplier}
                    onChange={setSupplier}
                  />
                  <PurchaseLookup
                    tenant={tenant}
                    kind="products"
                    value={product?.id || ""}
                    selected={product}
                    onChange={setProduct}
                  />
                </>
              )}
              <label className="field">
                <span>
                  {tr("Unit cost")} ({currency})
                </span>
                <input
                  name="unit_cost"
                  type="number"
                  min="0"
                  max="1000000000"
                  step="0.01"
                  required
                  defaultValue={(existing?.unit_cost || 0) / 100}
                />
              </label>
              <label className="field">
                <span>{tr("Minimum quantity")}</span>
                <input
                  name="minimum_quantity"
                  type="number"
                  min="0.001"
                  max="1000000"
                  step="0.001"
                  required
                  defaultValue={existing?.minimum_quantity || 1}
                />
              </label>
              <label className="field">
                <span>{tr("Lead time (days)")}</span>
                <input
                  name="lead_days"
                  type="number"
                  min="0"
                  max="365"
                  step="1"
                  required
                  defaultValue={existing?.lead_days ?? 7}
                />
              </label>
              <label className="field">
                <span>{tr("Valid from")}</span>
                <input
                  name="valid_from"
                  type="date"
                  required
                  defaultValue={existing?.valid_from || today}
                />
              </label>
              <label className="field">
                <span>{tr("Valid until")}</span>
                <input
                  name="valid_until"
                  type="date"
                  defaultValue={existing?.valid_until || ""}
                />
              </label>
              <label className="field">
                <span>{tr("Active")}</span>
                <input
                  name="active"
                  type="checkbox"
                  defaultChecked={existing?.active ?? true}
                />
              </label>
              <label className="field">
                <span>{tr("Notes")}</span>
                <textarea
                  name="notes"
                  maxLength={500}
                  defaultValue={existing?.notes || ""}
                />
              </label>
            </div>
            <div className="actions">
              <button className="primary" disabled={!supplier || !product}>
                {tr(busy ? "Saving…" : "Save quote")}
              </button>
              <button
                className="secondary"
                type="button"
                onClick={() => setEditor(null)}
              >
                {tr("Cancel")}
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {loading ? (
        <p role="status">{tr("Loading…")}</p>
      ) : (
        <div className="table-scroll">
          <table>
            {tab === "quotes" ? (
              <>
                <thead>
                  <tr>
                    {[
                      "Product",
                      "Supplier",
                      "Unit cost",
                      "Minimum quantity",
                      "Lead time (days)",
                      "Validity",
                      "Eligible",
                      "Actions",
                    ].map((h) => (
                      <th key={h}>{tr(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {quotes.map((o) => (
                    <tr key={o.id}>
                      <td>
                        <b>
                          {o.sku} · {o.product_name}
                        </b>
                        <small>{o.unit_name}</small>
                      </td>
                      <td>{o.supplier_name}</td>
                      <td className="numeric">{money(o.unit_cost)}</td>
                      <td>{o.minimum_quantity}</td>
                      <td>{o.lead_days}</td>
                      <td>
                        {o.valid_from} / {o.valid_until || "—"}
                        <small>{tr(o.active ? "Active" : "Inactive")}</small>
                      </td>
                      <td>{tr(o.eligible ? "Eligible" : "Not eligible")}</td>
                      <td>
                        <button
                          className="mini"
                          onClick={() => edit(o)}
                          disabled={busy}
                        >
                          {tr("Edit")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead>
                  <tr>
                    {[
                      "Supplier",
                      "Orders",
                      "Completed",
                      "Pending approval",
                      "Open orders",
                      "Late open orders",
                      "Receipt samples",
                      "Average days to first receipt",
                    ].map((h) => (
                      <th key={h}>{tr(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {performance.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <b>{s.name}</b>
                      </td>
                      <td>{s.orders}</td>
                      <td>{s.completed}</td>
                      <td>{s.pending_approval}</td>
                      <td>{s.open_orders}</td>
                      <td>{s.late_open_orders}</td>
                      <td>{s.delivery_samples}</td>
                      <td>{s.avg_first_delivery_days ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </table>
          {!items.length && <p>{tr("No results on this page.")}</p>}
        </div>
      )}
      <div className="pagination">
        <span>
          {tr("Page")} {page + 1}
        </span>
        <div className="actions">
          <button
            className="mini"
            disabled={!page || loading}
            onClick={() => setPage((p) => p - 1)}
          >
            {tr("Previous")}
          </button>
          <button
            className="mini"
            disabled={items.length < 50 || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            {tr("Next")}
          </button>
        </div>
      </div>
    </section>
  );
}
