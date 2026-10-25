import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";
type Event = {
  id: string;
  created: string;
  actor: string;
  action: string;
  details: string;
};
type Page = { items: Event[]; total: number };
export default function AuditLog({ tenant }: { tenant: string }) {
  const [data, setData] = useState<Page | null>(null),
    [query, setQuery] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [page, setPage] = useState(0),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setError("");
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        q: query,
        offset: String(page * 50),
      });
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      api<Page>(`/api/v1/tenants/${tenant}/audit-events?${params}`, {
        signal: c.signal,
      })
        .then(setData)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, query, start, end, page]);
  function exportPage() {
    if (!data) return;
    const cells = (v: unknown) =>
      '"' +
      String(v ?? "")
        .replace(/^[\s]*[=+@-]/, "'$&")
        .replaceAll('"', '""') +
      '"';
    const rows = [
      ["Event ID", "UTC timestamp", "Actor", "Action", "Details"],
      ...data.items.map((e) => [e.id, e.created, e.actor, e.action, e.details]),
    ];
    const u = URL.createObjectURL(
      new Blob(
        ["\uFEFF" + rows.map((r) => r.map(cells).join(",")).join("\r\n")],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const a = document.createElement("a");
    a.href = u;
    a.download = "audit-page.csv";
    a.click();
    URL.revokeObjectURL(u);
  }
  return (
    <section className="panel audit-log">
      <h2>{tr("Search audit history")}</h2>
      <p>
        {tr(
          "Read-only events for this business. Date filters use UTC. Export includes the current page only.",
        )}
      </p>
      <div className="role-fields">
        <label className="field">
          {tr("Search actor, action or details")}
          <input
            value={query}
            maxLength={150}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <label className="field">
          {tr("From date (UTC)")}
          <input
            type="date"
            value={start}
            onChange={(e) => {
              setStart(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <label className="field">
          {tr("Through date (UTC)")}
          <input
            type="date"
            value={end}
            onChange={(e) => {
              setEnd(e.target.value);
              setPage(0);
            }}
          />
        </label>
      </div>
      <button
        className="secondary"
        onClick={exportPage}
        disabled={!data?.items.length}
      >
        {tr("Export this page")}
      </button>
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
              {tr("Matching events")}: {data.total}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Date (UTC)")}</th>
                    <th>{tr("Actor")}</th>
                    <th>{tr("Action")}</th>
                    <th>{tr("Details")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((e) => (
                    <tr key={e.id}>
                      <td>
                        {new Date(e.created).toISOString().replace("T", " ")}
                      </td>
                      <td>{e.actor}</td>
                      <td>{e.action}</td>
                      <td>
                        <details>
                          <summary>{tr("View details")}</summary>
                          <pre>
                            {JSON.stringify(JSON.parse(e.details), null, 2)}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="toolbar">
              <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
                {tr("Previous")}
              </button>
              <span>{page + 1}</span>
              <button
                disabled={(page + 1) * 50 >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </>
        )
      )}
    </section>
  );
}
