from fastapi import APIRouter
from .router import User
from .. import db, service
from ..rules import fail
from ..features.till_reports import build, obj

router = APIRouter(prefix="/api/v1/tenants/{tenant}/tills", tags=["Till reports"])


@router.get("/{identifier}/reports/{kind}")
async def report(tenant: str, identifier: str, kind: str, user: User):
    if kind not in ("X", "Z"):
        fail("Choose X or Z report.")
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read", readonly=True):
            await service.authorize(c, user, tenant, "sale")
            session = await c.fetchrow(
                "SELECT * FROM till_sessions WHERE tenant=$1 AND id=$2",
                tenant,
                identifier,
            )
            if not session:
                fail("Till session not found.", 404)
            if session["actor"] != user["id"]:
                await service.authorize(c, user, tenant, "finance")
            if kind == "X":
                if session["status"] != "open":
                    fail("Use the frozen Z report for a closed session.", 409)
                return {"report": await build(c, tenant, session), "digest": None}
            saved = await c.fetchrow(
                "SELECT snapshot,digest FROM till_z_reports WHERE tenant=$1 AND session=$2",
                tenant,
                identifier,
            )
            if not saved:
                fail(
                    "No frozen Z report exists. Reports are generated when sessions close after this upgrade.",
                    409,
                )
            return {"report": obj(saved["snapshot"]), "digest": saved["digest"]}
