import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";

type Column = [string, string, "money"?];
export default function OperationalReports({
  tenant,
  currency,
}: {
  tenant: string;
  currency: string;
}) {
  const [view, setView] = useState("tax");
  const [filters, setFilters] = useState({
    days: 30,
    minimum_baskets: 2,
    horizon_days: 30,
    demand_pct: 0,
    price_pct: 0,
    cost_pct: 0,
  });
  const [query, setQuery] = useState(filters);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const money = (n: number) =>
    new Intl.NumberFormat("en-PK", { style: "currency", currency }).format(
      n / 100,
    );
  useEffect(() => {
    const abort = new AbortController();
    setData(null);
    setError("");
    setLoading(true);
    const params = new URLSearchParams(
      Object.entries(query).map(([k, v]) => [k, String(v)]),
    );
    api(`/api/v1/tenants/${tenant}/operational-report?${params}`, {
      signal: abort.signal,
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [tenant, query]);
  function download(rows: any[], columns: Column[], filename: string) {
    const cell = (x: unknown) =>
      '"' +
      String(x ?? "")
        .replace(/^[\s]*[=+@-]/, "'$&")
        .replaceAll('"', '""') +
      '"';
    const content = [
      columns.map((c) => c[1] + (c[2] ? " (minor units)" : "")),
      ...rows.map((row) => columns.map((c) => row[c[0]])),
    ];
    const url = URL.createObjectURL(
      new Blob(
        ["\uFEFF" + content.map((r) => r.map(cell).join(",")).join("\r\n")],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = filename + ".csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  function table(rows: any[], cols: Column[], name: string) {
    return (
      <>
        <button
          className="secondary"
          onClick={() => download(rows, cols, name)}
        >
          {tr("Export CSV")}
        </button>
        {!rows.length ? (
          <p>{tr("No matching records.")}</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {cols.map((c) => (
                    <th key={c[0]}>{tr(c[1])}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    {cols.map((c) => (
                      <td key={c[0]}>
                        {c[2]
                          ? money(r[c[0]])
                          : typeof r[c[0]] === "boolean"
                            ? tr(r[c[0]] ? "Yes" : "No")
                            : tr(String(r[c[0]] ?? "—"))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }
  return (
    <section className="panel">
      <h2>{tr("Operational reports")}</h2>
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery({ ...filters });
        }}
      >
        <label className="field">
          {tr("Report")}
          <select
            aria-label={tr("Report")}
            value={view}
            onChange={(e) => setView(e.target.value)}
          >
            <option value="tax">{tr("Tax register")}</option>
            <option value="stock">{tr("Stock age and valuation")}</option>
            <option value="baskets">{tr("Basket analysis")}</option>
            <option value="scenario">{tr("What-if simulation")}</option>
          </select>
        </label>
        <label className="field">
          {tr("Complete days")}
          <select
            aria-label={tr("Complete days")}
            value={filters.days}
            onChange={(e) =>
              setFilters({ ...filters, days: Number(e.target.value) })
            }
          >
            {[7, 30, 90].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        {view === "baskets" && (
          <label className="field">
            {tr("Minimum shared baskets")}
            <input
              required
              type="number"
              min={2}
              max={10000}
              aria-label={tr("Minimum shared baskets")}
              value={filters.minimum_baskets}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  minimum_baskets: Number(e.target.value),
                })
              }
            />
          </label>
        )}
        {view === "scenario" &&
          (
            [
              ["horizon_days", "Projection days", 1, 365],
              ["demand_pct", "Demand change (%)", -100, 500],
              ["price_pct", "Price change (%)", -100, 500],
              ["cost_pct", "Unit cost change (%)", -100, 500],
            ] as const
          ).map(([key, label, min, max]) => (
            <label className="field" key={key}>
              {tr(label)}
              <input
                required
                type="number"
                min={min}
                max={max}
                step={1}
                aria-label={tr(label)}
                value={filters[key]}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: Number(e.target.value) })
                }
              />
            </label>
          ))}
        <button className="primary" disabled={loading}>
          {tr("Apply filters")}
        </button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {loading && <p role="status">{tr("Loading…")}</p>}
      {data && (
        <>
          <p>
            {data.start} → {data.end} · {data.timezone}
          </p>
          {view === "tax" && (
            <>
              <h3>{tr("Tax register")}</h3>
              <p>
                {tr(
                  "Frozen invoice taxes for completed sales. Returned invoices are excluded even when returned later. This is not a statutory filing or return-period ledger.",
                )}
              </p>
              <p>
                {tr("Tax")}: {money(data.tax.summary.tax)} · {tr("Net sales")}:{" "}
                {money(data.tax.summary.taxable)}
              </p>
              {table(
                data.tax.groups,
                [
                  ["profile", "Tax profile"],
                  ["rate_bps", "Rate (basis points)"],
                  ["inclusive", "Inclusive"],
                  ["taxable", "Net sales", "money"],
                  ["tax", "Tax", "money"],
                ],
                "tax-summary",
              )}
              <h3>{tr("Invoices")}</h3>
              {table(
                data.tax.invoices,
                [
                  ["invoice", "Invoice"],
                  ["day", "Date"],
                  ["taxable", "Net sales", "money"],
                  ["tax_included", "Tax included in prices", "money"],
                  ["tax_added", "Tax added", "money"],
                  ["total", "Total", "money"],
                ],
                "tax-invoices",
              )}
            </>
          )}
          {view === "stock" && (
            <>
              <h3>{tr("Stock age and valuation")}</h3>
              <p>
                {tr(
                  "Current stock valued at current catalog cost. Age starts at the first creation of a batch, including replenished batches. This is not FIFO/LIFO or receipt-layer accounting. Different units are not added together.",
                )}
              </p>
              <p>
                {tr("As of")}: {data.stock.as_of} · {tr("Current cost value")}:{" "}
                {money(data.stock.summary.current_cost_value)} ·{" "}
                {tr("Expired value")}: {money(data.stock.summary.expired_value)}{" "}
                · {tr("Near-expiry value")}:{" "}
                {money(data.stock.summary.near_expiry_value)}
              </p>
              {table(
                data.stock.batches,
                [
                  ["sku", "SKU"],
                  ["name", "Product"],
                  ["lot", "Batch"],
                  ["units", "Quantity"],
                  ["unit", "Unit"],
                  ["age_days", "Age (days)"],
                  ["age_band", "Age band"],
                  ["expires", "Expiry"],
                  ["status", "Status"],
                  ["current_cost_value", "Current cost value", "money"],
                ],
                "stock-age",
              )}
            </>
          )}
          {view === "baskets" && (
            <>
              <h3>{tr("Basket analysis")}</h3>
              <p>
                {tr(
                  "Co-purchases in completed invoices, excluding returns. Support is the share of invoices containing both products; confidence is the share of A baskets also containing B; lift compares this with B frequency. Association does not prove a promotion will work.",
                )}
              </p>
              <p>
                {tr("Invoices")}: {data.baskets.invoices} ·{" "}
                {tr("Qualifying pairs")}: {data.baskets.qualifying_pairs} ·{" "}
                {tr("Showing up to 200 pairs")}
              </p>
              {table(
                data.baskets.pairs,
                [
                  ["sku_a", "SKU A"],
                  ["product_a", "Product A"],
                  ["sku_b", "SKU B"],
                  ["product_b", "Product B"],
                  ["baskets", "Shared baskets"],
                  ["support_pct", "Support (%)"],
                  ["confidence_a_b_pct", "Confidence A → B (%)"],
                  ["confidence_b_a_pct", "Confidence B → A (%)"],
                  ["lift", "Lift"],
                ],
                "basket-analysis",
              )}
            </>
          )}
          {view === "scenario" && (
            <>
              <h3>{tr("What-if simulation")}</h3>
              <p>
                {tr(
                  "Sensitivity estimate from average daily net sales and frozen sale costs. Demand, price and unit-cost changes are independent assumptions. Excludes tax, overhead, stock constraints and price elasticity; no prices or orders are changed.",
                )}
              </p>
              <p>
                {tr("Projection days")}: {data.scenario.horizon_days} ·{" "}
                {tr("Demand change (%)")}: {query.demand_pct} ·{" "}
                {tr("Price change (%)")}: {query.price_pct} ·{" "}
                {tr("Unit cost change (%)")}: {query.cost_pct}
              </p>
              {table(
                [data.scenario],
                [
                  ["baseline_net_sales", "Baseline net sales", "money"],
                  ["baseline_profit", "Baseline gross profit", "money"],
                  ["net_sales", "Projected net sales", "money"],
                  ["cost", "Projected cost", "money"],
                  ["profit", "Projected gross profit", "money"],
                  ["profit_change", "Profit change", "money"],
                  ["margin_pct", "Margin (%)"],
                ],
                "what-if",
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
