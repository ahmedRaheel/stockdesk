import { useEffect, useState } from "react";
import { api } from "./api";
import { t as tr } from "./i18n";
export default function MembershipStatus({
  tenant,
  customer,
}: {
  tenant: string;
  customer: string;
}) {
  const [membership, setMembership] = useState<{
      number: string;
      plan_name: string;
      benefits: string;
      valid_until: string;
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    setMembership(null);
    setError("");
    let generation = 0;
    async function refresh() {
      const current = ++generation;
      try {
        const r = await api<{ membership: typeof membership }>(
          `/api/v1/tenants/${tenant}/sale-customers/${customer}/membership`,
          { signal: c.signal },
        );
        if (!c.signal.aborted && current === generation) {
          setMembership(r.membership);
          setError("");
        }
      } catch (e) {
        if (!c.signal.aborted && current === generation) {
          setMembership(null);
          setError((e as Error).message);
        }
      }
    }
    if (!customer) return () => c.abort();
    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 60000);
    return () => {
      clearInterval(timer);
      c.abort();
    };
  }, [tenant, customer]);
  if (!customer) return null;
  if (error)
    return (
      <small role="status">
        {tr("Membership status unavailable. Reload to check.")}
      </small>
    );
  if (!membership) return null;
  return (
    <div className="pos-membership">
      <strong>
        {tr("Active membership")}: {membership.plan_name}
      </strong>
      <small>
        {membership.number} · {tr("Valid through")}:{" "}
        <span dir="ltr">{membership.valid_until}</span>
      </small>
      <p>{membership.benefits}</p>
      <small>{tr("Membership does not automatically change this bill.")}</small>
    </div>
  );
}
