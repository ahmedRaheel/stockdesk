import { useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import { t as tr } from "./i18n";
import PurchaseLookup, { PurchaseOption } from "./PurchaseLookup";

export default function CatalogTools({
  tenant,
  canProduct,
  canStock,
  money,
  onChanged,
}: {
  tenant: string;
  canProduct: boolean;
  canStock: boolean;
  money: (n: number) => string;
  onChanged: () => Promise<void>;
}) {
  const base = `/api/v1/tenants/${tenant}/catalog-tools`;
  const [tab, setTab] = useState(canProduct ? "families" : "recipes"),
    [items, setItems] = useState<any[]>([]),
    [q, setQ] = useState(""),
    [offset, setOffset] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [familyName, setFamilyName] = useState(""),
    [axes, setAxes] = useState("size,color"),
    [family, setFamily] = useState<any>(),
    [variants, setVariants] = useState<any[]>([]),
    [variantOffset, setVariantOffset] = useState(0),
    [variantProduct, setVariantProduct] = useState<PurchaseOption>(),
    [attributes, setAttributes] = useState<Record<string, string>>({}),
    [variantVersion, setVariantVersion] = useState<number>();
  const [recipe, setRecipe] = useState<any>(),
    [recipeName, setRecipeName] = useState(""),
    [kind, setKind] = useState("bom"),
    [output, setOutput] = useState<PurchaseOption>(),
    [component, setComponent] = useState<PurchaseOption>(),
    [components, setComponents] = useState<any[]>([]),
    [active, setActive] = useState(true),
    [job, setJob] = useState<any>({
      direction: "build",
      quantity: "1",
      lot: "",
      expires: "",
      note: "",
    }),
    [quote, setQuote] = useState<any>(),
    [posted, setPosted] = useState<any>();
  const pending = useRef<Record<string, { signature: string; id: string }>>({});
  function requestId(key: string, body: any) {
    const signature = JSON.stringify(body);
    if (pending.current[key]?.signature !== signature)
      pending.current[key] = { signature, id: newRequestId() };
    return pending.current[key].id;
  }
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function load() {
    const result = await api<any>(
      `${base}/${tab}?offset=${offset}&q=${encodeURIComponent(q)}`,
    );
    setItems(result.items);
  }
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      api<any>(`${base}/${tab}?offset=${offset}&q=${encodeURIComponent(q)}`)
        .then((r) => {
          if (live) setItems(r.items);
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    }, 200);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [tenant, tab, q, offset]);
  useEffect(() => {
    let live = true;
    setVariantVersion(undefined);
    if (!variantProduct) return;
    api<any>(`${base}/variants/${variantProduct.id}`)
      .then((r) => {
        if (!live) return;
        setVariantVersion(r.version);
        if (r.assignment?.family === family?.id)
          setAttributes(r.assignment.attributes);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [variantProduct?.id, family?.id, tenant]);
  async function openFamily(id: string, start = 0) {
    const r = await api<any>(`${base}/families/${id}?offset=${start}`);
    setFamily(r.family);
    setVariants(r.items);
    setVariantOffset(start);
    setVariantProduct(undefined);
    setAttributes({});
  }
  function newRecipe() {
    setRecipe(undefined);
    setRecipeName("");
    setKind("bom");
    setOutput(undefined);
    setComponents([]);
    setComponent(undefined);
    setActive(true);
    setQuote(undefined);
    setPosted(undefined);
  }
  async function openRecipe(id: string) {
    const r = await api<any>(`${base}/recipes/${id}`);
    setRecipe(r);
    setRecipeName(r.name);
    setKind(r.kind);
    setOutput({ id: r.output, name: r.output_name, sku: r.output_sku });
    setComponents(r.components.map((c: any) => ({ ...c, id: c.product })));
    setActive(r.active);
    setQuote(undefined);
    setPosted(undefined);
    setJob({
      direction: "build",
      quantity: "1",
      lot: "",
      expires: "",
      note: "",
    });
  }
  const recipeBody = () => ({
    name: recipeName,
    kind,
    output: output?.id,
    active,
    components: components.map((c) => ({
      product: c.id,
      quantity: c.quantity,
    })),
  });
  const jobBody = () => ({
    ...job,
    version: recipe.version,
    expires: job.expires || null,
  });
  function editJob(key: string, value: string) {
    setJob({ ...job, [key]: value });
    setQuote(undefined);
    setPosted(undefined);
  }
  const productPicker = (
    value: PurchaseOption | undefined,
    onChange: (v: PurchaseOption | undefined) => void,
  ) => (
    <PurchaseLookup
      tenant={tenant}
      kind="products"
      value={value?.id || ""}
      selected={value}
      onChange={onChange}
      required={false}
    />
  );
  return (
    <div className="catalog-tools">
      <div className="actions">
        {canProduct && (
          <button
            disabled={busy}
            className={tab === "families" ? "primary" : "secondary"}
            onClick={() => {
              setTab("families");
              setOffset(0);
              setItems([]);
              setQ("");
            }}
          >
            {tr("Variant families")}
          </button>
        )}
        {canStock && (
          <>
            <button
              disabled={busy}
              className={tab === "recipes" ? "primary" : "secondary"}
              onClick={() => {
                setTab("recipes");
                setOffset(0);
                setItems([]);
                setQ("");
              }}
            >
              {tr("Recipes and packs")}
            </button>
            <button
              disabled={busy}
              className={tab === "jobs" ? "primary" : "secondary"}
              onClick={() => {
                setTab("jobs");
                setOffset(0);
                setItems([]);
                setQ("");
              }}
            >
              {tr("Assembly history")}
            </button>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {tr(error)}
        </p>
      )}
      {message && <p role="status">{tr(message)}</p>}
      {tab !== "jobs" && (
        <label className="field">
          {tr("Search")}
          <input
            value={q}
            maxLength={100}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      )}
      {tab === "families" && (
        <>
          <p className="hint">
            {tr(
              "Each variant is a separate catalog SKU with its own price, barcode and stock. Create the SKUs in Inventory, then assign their variant attributes here.",
            )}
          </p>
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              task(async () => {
                const body = {
                  name: familyName,
                  axes: axes.split(",").map((x) => x.trim()),
                };
                const r: any = await send(base + "/families", {
                  ...body,
                  request: requestId("family", body),
                });
                delete pending.current.family;
                setFamilyName("");
                await load();
                await onChanged();
                await openFamily(r.id);
              });
            }}
          >
            <fieldset disabled={busy}>
              <h2>{tr("Create variant family")}</h2>
              <label className="field">
                {tr("Family name")}
                <input
                  required
                  maxLength={100}
                  value={familyName}
                  onChange={(e) => setFamilyName(e.target.value)}
                />
              </label>
              <label className="field">
                {tr("Variant axes (comma separated)")}
                <input
                  required
                  value={axes}
                  onChange={(e) => setAxes(e.target.value)}
                />
              </label>
              <button className="primary">{tr("Create family")}</button>
            </fieldset>
          </form>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr("Family name")}</th>
                  <th>{tr("Variant axes")}</th>
                  <th>{tr("Variants")}</th>
                  <th>{tr("Status")}</th>
                  <th>{tr("Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((f) => (
                  <tr key={f.id}>
                    <td>{f.name}</td>
                    <td>{f.axes.join(", ")}</td>
                    <td>{f.variants}</td>
                    <td>{tr(f.active ? "Active" : "Inactive")}</td>
                    <td>
                      <button
                        className="mini"
                        disabled={busy}
                        onClick={() => task(() => openFamily(f.id))}
                      >
                        {tr("Manage")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {family && (
            <section className="panel" style={{ padding: 20, marginTop: 16 }}>
              <fieldset disabled={busy}>
                <h2>{family.name}</h2>
                <label className="field">
                  {tr("Family name")}
                  <input
                    value={family.name}
                    maxLength={100}
                    onChange={(e) =>
                      setFamily({ ...family, name: e.target.value })
                    }
                  />
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={family.active}
                    onChange={(e) =>
                      setFamily({ ...family, active: e.target.checked })
                    }
                  />
                  {tr("Active family")}
                </label>
                <p className="hint">
                  {tr(
                    "Deactivating a family prevents new assignments. Existing SKUs remain independently sellable.",
                  )}
                </p>
                <button
                  className="secondary"
                  onClick={() =>
                    task(async () => {
                      const r: any = await send(
                        `${base}/families/${family.id}`,
                        {
                          version: family.version,
                          name: family.name,
                          active: family.active,
                        },
                        "PUT",
                      );
                      setFamily({ ...family, version: r.version });
                      await load();
                      await onChanged();
                      setMessage("Saved successfully.");
                    })
                  }
                >
                  {tr("Save family")}
                </button>
                <h3>{tr("Assign variant SKU")}</h3>
                {productPicker(variantProduct, setVariantProduct)}
                {family.axes.map((axis: string) => (
                  <label className="field" key={axis}>
                    {axis}
                    <input
                      aria-label={`${tr("Attribute")} ${axis}`}
                      maxLength={100}
                      value={attributes[axis] || ""}
                      onChange={(e) =>
                        setAttributes({ ...attributes, [axis]: e.target.value })
                      }
                    />
                  </label>
                ))}
                <button
                  className="primary"
                  disabled={
                    !family.active ||
                    !variantProduct ||
                    variantVersion === undefined ||
                    family.axes.some((x: string) => !attributes[x]?.trim())
                  }
                  onClick={() =>
                    task(async () => {
                      await send(
                        `${base}/families/${family.id}/variants/${variantProduct!.id}`,
                        {
                          version: variantVersion,
                          attributes: Object.fromEntries(
                            family.axes.map((a: string) => [a, attributes[a]]),
                          ),
                        },
                        "PUT",
                      );
                      await openFamily(family.id, variantOffset);
                      await load();
                      await onChanged();
                      setMessage("Variant assigned.");
                    })
                  }
                >
                  {tr("Save variant")}
                </button>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr("SKU")}</th>
                        <th>{tr("Attributes")}</th>
                        <th>{tr("Price")}</th>
                        <th>{tr("Stock")}</th>
                        <th>{tr("Actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {variants.map((v) => (
                        <tr key={v.product}>
                          <td>
                            {v.sku}
                            <small>{v.name}</small>
                          </td>
                          <td>
                            {Object.entries(v.attributes)
                              .map(([k, x]) => `${k}: ${x}`)
                              .join(" · ")}
                          </td>
                          <td>{money(v.price)}</td>
                          <td>{v.stock}</td>
                          <td>
                            <button
                              className="mini"
                              onClick={() => {
                                setVariantProduct({
                                  id: v.product,
                                  name: v.name,
                                  sku: v.sku,
                                });
                                setAttributes(v.attributes);
                                setVariantVersion(v.version);
                              }}
                            >
                              {tr("Edit")}
                            </button>{" "}
                            <button
                              className="mini"
                              onClick={() =>
                                task(async () => {
                                  await api(
                                    `${base}/families/${family.id}/variants/${v.product}?version=${v.version}`,
                                    { method: "DELETE" },
                                  );
                                  await openFamily(family.id, variantOffset);
                                  await load();
                                  await onChanged();
                                })
                              }
                            >
                              {tr("Remove assignment")}
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
                    disabled={!variantOffset}
                    onClick={() =>
                      task(() => openFamily(family.id, variantOffset - 50))
                    }
                  >
                    {tr("Previous variants")}
                  </button>
                  <button
                    className="secondary"
                    disabled={variants.length < 50}
                    onClick={() =>
                      task(() => openFamily(family.id, variantOffset + 50))
                    }
                  >
                    {tr("Next variants")}
                  </button>
                </div>
              </fieldset>
            </section>
          )}
        </>
      )}
      {tab === "recipes" && (
        <>
          <p className="hint">
            {tr(
              "Build stocked output SKUs from component stock. Pack recipes also support unpacking. Quantities below are components required per one output unit; assembly never happens automatically at checkout.",
            )}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr("Recipe")}</th>
                  <th>{tr("Output SKU")}</th>
                  <th>{tr("Type")}</th>
                  <th>{tr("Status")}</th>
                  <th>{tr("Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.name}</td>
                    <td>{r.output_sku}</td>
                    <td>
                      {tr(
                        r.kind === "pack" ? "Pack conversion" : "Recipe / BOM",
                      )}
                    </td>
                    <td>{tr(r.active ? "Active" : "Inactive")}</td>
                    <td>
                      <button
                        className="mini"
                        disabled={busy}
                        onClick={() => task(() => openRecipe(r.id))}
                      >
                        {tr("Manage")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="secondary" disabled={busy} onClick={newRecipe}>
            {tr("New recipe")}
          </button>
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              task(async () => {
                const body = recipeBody();
                const r: any = await send(
                  base + "/recipes" + (recipe ? `/${recipe.id}` : ""),
                  recipe
                    ? { ...body, version: recipe.version }
                    : { ...body, request: requestId("recipe", body) },
                  recipe ? "PUT" : "POST",
                );
                delete pending.current.recipe;
                await openRecipe(recipe?.id || r.id);
                await load();
                await onChanged();
                setMessage("Recipe saved.");
              });
            }}
          >
            <fieldset disabled={busy}>
              <h2>{tr(recipe ? "Edit recipe" : "Create recipe")}</h2>
              <label className="field">
                {tr("Recipe name")}
                <input
                  required
                  maxLength={100}
                  value={recipeName}
                  onChange={(e) => setRecipeName(e.target.value)}
                />
              </label>
              <label className="field">
                {tr("Recipe type")}
                <select
                  aria-label={tr("Recipe type")}
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  <option value="bom">{tr("Recipe / BOM")}</option>
                  <option value="pack">{tr("Pack conversion")}</option>
                </select>
              </label>
              <h3>{tr("Output SKU")}</h3>
              {productPicker(output, setOutput)}
              <h3>{tr("Component SKU")}</h3>
              {productPicker(component, setComponent)}
              <button
                className="secondary"
                type="button"
                disabled={
                  !component || components.some((c) => c.id === component.id)
                }
                onClick={() => {
                  setComponents([
                    ...components,
                    { ...component, quantity: "1" },
                  ]);
                  setComponent(undefined);
                }}
              >
                {tr("Add component")}
              </button>
              {components.map((c, i) => (
                <div className="cart-math" key={c.id}>
                  <span>
                    {c.sku} · {c.name}
                  </span>
                  <input
                    aria-label={`${tr("Component quantity")} ${c.name}`}
                    type="number"
                    required
                    min="0.001"
                    max="1000000"
                    step="0.001"
                    value={c.quantity}
                    onChange={(e) =>
                      setComponents(
                        components.map((x, j) =>
                          i === j ? { ...x, quantity: e.target.value } : x,
                        ),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="mini"
                    onClick={() =>
                      setComponents(components.filter((_, j) => j !== i))
                    }
                  >
                    {tr("Remove")}
                  </button>
                </div>
              ))}
              <label className="check">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(e) => setActive(e.target.checked)}
                />
                {tr("Active recipe")}
              </label>
              <p className="hint">
                {tr(
                  "After the first posted job, the output, type and component ratios cannot change. Use a new output SKU and recipe for a different conversion.",
                )}
              </p>
              <button
                className="primary"
                disabled={!output || !components.length}
              >
                {tr("Save recipe")}
              </button>
            </fieldset>
          </form>
          {recipe && (
            <section className="panel" style={{ padding: 20, marginTop: 16 }}>
              <fieldset disabled={busy}>
                <h2>{tr("Post assembly or conversion")}</h2>
                <p>
                  {recipe.name} · {tr("Version")}: {recipe.version}
                </p>
                <label className="field">
                  {tr("Direction")}
                  <select
                    aria-label={tr("Direction")}
                    value={job.direction}
                    onChange={(e) => editJob("direction", e.target.value)}
                  >
                    <option value="build">{tr("Build / pack")}</option>
                    {recipe.kind === "pack" && (
                      <option value="unpack">{tr("Unpack")}</option>
                    )}
                  </select>
                </label>
                <label className="field">
                  {tr("Output units / packs")}
                  <input
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={job.quantity}
                    onChange={(e) => editJob("quantity", e.target.value)}
                  />
                </label>
                <label className="field">
                  {tr("Output lot")}
                  <input
                    maxLength={80}
                    value={job.lot}
                    onChange={(e) => editJob("lot", e.target.value)}
                  />
                </label>
                <label className="field">
                  {tr("Output expiry")}
                  <input
                    type="date"
                    value={job.expires}
                    onChange={(e) => editJob("expires", e.target.value)}
                  />
                </label>
                <label className="field">
                  {tr("Production note")}
                  <input
                    maxLength={500}
                    value={job.note}
                    onChange={(e) => editJob("note", e.target.value)}
                  />
                </label>
                <p className="hint">
                  {tr(
                    "Only non-expired inputs are used. Output expiry cannot exceed the earliest consumed expiry. Review the saved recipe before posting; unsaved form edits are not used.",
                  )}
                </p>
                <button
                  className="secondary"
                  disabled={
                    !recipe.active || !job.lot.trim() || !job.note.trim()
                  }
                  onClick={() =>
                    task(async () => {
                      setQuote(undefined);
                      setPosted(undefined);
                      setQuote(
                        await send(
                          `${base}/recipes/${recipe.id}/preview`,
                          jobBody(),
                        ),
                      );
                    })
                  }
                >
                  {tr("Preview assembly")}
                </button>
                {quote && !posted && (
                  <>
                    <h3>{tr("Inputs consumed")}</h3>
                    {quote.inputs.map((x: any) => (
                      <p key={x.product}>
                        {x.sku} × {x.quantity}
                        <small>
                          {x.batches
                            .map(
                              (b: any) =>
                                `${b.lot}: ${b.quantity}${b.expires ? ` (${b.expires})` : ""}`,
                            )
                            .join(" · ")}
                        </small>
                      </p>
                    ))}
                    <h3>{tr("Outputs created")}</h3>
                    {quote.outputs.map((x: any) => (
                      <p key={x.product}>
                        {x.sku} × {x.quantity}
                      </p>
                    ))}
                    <p>
                      {tr("Input cost at current catalog prices")}:{" "}
                      {money(quote.input_catalog_cost)}
                    </p>
                    <p className="hint">
                      {tr(
                        "This is a cost estimate, not receipt-layer valuation. Output catalog costs are not changed automatically.",
                      )}
                    </p>
                    <button
                      className="primary"
                      onClick={() =>
                        task(async () => {
                          const body = {
                            ...jobBody(),
                            quote_token: quote.quote_token,
                          };
                          setPosted(
                            await send(`${base}/recipes/${recipe.id}/jobs`, {
                              ...body,
                              request: requestId("job", body),
                            }),
                          );
                          delete pending.current.job;
                          await onChanged();
                          setMessage("Assembly posted. Stock reconciled.");
                        })
                      }
                    >
                      {tr("Confirm assembly")}
                    </button>
                  </>
                )}
                {posted && (
                  <p role="status">
                    {tr("Assembly reference")}: {posted.id}
                  </p>
                )}
              </fieldset>
            </section>
          )}
        </>
      )}
      {tab === "jobs" &&
        items.map((j) => (
          <section
            className="panel"
            key={j.id}
            style={{ padding: 20, marginTop: 16 }}
          >
            <h3>
              {j.name} ·{" "}
              {tr(j.direction === "build" ? "Build / pack" : "Unpack")}
            </h3>
            <p>
              <bdi>{new Date(j.created).toLocaleString()}</bdi> ·{" "}
              <bdi>{j.actor}</bdi>
            </p>
            <p>
              {tr("Assembly reference")}: {j.id}
            </p>
            <p>
              {tr("Output lot")}: {j.lot} · {j.expires}
            </p>
            <p>{j.note}</p>
            <h4>{tr("Inputs consumed")}</h4>
            {j.inputs.map((x: any) => (
              <p key={x.product}>
                {x.sku} × {x.quantity}
                <small>
                  {x.batches
                    .map((b: any) => `${b.lot}: ${b.quantity}`)
                    .join(" · ")}
                </small>
              </p>
            ))}
            <h4>{tr("Outputs created")}</h4>
            {j.outputs.map((x: any) => (
              <p key={x.product}>
                {x.sku} × {x.quantity}
              </p>
            ))}
          </section>
        ))}
      <div className="actions">
        <button
          className="secondary"
          disabled={!offset || busy}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          {tr("Previous")}
        </button>
        <button
          className="secondary"
          disabled={items.length < 50 || busy}
          onClick={() => setOffset(offset + 50)}
        >
          {tr("Next")}
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => task(load)}
        >
          {tr("Refresh")}
        </button>
      </div>
    </div>
  );
}
