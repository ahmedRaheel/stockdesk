"use client";
import { useEffect, useState, useRef } from "react";
import {
  LayoutDashboard,
  Package,
  ShoppingCart,
  ArrowLeftRight,
  Receipt,
  Users,
  Building2,
  Settings,
  Plus,
  Search,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  Check,
  ShieldCheck,
  LogOut,
  X,
  Minus,
  Trash2,
  Printer,
  Download,
  AlertTriangle,
  Boxes,
  History,
  SlidersHorizontal,
  Loader2,
} from "lucide-react";
import { ROLES, permissions } from "./rules";
import PlotlyChart from "./PlotlyChart";
import Forecasts from "./Forecasts";
import Purchasing from "./Purchasing";
import { send } from "./api";
const titles: any = {
  purchasing: ["Purchasing", "Supplier orders and goods receiving."],
  forecasts: [
    "Sales forecasts & insights",
    "See what sells, what may run out, and what to replenish.",
  ],
  dashboard: [
    "Business overview",
    "Sales performance, inventory exposure, and stock exceptions.",
  ],
  products: [
    "Product inventory",
    "Manage your catalog, pricing, and stock thresholds.",
  ],
  pos: ["Point of sale", "A faster checkout, with stock that stays in sync."],
  sales: ["Sales & receipts", "A clear record of every sale and return."],
  movements: [
    "Stock movements",
    "Track what comes in, what goes out, and why.",
  ],
  team: ["Team & permissions", "Give the right people the right access."],
  businesses: [
    "Your businesses",
    "Separate workspaces. One connected platform.",
  ],
  settings: ["Business settings", "Business identity and invoice details."],
  audit: [
    "Activity log",
    "An accountable history of changes in this business.",
  ],
};
const icons: any = {
  purchasing: Package,
  forecasts: ArrowUpRight,
  dashboard: LayoutDashboard,
  products: Package,
  pos: ShoppingCart,
  sales: Receipt,
  movements: ArrowLeftRight,
  team: Users,
  businesses: Building2,
  settings: Settings,
  audit: History,
};
const status = (p: any) =>
  p.stock <= 0
    ? "Out of stock"
    : p.stock <= p.reorder
      ? "Low stock"
      : "In stock";
const initial: any = {
  tenants: [],
  products: [],
  sales: [],
  movements: [],
  members: [],
  audit: [],
  permissions: [],
  trend: [],
};
export default function Workspace({ onLogout }: { onLogout: () => void }) {
  const [data, setData] = useState<any>(initial),
    [tenant, setTenant] = useState(""),
    [view, setView] = useState("dashboard"),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [search, setSearch] = useState(""),
    [category, setCategory] = useState(""),
    [filter, setFilter] = useState(""),
    [modal, setModal] = useState<any>(null),
    [formError, setFormError] = useState(""),
    [cart, setCart] = useState<any[]>([]),
    [payment, setPayment] = useState("cash"),
    [customer, setCustomer] = useState(""),
    [tendered, setTendered] = useState(""),
    [receipt, setReceipt] = useState<any>(null),
    [page, setPage] = useState(0);
  const [discount, setDiscount] = useState("0"),
    [taxRate, setTaxRate] = useState("0");
  const [density, setDensity] = useState<"comfortable" | "compact">(() =>
    localStorage.getItem("stockdesk-density") === "compact"
      ? "compact"
      : "comfortable",
  );
  useEffect(() => {
    localStorage.setItem("stockdesk-density", density);
  }, [density]);
  const pending = useRef<any>(null),
    pendingMove = useRef<any>(null);
  const booted = useRef(false);
  const can = (p: string) => data.permissions.includes(p);
  const currency = data.tenant?.currency || "PKR";
  const money = (n: number) =>
    new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format((n || 0) / 100);
  const date = (s: string) =>
    new Date(s.includes("T") ? s : s + "Z").toLocaleString();
  async function load(id = tenant) {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(
        "/api/workspace" + (id ? "?tenant=" + encodeURIComponent(id) : ""),
      );
      const d = await r.json();
      if (r.status === 401) {
        onLogout();
        return;
      }
      if (!r.ok) throw Error(d.error);
      setData(d);
      if (!id && d.tenants.length) {
        const active = d.tenants.find((t: any) => t.status === "active");
        if (active) {
          setTenant(active.id);
          await load(active.id);
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (!booted.current) {
      booted.current = true;
      load("");
    }
  }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 6000);
    return () => clearTimeout(t);
  }, [toast]);
  const navigate = (v: string) => {
    setView(v);
    setSearch("");
    setCategory("");
    setFilter("");
    setPage(0);
  };
  async function switchTenant(id: string) {
    if (busy) return;
    setCart([]);
    pending.current = null;
    setTenant(id);
    setData({ ...initial, user: data.user, tenants: data.tenants });
    navigate("dashboard");
    await load(id);
  }
  async function post(action: string, payload: any) {
    const base = "/api/v1/tenants/" + encodeURIComponent(tenant);
    if (action === "product") {
      const { id, active, ...fields } = payload;
      return send(base + "/products", fields);
    }
    if (action === "editProduct") {
      const { id, initial, sku, ...fields } = payload;
      return send(base + "/products/" + encodeURIComponent(id), fields, "PUT");
    }
    if (action === "movement")
      return send(base + "/stock-adjustments", payload);
    if (action === "checkout") return send(base + "/sales", payload);
    if (action === "return") {
      const { id, ...fields } = payload;
      return send(
        base + "/sales/" + encodeURIComponent(id) + "/returns",
        fields,
      );
    }
    const r = await fetch("/api/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, tenant, ...payload }),
    });
    const d = await r.json();
    if (!r.ok) throw Error(d.error);
    return d;
  }
  function open(kind: string, item: any = null) {
    setFormError("");
    setModal({ kind, item });
  }
  async function submit(e: any) {
    e.preventDefault();
    if (busy) return;
    const f: any = Object.fromEntries(new FormData(e.target).entries());
    setBusy(true);
    setFormError("");
    try {
      let result: any;
      const kind = modal.kind;
      if (kind === "password") {
        const r = await fetch("/api/auth/password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(f),
        });
        result = await r.json();
        if (!r.ok) throw Error(result.error);
      } else if (kind === "product" || kind === "editProduct") {
        result = await post(kind, {
          ...f,
          id: modal.item?.id,
          price: Math.round(Number(f.price) * 100),
          cost: Math.round(Number(f.cost) * 100),
          initial: Number(f.initial || 0),
          reorder: Number(f.reorder),
          active: f.active === "on",
        });
      } else if (kind === "movement") {
        const payload = { ...f, quantity: Number(f.quantity) };
        const signature = JSON.stringify(payload);
        if (pendingMove.current?.signature !== signature)
          pendingMove.current = { signature, id: crypto.randomUUID() };
        result = await post(kind, {
          ...payload,
          request: pendingMove.current.id,
        });
        pendingMove.current = null;
      } else if (kind === "return")
        result = await post(kind, { id: modal.item.id, ...f });
      else result = await post(kind, f);
      setModal(null);
      setToast(
        kind === "tenant"
          ? "Business created. Welcome to your new workspace."
          : "Saved successfully.",
      );
      if (kind === "tenant") {
        setTenant(result.id);
        setCart([]);
        navigate("dashboard");
        await load(result.id);
      } else await load();
    } catch (e: any) {
      setFormError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(action: string, payload: any) {
    if (busy) return;
    setBusy(true);
    try {
      await post(action, payload);
      await load();
      setToast("Access updated.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const products = (data.products || []).filter(
    (p: any) =>
      (p.name + " " + p.sku + " " + (p.barcode || ""))
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!category || p.category === category) &&
      (!filter || (filter === "Archived" ? !p.active : status(p) === filter)),
  );
  const categories = [
    ...new Set<string>(data.products.map((p: any) => p.category)),
  ].sort();
  const subtotal = cart.reduce((s, p) => s + p.price * p.quantity, 0),
    discountCents = Math.round(Number(discount || 0) * 100),
    taxBps = Math.round(Number(taxRate || 0) * 100),
    tax = Math.floor(((subtotal - discountCents) * taxBps + 5000) / 10000),
    total = subtotal - discountCents + tax,
    units = cart.reduce((s, p) => s + p.quantity, 0);
  function add(p: any) {
    if (busy) return;
    const old = cart.find((x) => x.id === p.id);
    if ((old?.quantity || 0) >= p.stock) {
      setToast("No more stock available for " + p.name);
      return;
    }
    setCart(
      old
        ? cart.map((x) =>
            x.id === p.id ? { ...x, quantity: x.quantity + 1 } : x,
          )
        : [...cart, { ...p, quantity: 1 }],
    );
  }
  function quantity(id: string, delta: number) {
    setCart(
      cart
        .map((p) =>
          p.id === id
            ? { ...p, quantity: Math.min(p.stock, p.quantity + delta) }
            : p,
        )
        .filter((p) => p.quantity > 0),
    );
  }
  async function checkout() {
    if (!cart.length || busy) return;
    setBusy(true);
    setError("");
    const payload = {
      items: cart.map((p) => ({ id: p.id, quantity: p.quantity })),
      customer,
      payment,
      discount: discountCents,
      tax_bps: taxBps,
      expected: total,
      tendered: Math.round(Number(tendered || 0) * 100),
    };
    const signature = JSON.stringify(payload);
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: crypto.randomUUID() };
    try {
      const result = await post("checkout", {
        ...payload,
        request: pending.current.id,
      });
      setCart([]);
      setTendered("");
      setCustomer("");
      setDiscount("0");
      setTaxRate("0");
      pending.current = null;
      setToast("Sale completed. Stock updated.");
      await load();
      await showReceipt(result.id);
    } catch (e: any) {
      setError(
        e.message +
          " If the response was interrupted, retry the unchanged cart.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function showReceipt(id: string) {
    try {
      const r = await fetch(
        "/api/workspace?tenant=" +
          encodeURIComponent(tenant) +
          "&receipt=" +
          encodeURIComponent(id),
      );
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      setReceipt(d);
    } catch (e: any) {
      setError(e.message);
    }
  }
  function csv() {
    let rows: any[] = [],
      headers: string[] = [];
    if (view === "sales") {
      headers = ["Receipt", "Date", "Customer", "Payment", "Status", "Total"];
      rows = data.sales.map((s: any) => [
        s.id,
        s.created,
        s.customer,
        s.payment,
        s.status,
        s.total / 100,
      ]);
    } else {
      headers = [
        "SKU",
        "Product",
        "Category",
        "Price",
        "Cost",
        "Stock",
        "Reorder point",
      ];
      rows = products.map((p: any) => [
        p.sku,
        p.name,
        p.category,
        p.price / 100,
        p.cost / 100,
        p.stock,
        p.reorder,
      ]);
    }
    const safe = (v: any) =>
      '"' +
      String(v)
        .replace(/^[\s]*[=+@\-]/, (m) => "'" + m)
        .replaceAll('"', '""') +
      '"';
    const url = URL.createObjectURL(
      new Blob(
        [
          "\ufeff" +
            [headers, ...rows].map((r) => r.map(safe).join(",")).join("\r\n"),
        ],
        { type: "text/csv;charset=utf-8;" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `stockdesk-${view}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const nav = [
    "dashboard",
    ...(can("forecast") ? ["forecasts"] : []),
    "products",
    ...(can("sale") ? ["pos", "sales"] : []),
    "movements",
    ...(can("stock") ? ["purchasing"] : []),
    ...(can("team") ? ["team", "audit"] : []),
    "businesses",
    ...(can("settings") ? ["settings"] : []),
  ];
  const low = data.products.filter(
      (p: any) => p.active && p.stock <= p.reorder,
    ),
    value = data.products.reduce(
      (s: number, p: any) => s + p.stock * p.cost,
      0,
    );
  const active = data.products.filter((p: any) => p.active);
  const badge = (s: string) => (
    <span
      className={
        "badge " +
        (s === "Out of stock" || s === "suspended" || s === "returned"
          ? "red"
          : s === "Low stock"
            ? "amber"
            : "")
      }
    >
      {s}
    </span>
  );
  const empty = (label: string, detail: string, action?: () => void) => (
    <div className="empty">
      <div className="empty-icon">
        <Boxes size={30} />
      </div>
      <h3>{label}</h3>
      <p>{detail}</p>
      {action && (
        <button className="primary" onClick={action}>
          <Plus size={16} />
          Add your first product
        </button>
      )}
    </div>
  );
  const field = (
    label: string,
    name: string,
    type = "text",
    value: any = "",
    required = true,
  ) => (
    <label className="field">
      <span>{label}</span>
      <input
        name={name}
        type={type}
        readOnly={name === "sku" && modal?.kind === "editProduct"}
        defaultValue={value}
        required={required}
        min={type === "number" ? 0 : undefined}
        step={
          type === "number"
            ? name === "price" || name === "cost"
              ? "0.01"
              : "1"
            : undefined
        }
        maxLength={type === "text" ? 150 : undefined}
      />
    </label>
  );
  return (
    <div className={"app density-" + density}>
      <aside className="sidebar">
        <a className="brand" href="/">
          <span>
            <Boxes size={24} />
          </span>
          StockDesk<span className="saas">HQ</span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <div className="business-select">
          <Building2 size={18} />
          <select
            aria-label="Select business"
            value={tenant}
            disabled={busy || loading}
            onChange={(e) => switchTenant(e.target.value)}
          >
            <option value="">Select a business</option>
            {data.tenants
              .filter((t: any) => t.status === "active")
              .map((t: any) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
          </select>
        </div>
        <nav>
          {nav.map((v) => {
            const Icon = icons[v];
            return (
              <button
                key={v}
                title={titles[v][0]}
                aria-label={titles[v][0]}
                aria-current={view === v ? "page" : undefined}
                className={view === v ? "active" : ""}
                disabled={busy}
                onClick={() => navigate(v)}
              >
                <Icon size={18} />
                {v === "dashboard"
                  ? "Overview"
                  : v === "pos"
                    ? "Point of sale"
                    : v === "team"
                      ? "Team & roles"
                      : v === "businesses"
                        ? "Businesses"
                        : v === "audit"
                          ? "Activity log"
                          : v === "products"
                            ? "Inventory"
                            : v === "forecasts"
                              ? "Forecasts"
                              : v === "movements"
                                ? "Stock ledger"
                                : titles[v][0]}
                {v === "products" && !!low.length && (
                  <small>{low.length}</small>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="secure">
            <ShieldCheck size={17} />
            <span>Private business workspace</span>
          </div>
          <div className="profile">
            <div className="avatar">
              {(data.user?.displayName || "U").slice(0, 1).toUpperCase()}
            </div>
            <div>
              <b>{data.user?.displayName || "Connecting…"}</b>
              <small>
                {data.user?.admin ? "Super Admin" : data.role || "Member"}
              </small>
            </div>
            <button
              className="icon-button"
              onClick={onLogout}
              aria-label="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span> <b>{titles[view][0]}</b>
          </div>
          <div className="header-right">
            <button
              className="density-control"
              aria-label="Toggle table density"
              aria-pressed={density === "compact"}
              onClick={() =>
                setDensity(density === "compact" ? "comfortable" : "compact")
              }
            >
              <SlidersHorizontal size={15} />
              {density === "compact" ? "Compact" : "Comfortable"}
            </button>
            <span className="connected">
              <i />
              {loading ? "Syncing…" : "Connected"}
            </span>
            <button
              className="icon-button"
              aria-label="Change password"
              onClick={() => open("password")}
            >
              <ShieldCheck size={17} />
            </button>
            <button
              className="icon-button"
              aria-label="Refresh"
              disabled={busy || loading}
              onClick={() => load()}
            >
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
            <span className="role-chip">
              {data.user?.admin ? "Super Admin" : data.role || "Account"}
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {data.tenant?.name || "YOUR BUSINESS, ORGANIZED"}
              </div>
              <h1>{titles[view][0]}</h1>
              <p>{titles[view][1]}</p>
            </div>
            <div className="actions">
              {["dashboard", "products"].includes(view) && can("product") && (
                <button className="secondary" onClick={() => open("product")}>
                  <Plus size={16} />
                  Add product
                </button>
              )}
              {view === "dashboard" && can("sale") && (
                <button className="primary" onClick={() => navigate("pos")}>
                  <ShoppingCart size={16} />
                  Open point of sale
                </button>
              )}
              {view === "products" && (
                <button className="secondary" onClick={csv}>
                  <Download size={16} />
                  Export
                </button>
              )}
              {view === "movements" && can("stock") && (
                <button className="primary" onClick={() => open("movement")}>
                  <Plus size={16} />
                  Stock adjustment
                </button>
              )}
              {view === "team" && (
                <button className="primary" onClick={() => open("member")}>
                  <Plus size={16} />
                  Add team member
                </button>
              )}
              {view === "businesses" && data.user?.admin && (
                <button className="primary" onClick={() => open("tenant")}>
                  <Plus size={16} />
                  New business
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {toast && (
            <div className="toast" role="status">
              <Check size={17} />
              {toast}
            </div>
          )}
          {!tenant && view !== "businesses" && !loading ? (
            <div className="welcome panel">
              <span className="welcome-icon">
                <Building2 size={38} />
              </span>
              <div className="eyebrow">A FRESH START</div>
              <h2>Your business starts here.</h2>
              <p>
                Create your workspace, add your products, and make your first
                sale.
                <br />
                Your inventory and team stay organized from day one.
              </p>
              {data.user?.admin ? (
                <button className="primary" onClick={() => open("tenant")}>
                  <Plus size={17} />
                  Create a business
                </button>
              ) : (
                <p>Ask your administrator to assign you to a business.</p>
              )}
              <div className="welcome-features">
                <span>
                  <ShieldCheck />
                  Role-based access
                </span>
                <span>
                  <Package />
                  Live stock tracking
                </span>
                <span>
                  <Receipt />
                  Connected checkout
                </span>
              </div>
            </div>
          ) : (
            <>
              {view === "dashboard" && (
                <>
                  <div className="kpis">
                    {[
                      [
                        "Net sales",
                        money(data.stats?.revenue || 0),
                        "All completed sales",
                        Receipt,
                      ],
                      [
                        "Inventory value",
                        money(value),
                        "Stock at purchase cost",
                        Package,
                      ],
                      [
                        "Active products",
                        String(active.length),
                        "Products in your catalog",
                        Boxes,
                      ],
                      [
                        "Stock alerts",
                        String(low.length),
                        "Items at or below reorder point",
                        AlertTriangle,
                      ],
                    ].map(([label, val, sub, Icon]: any, i) => (
                      <div
                        key={label}
                        className={"kpi " + (i === 3 ? "warm" : "")}
                      >
                        <div>
                          <span>{label}</span>
                          <Icon size={19} />
                        </div>
                        <strong>{val}</strong>
                        <small>
                          {sub}
                          {i === 3 && low.length > 0 && (
                            <button
                              onClick={() => {
                                navigate("products");
                                setFilter("Low stock");
                              }}
                            >
                              Review <ArrowUpRight size={13} />
                            </button>
                          )}
                        </small>
                      </div>
                    ))}
                  </div>
                  <div className="dashboard-grid">
                    <section className="panel revenue">
                      <div className="panel-heading">
                        <div>
                          <h2>Sales performance</h2>
                          <p>Completed sales over the last 7 days · UTC</p>
                        </div>
                        <span className="subtle-tag">Last 7 days</span>
                      </div>
                      <div className="chart-total">
                        {money(
                          (data.trend || []).reduce(
                            (s: number, r: any) => s + r.total,
                            0,
                          ),
                        )}
                        <span>total revenue</span>
                      </div>
                      {data.salesChart && (
                        <PlotlyChart figure={data.salesChart} />
                      )}
                      {!can("sale") && (
                        <p className="muted">
                          Sales reporting is restricted to sales roles.
                        </p>
                      )}
                    </section>
                    <section className="panel health-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Inventory health</h2>
                          <p>Know where your stock stands</p>
                        </div>
                        <Package size={19} />
                      </div>
                      {data.healthChart && (
                        <PlotlyChart
                          figure={data.healthChart}
                          onSelect={(label) => {
                            navigate("products");
                            setFilter(
                              label === "In stock"
                                ? "In stock"
                                : label === "Low stock"
                                  ? "Low stock"
                                  : "Out of stock",
                            );
                          }}
                        />
                      )}
                    </section>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Needs your attention</h2>
                        <p>Replenish these products to keep business moving</p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("products")}
                      >
                        View inventory <ArrowUpRight size={15} />
                      </button>
                    </div>
                    {low.length ? (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Product</th>
                              <th>Category</th>
                              <th>Available</th>
                              <th>Reorder point</th>
                              <th>Status</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {low.slice(0, 5).map((p: any) => (
                              <tr key={p.id}>
                                <td>
                                  <b>{p.name}</b>
                                  <small>{p.sku}</small>
                                </td>
                                <td>{p.category}</td>
                                <td>
                                  <b>{p.stock}</b> units
                                </td>
                                <td>{p.reorder} units</td>
                                <td>{badge(status(p))}</td>
                                <td>
                                  {can("stock") && (
                                    <button
                                      className="mini"
                                      onClick={() => open("movement", p)}
                                    >
                                      Restock <Plus size={12} />
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      empty(
                        active.length
                          ? "Your stock is looking healthy"
                          : "Ready for your first product",
                        active.length
                          ? "No products need replenishment right now."
                          : "Add products to start tracking your stock.",
                        !active.length && can("product")
                          ? () => open("product")
                          : undefined,
                      )
                    )}
                  </section>
                </>
              )}
              {view === "purchasing" && can("stock") && (
                <Purchasing
                  key={tenant}
                  tenant={tenant}
                  currency={currency}
                  products={data.products}
                  onReceived={() => load()}
                />
              )}
              {view === "forecasts" && can("forecast") && (
                <Forecasts
                  key={tenant}
                  tenant={tenant}
                  currency={currency}
                  onRestock={(p) => open("movement", p)}
                />
              )}
              {view === "products" && (
                <section className="panel">
                  <div className="toolbar">
                    <div className="search">
                      <Search size={17} />
                      <input
                        placeholder="Search product name or SKU…"
                        value={search}
                        onChange={(e) => {
                          setSearch(e.target.value);
                          setPage(0);
                        }}
                      />
                    </div>
                    <select
                      aria-label="Category"
                      value={category}
                      onChange={(e) => {
                        setCategory(e.target.value);
                        setPage(0);
                      }}
                    >
                      <option value="">All categories</option>
                      {categories.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                    <select
                      aria-label="Stock status"
                      value={filter}
                      onChange={(e) => {
                        setFilter(e.target.value);
                        setPage(0);
                      }}
                    >
                      <option value="">All statuses</option>
                      {[
                        "In stock",
                        "Low stock",
                        "Out of stock",
                        "Archived",
                      ].map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  {products.length ? (
                    <>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Product</th>
                              <th>Category</th>
                              <th>Selling price</th>
                              <th>On hand</th>
                              <th>Reorder</th>
                              <th>Status</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {products
                              .slice(page * 15, page * 15 + 15)
                              .map((p: any) => (
                                <tr key={p.id}>
                                  <td>
                                    <b>{p.name}</b>
                                    <small>{p.sku}</small>
                                  </td>
                                  <td>{p.category}</td>
                                  <td>{money(p.price)}</td>
                                  <td>
                                    <b>{p.stock}</b> units
                                  </td>
                                  <td>{p.reorder}</td>
                                  <td>
                                    {badge(p.active ? status(p) : "Archived")}
                                  </td>
                                  <td>
                                    {can("product") && (
                                      <div className="actions">
                                        <button
                                          className="mini"
                                          onClick={() => open("editProduct", p)}
                                        >
                                          Edit <SlidersHorizontal size={12} />
                                        </button>
                                        <a
                                          className="mini"
                                          href={
                                            "/api/products/" +
                                            p.id +
                                            "/barcode.pdf?tenant=" +
                                            encodeURIComponent(tenant)
                                          }
                                        >
                                          Barcode label
                                        </a>
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="pagination">
                        <span>
                          {page * 15 + 1}–
                          {Math.min(page * 15 + 15, products.length)} of{" "}
                          {products.length} products
                        </span>
                        <div>
                          <button
                            className="mini"
                            disabled={!page}
                            onClick={() => setPage(page - 1)}
                          >
                            Previous
                          </button>
                          <button
                            className="mini"
                            disabled={(page + 1) * 15 >= products.length}
                            onClick={() => setPage(page + 1)}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    empty(
                      "No products found",
                      "Add a product or adjust your search.",
                      can("product") ? () => open("product") : undefined,
                    )
                  )}
                </section>
              )}
              {view === "pos" && can("sale") && (
                <div className="pos-grid">
                  <section>
                    <div className="toolbar pos-toolbar">
                      <div className="search">
                        <Search size={17} />
                        <input
                          autoFocus
                          placeholder="Scan barcode / SKU here, then Enter…"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const p = data.products.find(
                                (p: any) =>
                                  p.active &&
                                  (p.sku.toLowerCase() ===
                                    search.toLowerCase() ||
                                    p.barcode === search),
                              );
                              if (p) {
                                add(p);
                                setSearch("");
                              }
                            }
                          }}
                        />
                      </div>
                      <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        aria-label="Product category"
                      >
                        <option value="">All categories</option>
                        {categories.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                    <div className="pos-products">
                      {products
                        .filter((p: any) => p.active)
                        .map((p: any, i: number) => (
                          <button
                            disabled={p.stock <= 0 || busy}
                            className="product-tile"
                            key={p.id}
                            onClick={() => add(p)}
                          >
                            <div className={"product-visual tint-" + (i % 4)}>
                              <Package size={33} />
                              <span>{p.category}</span>
                            </div>
                            <div className="product-info">
                              <small>{p.sku}</small>
                              <h3>{p.name}</h3>
                              <div>
                                <b>{money(p.price)}</b>
                                <span
                                  className={
                                    p.stock <= p.reorder ? "warning" : ""
                                  }
                                >
                                  {p.stock} in stock
                                </span>
                              </div>
                            </div>
                            <span className="tile-add">
                              <Plus size={15} />
                            </span>
                          </button>
                        ))}
                    </div>
                    {!products.length &&
                      empty(
                        "Your shelf is empty",
                        "Add products before making a sale.",
                        can("product") ? () => open("product") : undefined,
                      )}
                  </section>
                  <section className="panel cart">
                    <div className="panel-heading">
                      <h2>
                        Current order <span>{units}</span>
                      </h2>
                      <button
                        className="icon-button"
                        aria-label="Clear cart"
                        disabled={busy}
                        onClick={() => setCart([])}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <label className="customer">
                      <Users size={16} />
                      <input
                        aria-label="Customer"
                        placeholder="Walk-in customer"
                        value={customer}
                        disabled={busy}
                        onChange={(e) => setCustomer(e.target.value)}
                      />
                    </label>
                    <div className="cart-items">
                      {cart.length ? (
                        cart.map((p) => (
                          <div className="cart-item" key={p.id}>
                            <div>
                              <b>{p.name}</b>
                              <small>{money(p.price)} each</small>
                              <div className="quantity">
                                <button
                                  disabled={busy}
                                  aria-label={"Decrease " + p.name}
                                  onClick={() => quantity(p.id, -1)}
                                >
                                  <Minus size={12} />
                                </button>
                                <span>{p.quantity}</span>
                                <button
                                  disabled={busy}
                                  aria-label={"Increase " + p.name}
                                  onClick={() => quantity(p.id, 1)}
                                >
                                  <Plus size={12} />
                                </button>
                              </div>
                            </div>
                            <strong>{money(p.price * p.quantity)}</strong>
                          </div>
                        ))
                      ) : (
                        <div className="cart-empty">
                          <ShoppingCart size={34} />
                          <h3>Your cart is empty</h3>
                          <p>Select a product to start an order.</p>
                        </div>
                      )}
                    </div>
                    <div className="cart-math">
                      <span>Subtotal</span>
                      <b>{money(subtotal)}</b>
                    </div>
                    <div className="form-grid">
                      <label className="field">
                        <span>Discount ({currency})</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          max={subtotal / 100}
                          value={discount}
                          disabled={busy}
                          onChange={(e) => setDiscount(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Tax (%)</span>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={taxRate}
                          disabled={busy}
                          onChange={(e) => setTaxRate(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="cart-math">
                      <span>Tax</span>
                      <b>{money(tax)}</b>
                    </div>
                    <div className="cart-total">
                      <span>Total</span>
                      <strong>{money(total)}</strong>
                    </div>
                    <div className="payment-tabs">
                      <button
                        disabled={busy}
                        className={payment === "cash" ? "selected" : ""}
                        onClick={() => setPayment("cash")}
                      >
                        Cash
                      </button>
                      <button
                        disabled={busy}
                        className={payment === "external" ? "selected" : ""}
                        onClick={() => setPayment("external")}
                      >
                        Paid externally
                      </button>
                    </div>
                    {payment === "cash" ? (
                      <label className="field">
                        <span>Cash received ({currency})</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={tendered}
                          disabled={busy}
                          onChange={(e) => setTendered(e.target.value)}
                        />
                        <small>
                          Change:{" "}
                          {money(
                            Math.max(
                              0,
                              Math.round(Number(tendered) * 100) - total,
                            ),
                          )}
                        </small>
                      </label>
                    ) : (
                      <p className="hint">
                        Records a payment already collected elsewhere. No card
                        is charged.
                      </p>
                    )}
                    <button
                      className="primary checkout"
                      disabled={
                        busy ||
                        !cart.length ||
                        discountCents > subtotal ||
                        discountCents < 0 ||
                        taxBps < 0 ||
                        taxBps > 10000 ||
                        (payment === "cash" && Number(tendered) * 100 < total)
                      }
                      onClick={checkout}
                    >
                      {busy ? (
                        <Loader2 className="spin" size={17} />
                      ) : (
                        <Check size={17} />
                      )}
                      Complete sale <span>{money(total)}</span>
                    </button>
                    <p className="checkout-note">
                      <ShieldCheck size={12} />
                      Stock updates securely at checkout
                    </p>
                  </section>
                </div>
              )}
              {view === "sales" && can("sale") && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Sales history</h2>
                      <p>
                        Latest 500 receipts · refunds are recorded separately
                      </p>
                    </div>
                    <button className="secondary" onClick={csv}>
                      <Download size={15} />
                      Export CSV
                    </button>
                  </div>
                  {data.sales.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Receipt</th>
                            <th>Customer</th>
                            <th>Payment</th>
                            <th>Total</th>
                            <th>Status</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {data.sales.map((s: any) => (
                            <tr key={s.id}>
                              <td>
                                <b>{s.invoice_number}</b>
                                <small>{date(s.created)}</small>
                              </td>
                              <td>{s.customer}</td>
                              <td className="capitalize">{s.payment}</td>
                              <td>
                                <b>{money(s.total)}</b>
                              </td>
                              <td>{badge(s.status)}</td>
                              <td>
                                <div className="actions">
                                  <button
                                    className="mini"
                                    onClick={() => showReceipt(s.id)}
                                  >
                                    Receipt
                                  </button>
                                  {can("return") &&
                                    s.status === "completed" && (
                                      <button
                                        className="mini"
                                        onClick={() => open("return", s)}
                                      >
                                        Return
                                      </button>
                                    )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    empty(
                      "No sales yet",
                      "Your receipts will appear here after the first checkout.",
                    )
                  )}
                </section>
              )}
              {view === "movements" && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Stock ledger</h2>
                      <p>
                        Latest 500 movements · positive quantities add stock
                      </p>
                    </div>
                    <ArrowLeftRight size={20} />
                  </div>
                  {data.movements.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Product</th>
                            <th>Movement</th>
                            <th>Quantity</th>
                            <th>Recorded by</th>
                            <th>Date</th>
                            <th>Notes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.movements.map((m: any) => (
                            <tr key={m.id}>
                              <td>
                                <b>{m.name}</b>
                                <small>{m.sku}</small>
                              </td>
                              <td>{badge(m.type)}</td>
                              <td
                                className={
                                  m.quantity < 0 ? "negative" : "positive"
                                }
                              >
                                {m.quantity > 0 ? "+" : ""}
                                {m.quantity}
                              </td>
                              <td>{m.actor}</td>
                              <td>{date(m.created)}</td>
                              <td className="wrap">{m.notes}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    empty(
                      "No stock movements yet",
                      "Opening stock, adjustments, sales and returns will appear here.",
                    )
                  )}
                </section>
              )}
              {view === "team" && can("team") && (
                <>
                  <div className="team-banner">
                    <ShieldCheck size={25} />
                    <div>
                      <h3>Access that matches each responsibility</h3>
                      <p>
                        Membership applies only to this business. Users sign in
                        with their own email and password.
                      </p>
                    </div>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Team members</h2>
                        <p>
                          Create staff accounts or assign existing users. No
                          invitation email is sent.
                        </p>
                      </div>
                      <span className="subtle-tag">
                        {data.members.length} members
                      </span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>User</th>
                            <th>Role</th>
                            <th>Status</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {data.members.map((m: any) => (
                            <tr key={m.id}>
                              <td>
                                <b>{m.email}</b>
                              </td>
                              <td>{m.role}</td>
                              <td>{badge(m.active ? "Active" : "Disabled")}</td>
                              <td>
                                {m.role !== "Owner" && (
                                  <div className="actions">
                                    <button
                                      className="mini"
                                      onClick={() => open("member", m)}
                                    >
                                      Change role
                                    </button>
                                    <button
                                      disabled={busy}
                                      className="mini"
                                      onClick={() =>
                                        toggle("memberStatus", {
                                          id: m.id,
                                          active: !m.active,
                                        })
                                      }
                                    >
                                      {m.active ? "Disable" : "Enable"}
                                    </button>
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                  <section className="panel role-matrix">
                    <div className="panel-heading">
                      <h2>Role permissions</h2>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Permission</th>
                            {ROLES.map((r) => (
                              <th key={r}>{r}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries({
                            forecast: "Forecasts & insights",
                            read: "View inventory",
                            product: "Manage products",
                            stock: "Adjust stock",
                            sale: "Checkout & receipts",
                            return: "Return sales",
                            team: "Manage team",
                            settings: "Business settings",
                          }).map(([p, label]) => (
                            <tr key={p}>
                              <td>{label}</td>
                              {ROLES.map((r) => (
                                <td key={r}>
                                  {permissions[r].includes(p) ? (
                                    <Check className="positive" size={16} />
                                  ) : (
                                    <span className="muted">—</span>
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
              {view === "businesses" && (
                <>
                  <div className="business-grid">
                    {data.tenants.map((t: any) => (
                      <section key={t.id} className="panel business-card">
                        <div className="business-icon">
                          <Building2 size={25} />
                        </div>
                        <div>{badge(t.status)}</div>
                        <h2>{t.name}</h2>
                        <p>
                          {t.currency} · Created{" "}
                          {new Date(t.created).toLocaleDateString()}
                        </p>
                        <div className="actions">
                          <button
                            className="primary"
                            disabled={busy || t.status !== "active"}
                            onClick={() => switchTenant(t.id)}
                          >
                            Open workspace <ArrowUpRight size={15} />
                          </button>
                          {data.user?.admin && (
                            <button
                              className="secondary"
                              onClick={() => open("tenantStatus", t)}
                            >
                              {t.status === "active" ? "Suspend" : "Reactivate"}
                            </button>
                          )}
                        </div>
                      </section>
                    ))}
                  </div>
                  {!data.tenants.length && (
                    <div className="welcome panel">
                      <Building2 size={36} />
                      <h2>Give your business a home.</h2>
                      <p>
                        Create an isolated workspace for your inventory, sales
                        and team.
                      </p>
                      {data.user?.admin && (
                        <button
                          className="primary"
                          onClick={() => open("tenant")}
                        >
                          <Plus size={16} />
                          Create business
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
              {view === "settings" && can("settings") && (
                <section className="panel settings">
                  <div className="panel-heading">
                    <h2>Business details</h2>
                  </div>
                  <dl>
                    <dt>Business name</dt>
                    <dd>{data.tenant?.name}</dd>
                    <dt>Currency</dt>
                    <dd>
                      {currency}{" "}
                      <small>
                        Fixed after creation to preserve sales history.
                      </small>
                    </dd>
                    <dt>Business ID</dt>
                    <dd className="mono">{tenant}</dd>
                  </dl>
                  <button
                    className="secondary"
                    onClick={() => open("settings", data.tenant)}
                  >
                    Edit business name
                  </button>
                  <div className="settings-note">
                    <ShieldCheck size={20} />
                    <p>
                      Team access is enforced on the server. User accounts are
                      managed by the platform and business owners. Staff can
                      only access businesses where they have active membership.
                    </p>
                  </div>
                </section>
              )}
              {view === "audit" && can("team") && (
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Recent activity</h2>
                    <span className="subtle-tag">Latest 100 actions</span>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Action</th>
                          <th>User</th>
                          <th>Date</th>
                          <th>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.audit.map((a: any) => (
                          <tr key={a.id}>
                            <td>
                              <b>{a.action}</b>
                            </td>
                            <td>{a.actor}</td>
                            <td>{date(a.created)}</td>
                            <td className="wrap mono">{a.details}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
          {loading && !data.tenant && (
            <div className="loading">
              <Loader2 className="spin" />
              Connecting to your workspace…
            </div>
          )}
          <footer>
            <ShieldCheck size={13} />
            StockDesk / Retail operations
            <span>All sales reporting dates use UTC.</span>
          </footer>
        </main>
      </div>
      {modal && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
          >
            <div className="modal-heading">
              <div>
                <div className="eyebrow">
                  {data.tenant?.name || "STOCKDESK"}
                </div>
                <h2 id="modal-title">
                  {
                    {
                      product: "Add a product",
                      editProduct: "Edit product",
                      movement: "Adjust stock",
                      member: "Manage team access",
                      tenant: "Create your business",
                      return: "Return this sale",
                      settings: "Business details",
                      tenantStatus: "Change business access",
                      password: "Change your password",
                    }[modal.kind as string]
                  }
                </h2>
              </div>
              <button
                disabled={busy}
                className="icon-button"
                aria-label="Close dialog"
                onClick={() => setModal(null)}
              >
                <X size={21} />
              </button>
            </div>
            <form
              onSubmit={async (e) => {
                if (modal.kind === "tenantStatus") {
                  e.preventDefault();
                  setBusy(true);
                  try {
                    await post("tenantStatus", {
                      tenant: modal.item.id,
                      status:
                        modal.item.status === "active" ? "suspended" : "active",
                    });
                    setModal(null);
                    if (tenant === modal.item.id) {
                      setTenant("");
                      setCart([]);
                      await load("");
                    } else await load();
                  } catch (err: any) {
                    setFormError(err.message);
                  } finally {
                    setBusy(false);
                  }
                  return;
                }
                await submit(e);
              }}
            >
              <fieldset disabled={busy}>
                {["product", "editProduct"].includes(modal.kind) && (
                  <>
                    {field("Product name", "name", "text", modal.item?.name)}
                    <div className="form-grid">
                      {modal.kind === "product"
                        ? field("SKU / Barcode", "sku")
                        : field(
                            "SKU (immutable)",
                            "sku",
                            "text",
                            modal.item?.sku,
                          )}
                      {field(
                        "Category",
                        "category",
                        "text",
                        modal.item?.category,
                      )}
                    </div>
                    {field(
                      "Barcode (optional; SKU is also scannable)",
                      "barcode",
                      "text",
                      modal.item?.barcode || "",
                      false,
                    )}
                    <div className="form-grid">
                      {field(
                        `Selling price (${currency})`,
                        "price",
                        "number",
                        (modal.item?.price || 0) / 100,
                      )}
                      {field(
                        `Purchase cost (${currency})`,
                        "cost",
                        "number",
                        (modal.item?.cost || 0) / 100,
                      )}
                    </div>
                    <div className="form-grid">
                      {modal.kind === "product" &&
                        field("Opening stock", "initial", "number", 0)}
                      {field(
                        "Reorder point",
                        "reorder",
                        "number",
                        modal.item?.reorder ?? 5,
                      )}
                    </div>
                    {modal.kind === "editProduct" && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          name="active"
                          defaultChecked={!!modal.item.active}
                        />
                        Active product (available at checkout)
                      </label>
                    )}
                    <p className="hint">
                      Stock changes are recorded through the ledger. Prices are
                      stored with two decimal places.
                    </p>
                  </>
                )}
                {modal.kind === "password" && (
                  <>
                    {field("Current password", "current", "password")}
                    {field(
                      "New password (12–128 characters)",
                      "password",
                      "password",
                    )}
                  </>
                )}
                {modal.kind === "movement" && (
                  <>
                    <label className="field">
                      <span>Product</span>
                      <select
                        name="product"
                        defaultValue={modal.item?.id || ""}
                        required
                      >
                        <option value="">Choose product</option>
                        {data.products
                          .filter((p: any) => p.active)
                          .map((p: any) => (
                            <option key={p.id} value={p.id}>
                              {p.sku} — {p.name} ({p.stock} available)
                            </option>
                          ))}
                      </select>
                    </label>
                    <div className="form-grid">
                      <label className="field">
                        <span>Movement</span>
                        <select name="type">
                          <option value="IN">Stock IN</option>
                          <option value="OUT">Stock OUT</option>
                        </select>
                      </label>
                      {field("Quantity", "quantity", "number", 1)}
                    </div>
                    {field("Reason / reference", "notes")}
                    <p className="hint">
                      Stock OUT cannot exceed available stock. Every change is
                      recorded in the activity log.
                    </p>
                  </>
                )}
                {modal.kind === "member" && (
                  <>
                    {field(
                      "Sign-in email",
                      "email",
                      "email",
                      modal.item?.email,
                    )}
                    {field(
                      "Name (new users)",
                      "name",
                      "text",
                      modal.item?.name || "",
                      false,
                    )}
                    {field(
                      "Initial password (new users, 12+ characters)",
                      "password",
                      "password",
                      "",
                      false,
                    )}
                    <label className="field">
                      <span>Role in this business</span>
                      <select
                        name="role"
                        defaultValue={modal.item?.role || "Cashier"}
                      >
                        {ROLES.map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </label>
                    <p className="hint">
                      For a new account, provide a name and a password of at
                      least 12 characters. Share credentials through your own
                      secure channel. For existing users, name and password
                      fields are ignored.
                    </p>
                  </>
                )}
                {modal.kind === "tenant" && (
                  <>
                    {field("Business name", "name")}
                    <label className="field">
                      <span>Business currency</span>
                      <select name="currency">
                        {["PKR", "USD", "SAR", "AED", "EUR", "GBP"].map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </label>
                    {field(
                      "Owner email (optional)",
                      "owner_email",
                      "email",
                      "",
                      false,
                    )}
                    {field(
                      "Owner name (new account)",
                      "owner_name",
                      "text",
                      "",
                      false,
                    )}
                    {field(
                      "Owner password (new account, 12+ characters)",
                      "owner_password",
                      "password",
                      "",
                      false,
                    )}
                    <p className="hint">
                      Leave owner email blank to own this workspace yourself.
                      Products, sales and team permissions are separate from
                      other businesses.
                    </p>
                  </>
                )}
                {modal.kind === "return" && (
                  <>
                    <div className="return-summary">
                      <Receipt size={24} />
                      <div>
                        <b>#{modal.item.id.slice(0, 8).toUpperCase()}</b>
                        <p>
                          {money(modal.item.total)} · {modal.item.customer}
                        </p>
                      </div>
                    </div>
                    {field("Reason for return", "reason")}
                    <p className="hint">
                      This returns the entire sale and restores all stock once.
                      Refund the customer separately; this action does not move
                      money.
                    </p>
                  </>
                )}
                {modal.kind === "settings" && (
                  <>
                    {field("Business name", "name", "text", modal.item?.name)}
                    {field(
                      "Business address",
                      "address",
                      "text",
                      modal.item?.address || "",
                      false,
                    )}
                    {field(
                      "Tax registration number",
                      "tax_number",
                      "text",
                      modal.item?.tax_number || "",
                      false,
                    )}
                  </>
                )}
                {modal.kind === "tenantStatus" && (
                  <p>
                    {modal.item.status === "active"
                      ? "Suspending"
                      : "Reactivating"}{" "}
                    <b>{modal.item.name}</b>{" "}
                    {modal.item.status === "active"
                      ? "will block all inventory and sales access for this business."
                      : "will restore access for active members."}
                  </p>
                )}
                {formError && (
                  <div className="form-error" role="alert">
                    {formError}
                  </div>
                )}
                <div className="modal-actions">
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => setModal(null)}
                  >
                    Cancel
                  </button>
                  <button className="primary" type="submit">
                    {busy ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Check size={16} />
                    )}{" "}
                    {modal.kind === "return"
                      ? "Confirm return"
                      : "Save changes"}
                  </button>
                </div>
              </fieldset>
            </form>
          </section>
        </div>
      )}
      {receipt && (
        <div className="modal-overlay receipt-overlay">
          <section
            className="modal receipt"
            role="dialog"
            aria-modal="true"
            aria-label="Sales receipt"
          >
            <div className="receipt-top">
              <Boxes size={30} />
              <h2>{receipt.sale.seller_name}</h2>
              <p>{receipt.sale.seller_address}</p>
              <small>{receipt.sale.seller_tax_number}</small>
              <p>Invoice · {receipt.sale.invoice_number}</p>
              <small>{date(receipt.sale.created)}</small>
            </div>
            <div className="receipt-customer">
              <span>{receipt.sale.customer}</span>
              {badge(receipt.sale.status)}
            </div>
            {receipt.items.map((i: any) => (
              <div className="receipt-line" key={i.id}>
                <div>
                  <b>{i.name}</b>
                  <small>
                    {i.quantity} × {money(i.price)}
                  </small>
                </div>
                <strong>{money(i.price * i.quantity)}</strong>
              </div>
            ))}
            <div className="cart-math">
              <span>Subtotal</span>
              <b>{money(receipt.sale.subtotal)}</b>
            </div>
            <div className="cart-math">
              <span>Discount</span>
              <b>−{money(receipt.sale.discount)}</b>
            </div>
            <div className="cart-math">
              <span>Tax ({receipt.sale.tax_bps / 100}%)</span>
              <b>{money(receipt.sale.tax)}</b>
            </div>
            <div className="receipt-total">
              <b>Total</b>
              <strong>{money(receipt.sale.total)}</strong>
            </div>
            <p className="hint">
              Payment:{" "}
              {receipt.sale.payment === "cash"
                ? "Cash"
                : "Collected externally"}
              <br />
              Served by {receipt.sale.actor}
            </p>
            <p className="receipt-thanks">Thank you for your business.</p>
            <div className="modal-actions no-print">
              <button className="secondary" onClick={() => setReceipt(null)}>
                Close
              </button>
              <a
                className="secondary"
                href={
                  "/api/invoices/" +
                  receipt.sale.id +
                  ".pdf?tenant=" +
                  encodeURIComponent(tenant)
                }
              >
                <Download size={16} />
                PDF
              </a>
              <button className="primary" onClick={() => window.print()}>
                <Printer size={16} />
                Print receipt
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
