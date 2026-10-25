import { useState } from "react";
import { t as tr } from "./i18n";
export default function ReportExports({
  tenant,
  name,
  filters,
  disabled = false,
}: {
  tenant: string;
  name: string;
  filters: Record<string, number>;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function download(format: string) {
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams(
        Object.entries(filters).map(([k, v]) => [k, String(v)]),
      );
      const response = await fetch(
        `/api/v1/tenants/${tenant}/report-export/${name}.${format}?${params}`,
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw Error(body?.error || tr("Report download failed."));
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}.${format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="report-exports">
      <button
        className="secondary"
        type="button"
        disabled={disabled || busy}
        onClick={() => download("xlsx")}
      >
        {tr("Export Excel")}
      </button>{" "}
      <button
        className="secondary"
        type="button"
        disabled={disabled || busy}
        onClick={() => download("pdf")}
      >
        {tr("Export PDF")}
      </button>
      {error && (
        <span role="alert" className="form-error">
          {tr(error)}
        </span>
      )}
    </span>
  );
}
