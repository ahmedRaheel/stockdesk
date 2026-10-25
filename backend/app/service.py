"""All writes run in one database transaction, with a tenant row lock.
The tenant lock serializes checkout, returns, price edits and role changes.
The ledger trigger and database CHECK prevent negative stock independently.
"""

import json, uuid
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
from .rules import ROLES, clean, fail, require_permission, EffectiveRole, grants
from .security import hash_password


def uid():
    return str(uuid.uuid4())


def rows(values):
    return [dict(r) for r in values]


def public_user(u):
    return {
        "userId": u["id"],
        "email": u["email"],
        "displayName": u["name"],
        "admin": u["is_admin"],
    }


async def audit(c, tenant, u, action, detail):
    await c.execute(
        "INSERT INTO audit(id,tenant,actor,action,details) VALUES($1,$2,$3,$4,$5)",
        uid(),
        tenant,
        u["email"],
        action,
        json.dumps(detail, default=str),
    )


async def authorize(c, u, tenant, permission="read", lock=False):
    t = await c.fetchrow(
        "SELECT * FROM tenants WHERE id=$1" + (" FOR UPDATE" if lock else ""), tenant
    )
    if not t:
        fail("Business not found.", 404)
    if t["status"] != "active":
        fail("This business is suspended.", 403)
    role = "Owner"
    if not u["is_admin"]:
        member = await c.fetchrow(
            "SELECT role,custom_role_id FROM members WHERE tenant=$1 AND user_id=$2 AND active=true",
            tenant,
            u["id"],
        )
        if not member:
            fail("You do not have access to this business.", 403)
        role = member["role"]
        if member["custom_role_id"]:
            custom = await c.fetchrow(
                "SELECT name FROM tenant_roles WHERE tenant=$1 AND id=$2 AND active=true",
                tenant,
                member["custom_role_id"],
            )
            if not custom:
                fail("Your assigned role is disabled. Contact the business owner.", 403)
            permissions = await c.fetch(
                "SELECT permission FROM tenant_role_permissions WHERE tenant=$1 AND role_id=$2",
                tenant,
                member["custom_role_id"],
            )
            role = EffectiveRole(custom["name"], [p["permission"] for p in permissions])
    require_permission(role, permission)
    return t, role


async def get_receipt(c, u, tenant, sale_id):
    _business, receipt_role = await authorize(c, u, tenant, "sale")
    sale = await c.fetchrow(
        "SELECT * FROM sales WHERE tenant=$1 AND id=$2", tenant, sale_id
    )
    if not sale:
        fail("Invoice not found.", 404)
    result = {
        "sale": dict(sale),
        "items": rows(
            await c.fetch(
                "SELECT * FROM sale_items WHERE tenant=$1 AND sale=$2 ORDER BY sku",
                tenant,
                sale_id,
            )
        ),
    }
    result["tenders"] = rows(
        await c.fetch(
            "SELECT method_name,method_name_ur,is_cash,amount,reference FROM sale_tenders WHERE tenant=$1 AND sale=$2 ORDER BY id",
            tenant,
            sale_id,
        )
    )
    result["sale"].pop("original_snapshot", None)
    result["sale"]["adjustments"] = [
        json.loads(r["result"]) if isinstance(r["result"], str) else r["result"]
        for r in await c.fetch(
            "SELECT result FROM sale_adjustments WHERE tenant=$1 AND sale=$2 ORDER BY revision",
            tenant,
            sale_id,
        )
    ]
    cash = sale["cash_amount"]
    result["sale"]["cash_received"] = sale["tendered"] if cash else 0
    result["sale"]["change"] = max(0, sale["tendered"] - cash) if cash else 0
    if "cost" not in grants(receipt_role):
        for item in result["items"]:
            item.pop("cost", None)
    return result


async def snapshot(c, u, tenant):
    tenants = rows(
        await c.fetch("SELECT * FROM tenants ORDER BY created")
        if u["is_admin"]
        else await c.fetch(
            "SELECT t.* FROM tenants t JOIN members m ON m.tenant=t.id WHERE m.user_id=$1 AND m.active=true ORDER BY t.created",
            u["id"],
        )
    )
    out = {
        "user": public_user(u),
        "tenants": tenants,
        "permissions": [],
        "products": [],
        "sales": [],
        "movements": [],
        "members": [],
        "audit": [],
        "trend": [],
    }
    if not tenant:
        return out
    t, role = await authorize(c, u, tenant)
    perms = grants(role)
    out.update(tenant=dict(t), role=role, permissions=sorted(perms))
    out["products"] = rows(
        await c.fetch("SELECT * FROM products WHERE tenant=$1 ORDER BY name", tenant)
    )
    out["movements"] = rows(
        await c.fetch(
            "SELECT m.*,p.name,p.sku FROM movements m JOIN products p ON p.id=m.product AND p.tenant=m.tenant WHERE m.tenant=$1 ORDER BY m.created DESC LIMIT 500",
            tenant,
        )
    )
    if "sale" in perms:
        out["sales"] = rows(
            await c.fetch(
                "SELECT * FROM sales WHERE tenant=$1 ORDER BY created DESC LIMIT 500",
                tenant,
            )
        )
        for sale in out["sales"]:
            sale.pop("original_snapshot", None)
        out["stats"] = dict(
            await c.fetchrow(
                "SELECT COUNT(*) AS orders,COALESCE(SUM(total),0)::bigint AS revenue,COALESCE(SUM(total) FILTER(WHERE (created AT TIME ZONE 'UTC')::date=(now() AT TIME ZONE 'UTC')::date),0)::bigint AS today FROM sales WHERE tenant=$1 AND status='completed'",
                tenant,
            )
        )
        trend = rows(
            await c.fetch(
                "SELECT (created AT TIME ZONE 'UTC')::date::text AS day,SUM(total)::bigint AS total FROM sales WHERE tenant=$1 AND status='completed' AND created>=(date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')-interval '6 days' GROUP BY 1 ORDER BY 1",
                tenant,
            )
        )
        out["trend"] = trend
        dates = [
            (datetime.now(timezone.utc) - timedelta(days=6 - i)).strftime("%Y-%m-%d")
            for i in range(7)
        ]
        amounts = {r["day"]: r["total"] / 100 for r in trend}
        fig = go.Figure(
            go.Bar(
                x=dates,
                y=[amounts.get(d, 0) for d in dates],
                marker_color="#426b9d",
                hovertemplate="%{x}<br>%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white",
            height=235,
            margin=dict(l=45, r=10, t=10, b=35),
            font=dict(family="Arial", size=11),
            yaxis_title=t["currency"],
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        out["salesChart"] = json.loads(fig.to_json())
    active = [p for p in out["products"] if p["active"]]
    counts = [
        sum(p["stock"] > p["reorder"] for p in active),
        sum(0 < p["stock"] <= p["reorder"] for p in active),
        sum(p["stock"] == 0 for p in active),
    ]
    fig = go.Figure(
        go.Pie(
            labels=["In stock", "Low stock", "Out of stock"],
            values=counts,
            hole=0.72,
            marker_colors=["#426b9d", "#bb8a37", "#b9645d"],
            textinfo="none",
            hovertemplate="%{label}: %{value}<extra></extra>",
            sort=False,
        )
    )
    fig.update_layout(
        height=220,
        margin=dict(l=0, r=0, t=10, b=25),
        showlegend=True,
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.05, font_size=10),
        annotations=[
            dict(text=str(len(active)), x=0.5, y=0.5, font_size=28, showarrow=False)
        ],
        paper_bgcolor="rgba(0,0,0,0)",
    )
    out["healthChart"] = json.loads(fig.to_json())
    if "team" in perms:
        out["members"] = rows(
            await c.fetch(
                "SELECT m.*,u.email,u.name,r.name AS custom_name FROM members m JOIN users u ON u.id=m.user_id LEFT JOIN tenant_roles r ON r.tenant=m.tenant AND r.id=m.custom_role_id WHERE m.tenant=$1 ORDER BY u.email",
                tenant,
            )
        )
    if "audit" in perms:
        out["audit"] = rows(
            await c.fetch(
                "SELECT * FROM audit WHERE tenant=$1 ORDER BY created DESC LIMIT 100",
                tenant,
            )
        )
    if "cost" not in perms:
        for product in out["products"]:
            product.pop("cost", None)

    return out


async def create_account(c, address, name, pwd):
    existing = await c.fetchrow("SELECT * FROM users WHERE email=$1", address)
    if existing:
        return existing
    user_id = uid()
    hashed = await hash_password(pwd)
    return await c.fetchrow(
        "INSERT INTO users(id,email,name,password_hash) VALUES($1,$2,$3,$4) RETURNING *",
        user_id,
        address,
        clean(name, "Name"),
        hashed,
    )


async def execute(c, u, b):
    """Dispatch legacy and v1 commands through one transaction/authorization boundary."""
    from .features import catalog, inventory, sales, tenancy

    action = b.get("action")
    tenant = clean(b.get("tenant", ""), "Business ID", 100, optional=True)
    command = {**b, "tenant": tenant}
    administrative = {
        "tenant": tenancy.create_business,
        "tenantStatus": tenancy.change_business_status,
    }
    if action in administrative:
        return await administrative[action](c, u, command)
    handlers = {
        "product": ("product", catalog.save_product),
        "editProduct": ("product", catalog.save_product),
        "movement": ("stock", inventory.adjust_stock),
        "checkout": ("sale", sales.checkout),
        "return": ("return", sales.return_sale),
        "member": ("team", tenancy.assign_member),
        "memberStatus": ("team", tenancy.set_member_status),
        "settings": ("settings", tenancy.update_business),
    }
    if action not in handlers:
        fail("Unknown action.")
    permission, handler = handlers[action]
    business, _role = await authorize(c, u, tenant, permission, lock=True)
    return await handler(c, u, command, business)
