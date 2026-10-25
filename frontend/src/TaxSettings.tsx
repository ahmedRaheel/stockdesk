import { t as tr } from "./i18n";
import { useEffect, useState } from "react";
import { api, send } from "./api";
export default function TaxSettings({
  tenant,
  onSaved,
}: {
  tenant: string;
  onSaved: () => void;
}) {
  const base = `/api/v1/tenants/${tenant}`;
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [edit, setEdit] = useState<any>(null),
    [mode, setMode] = useState("manual"),
    [defaultId, setDefault] = useState("");
  async function load() {
    try {
      const d = await api<any>(base + "/tax-settings");
      setData(d);
      setMode(d.mode);
      setDefault(d.default_profile || "");
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [tenant]);
  async function save(e: React.FormEvent<HTMLFormElement>, profile: boolean) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f: any = Object.fromEntries(new FormData(e.currentTarget).entries());
    try {
      if (profile) {
        await send(
          base + "/tax-profiles" + (edit?.id ? "/" + edit.id : ""),
          {
            name: f.name,
            name_ur: f.name_ur,
            rate_bps: Math.round(Number(f.rate) * 100),
            inclusive: f.inclusive === "on",
            active: f.active === "on",
            starts_on: f.starts_on || null,
            ends_on: f.ends_on || null,
          },
          edit?.id ? "PUT" : "POST",
        );
        setEdit(null);
      } else
        await send(
          base + "/tax-settings",
          { mode, default_profile: defaultId || null },
          "PUT",
        );
      await load();
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="retail-module tax-profiles">
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      <form className="panel" onSubmit={(e) => save(e, false)}>
        <fieldset disabled={busy || !data}>
          <h2>{tr("Tax configuration")}</h2>
          <p>
            {tr(
              "Choose when tax applies. Configure rates for your business; no statutory rates are assumed.",
            )}
          </p>
          <label className="field">
            <span>{tr("Tax mode")}</span>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="disabled">{tr("Disabled — no tax")}</option>
              <option value="configured">
                {tr("Configured tax profiles")}
              </option>
              <option value="manual">
                {tr("Legacy manual entry at checkout")}
              </option>
            </select>
          </label>
          <label className="field">
            <span>{tr("Default tax profile")}</span>
            <select
              value={defaultId}
              onChange={(e) => setDefault(e.target.value)}
            >
              <option value="">{tr("No default tax")}</option>
              {data?.profiles.map((p: any) => (
                <option key={p.id} value={p.id} disabled={!p.active}>
                  {p.name} · {p.rate_bps / 100}% ·{" "}
                  {p.inclusive ? tr("Inclusive") : tr("Exclusive")}
                  {!p.active ? tr(" · Inactive") : ""}
                </option>
              ))}
            </select>
          </label>
          <p>
            {tr(
              "Product overrides take precedence. Use a zero-rate profile for exempt products. Inactive or expired assigned profiles block checkout until corrected.",
            )}
          </p>
          <button className="primary">{tr("Save tax settings")}</button>
        </fieldset>
      </form>
      <div className="panel">
        <div className="panel-heading">
          <h2>{tr("Tax profiles")}</h2>
          <button className="secondary" onClick={() => setEdit({})}>
            {tr("Add tax profile")}
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{tr("Name")}</th>
                <th>{tr("Rate")}</th>
                <th>{tr("Pricing")}</th>
                <th>{tr("Effective dates")}</th>
                <th>{tr("Status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data?.profiles.map((p: any) => (
                <tr key={p.id}>
                  <td>
                    {p.name}
                    <small dir="rtl">{p.name_ur}</small>
                  </td>
                  <td>{p.rate_bps / 100}%</td>
                  <td>{p.inclusive ? tr("Inclusive") : tr("Exclusive")}</td>
                  <td>
                    {p.starts_on || "—"} / {p.ends_on || "—"}
                  </td>
                  <td>{p.active ? tr("Active") : tr("Inactive")}</td>
                  <td>
                    <button className="mini" onClick={() => setEdit(p)}>
                      {tr("Edit")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {edit && (
        <form
          className="panel"
          key={edit.id || "new"}
          onSubmit={(e) => save(e, true)}
        >
          <fieldset disabled={busy}>
            <h2>{edit.id ? tr("Edit tax profile") : tr("Add tax profile")}</h2>
            <div className="form-grid">
              <label className="field">
                <span>{tr("Name")}</span>
                <input
                  name="name"
                  required
                  maxLength={100}
                  defaultValue={edit.name}
                />
              </label>
              <label className="field">
                <span>{tr("Urdu name")}</span>
                <input
                  name="name_ur"
                  dir="rtl"
                  maxLength={100}
                  defaultValue={edit.name_ur}
                />
              </label>
              <label className="field">
                <span>{tr("Rate (%)")}</span>
                <input
                  name="rate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  required
                  defaultValue={(edit.rate_bps || 0) / 100}
                />
              </label>
              <label className="field">
                <span>{tr("Starts on")}</span>
                <input
                  name="starts_on"
                  type="date"
                  defaultValue={edit.starts_on || ""}
                />
              </label>
              <label className="field">
                <span>{tr("Ends on")}</span>
                <input
                  name="ends_on"
                  type="date"
                  defaultValue={edit.ends_on || ""}
                />
              </label>
            </div>
            <label>
              <input
                name="inclusive"
                type="checkbox"
                defaultChecked={edit.inclusive}
              />{" "}
              {tr("Prices include tax")}
            </label>
            <label>
              <input
                name="active"
                type="checkbox"
                defaultChecked={edit.active ?? true}
              />{" "}
              {tr("Active")}
            </label>
            <div className="actions">
              <button className="primary">{tr("Save profile")}</button>
              <button
                type="button"
                className="secondary"
                onClick={() => setEdit(null)}
              >
                {tr("Cancel")}
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </div>
  );
}
