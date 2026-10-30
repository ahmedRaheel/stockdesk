"""Transactional, permission-rechecked scheduled report snapshots; no outbound delivery."""

import asyncio
import json
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from .. import db, service
from ..api.report_builder import Definition, build
from ..api.reports import load_management_report

ZONE = ZoneInfo("Asia/Karachi")


def next_slot(now, frequency, weekday, hour, minute):
    local = now.astimezone(ZONE)
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if frequency == "weekly":
        target += timedelta(days=(weekday - target.weekday()) % 7)
        if target <= local:
            target += timedelta(days=7)
    elif target <= local:
        target += timedelta(days=1)
    return target


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


async def process_schedule(identifier):
    async with db.pool.acquire() as c:
        async with c.transaction():
            tenant = await c.fetchval(
                "SELECT tenant FROM report_schedules WHERE id=$1", identifier
            )
            if not tenant:
                return
            status = await c.fetchval(
                "SELECT status FROM tenants WHERE id=$1 FOR UPDATE", tenant
            )
            if status != "active":
                return
            row = await c.fetchrow(
                "SELECT * FROM report_schedules WHERE id=$1 FOR UPDATE", identifier
            )
            now = await c.fetchval("SELECT now()")
            if (
                not row["active"]
                or row["next_run"] > now
                or (row["retry_after"] and row["retry_after"] > now)
            ):
                return
            prior = await c.fetchrow(
                "SELECT * FROM report_runs WHERE tenant=$1 AND schedule=$2 AND scheduled_for=$3",
                tenant,
                identifier,
                row["next_run"],
            )
            if prior and prior["status"] != "retrying":
                return
            attempts = prior["attempts"] + 1 if prior else 1
            rid = prior["id"] if prior else service.uid()
            owner = await c.fetchrow(
                "SELECT * FROM users WHERE id=$1 AND active", row["owner_id"]
            )
            blocked = False
            try:
                if not owner:
                    raise HTTPException(403, "Inactive schedule owner")
                await service.authorize(c, owner, tenant, "cost")
            except HTTPException:
                blocked = True
            result = None
            error = ""
            final = False
            if blocked:
                error = "Schedule paused: its owner no longer has report access."
                final = True
            else:
                try:
                    # A savepoint keeps failed report SQL from aborting the run record.
                    async with c.transaction():
                        definition = Definition(**decoded(row["definition"]))
                        end = row["next_run"].astimezone(ZONE).date() - timedelta(
                            days=1
                        )
                        data = await load_management_report(
                            c, tenant, owner, definition.days, end
                        )
                        result = build(data, definition)
                        result["definition"]["end"] = str(end)
                        encoded = json.dumps(result, default=str)
                        if len(encoded.encode()) > 2_000_000:
                            raise HTTPException(422, "Snapshot exceeds size limit")
                except HTTPException:
                    error = "Report could not be generated within its data limits. Review the saved definition."
                    final = True
                    result = None
                except Exception:
                    logging.getLogger("stockdesk").exception(
                        "Scheduled report failed: %s", identifier
                    )
                    error = "Report generation failed. The worker will retry up to three attempts."
                    result = None
            state = (
                "succeeded"
                if result is not None
                else "failed" if final or attempts >= 3 else "retrying"
            )
            now = await c.fetchval("SELECT clock_timestamp()")
            if state == "failed" and attempts >= 3 and not final:
                error = "Report generation failed after three attempts."
            await c.execute(
                """INSERT INTO report_runs(id,tenant,schedule,scheduled_for,definition,status,attempts,result,error,finished,schedule_name,owner_email)
              VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8::jsonb,$9,CASE WHEN $6='retrying' THEN NULL ELSE clock_timestamp() END,$10,$11)
              ON CONFLICT(tenant,schedule,scheduled_for) DO UPDATE SET status=excluded.status,attempts=excluded.attempts,result=excluded.result,error=excluded.error,finished=excluded.finished""",
                rid,
                tenant,
                identifier,
                row["next_run"],
                json.dumps(decoded(row["definition"])),
                state,
                attempts,
                json.dumps(result, default=str) if result is not None else None,
                error,
                row["name"],
                (
                    owner["email"]
                    if owner
                    else await c.fetchval(
                        "SELECT email FROM users WHERE id=$1", row["owner_id"]
                    )
                ),
            )
            if state == "retrying":
                await c.execute(
                    "UPDATE report_schedules SET retry_after=$1 WHERE id=$2",
                    now + timedelta(seconds=60 if attempts == 1 else 300),
                    identifier,
                )
            else:
                following = next_slot(
                    now, row["frequency"], row["weekday"], row["hour"], row["minute"]
                )
                await c.execute(
                    "UPDATE report_schedules SET next_run=$1,retry_after=NULL,active=CASE WHEN $2 THEN false ELSE active END,version=version+CASE WHEN $2 THEN 1 ELSE 0 END WHERE id=$3",
                    following,
                    blocked,
                    identifier,
                )
            await service.audit(
                c,
                tenant,
                dict(email="system:scheduled-reports"),
                "Scheduled report " + state,
                dict(schedule=identifier, run=rid, attempt=attempts),
            )
            # Bounded retention: keep the most recent 30 runs for each schedule.
            await c.execute(
                "DELETE FROM report_runs WHERE tenant=$1 AND schedule=$2 AND id NOT IN (SELECT id FROM report_runs WHERE tenant=$1 AND schedule=$2 ORDER BY created DESC,id DESC LIMIT 30)",
                tenant,
                identifier,
            )
            return state


async def worker_once(tenant=None):
    async with db.pool.acquire() as c:
        rows = await c.fetch(
            """SELECT r.id FROM report_schedules r JOIN tenants t ON t.id=r.tenant
          WHERE t.status='active' AND r.active AND r.next_run<=now() AND (r.retry_after IS NULL OR r.retry_after<=now())
          AND ($1::text IS NULL OR r.tenant=$1) ORDER BY r.next_run,r.id LIMIT 100""",
            tenant,
        )
    counts = {}
    for row in rows:
        try:
            state = await process_schedule(row["id"])
            if state:
                counts[state] = counts.get(state, 0) + 1
        except Exception:
            logging.getLogger("stockdesk").exception(
                "Scheduled report transaction failed: %s", row["id"]
            )
    return counts


async def run_worker():
    while True:
        try:
            await worker_once()
        except Exception:
            logging.getLogger("stockdesk").exception("Report scheduler pass failed")
        await asyncio.sleep(30)
