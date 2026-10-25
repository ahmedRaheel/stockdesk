import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
export default function Tills({
  tenant,
  currency,
}: {
  tenant: string;
  currency: string;
}) {
  const base = `/api/v1/tenants/${tenant}/tills`;
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const pending = useRef<any>(null);
  const money = (n: number) =>
    `${currency === "PKR" ? "Rs." : currency} ${(n / 100).toFixed(2)}`;
  async function load() {
    try {
      setData(await api(base));
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [tenant]);
  async function submit(e: React.FormEvent<HTMLFormElement>, action: string) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f: any = Object.fromEntries(new FormData(e.currentTarget).entries());
    try {
      if (action === "open")
        await send(base, { opening_cash: Math.round(Number(f.amount) * 100) });
      if (action === "move") {
        const value = {
          type: f.type,
          amount: Math.round(Number(f.amount) * 100),
          reason: f.reason,
        };
        const sig = JSON.stringify(value);
        if (pending.current?.sig !== sig)
          pending.current = { sig, id: newRequestId() };
        await send(`${base}/${data.current.id}/cash-movements`, {
          ...value,
          request: pending.current.id,
        });
        pending.current = null;
      }
      if (action === "close")
        await send(`${base}/${data.current.id}/close`, {
          counted_cash: Math.round(Number(f.amount) * 100),
          note: f.note,
        });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const amount = (label: string) => (
    <label className="field">
      <span>
        {label} ({currency})
      </span>
      <input name="amount" type="number" min="0" step="0.01" required />
    </label>
  );
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="secondary" onClick={load}>
          {" "}
          {tr("Refresh")}{" "}
        </button>
      </div>
      <p>
        {" "}
        {tr(
          "Sessions belong to the signed-in cashier. Open a session before billing to include sales here. Existing sales without a session remain outside till reports.",
        )}{" "}
      </p>
      {!data ? (
        <p>{tr("Loading…")}</p>
      ) : (
        <>
          {data.current ? (
            <>
              <div className="kpis">
                {Object.entries(data.totals).map(([k, v]) => (
                  <div className="kpi" key={k}>
                    <div>{k.replaceAll("_", " ")}</div>
                    <strong>{money(Number(v))}</strong>
                  </div>
                ))}
              </div>
              <div className="forecast-grid">
                <form className="panel" onSubmit={(e) => submit(e, "move")}>
                  <fieldset disabled={busy}>
                    <h2>{tr("Cash in / out")}</h2>
                    <label className="field">
                      <span>{tr("Movement")}</span>
                      <select name="type">
                        <option value="IN">{tr("Cash in")}</option>
                        <option value="OUT">{tr("Cash out / refund")}</option>
                      </select>
                    </label>
                    {amount("Amount")}
                    <label className="field">
                      <span>{tr("Reason / refund reference")}</span>
                      <input name="reason" required maxLength={500} />
                    </label>
                    <button className="primary">{tr("Record movement")}</button>
                  </fieldset>
                </form>
                <form className="panel" onSubmit={(e) => submit(e, "close")}>
                  <fieldset disabled={busy}>
                    <h2>{tr("Close and reconcile")}</h2>
                    {amount("Counted cash")}
                    <label className="field">
                      <span>{tr("Discrepancy explanation / note")}</span>
                      <input name="note" maxLength={500} />
                    </label>
                    <p>
                      {" "}
                      {tr(
                        "Returns do not move cash automatically. Record an actual cash refund as cash out before closing.",
                      )}{" "}
                    </p>
                    <button className="primary">{tr("Close session")}</button>
                  </fieldset>
                </form>
              </div>
              <section className="panel retail-table">
                <h2>{tr("Cash movements")}</h2>
                {data.movements.map((m: any) => (
                  <p key={m.id}>
                    {new Date(m.created).toLocaleString()} · {money(m.amount)} ·{" "}
                    {m.reason}
                  </p>
                ))}
              </section>
            </>
          ) : (
            <form
              className="panel settings"
              onSubmit={(e) => submit(e, "open")}
            >
              <fieldset disabled={busy}>
                <h2>{tr("Open till")}</h2>
                {amount("Opening cash")}
                <button className="primary">{tr("Open session")}</button>
              </fieldset>
            </form>
          )}
          <section className="panel retail-table">
            <h2>{tr("Session history")}</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Opened")}</th>
                    <th>{tr("Status")}</th>
                    <th>{tr("Expected")}</th>
                    <th>{tr("Counted")}</th>
                    <th>{tr("Variance")}</th>
                    <th>{tr("Notes")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sessions.map((s: any) => (
                    <tr key={s.id}>
                      <td>{new Date(s.opened).toLocaleString()}</td>
                      <td>{s.status}</td>
                      <td>
                        {s.expected_cash === null
                          ? "—"
                          : money(s.expected_cash)}
                      </td>
                      <td>
                        {s.counted_cash === null ? "—" : money(s.counted_cash)}
                      </td>
                      <td>{s.variance === null ? "—" : money(s.variance)}</td>
                      <td>{s.closing_note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
