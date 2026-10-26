"""Persistent inventory alert episodes. Callers hold the tenant write lock."""

import asyncio
import json
import logging
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from .. import db, service
from ..rules import business_date, fail


def quiet_now(rule, now):
    start, end = rule.get("quiet_start"), rule.get("quiet_end")
    if start is None or end is None:
        return False
    local = now.astimezone(ZoneInfo("Asia/Karachi"))
    minute = local.hour * 60 + local.minute
    return start <= minute < end if start < end else minute >= start or minute < end


async def evaluate(c, tenant, user, due_only=False):
    rules = await c.fetch(
        "SELECT * FROM inventory_alert_rules WHERE tenant=$1 AND active=true AND ($2=false OR last_evaluated IS NULL OR last_evaluated<=now()-interval '60 seconds') ORDER BY id",
        tenant,
        due_only,
    )
    opened = resolved = escalated = deferred = 0
    now = await c.fetchval("SELECT now()")
    for rule in rules:
        quiet = quiet_now(rule, now)
        if rule["kind"] == "expiry":
            matches = await c.fetch(
                """SELECT b.id AS entity,p.id AS product,p.sku,p.name,b.lot,b.expires,b.stock,l.name AS unit
             FROM stock_batches b JOIN products p ON p.tenant=b.tenant AND p.id=b.product
             JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id
             WHERE b.tenant=$1 AND p.active AND b.stock>0 AND b.expires<=$2
               AND ($3::text IS NULL OR p.id=$3) ORDER BY b.id LIMIT 5001""",
                tenant,
                business_date() + timedelta(days=rule["expiry_days"]),
                rule["product"],
            )
        else:
            matches = await c.fetch(
                """SELECT p.id AS entity,p.id AS product,p.sku,p.name,p.stock,l.name AS unit,
              CASE WHEN $4='stock_out' THEN 0 ELSE COALESCE($3,p.reorder) END AS threshold
              FROM products p JOIN lookups l ON l.tenant=p.tenant AND l.id=p.unit_id
              WHERE p.tenant=$1 AND p.active AND ($2::text IS NULL OR p.id=$2)
              AND p.stock<=CASE WHEN $4='stock_out' THEN 0 ELSE COALESCE($3,p.reorder) END
              ORDER BY p.id LIMIT 5001""",
                tenant,
                rule["product"],
                rule["threshold"],
                rule["kind"],
            )
        if len(matches) > 5000:
            fail(
                "Alert rule matches more than 5000 items. Narrow its product scope.",
                422,
            )
        existing = {
            r["entity"]: r
            for r in await c.fetch(
                "SELECT id,entity FROM inventory_alerts WHERE tenant=$1 AND rule=$2 AND status IN ('open','acknowledged')",
                tenant,
                rule["id"],
            )
        }
        records = []
        for row in matches:
            prior = existing.pop(row["entity"], None)
            if quiet and not prior:
                deferred += 1
                continue
            records.append(
                dict(
                    id=prior["id"] if prior else service.uid(),
                    entity=row["entity"],
                    details=dict(row),
                )
            )
            if not prior:
                opened += 1
        if records:
            await c.execute(
                """INSERT INTO inventory_alerts(id,tenant,rule,entity,rule_name,kind,severity,details)
              SELECT x.id,$1,$2,x.entity,$3,$4,$5,x.details FROM jsonb_to_recordset($6::jsonb) AS x(id text,entity text,details jsonb)
              ON CONFLICT(tenant,rule,entity) WHERE status IN ('open','acknowledged')
              DO UPDATE SET details=excluded.details,last_seen=now()""",
                tenant,
                rule["id"],
                rule["name"],
                rule["kind"],
                rule["severity"],
                json.dumps(records, default=str),
            )
        if existing:
            await c.execute(
                "UPDATE inventory_alerts SET status='resolved',resolved=now(),resolution='condition_cleared' WHERE tenant=$1 AND id=ANY($2::text[])",
                tenant,
                [r["id"] for r in existing.values()],
            )
            resolved += len(existing)
        if not quiet and rule["escalate_after_minutes"] is not None:
            # Resolve cleared conditions first, then escalate only still-open episodes.
            promoted = await c.fetch(
                "UPDATE inventory_alerts SET escalated_from=severity,severity='critical',escalated_at=now(),escalation_minutes=$3 WHERE tenant=$1 AND rule=$2 AND status='open' AND severity IN ('info','warning') AND escalated_at IS NULL AND opened <= now()-($3::integer * interval '1 minute') RETURNING id",
                tenant,
                rule["id"],
                rule["escalate_after_minutes"],
            )
            if promoted:
                escalated += len(promoted)
                await service.audit(
                    c,
                    tenant,
                    user,
                    "Inventory alerts escalated",
                    dict(
                        rule=rule["id"],
                        count=len(promoted),
                        after_minutes=rule["escalate_after_minutes"],
                        severity="critical",
                    ),
                )
        await c.execute(
            "UPDATE inventory_alert_rules SET last_evaluated=now() WHERE tenant=$1 AND id=$2",
            tenant,
            rule["id"],
        )
    if opened or resolved:
        await service.audit(
            c,
            tenant,
            user,
            "Inventory alerts evaluated",
            dict(opened=opened, resolved=resolved),
        )
    return dict(
        evaluated=len(rules),
        opened=opened,
        resolved=resolved,
        escalated=escalated,
        deferred=deferred,
    )


async def worker_once(after=""):
    # Each worker rechecks due rules after obtaining the shared tenant lock.
    async with db.pool.acquire() as c:
        tenants = await c.fetch(
            """SELECT t.id FROM tenants t WHERE t.status='active' AND t.id>$1 AND EXISTS(
          SELECT 1 FROM inventory_alert_rules r WHERE r.tenant=t.id AND r.active
          AND (r.last_evaluated IS NULL OR r.last_evaluated<=now()-interval '60 seconds')) ORDER BY t.id LIMIT 100""",
            after,
        )
    for tenant in tenants:
        try:
            async with db.pool.acquire() as c:
                async with c.transaction():
                    status = await c.fetchval(
                        "SELECT status FROM tenants WHERE id=$1 FOR UPDATE",
                        tenant["id"],
                    )
                    if status == "active":
                        await evaluate(
                            c, tenant["id"], dict(email="system:inventory-alerts"), True
                        )
        except Exception:
            logging.getLogger("stockdesk").exception(
                "Inventory alert evaluation failed for tenant %s", tenant["id"]
            )

    return tenants[-1]["id"] if len(tenants) == 100 else ""


async def run_worker():
    cursor = ""
    while True:
        try:
            cursor = await worker_once(cursor)
        except Exception:
            logging.getLogger("stockdesk").exception(
                "Inventory alert worker pass failed"
            )
        await asyncio.sleep(30)
