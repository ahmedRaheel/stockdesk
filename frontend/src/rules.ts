export const ROLES = ["Owner", "Manager", "Cashier", "Stock Manager"] as const;
export const permissions: Record<string, string[]> = {
  Owner: [
    "credit",
    "credit_approve",
    "cost",
    "forecast",
    "read",
    "product",
    "stock",
    "sale",
    "return",
    "team",
    "settings",
  ],
  Manager: [
    "credit",
    "credit_approve",
    "cost",
    "forecast",
    "read",
    "product",
    "stock",
    "sale",
    "return",
  ],
  Cashier: ["credit", "read", "sale"],
  "Stock Manager": ["cost", "forecast", "read", "product", "stock"],
};
export function allowed(role: string, permission: string) {
  return !!permissions[role]?.includes(permission);
}
export function requirePermission(role: string, permission: string) {
  if (!allowed(role, permission))
    throw new Error("Forbidden: your role cannot perform this action.");
}
export function clean(v: unknown, label: string, max = 150) {
  if (typeof v !== "string" || !v.trim() || v.trim().length > max)
    throw new Error(`${label} is required (maximum ${max} characters).`);
  return v.trim();
}
export function num(v: unknown, label: string, min = 0, max = 100000000) {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < min || v > max)
    throw new Error(
      `${label} must be a whole number between ${min} and ${max}.`,
    );
  return v;
}
export function email(v: unknown) {
  const s = clean(v, "Email", 254).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s))
    throw new Error("Enter a valid email address.");
  return s;
}
export function normalizeCart(v: unknown) {
  if (!Array.isArray(v) || !v.length || v.length > 100)
    throw new Error("Cart must contain 1–100 products.");
  const seen = new Set();
  return v
    .map((x) => {
      const id = clean(x.id, "Product");
      if (seen.has(id)) throw new Error("Duplicate cart product.");
      seen.add(id);
      return { id, quantity: num(x.quantity, "Quantity", 1, 100000) };
    })
    .sort((a, b) => a.id.localeCompare(b.id));
}
