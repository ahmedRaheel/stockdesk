import { t as tr } from "./i18n";
import { useEffect, useState } from "react";
import { api } from "./api";
export default function BatchAlerts({
  tenant,
  onAdjust,
}: {
  tenant: string;
  onAdjust: (p: any) => void;
}) {
  const [data, setData] = useState<any>({ expired: [], near_expiry: [] }),
    [batches, setBatches] = useState<any[]>([]),
    [error, setError] = useState(""),
    [page, setPage] = useState(0),
    [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    try {
      const [alerts, all] = await Promise.all([
        api<any>(`/api/v1/tenants/${tenant}/inventory-alerts`),
        api<any>(
          `/api/v1/tenants/${tenant}/batches?limit=100&offset=${page * 100}`,
        ),
      ]);
      setData(alerts);
      setBatches(all.items);
      setError("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [tenant, page]);
  const table = (items: any[]) => (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>{tr("Product")}</th>
            <th>{tr("Batch")}</th>
            <th>{tr("Expiry")}</th>
            <th>{tr("Quantity")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td>
                <b>{b.name}</b>
                <small>{b.sku}</small>
              </td>
              <td>{b.lot}</td>
              <td>{b.expires || "Not tracked"}</td>
              <td>{b.stock}</td>
              <td>
                <button
                  className="mini"
                  onClick={() =>
                    onAdjust({ id: b.product, batch_id: b.id, lot: b.lot })
                  }
                >
                  {" "}
                  {tr("Adjust this batch")}{" "}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="secondary" disabled={loading} onClick={load}>
          {" "}
          {tr("Refresh alerts")}{" "}
        </button>
      </div>
      <div className="forecast-grid retail-table">
        <section className="panel">
          <h2>{tr("Expired batches")}</h2>
          <p>
            {" "}
            {tr(
              "Blocked from sale; record disposal or supplier return separately. First 200 matches.",
            )}{" "}
          </p>
          {table(data.expired)}
        </section>
        <section className="panel">
          <h2>{tr("Due to expire in 30 days")}</h2>
          <p>
            {" "}
            {tr(
              "FEFO checkout allocates earliest expiry first. First 200 matches.",
            )}{" "}
          </p>
          {table(data.near_expiry)}
        </section>
      </div>
      <section className="panel retail-table">
        <h2>{tr("Batch inventory")}</h2>
        <p>
          {" "}
          {tr(
            "Expiry dates are inclusive through the labelled date, using Pakistan time.",
          )}{" "}
        </p>
        {table(batches)}
        <div className="pagination">
          <span>
            {tr("Page")} {page + 1}
          </span>
          <div>
            <button
              className="mini"
              disabled={!page || loading}
              onClick={() => setPage(page - 1)}
            >
              {" "}
              {tr("Previous")}{" "}
            </button>
            <button
              className="mini"
              disabled={batches.length < 100 || loading}
              onClick={() => setPage(page + 1)}
            >
              {" "}
              {tr("Next")}{" "}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
