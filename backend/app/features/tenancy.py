"""Tenancy commands. Caller owns authorization and transaction scope."""

from ..rules import clean, boolean, fail, email, ROLES
import re
from ..service import uid, audit, create_account


async def create_business(c, u, b, t=None):
    tenant = b.get("tenant", "")
    if not u["is_admin"]:
        fail("Only the platform administrator can create businesses.", 403)
    currency = clean(b.get("currency"), "Currency", 3)
    if currency not in ["PKR", "USD", "SAR", "AED", "EUR", "GBP"]:
        fail("Unsupported currency.")
    name = clean(b.get("name"), "Business name", 100)
    owner = u
    if b.get("owner_email"):
        owner = await create_account(
            c, email(b["owner_email"]), b.get("owner_name"), b.get("owner_password")
        )
    tid = uid()
    await c.execute(
        "INSERT INTO tenants(id,name,currency) VALUES($1,$2,$3)", tid, name, currency
    )
    await c.execute(
        "INSERT INTO members(id,tenant,user_id,role) VALUES($1,$2,$3,'Owner')",
        uid(),
        tid,
        owner["id"],
    )
    await audit(c, tid, u, "Business created", {"name": name, "owner": owner["email"]})
    return {"id": tid}


async def change_business_status(c, u, b, t=None):
    tenant = b.get("tenant", "")
    if not u["is_admin"]:
        fail("Platform administrator only.", 403)
    t = await c.fetchrow("SELECT * FROM tenants WHERE id=$1 FOR UPDATE", tenant)
    if not t:
        fail("Business not found.", 404)
    if b.get("status") not in ["active", "suspended"]:
        fail("Invalid status.")
    await c.execute("UPDATE tenants SET status=$1 WHERE id=$2", b["status"], tenant)
    await audit(c, tenant, u, "Business status changed", {"status": b["status"]})
    return {"ok": True}


async def assign_member(c, u, b, t=None):
    tenant = b.get("tenant", "")
    address = email(b.get("email"))
    role = b.get("role")
    if role not in ROLES:
        fail("Invalid role.")
    account = await create_account(c, address, b.get("name"), b.get("password"))
    previous = await c.fetchrow(
        "SELECT * FROM members WHERE tenant=$1 AND user_id=$2", tenant, account["id"]
    )
    if previous and previous["role"] == "Owner" and (role != "Owner"):
        fail("An owner cannot be demoted here.")
    await c.execute(
        "INSERT INTO members(id,tenant,user_id,role) VALUES($1,$2,$3,$4) ON CONFLICT(tenant,user_id) DO UPDATE SET role=excluded.role,custom_role_id=NULL,active=true",
        uid(),
        tenant,
        account["id"],
        role,
    )
    await audit(c, tenant, u, "Team access assigned", {"email": address, "role": role})
    return {"ok": True}


async def set_member_status(c, u, b, t=None):
    tenant = b.get("tenant", "")
    mid = clean(b.get("id"), "Member ID", 100)
    member = await c.fetchrow(
        "SELECT * FROM members WHERE tenant=$1 AND id=$2", tenant, mid
    )
    if not member:
        fail("Member not found.", 404)
    if member["role"] == "Owner":
        fail("Owner accounts cannot be disabled here.")
    active = boolean(b.get("active"))
    await c.execute(
        "UPDATE members SET active=$1 WHERE tenant=$2 AND id=$3", active, tenant, mid
    )
    await audit(c, tenant, u, "Team access changed", {"id": mid, "active": active})
    return {"ok": True}


async def update_business(c, u, b, t=None):
    tenant = b.get("tenant", "")
    existing = dict(t) if t is not None else {}
    # Invoice identity is tenant-owned and validated on the server. Values are
    # snapshotted on each sale so later profile edits never rewrite old invoices.
    fields = {
        "name": clean(b.get("name"), "Business name", 100),
        "address": clean(b.get("address", existing.get("address", "")), "Business address", 500, True),
        "tax_number": clean(b.get("tax_number", existing.get("tax_number", "")), "Tax number", 100, True),
        "branch_name": clean(b.get("branch_name", existing.get("branch_name", "")), "Branch name", 100, True),
        "shop_number": clean(b.get("shop_number", existing.get("shop_number", "")), "Shop number", 80, True),
        "business_type": clean(b.get("business_type", existing.get("business_type", "retail")), "Business type", 40),
        "phone": clean(b.get("phone", existing.get("phone", "")), "Phone", 40, True),
        "email": clean(b.get("email", existing.get("email", "")), "Business email", 254, True),
        "website": clean(b.get("website", existing.get("website", "")), "Website", 200, True),
        "ntn": clean(b.get("ntn", existing.get("ntn", "")), "NTN", 40, True),
        "strn": clean(b.get("strn", existing.get("strn", "")), "STRN", 40, True),
        "invoice_title": clean(b.get("invoice_title", existing.get("invoice_title", "CASH INVOICE")), "Invoice title", 60),
        "invoice_header": clean(b.get("invoice_header", existing.get("invoice_header", "")), "Invoice header", 500, True),
        "invoice_footer": clean(b.get("invoice_footer", existing.get("invoice_footer", "Thank you for your business.")), "Invoice footer", 500, True),
        "return_policy": clean(b.get("return_policy", existing.get("return_policy", "")), "Return policy", 1000, True),
        "exchange_policy": clean(b.get("exchange_policy", existing.get("exchange_policy", "")), "Exchange policy", 1000, True),
        "pos_charge_label": clean(b.get("pos_charge_label", existing.get("pos_charge_label", "POS Charges")), "POS charge label", 60),
        "receipt_width": clean(b.get("receipt_width", existing.get("receipt_width", "80mm")), "Receipt width", 10),
        "logo_url": clean(b.get("logo_url", existing.get("logo_url", "")), "Logo URL", 500, True),
    }
    if fields["business_type"] not in ("retail", "grocery", "pharmacy", "restaurant", "wholesale", "other"):
        fail("Invalid business type.")
    if fields["receipt_width"] not in ("58mm", "80mm", "A4"):
        fail("Invalid receipt width.")
    if fields["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]):
        fail("Enter a valid business email.")
    if fields["logo_url"] and not (fields["logo_url"].startswith("https://") or re.fullmatch(r"/api/v1/business-logos/[a-f0-9]{64}\.png", fields["logo_url"])):
        fail("Business logo must use HTTPS or a StockDesk-managed asset.")
    pos_charge = b.get("pos_charge", existing.get("pos_charge", 0))
    if isinstance(pos_charge, bool) or not isinstance(pos_charge, int) or pos_charge < 0 or pos_charge > 100_000_000:
        fail("POS charge must be a non-negative amount in minor currency units.")
    await c.execute(
        """UPDATE tenants SET name=$1,address=$2,tax_number=$3,branch_name=$4,
        shop_number=$5,business_type=$6,phone=$7,email=$8,website=$9,ntn=$10,
        strn=$11,invoice_title=$12,invoice_header=$13,invoice_footer=$14,
        return_policy=$15,exchange_policy=$16,pos_charge_label=$17,
        pos_charge=$18,receipt_width=$19,logo_url=$20 WHERE id=$21""",
        fields["name"], fields["address"], fields["tax_number"], fields["branch_name"],
        fields["shop_number"], fields["business_type"], fields["phone"], fields["email"],
        fields["website"], fields["ntn"], fields["strn"], fields["invoice_title"],
        fields["invoice_header"], fields["invoice_footer"], fields["return_policy"],
        fields["exchange_policy"], fields["pos_charge_label"], pos_charge,
        fields["receipt_width"], fields["logo_url"], tenant,
    )
    await audit(c, tenant, u, "Business invoice profile updated", {
        "business_type": fields["business_type"], "receipt_width": fields["receipt_width"],
        "tax_registration_updated": bool(fields["ntn"] or fields["strn"] or fields["tax_number"]),
    })
    return {"ok": True}
