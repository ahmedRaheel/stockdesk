"""Purchasing approvals, quoted prices and observed supplier performance."""

from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from pydantic import Field
from .contracts import Contract, Identifier, Money, Quantity
from .router import User, authenticated
from .payables import today
from .. import db, service, security
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}",
    dependencies=[Depends(authenticated)],
    tags=["Purchasing controls"],
)


class Policy(Contract):
    enabled: bool = Field(strict=True)
    threshold: Money
    version: int = Field(strict=True, ge=0)


class Decision(Contract):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=1, max_length=500)


class PriceTier(Contract):
    minimum_quantity: Quantity
    unit_cost: Money


class Offer(Contract):
    # Omission preserves existing tiers on updates for older clients. [] clears them.
    tiers: list[PriceTier] | None = Field(default=None, max_length=20)
    supplier: Identifier
    product: Identifier
    unit_cost: Money
    minimum_quantity: Quantity = Decimal(1)
    lead_days: int = Field(strict=True, ge=0, le=365)
    valid_from: date
    valid_until: date | None = None
    active: bool = Field(default=True, strict=True)
    notes: str = Field(default="", max_length=500)


class OfferUpdate(Offer):
    version: int = Field(strict=True, ge=1)


@router.get("/purchasing-policy")
async def get_policy(tenant: str, user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c, user, tenant, "stock")
        row = await c.fetchrow(
            "SELECT * FROM purchasing_policies WHERE tenant=$1", tenant
        )
        return dict(row) if row else {"enabled": False, "threshold": 0, "version": 0}


@router.put("/purchasing-policy")
async def policy(tenant: str, payload: Policy, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            # Policy bypass must not be delegatable through business-settings permission.
            await service.authorize(c, user, tenant, "roles", lock=True)
            prior = await c.fetchrow(
                "SELECT * FROM purchasing_policies WHERE tenant=$1", tenant
            )
            if payload.version != (prior["version"] if prior else 0):
                fail("Purchasing policy changed. Reload before saving.", 409)
            await c.execute(
                "INSERT INTO purchasing_policies(tenant,enabled,threshold,version) VALUES($1,$2,$3,1) ON CONFLICT(tenant) DO UPDATE SET enabled=excluded.enabled,threshold=excluded.threshold,version=purchasing_policies.version+1",
                tenant,
                payload.enabled,
                payload.threshold,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Purchasing approval policy changed",
                payload.model_dump(),
            )
    return {"ok": True}


@router.post("/purchase-orders/{identifier}/decision")
async def decide(
    tenant: str, identifier: str, payload: Decision, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "purchase_approve", lock=True)
            row = await c.fetchrow(
                "SELECT * FROM purchase_orders WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not row:
                fail("Purchase order not found.", 404)
            if row["actor"] == user["email"]:
                fail(
                    "A different user must approve or reject this purchase order.", 403
                )
            if row["decision"]:
                if (
                    row["decision"] == payload.decision
                    and row["decision_note"] == payload.note
                    and row["decided_by"] == user["id"]
                ):
                    return {"ok": True, "replayed": True}
                fail("A decision has already been recorded.", 409)
            if row["status"] != "pending_approval" or not row["approval_required"]:
                fail("Only pending orders can be decided.", 409)
            await c.execute(
                "UPDATE purchase_orders SET status=$1,decision=$2,decision_note=$3,decided_by=$4,decided_on=now() WHERE tenant=$5 AND id=$6",
                "open" if payload.decision == "approve" else "rejected",
                payload.decision,
                payload.note,
                user["id"],
                tenant,
                identifier,
            )
            await service.audit(
                c,
                tenant,
                user,
                "Purchase order decision",
                {"id": identifier, **payload.model_dump()},
            )
    return {"ok": True}


async def save_offer(c, user, tenant, payload, identifier=None):
    if payload.valid_until and payload.valid_until < payload.valid_from:
        fail("Quote expiry cannot precede its start date.")
    if not await c.fetchval(
        "SELECT 1 FROM suppliers WHERE tenant=$1 AND id=$2", tenant, payload.supplier
    ):
        fail("Supplier not found.", 404)
    product = await c.fetchrow(
        "SELECT p.*,u.fractional FROM products p JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id WHERE p.tenant=$1 AND p.id=$2",
        tenant,
        payload.product,
    )
    if not product or (payload.active and not product["active"]):
        fail("Active product not found.", 404)
    if not product["fractional"] and payload.minimum_quantity != int(
        payload.minimum_quantity
    ):
        fail("This product requires whole quantities.")
    tiers = payload.tiers
    if tiers is None:
        tiers = [
            PriceTier(**dict(row))
            for row in await c.fetch(
                "SELECT minimum_quantity,unit_cost FROM supplier_offer_tiers WHERE tenant=$1 AND offer=$2 ORDER BY minimum_quantity",
                tenant,
                identifier or "",
            )
        ]
    tiers = sorted(tiers, key=lambda tier: tier.minimum_quantity)
    previous_quantity, previous_cost = payload.minimum_quantity, payload.unit_cost
    for tier in tiers:
        if tier.minimum_quantity <= previous_quantity:
            fail("Price breaks must have unique quantities above the base minimum.")
        if tier.unit_cost >= previous_cost:
            fail("Each price break must reduce the preceding unit cost.")
        if not product["fractional"] and tier.minimum_quantity != int(
            tier.minimum_quantity
        ):
            fail("This product requires whole quantities.")
        previous_quantity, previous_cost = tier.minimum_quantity, tier.unit_cost
    if identifier:
        old = await c.fetchrow(
            "SELECT * FROM supplier_offers WHERE tenant=$1 AND id=$2",
            tenant,
            identifier,
        )
        if not old:
            fail("Supplier quote not found.", 404)
        if old["version"] != payload.version:
            fail("Supplier quote changed. Reload before saving.", 409)
        if old["supplier"] != payload.supplier or old["product"] != payload.product:
            fail("A quote’s supplier and product cannot be changed.")
        await c.execute(
            "UPDATE supplier_offers SET unit_cost=$1,minimum_quantity=$2,lead_days=$3,valid_from=$4,valid_until=$5,active=$6,notes=$7,version=version+1,updated=now() WHERE tenant=$8 AND id=$9",
            payload.unit_cost,
            payload.minimum_quantity,
            payload.lead_days,
            payload.valid_from,
            payload.valid_until,
            payload.active,
            payload.notes,
            tenant,
            identifier,
        )
    else:
        if await c.fetchval(
            "SELECT 1 FROM supplier_offers WHERE tenant=$1 AND supplier=$2 AND product=$3",
            tenant,
            payload.supplier,
            payload.product,
        ):
            fail(
                "A quote already exists for this supplier and product. Edit that quote.",
                409,
            )
        identifier = service.uid()
        await c.execute(
            "INSERT INTO supplier_offers(id,tenant,supplier,product,unit_cost,minimum_quantity,lead_days,valid_from,valid_until,active,notes) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
            identifier,
            tenant,
            payload.supplier,
            payload.product,
            payload.unit_cost,
            payload.minimum_quantity,
            payload.lead_days,
            payload.valid_from,
            payload.valid_until,
            payload.active,
            payload.notes,
        )
    await c.execute(
        "DELETE FROM supplier_offer_tiers WHERE tenant=$1 AND offer=$2",
        tenant,
        identifier,
    )
    for tier in tiers:
        await c.execute(
            "INSERT INTO supplier_offer_tiers(tenant,offer,minimum_quantity,unit_cost) VALUES($1,$2,$3,$4)",
            tenant,
            identifier,
            tier.minimum_quantity,
            tier.unit_cost,
        )
    await service.audit(
        c,
        tenant,
        user,
        "Supplier quote saved",
        {
            "id": identifier,
            **payload.model_dump(mode="json"),
            "tiers": [t.model_dump(mode="json") for t in tiers],
        },
    )
    return {"id": identifier}


@router.post("/supplier-offers", status_code=201)
async def create_offer(tenant: str, payload: Offer, request: Request, user: User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "stock", lock=True)
            return await save_offer(c, user, tenant, payload)


@router.put("/supplier-offers/{identifier}")
async def update_offer(
    tenant: str, identifier: str, payload: OfferUpdate, request: Request, user: User
):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c, user, tenant, "stock", lock=True)
            return await save_offer(c, user, tenant, payload, identifier)


@router.get("/supplier-offers")
async def offers(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    product: str = "",
    supplier: str = "",
    quantity: Decimal = Query(
        Decimal(1), gt=0, le=1_000_000, max_digits=12, decimal_places=3
    ),
    eligible: bool = False,
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "stock")
            rows = await c.fetch(
                """SELECT o.*,s.name AS supplier_name,p.name AS product_name,p.sku,u.name AS unit_name,
      COALESCE(tier.unit_cost,o.unit_cost) AS effective_unit_cost,
      COALESCE(tier.minimum_quantity,o.minimum_quantity) AS applied_minimum_quantity,
      CASE WHEN ROUND(COALESCE(tier.unit_cost,o.unit_cost)*$4)<=100000000000 THEN ROUND(COALESCE(tier.unit_cost,o.unit_cost)*$4)::bigint END AS estimated_total,
      (o.active AND p.active AND o.valid_from<=$5 AND (o.valid_until IS NULL OR o.valid_until>=$5) AND o.minimum_quantity<=$4 AND (u.fractional OR trunc($4::numeric)=$4) AND ROUND(COALESCE(tier.unit_cost,o.unit_cost)*$4)<=100000000000) AS eligible
      FROM supplier_offers o JOIN suppliers s ON s.tenant=o.tenant AND s.id=o.supplier JOIN products p ON p.tenant=o.tenant AND p.id=o.product JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id
      LEFT JOIN LATERAL (SELECT t.unit_cost,t.minimum_quantity FROM supplier_offer_tiers t WHERE t.tenant=o.tenant AND t.offer=o.id AND t.minimum_quantity<=$4 ORDER BY t.minimum_quantity DESC LIMIT 1) tier ON true
      WHERE o.tenant=$1 AND ($8='' OR o.supplier=$8) AND ($2='' OR o.product=$2) AND ($3='' OR strpos(lower(s.name||' '||p.name||' '||p.sku),lower($3))>0)
      AND (NOT $6 OR (o.active AND p.active AND o.valid_from<=$5 AND (o.valid_until IS NULL OR o.valid_until>=$5) AND o.minimum_quantity<=$4 AND (u.fractional OR trunc($4::numeric)=$4) AND ROUND(COALESCE(tier.unit_cost,o.unit_cost)*$4)<=100000000000))
      ORDER BY p.sku,effective_unit_cost,o.lead_days,s.name,o.id LIMIT 50 OFFSET $7""",
                tenant,
                product,
                q,
                quantity,
                today(),
                eligible,
                offset,
                supplier,
            )
            tier_rows = await c.fetch(
                "SELECT offer,minimum_quantity,unit_cost FROM supplier_offer_tiers WHERE tenant=$1 AND offer=ANY($2::text[]) ORDER BY minimum_quantity",
                tenant,
                [r["id"] for r in rows],
            )
            items = service.rows(rows)
            for item in items:
                item["tiers"] = [
                    dict(
                        minimum_quantity=t["minimum_quantity"], unit_cost=t["unit_cost"]
                    )
                    for t in tier_rows
                    if t["offer"] == item["id"]
                ]
            return {"items": items, "as_of": today(), "quantity": quantity}


@router.get("/supplier-performance")
async def performance(
    tenant: str,
    user: User,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "stock")
            rows = await c.fetch(
                """SELECT s.id,s.name,s.lead_days,
   COUNT(o.id) AS orders,COUNT(o.id) FILTER(WHERE o.status='received') AS completed,
   COUNT(o.id) FILTER(WHERE o.status='pending_approval') AS pending_approval,
   COUNT(o.id) FILTER(WHERE o.status IN ('open','partial')) AS open_orders,
   COUNT(o.id) FILTER(WHERE o.status IN ('open','partial') AND o.lead_days_snapshot IS NOT NULL AND now()>COALESCE(o.decided_on,o.created)+o.lead_days_snapshot*interval '1 day') AS late_open_orders,
   COUNT(first_receipt.created) AS delivery_samples,
   ROUND(AVG(EXTRACT(EPOCH FROM (first_receipt.created-COALESCE(o.decided_on,o.created)))/86400)::numeric,2) AS avg_first_delivery_days
   FROM suppliers s LEFT JOIN purchase_orders o ON o.tenant=s.tenant AND o.supplier=s.id
   LEFT JOIN LATERAL (SELECT MIN(r.created) AS created FROM purchase_receipts r WHERE r.tenant=o.tenant AND r.purchase=o.id) first_receipt ON true
   WHERE s.tenant=$1 AND ($2='' OR strpos(lower(s.name),lower($2))>0) GROUP BY s.id,s.name,s.lead_days
   ORDER BY s.name,s.id LIMIT 50 OFFSET $3""",
                tenant,
                q,
                offset,
            )
            return {"items": service.rows(rows), "as_of": today()}
