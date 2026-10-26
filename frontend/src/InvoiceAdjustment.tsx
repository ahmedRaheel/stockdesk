import { newRequestId } from "./requestId";
import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";

export default function InvoiceAdjustment({
  tenant,
  sale,
  money,
  onClose,
  onSaved,
  showReceipt,
}: {
  tenant: string;
  sale: any;
  money: (n: number) => string;
  onClose: () => void;
  onSaved: () => void;
  showReceipt: (id: string) => void;
}) {
  const base = `/api/v1/tenants/${tenant}/sales/${sale.id}/adjustments`;
  const [receipt, setReceipt] = useState<any>(),
    [lines, setLines] = useState<any[]>([]),
    [replacements, setReplacements] = useState<any[]>([]),
    [selected, setSelected] = useState<PurchaseOption>(),
    [quote, setQuote] = useState<any>(),
    [result, setResult] = useState<any>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [settlement, setSettlement] = useState("cash"),
    [received, setReceived] = useState(""),
    [reference, setReference] = useState(""),
    [rate, setRate] = useState("0"),
    [prescription, setPrescription] = useState("");
  const pending = useRef<{ signature: string; id: string } | undefined>(
    undefined,
  );
  useEffect(() => {
    Promise.all([
      api<any>(`/api/v1/tenants/${tenant}/sales/${sale.id}`),
      api<any>(base + "/batches"),
    ])
      .then(([r, allocation]) => {
        setReceipt(r);
        setLines(
          r.items.map((i: any) => ({
            ...i,
            returnQty: "0",
            reason: "damaged",
            restock: false,
            batches: (
              allocation.items.find((a: any) => a.item === i.id)?.batches || []
            )
              .filter((b: any) => Number(b.available) > 0)
              .map((b: any) => ({ ...b, quantity: "0" })),
          })),
        );
      })
      .catch((e) => setError(e.message));
  }, [tenant, sale.id]);
  function update(index: number, key: string, value: any) {
    setQuote(undefined);
    setLines(
      lines.map((l, i) =>
        i === index
          ? {
              ...l,
              [key]: value,
              ...(key === "reason" ? { restock: false } : {}),
            }
          : l,
      ),
    );
  }
  const body = () => ({
    revision: receipt.sale.revision,
    returns: lines
      .filter((l) => Number(l.returnQty) > 0)
      .map((l) => ({
        item: l.id,
        quantity: l.returnQty,
        reason: l.reason,
        restock: l.restock,
        batches: l.batches
          .filter((b: any) => Number(b.quantity) > 0)
          .map((b: any) => ({ batch: b.batch, quantity: b.quantity })),
      })),
    replacements: replacements.map((l) => ({ id: l.id, quantity: l.quantity })),
    tax_bps: Math.round(Number(rate) * 100),
    prescription_reference: prescription,
  });
  async function preview() {
    setBusy(true);
    setError("");
    try {
      setQuote(await send(base + "/preview", body()));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const approvalRequest = useRef<{ signature: string; id: string } | undefined>(
    undefined,
  );
  const [approval, setApproval] = useState<{ signature: string; id: string }>();
  async function commit(requestApproval = false) {
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...body(),
        quote_token: quote.quote_token,
        settlement,
        tendered: Math.round(Number(received || 0) * 100),
        reference,
      };
      const signature = JSON.stringify(payload);
      if (pending.current?.signature !== signature)
        pending.current = { signature, id: newRequestId() };
      if (requestApproval) {
        if (approvalRequest.current?.signature !== signature)
          approvalRequest.current = { signature, id: newRequestId() };
        const answer: any = await send(
          `/api/v1/tenants/${tenant}/transaction-approvals`,
          {
            request: approvalRequest.current.id,
            kind: "adjustment",
            sale: sale.id,
            payload,
          },
        );
        approvalRequest.current = undefined;
        setApproval({ signature, id: answer.id });
        return;
      }
      setResult(
        await send(base, {
          ...payload,
          request: pending.current.id,
          approval_id: approval?.signature === signature ? approval.id : null,
        }),
      );
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-overlay">
      <section
        className="modal invoice-adjustment"
        role="dialog"
        aria-modal="true"
        aria-label={tr("Return or exchange items")}
        style={{
          width: "min(960px,96vw)",
          maxHeight: "92vh",
          overflowY: "auto",
          padding: 24,
        }}
      >
        <div className="panel-heading">
          <div>
            <h2>{tr("Return or exchange items")}</h2>
            <p>
              {sale.invoice_number} · {sale.customer}
            </p>
          </div>
          <button className="secondary" disabled={busy} onClick={onClose}>
            {tr("Close")}
          </button>
        </div>
        {error && (
          <p role="alert" className="form-error">
            {tr(error)}
          </p>
        )}
        {result ? (
          <>
            <h3>{tr("Adjustment saved")}</h3>
            <p>
              {tr("Return credit")}: <b>{money(result.credit)}</b>
            </p>
            <p>
              {tr("Revised invoice total")}:{" "}
              <b>{money(result.revised_total)}</b>
            </p>
            <h3>
              {tr(
                result.net > 0
                  ? "Collected from customer"
                  : result.net < 0
                    ? "Refunded to customer"
                    : "No payment difference",
              )}
              : {money(Math.abs(result.net))}
            </h3>
            {result.change > 0 && (
              <h3>
                {tr("Change returned")}: {money(result.change)}
              </h3>
            )}
            {result.outstanding_before > 0 && (
              <p>
                {tr("Khata debt reduction")}: {money(result.debt_credit)} ·{" "}
                {tr("Financing balance waived")}: {money(result.debt_waiver)} ·{" "}
                {tr("Remaining invoice debt")}:{" "}
                {money(result.outstanding_after)}
              </p>
            )}
            <p>
              {tr("Adjustment reference")}: {result.id}
            </p>
            <button className="secondary" onClick={() => showReceipt(sale.id)}>
              {tr("Revised receipt")}
            </button>
            {result.replacement_sale && (
              <button
                className="secondary"
                onClick={() => showReceipt(result.replacement_sale)}
              >
                {tr("Replacement receipt")} · {result.replacement_invoice}
              </button>
            )}
          </>
        ) : (
          receipt && (
            <>
              <p className="hint">
                {tr(
                  "Select only the quantities returned. Expired, damaged and opened items are written off. Only verified unopened incorrect items may be restocked. Replacement items use current prices and taxes.",
                )}
              </p>
              {receipt.sale.return_pair_products?.length > 0 && (
                <div className="hint">
                  <p>
                    {tr(
                      "Return all remaining qualifying and reward product quantities together for this cross-product offer.",
                    )}
                  </p>
                  <button
                    className="secondary"
                    onClick={() => {
                      setQuote(undefined);
                      setLines(
                        lines.map((l) =>
                          receipt.sale.return_pair_products.includes(l.product)
                            ? { ...l, returnQty: String(l.quantity) }
                            : l,
                        ),
                      );
                    }}
                  >
                    {tr("Select all promotional items")}
                  </button>
                </div>
              )}
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{tr("Product")}</th>
                      <th>{tr("Available to return")}</th>
                      <th>{tr("Return quantity")}</th>
                      <th>{tr("Return reason")}</th>
                      <th>{tr("Restock")}</th>
                      <th>{tr("Returned batches")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l, i) => (
                      <tr key={l.id}>
                        <td>
                          {l.name}
                          <small>{l.sku}</small>
                        </td>
                        <td>{l.quantity}</td>
                        <td>
                          <input
                            aria-label={`${tr("Return quantity")} ${l.name}`}
                            type="number"
                            min="0"
                            max={l.quantity}
                            step="0.001"
                            value={l.returnQty}
                            onChange={(e) =>
                              update(i, "returnQty", e.target.value)
                            }
                            style={{ width: 100 }}
                          />
                        </td>
                        <td>
                          <select
                            aria-label={`${tr("Return reason")} ${l.name}`}
                            value={l.reason}
                            onChange={(e) =>
                              update(i, "reason", e.target.value)
                            }
                          >
                            {[
                              ["expired", "Expired item"],
                              ["damaged", "Damaged item"],
                              ["incorrect", "Incorrect item"],
                              ["opened", "Opened item"],
                            ].map(([v, n]) => (
                              <option key={v} value={v}>
                                {tr(n)}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`${tr("Restock")} ${l.name}`}
                            disabled={l.reason !== "incorrect"}
                            checked={l.restock}
                            onChange={(e) =>
                              update(i, "restock", e.target.checked)
                            }
                          />
                        </td>
                        <td>
                          {l.batches.map((b: any) => (
                            <label className="field" key={b.batch}>
                              <span>
                                {b.lot || tr("Unlabelled batch")} ·{" "}
                                {tr("Available to return")}: {b.available}
                                {b.expires ? ` · ${b.expires}` : ""}
                              </span>
                              <input
                                type="number"
                                min="0"
                                max={b.available}
                                step="0.001"
                                aria-label={`${tr("Batch return quantity")} ${l.name} ${b.lot || b.batch}`}
                                value={b.quantity}
                                onChange={(e) =>
                                  update(
                                    i,
                                    "batches",
                                    l.batches.map((x: any) =>
                                      x.batch === b.batch
                                        ? { ...x, quantity: e.target.value }
                                        : x,
                                    ),
                                  )
                                }
                              />
                            </label>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="hint">
                {tr(
                  "Batch quantities must total the return quantity. Leave all at zero for automatic allocation; partial restocking from multiple batches requires selection.",
                )}
              </p>
              <p className="hint">
                {tr(
                  "Khata returns reduce this invoice's debt first, starting with the latest unpaid installments. Remaining credit funds replacements or a refund. Fully returning the invoice waives its remaining financing balance.",
                )}
              </p>
              <h3>{tr("Replacement items (optional)")}</h3>
              <PurchaseLookup
                tenant={tenant}
                kind="products"
                required={false}
                value={selected?.id || ""}
                selected={selected}
                onChange={setSelected}
              />
              <button
                className="secondary"
                disabled={
                  !selected || replacements.some((l) => l.id === selected.id)
                }
                onClick={() => {
                  setReplacements([
                    ...replacements,
                    { ...selected, quantity: "1" },
                  ]);
                  setQuote(undefined);
                  setSelected(undefined);
                }}
              >
                {tr("Add replacement")}
              </button>
              {replacements.map((l, i) => (
                <div className="cart-math" key={l.id}>
                  <span>{l.name}</span>
                  <input
                    aria-label={`${tr("Replacement quantity")} ${l.name}`}
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={l.quantity}
                    onChange={(e) => {
                      setReplacements(
                        replacements.map((r, j) =>
                          j === i ? { ...r, quantity: e.target.value } : r,
                        ),
                      );
                      setQuote(undefined);
                    }}
                  />
                  <button
                    className="mini"
                    onClick={() => {
                      setReplacements(replacements.filter((_, j) => j !== i));
                      setQuote(undefined);
                    }}
                  >
                    {tr("Remove")}
                  </button>
                </div>
              ))}
              {replacements.length > 0 && (
                <>
                  <label className="field">
                    {tr("Manual replacement tax (%)")}
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={rate}
                      onChange={(e) => {
                        setRate(e.target.value);
                        setQuote(undefined);
                      }}
                    />
                  </label>
                  <p className="hint">
                    {tr(
                      "Configured tax rules take precedence over manual tax.",
                    )}
                  </p>
                  <label className="field">
                    {tr("Prescription reference")}
                    <input
                      value={prescription}
                      maxLength={150}
                      onChange={(e) => {
                        setPrescription(e.target.value);
                        setQuote(undefined);
                      }}
                    />
                  </label>
                </>
              )}
              <button
                className="primary"
                disabled={busy || !lines.some((l) => Number(l.returnQty) > 0)}
                onClick={preview}
              >
                {tr("Preview adjustment")}
              </button>
              {quote && (
                <section
                  className="panel"
                  style={{ padding: 20, marginTop: 20 }}
                >
                  <div className="cart-math">
                    <span>{tr("Return credit")}</span>
                    <b>{money(quote.credit)}</b>
                  </div>
                  {quote.outstanding_before > 0 && (
                    <>
                      <div className="cart-math">
                        <span>{tr("Khata debt reduction")}</span>
                        <b>{money(quote.debt_credit)}</b>
                      </div>
                      <div className="cart-math">
                        <span>{tr("Financing balance waived")}</span>
                        <b>{money(quote.debt_waiver)}</b>
                      </div>
                      <div className="cart-math">
                        <span>{tr("Remaining invoice debt")}</span>
                        <b>{money(quote.outstanding_after)}</b>
                      </div>
                      <div className="cart-math">
                        <span>{tr("Credit available for settlement")}</span>
                        <b>{money(quote.available_credit)}</b>
                      </div>
                    </>
                  )}
                  <div className="cart-math">
                    <span>{tr("Revised invoice total")}</span>
                    <b>{money(quote.revised_total)}</b>
                  </div>
                  <div className="cart-math">
                    <span>{tr("Replacement total")}</span>
                    <b>{money(quote.replacement_total)}</b>
                  </div>
                  <h3>
                    {tr(
                      quote.net > 0
                        ? "Collect from customer"
                        : quote.net < 0
                          ? "Refund to customer"
                          : "No payment difference",
                    )}
                    : {money(Math.abs(quote.net))}
                  </h3>
                  <label className="field">
                    {tr("Settlement method")}
                    <select
                      value={settlement}
                      onChange={(e) => {
                        setSettlement(e.target.value);
                        setReceived("");
                      }}
                    >
                      <option value="cash">{tr("Cash")}</option>
                      <option value="external">
                        {tr("Collected externally")}
                      </option>
                    </select>
                  </label>
                  {settlement === "cash" && quote.net > 0 && (
                    <label className="field">
                      {tr("Cash received")}
                      <input
                        type="number"
                        aria-label={tr("Cash received")}
                        min={quote.net / 100}
                        step="0.01"
                        value={received}
                        onChange={(e) => setReceived(e.target.value)}
                      />
                      <strong>
                        {tr("Change to return")}:{" "}
                        {money(
                          Math.max(
                            0,
                            Math.round(Number(received) * 100) - quote.net,
                          ),
                        )}
                      </strong>
                    </label>
                  )}
                  <label className="field">
                    {tr("Settlement reference / notes")}
                    <input
                      maxLength={500}
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                    />
                  </label>
                  <p className="hint">
                    {tr(
                      "Confirm after collecting payment or giving the refund. Cash settlement is recorded in your open till; external settlement is recorded only and does not call a payment provider.",
                    )}
                  </p>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => commit(true)}
                  >
                    {tr("Request return approval")}
                  </button>
                  {approval && (
                    <p className="hint">
                      {tr("Approval reference")}: {approval.id} ·{" "}
                      {tr(
                        "After another user approves, confirm the unchanged adjustment.",
                      )}
                    </p>
                  )}
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      (settlement === "cash" &&
                        quote.net > 0 &&
                        Math.round(Number(received) * 100) < quote.net) ||
                      (settlement === "external" &&
                        quote.net !== 0 &&
                        !reference.trim())
                    }
                    onClick={() => commit()}
                  >
                    {tr("Confirm adjustment and settlement")}
                  </button>
                </section>
              )}
            </>
          )
        )}
      </section>
    </div>
  );
}
