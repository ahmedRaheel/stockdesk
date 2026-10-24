import { useEffect, useState } from "react";
import { api } from "./api";
export type Lookup = {
  id: string;
  kind: string;
  code: string;
  name: string;
  name_ur: string;
  active: boolean;
  fractional: boolean;
};
/** Bounded server search. Labels are presentation; forms submit only lookup IDs. */
export default function LookupSelect({
  tenant,
  kind,
  label,
  name,
  value,
  onChange,
  required = true,
  language = "en",
}: {
  tenant: string;
  kind: string;
  label: string;
  name?: string;
  value?: string;
  onChange?: (id: string, item?: Lookup) => void;
  required?: boolean;
  language?: string;
}) {
  const [query, setQuery] = useState(""),
    [options, setOptions] = useState<Lookup[]>([]),
    [selected, setSelected] = useState(value || ""),
    [chosen, setChosen] = useState<Lookup | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [offset, setOffset] = useState(0),
    [more, setMore] = useState(false);
  useEffect(() => {
    setSelected(value || "");
    if (value)
      api<Lookup>(`/api/v1/tenants/${tenant}/lookups/${value}`)
        .then(setChosen)
        .catch(() => setChosen(null));
    else setChosen(null);
  }, [value, tenant]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError("");
      api<{ items: Lookup[] }>(
        `/api/v1/tenants/${tenant}/lookups?kind=${kind}&q=${encodeURIComponent(query)}&limit=50&offset=${offset}`,
        { signal: controller.signal },
      )
        .then((d) => {
          setOptions((old) => (offset ? [...old, ...d.items] : d.items));
          setMore(d.items.length === 50);
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [tenant, kind, query, offset]);
  const all =
    chosen && !options.some((x) => x.id === chosen.id)
      ? [chosen, ...options]
      : options;
  return (
    <div className="lookup-field">
      <label className="field">
        <span>{label}</span>
        <input
          aria-label={`Search ${label}`}
          type="search"
          placeholder={language === "ur" ? "تلاش کریں" : "Search options…"}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label={label}
          name={name}
          required={required}
          value={selected}
          onChange={(e) => {
            const option = all.find((x) => x.id === e.target.value);
            setSelected(e.target.value);
            setChosen(option || null);
            onChange?.(e.target.value, option);
          }}
        >
          <option value="">{loading ? "Loading…" : "Select…"}</option>
          {all.map((x) => (
            <option key={x.id} value={x.id} disabled={!x.active}>
              {language === "ur" && x.name_ur ? x.name_ur : x.name}
              {!x.active ? " (inactive)" : ""}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {more && (
        <button
          type="button"
          className="mini"
          disabled={loading}
          onClick={() => setOffset(offset + 50)}
        >
          More options
        </button>
      )}
    </div>
  );
}
