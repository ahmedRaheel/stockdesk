import { t as tr } from "./i18n";
import { useLanguage } from "./i18n";
("use client");
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
import Retail from "./Retail";
import AuditLog from "./AuditLog";
import RoleManagement from "./RoleManagement";
import CatalogImport from "./CatalogImport";
import Payables from "./Payables";
import Promotions, { PromotionPicker } from "./Promotions";
import ManagementReport from "./ManagementReport";
import StockCounts from "./StockCounts";
import PosEntry from "./PosEntry";
import SplitPayments, { PaymentRow } from "./SplitPayments";
import TaxSettings from "./TaxSettings";
import Tills from "./Tills";
import BatchAlerts from "./BatchAlerts";
import LookupSelect from "./LookupSelect";
import CustomerSelect from "./CustomerSelect";
import { send } from "./api";
const titles: any = {
  promotions: [
    "Promotions and coupons",
    "Scheduled discounts, BOGO offers and bundles.",
  ],
  roles: ["Custom roles", "Business permissions and staff assignments."],
  imports: ["Catalog import", "Validate and import products from CSV."],
  payables: [
    "Supplier payables",
    "Matched invoices, payments, and outstanding balances.",
  ],
  reports: [
    "Management reports",
    "Margin, category, cashier, hourly sales and ABC/XYZ.",
  ],
  counts: ["Stock counts", "Physical batch counts with independent approval."],
  taxes: [
    "Tax configuration",
    "Configure rates, effective dates, and when tax applies.",
  ],
  tills: [
    "Till sessions",
    "Opening cash, cash movements, and closing reconciliation.",
  ],
  batches: [
    "Batches & expiry",
    "FEFO stock allocation, near-expiry alerts, and batch adjustments.",
  ],
  khata: ["Customers & khata", "Credit sales, recoveries, and installments."],
  lookups: [
    "Lookup management",
    "Manage business reference data and Urdu labels.",
  ],
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
  promotions: SlidersHorizontal,
  roles: ShieldCheck,
  imports: Download,
  payables: Receipt,
  tills: Receipt,
  batches: AlertTriangle,
  khata: Users,
  lookups: SlidersHorizontal,
  taxes: SlidersHorizontal,
  counts: Package,
  reports: Package,
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
  const [heldBills, setHeldBills] = useState<any[]>([]),
    [heldId, setHeldId] = useState("");
  async function refreshHeld() {
    const r = await fetch("/api/v1/tenants/" + tenant + "/held-bills");
    const d = await r.json();
    if (!r.ok) throw Error(d.error);
    setHeldBills(d.items);
  }
  useEffect(() => {
    if (tenant && can("sale")) refreshHeld().catch((e) => setError(e.message));
  }, [tenant, view]);
  async function holdCurrent() {
    if (!cart.length || busy) return;
    setBusy(true);
    try {
      await send("/api/v1/tenants/" + tenant + "/held-bills", {
        id: crypto.randomUUID(),
        label: customer || "Held bill " + new Date().toLocaleTimeString(),
        items: cart.map((p) => ({ id: p.id, quantity: p.quantity })),
        customer_id: customerId || null,
        promotion_code: promotionCode,
      });
      setCart([]);
      setPromotionCode("");
      setHeldId("");
      await refreshHeld();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function resumeHeld(id: string) {
    const bill = heldBills.find((b) => b.id === id);
    if (!bill) return;
    const lines = bill.payload.items.map((i: any) => {
      const p = data.products.find((p: any) => p.id === i.id && p.active);
      if (!p) throw Error("A held product is no longer active.");
      return { ...p, quantity: Number(i.quantity) };
    });
    setCart(lines);
    setPromotionCode(bill.payload.promotion_code || "");
    setHeldId(id);
    setCustomerId(bill.payload.customer_id || "");
    setCreditMode(false);
    setDiscount("0");
    setTaxRate("0");
    setToast("Bill resumed at current prices. Review totals and stock.");
  }
  const [prescriptionRef, setPrescriptionRef] = useState("");
  const [customerId, setCustomerId] = useState(""),
    [creditMode, setCreditMode] = useState(false),
    [paidNow, setPaidNow] = useState("0"),
    [dueDate, setDueDate] = useState(""),
    [methodId, setMethodId] = useState("");
  const [language, setLanguage] = useLanguage();
  const navUr: Record<string, string> = {
    dashboard: "خلاصہ",
    products: "مصنوعات",
    pos: "فروخت",
    sales: "رسیدیں",
    movements: "اسٹاک",
    purchasing: "خریداری",
    khata: "کھاتہ",
    forecasts: "پیش گوئی",
    lookups: "فہرستیں",
    team: "عملہ",
    audit: "سرگرمیاں",
    businesses: "کاروبار",
    settings: "ترتیبات",
  };
  useEffect(() => {
    localStorage.setItem("stockdesk-language", language);
  }, [language]);
  const [promotionCode, setPromotionCode] = useState("");
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
    setPromotionCode("");
    setDiscount("0");
    setCustomerId("");
    setSplit(false);
    setPaymentRows([]);
    setCreditMode(false);
    setMethodId("");
    setHeldId("");
    setHeldBills([]);
    setPrescriptionRef("");
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
          expiry_required: f.expiry_required === "on",
          prescription_required: f.prescription_required === "on",
          tax_profile_id: f.tax_profile_id || null,
        });
      } else if (kind === "movement") {
        const payload = {
          ...f,
          quantity: Number(f.quantity),
          expires: f.expires || null,
          batch_id: modal.item?.batch_id || null,
          reason_id: f.reason_id || null,
        };
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
      (
        p.name +
        " " +
        p.sku +
        " " +
        (p.barcode || "") +
        " " +
        (p.search_aliases || "")
      )
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!category || p.category === category) &&
      (!filter || (filter === "Archived" ? !p.active : status(p) === filter)),
  );
  const categories = [
    ...new Set<string>(data.products.map((p: any) => p.category)),
  ].sort();
  const [taxSettings, setTaxSettings] = useState<any>(null),
    [quote, setQuote] = useState<any>(null),
    [quoteError, setQuoteError] = useState("");
  useEffect(() => {
    setTaxSettings(null);
    if (!tenant) return;
    const controller = new AbortController();
    fetch(`/api/v1/tenants/${tenant}/tax-settings`, {
      signal: controller.signal,
    })
      .then((r) => r.json())
      .then(setTaxSettings)
      .catch(() => {});
    return () => controller.abort();
  }, [tenant, data.tenant]);
  const quoteBody = JSON.stringify({
    promotion_code: promotionCode,
    items: cart.map((p) => ({ id: p.id, quantity: p.quantity })),
    discount: Math.round(Number(discount || 0) * 100),
    tax_bps: Math.round(Number(taxRate || 0) * 100),
  });
  useEffect(() => {
    setQuote(null);
    setQuoteError("");
    if (!tenant || !cart.length) return;
    const c = new AbortController();
    const timer = setTimeout(() => {
      fetch(`/api/v1/tenants/${tenant}/sales/quote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: quoteBody,
        signal: c.signal,
      })
        .then(async (r) => {
          const d = await r.json();
          if (!r.ok) throw Error(d.error);
          return d;
        })
        .then((d) => setQuote({ ...d, body: quoteBody }))
        .catch((e) => {
          if (e.name !== "AbortError") setQuoteError(e.message);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [tenant, quoteBody, taxSettings]);
  const quoteReady = quote?.body === quoteBody;
  const subtotal = cart.reduce(
      (s, p) => s + Math.round(p.price * p.quantity),
      0,
    ),
    discountCents = Math.round(Number(discount || 0) * 100),
    taxBps = Math.round(Number(taxRate || 0) * 100),
    tax = quoteReady ? quote.tax : 0,
    total = quoteReady ? quote.total : subtotal - discountCents,
    units = cart.reduce((s, p) => s + p.quantity, 0);
  const [split, setSplit] = useState(false),
    [paymentRows, setPaymentRows] = useState<PaymentRow[]>([]);
  const collected = split
    ? paymentRows.reduce(
        (sum, r) => sum + Math.round(Number(r.amount) * 100),
        0,
      )
    : creditMode
      ? Math.round(Number(paidNow) * 100)
      : total;
  const cashCollected = split
    ? paymentRows
        .filter((r) => r.is_cash)
        .reduce((sum, r) => sum + Math.round(Number(r.amount) * 100), 0)
    : payment === "cash"
      ? collected
      : 0;
  function add(p: any, amount = 1) {
    if (busy) return false;
    const existing = cart.find((x) => x.id === p.id);
    const next = Math.round(((existing?.quantity || 0) + amount) * 1000) / 1000;
    if (!Number.isFinite(amount) || amount <= 0 || next > Number(p.stock)) {
      setToast(tr("Requested quantity exceeds available stock."));
      return false;
    }
    setCart((previous) => {
      const current = previous.find((x) => x.id === p.id);
      const qty = Math.round(((current?.quantity || 0) + amount) * 1000) / 1000;
      if (qty > Number(p.stock)) return previous;
      return current
        ? previous.map((x) => (x.id === p.id ? { ...x, quantity: qty } : x))
        : [...previous, { ...p, quantity: amount }];
    });
    return true;
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
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (
        view !== "pos" ||
        modal ||
        receipt ||
        e.altKey ||
        e.ctrlKey ||
        e.metaKey
      )
        return;
      const selectors: Record<string, string> = {
        F2: "[data-pos-search]",
        F4: ".checkout",
        F8: "[data-hold-bill]",
      };
      const selector = selectors[e.key];
      if (!selector) return;
      e.preventDefault();
      const element = document.querySelector<
        HTMLInputElement | HTMLButtonElement
      >(selector);
      if (element && !element.disabled) {
        if (e.key === "F2") element.focus();
        else element.click();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [view, modal, receipt]);
  async function checkout() {
    if (!cart.length || busy || !quoteReady) return;
    setBusy(true);
    setError("");
    const payload = {
      quote_token: quote.quote_token,
      promotion_code: promotionCode,
      items: cart.map((p) => ({ id: p.id, quantity: p.quantity })),
      customer,
      held_bill_id: heldId || null,
      prescription_reference: prescriptionRef,
      customer_id: customerId || null,
      paid_now: split
        ? collected
        : creditMode
          ? Math.round(Number(paidNow) * 100)
          : null,
      tenders: split
        ? paymentRows.map((r) => ({
            method_id: r.method_id,
            amount: Math.round(Number(r.amount) * 100),
            reference: r.reference,
          }))
        : null,
      due_date: creditMode ? dueDate : null,
      payment_method_id: split ? null : methodId || null,
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
      setSplit(false);
      setPaymentRows([]);
      setTendered("");
      setHeldId("");
      await refreshHeld();
      setPrescriptionRef("");
      setCustomer("");
      setCustomerId("");
      setCreditMode(false);
      setPaidNow("0");
      setDiscount("0");
      setPromotionCode("");
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
    if (view !== "sales" && !can("cost")) {
      const index = headers.indexOf("Cost");
      if (index >= 0) {
        headers.splice(index, 1);
        rows.forEach((row) => row.splice(index, 1));
      }
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
    ...(can("sale") ? ["pos", "sales", "tills"] : []),
    "movements",
    ...(can("stock") ? ["purchasing", "batches", "counts"] : []),
    ...(can("credit") ? ["khata"] : []),
    ...(can("settings") ? ["lookups", "taxes"] : []),
    ...(can("promotions") ? ["promotions"] : []),
    ...(can("cost") ? ["reports"] : []),
    ...(can("finance") ? ["payables"] : []),
    ...(can("product") ? ["imports"] : []),
    ...(can("team") ? ["team"] : []),
    ...(can("audit") ? ["audit"] : []),
    ...(can("roles") ? ["roles"] : []),
    "businesses",
    ...(can("settings") ? ["settings"] : []),
  ];
  const low = data.products.filter(
      (p: any) => p.active && p.stock <= p.reorder,
    ),
    value = data.products.reduce(
      (s: number, p: any) => s + p.stock * (p.cost || 0),
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
      {tr(s)}
    </span>
  );
  const empty = (label: string, detail: string, action?: () => void) => (
    <div className="empty">
      <div className="empty-icon">
        <Boxes size={30} />
      </div>
      <h3>{tr(label)}</h3>
      <p>{tr(detail)}</p>
      {action && (
        <button className="primary" onClick={action}>
          <Plus size={16} /> {tr("Add your first product")}{" "}
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
      <span>{tr(label)}</span>
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
              : ["initial", "quantity", "reorder"].includes(name)
                ? "0.001"
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
          </span>{" "}
          {tr("StockDesk")}
          <span className="saas">{tr("HQ")}</span>
        </a>
        <div className="workspace-label">{tr("WORKSPACE")}</div>
        <div className="business-select">
          <Building2 size={18} />
          <select
            aria-label={tr("Select business")}
            value={tenant}
            disabled={busy || loading}
            onChange={(e) => switchTenant(e.target.value)}
          >
            <option value="">{tr("Select a business")}</option>
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
                title={tr(titles[v][0])}
                aria-label={tr(titles[v][0])}
                aria-current={view === v ? "page" : undefined}
                className={view === v ? "active" : ""}
                disabled={busy}
                onClick={() => navigate(v)}
              >
                <Icon size={18} />
                {language === "ur"
                  ? navUr[v] || tr(titles[v][0])
                  : v === "dashboard"
                    ? tr("Overview")
                    : v === "pos"
                      ? tr("Point of sale")
                      : v === "team"
                        ? tr("Team & roles")
                        : v === "businesses"
                          ? tr("Businesses")
                          : v === "audit"
                            ? tr("Activity log")
                            : v === "products"
                              ? tr("Inventory")
                              : v === "forecasts"
                                ? tr("Forecasts")
                                : v === "movements"
                                  ? tr("Stock ledger")
                                  : tr(titles[v][0])}
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
            <span>{tr("Private business workspace")}</span>
          </div>
          <div className="profile">
            <div className="avatar">
              {(data.user?.displayName || "U").slice(0, 1).toUpperCase()}
            </div>
            <div>
              <b>{data.user?.displayName || "Connecting…"}</b>
              <small>
                {tr(data.user?.admin ? "Super Admin" : data.role || "Member")}
              </small>
            </div>
            <button
              className="icon-button"
              onClick={onLogout}
              aria-label={tr("Sign out")}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header>
          <div className="breadcrumb">
            {" "}
            {tr("Workspace")} <span>/</span> <b>{tr(titles[view][0])}</b>
          </div>
          <div className="header-right">
            <button
              className="mini"
              onClick={() => setLanguage(language === "en" ? "ur" : "en")}
            >
              {language === "en" ? "اردو" : tr("English")}
            </button>
            <button
              className="density-control"
              aria-label={tr("Toggle table density")}
              aria-pressed={density === "compact"}
              onClick={() =>
                setDensity(density === "compact" ? "comfortable" : "compact")
              }
            >
              <SlidersHorizontal size={15} />
              {density === "compact" ? tr("Compact") : tr("Comfortable")}
            </button>
            <span className="connected">
              <i />
              {loading ? tr("Syncing…") : tr("Connected")}
            </span>
            <button
              className="icon-button"
              aria-label={tr("Change password")}
              onClick={() => open("password")}
            >
              <ShieldCheck size={17} />
            </button>
            <button
              className="icon-button"
              aria-label={tr("Refresh")}
              disabled={busy || loading}
              onClick={() => load()}
            >
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
            <span className="role-chip">
              {data.user?.admin ? tr("Super Admin") : data.role || "Account"}
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {data.tenant?.name || "YOUR BUSINESS, ORGANIZED"}
              </div>
              <h1>{tr(titles[view][0])}</h1>
              <p>{tr(titles[view][1])}</p>
            </div>
            <div className="actions">
              {["dashboard", "products"].includes(view) && can("product") && (
                <button className="secondary" onClick={() => open("product")}>
                  <Plus size={16} /> {tr("Add product")}{" "}
                </button>
              )}
              {view === "dashboard" && can("sale") && (
                <button className="primary" onClick={() => navigate("pos")}>
                  <ShoppingCart size={16} /> {tr("Open point of sale")}{" "}
                </button>
              )}
              {view === "products" && (
                <button className="secondary" onClick={csv}>
                  <Download size={16} /> {tr("Export")}{" "}
                </button>
              )}
              {view === "movements" && can("stock") && (
                <button className="primary" onClick={() => open("movement")}>
                  <Plus size={16} /> {tr("Stock adjustment")}{" "}
                </button>
              )}
              {view === "team" && (
                <button className="primary" onClick={() => open("member")}>
                  <Plus size={16} /> {tr("Add team member")}{" "}
                </button>
              )}
              {view === "businesses" && data.user?.admin && (
                <button className="primary" onClick={() => open("tenant")}>
                  <Plus size={16} /> {tr("New business")}{" "}
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <AlertTriangle size={18} />
              <span>{tr(error)}</span>
              <button
                onClick={() => setError("")}
                aria-label={tr("Dismiss error")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {toast && (
            <div className="toast" role="status">
              <Check size={17} />
              {tr(toast)}
            </div>
          )}
          {!tenant && view !== "businesses" && !loading ? (
            <div className="welcome panel">
              <span className="welcome-icon">
                <Building2 size={38} />
              </span>
              <div className="eyebrow">{tr("A FRESH START")}</div>
              <h2>{tr("Your business starts here.")}</h2>
              <p>
                {" "}
                {tr(
                  "Create your workspace, add your products, and make your first sale.",
                )}{" "}
                <br />{" "}
                {tr(
                  "Your inventory and team stay organized from day one.",
                )}{" "}
              </p>
              {data.user?.admin ? (
                <button className="primary" onClick={() => open("tenant")}>
                  <Plus size={17} /> {tr("Create a business")}{" "}
                </button>
              ) : (
                <p>
                  {tr("Ask your administrator to assign you to a business.")}
                </p>
              )}
              <div className="welcome-features">
                <span>
                  <ShieldCheck /> {tr("Role-based access")}{" "}
                </span>
                <span>
                  <Package /> {tr("Live stock tracking")}{" "}
                </span>
                <span>
                  <Receipt /> {tr("Connected checkout")}{" "}
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
                        can("cost") ? "Inventory value" : "Units on hand",
                        can("cost")
                          ? money(value)
                          : String(
                              active.reduce(
                                (s: number, p: any) => s + Number(p.stock),
                                0,
                              ),
                            ),
                        can("cost")
                          ? "Stock at purchase cost"
                          : "Active inventory",
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
                          <span>{tr(label)}</span>
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
                              {" "}
                              {tr("Review")} <ArrowUpRight size={13} />
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
                          <h2>{tr("Sales performance")}</h2>
                          <p>
                            {tr("Completed sales over the last 7 days · UTC")}
                          </p>
                        </div>
                        <span className="subtle-tag">{tr("Last 7 days")}</span>
                      </div>
                      <div className="chart-total">
                        {money(
                          (data.trend || []).reduce(
                            (s: number, r: any) => s + r.total,
                            0,
                          ),
                        )}
                        <span>{tr("total revenue")}</span>
                      </div>
                      {data.salesChart && (
                        <PlotlyChart figure={data.salesChart} />
                      )}
                      {!can("sale") && (
                        <p className="muted">
                          {" "}
                          {tr(
                            "Sales reporting is restricted to sales roles.",
                          )}{" "}
                        </p>
                      )}
                    </section>
                    <section className="panel health-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>{tr("Inventory health")}</h2>
                          <p>{tr("Know where your stock stands")}</p>
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
                        <h2>{tr("Needs your attention")}</h2>
                        <p>
                          {tr(
                            "Replenish these products to keep business moving",
                          )}
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("products")}
                      >
                        {" "}
                        {tr("View inventory")} <ArrowUpRight size={15} />
                      </button>
                    </div>
                    {low.length ? (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>{tr("Product")}</th>
                              <th>{tr("Category")}</th>
                              <th>{tr("Available")}</th>
                              <th>{tr("Reorder point")}</th>
                              <th>{tr("Status")}</th>
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
                                  <b>{p.stock}</b> {tr("units")}{" "}
                                </td>
                                <td>
                                  {p.reorder} {tr("units")}
                                </td>
                                <td>{badge(status(p))}</td>
                                <td>
                                  {can("stock") && (
                                    <button
                                      className="mini"
                                      onClick={() => open("movement", p)}
                                    >
                                      {" "}
                                      {tr("Restock")} <Plus size={12} />
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
                  canApprove={can("purchase_approve")}
                  canConfigure={can("roles")}
                  userEmail={data.user?.email || ""}
                  onReceived={() => load()}
                />
              )}
              {view === "tills" && can("sale") && (
                <Tills key={tenant} tenant={tenant} currency={currency} />
              )}
              {view === "batches" && can("stock") && (
                <BatchAlerts
                  key={tenant}
                  tenant={tenant}
                  onAdjust={(p) => open("movement", p)}
                />
              )}
              {view === "khata" && can("credit") && (
                <Retail
                  key={tenant + "khata"}
                  tenant={tenant}
                  currency={currency}
                  approve={can("credit_approve")}
                  lookupAdmin={can("settings")}
                  language={language}
                />
              )}
              {view === "roles" && can("roles") && (
                <RoleManagement key={tenant} tenant={tenant} />
              )}
              {view === "imports" && can("product") && (
                <CatalogImport
                  key={tenant}
                  tenant={tenant}
                  onImported={() => load()}
                />
              )}
              {view === "payables" && can("finance") && (
                <Payables
                  key={tenant}
                  tenant={tenant}
                  currency={currency}
                  canReturn={can("supplier_return")}
                />
              )}
              {view === "promotions" && can("promotions") && (
                <Promotions key={tenant} tenant={tenant} currency={currency} />
              )}
              {view === "reports" && can("cost") && (
                <ManagementReport tenant={tenant} currency={currency} />
              )}
              {view === "counts" && can("stock") && (
                <StockCounts
                  key={tenant}
                  tenant={tenant}
                  products={data.products}
                  userId={data.user?.userId}
                  canApprove={can("count_approve")}
                  onPosted={() => load()}
                />
              )}
              {view === "taxes" && (
                <TaxSettings tenant={tenant} onSaved={() => load()} />
              )}
              {view === "lookups" && can("settings") && (
                <Retail
                  key={tenant + "lookups"}
                  tenant={tenant}
                  currency={currency}
                  approve={can("credit_approve")}
                  lookupAdmin={true}
                  mode="lookups"
                  language={language}
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
                        placeholder={tr("Search product name or SKU…")}
                        value={search}
                        onChange={(e) => {
                          setSearch(e.target.value);
                          setPage(0);
                        }}
                      />
                    </div>
                    <select
                      aria-label={tr("Category")}
                      value={category}
                      onChange={(e) => {
                        setCategory(e.target.value);
                        setPage(0);
                      }}
                    >
                      <option value="">{tr("All categories")}</option>
                      {categories.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                    <select
                      aria-label={tr("Stock status")}
                      value={filter}
                      onChange={(e) => {
                        setFilter(e.target.value);
                        setPage(0);
                      }}
                    >
                      <option value="">{tr("All statuses")}</option>
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
                              <th>{tr("Product")}</th>
                              <th>{tr("Category")}</th>
                              <th>{tr("Selling price")}</th>
                              <th>{tr("On hand")}</th>
                              <th>{tr("Reorder")}</th>
                              <th>{tr("Status")}</th>
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
                                    <b>{p.stock}</b> {tr("units")}{" "}
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
                                          {" "}
                                          {tr("Edit")}{" "}
                                          <SlidersHorizontal size={12} />
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
                                          {" "}
                                          {tr("Barcode label")}{" "}
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
                          {Math.min(page * 15 + 15, products.length)} {tr("of")}{" "}
                          {products.length} {tr("products")}{" "}
                        </span>
                        <div>
                          <button
                            className="mini"
                            disabled={!page}
                            onClick={() => setPage(page - 1)}
                          >
                            {" "}
                            {tr("Previous")}{" "}
                          </button>
                          <button
                            className="mini"
                            disabled={(page + 1) * 15 >= products.length}
                            onClick={() => setPage(page + 1)}
                          >
                            {" "}
                            {tr("Next")}{" "}
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
                    <PosEntry
                      key={tenant}
                      products={data.products}
                      busy={busy}
                      onAdd={add}
                    />
                    <div className="toolbar pos-toolbar">
                      <div className="search">
                        <Search size={17} />
                        <input
                          placeholder={tr("Search product name or SKU…")}
                          aria-label={tr("Search catalog")}
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                      <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        aria-label={tr("Product category")}
                      >
                        <option value="">{tr("All categories")}</option>
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
                                  {p.stock} {tr("in stock")}{" "}
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
                        {" "}
                        {tr("Current order")} <span>{units}</span>
                      </h2>
                      <button
                        className="icon-button"
                        aria-label={tr("Clear cart")}
                        disabled={busy}
                        onClick={() => {
                          setCart([]);
                          setPromotionCode("");
                          setDiscount("0");
                          setHeldId("");
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="actions">
                      <button
                        className="mini"
                        disabled={
                          busy || !quoteReady || !cart.length || !!heldId
                        }
                        data-hold-bill
                        onClick={holdCurrent}
                      >
                        {" "}
                        {tr("Hold bill")}{" "}
                      </button>
                      <select
                        aria-label={tr("Resume held bill")}
                        value={heldId}
                        disabled={busy || !!cart.length}
                        onChange={(e) => {
                          try {
                            resumeHeld(e.target.value);
                          } catch (err: any) {
                            setError(err.message);
                          }
                        }}
                      >
                        <option value="">{tr("Resume held bill…")}</option>
                        {heldBills.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <label className="customer">
                      <Users size={16} />
                      <input
                        aria-label={tr("Customer")}
                        placeholder={tr("Walk-in customer")}
                        value={customer}
                        disabled={busy}
                        onChange={(e) => setCustomer(e.target.value)}
                      />
                    </label>
                    {can("credit") && (
                      <CustomerSelect
                        tenant={tenant}
                        value={customerId}
                        onChange={(id, c) => {
                          setCustomerId(id);
                          setCustomer(c?.name || "");
                          if (!id) setCreditMode(false);
                        }}
                      />
                    )}
                    <div className="cart-items">
                      {cart.length ? (
                        cart.map((p) => (
                          <div className="cart-item" key={p.id}>
                            <div>
                              <b>{p.name}</b>
                              <small>
                                {money(p.price)} {tr("each")}
                              </small>
                              <div className="quantity">
                                <button
                                  disabled={busy}
                                  aria-label={"Decrease " + p.name}
                                  onClick={() => quantity(p.id, -1)}
                                >
                                  <Minus size={12} />
                                </button>
                                <input
                                  aria-label={"Quantity " + p.name}
                                  type="number"
                                  min="0.001"
                                  step="0.001"
                                  max={p.stock}
                                  value={p.quantity}
                                  onChange={(e) =>
                                    setCart(
                                      cart.map((item) =>
                                        item.id === p.id
                                          ? {
                                              ...item,
                                              quantity: Number(e.target.value),
                                            }
                                          : item,
                                      ),
                                    )
                                  }
                                />
                                <button
                                  disabled={busy}
                                  aria-label={"Increase " + p.name}
                                  onClick={() => quantity(p.id, 1)}
                                >
                                  <Plus size={12} />
                                </button>
                              </div>
                            </div>
                            <strong>
                              {money(Math.round(p.price * p.quantity))}
                            </strong>
                          </div>
                        ))
                      ) : (
                        <div className="cart-empty">
                          <ShoppingCart size={34} />
                          <h3>{tr("Your cart is empty")}</h3>
                          <p>{tr("Select a product to start an order.")}</p>
                        </div>
                      )}
                    </div>
                    <div className="cart-math">
                      <span>{tr("Subtotal")}</span>
                      <b>{money(subtotal)}</b>
                    </div>
                    <PromotionPicker
                      tenant={tenant}
                      value={promotionCode}
                      disabled={busy}
                      onChange={(code) => {
                        setPromotionCode(code);
                        if (code) setDiscount("0");
                      }}
                    />
                    {quoteReady && quote.promotion && (
                      <div className="cart-math">
                        <span>
                          {language === "ur"
                            ? quote.promotion.name_ur || quote.promotion.name
                            : quote.promotion.name}{" "}
                          · {quote.promotion.code}
                        </span>
                        <b>−{money(quote.discount)}</b>
                      </div>
                    )}
                    <div className="form-grid">
                      <label className="field">
                        <span>
                          {tr("Discount (")}
                          {currency})
                        </span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          max={subtotal / 100}
                          value={discount}
                          disabled={busy || !!promotionCode}
                          onChange={(e) => setDiscount(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>{tr("Tax (%)")}</span>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={taxRate}
                          disabled={busy || taxSettings?.mode !== "manual"}
                          onChange={(e) => setTaxRate(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="cart-math">
                      <span>{tr("Tax added")}</span>
                      <b>
                        {money(tax - (quoteReady ? quote.tax_included : 0))}
                      </b>
                    </div>
                    {quoteReady && quote.tax_included > 0 && (
                      <div className="cart-math">
                        <span>{tr("Tax included in prices")}</span>
                        <b>{money(quote.tax_included)}</b>
                      </div>
                    )}
                    {quoteError && (
                      <p role="alert" className="form-error">
                        {tr(quoteError)}
                      </p>
                    )}
                    {cart.length > 0 && !quoteReady && !quoteError && (
                      <p>{tr("Calculating tax…")}</p>
                    )}
                    <div className="cart-total">
                      <span>{tr("Total")}</span>
                      <strong>{money(total)}</strong>
                    </div>
                    {cart.some((p) => p.prescription_required) && (
                      <label className="field">
                        <span>{tr("Prescription reference")}</span>
                        <input
                          required
                          value={prescriptionRef}
                          onChange={(e) => setPrescriptionRef(e.target.value)}
                        />
                      </label>
                    )}
                    {can("credit") && customerId && (
                      <>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={creditMode}
                            disabled={busy}
                            onChange={(e) => setCreditMode(e.target.checked)}
                          />{" "}
                          {tr("Part payment / khata · ادھار")}{" "}
                        </label>
                        {creditMode && (
                          <div className="form-grid">
                            <label className="field">
                              <span>
                                {tr("Pay now (")}
                                {currency})
                              </span>
                              <input
                                type="number"
                                min="0"
                                max={total / 100}
                                step="0.01"
                                required
                                value={
                                  split ? (collected / 100).toString() : paidNow
                                }
                                disabled={split}
                                onChange={(e) => setPaidNow(e.target.value)}
                              />
                            </label>
                            <label className="field">
                              <span>{tr("Credit due date")}</span>
                              <input
                                type="date"
                                required
                                value={dueDate}
                                onChange={(e) => setDueDate(e.target.value)}
                              />
                            </label>
                          </div>
                        )}
                      </>
                    )}
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={split}
                        onChange={(e) => {
                          setSplit(e.target.checked);
                          setPaymentRows([]);
                        }}
                      />
                      {tr("Split payment")}
                    </label>
                    {split && (
                      <SplitPayments
                        tenant={tenant}
                        rows={paymentRows}
                        onChange={setPaymentRows}
                        busy={busy}
                      />
                    )}
                    {!split && (
                      <LookupSelect
                        tenant={tenant}
                        kind="payment_method"
                        label="Payment method"
                        value={methodId}
                        required={false}
                        onChange={(id, item) => {
                          setMethodId(id);
                          setPayment(
                            item?.code === "cash" ? "cash" : "external",
                          );
                        }}
                        language={language}
                      />
                    )}
                    {!split && (
                      <div className="payment-tabs">
                        <button
                          disabled={busy}
                          className={payment === "cash" ? "selected" : ""}
                          onClick={() => {
                            setPayment("cash");
                            setMethodId("");
                          }}
                        >
                          {" "}
                          {tr("Cash")}{" "}
                        </button>
                        <button
                          disabled={busy}
                          className={payment === "external" ? "selected" : ""}
                          onClick={() => {
                            setPayment("external");
                            setMethodId("");
                          }}
                        >
                          {" "}
                          {tr("Paid externally")}{" "}
                        </button>
                      </div>
                    )}
                    {(split ? cashCollected > 0 : payment === "cash") ? (
                      <label className="field">
                        <span>
                          {tr("Cash received (")}
                          {currency})
                        </span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={tendered}
                          disabled={busy}
                          onChange={(e) => setTendered(e.target.value)}
                        />
                        <strong
                          role="status"
                          aria-live="polite"
                          className="cash-change"
                        >
                          {tr("Change to return:")}{" "}
                          {money(
                            Math.max(
                              0,
                              Math.round(Number(tendered) * 100) -
                                cashCollected,
                            ),
                          )}
                        </strong>
                        {Math.round(Number(tendered || 0) * 100) <
                          cashCollected && (
                          <small>
                            {tr("Cash still required:")}{" "}
                            {money(
                              cashCollected -
                                Math.round(Number(tendered || 0) * 100),
                            )}
                          </small>
                        )}
                        <button
                          type="button"
                          disabled={busy || !quoteReady}
                          onClick={() =>
                            setTendered((cashCollected / 100).toFixed(2))
                          }
                        >
                          {tr("Exact cash")}
                        </button>
                      </label>
                    ) : (
                      <p className="hint">
                        {" "}
                        {tr(
                          "Records a payment already collected elsewhere. No card is charged.",
                        )}{" "}
                      </p>
                    )}
                    <button
                      className="primary checkout"
                      disabled={
                        busy ||
                        !quoteReady ||
                        !cart.length ||
                        discountCents > subtotal ||
                        discountCents < 0 ||
                        taxBps < 0 ||
                        taxBps > 10000 ||
                        (cashCollected > 0 &&
                          Number(tendered) * 100 < cashCollected) ||
                        collected < 0 ||
                        collected > total ||
                        (collected < total &&
                          (!creditMode || !customerId || !dueDate)) ||
                        (split &&
                          (!paymentRows.length ||
                            paymentRows.some(
                              (r) =>
                                !r.method_id ||
                                !Number.isFinite(Number(r.amount)) ||
                                Number(r.amount) <= 0,
                            )))
                      }
                      onClick={checkout}
                    >
                      {busy ? (
                        <Loader2 className="spin" size={17} />
                      ) : (
                        <Check size={17} />
                      )}{" "}
                      {tr("Complete sale")} <span>{money(total)}</span>
                    </button>
                    <p className="checkout-note">
                      <ShieldCheck size={12} />{" "}
                      {tr("Stock updates securely at checkout")}{" "}
                    </p>
                  </section>
                </div>
              )}
              {view === "sales" && can("sale") && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>{tr("Sales history")}</h2>
                      <p>
                        {" "}
                        {tr(
                          "Latest 500 receipts · refunds are recorded separately",
                        )}{" "}
                      </p>
                    </div>
                    <button className="secondary" onClick={csv}>
                      <Download size={15} /> {tr("Export CSV")}{" "}
                    </button>
                  </div>
                  {data.sales.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{tr("Receipt")}</th>
                            <th>{tr("Customer")}</th>
                            <th>{tr("Payment")}</th>
                            <th>{tr("Total")}</th>
                            <th>{tr("Status")}</th>
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
                              <td className="capitalize">{tr(s.payment)}</td>
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
                                    {" "}
                                    {tr("Receipt")}{" "}
                                  </button>
                                  {can("return") &&
                                    s.status === "completed" && (
                                      <button
                                        className="mini"
                                        onClick={() => open("return", s)}
                                      >
                                        {" "}
                                        {tr("Return")}{" "}
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
                      <h2>{tr("Stock ledger")}</h2>
                      <p>
                        {" "}
                        {tr(
                          "Latest 500 movements · positive quantities add stock",
                        )}{" "}
                      </p>
                    </div>
                    <ArrowLeftRight size={20} />
                  </div>
                  {data.movements.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{tr("Product")}</th>
                            <th>{tr("Movement")}</th>
                            <th>{tr("Quantity")}</th>
                            <th>{tr("Recorded by")}</th>
                            <th>{tr("Date")}</th>
                            <th>{tr("Notes")}</th>
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
                      <h3>{tr("Access that matches each responsibility")}</h3>
                      <p>
                        {" "}
                        {tr(
                          "Membership applies only to this business. Users sign in with their own email and password.",
                        )}{" "}
                      </p>
                    </div>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>{tr("Team members")}</h2>
                        <p>
                          {" "}
                          {tr(
                            "Create staff accounts or assign existing users. No invitation email is sent.",
                          )}{" "}
                        </p>
                      </div>
                      <span className="subtle-tag">
                        {data.members.length} {tr("members")}{" "}
                      </span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{tr("User")}</th>
                            <th>{tr("Role")}</th>
                            <th>{tr("Status")}</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {data.members.map((m: any) => (
                            <tr key={m.id}>
                              <td>
                                <b>{m.email}</b>
                              </td>
                              <td>{m.custom_name || m.role}</td>
                              <td>{badge(m.active ? "Active" : "Disabled")}</td>
                              <td>
                                {m.role !== "Owner" && (
                                  <div className="actions">
                                    <button
                                      className="mini"
                                      onClick={() => open("member", m)}
                                    >
                                      {" "}
                                      {tr("Change role")}{" "}
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
                                      {m.active ? tr("Disable") : tr("Enable")}
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
                      <h2>{tr("Role permissions")}</h2>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{tr("Permission")}</th>
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
                          {t.currency} {tr("· Created")}{" "}
                          {new Date(t.created).toLocaleDateString()}
                        </p>
                        <div className="actions">
                          <button
                            className="primary"
                            disabled={busy || t.status !== "active"}
                            onClick={() => switchTenant(t.id)}
                          >
                            {" "}
                            {tr("Open workspace")} <ArrowUpRight size={15} />
                          </button>
                          {data.user?.admin && (
                            <button
                              className="secondary"
                              onClick={() => open("tenantStatus", t)}
                            >
                              {t.status === "active"
                                ? tr("Suspend")
                                : tr("Reactivate")}
                            </button>
                          )}
                        </div>
                      </section>
                    ))}
                  </div>
                  {!data.tenants.length && (
                    <div className="welcome panel">
                      <Building2 size={36} />
                      <h2>{tr("Give your business a home.")}</h2>
                      <p>
                        {" "}
                        {tr(
                          "Create an isolated workspace for your inventory, sales and team.",
                        )}{" "}
                      </p>
                      {data.user?.admin && (
                        <button
                          className="primary"
                          onClick={() => open("tenant")}
                        >
                          <Plus size={16} /> {tr("Create business")}{" "}
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
              {view === "settings" && can("settings") && (
                <section className="panel settings">
                  <div className="panel-heading">
                    <h2>{tr("Business details")}</h2>
                  </div>
                  <dl>
                    <dt>{tr("Business name")}</dt>
                    <dd>{data.tenant?.name}</dd>
                    <dt>{tr("Currency")}</dt>
                    <dd>
                      {currency}{" "}
                      <small>
                        {" "}
                        {tr(
                          "Fixed after creation to preserve sales history.",
                        )}{" "}
                      </small>
                    </dd>
                    <dt>{tr("Business ID")}</dt>
                    <dd className="mono">{tenant}</dd>
                  </dl>
                  <button
                    className="secondary"
                    onClick={() => open("settings", data.tenant)}
                  >
                    {" "}
                    {tr("Edit business name")}{" "}
                  </button>
                  <div className="settings-note">
                    <ShieldCheck size={20} />
                    <p>
                      {" "}
                      {tr(
                        "Team access is enforced on the server. User accounts are managed by the platform and business owners. Staff can only access businesses where they have active membership.",
                      )}{" "}
                    </p>
                  </div>
                </section>
              )}
              {view === "audit" && can("audit") && (
                <AuditLog key={tenant} tenant={tenant} />
              )}
            </>
          )}
          {loading && !data.tenant && (
            <div className="loading">
              <Loader2 className="spin" />{" "}
              {tr("Connecting to your workspace…")}{" "}
            </div>
          )}
          <footer>
            <ShieldCheck size={13} /> {tr("StockDesk / Retail operations")}{" "}
            <span>
              {tr(
                "Management reports use Asia/Karachi; other sales charts use UTC.",
              )}
            </span>
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
                aria-label={tr("Close dialog")}
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
                      <LookupSelect
                        tenant={tenant}
                        kind="category"
                        label="Category"
                        name="category_id"
                        value={modal.item?.category_id}
                        language={language}
                      />
                    </div>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        name="expiry_required"
                        defaultChecked={modal.item?.expiry_required || false}
                      />{" "}
                      {tr("Batch and expiry required")}{" "}
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        name="prescription_required"
                        defaultChecked={
                          modal.item?.prescription_required || false
                        }
                      />{" "}
                      {tr("Prescription reference required at sale")}{" "}
                    </label>
                    {field(
                      "Generic name (optional)",
                      "generic_name",
                      "text",
                      modal.item?.generic_name || "",
                      false,
                    )}
                    {field(
                      "Strength (optional)",
                      "strength",
                      "text",
                      modal.item?.strength || "",
                      false,
                    )}
                    <LookupSelect
                      tenant={tenant}
                      kind="unit"
                      label="Selling unit"
                      name="unit_id"
                      value={modal.item?.unit_id}
                      language={language}
                    />
                    {field(
                      "Roman Urdu / search aliases",
                      "search_aliases",
                      "text",
                      modal.item?.search_aliases || "",
                      false,
                    )}
                    <label className="field">
                      <span>{tr("Tax profile")}</span>
                      <select
                        name="tax_profile_id"
                        defaultValue={modal.item?.tax_profile_id || ""}
                      >
                        <option value="">{tr("Business default")}</option>
                        {taxSettings?.profiles.map((p: any) => (
                          <option key={p.id} value={p.id} disabled={!p.active}>
                            {p.name} · {p.rate_bps / 100}%
                          </option>
                        ))}
                      </select>
                    </label>
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
                        />{" "}
                        {tr("Active product (available at checkout)")}{" "}
                      </label>
                    )}
                    <p className="hint">
                      {" "}
                      {tr(
                        "Stock changes are recorded through the ledger. Prices are stored with two decimal places.",
                      )}{" "}
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
                      <span>{tr("Product")}</span>
                      <select
                        name="product"
                        defaultValue={modal.item?.id || ""}
                        required
                      >
                        <option value="">{tr("Choose product")}</option>
                        {data.products
                          .filter((p: any) => p.active)
                          .map((p: any) => (
                            <option key={p.id} value={p.id}>
                              {p.sku} — {p.name} ({p.stock}{" "}
                              {tr("available)")}{" "}
                            </option>
                          ))}
                      </select>
                    </label>
                    <div className="form-grid">
                      <label className="field">
                        <span>{tr("Movement")}</span>
                        <select
                          name="type"
                          defaultValue={
                            modal.item?.batch_id ? tr("OUT") : tr("IN")
                          }
                        >
                          {!modal.item?.batch_id && (
                            <option value="IN">{tr("Stock IN")}</option>
                          )}
                          <option value="OUT">{tr("Stock OUT")}</option>
                        </select>
                      </label>
                      {field("Quantity", "quantity", "number", 1)}
                    </div>
                    <LookupSelect
                      tenant={tenant}
                      kind="adjustment_reason"
                      label="Adjustment reason"
                      name="reason_id"
                    />
                    {field(
                      "Batch number (required for tracked IN)",
                      "lot",
                      "text",
                      "",
                      false,
                    )}
                    {field(
                      "Expiry date (required for tracked IN)",
                      "expires",
                      "date",
                      "",
                      false,
                    )}
                    {field("Reason / reference", "notes")}
                    <p className="hint">
                      {" "}
                      {tr(
                        "Stock OUT cannot exceed available stock. Every change is recorded in the activity log.",
                      )}{" "}
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
                      <span>{tr("Role in this business")}</span>
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
                      {" "}
                      {tr(
                        "For a new account, provide a name and a password of at least 12 characters. Share credentials through your own secure channel. For existing users, name and password fields are ignored.",
                      )}{" "}
                    </p>
                  </>
                )}
                {modal.kind === "tenant" && (
                  <>
                    {field("Business name", "name")}
                    <label className="field">
                      <span>{tr("Business currency")}</span>
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
                      {" "}
                      {tr(
                        "Leave owner email blank to own this workspace yourself. Products, sales and team permissions are separate from other businesses.",
                      )}{" "}
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
                    <LookupSelect
                      tenant={tenant}
                      kind="return_reason"
                      label="Return reason"
                      name="reason_id"
                      required={false}
                    />
                    {field("Reason for return", "reason")}
                    <p className="hint">
                      {" "}
                      {tr(
                        "This returns the entire sale and restores all stock once. Refund the customer separately; this action does not move money.",
                      )}{" "}
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
                      ? tr("Suspending")
                      : tr("Reactivating")}{" "}
                    <b>{modal.item.name}</b>{" "}
                    {modal.item.status === "active"
                      ? tr(
                          "will block all inventory and sales access for this business.",
                        )
                      : tr("will restore access for active members.")}
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
                    {" "}
                    {tr("Cancel")}{" "}
                  </button>
                  <button className="primary" type="submit">
                    {busy ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Check size={16} />
                    )}{" "}
                    {modal.kind === "return"
                      ? tr("Confirm return")
                      : tr("Save changes")}
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
            aria-label={tr("Sales receipt")}
          >
            <div className="receipt-top">
              <Boxes size={30} />
              <h2>{receipt.sale.seller_name}</h2>
              <p>{receipt.sale.seller_address}</p>
              <small>{receipt.sale.seller_tax_number}</small>
              <p>
                {tr("Invoice ·")} {receipt.sale.invoice_number}
              </p>
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
                    {i.quantity} {tr(i.unit_name || "")} × {money(i.price)}
                  </small>
                </div>
                <strong>
                  {money(i.line_total ?? Math.round(i.price * i.quantity))}
                </strong>
              </div>
            ))}
            <div className="cart-math">
              <span>{tr("Subtotal")}</span>
              <b>{money(receipt.sale.subtotal)}</b>
            </div>
            <div className="cart-math">
              <span>{tr("Discount")}</span>
              <b>−{money(receipt.sale.discount)}</b>
            </div>
            {(() => {
              const p =
                typeof receipt.sale.promotion_snapshot === "string"
                  ? JSON.parse(receipt.sale.promotion_snapshot)
                  : receipt.sale.promotion_snapshot;
              return p?.code ? (
                <p>
                  {tr("Promotion")}: {p.code} ·{" "}
                  {language === "ur" ? p.name_ur || p.name : p.name}
                </p>
              ) : null;
            })()}

            <div className="cart-math">
              <span>{tr("Tax added")}</span>
              <b>
                {money(receipt.sale.tax - (receipt.sale.tax_included || 0))}
              </b>
            </div>
            <div className="receipt-total">
              <b>{tr("Total")}</b>
              <strong>{money(receipt.sale.total)}</strong>
            </div>
            {receipt.sale.tax_included > 0 && (
              <div className="cart-math">
                <span>{tr("Tax included in prices")}</span>
                <b>{money(receipt.sale.tax_included)}</b>
              </div>
            )}
            <p className="hint">
              {" "}
              {tr("Payment:")}{" "}
              {receipt.tenders?.length > 1
                ? tr("Split payment")
                : receipt.sale.payment === "cash"
                  ? tr("Cash")
                  : tr("Collected externally")}
              <br /> {tr("Served by")} {receipt.sale.actor}
            </p>
            <div className="cart-math">
              <span>{tr("Paid now / وصول")}</span>
              <b>{money(receipt.sale.paid_now ?? receipt.sale.total)}</b>
            </div>
            <div className="cart-math">
              <span>{tr("Khata / ادھار")}</span>
              <b>{money(receipt.sale.credit_amount || 0)}</b>
            </div>
            {receipt.sale.cash_amount > 0 && (
              <>
                <div className="cart-math">
                  <span>{tr("Cash received")}</span>
                  <b>{money(receipt.sale.cash_received)}</b>
                </div>
                <div className="receipt-total">
                  <span>{tr("Change returned")}</span>
                  <strong>{money(receipt.sale.change)}</strong>
                </div>
              </>
            )}
            {receipt.tenders?.map((r: any, i: number) => (
              <div className="cart-math" key={i}>
                <span>
                  {language === "ur" && r.method_name_ur
                    ? r.method_name_ur
                    : tr(r.method_name)}
                </span>
                <b>{money(r.amount)}</b>
              </div>
            ))}
            <p className="receipt-thanks">
              {tr("Thank you for your business.")}
            </p>
            <div className="modal-actions no-print">
              <button className="secondary" onClick={() => setReceipt(null)}>
                {" "}
                {tr("Close")}{" "}
              </button>
              <a
                className="secondary"
                href={
                  "/api/invoices/" +
                  receipt.sale.id +
                  ".pdf?tenant=" +
                  encodeURIComponent(tenant) +
                  "&language=" +
                  language
                }
              >
                <Download size={16} /> {tr("PDF")}{" "}
              </a>
              <button className="primary" onClick={() => window.print()}>
                <Printer size={16} /> {tr("Print receipt")}{" "}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
