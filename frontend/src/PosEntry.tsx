import CameraScanner from "./CameraScanner";
import { useEffect, useRef, useState } from "react";
import { ScanBarcode, Keyboard, Plus } from "lucide-react";
import { t as tr } from "./i18n";
export type EntryProduct = {
  id: string;
  sku: string;
  barcode?: string | null;
  name: string;
  active: boolean;
  stock: number;
};
/** Scanners operate as keyboards with Enter suffix. No timing heuristics or global key capture. */
export default function PosEntry({
  products,
  busy,
  onAdd,
}: {
  products: EntryProduct[];
  busy: boolean;
  onAdd: (p: EntryProduct, quantity: number) => boolean;
}) {
  const [mode, setMode] = useState<"scanner" | "manual">(() =>
    localStorage.getItem("stockdesk-pos-entry") === "manual"
      ? "manual"
      : "scanner",
  );
  const [code, setCode] = useState(""),
    [quantity, setQuantity] = useState("1"),
    [message, setMessage] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const [camera, setCamera] = useState(false);
  useEffect(() => {
    if (busy) setCamera(false);
  }, [busy]);
  useEffect(() => {
    localStorage.setItem("stockdesk-pos-entry", mode);
    setCode("");
    setMessage("");
    input.current?.focus();
  }, [mode]);
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const exact = code.trim();
    const qty = Number(quantity);
    if (!exact) return;
    if (
      !Number.isFinite(qty) ||
      qty <= 0 ||
      Math.abs(qty * 1000 - Math.round(qty * 1000)) > 1e-7
    ) {
      setMessage(tr("Enter a positive quantity with up to three decimals."));
      return;
    }
    const product = products.find(
      (p) =>
        p.active &&
        (p.sku.toLocaleLowerCase() === exact.toLocaleLowerCase() ||
          p.barcode?.toLocaleLowerCase() === exact.toLocaleLowerCase()),
    );
    if (!product) {
      setMessage(
        tr("Barcode or SKU not found. Search the catalog or correct the code."),
      );
      input.current?.select();
      return;
    }
    if (!onAdd(product, qty)) {
      setMessage(tr("Requested quantity exceeds available stock."));
      input.current?.select();
      return;
    }
    setMessage(tr("Added to order") + ": " + product.name + " × " + qty);
    setCode("");
    input.current?.focus();
  }
  return (
    <section className="panel pos-entry">
      <div
        className="entry-tabs"
        role="group"
        aria-label={tr("Product entry mode")}
      >
        <button
          type="button"
          aria-pressed={mode === "scanner"}
          className={mode === "scanner" ? "selected" : ""}
          onClick={() => setMode("scanner")}
        >
          <ScanBarcode size={17} />
          {tr("Barcode reader")}
        </button>
        <button
          type="button"
          aria-pressed={mode === "manual"}
          className={mode === "manual" ? "selected" : ""}
          onClick={() => setMode("manual")}
        >
          <Keyboard size={17} />
          {tr("Manual entry")}
        </button>
      </div>
      <button
        type="button"
        className="secondary"
        disabled={busy || camera}
        onClick={() => setCamera(true)}
      >
        {tr("Scan with camera")}
      </button>
      {camera && (
        <CameraScanner
          onClose={() => setCamera(false)}
          onCode={(value) => {
            setCode(value);
            setCamera(false);
            setMessage(tr("Code scanned. Review quantity and add to bill."));
            input.current?.focus();
          }}
        />
      )}
      <form onSubmit={submit}>
        <div className="entry-fields">
          <label className="field">
            <span>
              {mode === "scanner" ? tr("Scan barcode") : tr("Barcode / SKU")}
            </span>
            <input
              ref={input}
              data-pos-search
              aria-label={tr("Barcode / SKU")}
              value={code}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              maxLength={100}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.repeat) e.preventDefault();
              }}
              placeholder={
                mode === "scanner"
                  ? tr("Scan here; reader must send Enter")
                  : tr("Type barcode or SKU")
              }
            />
          </label>
          <label className="field">
            <span>{tr("Quantity")}</span>
            <input
              aria-label={tr("Entry quantity")}
              type="number"
              min="0.001"
              max="1000000"
              step="0.001"
              required
              disabled={busy}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || !code.trim()}>
            <Plus size={16} />
            {tr("Add to bill")}
          </button>
        </div>
      </form>
      <p className="hint">
        {mode === "scanner"
          ? tr(
              "USB or Bluetooth keyboard-mode readers are supported. F2 returns focus here.",
            )
          : tr("Enter an exact code, or search below and select a product.")}
      </p>
      <p role="status" aria-live="polite" className="entry-status">
        {message}
      </p>
    </section>
  );
}
