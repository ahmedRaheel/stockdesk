import { t as tr } from "./i18n";
import { useEffect, useState } from "react";
import { api } from "./api";
export default function CustomerSelect({
  tenant,
  sales = false,
  value,
  onChange,
}: {
  tenant: string;
  sales?: boolean;
  value: string;
  onChange: (id: string, customer?: any) => void;
}) {
  const [q, setQ] = useState(""),
    [items, setItems] = useState<any[]>([]),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<any>(null);
  useEffect(() => {
    setSelected(null);
    if (!value) return;
    const c = new AbortController();
    api<any>(
      `/api/v1/tenants/${tenant}/${sales ? "sale-customers" : "customers"}/${value}`,
      {
        signal: c.signal,
      },
    )
      .then(setSelected)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [tenant, value, sales]);
  useEffect(() => {
    const c = new AbortController();
    const timer = setTimeout(() => {
      api<any>(
        `/api/v1/tenants/${tenant}/${sales ? "sale-customers" : "customers"}?q=${encodeURIComponent(q)}&limit=50`,
        { signal: c.signal },
      )
        .then((d) => {
          setItems(d.items);
          setError("");
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, q, sales]);
  return (
    <div className="customer-select">
      <input
        aria-label={tr("Search customer")}
        placeholder={tr("Name, phone, Roman Urdu…")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <select
        aria-label={tr(sales ? "Registered customer" : "Khata customer")}
        value={value}
        onChange={(e) =>
          onChange(
            e.target.value,
            items.find((x) => x.id === e.target.value),
          )
        }
      >
        <option value="">{tr("Walk-in / no khata")}</option>
        {selected && !items.some((c) => c.id === selected.id) && (
          <option value={selected.id}>
            {selected.name} · {selected.phone}
          </option>
        )}
        {items.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} · {c.phone}
          </option>
        ))}
      </select>
      {error && <small role="alert">{tr(error)}</small>}
      <small>{tr("First 50 matches; search to narrow results.")}</small>
    </div>
  );
}
