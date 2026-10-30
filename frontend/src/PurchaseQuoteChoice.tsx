import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";
import "./supplier-prices.css";
export type QuoteSelection = { id: string; version: number };
type Price = {
  id: string;
  version: number;
  effective_unit_cost: number;
  applied_minimum_quantity: number;
  estimated_total: number;
};
export default function PurchaseQuoteChoice({
  tenant,
  supplier,
  product,
  quantity,
  currency,
  selected,
  onApply,
}: {
  tenant: string;
  supplier: string;
  product: string;
  quantity: number;
  currency: string;
  selected?: QuoteSelection;
  onApply: (cost: number, quote: QuoteSelection) => void;
}) {
  const [quote, setQuote] = useState<Price>();
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setQuote(undefined);
    setError("");
    if (!supplier || !product || !(quantity > 0) || quantity > 1000000) {
      setLoading(false);
      return () => controller.abort();
    }
    setLoading(true);
    const timer = setTimeout(() => {
      api<{ items: Price[] }>(
        `/api/v1/tenants/${tenant}/supplier-offers?supplier=${encodeURIComponent(supplier)}&product=${encodeURIComponent(product)}&quantity=${quantity}&eligible=true`,
        { signal: controller.signal },
      )
        .then((r) => {
          if (!controller.signal.aborted) setQuote(r.items[0]);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [tenant, supplier, product, quantity]);
  const money = (n: number) =>
    new Intl.NumberFormat("en", { style: "currency", currency }).format(
      n / 100,
    );
  if (!supplier || !product) return null;
  return (
    <div className="purchase-quote-choice" aria-live="polite">
      {loading ? (
        <span>{tr("Checking quantity price…")}</span>
      ) : error ? (
        <span role="alert">{tr(error)}</span>
      ) : quote ? (
        <>
          <span>
            <strong>{money(quote.effective_unit_cost)}</strong> ·{" "}
            {tr("From quantity")}: {quote.applied_minimum_quantity} ·{" "}
            {tr("Estimated total")}: {money(quote.estimated_total)}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={
              selected?.id === quote.id && selected?.version === quote.version
            }
            onClick={() =>
              onApply(quote.effective_unit_cost, {
                id: quote.id,
                version: quote.version,
              })
            }
          >
            {tr(
              selected?.id === quote.id && selected?.version === quote.version
                ? "Quoted price selected"
                : "Use quoted price",
            )}
          </button>
        </>
      ) : (
        <span>
          {tr(
            "No eligible quote for this supplier and quantity. Enter an agreed cost manually.",
          )}
        </span>
      )}
      {selected && (
        <small>
          {tr("Quote revision")}: {selected.version}.{" "}
          {tr("Changing quantity or cost clears the quote selection.")}
        </small>
      )}
    </div>
  );
}
