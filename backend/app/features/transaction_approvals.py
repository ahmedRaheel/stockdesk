"""Single-use, actor-bound approval of an exact transaction, under the tenant lock."""
import hashlib
import json
from .. import service
from ..rules import fail


def normalized(kind, payload):
    from ..api.contracts import Checkout, ReturnSale
    from ..api.exchanges import Commit
    model = {'discount': Checkout, 'return': ReturnSale, 'adjustment': Commit}[kind]
    data = {k:v for k,v in payload.items() if k not in ('tenant','action','id','approval_id')}
    if kind != 'return':
        data.setdefault('request', 'approval-preview')
    from pydantic import ValidationError
    try:
        value = model.model_validate(data).model_dump(mode='json', exclude={'request','approval_id'})
    except ValidationError:
        fail('Invalid approval transaction payload.', 422)
    # Quantity spellings (1, 1.0, 1.000) must describe the same transaction.
    from decimal import Decimal
    def canonical(v):
        if isinstance(v,list):
            return [canonical(x) for x in v]
        if isinstance(v,dict):
            return {k: format(Decimal(str(x)).normalize(),'f') if k=='quantity' else canonical(x) for k,x in v.items()}
        return v
    return canonical(value)


def fingerprint(kind, sale, value):
    return hashlib.sha256(json.dumps({'kind':kind,'sale':sale,'payload':value},sort_keys=True,separators=(',',':')).encode()).hexdigest()


async def consume(c, user, tenant, kind, payload, sale=None):
    key = 'discount_approval_required' if kind == 'discount' else 'void_approval_required'
    if not await c.fetchval(f'SELECT {key} FROM tenants WHERE id=$1',tenant):
        return
    if kind == 'discount' and not payload.get('discount',0):
        return
    identifier = payload.get('approval_id')
    approval = await c.fetchrow('SELECT * FROM transaction_approvals WHERE tenant=$1 AND id=$2 FOR UPDATE',tenant,identifier or '')
    if not approval or approval['status']!='approved' or approval['requester']!=user['id']:
        fail('An independent approval is required for this exact transaction.',409)
    value=normalized(kind,payload)
    if approval['fingerprint']!=fingerprint(kind,sale,value) or approval['expires'] <= await c.fetchval('SELECT now()'):
        fail('Approval expired or transaction changed. Request a new approval.',409)
    # Revoked membership/permission invalidates even a previously approved request.
    approver = await c.fetchrow('SELECT * FROM users WHERE id=$1',approval['decision_by'])
    if not approver or not approver['active']:
        fail('The approver account is no longer active.', 403)
    await service.authorize(c,dict(approver),tenant,'discount_approve' if kind=='discount' else 'void_approve')
    await c.execute("UPDATE transaction_approvals SET status='consumed',consumed=now() WHERE tenant=$1 AND id=$2",tenant,identifier)
    await service.audit(c,tenant,user,'Transaction approval consumed',{'approval':identifier,'kind':kind,'sale':sale})
