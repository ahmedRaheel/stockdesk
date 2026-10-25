import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";
export type PurchaseOption = {
  id: string;
  name: string;
  sku?: string;
  active?: boolean;
};
/** Bounded database search. Retain a selected option when the search changes. */
export default function PurchaseLookup({
  tenant,
  kind,
  value,
  selected,
  onChange,
  required = true,
}: {
  tenant: string;
  kind: "suppliers" | "products";
  value: string;
  selected?: PurchaseOption;
  onChange: (value: PurchaseOption | undefined) => void;
  required?: boolean;
}) {
  const [q, setQ] = useState(""),
    [items, setItems] = useState<PurchaseOption[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const label = kind === "suppliers" ? tr("Supplier") : tr("Product");
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      api<{ items: PurchaseOption[] }>(
        `/api/v1/tenants/${tenant}/${kind}?q=${encodeURIComponent(q)}&limit=50`,
        { signal: c.signal },
      )
        .then((r) => {
          setItems(r.items.filter((x) => x.active !== false));
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
  }, [tenant, kind, q]);
  return (
    <div className="field">
      <span>{label}</span>
      <input
        aria-label={`${tr("Search")} ${label}`}
        placeholder={tr("Search by name or SKU")}
        value={q}
        maxLength={100}
        onChange={(e) => setQ(e.target.value)}
      />
      <select
        aria-label={label}
        required={required}
        value={value}
        onChange={(e) =>
          onChange(
            items.find((x) => x.id === e.target.value) ||
              (selected?.id === e.target.value ? selected : undefined),
          )
        }
      >
        <option value="">{tr("Select")}</option>
        {selected && !items.some((x) => x.id === selected.id) && (
          <option value={selected.id}>{selected.name}</option>
        )}
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.sku ? `${x.sku} · ` : ""}
            {x.name}
          </option>
        ))}
      </select>
      <small>
        {tr(
          loading ? "Loading…" : "First 50 matches; search to narrow results.",
        )}
      </small>
      {error && <small role="alert">{tr(error)}</small>}
    </div>
  );
}
