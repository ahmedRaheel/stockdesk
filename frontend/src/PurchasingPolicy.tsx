import { useEffect, useState } from "react";
import { api, send } from "./api";
import { t as tr } from "./i18n";
type Policy = { enabled: boolean; threshold: number; version: number };
export default function PurchasingPolicy({
  tenant,
  currency,
  canConfigure,
}: {
  tenant: string;
  currency: string;
  canConfigure: boolean;
}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const path = `/api/v1/tenants/${tenant}/purchasing-policy`;
  async function load(signal?: AbortSignal) {
    try {
      setPolicy(await api<Policy>(path, { signal }));
      setError("");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    }
  }
  useEffect(() => {
    const c = new AbortController();
    load(c.signal);
    return () => c.abort();
  }, [tenant]);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!policy || busy) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await send(
        path,
        {
          enabled: f.get("enabled") === "on",
          threshold: Math.round(Number(f.get("threshold")) * 100),
          version: policy.version,
        },
        "PUT",
      );
      await load();
      setNotice("Approval policy saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{tr("Purchase approval policy")}</h2>
        <button className="mini" disabled={busy} onClick={() => load()}>
          {tr("Reload")}
        </button>
      </div>
      <p className="hint">
        {tr(
          "When enabled, new orders at or above the threshold require a different approver. Existing orders keep their original policy. Make sure another user has approval permission.",
        )}
      </p>
      {policy &&
        (canConfigure ? (
          <form key={policy.version} onSubmit={save}>
            <fieldset disabled={busy}>
              <div className="form-grid">
                <label className="field">
                  <span>{tr("Require independent approval")}</span>
                  <input
                    type="checkbox"
                    name="enabled"
                    defaultChecked={policy.enabled}
                  />
                </label>
                <label className="field">
                  <span>
                    {tr("Approval threshold")} ({currency})
                  </span>
                  <input
                    name="threshold"
                    type="number"
                    min="0"
                    max="1000000000"
                    step="0.01"
                    required
                    defaultValue={policy.threshold / 100}
                  />
                </label>
              </div>
              <button className="secondary">
                {tr(busy ? "Saving…" : "Save policy")}
              </button>
            </fieldset>
          </form>
        ) : (
          <p>
            {tr(policy.enabled ? "Approval enabled" : "Approval disabled")} ·{" "}
            {currency} {(policy.threshold / 100).toFixed(2)}
          </p>
        ))}
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
    </section>
  );
}
