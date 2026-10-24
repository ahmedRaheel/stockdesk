"""Tenant-scoped reference validation; labels are never trusted as identifiers."""

from ..rules import fail


async def lookup(c, tenant, identifier, kind, allow_inactive=False):
    record = await c.fetchrow(
        "SELECT * FROM lookups WHERE tenant=$1 AND id=$2 AND kind=$3",
        tenant,
        identifier,
        kind,
    )
    if not record or (not allow_inactive and not record["active"]):
        fail(f'Choose an active {kind.replace("_"," ")} from this business.', 400)
    return record
