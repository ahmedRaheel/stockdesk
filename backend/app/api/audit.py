"""Read-only tenant audit search, independently permissioned from team administration."""

from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from .router import User, authenticated
from .. import db, service
from ..rules import fail

router = APIRouter(
    prefix="/api/v1/tenants/{tenant}/audit-events",
    dependencies=[Depends(authenticated)],
    tags=["Audit"],
)


@router.get("")
async def events(
    tenant: str,
    user: User,
    q: str = Query("", max_length=150),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if start and end and start > end:
        fail("Start date must not follow end date.")
    if end and end.year == 9999:
        fail("End date is outside the supported range.")
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "audit")
            clause = "tenant=$1 AND ($2='' OR strpos(lower(actor||' '||action||' '||details),lower($2))>0) AND ($3::date IS NULL OR created >= ($3::timestamp AT TIME ZONE 'UTC')) AND ($4::date IS NULL OR created < ($4::timestamp AT TIME ZONE 'UTC'))"
            params = (tenant, q, start, end + timedelta(days=1) if end else None)
            total = await c.fetchval(
                "SELECT COUNT(*) FROM audit WHERE " + clause, *params
            )
            rows = await c.fetch(
                "SELECT id,created,actor,action,details FROM audit WHERE "
                + clause
                + " ORDER BY created DESC,id DESC LIMIT $5 OFFSET $6",
                *params,
                limit,
                offset
            )
            return {
                "items": service.rows(rows),
                "total": total,
                "limit": limit,
                "offset": offset,
                "timezone": "UTC",
            }
