import { newRequestId } from "./requestId";
import { useRef, useState } from "react";
import { send } from "./api";
import { t as tr } from "./i18n";
type Preview = {
  count: number;
  preview_token?: string;
  changes?: {
    row: number;
    sku: string;
    name: string;
    changes: Record<string, { before: any; after: any }>;
  }[];
  items: {
    row: number;
    sku: string;
    name: string;
    price: number;
    initial: number;
  }[];
};
export default function CatalogImport({
  tenant,
  onImported,
  canUpdate,
}: {
  tenant: string;
  onImported: () => void;
  canUpdate: boolean;
}) {
  const [mode, setMode] = useState("create"),
    [exportSearch, setExportSearch] = useState("");
  const [text, setText] = useState(""),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState<{ mode: string; count: number } | null>(
      null,
    );
  const pending = useRef<{ text: string; id: string } | null>(null);
  function template() {
    const u = URL.createObjectURL(
      new Blob(
        [
          "sku,name,category_code,unit_code,barcode,price,cost,initial,reorder\r\nSAMPLE-001,Sample product,general,piece,001234567,150.00,100.00,0,5\r\n",
        ],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const a = document.createElement("a");
    a.href = u;
    a.download = "catalog-template.csv";
    a.click();
    URL.revokeObjectURL(u);
  }
  async function load(file?: File) {
    if (!file) return;
    setError("");
    setPreview(null);
    setNotice(null);
    setText("");
    const suffix = file.name.toLowerCase().split(".").pop();
    const excel = suffix === "xlsx" || suffix === "xls";
    if (!["csv", "xlsx", "xls"].includes(suffix || "")) {
      setError(tr("Choose a CSV, XLSX or XLS catalog file."));
      return;
    }
    if (file.size > (excel ? 1000000 : 200000)) {
      setError(
        tr(
          excel
            ? "Excel file is too large. Maximum 1 MB."
            : "CSV file is too large. Maximum 200 KB.",
        ),
      );
      return;
    }
    setBusy(true);
    try {
      if (excel) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        for (let i = 0; i < bytes.length; i += 32768)
          binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
        const converted = await send<{ csv_text: string }>(
          `/api/v1/tenants/${tenant}/catalog-imports/convert-${suffix}`,
          { file_base64: btoa(binary) },
        );
        setText(converted.csv_text);
      } else setText(await file.text());
    } catch (e) {
      setError((e as Error).message || tr("Could not read the catalog file."));
    } finally {
      setBusy(false);
    }
  }
  async function run(commit = false) {
    setBusy(true);
    setError("");
    setNotice(null);
    try {
      const base = `/api/v1/tenants/${tenant}/catalog-imports`;
      if (commit) {
        if (!pending.current || pending.current.text !== mode + text)
          pending.current = { text: mode + text, id: newRequestId() };
        const r = await send<{ product_ids: string[] }>(base, {
          csv_text: text,
          mode,
          preview_token: preview?.preview_token,
          request: pending.current.id,
        });
        setNotice({ mode, count: r.product_ids.length });
        setPreview(null);
        setText("");
        pending.current = null;
        onImported();
      } else
        setPreview(
          await send<Preview>(base + "/preview", { csv_text: text, mode }),
        );
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel catalog-import">
      <h2>{tr("Catalog import and updates")}</h2>
      <label className="field">
        {tr("Import mode")}
        <select
          value={mode}
          disabled={busy}
          onChange={(e) => {
            setMode(e.target.value);
            setPreview(null);
            setNotice(null);
            setError("");
            pending.current = null;
          }}
        >
          <option value="create">{tr("Create new products")}</option>
          {canUpdate && (
            <option value="update">
              {tr("Update existing products by SKU")}
            </option>
          )}
        </select>
      </label>
      {canUpdate && (
        <div className="panel" style={{ padding: 16, marginBlock: 16 }}>
          <label className="field">
            {tr("Export search (name, SKU or barcode)")}
            <input
              value={exportSearch}
              maxLength={100}
              onChange={(e) => setExportSearch(e.target.value)}
            />
          </label>
          <button
            className="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const r = await fetch(
                  `/api/v1/tenants/${tenant}/catalog-imports/export.xlsx?q=${encodeURIComponent(exportSearch)}`,
                );
                if (!r.ok) {
                  const e = await r.json();
                  throw Error(e.error);
                }
                const url = URL.createObjectURL(await r.blob());
                const a = document.createElement("a");
                a.href = url;
                a.download = "catalog-update.xlsx";
                a.click();
                URL.revokeObjectURL(url);
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {tr("Export editable Excel")}
          </button>
          <p className="hint">
            {tr(
              "Export includes active and inactive matches, up to 200 products. Narrow the search for larger catalogs. Opening stock is always zero in an update file.",
            )}
          </p>
        </div>
      )}
      {mode === "update" && (
        <p className="hint">
          {tr(
            "Updates require existing SKUs and zero opening stock. Names, barcodes, category, prices, costs and reorder levels can change. Units, stock, active status, tax and medical settings are preserved. Blank barcode clears it; other values replace existing values.",
          )}
        </p>
      )}
      {mode === "create" && (
        <p>
          {tr(
            "Upload UTF-8 CSV or a single-sheet XLSX/XLS workbook, up to 200 rows. Existing products are never overwritten in create mode. All rows succeed together or none are added.",
          )}
        </p>
      )}
      <p>
        {tr(
          "Use active category and unit codes from Lookup management. Prices and costs are in major currency units. Barcode cells must be text to retain leading zeros.",
        )}
      </p>
      <button className="secondary" onClick={template}>
        {tr("Download CSV template")}
      </button>
      <a
        className="secondary"
        href={`/api/v1/tenants/${tenant}/catalog-imports/template.xlsx`}
      >
        {tr("Download Excel template")}
      </a>
      <p>
        {tr(
          "Excel formulas, macros and external workbook links are rejected. Use text for SKU, category, unit and barcode cells. Replace the sample row before importing.",
        )}
      </p>
      <label className="field">
        {tr("CSV or Excel file")}
        <input
          type="file"
          accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={busy}
          onChange={(e) => load(e.target.files?.[0])}
        />
      </label>
      <label className="field">
        {tr("CSV contents")}
        <textarea
          aria-label={tr("CSV contents")}
          rows={8}
          value={text}
          disabled={busy}
          onChange={(e) => {
            setText(e.target.value);
            setPreview(null);
            setNotice(null);
          }}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && (
        <p role="status">
          {tr(
            notice.mode === "update"
              ? "Product updates processed"
              : "Products imported",
          )}
          : {notice.count}
        </p>
      )}
      <button
        className="secondary"
        disabled={busy || !text}
        onClick={() => run()}
      >
        {tr("Validate and preview")}
      </button>
      {preview && (
        <>
          <p>
            {tr("Validated rows")}: {preview.count}
          </p>
          {mode === "update" ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("SKU")}</th>
                    <th>{tr("Field")}</th>
                    <th>{tr("Before")}</th>
                    <th>{tr("After")}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.changes?.flatMap((p) =>
                    Object.keys(p.changes).length
                      ? Object.entries(p.changes).map(([key, value]) => (
                          <tr key={p.row + key}>
                            <td>{p.sku}</td>
                            <td>
                              {tr(
                                (
                                  {
                                    name: "Product",
                                    barcode: "Barcode",
                                    price: "Price",
                                    cost: "Cost",
                                    reorder: "Reorder point",
                                    category_code: "Category code",
                                  } as Record<string, string>
                                )[key] || key,
                              )}
                            </td>
                            <td>
                              {key === "price" || key === "cost"
                                ? (Number(value.before) / 100).toFixed(2)
                                : String(value.before ?? "—")}
                            </td>
                            <td>
                              {key === "price" || key === "cost"
                                ? (Number(value.after) / 100).toFixed(2)
                                : String(value.after ?? "—")}
                            </td>
                          </tr>
                        ))
                      : [
                          <tr key={p.row}>
                            <td>{p.sku}</td>
                            <td colSpan={3}>{tr("No changes")}</td>
                          </tr>,
                        ],
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr("Row")}</th>
                    <th>{tr("SKU")}</th>
                    <th>{tr("Product")}</th>
                    <th>{tr("Opening stock")}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((p) => (
                    <tr key={p.row}>
                      <td>{p.row}</td>
                      <td>{p.sku}</td>
                      <td>{p.name}</td>
                      <td>{p.initial}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p>
            {tr(
              mode === "update"
                ? "Changes after preview reject the entire update. Validate again to review the latest values. Stock movements alone do not invalidate the preview."
                : "Preview does not reserve SKUs. All rules are checked again when importing.",
            )}
          </p>
          <button className="primary" disabled={busy} onClick={() => run(true)}>
            {tr(
              mode === "update"
                ? "Apply reviewed updates"
                : "Import validated products",
            )}
          </button>
        </>
      )}
    </section>
  );
}
