import { downloadCsv } from "./csv";
import { t as tr } from "./i18n";
import { useEffect, useState } from "react";
import {
  TrendingUp,
  AlertTriangle,
  Package,
  Download,
  RefreshCw,
  Search,
  Info,
  ArrowUpRight,
} from "lucide-react";
import PlotlyChart from "./PlotlyChart";
export default function Forecasts({
  tenant,
  currency,
  onRestock,
}: {
  tenant: string;
  currency: string;
  onRestock: (p: any) => void;
}) {
  const [data, setData] = useState<any>(null),
    [period, setPeriod] = useState("last7"),
    [lead, setLead] = useState(7),
    [cover, setCover] = useState(30),
    [eventPct, setEventPct] = useState(0),
    [eventStart, setEventStart] = useState(1),
    [eventDays, setEventDays] = useState(7),
    [safety, setSafety] = useState(20),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [query, setQuery] = useState(""),
    [risk, setRisk] = useState(""),
    [tab, setTab] = useState("forecast"),
    [revision, setRevision] = useState(0);
  const money = (n: number) =>
    new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format((n || 0) / 100);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setData(null);
    setError("");
    fetch(
      `/api/forecasts?tenant=${encodeURIComponent(tenant)}&period=${period}&lead=${lead}&cover=${cover}&safety=${safety}&event_pct=${eventPct}&event_start=${eventStart}&event_days=${eventDays}`,
      { signal: controller.signal },
    )
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.error || "Forecast request failed");
        return d;
      })
      .then((d) => setData(d))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    tenant,
    period,
    lead,
    cover,
    safety,
    eventPct,
    eventStart,
    eventDays,
    revision,
  ]);
  const filtered = (data?.forecasts || []).filter(
    (f: any) =>
      (!risk || f.risk === risk) &&
      (f.name + " " + f.sku).toLowerCase().includes(query.toLowerCase()),
  );
  function exportCsv() {
    const rows = [
      [
        "SKU",
        "Product",
        "Stock",
        "Next 7 days",
        "Next 30 days",
        "Days of cover",
        "Estimated stockout",
        "Suggested reorder",
        "Evidence",
        "Backtest WAPE %",
        "Baseline next 30 days",
        "Test MAE (units/day)",
        "Test bias (%)",
      ].map(tr),
      ...filtered.map((f: any) => [
        f.sku,
        f.name,
        f.stock,
        f.next7 ?? "",
        f.next30 ?? "",
        f.days_cover ?? "",
        f.stockout_date || "",
        f.reorder_qty ?? "",
        tr(f.quality),
        f.wape ?? "",
        f.baseline_next30 ?? "",
        f.evaluation.mae ?? "",
        f.evaluation.bias_pct ?? "",
      ]),
    ];
    downloadCsv("stockdesk-forecasts.csv", [
      [
        tr("Demand event adjustment (%)"),
        eventPct,
        tr("Event starts on forecast day"),
        eventStart,
        tr("Event duration (days)"),
        eventDays,
      ],
      ...rows,
    ]);
  }

  const ranking = (title: string, list: any[], mode = "units") => (
    <section className="panel">
      <div className="panel-heading">
        <h2>{tr(title)}</h2>
        <span className="subtle-tag">
          {mode === "growth"
            ? tr("Last 7 vs previous 7")
            : tr("Selected period")}
        </span>
      </div>
      {list.length ? (
        <div className="rank-list">
          {list.map((p: any, i: number) => (
            <div key={p.id}>
              <span className="rank-number">{i + 1}</span>
              <div>
                <b>{p.name}</b>
                <small>
                  {p.sku}
                  {!p.active ? tr(" · Archived") : ""}
                </small>
              </div>
              <strong>
                {mode === "growth"
                  ? `${p.growth_pct === null ? tr("New demand") : p.growth_pct + "%"} (${p.last7 - p.previous7 > 0 ? "+" : ""}${p.last7 - p.previous7} ${tr("units")})`
                  : `${p.units} ${tr("units")}`}
                <small>
                  {money(p.gross)} {tr("gross")}
                </small>
              </strong>
            </div>
          ))}
        </div>
      ) : (
        <p className="hint">{tr("No matching products in this period.")}</p>
      )}
    </section>
  );
  return (
    <div className="forecasts">
      <div className="panel forecast-controls">
        <div className="toolbar">
          <label>
            {" "}
            {tr("Sales period")}{" "}
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="today">{tr("Today (partial day)")}</option>
              <option value="yesterday">{tr("Yesterday")}</option>
              <option value="last7">{tr("Last 7 complete days")}</option>
              <option value="last_week">
                {tr("Last calendar week (Mon–Sun)")}
              </option>
              <option value="month">{tr("This month to date")}</option>
              <option value="last_month">{tr("Last calendar month")}</option>
              <option value="last30">{tr("Last 30 complete days")}</option>
            </select>
          </label>
          <label>
            {" "}
            {tr("Supplier lead time")}{" "}
            <select value={lead} onChange={(e) => setLead(+e.target.value)}>
              {[1, 3, 7, 14, 21, 30, 60, 90].map((n) => (
                <option key={n} value={n}>
                  {n} {tr("days")}{" "}
                </option>
              ))}
            </select>
          </label>
          <label>
            {" "}
            {tr("Target coverage")}{" "}
            <select value={cover} onChange={(e) => setCover(+e.target.value)}>
              {[7, 14, 30, 60, 90].map((n) => (
                <option key={n} value={n}>
                  {n} {tr("days")}{" "}
                </option>
              ))}
            </select>
          </label>
          <label>
            {" "}
            {tr("Safety allowance")}{" "}
            <select value={safety} onChange={(e) => setSafety(+e.target.value)}>
              {[0, 10, 20, 30, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}%
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            disabled={loading}
            onClick={() => setRevision(revision + 1)}
          >
            <RefreshCw size={15} className={loading ? "spin" : ""} />{" "}
            {tr("Refresh")}{" "}
          </button>
        </div>
        <p className="hint">
          {" "}
          {tr(
            "Period changes historical rankings. Forecasts use complete-day history independently. All dates use UTC. Settings are planning assumptions and do not place orders.",
          )}{" "}
        </p>
      </div>
      <section className="panel forecast-event">
        <h2>{tr("Demand event scenario")}</h2>
        <p>
          {tr(
            "Plan a festival, weather or promotion assumption. This is a manual percentage adjustment, not a learned event forecast. It applies to every eligible product on the selected dates.",
          )}
        </p>
        <div className="toolbar">
          <label>
            {tr("Demand event adjustment (%)")}
            <select
              aria-label={tr("Demand event adjustment (%)")}
              value={eventPct}
              onChange={(e) => setEventPct(Number(e.target.value))}
            >
              {[-100, -50, -25, -10, 0, 10, 25, 50, 100, 200, 300].map((n) => (
                <option key={n} value={n}>
                  {n > 0 ? "+" : ""}
                  {n}%
                </option>
              ))}
            </select>
          </label>
          <label>
            {tr("Event starts on forecast day")}
            <select
              aria-label={tr("Event starts on forecast day")}
              value={eventStart}
              onChange={(e) => {
                const start = Number(e.target.value);
                setEventStart(start);
                setEventDays((d) => Math.min(d, 31 - start));
              }}
            >
              {Array.from({ length: 30 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label>
            {tr("Event duration (days)")}
            <select
              aria-label={tr("Event duration (days)")}
              value={eventDays}
              onChange={(e) => setEventDays(Number(e.target.value))}
            >
              {Array.from({ length: 31 - eventStart }, (_, i) => i + 1).map(
                (n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ),
              )}
            </select>
          </label>
          <button
            className="secondary"
            onClick={() => {
              setEventPct(0);
              setEventStart(1);
              setEventDays(7);
            }}
          >
            {tr("Reset scenario")}
          </button>
        </div>
        {data && eventPct !== 0 && (
          <p>
            {tr("Scenario dates (UTC)")}:{" "}
            <span dir="ltr">
              {data.event.first_date} — {data.event.last_date}
            </span>
          </p>
        )}
      </section>
      {error && <div className="alert error">{tr(error)}</div>}
      {loading && (
        <p className="hint" role="status">
          {" "}
          {tr("Calculating sales insights…")}{" "}
        </p>
      )}
      {data && (
        <>
          <div className="kpis">
            <div className="kpi">
              <div>
                <span>{tr("Units sold")}</span>
                <TrendingUp size={18} />
              </div>
              <strong>{data.summary.units}</strong>
              <small>
                {data.start} {tr("to")} {data.end}
              </small>
            </div>
            <div className="kpi">
              <div>
                <span>
                  {tr(
                    eventPct
                      ? "Next 30 days · scenario"
                      : "Next 30 days · forecast",
                  )}
                </span>
                <Package size={18} />
              </div>
              <strong>
                {data.summary.eligible
                  ? data.summary.forecast30 + " " + tr("units")
                  : tr("Not enough history")}
              </strong>
              <small>
                {data.summary.eligible} {tr("of")} {data.summary.active}{" "}
                {tr("active products eligible")}{" "}
              </small>
            </div>
            <div className="kpi warm">
              <div>
                <span>{tr("Stockout risk")}</span>
                <AlertTriangle size={18} />
              </div>
              <strong>{data.summary.at_risk}</strong>
              <small>{tr("May run out within supplier lead time")}</small>
            </div>
            <div className="kpi">
              <div>
                <span>{tr("Already out / slow moving")}</span>
                <Package size={18} />
              </div>
              <strong>
                {data.summary.out_of_stock} / {data.summary.slow_moving}
              </strong>
              <small>{tr("Slow moving: stocked, no sale for 30+ days")}</small>
            </div>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>{tr("Observed sales & next-month forecast")}</h2>
                <p>
                  {" "}
                  {tr(
                    "Today's observed sales are partial. History includes all products. Forecast includes only eligible active products; it begins tomorrow.",
                  )}{" "}
                </p>
              </div>
              <span className="subtle-tag">{tr("Units, not revenue")}</span>
            </div>
            <PlotlyChart
              figure={{
                ...data.chart,
                data: data.chart.data.map((trace: any) => ({
                  ...trace,
                  name: tr(trace.name),
                })),
                layout: {
                  ...data.chart.layout,
                  yaxis: {
                    ...data.chart.layout.yaxis,
                    title: {
                      ...data.chart.layout.yaxis.title,
                      text: tr("Units"),
                    },
                  },
                },
              }}
            />
          </section>
          <div className="forecast-tabs">
            {[
              ["forecast", "Demand & stockouts"],
              ["rankings", "Best & least selling"],
              ["trends", "Rising & declining"],
              ["history", "Daily & monthly"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {tr(label)}
              </button>
            ))}
          </div>
          {tab === "forecast" && (
            <section className="panel">
              <div className="panel-heading">
                <h2>{tr("Product forecasts & replenishment")}</h2>
                <button className="secondary" onClick={exportCsv}>
                  <Download size={14} /> {tr("Export CSV")}{" "}
                </button>
              </div>
              <div className="toolbar">
                <div className="search">
                  <Search size={15} />
                  <input
                    placeholder={tr("Search product or SKU…")}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <select
                  value={risk}
                  onChange={(e) => setRisk(e.target.value)}
                  aria-label={tr("Risk filter")}
                >
                  <option value="">{tr("All products")}</option>
                  {[
                    "Out of stock",
                    "At risk",
                    "Slow moving",
                    "No forecast",
                    "Covered",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {tr(s)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{tr("Product")}</th>
                      <th>{tr("Stock / risk")}</th>
                      <th>{tr("Next 7 / 30 days")}</th>
                      <th>{tr("Stock cover")}</th>
                      <th>{tr("Stockout estimate")}</th>
                      <th>{tr("Reorder")}</th>
                      <th>{tr("Evidence")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((f: any) => (
                      <tr key={f.id}>
                        <td>
                          <b>{f.name}</b>
                          <small>{f.sku}</small>
                          <small>
                            {f.days_unsold}{" "}
                            {tr("days since sale / listing")}{" "}
                          </small>
                        </td>
                        <td>
                          <b>
                            {f.stock} {tr("units")}
                          </b>
                          <small>
                            <span
                              className={
                                "badge " +
                                (["Out of stock", "At risk"].includes(f.risk)
                                  ? "red"
                                  : f.risk === "Slow moving"
                                    ? "amber"
                                    : "")
                              }
                            >
                              {tr(f.risk)}
                            </span>
                          </small>
                        </td>
                        <td>
                          {f.next7 === null
                            ? tr("Not enough history")
                            : `${f.next7} / ${f.next30} ${tr("units")}`}
                          <small>
                            {f.range30
                              ? `${tr("30-day variation")}: ${f.range30[0]}–${f.range30[1]}`
                              : f.next30 !== null
                                ? tr(
                                    "Variation range omitted for event scenarios.",
                                  )
                                : tr(
                                    "At least 14 complete days and 3 selling days required",
                                  )}
                          </small>
                          <small>
                            {f.sales_value30 !== null
                              ? money(f.sales_value30) +
                                " " +
                                tr("at current prices")
                              : ""}
                          </small>
                        </td>
                        <td>
                          {f.days_cover === null
                            ? tr("Not estimable")
                            : f.days_cover + " " + tr("days")}
                          <small>
                            {f.overstock_units > 0
                              ? `${f.overstock_units} ${tr("units above 90-day cover")}`
                              : ""}
                          </small>
                        </td>
                        <td>
                          {f.stockout_date ||
                            (f.next30 !== null
                              ? tr("Not within 30-day forecast")
                              : tr("Not estimable"))}
                        </td>
                        <td>
                          {f.reorder_qty === null
                            ? tr("Review manually")
                            : f.reorder_qty + " " + tr("units")}
                        </td>
                        <td>
                          <span className="badge">{tr(f.quality)}</span>
                          <small>
                            {f.history_days} {tr("observed days ·")}{" "}
                            {f.selling_days} {tr("selling days")}{" "}
                          </small>
                          <small>
                            {f.wape === null
                              ? tr("Backtest unavailable")
                              : `${tr("Independent 7-day WAPE")}: ${f.wape}%`}
                          </small>
                          <small>{tr(f.model || "")}</small>
                          {f.evaluation.test_days > 0 && (
                            <small>
                              {tr("Test MAE (units/day)")}: {f.evaluation.mae} ·{" "}
                              {tr("Test bias (%)")}:{" "}
                              {f.evaluation.bias_pct ?? "—"}
                            </small>
                          )}
                          <details>
                            <summary>
                              {tr("Forecast evidence and daily plan")}
                            </summary>
                            <p>
                              {tr("Model selection days")}:{" "}
                              {f.evaluation.selection_days} ·{" "}
                              {tr("Independent test days")}:{" "}
                              {f.evaluation.test_days}
                            </p>
                            {f.evaluation.test_start && (
                              <p dir="ltr">
                                {f.evaluation.test_start} —{" "}
                                {f.evaluation.test_end}
                              </p>
                            )}
                            <p>
                              {tr(
                                "Positive bias means overprediction. Error scores measure the baseline, not the event scenario.",
                              )}
                            </p>
                            {f.baseline_next30 !== null && (
                              <p>
                                {tr("Baseline next 30 days")}:{" "}
                                {f.baseline_next30}
                              </p>
                            )}
                            {f.daily_forecast.length > 0 && (
                              <table>
                                <thead>
                                  <tr>
                                    <th>{tr("Day (UTC)")}</th>
                                    <th>{tr("Baseline units")}</th>
                                    <th>{tr("Planned units")}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {f.daily_forecast.map((day: any) => (
                                    <tr key={day.day}>
                                      <td>{day.day}</td>
                                      <td>{day.baseline}</td>
                                      <td>{day.planned}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </details>
                        </td>
                        <td>
                          <button className="mini" onClick={() => onRestock(f)}>
                            {" "}
                            {tr("Adjust stock")} <ArrowUpRight size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!filtered.length && (
                  <div className="empty">
                    {tr("No matching active products.")}
                  </div>
                )}
              </div>
            </section>
          )}
          {tab === "rankings" && (
            <>
              <div className="forecast-grid">
                {ranking("Best-selling products", data.top)}
                {ranking(
                  "Least-selling products · includes zero sales",
                  data.least,
                )}
              </div>
              <p className="hint">
                {" "}
                {tr(
                  "Ranked by units, with SKU as the tie-breaker. Zero-sale products are included. Gross line sales exclude invoice-level discounts and taxes. Returned invoices are excluded.",
                )}{" "}
              </p>
            </>
          )}
          {tab === "trends" && (
            <div className="forecast-grid">
              {ranking("Rising products", data.rising, "growth")}
              {ranking("Declining products", data.declining, "growth")}
            </div>
          )}
          {tab === "history" && (
            <div className="forecast-grid">
              <section className="panel">
                <h2>{tr("Daily sales · last 30 days")}</h2>
                <div className="table-scroll history-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr("Day (UTC)")}</th>
                        <th>{tr("Units")}</th>
                        <th>{tr("Gross line sales")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.daily].reverse().map((d: any) => (
                        <tr key={d.day}>
                          <td>{d.day}</td>
                          <td>{d.units}</td>
                          <td>{money(d.gross)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="panel">
                <h2>{tr("Monthly sales · available 120-day window")}</h2>
                <p className="hint">
                  {" "}
                  {tr(
                    "The earliest month and current month may be partial. Months without sales are omitted.",
                  )}{" "}
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>{tr("Month")}</th>
                      <th>{tr("Units")}</th>
                      <th>{tr("Gross line sales")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.monthly].reverse().map((d: any) => (
                      <tr key={d.month}>
                        <td>{d.month}</td>
                        <td>{d.units}</td>
                        <td>{money(d.gross)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </div>
          )}
          <details className="panel forecast-method">
            <summary>
              <Info size={16} /> {tr("How these estimates work")}{" "}
            </summary>
            <p>
              {" "}
              {tr(
                "Model choice uses up to three earlier weekly validation windows. A separate final seven-day holdout measures WAPE, daily MAE and bias. Models are refitted on all complete days for planning. Zero-sales days count; today never trains the forecast. Undefined WAPE means zero holdout sales. Evidence is not a guarantee.",
              )}{" "}
            </p>
            <p>
              {" "}
              {tr(
                "Reorder planning extends the baseline average through lead time plus coverage, adds event changes only on affected forecast dates, then applies safety and subtracts stock and open purchases. Stockout assumes no replenishment. Event scenarios omit the rough variation range. Lost sales, learned weather/festival effects and price elasticity are not modeled.",
              )}{" "}
            </p>
            <p>
              {" "}
              {tr(
                "Historical sales exclude invoices currently marked returned, so a later return revises past sales statistics. No-sale and low-history items require manual review. Suggested quantities are never ordered automatically.",
              )}{" "}
            </p>
          </details>
        </>
      )}
    </div>
  );
}
