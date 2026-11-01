"""Tenancy commands. Caller owns authorization and transaction scope."""

from ..rules import clean, boolean, fail, email, ROLES
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
    await c.execute(
        "UPDATE tenants SET name=$1,address=$2,tax_number=$3 WHERE id=$4",
        clean(b.get("name"), "Name", 100),
        clean(b.get("address", ""), "Address", 500, True),
        clean(b.get("tax_number", ""), "Tax number", 100, True),
        tenant,
    )
    await audit(c, tenant, u, "Business settings updated", {})
    return {"ok": True}
