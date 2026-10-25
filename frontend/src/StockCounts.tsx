import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
type Product = {
  id: string;
  sku: string;
  barcode?: string;
  name: string;
  active: boolean;
};
type Count = {
  id: string;
  reference: string;
  status: string;
  created_by: string;
  counter_name?: string;
  created: string;
  note: string;
};
type Line = {
  product: string;
  batch: string;
  name: string;
  sku: string;
  lot: string;
  expires: string | null;
  expected: number;
  counted: number | null;
  revision: number;
  current_revision: number;
  fractional: boolean;
};
export default function StockCounts({
  tenant,
  products,
  userId,
  canApprove,
  onPosted,
}: {
  tenant: string;
  products: Product[];
  userId: string;
  canApprove: boolean;
  onPosted: () => void;
}) {
  const base = `/api/v1/tenants/${tenant}/stock-counts`;
  const [items, setItems] = useState<Count[]>([]),
    [detail, setDetail] = useState<{ count: Count; lines: Line[] } | null>(
      null,
    ),
    [draft, setDraft] = useState<Record<string, string>>({}),
    [selected, setSelected] = useState<string[]>([]),
    [reference, setReference] = useState(""),
    [scan, setScan] = useState(""),
    [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [page, setPage] = useState(0);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  async function load() {
    const d = await api<{ items: Count[] }>(
      base + `?limit=50&offset=${page * 50}`,
    );
    setItems(d.items);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [tenant, page]);
  async function open(id: string) {
    const d = await api<{ count: Count; lines: Line[] }>(base + "/" + id);
    setDetail(d);
    setDraft(
      Object.fromEntries(
        d.lines.map((x) => [
          x.batch,
          x.counted === null ? "" : String(x.counted),
        ]),
      ),
    );
    setNote("");
  }
  async function action(kind: string) {
    setBusy(true);
    setError("");
    try {
      if (kind === "create") {
        const body = { reference, products: selected },
          signature = JSON.stringify(body);
        if (pending.current?.signature !== signature)
          pending.current = { signature, id: crypto.randomUUID() };
        const r = await send<{ id: string }>(base, {
          ...body,
          request: pending.current.id,
        });
        await open(r.id);
        pending.current = null;
        setSelected([]);
        setReference("");
      } else if (detail) {
        if (kind === "save" || kind === "submit") {
          const lines = detail.lines
            .filter((x) => draft[x.batch] !== "")
            .map((x) => ({ batch: x.batch, counted: Number(draft[x.batch]) }));
          if (!lines.length)
            throw Error(tr("Record quantities before saving."));
          await send(base + "/" + detail.count.id + "/lines", { lines }, "PUT");
          if (kind === "submit")
            await send(base + "/" + detail.count.id + "/submit", {});
        } else await send(base + "/" + detail.count.id + "/" + kind, { note });
        await open(detail.count.id);
        if (kind === "post") onPosted();
      }
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const editable =
    detail?.count.status === "draft" && detail.count.created_by === userId;
  const stale = detail?.lines.some((x) => x.revision !== x.current_revision);
  return (
    <div className="stock-counts">
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      <p>
        {tr(
          "Count physical quantities by batch. A different manager approves adjustments. Stock movement during the count requires a new count.",
        )}
      </p>
      {!detail ? (
        <>
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              action("create");
            }}
          >
            <fieldset disabled={busy}>
              <h2>{tr("Start stock count")}</h2>
              <label className="field">
                <span>{tr("Reference")}</span>
                <input
                  required
                  maxLength={150}
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                />
              </label>
              <label className="field">
                <span>{tr("Scan or enter SKU to select")}</span>
                <input
                  value={scan}
                  onChange={(e) => setScan(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      const p = products.find(
                        (x) =>
                          x.active &&
                          (x.sku.toLowerCase() === scan.trim().toLowerCase() ||
                            x.barcode === scan.trim()),
                      );
                      if (p) {
                        setSelected((xs) =>
                          xs.includes(p.id) ? xs : [...xs, p.id],
                        );
                        setScan("");
                        setError("");
                      } else setError(tr("Product not found."));
                    }
                  }}
                />
              </label>
              <label className="field">
                <span>{tr("Products to count")}</span>
                <select
                  aria-label={tr("Products to count")}
                  multiple
                  size={6}
                  required
                  value={selected}
                  onChange={(e) =>
                    setSelected(
                      Array.from(e.target.selectedOptions, (x) => x.value),
                    )
                  }
                >
                  {products
                    .filter((p) => p.active)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.sku} · {p.name}
                      </option>
                    ))}
                </select>
              </label>
              <p>{selected.length} / 200</p>
              <button
                className="primary"
                disabled={!selected.length || selected.length > 200}
              >
                {tr("Start count")}
              </button>
            </fieldset>
          </form>
          <div className="panel table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr("Reference")}</th>
                  <th>{tr("Counter")}</th>
                  <th>{tr("Status")}</th>
                  <th>{tr("Date")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}>
                    <td>{c.reference}</td>
                    <td>{c.counter_name}</td>
                    <td>{tr(c.status)}</td>
                    <td>{new Date(c.created).toLocaleString()}</td>
                    <td>
                      <button
                        className="mini"
                        onClick={() =>
                          open(c.id).catch((e) => setError(e.message))
                        }
                      >
                        {tr("Review")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="actions">
              <button disabled={!page} onClick={() => setPage(page - 1)}>
                {tr("Previous")}
              </button>
              <span>{page + 1}</span>
              <button
                disabled={items.length < 50}
                onClick={() => setPage(page + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </div>
        </>
      ) : (
        <>
          <button
            className="secondary"
            onClick={() => {
              setDetail(null);
              setError("");
            }}
          >
            {tr("Back to counts")}
          </button>
          <section className="panel">
            <h2>
              {detail.count.reference} · {tr(detail.count.status)}
            </h2>
            {stale && detail.count.status !== "posted" && (
              <p className="form-error">
                {tr(
                  "Stock moved after this count opened. Cancel it and recount before posting.",
                )}
              </p>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Product")}</th>
                    <th>{tr("Batch")}</th>
                    <th>{tr("Expiry")}</th>
                    <th>{tr("Physical quantity")}</th>
                    {detail.count.status !== "draft" && (
                      <>
                        <th>{tr("Expected")}</th>
                        <th>{tr("Variance")}</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {detail.lines.map((l) => (
                    <tr key={l.batch}>
                      <td>
                        {l.name}
                        <small>{l.sku}</small>
                      </td>
                      <td>{l.lot}</td>
                      <td>{l.expires || "—"}</td>
                      <td>
                        <input
                          aria-label={
                            tr("Physical quantity") + " " + l.sku + " " + l.lot
                          }
                          type="number"
                          min="0"
                          max="1000000000"
                          step={l.fractional ? "0.001" : "1"}
                          value={draft[l.batch] ?? ""}
                          disabled={!editable || busy}
                          onChange={(e) =>
                            setDraft({ ...draft, [l.batch]: e.target.value })
                          }
                        />
                      </td>
                      {detail.count.status !== "draft" && (
                        <>
                          <td>{l.expected}</td>
                          <td>
                            {l.counted === null
                              ? "—"
                              : Number(l.counted) - Number(l.expected)}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {editable && (
              <div className="actions">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => action("save")}
                >
                  {tr("Save quantities")}
                </button>
                <button
                  className="primary"
                  disabled={
                    busy || detail.lines.some((l) => draft[l.batch] === "")
                  }
                  onClick={() => action("submit")}
                >
                  {tr("Submit for approval")}
                </button>
              </div>
            )}
            {["draft", "submitted"].includes(detail.count.status) && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action("post");
                }}
              >
                <label className="field">
                  <span>{tr("Decision note")}</span>
                  <textarea
                    required
                    maxLength={500}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                <div className="actions">
                  {canApprove &&
                    detail.count.created_by !== userId &&
                    detail.count.status === "submitted" && (
                      <button
                        className="primary"
                        disabled={busy || stale || !note.trim()}
                      >
                        {tr("Approve and post adjustments")}
                      </button>
                    )}
                  {(canApprove || detail.count.created_by === userId) && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy || !note.trim()}
                      onClick={() => action("cancel")}
                    >
                      {tr("Cancel count")}
                    </button>
                  )}
                </div>
              </form>
            )}
            {detail.count.note && <p>{detail.count.note}</p>}
          </section>
        </>
      )}
    </div>
  );
}
