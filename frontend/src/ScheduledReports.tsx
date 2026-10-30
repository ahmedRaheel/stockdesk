import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { downloadCsv } from "./csv";
import { t as tr } from "./i18n";
import "./memberships.css";
type View = {
  id: string;
  name: string;
  version: number;
  definition: { end: string | null };
};
type Schedule = {
  id: string;
  name: string;
  version: number;
  frequency: string;
  weekday: number;
  hour: number;
  minute: number;
  active: boolean;
  next_run: string;
  retry_after: string | null;
  owner_email: string;
};
type Run = {
  id: string;
  name: string;
  scheduled_for: string;
  status: string;
  attempts: number;
  error: string;
  finished: string | null;
};
type Snapshot = {
  result: {
    start: string;
    end: string;
    currency: string;
    columns: { key: string; label: string; kind: string }[];
    rows: Record<string, unknown>[];
    matching_rows: number;
    truncated: boolean;
  } | null;
};
const states: Record<string, string> = {
  succeeded: "Ready",
  failed: "Failed",
  retrying: "Retry scheduled",
  cancelled: "Cancelled",
};
const weekdays = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const date = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Karachi",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
export default function ScheduledReports({ tenant }: { tenant: string }) {
  const url = `/api/v1/tenants/${tenant}/report-schedules`;
  const [schedules, setSchedules] = useState<Schedule[]>([]),
    [runs, setRuns] = useState<Run[]>([]),
    [views, setViews] = useState<View[]>([]),
    [viewPage, setViewPage] = useState(0),
    [page, setPage] = useState(0),
    [revision, setRevision] = useState(0);
  const [mode, setMode] = useState<"list" | "edit" | "snapshot">("list"),
    [editing, setEditing] = useState<Schedule | null>(null),
    [selectedView, setSelectedView] = useState(""),
    [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [worker, setWorker] = useState(true);
  const editor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (mode !== "list") {
      editor.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      editor.current?.focus();
    }
  }, [mode, editing?.id, selectedRun?.id]);
  const draftId = useRef(newRequestId()),
    controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const c = new AbortController();
    Promise.all([
      api<{ items: Schedule[]; worker_enabled: boolean }>(url, {
        signal: c.signal,
      }),
      api<{ items: Run[] }>(`${url}/runs?offset=${page * 30}`, {
        signal: c.signal,
      }),
    ])
      .then(([s, r]) => {
        if (!c.signal.aborted) {
          setSchedules(s.items);
          setWorker(s.worker_enabled);
          setRuns(r.items);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [tenant, page, revision]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") setRevision((n) => n + 1);
    }, 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const c = new AbortController();
    if (mode !== "edit") return () => c.abort();
    api<{ items: View[] }>(
      `/api/v1/tenants/${tenant}/report-builder/views?offset=${viewPage * 30}`,
      { signal: c.signal },
    )
      .then((r) => {
        if (!c.signal.aborted) setViews(r.items);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [tenant, mode, viewPage]);
  function edit(s: Schedule | null) {
    setEditing(s);
    setSelectedView("");
    setViewPage(0);
    draftId.current = newRequestId();
    setMode("edit");
    setError("");
    setNotice("");
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const view = views.find((v) => v.id === selectedView);
    if (!view || busy) return;
    const f = new FormData(e.currentTarget);
    const time = String(f.get("time")).split(":").map(Number);
    setBusy(true);
    setError("");
    try {
      await send(
        url,
        {
          id: editing?.id || draftId.current,
          version: editing?.version || 0,
          name: f.get("name"),
          view: view.id,
          view_version: view.version,
          frequency: f.get("frequency"),
          weekday: Number(f.get("weekday")),
          hour: time[0],
          minute: time[1],
          active: f.get("active") === "on",
          start_now: f.get("start_now") === "on",
        },
        "PUT",
      );
      setMode("list");
      setNotice("Report schedule saved.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function activate(s: Schedule) {
    setBusy(true);
    setError("");
    try {
      await send(`${url}/${s.id}/activation`, {
        version: s.version,
        active: !s.active,
      });
      setNotice("Report schedule updated.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function evaluate() {
    setBusy(true);
    setError("");
    try {
      await send(url + "/evaluate", {});
      setNotice("Due schedules checked. Open the report inbox for results.");
      setRevision((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function open(run: Run) {
    setBusy(true);
    setError("");
    setSnapshot(null);
    setSelectedRun(run);
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    try {
      const r = await api<Snapshot>(`${url}/runs/${run.id}`, {
        signal: c.signal,
      });
      if (!c.signal.aborted) {
        setSnapshot(r);
        setMode("snapshot");
      }
    } catch (e) {
      if (!c.signal.aborted) setError((e as Error).message);
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  function download() {
    const r = snapshot?.result;
    if (!r) return;
    downloadCsv("scheduled-report.csv", [
      [tr("Period"), r.start, r.end],
      [tr("Currency"), r.currency],
      r.columns.map(
        (c) => tr(c.label) + (c.kind === "money" ? ` (${r.currency})` : ""),
      ),
      ...r.rows.map((row) =>
        r.columns.map((c) =>
          c.kind === "money"
            ? Number(row[c.key]) / 100
            : c.key === "xyz"
              ? tr(String(row[c.key]))
              : row[c.key],
        ),
      ),
    ]);
  }
  return (
    <section className="panel memberships scheduled-reports">
      <div className="membership-heading">
        <div>
          <h2>{tr("Scheduled reports")}</h2>
          <p>
            {tr(
              "Daily or weekly reports, generated into your business inbox. All schedule times use Karachi.",
            )}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              setError("");
              setRevision((n) => n + 1);
            }}
          >
            {tr("Reload")}
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => edit(null)}
          >
            {tr("New schedule")}
          </button>
        </div>
      </div>
      <p className="hint">
        {tr(
          "Each schedule freezes a saved report definition and runs with its last editor’s current permissions. No email or message is sent. The latest 30 runs per schedule are retained.",
        )}
      </p>
      {!worker && (
        <p className="hint">
          {tr(
            "Background report worker is disabled. Use Run due schedules or enable it on the server.",
          )}
        </p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {mode === "edit" ? (
        <div
          className="membership-editor"
          ref={editor}
          tabIndex={-1}
          key={editing?.id || draftId.current}
        >
          <div className="membership-heading">
            <h3>{tr(editing ? "Edit report schedule" : "New schedule")}</h3>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => setMode("list")}
            >
              {tr("Close")}
            </button>
          </div>
          <form onSubmit={save}>
            <fieldset disabled={busy}>
              <label className="field">
                <span>{tr("Schedule name")}</span>
                <input
                  name="name"
                  required
                  maxLength={100}
                  defaultValue={editing?.name || ""}
                />
              </label>
              <label className="field">
                <span>{tr("Saved report view")}</span>
                <select
                  aria-label={tr("Saved report view")}
                  value={selectedView}
                  required
                  onChange={(e) => setSelectedView(e.target.value)}
                >
                  <option value="">
                    {tr("Select a relative report view")}
                  </option>
                  {views
                    .filter((v) => !v.definition.end)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                </select>
              </label>
              <div className="actions">
                <button
                  type="button"
                  className="secondary"
                  disabled={!viewPage}
                  onClick={() => {
                    setSelectedView("");
                    setViewPage((p) => p - 1);
                  }}
                >
                  {tr("Previous views")}
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={views.length < 30}
                  onClick={() => {
                    setSelectedView("");
                    setViewPage((p) => p + 1);
                  }}
                >
                  {tr("Next views")}
                </button>
              </div>
              <p>
                {tr(
                  "Save a custom report with a blank end date first. Editing this schedule replaces its frozen definition and cancels pending retries.",
                )}
              </p>
              <div className="toolbar">
                <label className="field">
                  <span>{tr("Frequency")}</span>
                  <select
                    name="frequency"
                    aria-label={tr("Frequency")}
                    defaultValue={editing?.frequency || "daily"}
                  >
                    <option value="daily">{tr("Daily")}</option>
                    <option value="weekly">{tr("Weekly")}</option>
                  </select>
                </label>
                <label className="field">
                  <span>{tr("Weekly day")}</span>
                  <select
                    name="weekday"
                    aria-label={tr("Weekly day")}
                    defaultValue={editing?.weekday || 0}
                  >
                    {weekdays.map((day, i) => (
                      <option key={day} value={i}>
                        {tr(day)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>{tr("Time in Karachi")}</span>
                  <input
                    name="time"
                    type="time"
                    required
                    defaultValue={
                      editing
                        ? `${String(editing.hour).padStart(2, "0")}:${String(editing.minute).padStart(2, "0")}`
                        : "08:00"
                    }
                  />
                </label>
              </div>
              <div className="actions">
                <label>
                  <input
                    type="checkbox"
                    name="active"
                    defaultChecked={editing?.active ?? true}
                  />
                  {tr("Active")}
                </label>
                <label>
                  <input
                    type="checkbox"
                    name="start_now"
                    defaultChecked={!editing}
                  />
                  {tr("Queue first report now")}
                </label>
              </div>
              <button className="primary" disabled={!selectedView}>
                {tr("Save report schedule")}
              </button>
            </fieldset>
          </form>
        </div>
      ) : mode === "snapshot" && snapshot?.result ? (
        <div className="membership-editor">
          <div className="membership-heading">
            <h3>{selectedRun?.name}</h3>
            <div className="actions">
              <button className="secondary" onClick={download}>
                {tr("Export CSV")}
              </button>
              <button className="secondary" onClick={() => setMode("list")}>
                {tr("Close")}
              </button>
            </div>
          </div>
          <p>
            <span dir="ltr">
              {snapshot.result.start} — {snapshot.result.end}
            </span>{" "}
            · {tr("Generated")}:{" "}
            <span dir="ltr">
              {selectedRun?.finished ? date(selectedRun.finished) : "—"}
            </span>
          </p>
          <p>
            {tr(
              "This saved snapshot does not change when invoices, products or report views change later.",
            )}
          </p>
          {snapshot.result.truncated && (
            <p>
              {tr(
                "The row limit was reached. This snapshot contains only the configured rows.",
              )}
            </p>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {snapshot.result.columns.map((c) => (
                    <th key={c.key}>{tr(c.label)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {snapshot.result.rows.map((row, i) => (
                  <tr key={i}>
                    {snapshot.result!.columns.map((c) => (
                      <td key={c.key}>
                        {row[c.key] == null
                          ? "—"
                          : c.kind === "money"
                            ? new Intl.NumberFormat("en-PK", {
                                style: "currency",
                                currency: snapshot.result!.currency,
                              }).format(Number(row[c.key]) / 100)
                            : c.key === "xyz"
                              ? tr(String(row[c.key]))
                              : String(row[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <>
          <div className="membership-cards">
            {schedules.map((s) => (
              <article key={s.id}>
                <div className="membership-heading">
                  <h3>{s.name}</h3>
                  <span className="membership-badge">
                    {tr(s.active ? "Active" : "Paused")}
                  </span>
                </div>
                <p>
                  {tr(s.frequency === "daily" ? "Daily" : "Weekly")}
                  {s.frequency === "weekly"
                    ? ` · ${tr(weekdays[s.weekday])}`
                    : ""}{" "}
                  ·{" "}
                  <span dir="ltr">
                    {String(s.hour).padStart(2, "0")}:
                    {String(s.minute).padStart(2, "0")}
                  </span>
                </p>
                <small>
                  {tr("Runs as")}: {s.owner_email}
                </small>
                <p>
                  {tr(s.retry_after ? "Retry at" : "Next run")}:{" "}
                  <span dir="ltr">
                    {s.active ? date(s.retry_after || s.next_run) : "—"}
                  </span>
                </p>
                <div className="actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => edit(s)}
                  >
                    {tr("Edit schedule")}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => activate(s)}
                  >
                    {tr(s.active ? "Pause schedule" : "Resume schedule")}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {!schedules.length && <p>{tr("No report schedules yet.")}</p>}
          <div className="membership-heading">
            <h3>{tr("Report inbox")}</h3>
            <button className="secondary" disabled={busy} onClick={evaluate}>
              {tr("Run due schedules")}
            </button>
          </div>
          <div className="membership-cards">
            {runs.map((r) => (
              <article key={r.id}>
                <div className="membership-heading">
                  <h3>{r.name}</h3>
                  <span className="membership-badge">
                    {tr(states[r.status])}
                  </span>
                </div>
                <p>
                  {tr("Scheduled for")}:{" "}
                  <span dir="ltr">{date(r.scheduled_for)}</span>
                </p>
                <small>
                  {tr("Attempts")}: {r.attempts}/3
                </small>
                {r.error && <p>{tr(r.error)}</p>}
                {r.status === "succeeded" && (
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => open(r)}
                  >
                    {tr("Open snapshot")}
                  </button>
                )}
              </article>
            ))}
          </div>
          {!runs.length && <p>{tr("No generated reports yet.")}</p>}
          <div className="pagination">
            <span>
              {tr("Page")} {page + 1}
            </span>
            <div className="actions">
              <button
                className="secondary"
                disabled={!page || busy}
                onClick={() => setPage((p) => p - 1)}
              >
                {tr("Previous")}
              </button>
              <button
                className="secondary"
                disabled={runs.length < 30 || busy}
                onClick={() => setPage((p) => p + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </div>
        </>
      )}
      {busy && <p role="status">{tr("Loading…")}</p>}
    </section>
  );
}
