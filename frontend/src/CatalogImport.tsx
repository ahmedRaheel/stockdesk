import { useRef, useState } from "react";
import { send } from "./api";
import { t as tr } from "./i18n";
type Preview = {
  count: number;
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
}: {
  tenant: string;
  onImported: () => void;
}) {
  const [text, setText] = useState(""),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
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
    setNotice("");
    setText("");
    const excel = file.name.toLowerCase().endsWith(".xlsx");
    if (file.size > (excel ? 1000000 : 200000)) {
      setError(
        tr(
          excel
            ? "XLSX file is too large. Maximum 1 MB."
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
          `/api/v1/tenants/${tenant}/catalog-imports/convert-xlsx`,
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
    setNotice("");
    try {
      const base = `/api/v1/tenants/${tenant}/catalog-imports`;
      if (commit) {
        if (!pending.current || pending.current.text !== text)
          pending.current = { text, id: crypto.randomUUID() };
        const r = await send<{ product_ids: string[] }>(base, {
          csv_text: text,
          request: pending.current.id,
        });
        setNotice(`${tr("Products imported")}: ${r.product_ids.length}`);
        setPreview(null);
        setText("");
        pending.current = null;
        onImported();
      } else
        setPreview(await send<Preview>(base + "/preview", { csv_text: text }));
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel catalog-import">
      <h2>{tr("Import new products")}</h2>
      <p>
        {tr(
          "Upload UTF-8 CSV or a single-sheet XLSX workbook, up to 200 rows. Existing products are never overwritten. All rows succeed together or no products are added.",
        )}
      </p>
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
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={busy}
          onChange={(e) => load(e.target.files?.[0])}
        />
      </label>
      <label className="field">
        {tr("CSV contents")}
        <textarea
          rows={8}
          value={text}
          disabled={busy}
          onChange={(e) => {
            setText(e.target.value);
            setPreview(null);
            setNotice("");
          }}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
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
          <p>
            {tr(
              "Preview does not reserve SKUs. All rules are checked again when importing.",
            )}
          </p>
          <button className="primary" disabled={busy} onClick={() => run(true)}>
            {tr("Import validated products")}
          </button>
        </>
      )}
    </section>
  );
}
