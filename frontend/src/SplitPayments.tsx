import LookupSelect from "./LookupSelect";
import { t as tr } from "./i18n";
export type PaymentRow = {
  key: string;
  method_id: string;
  amount: string;
  reference: string;
  is_cash: boolean;
};
export default function SplitPayments({
  tenant,
  rows,
  onChange,
  busy,
}: {
  tenant: string;
  rows: PaymentRow[];
  onChange: (r: PaymentRow[]) => void;
  busy: boolean;
}) {
  const change = (key: string, patch: Partial<PaymentRow>) =>
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  return (
    <fieldset disabled={busy}>
      <legend>{tr("Split payment")}</legend>
      {rows.map((row, i) => (
        <div className="split-payment" key={row.key}>
          <LookupSelect
            tenant={tenant}
            kind="payment_method"
            label={tr("Payment method")}
            value={row.method_id}
            onChange={(id, p) =>
              change(row.key, { method_id: id, is_cash: p?.code === "cash" })
            }
          />
          <label className="field">
            <span>{tr("Amount")}</span>
            <input
              aria-label={tr("Amount") + " " + (i + 1)}
              type="number"
              min="0.01"
              step="0.01"
              value={row.amount}
              onChange={(e) => change(row.key, { amount: e.target.value })}
            />
          </label>
          <label className="field">
            <span>{tr("Reference")}</span>
            <input
              maxLength={150}
              value={row.reference}
              onChange={(e) => change(row.key, { reference: e.target.value })}
            />
          </label>
          <button
            type="button"
            className="mini"
            onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
          >
            {tr("Remove")}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="secondary"
        disabled={rows.length >= 10}
        onClick={() =>
          onChange([
            ...rows,
            {
              key: crypto.randomUUID(),
              method_id: "",
              amount: "",
              reference: "",
              is_cash: false,
            },
          ])
        }
      >
        {tr("Add payment")}
      </button>
      <p>
        {tr(
          "Only record payments already collected. Gateways are not charged.",
        )}
      </p>
    </fieldset>
  );
}
