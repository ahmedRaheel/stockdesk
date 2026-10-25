import { useEffect, useState } from "react";
import { api, send } from "./api";
import { t as tr, useLanguage } from "./i18n";
type Role = {
  id: string;
  name: string;
  name_ur: string;
  active: boolean;
  version: number;
  members: number;
  permissions: string[];
};
type Member = {
  id: string;
  name: string;
  email: string;
  role: string;
  custom_role_id: string | null;
  custom_name: string | null;
  active: boolean;
};
type Catalog = {
  items: Role[];
  permissions: Record<string, string>;
  dependencies: Record<string, string[]>;
};
export default function RoleManagement({ tenant }: { tenant: string }) {
  const base = `/api/v1/tenants/${tenant}/roles`;
  const [language] = useLanguage();
  const [data, setData] = useState<Catalog | null>(null),
    [members, setMembers] = useState<Member[]>([]),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [selected, setSelected] = useState<Role | null>(null),
    [editing, setEditing] = useState(false),
    [grants, setGrants] = useState<string[]>(["read"]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    api<Catalog>(base, { signal: c.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [base, revision]);
  useEffect(() => {
    const c = new AbortController();
    const timer = setTimeout(
      () =>
        api<{ items: Member[] }>(
          `${base}/members?q=${encodeURIComponent(query)}&offset=${page * 50}`,
          { signal: c.signal },
        )
          .then((r) => setMembers(r.items))
          .catch((e) => {
            if (e.name !== "AbortError") setError(e.message);
          }),
      180,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [base, query, page, revision]);
  function edit(role: Role | null) {
    setSelected(role);
    setGrants(role?.permissions || ["read"]);
    setEditing(true);
    setError("");
    setNotice("");
  }
  function toggle(key: string) {
    if (key === "read") return;
    setGrants((old) => {
      const next = new Set(old);
      if (next.has(key)) {
        next.delete(key);
        let changed = true;
        while (changed) {
          changed = false;
          for (const p of next)
            if ((data?.dependencies[p] || []).some((d) => !next.has(d))) {
              next.delete(p);
              changed = true;
            }
        }
      } else {
        next.add(key);
        for (const d of data?.dependencies[key] || []) next.add(d);
      }
      return [...next];
    });
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const payload = {
      name: f.get("name"),
      name_ur: f.get("name_ur"),
      permissions: grants,
    };
    try {
      await send(
        selected ? `${base}/${selected.id}` : base,
        selected
          ? {
              ...payload,
              version: selected.version,
              active: f.get("active") === "on",
            }
          : payload,
        selected ? "PUT" : "POST",
      );
      setEditing(false);
      setRevision((x) => x + 1);
      setNotice("Role saved. Changes apply on the next API request.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function assign(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await send(`${base}/assignments`, {
        member: f.get("member"),
        role_id: f.get("role_id"),
      });
      setRevision((x) => x + 1);
      setNotice("Role assignment saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="role-management">
      <p>
        {tr(
          "Custom roles apply to this business only. Owner and team administration cannot be delegated. Disabling a role blocks its assigned members until reassigned.",
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {!data ? (
        <p>{tr("Loading…")}</p>
      ) : (
        <>
          <button
            className="primary"
            onClick={() => edit(null)}
            disabled={busy}
          >
            {tr("Create custom role")}
          </button>
          {editing && (
            <form key={selected?.id || "new"} className="panel" onSubmit={save}>
              <h2>
                {selected ? tr("Edit custom role") : tr("Create custom role")}
              </h2>
              <fieldset disabled={busy}>
                <div className="role-fields">
                  <label className="field">
                    {tr("Role name")}
                    <input
                      name="name"
                      required
                      maxLength={80}
                      defaultValue={selected?.name}
                    />
                  </label>
                  <label className="field">
                    {tr("Urdu role name")}
                    <input
                      name="name_ur"
                      maxLength={80}
                      defaultValue={selected?.name_ur}
                    />
                  </label>
                </div>
                {selected && (
                  <label>
                    <input
                      type="checkbox"
                      name="active"
                      defaultChecked={selected.active}
                    />
                    {tr("Role enabled")}
                  </label>
                )}
                <p>
                  {tr(
                    "Required permissions are selected automatically. Removing a prerequisite also removes permissions that depend on it.",
                  )}
                </p>
                <div className="permission-grid">
                  {Object.entries(data.permissions).map(([key, label]) => (
                    <label key={key}>
                      <input
                        type="checkbox"
                        checked={grants.includes(key)}
                        disabled={key === "read"}
                        onChange={() => toggle(key)}
                      />
                      <span>{tr(label)}</span>
                    </label>
                  ))}
                </div>
                <button className="primary" disabled={busy}>
                  {tr("Save role")}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditing(false)}
                >
                  {tr("Cancel")}
                </button>
              </fieldset>
            </form>
          )}
          <section className="panel">
            <h2>{tr("Custom role register")}</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Role")}</th>
                    <th>{tr("Status")}</th>
                    <th>{tr("Assigned members")}</th>
                    <th>{tr("Permissions")}</th>
                    <th>{tr("Action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={r.id}>
                      <td>
                        {language === "ur" && r.name_ur ? r.name_ur : r.name}
                      </td>
                      <td>{tr(r.active ? "Active" : "Disabled")}</td>
                      <td>{r.members}</td>
                      <td>
                        {r.permissions
                          .map((p) => tr(data.permissions[p] || p))
                          .join(" · ")}
                      </td>
                      <td>
                        <button onClick={() => edit(r)} disabled={busy}>
                          {tr("Edit")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data.items.length && <p>{tr("No custom roles yet.")}</p>}
          </section>
          <section className="panel">
            <h2>{tr("Assign custom role")}</h2>
            <p>
              {tr(
                "Create staff accounts in Team & roles first. Owner memberships are protected. Assigning a role does not reactivate a disabled member. Use Team & roles to restore a built-in role.",
              )}
            </p>
            <label className="field">
              {tr("Search staff")}
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </label>
            <form onSubmit={assign}>
              <fieldset disabled={busy}>
                <div className="role-fields">
                  <label className="field">
                    {tr("Staff member")}
                    <select
                      name="member"
                      required
                      aria-label={tr("Staff member")}
                      defaultValue=""
                    >
                      <option value="">{tr("Select…")}</option>
                      {members
                        .filter((m) => m.role !== "Owner")
                        .map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} · {m.email} · {m.custom_name || m.role}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label className="field">
                    {tr("Custom role")}
                    <select
                      name="role_id"
                      required
                      aria-label={tr("Custom role")}
                      defaultValue=""
                    >
                      <option value="">{tr("Select…")}</option>
                      {data.items
                        .filter((r) => r.active)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {language === "ur" && r.name_ur
                              ? r.name_ur
                              : r.name}
                          </option>
                        ))}
                    </select>
                  </label>
                </div>
                <button className="primary" disabled={busy}>
                  {tr("Assign role")}
                </button>
              </fieldset>
            </form>
            <div className="toolbar">
              <button
                disabled={!page || busy}
                onClick={() => setPage((p) => p - 1)}
              >
                {tr("Previous")}
              </button>
              <button
                disabled={members.length < 50 || busy}
                onClick={() => setPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
