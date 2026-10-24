import { useEffect, useRef, useState } from "react";
import { Plus, RefreshCw, Truck, X } from "lucide-react";
import { api, send } from "./api";

type Product = {
  id: string;
  sku: string;
  name: string;
  active: boolean;
  cost: number;
};
type Supplier = {
  id: string;
  name: string;
  contact: string;
  lead_days: number;
};
type Line = {
  product: string;
  quantity: number;
  received: number;
  unit_cost: number;
  name: string;
  sku: string;
};
type Order = {
  id: string;
  reference: string;
  supplier_name: string;
  status: string;
  created: string;
  lines: Line[];
};
type DraftLine = { product: string; quantity: number; unit_cost: number };
type Props = {
  tenant: string;
  currency: string;
  products: Product[];
  onReceived: () => void;
};

/** Purchasing owns its remote state. Tenant changes remount the feature at its boundary. */
export default function Purchasing({
  tenant,
  currency,
  products,
  onReceived,
}: Props) {
  const base = `/api/v1/tenants/${encodeURIComponent(tenant)}`;
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState<
    "supplier" | "order" | "receive" | "cancel" | null
  >(null);
  const [selected, setSelected] = useState<Order | null>(null);
  const [lines, setLines] = useState<DraftLine[]>([
    { product: "", quantity: 1, unit_cost: 0 },
  ]);
  const [batchInfo, setBatchInfo] = useState<
    Record<string, { lot: string; expires: string }>
  >({});
  const [receiving, setReceiving] = useState<Record<string, number>>({});
  const [page, setPage] = useState(0);
  const request = useRef<{ signature: string; id: string } | null>(null);
  const modalRef = useRef<HTMLElement>(null);
  const money = (n: number) =>
    new Intl.NumberFormat("en", { style: "currency", currency }).format(
      n / 100,
    );
  const activeProducts = products.filter((p) => p.active);

  async function load(signal?: AbortSignal) {
    setLoading(true);
    try {
      const [supplierPage, orderPage] = await Promise.all([
        api<{ items: Supplier[] }>(`${base}/suppliers?limit=200`, { signal }),
        api<{ items: Order[] }>(
          `${base}/purchase-orders?limit=50&offset=${page * 50}`,
          { signal },
        ),
      ]);
      setSuppliers(supplierPage.items);
      setOrders(orderPage.items);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError"))
        setError((e as Error).message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [tenant, page]);
  useEffect(() => {
    if (!modal) return;
    const prior = document.activeElement as HTMLElement;
    modalRef.current
      ?.querySelector<HTMLElement>("input,select,button")
      ?.focus();
    return () => prior?.focus();
  }, [modal]);

  function open(kind: typeof modal, order: Order | null = null) {
    setError("");
    setNotice("");
    request.current = null;
    setSelected(order);
    setReceiving({});
    setBatchInfo({});
    setLines([{ product: "", quantity: 1, unit_cost: 0 }]);
    setModal(kind);
  }
  function deduplicated(payload: object) {
    const signature = JSON.stringify(payload);
    if (request.current?.signature !== signature)
      request.current = { signature, id: crypto.randomUUID() };
    return { ...payload, request: request.current.id };
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      if (modal === "supplier") {
        await send(`${base}/suppliers`, {
          name: form.get("name"),
          contact: form.get("contact"),
          lead_days: Number(form.get("lead_days")),
        });
      } else if (modal === "order") {
        await send(
          `${base}/purchase-orders`,
          deduplicated({
            supplier: form.get("supplier"),
            reference: form.get("reference"),
            lines,
          }),
        );
      } else if (modal === "receive" && selected) {
        const receipts = Object.entries(receiving)
          .filter(([, quantity]) => quantity > 0)
          .map(([product, quantity]) => ({
            product,
            quantity,
            lot: batchInfo[product]?.lot || "",
            expires: batchInfo[product]?.expires || null,
          }));
        if (!receipts.length)
          throw new Error("Enter at least one quantity received.");
        await send(
          `${base}/purchase-orders/${selected.id}/receipts`,
          deduplicated({ lines: receipts }),
        );
        onReceived();
      } else if (modal === "cancel" && selected) {
        await send(`${base}/purchase-orders/${selected.id}/cancel`, {});
      }
      request.current = null;
      setModal(null);
      setNotice("Saved. Stock changes are recorded in the ledger.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function updateLine(index: number, next: Partial<DraftLine>) {
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...next } : line)),
    );
  }

  return (
    <>
      {!modal && error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="operation-notice" role="status">
          {notice}
        </div>
      )}
      <div className="purchasing-toolbar">
        <p>Order stock, record deliveries, and track outstanding quantities.</p>
        <div className="actions">
          <button
            className="secondary"
            onClick={() => load()}
            disabled={loading}
          >
            <RefreshCw size={15} />
            Refresh
          </button>
          <button className="secondary" onClick={() => open("supplier")}>
            <Plus size={15} />
            Supplier
          </button>
          <button
            className="primary"
            disabled={!suppliers.length || !activeProducts.length}
            onClick={() => open("order")}
          >
            <Plus size={15} />
            Purchase order
          </button>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Purchase orders</h2>
            <p>
              50 orders per page · quantities use each product’s selling unit
            </p>
          </div>
          <Truck size={20} />
        </div>
        {loading ? (
          <p role="status">Loading purchasing…</p>
        ) : !orders.length ? (
          <div className="empty">
            <h3>No purchase orders on this page</h3>
            <p>Add a supplier and products, then create your first order.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Reference / created</th>
                  <th>Supplier</th>
                  <th>Status</th>
                  <th>Ordered</th>
                  <th>Outstanding</th>
                  <th>Order value</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>
                      <b>
                        {order.reference || order.id.slice(0, 8).toUpperCase()}
                      </b>
                      <small>
                        {new Date(order.created).toLocaleDateString()}
                      </small>
                    </td>
                    <td>{order.supplier_name}</td>
                    <td>
                      <span
                        className={`badge ${order.status === "partial" ? "amber" : order.status === "cancelled" ? "red" : ""}`}
                      >
                        {order.status}
                      </span>
                    </td>
                    <td>
                      {order.lines.reduce((sum, l) => sum + l.quantity, 0)}
                    </td>
                    <td>
                      {order.status === "cancelled"
                        ? "Cancelled"
                        : order.lines.reduce(
                            (sum, l) => sum + l.quantity - l.received,
                            0,
                          )}
                    </td>
                    <td className="numeric">
                      {money(
                        order.lines.reduce(
                          (sum, l) => sum + l.quantity * l.unit_cost,
                          0,
                        ),
                      )}
                    </td>
                    <td>
                      <div className="actions">
                        <button
                          className="mini"
                          onClick={() => open("receive", order)}
                        >
                          {["open", "partial"].includes(order.status)
                            ? "Receive / details"
                            : "View details"}
                        </button>
                        {["open", "partial"].includes(order.status) && (
                          <button
                            className="mini"
                            onClick={() => open("cancel", order)}
                          >
                            Cancel remainder
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <span>Page {page + 1}</span>
          <div>
            <button
              className="mini"
              disabled={!page || loading}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </button>
            <button
              className="mini"
              disabled={orders.length < 50 || loading}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
      <section className="panel supplier-panel">
        <div className="panel-heading">
          <h2>Suppliers</h2>
          <span className="subtle-tag">First 200 by name</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Contact</th>
                <th>Lead time</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((s) => (
                <tr key={s.id}>
                  <td>
                    <b>{s.name}</b>
                  </td>
                  <td>{s.contact || "—"}</td>
                  <td>{s.lead_days} days</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {modal && (
        <div className="modal-overlay">
          <section
            ref={modalRef}
            className="modal purchase-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="purchase-title"
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) setModal(null);
              if (event.key === "Tab") {
                const nodes = [
                  ...(modalRef.current?.querySelectorAll<HTMLElement>(
                    "button:not(:disabled),input:not(:disabled),select:not(:disabled)",
                  ) || []),
                ];
                const first = nodes[0],
                  last = nodes[nodes.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last?.focus();
                }
                if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <div className="modal-heading">
              <h2 id="purchase-title">
                {
                  {
                    supplier: "New supplier",
                    order: "New purchase order",
                    receive: "Goods receiving",
                    cancel: "Cancel outstanding quantities",
                  }[modal]
                }
              </h2>
              <button
                className="icon-button"
                aria-label="Close"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={submit}>
              <fieldset disabled={busy}>
                {modal === "supplier" && (
                  <>
                    <label className="field">
                      <span>Supplier name</span>
                      <input name="name" required maxLength={150} />
                    </label>
                    <label className="field">
                      <span>Contact details</span>
                      <input name="contact" maxLength={250} />
                    </label>
                    <label className="field">
                      <span>Typical lead time (days)</span>
                      <input
                        name="lead_days"
                        type="number"
                        min={0}
                        max={365}
                        step="0.001"
                        defaultValue={7}
                        required
                      />
                    </label>
                  </>
                )}
                {modal === "order" && (
                  <>
                    <div className="form-grid">
                      <label className="field">
                        <span>Supplier</span>
                        <select name="supplier" required>
                          {suppliers.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Your order reference</span>
                        <input name="reference" maxLength={150} />
                      </label>
                    </div>
                    <div className="purchase-lines">
                      {lines.map((line, i) => (
                        <div className="purchase-line" key={i}>
                          <label className="field">
                            <span>Product</span>
                            <select
                              required
                              aria-label={`Product line ${i + 1}`}
                              value={line.product}
                              onChange={(e) => {
                                const p = products.find(
                                  (p) => p.id === e.target.value,
                                );
                                updateLine(i, {
                                  product: e.target.value,
                                  unit_cost: p?.cost || 0,
                                });
                              }}
                            >
                              <option value="">Select product</option>
                              {activeProducts.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.sku} · {p.name}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="field">
                            <span>Units</span>
                            <input
                              type="number"
                              min={1}
                              max={1000000}
                              step="0.001"
                              required
                              value={line.quantity}
                              onChange={(e) =>
                                updateLine(i, {
                                  quantity: Number(e.target.value),
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Unit cost ({currency})</span>
                            <input
                              type="number"
                              min={0}
                              step="0.01"
                              required
                              value={line.unit_cost / 100}
                              onChange={(e) =>
                                updateLine(i, {
                                  unit_cost: Math.round(
                                    Number(e.target.value) * 100,
                                  ),
                                })
                              }
                            />
                          </label>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Remove line ${i + 1}`}
                            disabled={lines.length === 1}
                            onClick={() =>
                              setLines(lines.filter((_, n) => i !== n))
                            }
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      className="secondary"
                      disabled={lines.length >= 100}
                      onClick={() =>
                        setLines([
                          ...lines,
                          { product: "", quantity: 1, unit_cost: 0 },
                        ])
                      }
                    >
                      <Plus size={15} />
                      Add line
                    </button>
                    <p className="hint">
                      Creating an order does not change stock. Costs are
                      recorded on the order; receiving does not change the
                      catalog purchase cost.
                    </p>
                  </>
                )}
                {modal === "receive" && selected && (
                  <>
                    <p>
                      {selected.supplier_name} ·{" "}
                      {selected.reference || selected.id}
                    </p>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Product</th>
                            <th>Ordered</th>
                            <th>Received</th>
                            <th>Receive now</th>
                            <th>Batch / expiry</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.lines.map((l) => (
                            <tr key={l.product}>
                              <td>
                                <b>{l.name}</b>
                                <small>{l.sku}</small>
                              </td>
                              <td>{l.quantity}</td>
                              <td>{l.received}</td>
                              <td>
                                <input
                                  aria-label={`Receive ${l.name}`}
                                  className="receive-input"
                                  type="number"
                                  min={0}
                                  max={l.quantity - l.received}
                                  step="0.001"
                                  value={receiving[l.product] || 0}
                                  disabled={
                                    !["open", "partial"].includes(
                                      selected.status,
                                    ) || l.received === l.quantity
                                  }
                                  onChange={(e) =>
                                    setReceiving({
                                      ...receiving,
                                      [l.product]: Number(e.target.value),
                                    })
                                  }
                                />
                              </td>
                              <td>
                                <input
                                  aria-label={"Batch " + l.name}
                                  placeholder="Batch number"
                                  value={batchInfo[l.product]?.lot || ""}
                                  onChange={(e) =>
                                    setBatchInfo({
                                      ...batchInfo,
                                      [l.product]: {
                                        lot: e.target.value,
                                        expires:
                                          batchInfo[l.product]?.expires || "",
                                      },
                                    })
                                  }
                                />
                                <input
                                  aria-label={"Expiry " + l.name}
                                  type="date"
                                  value={batchInfo[l.product]?.expires || ""}
                                  onChange={(e) =>
                                    setBatchInfo({
                                      ...batchInfo,
                                      [l.product]: {
                                        lot: batchInfo[l.product]?.lot || "",
                                        expires: e.target.value,
                                      },
                                    })
                                  }
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="hint">
                      Enter physically received units only. Partial deliveries
                      leave the remainder open.
                    </p>
                  </>
                )}
                {modal === "cancel" && (
                  <p>
                    Cancel the unreceived remainder? Previously received stock
                    stays in inventory. This does not send a cancellation to the
                    supplier.
                  </p>
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
                    onClick={() => setModal(null)}
                  >
                    Close
                  </button>
                  {!(
                    modal === "receive" &&
                    selected &&
                    !["open", "partial"].includes(selected.status)
                  ) && (
                    <button className="primary" disabled={busy}>
                      {busy
                        ? "Saving…"
                        : modal === "receive"
                          ? "Record delivery"
                          : modal === "cancel"
                            ? "Cancel remainder"
                            : "Save"}
                    </button>
                  )}
                </div>
              </fieldset>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
