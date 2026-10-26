import { useEffect, useState } from "react";
import { api, send } from "./api";
import { t as tr, useLanguage } from "./i18n";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";

type Part = { product: string; quantity: string; name: string; sku?: string };
export default function Promotions({
  tenant,
  currency,
}: {
  tenant: string;
  currency: string;
}) {
  const [language] = useLanguage();
  const [data, setData] = useState<any>(null),
    [q, setQ] = useState(""),
    [page, setPage] = useState(0);
  const [selected, setSelected] = useState<any>(null),
    [kind, setKind] = useState("percentage");
  const [parts, setParts] = useState<Part[]>([]),
    [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const base = `/api/v1/tenants/${tenant}/promotions`;
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    const timer = setTimeout(
      () =>
        api<any>(
          `${base}?include_inactive=true&q=${encodeURIComponent(q)}&offset=${page * 50}`,
          { signal: c.signal },
        )
          .then(setData)
          .catch((e) => {
            if (e.name !== "AbortError") setError(e.message);
          }),
      200,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [base, q, page, revision]);
  const isBogo = kind === "bogo" || kind === "cross_bogo";
  function edit(row: any) {
    setSelected(row);
    setKind(row?.kind || "percentage");
    setParts(
      [...(row?.components || [])]
        .sort((a: any, b: any) =>
          row?.kind === "cross_bogo"
            ? Number(a.product === row.reward_product) -
              Number(b.product === row.reward_product)
            : 0,
        )
        .map((p: any) => ({
          ...p,
          quantity: String(p.quantity),
        })),
    );
    setError("");
    setNotice("");
  }
  function changeKind(value: string) {
    setKind(value);
    setParts(
      value === "bogo"
        ? [{ product: "", quantity: "1", name: "" }]
        : value === "bundle" || value === "cross_bogo"
          ? [
              { product: "", quantity: "1", name: "" },
              { product: "", quantity: "1", name: "" },
            ]
          : [],
    );
  }
  const time = (n: number | null | undefined) =>
    n == null
      ? ""
      : `${String(Math.floor(n / 60) % 24).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const text = (k: string) => String(f.get(k) || "");
    const amount = (k: string) => Math.round(Number(text(k)) * 100);
    const minute = (k: string, end = false) => {
      if (!text(k)) return null;
      const [h, m] = text(k).split(":").map(Number);
      return end && h === 0 && m === 0 ? 1440 : h * 60 + m;
    };
    const payload = {
      code: text("code").trim().toUpperCase(),
      name: text("name"),
      name_ur: text("name_ur"),
      kind,
      reward_product: kind === "cross_bogo" ? parts[1]?.product || null : null,
      value: isBogo ? 0 : amount("value"),
      minimum_subtotal: amount("minimum_subtotal"),
      maximum_discount: text("maximum_discount")
        ? amount("maximum_discount")
        : null,
      buy_quantity: isBogo ? Number(text("buy_quantity")) : 1,
      free_quantity: isBogo ? Number(text("free_quantity")) : 1,
      weekdays: f.getAll("weekdays").map(Number),
      starts_on: text("starts_on") || null,
      ends_on: text("ends_on") || null,
      starts_minute: minute("starts_minute"),
      ends_minute: minute("ends_minute", true),
      usage_limit: text("usage_limit") ? Number(text("usage_limit")) : null,
      per_customer_limit: text("per_customer_limit")
        ? Number(text("per_customer_limit"))
        : null,
      active: f.has("active"),
      components: parts.map((p) => ({
        product: p.product,
        quantity: isBogo ? "1" : p.quantity,
      })),
      ...(selected ? { version: selected.version } : {}),
    };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await send(
        base + (selected ? "/" + selected.id : ""),
        payload,
        selected ? "PUT" : "POST",
      );
      edit(null);
      setRevision((v) => v + 1);
      setNotice(tr("Promotion saved."));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const field = (
    label: string,
    name: string,
    type = "text",
    value: any = "",
    extra: any = {},
  ) => (
    <label className="field" key={name === "value" ? kind : name}>
      <span>{tr(label)}</span>
      <input
        name={name}
        aria-label={tr(label)}
        type={type}
        defaultValue={value ?? ""}
        {...extra}
      />
    </label>
  );
  return (
    <>
      <section className="panel">
        <h2>{tr(selected ? "Edit promotion" : "New promotion")}</h2>
        <p>
          {tr(
            "One promotion per sale. Manual discounts cannot be combined. Cashiers select or enter a code; eligibility and usage are checked again at checkout.",
          )}
        </p>
        <form key={`${selected?.id || "new"}-${revision}`} onSubmit={save}>
          <fieldset
            disabled={busy}
            style={{ border: 0, padding: 0, margin: 0 }}
          >
            <div className="form-grid">
              {field("Promotion code", "code", "text", selected?.code, {
                required: true,
                maxLength: 40,
                pattern: "[A-Za-z0-9_\\-]+",
                readOnly: !!selected,
              })}
              {field("Promotion name", "name", "text", selected?.name, {
                required: true,
                maxLength: 150,
              })}
              {field("Urdu name", "name_ur", "text", selected?.name_ur, {
                maxLength: 150,
              })}
              <label className="field">
                <span>{tr("Promotion type")}</span>
                <select
                  aria-label={tr("Promotion type")}
                  value={kind}
                  onChange={(e) => changeKind(e.target.value)}
                >
                  <option value="percentage">{tr("Percentage coupon")}</option>
                  <option value="fixed">{tr("Fixed coupon")}</option>
                  <option value="bogo">{tr("Buy X get Y free")}</option>
                  <option value="cross_bogo">
                    {tr("Buy one product, get another free")}
                  </option>
                  <option value="bundle">{tr("Bundle price")}</option>
                </select>
              </label>
              {!isBogo &&
                field(
                  kind === "percentage"
                    ? "Percentage (%)"
                    : kind === "bundle"
                      ? "Bundle price"
                      : "Discount amount",
                  "value",
                  "number",
                  selected?.kind === kind ? selected.value / 100 : 0,
                  {
                    required: true,
                    min: kind === "bundle" ? 0 : 0.01,
                    max: kind === "percentage" ? 100 : 1000000000,
                    step: 0.01,
                  },
                )}
              {isBogo && (
                <>
                  {field(
                    "Buy quantity",
                    "buy_quantity",
                    "number",
                    selected?.buy_quantity || 1,
                    { required: true, min: 1, max: 1000000, step: 1 },
                  )}
                  {field(
                    "Free quantity",
                    "free_quantity",
                    "number",
                    selected?.free_quantity || 1,
                    { required: true, min: 1, max: 1000000, step: 1 },
                  )}
                </>
              )}
              {field(
                "Minimum subtotal",
                "minimum_subtotal",
                "number",
                (selected?.minimum_subtotal || 0) / 100,
                { required: true, min: 0, max: 1000000000, step: 0.01 },
              )}
              {field(
                "Maximum discount (optional)",
                "maximum_discount",
                "number",
                selected?.maximum_discount
                  ? selected.maximum_discount / 100
                  : "",
                { min: 0.01, max: 1000000000, step: 0.01 },
              )}
              {field("Start date", "starts_on", "date", selected?.starts_on)}
              {field("End date", "ends_on", "date", selected?.ends_on)}
              {field(
                "Daily start time",
                "starts_minute",
                "time",
                time(selected?.starts_minute),
              )}
              {field(
                "Daily end time (exclusive)",
                "ends_minute",
                "time",
                time(selected?.ends_minute),
              )}
              {field(
                "Total redemption limit (optional)",
                "usage_limit",
                "number",
                selected?.usage_limit,
                { min: 1, max: 1000000000, step: 1 },
              )}
              {field(
                "Per-customer redemption limit (optional)",
                "per_customer_limit",
                "number",
                selected?.per_customer_limit,
                { min: 1, max: 1000000000, step: 1 },
              )}
              <label className="check">
                <input
                  name="active"
                  type="checkbox"
                  defaultChecked={selected?.active ?? true}
                />
                {tr("Active promotion")}
              </label>
            </div>
            <p className="hint">
              {tr(
                "Limited offers require a registered customer. Returns do not restore redemptions; leave blank for no per-customer cap.",
              )}
            </p>
            <fieldset
              style={{
                border: "1px solid #dbe2ea",
                padding: 12,
                marginBlock: 12,
              }}
            >
              <legend>{tr("Active weekdays")}</legend>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {[
                  "Monday",
                  "Tuesday",
                  "Wednesday",
                  "Thursday",
                  "Friday",
                  "Saturday",
                  "Sunday",
                ].map((day, index) => (
                  <label className="check" key={day}>
                    <input
                      type="checkbox"
                      name="weekdays"
                      value={index}
                      defaultChecked={
                        selected?.weekdays
                          ? selected.weekdays.includes(index)
                          : true
                      }
                    />
                    {tr(day)}
                  </label>
                ))}
              </div>
            </fieldset>
            <p className="hint">
              {tr(
                "If end time is earlier than start time, the offer continues after midnight. Weekdays and effective dates refer to the start of that window.",
              )}
            </p>
            <p>
              {currency} ·{" "}
              {tr(
                "Dates and daily times use Asia/Karachi. End date is inclusive; end time is exclusive. End time 00:00 means the end of that day. Leave both times empty for all day.",
              )}
            </p>
            {(isBogo || kind === "bundle") && (
              <>
                <h3>{tr("Promotion products")}</h3>
                {kind === "cross_bogo" && (
                  <p className="hint">
                    {tr(
                      "Only reward units already in the cart are discounted. Extra reward units remain paid. Qualifying and reward products must be distinct whole-unit products.",
                    )}
                  </p>
                )}
                <p>
                  {tr(
                    "Add all required products, including free units, to the cart. BOGO accepts whole-unit products. Bundle quantities follow the product unit.",
                  )}
                </p>
                {parts.map((part, i) => (
                  <div className="form-grid" key={i}>
                    {kind === "cross_bogo" && (
                      <h4 style={{ gridColumn: "1 / -1" }}>
                        {tr(
                          i === 0
                            ? "Qualifying product (buy)"
                            : "Reward product (free)",
                        )}
                      </h4>
                    )}
                    <PurchaseLookup
                      tenant={tenant}
                      kind="products"
                      value={part.product}
                      selected={
                        part.product
                          ? { id: part.product, name: part.name, sku: part.sku }
                          : undefined
                      }
                      onChange={(p: PurchaseOption | undefined) =>
                        setParts((ps) =>
                          ps.map((v, j) =>
                            j === i
                              ? {
                                  ...v,
                                  product: p?.id || "",
                                  name: p?.name || "",
                                  sku: p?.sku,
                                }
                              : v,
                          ),
                        )
                      }
                    />
                    {kind === "bundle" && (
                      <label className="field">
                        {tr("Quantity per bundle")}
                        <input
                          required
                          type="number"
                          min="0.001"
                          max="1000000"
                          step="0.001"
                          value={part.quantity}
                          onChange={(e) =>
                            setParts((ps) =>
                              ps.map((p, j) =>
                                i === j
                                  ? { ...p, quantity: e.target.value }
                                  : p,
                              ),
                            )
                          }
                        />
                      </label>
                    )}
                    {kind === "bundle" && (
                      <button
                        type="button"
                        className="secondary"
                        disabled={parts.length <= 2}
                        onClick={() =>
                          setParts((ps) => ps.filter((_, j) => i !== j))
                        }
                      >
                        {tr("Remove product")}
                      </button>
                    )}
                  </div>
                ))}
                {kind === "bundle" && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={parts.length >= 20}
                    onClick={() =>
                      setParts((ps) => [
                        ...ps,
                        { product: "", name: "", quantity: "1" },
                      ])
                    }
                  >
                    {tr("Add product")}
                  </button>
                )}
              </>
            )}
            <div className="actions">
              <button className="primary" type="submit">
                {tr("Save promotion")}
              </button>
              {selected && (
                <button
                  className="secondary"
                  type="button"
                  onClick={() => edit(null)}
                >
                  {tr("Cancel edit")}
                </button>
              )}
            </div>
          </fieldset>
        </form>
        {error && (
          <p className="form-error" role="alert">
            {tr(error)}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
      </section>
      <section className="panel">
        <h2>{tr("Promotions and coupons")}</h2>
        <label className="field">
          {tr("Search promotions")}
          <input
            value={q}
            maxLength={100}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </label>
        {!data ? (
          <p>{tr("Loading…")}</p>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      "Code",
                      "Name",
                      "Promotion type",
                      "Active",
                      "Redemptions",
                      "Version",
                      "Actions",
                    ].map((x) => (
                      <th key={x}>{tr(x)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p: any) => (
                    <tr key={p.id}>
                      <td>{p.code}</td>
                      <td>
                        {language === "ur" ? p.name_ur || p.name : p.name}
                      </td>
                      <td>
                        {tr(
                          (
                            {
                              percentage: "Percentage coupon",
                              fixed: "Fixed coupon",
                              bogo: "Buy X get Y free",
                              cross_bogo: "Buy one product, get another free",
                              bundle: "Bundle price",
                            } as any
                          )[p.kind],
                        )}
                      </td>
                      <td>{tr(p.active ? "Yes" : "No")}</td>
                      <td>
                        {p.used} / {p.usage_limit ?? "∞"}
                      </td>
                      <td>{p.version}</td>
                      <td>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => edit(p)}
                        >
                          {tr("Edit")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="actions">
              <button
                className="secondary"
                disabled={!page}
                onClick={() => setPage((v) => v - 1)}
              >
                {tr("Previous")}
              </button>
              <span>
                {data.total ? page * 50 + 1 : 0}–
                {Math.min((page + 1) * 50, data.total)} / {data.total}
              </span>
              <button
                className="secondary"
                disabled={(page + 1) * 50 >= data.total}
                onClick={() => setPage((v) => v + 1)}
              >
                {tr("Next")}
              </button>
            </div>
          </>
        )}
      </section>
    </>
  );
}

export function PromotionPicker({
  tenant,
  value,
  onChange,
  disabled,
}: {
  tenant: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const [items, setItems] = useState<any[]>([]),
    [error, setError] = useState("");
  const [language] = useLanguage();
  useEffect(() => {
    const c = new AbortController();
    const timer = setTimeout(
      () =>
        api<any>(
          `/api/v1/tenants/${tenant}/promotions?q=${encodeURIComponent(value)}`,
          { signal: c.signal },
        )
          .then((r) => {
            setItems(r.items);
            setError("");
          })
          .catch((e) => {
            if (e.name !== "AbortError") setError(e.message);
          }),
      200,
    );
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, value]);
  return (
    <label className="field">
      <span>{tr("Promotion / coupon code")}</span>
      <input
        aria-label={tr("Promotion / coupon code")}
        list="pos-promotion-codes"
        value={value}
        maxLength={40}
        disabled={disabled}
        placeholder={tr("Optional promotion code")}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
      />
      <datalist id="pos-promotion-codes">
        {items.map((p) => (
          <option key={p.id} value={p.code}>
            {language === "ur" ? p.name_ur || p.name : p.name}
          </option>
        ))}
      </datalist>
      {error && <small role="alert">{tr(error)}</small>}
    </label>
  );
}
