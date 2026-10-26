import { useEffect, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
export default function TransactionApprovals({
  tenant,
  owner,
  discountApprover,
  voidApprover,
  email,
  money,
}: {
  tenant: string;
  owner: boolean;
  discountApprover: boolean;
  voidApprover: boolean;
  email: string;
  money: (n: number) => string;
}) {
  const base = `/api/v1/tenants/${tenant}/transaction-approvals`;
  const [items, setItems] = useState<any[]>([]),
    [policy, setPolicy] = useState<any>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [offset, setOffset] = useState(0),
    [notes, setNotes] = useState<Record<string, string>>({});
  async function load() {
    try {
      const [queue, p] = await Promise.all([
        api<any>(`${base}?offset=${offset}`),
        api<any>(base + "/policy"),
      ]);
      setItems(queue.items);
      setPolicy(p);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [tenant, offset]);
  async function decision(id: string, decision: string) {
    setBusy(true);
    setError("");
    try {
      await send(`${base}/${id}/decision`, { decision, note: notes[id] || "" });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setPolicy(await send(base + "/policy", policy, "PUT"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      <p>
        {tr(
          "Approvals require a different authorized user, expire after 30 minutes, and apply once to the exact transaction. Changes require a new approval.",
        )}
      </p>
      <button className="secondary" disabled={busy} onClick={load}>
        {tr("Refresh")}
      </button>
      {owner && policy && (
        <form className="panel" onSubmit={save}>
          <fieldset disabled={busy}>
            <h2>{tr("Transaction approval policy")}</h2>
            <label>
              <input
                type="checkbox"
                checked={policy.discount_required}
                onChange={(e) =>
                  setPolicy({ ...policy, discount_required: e.target.checked })
                }
              />
              {tr("Require independent manual discount approval")}
            </label>
            <label>
              <input
                type="checkbox"
                checked={policy.void_required}
                onChange={(e) =>
                  setPolicy({ ...policy, void_required: e.target.checked })
                }
              />
              {tr("Require independent return and exchange approval")}
            </label>
            <p className="hint">
              {tr(
                "Assign a second approver before enabling. Owners cannot approve their own requests. Configured promotions do not need manual discount approval.",
              )}
            </p>
            <button className="primary">{tr("Save policy")}</button>
          </fieldset>
        </form>
      )}
      {items.map((row) => {
        const s = row.summary;
        const expired = new Date(row.expires).getTime() <= Date.now();
        const allowed =
          row.kind === "discount" ? discountApprover : voidApprover;
        return (
          <section
            className="panel"
            key={row.id}
            style={{ padding: 20, marginTop: 16 }}
          >
            <h3>
              {tr(
                row.kind === "discount"
                  ? "Manual discount approval"
                  : "Return approval",
              )}{" "}
              · {s.invoice || row.requester_email}
            </h3>
            <p>
              {row.requester_email} · {tr(row.status)} · {tr("Expires")}:{" "}
              {new Date(row.expires).toLocaleString()}
              {expired ? ` · ${tr("Expired")}` : ""}
            </p>
            <p>
              {tr("Approval reference")}: <code>{row.id}</code>
            </p>
            {s.total !== undefined && (
              <p>
                {tr("Total")}: {money(s.total)}
              </p>
            )}
            {s.discount !== undefined && (
              <p>
                {tr("Discount")}: {money(s.discount)}
              </p>
            )}
            {s.customer && (
              <p>
                {tr("Customer")}: {s.customer}
              </p>
            )}
            {(s.items || s.returns || []).map((line: any, i: number) => (
              <p key={i}>
                {line.name} · {line.sku} × {line.quantity}{" "}
                {line.reason
                  ? `· ${tr(({ expired: "Expired item", damaged: "Damaged item", incorrect: "Incorrect item", opened: "Opened item" } as Record<string, string>)[line.reason] || line.reason)}`
                  : ""}
                {line.restock ? ` · ${tr("Restock")}` : ""}
              </p>
            ))}
            {s.credit !== undefined && (
              <p>
                {tr("Return credit")}: {money(s.credit)} ·{" "}
                {tr("Khata debt reduction")}: {money(s.debt_credit || 0)} ·{" "}
                {tr("Financing balance waived")}: {money(s.debt_waiver || 0)} ·{" "}
                {tr("Replacement total")}: {money(s.replacement_total)} ·{" "}
                {tr(
                  s.net > 0
                    ? "Collect from customer"
                    : s.net < 0
                      ? "Refund to customer"
                      : "No payment difference",
                )}
                : {money(Math.abs(s.net))}
              </p>
            )}
            {s.reason && <p>{s.reason}</p>}
            {row.note && (
              <p>
                {row.decision_email} · {row.note}
              </p>
            )}
            {row.status === "pending" &&
              !expired &&
              allowed &&
              row.requester_email !== email && (
                <fieldset disabled={busy}>
                  <label className="field">
                    {tr("Decision note")}
                    <input
                      value={notes[row.id] || ""}
                      maxLength={500}
                      onChange={(e) =>
                        setNotes({ ...notes, [row.id]: e.target.value })
                      }
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={!notes[row.id]?.trim()}
                    onClick={() => decision(row.id, "approved")}
                  >
                    {tr("Approve")}
                  </button>{" "}
                  <button
                    className="secondary"
                    disabled={!notes[row.id]?.trim()}
                    onClick={() => decision(row.id, "rejected")}
                  >
                    {tr("Reject")}
                  </button>
                </fieldset>
              )}
          </section>
        );
      })}
      {!items.length && <p>{tr("No approval requests.")}</p>}
      <div className="actions">
        <button
          className="secondary"
          disabled={!offset || busy}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          {tr("Previous")}
        </button>
        <button
          className="secondary"
          disabled={items.length < 50 || busy}
          onClick={() => setOffset(offset + 50)}
        >
          {tr("Next")}
        </button>
      </div>
    </>
  );
}
