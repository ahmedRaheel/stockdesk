import { useEffect, useState } from "react";
import ScheduledReports from "./ScheduledReports";
import ReportBuilder from "./ReportBuilder";
import InventoryTurnover from "./InventoryTurnover";
import ReportExports from "./ReportExports";
import OperationalReports from "./OperationalReports";
import { downloadCsv } from "./csv";
import { api } from "./api";
import { t as tr } from "./i18n";
export default function ManagementReport({
  tenant,
  currency,
}: {
  tenant: string;
  currency: string;
}) {
  const [scheduled, setScheduled] = useState(false);
  const [builder, setBuilder] = useState(false);
  const [operational, setOperational] = useState(false);
  const [turnover, setTurnover] = useState(false);
  const [days, setDays] = useState(30),
    [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const money = (n: number) =>
    new Intl.NumberFormat("en-PK", { style: "currency", currency }).format(
      n / 100,
    );
  useEffect(() => {
    setData(null);
    setError("");
    const c = new AbortController();
    api(`/api/v1/tenants/${tenant}/management-report?days=${days}`, {
      signal: c.signal,
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [tenant, days]);
  function download() {
    const rows = [
      [
        "SKU",
        "Product",
        "Net sales (minor units)",
        "Cost (minor units)",
        "Profit (minor units)",
        "Units",
        "ABC",
        "XYZ",
        "CV",
        "Observed days",
      ].map(tr),
      ...data.products.map((p: any) => [
        p.sku,
        p.name,
        p.net_sales,
        p.cost,
        p.profit,
        p.units,
        p.abc,
        tr(p.xyz),
        p.cv ?? "",
        p.observed_days,
      ]),
    ];
    downloadCsv("management-report.csv", [
      [tr("Period"), data.start, data.end, data.timezone],
      [tr("Currency"), currency],
      ...rows,
    ]);
  }

  const table = (rows: any[], columns: [string, string][]) => (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th key={key}>{tr(label)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map(([key]) => (
                <td key={key}>
                  {["net_sales", "cost", "profit"].includes(key)
                    ? money(r[key])
                    : key === "xyz"
                      ? tr(r[key] ?? "—")
                      : (r[key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  if (scheduled)
    return (
      <>
        <button className="secondary" onClick={() => setScheduled(false)}>
          {tr("Sales and margin reports")}
        </button>
        <ScheduledReports key={tenant} tenant={tenant} />
      </>
    );
  if (builder)
    return (
      <>
        <button className="secondary" onClick={() => setBuilder(false)}>
          {tr("Sales and margin reports")}
        </button>
        <ReportBuilder tenant={tenant} />
      </>
    );
  if (turnover)
    return (
      <>
        <button className="secondary" onClick={() => setTurnover(false)}>
          {tr("Sales and margin reports")}
        </button>
        <InventoryTurnover tenant={tenant} />
      </>
    );
  if (operational)
    return (
      <>
        <button className="secondary" onClick={() => setOperational(false)}>
          {tr("Sales and margin reports")}
        </button>
        <OperationalReports tenant={tenant} currency={currency} />
      </>
    );
  return (
    <>
      <button className="secondary" onClick={() => setScheduled(true)}>
        {tr("Scheduled reports")}
      </button>
      <button className="secondary" onClick={() => setBuilder(true)}>
        {tr("Custom report builder")}
      </button>
      <button className="secondary" onClick={() => setTurnover(true)}>
        {tr("Inventory turnover")}
      </button>
      <button className="secondary" onClick={() => setOperational(true)}>
        {tr("Operational reports")}
      </button>
      <div className="toolbar">
        <label className="field">
          <span>{tr("Complete days")}</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>7</option>
            <option value={30}>30</option>
            <option value={90}>90</option>
          </select>
        </label>
        <button className="secondary" disabled={!data} onClick={download}>
          {tr("Export CSV")}
        </button>
        <ReportExports
          tenant={tenant}
          name="products"
          filters={{ days }}
          disabled={!data}
        />
      </div>
      <p>
        {tr(
          "Net sales exclude tax and invoice discounts. Costs use the original sale-line cost, not FIFO valuation. Returned invoices are excluded, including later returns.",
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {!data && !error ? (
        <p>{tr("Loading…")}</p>
      ) : (
        data && (
          <>
            <p>
              {data.start} → {data.end} · {data.timezone}
            </p>
            <div className="kpis">
              {[
                ["net_sales", "Net sales"],
                ["cost", "Cost"],
                ["profit", "Gross profit"],
                ["tax", "Tax"],
              ].map(([key, label]) => (
                <div className="kpi" key={key}>
                  <span>{tr(label)}</span>
                  <strong>{money(data.summary[key])}</strong>
                </div>
              ))}
            </div>
            <section className="panel">
              <h2>{tr("ABC / XYZ analysis")}</h2>
              <p>
                {tr(
                  "ABC groups cumulative net sales at 80% and 95%. XYZ uses daily unit-sales variation: X ≤ 0.5, Y ≤ 1, otherwise Z. At least 14 complete days are required. These are descriptive classifications, not forecasts.",
                )}
              </p>
              {table(data.products, [
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
              ])}
            </section>
            <section className="panel">
              <h2>{tr("By category")}</h2>
              <ReportExports
                tenant={tenant}
                name="categories"
                filters={{ days }}
              />
              {table(data.categories, [
                ["category", "Category"],
                ["net_sales", "Net sales"],
                ["cost", "Cost"],
                ["profit", "Gross profit"],
              ])}
            </section>
            <section className="panel">
              <h2>{tr("By cashier")}</h2>
              <ReportExports
                tenant={tenant}
                name="cashiers"
                filters={{ days }}
              />
              {table(data.cashiers, [
                ["cashier", "Cashier"],
                ["invoices", "Invoices"],
                ["net_sales", "Net sales"],
                ["profit", "Gross profit"],
              ])}
            </section>
            <section className="panel">
              <h2>{tr("By hour")}</h2>
              <ReportExports tenant={tenant} name="hours" filters={{ days }} />
              {table(data.hours, [
                ["hour", "Hour"],
                ["invoices", "Invoices"],
                ["net_sales", "Net sales"],
              ])}
            </section>
          </>
        )
      )}
    </>
  );
}
