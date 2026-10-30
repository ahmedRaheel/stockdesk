import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { downloadCsv } from "./csv";
import { t as tr } from "./i18n";
import "./memberships.css";
const fields: Record<string, [string, string][]> = {
  products: [
    ["sku", "SKU"],
    ["name", "Product"],
    ["units", "Units"],
    ["net_sales", "Net sales"],
    ["cost", "Cost"],
    ["profit", "Gross profit"],
    ["margin_pct", "Margin (%)"],
    ["abc", "ABC"],
    ["xyz", "XYZ"],
    ["cv", "CV"],
    ["observed_days", "Observed days"],
  ],
  categories: [
    ["category", "Category"],
    ["net_sales", "Net sales"],
    ["cost", "Cost"],
    ["profit", "Gross profit"],
    ["units", "Units (mixed units)"],
  ],
  cashiers: [
    ["cashier", "Cashier"],
    ["invoices", "Invoices"],
    ["net_sales", "Net sales"],
    ["cost", "Cost"],
    ["profit", "Gross profit"],
  ],
  hours: [
    ["hour", "Hour"],
    ["invoices", "Invoices"],
    ["net_sales", "Net sales"],
  ],
};
type Definition = {
  group: string;
  columns: string[];
  days: number;
  end: string | null;
  search: string;
  hide_zero: boolean;
  sort: string;
  descending: boolean;
  limit: number;
};
type View = {
  id: string;
  name: string;
  definition: Definition;
  version: number;
};
type Result = {
  columns: { key: string; label: string; kind: string }[];
  rows: Record<string, string | number | null>[];
  matching_rows: number;
  returned_rows: number;
  truncated: boolean;
  start: string;
  end: string;
  timezone: string;
  currency: string;
};
const initial: Definition = {
  group: "products",
  columns: ["sku", "name", "units", "net_sales", "profit"],
  days: 30,
  end: null,
  search: "",
  hide_zero: false,
  sort: "net_sales",
  descending: true,
  limit: 100,
};
export default function ReportBuilder({ tenant }: { tenant: string }) {
  const url = `/api/v1/tenants/${tenant}/report-builder`;
  const [definition, setDefinition] = useState<Definition>(initial),
    [name, setName] = useState(""),
    [saved, setSaved] = useState<View | null>(null),
    [views, setViews] = useState<View[]>([]),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [data, setData] = useState<Result | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const newId = useRef(newRequestId()),
    runAbort = useRef<AbortController | null>(null);
  useEffect(() => () => runAbort.current?.abort(), []);
  useEffect(() => {
    const c = new AbortController();
    api<{ items: View[] }>(`${url}/views?offset=${page * 30}`, {
      signal: c.signal,
    })
      .then((r) => {
        if (!c.signal.aborted) setViews(r.items);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [tenant, page, revision]);
  function change(patch: Partial<Definition>) {
    setDefinition((d) => ({ ...d, ...patch }));
    setData(null);
    setNotice("");
  }
  async function run() {
    setBusy(true);
    setError("");
    setData(null);
    runAbort.current?.abort();
    const c = new AbortController();
    runAbort.current = c;
    try {
      const result = await api<Result>(url + "/run", {
        method: "POST",
        body: JSON.stringify(definition),
        signal: c.signal,
      });
      if (!c.signal.aborted) setData(result);
    } catch (e) {
      if (!c.signal.aborted) setError((e as Error).message);
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const r = await send<{ id: string; version: number }>(
        url + "/views",
        {
          id: saved?.id || newId.current,
          name,
          definition,
          version: saved?.version || 0,
        },
        "PUT",
      );
      setSaved({ id: r.id, name, definition, version: r.version });
      setNotice("Report view saved.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!saved) return;
    setBusy(true);
    setError("");
    try {
      await api(`${url}/views/${saved.id}?version=${saved.version}`, {
        method: "DELETE",
      });
      setSaved(null);
      setName("");
      newId.current = newRequestId();
      setNotice("Report view deleted.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function exportCsv() {
    if (!data) return;
    downloadCsv("custom-report.csv", [
      [tr("Period"), data.start, data.end, data.timezone],
      [tr("Currency"), data.currency],
      data.columns.map(
        (c) => tr(c.label) + (c.kind === "money" ? ` (${data.currency})` : ""),
      ),
      ...data.rows.map((row) =>
        data.columns.map((c) =>
          c.kind === "money" && typeof row[c.key] === "number"
            ? Number(row[c.key]) / 100
            : c.key === "xyz" && typeof row[c.key] === "string"
              ? tr(String(row[c.key]))
              : row[c.key],
        ),
      ),
    ]);
  }
  const format = (v: string | number | null, kind: string, key: string) =>
    v === null
      ? "—"
      : kind === "money" && data
        ? new Intl.NumberFormat("en-PK", {
            style: "currency",
            currency: data.currency,
          }).format(Number(v) / 100)
        : key === "xyz"
          ? tr(String(v))
          : String(v);
  return (
    <section className="panel report-builder">
      <div className="membership-heading">
        <div>
          <h2>{tr("Custom report builder")}</h2>
          <p>
            {tr(
              "Choose a grouping, period, columns and filters. Save the view for your team.",
            )}
          </p>
        </div>
      </div>
      <p className="hint">
        {tr(
          "Completed invoices only. Later returns revise historical results. Costs are frozen sale-line costs, not FIFO or statutory financial statements.",
        )}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      <fieldset disabled={busy} className="report-controls">
        <div className="toolbar">
          <label className="field">
            <span>{tr("Saved report views")}</span>
            <select
              aria-label={tr("Saved report views")}
              value={saved?.id || ""}
              onChange={(e) => {
                const v = views.find((v) => v.id === e.target.value);
                setSaved(v || null);
                setDefinition(v?.definition || initial);
                setName(v?.name || "");
                setData(null);
                setError("");
                setNotice("");
                newId.current = newRequestId();
              }}
            >
              <option value="">{tr("New report view")}</option>
              {saved && !views.some((v) => v.id === saved.id) && (
                <option value={saved.id}>{saved.name}</option>
              )}
              {views.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            disabled={!page}
            onClick={() => setPage((p) => p - 1)}
          >
            {tr("Previous views")}
          </button>
          <button
            className="secondary"
            disabled={views.length < 30}
            onClick={() => setPage((p) => p + 1)}
          >
            {tr("Next views")}
          </button>
          <button
            className="secondary"
            onClick={() => setRevision((n) => n + 1)}
          >
            {tr("Reload views")}
          </button>
        </div>
        <div className="toolbar">
          <label className="field">
            <span>{tr("Group report by")}</span>
            <select
              aria-label={tr("Group report by")}
              value={definition.group}
              onChange={(e) =>
                change({
                  group: e.target.value,
                  columns: fields[e.target.value].map((f) => f[0]),
                  sort: "net_sales",
                })
              }
            >
              {Object.entries({
                products: "Product",
                categories: "Category",
                cashiers: "Cashier",
                hours: "Hour",
              }).map(([k, v]) => (
                <option key={k} value={k}>
                  {tr(v)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{tr("Complete days")}</span>
            <input
              aria-label={tr("Complete days")}
              type="number"
              min={1}
              max={90}
              value={definition.days}
              onChange={(e) => change({ days: Number(e.target.value) })}
            />
          </label>
          <label className="field">
            <span>{tr("Period ends")}</span>
            <input
              aria-label={tr("Period ends")}
              type="date"
              min="2000-01-01"
              value={definition.end || ""}
              onChange={(e) => change({ end: e.target.value || null })}
            />
            <small>
              {tr(
                "Blank means yesterday in Karachi; saved relative views move with the date.",
              )}
            </small>
          </label>
          <label className="field">
            <span>{tr("Filter group labels")}</span>
            <input
              value={definition.search}
              maxLength={100}
              onChange={(e) => change({ search: e.target.value })}
            />
          </label>
          <label className="field">
            <span>{tr("Sort by")}</span>
            <select
              aria-label={tr("Sort by")}
              value={definition.sort}
              onChange={(e) => change({ sort: e.target.value })}
            >
              {fields[definition.group].map(([k, v]) => (
                <option key={k} value={k}>
                  {tr(v)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{tr("Maximum rows")}</span>
            <input
              type="number"
              min={1}
              max={5000}
              value={definition.limit}
              onChange={(e) => change({ limit: Number(e.target.value) })}
            />
          </label>
        </div>
        <div className="actions">
          <label>
            <input
              type="checkbox"
              checked={definition.descending}
              onChange={(e) => change({ descending: e.target.checked })}
            />
            {tr("Descending order")}
          </label>
          <label>
            <input
              type="checkbox"
              checked={definition.hide_zero}
              onChange={(e) => change({ hide_zero: e.target.checked })}
            />
            {tr("Hide zero net sales")}
          </label>
        </div>
        <fieldset className="report-columns">
          <legend>{tr("Report columns")}</legend>
          {fields[definition.group].map(([k, v]) => (
            <label key={k}>
              <input
                type="checkbox"
                checked={definition.columns.includes(k)}
                onChange={(e) =>
                  change({
                    columns: e.target.checked
                      ? [...definition.columns, k]
                      : definition.columns.filter((c) => c !== k),
                  })
                }
              />
              {tr(v)}
            </label>
          ))}
        </fieldset>
        <div className="toolbar">
          <button
            className="primary"
            disabled={!definition.columns.length}
            onClick={run}
          >
            {tr("Run report")}
          </button>
          <label className="field">
            <span>{tr("Report view name")}</span>
            <input
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            className="secondary"
            disabled={!name.trim() || !definition.columns.length}
            onClick={save}
          >
            {tr(saved ? "Update saved view" : "Save new view")}
          </button>
          {saved && (
            <button className="secondary" onClick={remove}>
              {tr("Delete saved view")}
            </button>
          )}
        </div>
      </fieldset>
      {busy && <p role="status">{tr("Loading…")}</p>}
      {data && (
        <>
          <div className="membership-heading">
            <p>
              <span dir="ltr">
                {data.start} — {data.end}
              </span>{" "}
              · {data.timezone} · {tr("Matching rows")}: {data.matching_rows} ·{" "}
              {tr("Displayed rows")}: {data.returned_rows}
            </p>
            <button className="secondary" onClick={exportCsv}>
              {tr("Export CSV")}
            </button>
          </div>
          {data.truncated && (
            <p className="hint">
              {tr(
                "The row limit was reached. Narrow filters or increase the limit; the CSV contains displayed rows only.",
              )}
            </p>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th key={c.key}>{tr(c.label)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i}>
                    {data.columns.map((c) => (
                      <td key={c.key}>{format(r[c.key], c.kind, c.key)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.rows.length && <p>{tr("No matching report rows.")}</p>}
          </div>
        </>
      )}
    </section>
  );
}
