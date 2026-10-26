import { t as tr } from "./i18n";
const labels: Record<string, string> = {
  invoice_count: "Invoice count",
  gross_subtotal: "Gross subtotal",
  discounts: "Discounts",
  sales_tax: "Sales tax",
  gross_sales: "Gross sales",
  credit_sales: "Credit sales",
  returns: "Returns",
  return_tax: "Return tax",
  net_sales: "Net sales",
  net_tax: "Net tax",
  cash_sales: "Cash sales",
  cash_in: "Cash in",
  cash_out: "Cash out",
  opening_cash: "Opening cash",
  expected_cash: "Expected cash",
};
export default function TillReport({
  data,
  onClose,
}: {
  data: any;
  onClose: () => void;
}) {
  const report = data.report;
  const money = (n: number) =>
    `${report.business.currency} ${(n / 100).toFixed(2)}`;
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `till-${report.kind}-${report.number || report.session.id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section className="panel retail-table" aria-label={tr("Till report")}>
      <div className="actions">
        <h2>
          {report.kind} {tr("Till report")}{" "}
          {report.number && `#${report.number}`}
        </h2>
        <button className="secondary" onClick={download}>
          {tr("Download report JSON")}
        </button>
        <button className="secondary" onClick={onClose}>
          {tr("Close report")}
        </button>
      </div>
      <p>
        {report.business.name} ·{" "}
        {new Date(report.generated_at).toLocaleString()}
      </p>
      <p className="hint">
        {tr(
          "Operational report, not a tax-authority certified fiscal document. Return history starts with this upgrade. Transactions without an open till are excluded.",
        )}
      </p>
      <div className="table-scroll">
        <table>
          <tbody>
            {Object.keys(labels).map((key) => (
              <tr key={key}>
                <th>{tr(labels[key] || key)}</th>
                <td>
                  {key === "invoice_count"
                    ? Number(report.totals[key])
                    : money(Number(report.totals[key]))}
                </td>
              </tr>
            ))}
            {report.kind === "Z" && (
              <>
                <tr>
                  <th>{tr("Counted cash")}</th>
                  <td>{money(report.session.counted_cash)}</td>
                </tr>
                <tr>
                  <th>{tr("Variance")}</th>
                  <td>{money(report.session.variance)}</td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>
      <h3>{tr("Original tender totals")}</h3>
      {report.tenders.map((t: any, i: number) => (
        <p key={i}>
          {t.method}: {money(t.amount)}
        </p>
      ))}
      <h3>{tr("Invoices")}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{tr("Invoice")}</th>
              <th>{tr("Total")}</th>
              <th>{tr("Tax")}</th>
            </tr>
          </thead>
          <tbody>
            {report.invoices.map((i: any) => (
              <tr key={i.id}>
                <td>{i.invoice}</td>
                <td>{money(i.total)}</td>
                <td>{money(i.tax)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{tr("Returns")}</h3>
      {report.returns.map((r: any) => (
        <p key={r.source}>
          {new Date(r.created).toLocaleString()} · {r.source} · {money(r.total)}
        </p>
      ))}
      <p className="hint">
        {tr(
          "Invoice credits and refunds are separate. Cash refunds are included in cash movements; do not subtract returns again from expected cash.",
        )}
      </p>
      {data.digest && (
        <p className="hint" style={{ overflowWrap: "anywhere" }}>
          SHA-256: {data.digest}
        </p>
      )}
    </section>
  );
}
