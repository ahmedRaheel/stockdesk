import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";
import ReportExports from "./ReportExports";
export default function InventoryTurnover({ tenant }: { tenant: string }) {
  const [days, setDays] = useState(30),
    [page, setPage] = useState(0),
    [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setPage(0);
    setError("");
    api(`/api/v1/tenants/${tenant}/inventory-turnover?days=${days}`, {
      signal: c.signal,
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [tenant, days]);
  const columns = [
    ["sku", "SKU"],
    ["name", "Product"],
    ["unit", "Unit"],
    ["opening", "Opening stock"],
    ["closing", "Closing stock"],
    ["sold", "Sold units"],
    ["returned", "Returned units"],
    ["net_units", "Net sold units"],
    ["average_stock", "Average daily closing stock"],
    ["turnover", "Period turnover"],
    ["days_per_turn", "Days per turn"],
  ];
  return (
    <section className="panel">
      <h2>{tr("Inventory turnover")}</h2>
      <p>
        {tr(
          "Turnover is net sold units divided by average daily closing stock, per SKU. Sales and returns follow movement dates. This is period quantity turnover, not annualized or cost-based turnover.",
        )}
      </p>
      <p>
        {tr(
          "A dash means no positive stock basis or no positive sales rate. Negative turnover means returns exceeded sales. Different units are never combined.",
        )}
      </p>
      <div className="toolbar">
        <label className="field">
          {tr("Complete days")}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {[7, 30, 90].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <ReportExports
          tenant={tenant}
          name="turnover"
          filters={{ days }}
          disabled={!data}
        />
      </div>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {!data && !error && <p>{tr("Loading…")}</p>}
      {data && (
        <>
          <p>
            {data.start} → {data.end} · {data.timezone}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map(([k, l]) => (
                    <th key={k}>{tr(l)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items
                  .slice(page * 100, (page + 1) * 100)
                  .map((r: any) => (
                    <tr key={r.id}>
                      {columns.map(([k]) => (
                        <td key={k}>{r[k] ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
              </tbody>
            </table>
            {!data.items.length && <p>{tr("No matching records.")}</p>}
          </div>
          <div className="toolbar">
            <button
              className="secondary"
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              {tr("Previous")}
            </button>
            <span>
              {data.items.length ? page * 100 + 1 : 0}–
              {Math.min((page + 1) * 100, data.items.length)} /{" "}
              {data.items.length}
            </span>
            <button
              className="secondary"
              disabled={(page + 1) * 100 >= data.items.length}
              onClick={() => setPage(page + 1)}
            >
              {tr("Next")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
